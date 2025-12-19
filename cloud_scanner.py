"""
BETGO Cloud Scanner - Standalone script for GitHub Actions
Runs without Flask, just scans and sends Discord notifications
"""

import os
import json
import requests
from datetime import datetime

# Configuration from environment variables (GitHub Secrets)
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK')
API_KEYS = json.loads(os.environ.get('API_KEYS', '[]'))

# The Odds API configuration
API_BASE_URL = "https://api.the-odds-api.com/v4"

# Austrian-legal bookmakers
BOOKMAKERS = [
    'pinnacle', 'betfair', 'betfair_ex_eu', 'betsson', 
    'unibet_eu', 'sport888', 'williamhill'
]


def get_best_api_key():
    """Get the API key with most remaining credits"""
    if not API_KEYS:
        raise ValueError("No API keys configured!")
    
    best_key = None
    best_remaining = -1
    
    for key_data in API_KEYS:
        key = key_data if isinstance(key_data, str) else key_data.get('key')
        
        # Check remaining credits
        try:
            r = requests.get(f"{API_BASE_URL}/sports", params={'apiKey': key})
            remaining = int(r.headers.get('x-requests-remaining', 0))
            if remaining > best_remaining:
                best_remaining = remaining
                best_key = key
        except:
            continue
    
    print(f"Using API key with {best_remaining} credits remaining")
    return best_key


def send_discord(title, description, color=0x00FF00, fields=None):
    """Send Discord notification"""
    if not DISCORD_WEBHOOK:
        print("Discord webhook not configured!")
        return False
    
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "BETGO Cloud Scanner"}
    }
    
    if fields:
        embed["fields"] = fields
    
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]})
        return r.status_code == 204
    except Exception as e:
        print(f"Discord error: {e}")
        return False


def get_odds(api_key, sport):
    """Fetch odds for a sport"""
    params = {
        'apiKey': api_key,
        'regions': 'eu',
        'markets': 'h2h',
        'bookmakers': ','.join(BOOKMAKERS),
        'oddsFormat': 'decimal'
    }
    
    r = requests.get(f"{API_BASE_URL}/sports/{sport}/odds", params=params)
    
    if r.status_code == 200:
        return r.json()
    return []


def find_arbitrage(events):
    """Find arbitrage opportunities in events"""
    opportunities = []
    
    for event in events:
        bookmakers = event.get('bookmakers', [])
        if len(bookmakers) < 2:
            continue
        
        # Find best odds for each outcome
        best_odds = {}
        
        for bookmaker in bookmakers:
            for market in bookmaker.get('markets', []):
                if market.get('key') != 'h2h':
                    continue
                
                for outcome in market.get('outcomes', []):
                    name = outcome.get('name')
                    price = outcome.get('price', 0)
                    
                    if name not in best_odds or price > best_odds[name]['odds']:
                        best_odds[name] = {
                            'odds': price,
                            'bookmaker': bookmaker.get('title'),
                            'outcome': name
                        }
        
        if len(best_odds) < 2:
            continue
        
        # Calculate arbitrage
        implied_probs = sum(1 / b['odds'] for b in best_odds.values())
        
        if implied_probs < 1:
            roi = ((1 / implied_probs) - 1) * 100
            
            if roi >= 0.5:  # Min 0.5% ROI
                opportunities.append({
                    'sport': event.get('sport_key', ''),
                    'home_team': event.get('home_team', ''),
                    'away_team': event.get('away_team', ''),
                    'roi': round(roi, 2),
                    'bets': list(best_odds.values()),
                    'commence_time': event.get('commence_time', '')
                })
    
    return opportunities


def run_scan():
    """Run a full arbitrage scan"""
    print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] Starting cloud scan...")
    
    # Get best API key
    api_key = get_best_api_key()
    
    # Get available sports
    r = requests.get(f"{API_BASE_URL}/sports", params={'apiKey': api_key})
    sports = [s['key'] for s in r.json() if not s.get('has_outrights')][:5]  # Top 5 sports
    
    all_opportunities = []
    
    for sport in sports:
        print(f"   Scanning {sport}...")
        events = get_odds(api_key, sport)
        opportunities = find_arbitrage(events)
        all_opportunities.extend(opportunities)
    
    print(f"\n📊 Found {len(all_opportunities)} arbitrage opportunities!")
    
    # Send Discord notifications
    if all_opportunities:
        for opp in all_opportunities[:5]:  # Max 5 notifications
            fields = [
                {"name": "🏆 Sport", "value": opp['sport'], "inline": True},
                {"name": "📈 ROI", "value": f"{opp['roi']}%", "inline": True},
                {"name": "🎯 Match", "value": f"{opp['home_team']} vs {opp['away_team']}", "inline": False}
            ]
            
            for bet in opp['bets']:
                fields.append({
                    "name": f"💰 {bet['bookmaker']}",
                    "value": f"{bet['outcome']} @ {bet['odds']}",
                    "inline": True
                })
            
            send_discord(
                title=f"🎲 Arbitrage: {opp['roi']}% ROI!",
                description=f"{opp['home_team']} vs {opp['away_team']}",
                color=0x00FF00,
                fields=fields
            )
    else:
        # Send summary even if no opportunities
        send_discord(
            title="📊 Scan Complete",
            description=f"Scanned {len(sports)} sports, no arbitrage found",
            color=0x3498DB
        )
    
    return all_opportunities


if __name__ == "__main__":
    print("=" * 50)
    print("BETGO Cloud Scanner")
    print("=" * 50)
    
    if not DISCORD_WEBHOOK:
        print("⚠️ DISCORD_WEBHOOK not set!")
    
    if not API_KEYS:
        print("⚠️ API_KEYS not set!")
    else:
        print(f"✅ {len(API_KEYS)} API keys loaded")
    
    opportunities = run_scan()
    print(f"\n✅ Scan complete! Found {len(opportunities)} opportunities")
