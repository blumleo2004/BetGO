# BETGO Configuration
# Austria-accessible bookmakers and API settings

import os
import json
from pathlib import Path

def _load_api_key():
    """Load API key from environment variable or api_keys.json"""
    # First try environment variable
    env_key = os.environ.get('BETGO_API_KEY')
    if env_key:
        return env_key
    
    # Then try api_keys.json
    keys_path = Path(__file__).parent / 'api_keys.json'
    if keys_path.exists():
        try:
            with open(keys_path, 'r') as f:
                data = json.load(f)
                # Support multiple formats
                if 'the_odds_api' in data:
                    keys = data['the_odds_api'].get('keys', [])
                    if keys:
                        return keys[0].get('key') if isinstance(keys[0], dict) else keys[0]
                elif 'keys' in data:
                    keys = data['keys']
                    if keys:
                        return keys[0].get('key') if isinstance(keys[0], dict) else keys[0]
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Return None if no key found - will need to be configured
    return None

API_KEY = _load_api_key()

# Default settings
DEFAULT_INVESTMENT = 500.00
DEFAULT_MIN_ROI = 0.5  # Minimum ROI percentage to display

# Austria-accessible bookmakers from The Odds API
# Removed: 1xBet (not licensed in Austria)
# Format: { api_key: { name, url, color } }
BOOKMAKERS = {
    'bet365': {
        'name': 'Bet365',
        'url': 'https://www.bet365.com/',
        'color': '#027b5b'
    },
    'bwin': {
        'name': 'Bwin',
        'url': 'https://sports.bwin.com/',
        'color': '#ffcc00'
    },
    'unibet': {
        'name': 'Unibet',
        'url': 'https://www.unibet.com/',
        'color': '#14805e'
    },
    'unibet_eu': {
        'name': 'Unibet EU',
        'url': 'https://www.unibet.eu/',
        'color': '#14805e'
    },
    'betway': {
        'name': 'Betway',
        'url': 'https://www.betway.com/',
        'color': '#00a826'
    },
    'pinnacle': {
        'name': 'Pinnacle',
        'url': 'https://www.pinnacle.com/',
        'color': '#c41230'
    },
    'betfair_ex_eu': {
        'name': 'Betfair Exchange',
        'url': 'https://www.betfair.com/exchange/',
        'color': '#ffb80c'
    },
    'betfair': {
        'name': 'Betfair Sportsbook',
        'url': 'https://www.betfair.com/',
        'color': '#ffb80c'
    },
    '888sport': {
        'name': '888sport',
        'url': 'https://www.888sport.com/',
        'color': '#1d1d1d'
    },
    'williamhill': {
        'name': 'William Hill',
        'url': 'https://www.williamhill.com/',
        'color': '#002a5c'
    },
    'tipico_de': {
        'name': 'Tipico',
        'url': 'https://www.tipico.at/',
        'color': '#004a99'
    },
    'betsson': {
        'name': 'Betsson',
        'url': 'https://www.betsson.com/',
        'color': '#ff6600'
    },
    'betvictor': {
        'name': 'Bet Victor',
        'url': 'https://www.betvictor.com/',
        'color': '#cc0000'
    },
    'marathonbet': {
        'name': 'Marathon Bet',
        'url': 'https://www.marathonbet.com/',
        'color': '#004d99'
    },
    'leovegas': {
        'name': 'LeoVegas',
        'url': 'https://www.leovegas.com/',
        'color': '#ff6b00'
    },
    'nordicbet': {
        'name': 'NordicBet',
        'url': 'https://www.nordicbet.com/',
        'color': '#00274d'
    },
    'coolbet': {
        'name': 'Coolbet',
        'url': 'https://www.coolbet.com/',
        'color': '#6c5ce7'
    },
    # Austria-specific bookmakers
    'interwetten': {
        'name': 'Interwetten',
        'url': 'https://www.interwetten.com/',
        'color': '#003366'
    },
    'betatHome': {
        'name': 'bet-at-home',
        'url': 'https://www.bet-at-home.com/',
        'color': '#00923f'
    },
    'sport888': {
        'name': '888sport',
        'url': 'https://www.888sport.com/',
        'color': '#ff6600'
    }
}

# Market types
MARKETS = {
    'h2h': 'Moneyline (1X2)',
    'spreads': 'Handicap/Spread',
    'totals': 'Over/Under'
}

# Sport categories for filtering
SPORT_CATEGORIES = {
    'soccer': 'Football/Soccer',
    'basketball': 'Basketball',
    'tennis': 'Tennis',
    'americanfootball': 'American Football',
    'icehockey': 'Ice Hockey',
    'baseball': 'Baseball',
    'mma': 'MMA/UFC',
    'boxing': 'Boxing',
    'golf': 'Golf',
    'rugbyleague': 'Rugby',
    'cricket': 'Cricket',
    'aussierules': 'Aussie Rules',
    'handball': 'Handball',
    'volleyball': 'Volleyball',
}

# Timeframe options (in hours)
TIMEFRAMES = {
    '1h': 1,
    '3h': 3,
    '6h': 6,
    '12h': 12,
    '24h': 24,
    '48h': 48,
    '7d': 168
}


# API endpoints
API_BASE_URL = 'https://api.the-odds-api.com/v4'

# Database Configuration
SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///betgo.db')
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

