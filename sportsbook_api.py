"""
BETGO - Sportsbook API Integration
Additional data source: 50 requests/day FREE (1,500/month)
https://sportsbookapi.com/
Via RapidAPI: https://rapidapi.com/sportsbook-api-sportsbook-api-default/api/sportsbook-api2
"""

import requests
from typing import Optional, List
from datetime import datetime

# RapidAPI configuration for Sportsbook API
RAPIDAPI_HOST = "sportsbook-api2.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"


class SportsbookAPIClient:
    """Client for Sportsbook API via RapidAPI"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.requests_today = 0
        self.last_request_date = None
    
    def set_api_key(self, api_key: str):
        """Set RapidAPI key"""
        self.api_key = api_key
    
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make request to Sportsbook API"""
        if not self.api_key:
            return {'error': 'No API key set. Get one at RapidAPI.'}
        
        headers = {
            'x-rapidapi-key': self.api_key,
            'x-rapidapi-host': RAPIDAPI_HOST
        }
        
        try:
            url = f"{BASE_URL}/{endpoint}"
            response = requests.get(url, headers=headers, params=params or {})
            
            # Track requests
            today = datetime.now().date()
            if self.last_request_date != today:
                self.requests_today = 0
                self.last_request_date = today
            self.requests_today += 1
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                return {'error': 'Rate limit exceeded (50/day on free plan)'}
            else:
                return {'error': f'API error: {response.status_code}'}
        except Exception as e:
            return {'error': str(e)}
    
    def get_usage(self) -> dict:
        """Get usage stats"""
        return {
            'requests_today': self.requests_today,
            'limit_per_day': 50,
            'remaining': max(0, 50 - self.requests_today)
        }
    
    def get_sports(self) -> List[dict]:
        """Get available sports"""
        result = self._make_request('sports')
        if 'error' in result:
            print(f"Sportsbook API error: {result['error']}")
            return []
        return result if isinstance(result, list) else []
    
    def get_events(self, sport: str) -> List[dict]:
        """Get events for a sport"""
        result = self._make_request(f'events/{sport}')
        if 'error' in result:
            return []
        return result if isinstance(result, list) else []
    
    def get_odds(self, event_id: str, market: str = 'moneyline') -> dict:
        """Get odds for an event"""
        result = self._make_request(f'odds/{event_id}', {'market': market})
        if 'error' in result:
            return {}
        return result
    
    def get_arbitrage(self) -> List[dict]:
        """Get pre-calculated arbitrage opportunities (if available)"""
        result = self._make_request('arbitrage')
        if 'error' in result:
            return []
        return result if isinstance(result, list) else []


def convert_to_standard_format(sportsbook_data: dict) -> dict:
    """
    Convert Sportsbook API format to match The Odds API format
    for consistent processing in the arbitrage engine
    """
    # This will need adjustment based on actual API response structure
    if not sportsbook_data:
        return None
    
    converted = {
        'sport_key': sportsbook_data.get('sport', ''),
        'sport_title': sportsbook_data.get('sport_name', ''),
        'home_team': sportsbook_data.get('home_team', ''),
        'away_team': sportsbook_data.get('away_team', ''),
        'commence_time': sportsbook_data.get('start_time', ''),
        'bookmakers': []
    }
    
    # Convert bookmaker odds
    for book_name, odds in sportsbook_data.get('odds', {}).items():
        book_data = {
            'key': book_name.lower().replace(' ', '_'),
            'title': book_name,
            'markets': []
        }
        
        # Convert to markets format
        market = {
            'key': 'h2h',
            'outcomes': []
        }
        
        if 'home' in odds:
            market['outcomes'].append({
                'name': converted['home_team'],
                'price': float(odds['home'])
            })
        if 'away' in odds:
            market['outcomes'].append({
                'name': converted['away_team'],
                'price': float(odds['away'])
            })
        if 'draw' in odds:
            market['outcomes'].append({
                'name': 'Draw',
                'price': float(odds['draw'])
            })
        
        book_data['markets'].append(market)
        converted['bookmakers'].append(book_data)
    
    return converted


# Global client instance
sportsbook_client = SportsbookAPIClient()


def set_api_key(key: str):
    """Set Sportsbook API key (RapidAPI)"""
    sportsbook_client.set_api_key(key)


def get_sports() -> List[dict]:
    """Get available sports"""
    return sportsbook_client.get_sports()


def get_odds(sport: str) -> List[dict]:
    """Get odds for a sport"""
    events = sportsbook_client.get_events(sport)
    all_odds = []
    
    for event in events[:10]:  # Limit to save requests
        event_id = event.get('id')
        if event_id:
            odds = sportsbook_client.get_odds(event_id)
            if odds:
                converted = convert_to_standard_format(odds)
                if converted:
                    all_odds.append(converted)
    
    return all_odds


def get_usage() -> dict:
    """Get API usage"""
    return sportsbook_client.get_usage()
