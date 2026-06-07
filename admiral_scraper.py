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
        return events

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
