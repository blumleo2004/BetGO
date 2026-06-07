import hashlib
import json
import logging
import threading
import time
import requests

logger = logging.getLogger(__name__)

_ENDPOINT_CANDIDATES = [
    "https://eu-offering-api.kambicdn.com/offering/v2018/admiralatlet/listView/football.json",
    "https://eu-offering-api.kambicdn.com/offering/v2018/admiral/listView/football.json",
    "https://eu-offering-api.kambicdn.com/offering/v2018/admiralbet/listView/football.json",
    "https://eu-offering-api.kambicdn.com/offering/v2018/admiralat/listView/football.json",
]

_PARAMS = {"lang": "de_AT", "market": "AT", "limit": 50}


class AdmiralScraper:
    def __init__(self, notifier=None):
        self.notifier = notifier
        self._endpoint = None
        self._schema_baseline = None
        self._paused = False
        self.running = False
        self._thread = None

    def _discover_endpoint(self):
        for url in _ENDPOINT_CANDIDATES:
            try:
                resp = requests.get(url, params=_PARAMS, timeout=8)
                if resp.status_code == 200:
                    logger.info(f"[Admiral] Endpoint found: {url}")
                    return url
            except Exception:
                continue
        return None

    def _schema_hash(self, data):
        def extract_keys(obj):
            if isinstance(obj, dict):
                return {k: extract_keys(v) for k, v in sorted(obj.items())}
            elif isinstance(obj, list) and obj:
                return [extract_keys(obj[0])]
            return None

        skeleton = extract_keys(data)
        return hashlib.sha256(json.dumps(skeleton, sort_keys=True).encode()).hexdigest()

    def _fetch_odds(self):
        if not self._endpoint:
            self._endpoint = self._discover_endpoint()
        if not self._endpoint:
            logger.warning("[Admiral] No working endpoint found")
            return None
        try:
            resp = requests.get(self._endpoint, params=_PARAMS, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[Admiral] Fetch error: {e}")
            return None

    def _check_canary(self, data):
        current_hash = self._schema_hash(data)
        if self._schema_baseline is None:
            self._schema_baseline = current_hash
            logger.info(f"[Admiral] Schema baseline set: {current_hash[:12]}...")
            return True
        if current_hash != self._schema_baseline:
            logger.error(f"[Admiral] Schema changed! {self._schema_baseline[:12]} -> {current_hash[:12]}")
            return False
        return True

    def _parse_wm_events(self, data):
        events = []
        raw = data.get("events") or data.get("result") or []
        for item in raw:
            event = item.get("event") or item
            name = event.get("name", "")
            group = (event.get("group", "") + " " + event.get("groupId", "")).lower()
            if "world cup" not in group and "wm" not in group and "fifa" not in name.lower():
                continue
            parts = name.split(" - ") if " - " in name else name.split(" v ")
            if len(parts) < 2:
                continue
            home, away = parts[0].strip(), parts[1].strip()
            outcomes = []
            for offer in item.get("betOffers", []):
                if offer.get("betOfferType", {}).get("name") == "Match":
                    for outcome in offer.get("outcomes", []):
                        label = outcome.get("label", "")
                        odds_val = outcome.get("odds", 0) / 1000
                        if odds_val > 1.0:
                            outcomes.append({"name": label, "odds": odds_val})
            if outcomes:
                events.append({"home": home, "away": away, "outcomes": outcomes})
        return events

    def scan_once(self):
        if self._paused:
            return []

        data = self._fetch_odds()
        if data is None:
            return []

        if not self._check_canary(data):
            self._paused = True
            if self.notifier:
                self.notifier.send(
                    "*Admiral API Schema geändert — Scraper pausiert*\n"
                    "Bitte `admiral_scraper.py` prüfen und Railway neu deployen."
                )
            return []

        events = self._parse_wm_events(data)
        logger.info(f"[Admiral] {len(events)} WM events found")

        arbs_found = []
        try:
            import arb_engine
            engine = arb_engine.ArbEngine()
            betfair_data = engine.get_odds('soccer_fifa_world_cup', bookmakers=['betfair_ex_eu'])
            for adm_event in events:
                for bf_game in betfair_data:
                    home_match = adm_event['home'].lower() in bf_game.get('home_team', '').lower()
                    away_match = adm_event['away'].lower() in bf_game.get('away_team', '').lower()
                    if not (home_match or away_match):
                        continue
                    for adm_outcome in adm_event['outcomes']:
                        for bf_book in bf_game.get('bookmakers', []):
                            if bf_book.get('key') != 'betfair_ex_eu':
                                continue
                            for mkt in bf_book.get('markets', []):
                                for bf_outcome in mkt.get('outcomes', []):
                                    if adm_outcome['name'].lower() not in bf_outcome.get('name', '').lower():
                                        continue
                                    combined = 1 / adm_outcome['odds'] + 1 / bf_outcome['price']
                                    if combined < 1.0:
                                        roi = round((1 / combined - 1) * 100, 2)
                                        if roi >= 0.3:
                                            arb = {
                                                'home_team': adm_event['home'],
                                                'away_team': adm_event['away'],
                                                'roi': roi,
                                                'bets': [
                                                    {'bookmaker': 'Admiral', 'bookmaker_key': 'admiral',
                                                     'outcome': adm_outcome['name'], 'odds': adm_outcome['odds'],
                                                     'stake': 100 / (combined * adm_outcome['odds'] * 100)},
                                                    {'bookmaker': 'Betfair', 'bookmaker_key': 'betfair_ex_eu',
                                                     'outcome': bf_outcome['name'], 'odds': bf_outcome['price'],
                                                     'stake': 100 / (combined * bf_outcome['price'] * 100)},
                                                ]
                                            }
                                            arbs_found.append(arb)
                                            if self.notifier:
                                                self.notifier.notify_arb_found(arb)
                                            logger.info(f"[Admiral] ARB: {adm_event['home']} vs {adm_event['away']} {roi}% ROI")
        except Exception as e:
            logger.warning(f"[Admiral] Betfair comparison error: {e}")

        return arbs_found

    def _run_loop(self, interval_seconds=600):
        logger.info("[Admiral] Scraper thread started")
        while self.running:
            try:
                self.scan_once()
            except Exception as e:
                logger.error(f"[Admiral] Unexpected error: {e}")
            for _ in range(interval_seconds):
                if not self.running:
                    break
                time.sleep(1)

    def start(self, interval_seconds=600):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop,
                                        args=(interval_seconds,), daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
