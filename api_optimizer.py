"""
BETGO API Optimizer
- Caching system to reduce API calls
- Multi-key rotation for more credits
- Smart scheduling for optimal scan times
"""

import json
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import hashlib

# Cache file path
CACHE_PATH = Path(__file__).parent / 'api_cache.json'
KEYS_PATH = Path(__file__).parent / 'api_keys.json'

# Cache settings
CACHE_DURATION_MINUTES = 5  # How long to cache odds data
SPORTS_CACHE_DURATION_HOURS = 24  # How long to cache sports list


class APIKeyManager:
    """Manages multiple API keys with rotation and usage tracking"""
    
    def __init__(self):
        self.keys = self._load_keys()
        self.api_sports_key = self._load_api_sports_key()
        self.current_index = 0
    
    def _load_keys(self) -> List[dict]:
        """Load The Odds API keys from file"""
        if KEYS_PATH.exists():
            with open(KEYS_PATH, 'r') as f:
                data = json.load(f)
                # Support both old and new format
                if 'the_odds_api' in data:
                    return data['the_odds_api'].get('keys', [])
                return data.get('keys', [])
        return []
    
    def _load_api_sports_key(self) -> Optional[str]:
        """Load API-Sports key"""
        if KEYS_PATH.exists():
            with open(KEYS_PATH, 'r') as f:
                data = json.load(f)
                if 'api_sports' in data:
                    return data['api_sports'].get('key')
        return None
    
    def get_api_sports_key(self) -> Optional[str]:
        """Get API-Sports key"""
        return self.api_sports_key
    
    def set_api_sports_key(self, key: str):
        """Set API-Sports key"""
        self.api_sports_key = key
        self._save_all()
    
    def _save_all(self):
        """Save all keys to file"""
        data = {
            'the_odds_api': {
                'keys': self.keys,
                'comment': 'The Odds API - 500 credits/month per key'
            },
            'api_sports': {
                'key': self.api_sports_key,
                'comment': 'API-Sports - 100 requests/day FREE! Get key at: https://dashboard.api-football.com/register'
            },
            'updated_at': datetime.now().isoformat()
        }
        with open(KEYS_PATH, 'w') as f:
            json.dump(data, f, indent=2)
    
    def save_keys(self, keys: List[str]):
        """Save API keys to file"""
        key_data = {
            'keys': [{'key': k, 'remaining': None, 'last_used': None} for k in keys],
            'updated_at': datetime.now().isoformat()
        }
        with open(KEYS_PATH, 'w') as f:
            json.dump(key_data, f, indent=2)
        self.keys = key_data['keys']
    
    def add_key(self, key: str):
        """Add a new API key"""
        self.keys.append({'key': key, 'remaining': None, 'last_used': None})
        self._save()
    
    def _save(self):
        """Save current keys state"""
        with open(KEYS_PATH, 'w') as f:
            json.dump({'keys': self.keys, 'updated_at': datetime.now().isoformat()}, f, indent=2)
    
    def get_best_key(self) -> Optional[str]:
        """Get the key with most remaining credits"""
        if not self.keys:
            return None
        
        # Sort by remaining credits (None = unknown, put at end)
        available = [k for k in self.keys if k.get('remaining') is None or k.get('remaining', 0) > 0]
        
        if not available:
            return None
        
        # Prefer keys with known remaining credits
        known = [k for k in available if k.get('remaining') is not None]
        if known:
            best = max(known, key=lambda x: x.get('remaining', 0))
            return best['key']
        
        # Otherwise return first unknown key
        return available[0]['key']
    
    def update_usage(self, key: str, remaining: int):
        """Update usage stats for a key"""
        for k in self.keys:
            if k['key'] == key:
                k['remaining'] = remaining
                k['last_used'] = datetime.now().isoformat()
                break
        self._save()
    
    def get_total_remaining(self) -> int:
        """Get total remaining credits across all keys"""
        return sum(k.get('remaining', 0) or 0 for k in self.keys)
    
    def get_stats(self) -> dict:
        """Get usage statistics"""
        return {
            'total_keys': len(self.keys),
            'total_remaining': self.get_total_remaining(),
            'keys': [
                {
                    'key': k['key'][:8] + '...',
                    'remaining': k.get('remaining'),
                    'last_used': k.get('last_used')
                }
                for k in self.keys
            ]
        }


class CacheManager:
    """Manages caching of API responses"""
    
    def __init__(self):
        self.cache = self._load_cache()
    
    def _load_cache(self) -> dict:
        """Load cache from file"""
        if CACHE_PATH.exists():
            try:
                with open(CACHE_PATH, 'r') as f:
                    return json.load(f)
            except:
                return {'sports': None, 'odds': {}}
        return {'sports': None, 'odds': {}}
    
    def _save_cache(self):
        """Save cache to file"""
        with open(CACHE_PATH, 'w') as f:
            json.dump(self.cache, f)
    
    def _get_cache_key(self, sport: str, markets: str, bookmakers: Optional[str] = None) -> str:
        """Generate cache key for odds request"""
        key_str = f"{sport}:{markets}:{bookmakers or 'all'}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get_sports(self) -> Optional[list]:
        """Get cached sports list"""
        if not self.cache.get('sports'):
            return None
        
        cached = self.cache['sports']
        cached_time = datetime.fromisoformat(cached['timestamp'])
        
        if datetime.now() - cached_time < timedelta(hours=SPORTS_CACHE_DURATION_HOURS):
            return cached['data']
        
        return None
    
    def set_sports(self, sports: list):
        """Cache sports list"""
        self.cache['sports'] = {
            'data': sports,
            'timestamp': datetime.now().isoformat()
        }
        self._save_cache()
    
    def get_odds(self, sport: str, markets: str, bookmakers: Optional[str] = None) -> Optional[list]:
        """Get cached odds"""
        cache_key = self._get_cache_key(sport, markets, bookmakers)
        
        if cache_key not in self.cache.get('odds', {}):
            return None
        
        cached = self.cache['odds'][cache_key]
        cached_time = datetime.fromisoformat(cached['timestamp'])
        
        if datetime.now() - cached_time < timedelta(minutes=CACHE_DURATION_MINUTES):
            return cached['data']
        
        return None
    
    def set_odds(self, sport: str, markets: str, odds: list, bookmakers: Optional[str] = None):
        """Cache odds data"""
        cache_key = self._get_cache_key(sport, markets, bookmakers)
        
        if 'odds' not in self.cache:
            self.cache['odds'] = {}
        
        self.cache['odds'][cache_key] = {
            'data': odds,
            'timestamp': datetime.now().isoformat()
        }
        self._save_cache()
    
    def clear(self):
        """Clear all cache"""
        self.cache = {'sports': None, 'odds': {}}
        self._save_cache()
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        odds_count = len(self.cache.get('odds', {}))
        sports_cached = self.cache.get('sports') is not None
        
        return {
            'sports_cached': sports_cached,
            'odds_entries': odds_count,
            'cache_duration_minutes': CACHE_DURATION_MINUTES
        }


class SmartScheduler:
    """
    Determines optimal times to scan based on sports schedules
    Peak arbitrage times:
    - 1-2 hours before major games
    - When odds are being updated (mornings, before events)
    - Weekends for football/soccer
    """
    
    # Peak hours for different sports (in local time)
    PEAK_TIMES = {
        'soccer': {
            'weekday': [(17, 22)],  # Evening games
            'weekend': [(12, 22)],  # Full day on weekends
        },
        'basketball': {
            'weekday': [(18, 23)],  # NBA evening
            'weekend': [(15, 23)],
        },
        'icehockey': {
            'weekday': [(18, 23)],
            'weekend': [(15, 23)],
        },
        'tennis': {
            'weekday': [(10, 20)],  # Throughout day
            'weekend': [(10, 20)],
        },
        'default': {
            'weekday': [(16, 23)],
            'weekend': [(12, 23)],
        }
    }
    
    @classmethod
    def is_optimal_time(cls, sport: Optional[str] = None) -> bool:
        """Check if current time is optimal for scanning"""
        now = datetime.now()
        hour = now.hour
        is_weekend = now.weekday() >= 5
        
        day_type = 'weekend' if is_weekend else 'weekday'
        
        # Get sport-specific or default times
        sport_key = 'default'
        if sport:
            for key in cls.PEAK_TIMES.keys():
                if key in sport.lower():
                    sport_key = key
                    break
        
        peak_ranges = cls.PEAK_TIMES[sport_key][day_type]
        
        for start, end in peak_ranges:
            if start <= hour <= end:
                return True
        
        return False
    
    @classmethod
    def get_next_optimal_time(cls) -> datetime:
        """Get next optimal scanning time"""
        now = datetime.now()
        hour = now.hour
        is_weekend = now.weekday() >= 5
        
        day_type = 'weekend' if is_weekend else 'weekday'
        peak_ranges = cls.PEAK_TIMES['default'][day_type]
        
        # Find next peak time today or tomorrow
        for start, end in peak_ranges:
            if hour < start:
                return now.replace(hour=start, minute=0, second=0)
        
        # Next day
        tomorrow = now + timedelta(days=1)
        is_weekend_tomorrow = tomorrow.weekday() >= 5
        day_type_tomorrow = 'weekend' if is_weekend_tomorrow else 'weekday'
        start = cls.PEAK_TIMES['default'][day_type_tomorrow][0][0]
        
        return tomorrow.replace(hour=start, minute=0, second=0)
    
    @classmethod
    def get_recommended_interval(cls) -> int:
        """Get recommended scan interval in seconds based on current time"""
        if cls.is_optimal_time():
            return 5 * 60  # Every 5 minutes during peak
        else:
            return 30 * 60  # Every 30 minutes off-peak
    
    @classmethod
    def get_status(cls) -> dict:
        """Get scheduler status"""
        now = datetime.now()
        is_optimal = cls.is_optimal_time()
        next_optimal = cls.get_next_optimal_time() if not is_optimal else None
        
        return {
            'is_optimal_time': is_optimal,
            'current_hour': now.hour,
            'is_weekend': now.weekday() >= 5,
            'recommended_interval_seconds': cls.get_recommended_interval(),
            'next_optimal_time': next_optimal.isoformat() if next_optimal else None,
            'status': '🟢 Peak Time - Scan frequently!' if is_optimal else '🟡 Off-peak - Save credits'
        }


# Global instances
key_manager = APIKeyManager()
cache_manager = CacheManager()
scheduler = SmartScheduler()


# Convenience functions
def get_api_key() -> str:
    """Get best available API key"""
    return key_manager.get_best_key()

def update_key_usage(key: str, remaining: int):
    """Update API key usage"""
    key_manager.update_usage(key, remaining)

def get_cached_sports() -> Optional[list]:
    """Get cached sports"""
    return cache_manager.get_sports()

def cache_sports(sports: list):
    """Cache sports list"""
    cache_manager.set_sports(sports)

def get_cached_odds(sport: str, markets: str) -> Optional[list]:
    """Get cached odds"""
    return cache_manager.get_odds(sport, markets)

def cache_odds(sport: str, markets: str, odds: list):
    """Cache odds"""
    cache_manager.set_odds(sport, markets, odds)

def is_optimal_time() -> bool:
    """Check if now is optimal for scanning"""
    return scheduler.is_optimal_time()

def get_optimizer_stats() -> dict:
    """Get all optimizer statistics"""
    return {
        'keys': key_manager.get_stats(),
        'cache': cache_manager.get_stats(),
        'scheduler': scheduler.get_status()
    }
