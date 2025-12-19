"""
BETGO Cloud Scanner - Standalone script for GitHub Actions
Runs without Flask, just scans and sends Discord notifications
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta

# Configuration from environment variables (GitHub Secrets)
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK')
API_KEYS = json.loads(os.environ.get('API_KEYS', '[]'))

# The Odds API configuration
API_BASE_URL = "https://api.the-odds-api.com/v4"

# Austria-accessible bookmakers only
BOOKMAKERS = [
    # Sharp Bookmakers (best odds)
    'pinnacle',        # International - best for arb
    'betfair_ex_eu',   # Betting exchange
    'matchbook',       # Betting exchange
    
    # Major EU Bookmakers (work in Austria)
    'sport888',        # 888sport
    'williamhill',     # William Hill
    'betsson',         # Betsson
    'marathonbet',     # Marathon
    'onexbet',         # 1xBet
    
    # German Market (accessible from Austria)
    'tipico_de',       # Tipico - very popular in AT
    'winamax_de',      # Winamax Germany
    
    # International
    'unibet_nl',       # Unibet (international version)
    'suprabets',       # Suprabets
    'everygame',       # Everygame
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


def calculate_stakes(best_odds, total_investment=100):
    """Calculate optimal stake distribution for arbitrage"""
    implied_probs = {name: 1/bet['odds'] for name, bet in best_odds.items()}
    total_implied = sum(implied_probs.values())
    
    stakes = {}
    for name, bet in best_odds.items():
        # Stake proportional to implied probability
        stake = (implied_probs[name] / total_implied) * total_investment
        percentage = (stake / total_investment) * 100
        stakes[name] = {
            'stake': round(stake, 2),
            'percentage': round(percentage, 1),
            'odds': bet['odds'],
            'bookmaker': bet['bookmaker'],
            'outcome': name,
            'potential_return': round(stake * bet['odds'], 2)
        }
    
    # Calculate guaranteed profit
    min_return = min(s['potential_return'] for s in stakes.values())
    profit = min_return - total_investment
    
    return stakes, round(profit, 2)


def find_arbitrage(events, min_roi=0.5, max_roi=5.0, min_minutes_to_start=30):
    """Find arbitrage opportunities in events with realistic ROI filter"""
    opportunities = []
    now = datetime.now(timezone.utc)
    
    for event in events:
        # Check if event starts in at least min_minutes_to_start
        commence_time_str = event.get('commence_time', '')
        if commence_time_str:
            try:
                commence_time = datetime.fromisoformat(commence_time_str.replace('Z', '+00:00'))
                minutes_until_start = (commence_time - now).total_seconds() / 60
                
                # Skip events that have started or start too soon
                if minutes_until_start < min_minutes_to_start:
                    continue
            except:
                continue  # Skip if can't parse time
        else:
            continue  # Skip if no commence time
        
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
            
            # Filter: Min 0.5%, Max 5% ROI (realistic range)
            if min_roi <= roi <= max_roi:
                # Calculate stakes for €100
                stakes, profit = calculate_stakes(best_odds, 100)
                
                opportunities.append({
                    'sport': event.get('sport_key', ''),
                    'home_team': event.get('home_team', ''),
                    'away_team': event.get('away_team', ''),
                    'roi': round(roi, 2),
                    'profit': profit,
                    'stakes': stakes,
                    'bets': list(best_odds.values()),
                    'commence_time': event.get('commence_time', ''),
                    'minutes_until_start': round(minutes_until_start)
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
        opportunities = find_arbitrage(events, min_roi=0.5, max_roi=5.0)
        all_opportunities.extend(opportunities)
    
    # Sort by ROI (best first)
    all_opportunities.sort(key=lambda x: x['roi'], reverse=True)
    
    print(f"\n📊 Found {len(all_opportunities)} realistic arbitrage opportunities!")
    
    # Send Discord notifications
    if all_opportunities:
        for opp in all_opportunities[:3]:  # Max 3 notifications
            # Format time until start
            mins = opp.get('minutes_until_start', 0)
            if mins >= 60:
                time_str = f"{mins // 60}h {mins % 60}min"
            else:
                time_str = f"{mins}min"
            
            fields = [
                {"name": "🏆 Sport", "value": opp['sport'], "inline": True},
                {"name": "📈 ROI", "value": f"{opp['roi']}%", "inline": True},
                {"name": "💰 Profit", "value": f"€{opp['profit']}", "inline": True},
                {"name": "⏱️ Startet in", "value": time_str, "inline": True},
                {"name": "🎯 Match", "value": f"{opp['home_team']} vs {opp['away_team']}", "inline": False},
                {"name": "💵 Investment", "value": "€100", "inline": True}
            ]
            
            # Add stake details for each bet
            stakes = opp['stakes']
            for name, stake_info in stakes.items():
                fields.append({
                    "name": f"🎰 {stake_info['bookmaker']}",
                    "value": f"**{stake_info['outcome']}** @ {stake_info['odds']}\n€{stake_info['stake']} ({stake_info['percentage']}%)",
                    "inline": True
                })
            
            # Color based on ROI (green gradient)
            if opp['roi'] >= 2:
                color = 0x00FF00  # Bright green - great!
            elif opp['roi'] >= 1:
                color = 0x7CFC00  # Yellow-green - good
            else:
                color = 0x32CD32  # Lime - decent
            
            send_discord(
                title=f"💰 Arbitrage: {opp['roi']}% → €{opp['profit']} Profit!",
                description=f"**{opp['home_team']}** vs **{opp['away_team']}**\nInvestment: €100 → Return: €{100 + opp['profit']:.2f}",
                color=color,
                fields=fields
            )
            print(f"   📤 Sent notification: {opp['home_team']} vs {opp['away_team']} ({opp['roi']}% ROI)")
    else:
        # Send summary even if no opportunities
        send_discord(
            title="📊 Scan Complete - No Arbitrage",
            description=f"Scanned {len(sports)} sports at {datetime.now().strftime('%H:%M')}\n*Only showing realistic opportunities (0.5-5% ROI)*",
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
    
    print("📊 ROI filter: 0.5% - 5.0% (realistic only)")
    
    opportunities = run_scan()
    print(f"\n✅ Scan complete! Found {len(opportunities)} opportunities")

