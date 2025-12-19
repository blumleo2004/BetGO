"""
BETGO - API-Sports Integration
Second data source for more API credits (100 requests/day free)
https://api-sports.io/

Covers: Football (Soccer), Basketball, NHL, NFL, Baseball, Tennis, etc.
"""

import requests
from datetime import datetime
from typing import Optional, List

# API-Sports base URLs
API_SPORTS_URLS = {
    'football': 'https://v3.football.api-sports.io',
    'basketball': 'https://v1.basketball.api-sports.io',
    'hockey': 'https://v1.hockey.api-sports.io',
    'baseball': 'https://v1.baseball.api-sports.io',
}

# Mapping from The Odds API sport keys to API-Sports endpoints
SPORT_MAPPING = {
    # Soccer/Football
    'soccer_epl': {'sport': 'football', 'league': 39},  # Premier League
    'soccer_germany_bundesliga': {'sport': 'football', 'league': 78},
    'soccer_spain_la_liga': {'sport': 'football', 'league': 140},
    'soccer_italy_serie_a': {'sport': 'football', 'league': 135},
    'soccer_france_ligue_one': {'sport': 'football', 'league': 61},
    'soccer_uefa_champs_league': {'sport': 'football', 'league': 2},
    'soccer_uefa_europa_league': {'sport': 'football', 'league': 3},
    'soccer_austria_bundesliga': {'sport': 'football', 'league': 218},
    
    # US Sports
    'basketball_nba': {'sport': 'basketball', 'league': 12},
    'basketball_ncaab': {'sport': 'basketball', 'league': 116},
    'icehockey_nhl': {'sport': 'hockey', 'league': 57},
    'baseball_mlb': {'sport': 'baseball', 'league': 1},
}


class APISportsClient:
    """Client for API-Sports data fetching"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.remaining_requests = None
        self.requests_used = 0
    
    def set_api_key(self, api_key: str):
        """Set API key"""
        self.api_key = api_key
    
    def _make_request(self, sport: str, endpoint: str, params: dict = None) -> dict:
        """Make request to API-Sports"""
        if not self.api_key:
            return {'error': 'No API key set'}
        
        base_url = API_SPORTS_URLS.get(sport)
        if not base_url:
            return {'error': f'Unknown sport: {sport}'}
        
        headers = {
            'x-apisports-key': self.api_key
        }
        
        try:
            response = requests.get(
                f'{base_url}/{endpoint}',
                headers=headers,
                params=params or {}
            )
            
            # Track usage
            if 'x-ratelimit-requests-remaining' in response.headers:
                self.remaining_requests = int(response.headers['x-ratelimit-requests-remaining'])
            
            self.requests_used += 1
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'API error: {response.status_code}'}
        except Exception as e:
            return {'error': str(e)}
    
    def get_usage(self) -> dict:
        """Get API usage stats"""
        return {
            'remaining': self.remaining_requests,
            'used': self.requests_used
        }
    
    def get_fixtures(self, sport: str, league: int, next_hours: int = 24) -> List[dict]:
        """Get upcoming fixtures/games"""
        # Calculate date range
        today = datetime.now().strftime('%Y-%m-%d')
        
        if sport == 'football':
            result = self._make_request(sport, 'fixtures', {
                'league': league,
                'from': today,
                'status': 'NS',  # Not Started
                'timezone': 'Europe/Vienna'
            })
        elif sport == 'basketball':
            result = self._make_request(sport, 'games', {
                'league': league,
                'date': today,
                'timezone': 'Europe/Vienna'
            })
        elif sport == 'hockey':
            result = self._make_request(sport, 'games', {
                'league': league,
                'date': today,
                'timezone': 'Europe/Vienna'
            })
        else:
            return []
        
        if 'error' in result:
            print(f"API-Sports error: {result['error']}")
            return []
        
        return result.get('response', [])
    
    def get_odds(self, sport: str, fixture_id: int, bookmaker_id: int = None) -> dict:
        """Get odds for a specific fixture"""
        params = {'fixture': fixture_id}
        if bookmaker_id:
            params['bookmaker'] = bookmaker_id
        
        if sport == 'football':
            result = self._make_request(sport, 'odds', params)
        else:
            # Basketball, hockey have different odds structure
            result = self._make_request(sport, 'odds', params)
        
        if 'error' in result:
            return {}
        
        return result.get('response', [])
    
    def get_live_odds(self, sport: str, fixture_id: int) -> dict:
        """Get live odds"""
        result = self._make_request(sport, 'odds/live', {'fixture': fixture_id})
        
        if 'error' in result:
            return {}
        
        return result.get('response', [])
    
    def get_bookmakers(self, sport: str = 'football') -> List[dict]:
        """Get list of available bookmakers"""
        result = self._make_request(sport, 'odds/bookmakers')
        
        if 'error' in result:
            return []
        
        return result.get('response', [])
    
    def get_leagues(self, sport: str = 'football', country: str = 'Austria') -> List[dict]:
        """Get leagues for a country"""
        result = self._make_request(sport, 'leagues', {'country': country})
        
        if 'error' in result:
            return []
        
        return result.get('response', [])


def convert_to_standard_format(api_sports_odds: dict, sport_key: str) -> dict:
    """
    Convert API-Sports odds format to The Odds API format
    so it can be processed by the same arbitrage engine
    """
    # API-Sports odds structure is different
    # This function normalizes it
    
    # Example API-Sports response:
    # {
    #   "fixture": {"id": 123, "date": "2024-01-01"},
    #   "bookmakers": [
    #     {
    #       "id": 1, "name": "Bet365",
    #       "bets": [
    #         {"id": 1, "name": "Match Winner", "values": [
    #           {"value": "Home", "odd": "1.50"},
    #           {"value": "Draw", "odd": "3.00"},
    #           {"value": "Away", "odd": "5.00"}
    #         ]}
    #       ]
    #     }
    #   ]
    # }
    
    if not api_sports_odds or not isinstance(api_sports_odds, list):
        return None
    
    # Convert to The Odds API format
    converted = {
        'sport_key': sport_key,
        'sport_title': sport_key.replace('_', ' ').title(),
        'home_team': '',
        'away_team': '',
        'commence_time': '',
        'bookmakers': []
    }
    
    for odds_data in api_sports_odds:
        fixture = odds_data.get('fixture', {})
        converted['commence_time'] = fixture.get('date', '')
        
        teams = odds_data.get('teams', odds_data.get('league', {}))
        if 'home' in teams:
            converted['home_team'] = teams['home'].get('name', '')
        if 'away' in teams:
            converted['away_team'] = teams['away'].get('name', '')
        
        for bookmaker in odds_data.get('bookmakers', []):
            book_data = {
                'key': bookmaker.get('name', '').lower().replace(' ', ''),
                'title': bookmaker.get('name', ''),
                'markets': []
            }
            
            for bet in bookmaker.get('bets', []):
                bet_name = bet.get('name', '').lower()
                
                # Map bet types to standard markets
                if 'winner' in bet_name or 'match' in bet_name:
                    market_key = 'h2h'
                elif 'spread' in bet_name or 'handicap' in bet_name:
                    market_key = 'spreads'
                elif 'total' in bet_name or 'over' in bet_name:
                    market_key = 'totals'
                else:
                    continue
                
                market = {
                    'key': market_key,
                    'outcomes': []
                }
                
                for value in bet.get('values', []):
                    outcome = {
                        'name': str(value.get('value', '')),
                        'price': float(value.get('odd', 0))
                    }
                    
                    # Handle point values for spreads/totals
                    if 'handicap' in value or 'point' in str(value.get('value', '')):
                        try:
                            # Extract point value
                            val_str = str(value.get('value', ''))
                            if '+' in val_str or '-' in val_str:
                                outcome['point'] = float(val_str.split()[-1])
                        except:
                            pass
                    
                    market['outcomes'].append(outcome)
                
                book_data['markets'].append(market)
            
            converted['bookmakers'].append(book_data)
    
    return converted


# Global client instance
api_sports_client = APISportsClient()


def set_api_key(key: str):
    """Set API-Sports API key"""
    api_sports_client.set_api_key(key)


def get_odds_for_sport(sport_key: str) -> List[dict]:
    """
    Get odds for a sport, converted to standard format
    Returns list of games with odds in The Odds API format
    """
    if sport_key not in SPORT_MAPPING:
        return []
    
    mapping = SPORT_MAPPING[sport_key]
    sport = mapping['sport']
    league = mapping['league']
    
    # Get fixtures
    fixtures = api_sports_client.get_fixtures(sport, league)
    
    games = []
    for fixture in fixtures[:5]:  # Limit to save API calls
        fixture_id = fixture.get('fixture', {}).get('id')
        if not fixture_id:
            continue
        
        # Get odds for fixture
        odds = api_sports_client.get_odds(sport, fixture_id)
        
        if odds:
            converted = convert_to_standard_format(odds, sport_key)
            if converted:
                games.append(converted)
    
    return games


def get_usage() -> dict:
    """Get API usage stats"""
    return api_sports_client.get_usage()
