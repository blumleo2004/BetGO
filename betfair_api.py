"""
BETGO Betfair Exchange API Integration
Fetches live exchange odds from Betfair to complement The Odds API data.
Credentials stored in api_keys.json under 'betfair' key.
"""

import requests
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


BETFAIR_LOGIN_URL = 'https://identitysso.betfair.com/api/login'
BETFAIR_API_URL = 'https://api.betfair.com/exchange/betting/rest/v1.0'

_CREDS_PATH = Path(__file__).parent / 'api_keys.json'


def _load_creds() -> dict:
    if _CREDS_PATH.exists():
        try:
            with open(_CREDS_PATH, 'r') as f:
                data = json.load(f)
                return data.get('betfair', {})
        except Exception:
            pass
    return {}


def _save_creds(username: str, password: str, app_key: str):
    data = {}
    if _CREDS_PATH.exists():
        try:
            with open(_CREDS_PATH, 'r') as f:
                data = json.load(f)
        except Exception:
            pass
    data['betfair'] = {'username': username, 'password': password, 'app_key': app_key}
    with open(_CREDS_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def _normalize_team(name: str) -> str:
    """Normalize team name for fuzzy matching across APIs."""
    name = name.lower().strip()
    for suffix in [' fc', ' cf', ' sc', ' ac', ' afc', ' utd', ' united',
                   ' city', ' town', ' athletic', ' athletico']:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    return name


def _teams_match(betfair_name: str, odds_api_name: str) -> bool:
    """Check if two team names refer to the same team."""
    a = _normalize_team(betfair_name)
    b = _normalize_team(odds_api_name)
    return a == b or a in b or b in a


class BetfairSession:
    def __init__(self):
        self.token: Optional[str] = None
        self.app_key: Optional[str] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.token_expires: Optional[datetime] = None
        self._load_from_file()

    def _load_from_file(self):
        creds = _load_creds()
        self.username = creds.get('username')
        self.password = creds.get('password')
        self.app_key = creds.get('app_key')

    def configure(self, username: str, password: str, app_key: str):
        self.username = username
        self.password = password
        self.app_key = app_key
        _save_creds(username, password, app_key)

    def is_configured(self) -> bool:
        return bool(self.username and self.password and self.app_key)

    def login(self) -> tuple[bool, str]:
        """Login and get session token. Returns (success, error_msg)."""
        if not self.is_configured():
            return False, 'Keine Betfair-Zugangsdaten konfiguriert'
        try:
            resp = requests.post(
                BETFAIR_LOGIN_URL,
                data={'username': self.username, 'password': self.password},
                headers={
                    'X-Application': self.app_key,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=10,
            )
            data = resp.json()
            if data.get('status') == 'SUCCESS':
                self.token = data['token']
                # Betfair tokens expire after 4h of inactivity
                self.token_expires = datetime.utcnow() + timedelta(hours=3, minutes=50)
                return True, ''
            return False, data.get('error', 'Login fehlgeschlagen')
        except Exception as e:
            return False, str(e)

    def ensure_logged_in(self) -> bool:
        if not self.token or (self.token_expires and datetime.utcnow() >= self.token_expires):
            ok, _ = self.login()
            return ok
        return True

    def _headers(self) -> dict:
        return {
            'X-Application': self.app_key,
            'X-Authentication': self.token,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def api_call(self, endpoint: str, payload: dict) -> Optional[list]:
        """Call a Betfair APING endpoint. Returns parsed JSON or None."""
        if not self.ensure_logged_in():
            return None
        try:
            resp = requests.post(
                f'{BETFAIR_API_URL}/{endpoint}/',
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            print(f'[Betfair] {endpoint} HTTP {resp.status_code}: {resp.text[:200]}')
            return None
        except Exception as e:
            print(f'[Betfair] {endpoint} error: {e}')
            return None


class BetfairOddsProvider:
    """Fetches Betfair Exchange odds in BetGO-compatible format."""

    # Betfair event type IDs
    SPORT_IDS = {
        'soccer': '1',
        'tennis': '2',
        'basketball': '7522',
        'american_football': '6423',
        'ice_hockey': '7524',
    }

    def __init__(self):
        self.session = BetfairSession()

    def configure(self, username: str, password: str, app_key: str) -> dict:
        self.session.configure(username, password, app_key)
        return self.get_status()

    def get_status(self) -> dict:
        configured = self.session.is_configured()
        logged_in = False
        error = None
        if configured and not self.session.token:
            ok, err = self.session.login()
            logged_in = ok
            error = err if not ok else None
        elif configured:
            logged_in = bool(self.session.token)
        return {
            'configured': configured,
            'logged_in': logged_in,
            'username': self.session.username,
            'token_expires': self.session.token_expires.isoformat() if self.session.token_expires else None,
            'error': error,
        }

    def get_odds(self, sport: str = 'soccer', hours_ahead: int = 24) -> list:
        """
        Fetch Match Odds for a sport in the next N hours.
        Returns list of game dicts in BetGO/The-Odds-API format.
        """
        if not self.session.is_configured():
            return []

        sport_id = self.SPORT_IDS.get(sport, '1')
        now = datetime.now(timezone.utc)
        until = now + timedelta(hours=hours_ahead)

        # Step 1: list market catalogue to get event names + runner names
        catalogue = self.session.api_call('listMarketCatalogue', {
            'filter': {
                'eventTypeIds': [sport_id],
                'marketTypeCodes': ['MATCH_ODDS'],
                'marketStartTime': {
                    'from': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'to': until.strftime('%Y-%m-%dT%H:%M:%SZ'),
                },
            },
            'marketProjection': ['EVENT', 'RUNNER_DESCRIPTION', 'MARKET_START_TIME'],
            'maxResults': 200,
        })

        if not catalogue:
            return []

        # Build lookup maps
        runner_names: dict[str, dict[int, str]] = {}   # marketId -> {selectionId -> name}
        event_info: dict[str, dict] = {}                # marketId -> {home, away, start_time}

        for m in catalogue:
            mid = m['marketId']
            runner_names[mid] = {
                r['selectionId']: r['runnerName']
                for r in m.get('runners', [])
            }
            ev = m.get('event', {})
            name = ev.get('name', '')
            # Betfair format: "Home v Away" or "Home vs Away"
            sep = ' v ' if ' v ' in name else ' vs '
            parts = name.split(sep, 1)
            event_info[mid] = {
                'home': parts[0].strip() if len(parts) == 2 else name,
                'away': parts[1].strip() if len(parts) == 2 else '',
                'start_time': m.get('marketStartTime', ''),
                'event_id': ev.get('id', ''),
            }

        market_ids = list(runner_names.keys())
        if not market_ids:
            return []

        # Step 2: get live best-back prices (process in batches of 50)
        all_books = []
        for i in range(0, len(market_ids), 50):
            batch = market_ids[i:i + 50]
            books = self.session.api_call('listMarketBook', {
                'marketIds': batch,
                'priceProjection': {
                    'priceData': ['EX_BEST_OFFERS'],
                    'exBestOffersOverrides': {'bestPricesDepth': 1},
                },
            })
            if books:
                all_books.extend(books)

        # Step 3: convert to BetGO format
        results = []
        for book in all_books:
            mid = book['marketId']
            runners_map = runner_names.get(mid, {})
            ev = event_info.get(mid, {})

            outcomes = []
            for runner in book.get('runners', []):
                if runner.get('status') != 'ACTIVE':
                    continue
                sel_id = runner['selectionId']
                name = runners_map.get(sel_id, str(sel_id))
                back = runner.get('ex', {}).get('availableToBack', [])
                if not back:
                    continue
                best_price = back[0]['price']
                if best_price <= 1.0:
                    continue
                outcomes.append({'name': name, 'price': best_price})

            if len(outcomes) < 2:
                continue

            results.append({
                'id': f'betfair_{mid}',
                'sport_key': f'{sport}_betfair',
                'sport_title': f'{sport.capitalize()} (Betfair Exchange)',
                'home_team': ev.get('home', ''),
                'away_team': ev.get('away', ''),
                'commence_time': ev.get('start_time', ''),
                'bookmakers': [{
                    'key': 'betfair_ex_eu',
                    'title': 'Betfair Exchange',
                    'markets': [{
                        'key': 'h2h',
                        'outcomes': outcomes,
                    }]
                }]
            })

        return results

    def merge_with_odds_api(self, odds_api_games: list, betfair_games: list) -> list:
        """
        Merge Betfair odds into The Odds API game list.
        For matching events: adds Betfair as an additional bookmaker.
        For unmatched Betfair events: appends as standalone games.
        Matching: both teams fuzzy-match AND start times within 60 min.
        """
        merged = [dict(g) for g in odds_api_games]
        matched_bf_ids = set()

        for bf_game in betfair_games:
            bf_home = bf_game['home_team']
            bf_away = bf_game['away_team']
            bf_time = bf_game.get('commence_time', '')

            best_match = None
            for api_game in merged:
                if not _teams_match(bf_home, api_game.get('home_team', '')):
                    continue
                if not _teams_match(bf_away, api_game.get('away_team', '')):
                    continue
                # Check time proximity (within 60 minutes)
                try:
                    t_bf = datetime.fromisoformat(bf_time.replace('Z', '+00:00'))
                    t_api = datetime.fromisoformat(
                        api_game['commence_time'].replace('Z', '+00:00')
                    )
                    if abs((t_bf - t_api).total_seconds()) > 3600:
                        continue
                except Exception:
                    pass
                best_match = api_game
                break

            if best_match is not None:
                # Add Betfair as additional bookmaker to existing game
                bf_books = bf_game.get('bookmakers', [])
                existing_keys = {b['key'] for b in best_match.get('bookmakers', [])}
                for bk in bf_books:
                    if bk['key'] not in existing_keys:
                        best_match.setdefault('bookmakers', []).append(bk)
                matched_bf_ids.add(bf_game['id'])
            else:
                # Unmatched — add as standalone (Betfair-only game)
                merged.append(bf_game)
                matched_bf_ids.add(bf_game['id'])

        return merged


# ── Global instance ───────────────────────────────────────────────────────────
provider = BetfairOddsProvider()


def configure(username: str, password: str, app_key: str) -> dict:
    return provider.configure(username, password, app_key)


def get_status() -> dict:
    return provider.get_status()


def get_soccer_odds(hours_ahead: int = 24) -> list:
    return provider.get_odds('soccer', hours_ahead)


def merge_with_odds_api(odds_api_games: list, betfair_games: list) -> list:
    return provider.merge_with_odds_api(odds_api_games, betfair_games)
