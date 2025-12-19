"""
Debug script to check what odds data is available
and find near-arbitrage opportunities
"""
import requests
import config

def debug_api():
    print("🔍 DEBUG: Checking The Odds API...")
    print(f"   API Key: {config.API_KEY[:10]}...")
    
    # Get sports
    response = requests.get(
        f'{config.API_BASE_URL}/sports',
        params={'api_key': config.API_KEY}
    )
    
    if response.status_code != 200:
        print(f"❌ API Error: {response.status_code}")
        print(response.text)
        return
    
    sports = [s for s in response.json() if s.get('active')]
    print(f"✅ Found {len(sports)} active sports")
    
    remaining = response.headers.get('x-requests-remaining', '?')
    print(f"📊 API Credits Remaining: {remaining}")
    
    # Get odds for one sport
    print("\n🏈 Checking Soccer (most common)...")
    
    # Find a soccer sport
    soccer_sport = None
    for s in sports:
        if 'soccer' in s['key']:
            soccer_sport = s['key']
            break
    
    if not soccer_sport:
        soccer_sport = sports[0]['key'] if sports else None
    
    if not soccer_sport:
        print("❌ No sports available")
        return
    
    print(f"   Using: {soccer_sport}")
    
    response = requests.get(
        f'{config.API_BASE_URL}/sports/{soccer_sport}/odds',
        params={
            'api_key': config.API_KEY,
            'regions': 'eu,uk',
            'markets': 'h2h',
            'oddsFormat': 'decimal'
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Odds API Error: {response.status_code}")
        return
    
    games = response.json()
    print(f"✅ Found {len(games)} upcoming games")
    
    if not games:
        print("   No games scheduled!")
        return
    
    # Analyze first few games for near-arbitrage
    print("\n📊 Analyzing odds (looking for ANY margin < 105%)...")
    print("   (True arbitrage = margin < 100%)")
    print("-" * 60)
    
    near_arbs = []
    
    for game in games[:20]:
        home = game.get('home_team', '')
        away = game.get('away_team', '')
        
        # Find best odds for each outcome
        best_odds = {}
        
        for bookie in game.get('bookmakers', []):
            for market in bookie.get('markets', []):
                if market.get('key') != 'h2h':
                    continue
                for outcome in market.get('outcomes', []):
                    name = outcome.get('name', '')
                    price = outcome.get('price', 0)
                    if name not in best_odds or price > best_odds[name]['price']:
                        best_odds[name] = {
                            'price': price,
                            'book': bookie.get('title', '')
                        }
        
        if len(best_odds) >= 2:
            # Calculate margin
            implied_probs = [1/v['price'] for v in best_odds.values()]
            margin = sum(implied_probs) * 100
            
            if margin < 105:  # Near-arbitrage
                near_arbs.append({
                    'game': f"{home} vs {away}",
                    'margin': margin,
                    'odds': best_odds
                })
    
    if near_arbs:
        print(f"\n🎯 Found {len(near_arbs)} games with margin < 105%:\n")
        for arb in sorted(near_arbs, key=lambda x: x['margin'])[:10]:
            margin = arb['margin']
            is_true_arb = margin < 100
            icon = "🚨 ARBITRAGE!" if is_true_arb else "📈"
            print(f"{icon} {arb['game']}")
            print(f"   Margin: {margin:.2f}% {'(PROFIT OPPORTUNITY!)' if is_true_arb else ''}")
            for outcome, data in arb['odds'].items():
                print(f"   → {outcome}: {data['price']} @ {data['book']}")
            print()
    else:
        print("\n❌ No games with margin < 105% right now")
        print("   Bookmaker margins are typically 102-108%")
        print("   True arbitrage (< 100%) is VERY rare in real-time")
    
    print("\n" + "=" * 60)
    print("💡 TIP: Arbitrage opportunities are rare and last seconds!")
    print("   Consider lowering min ROI or running auto-refresh.")
    print(f"\n📊 API Credits Remaining: {response.headers.get('x-requests-remaining', '?')}")

if __name__ == '__main__':
    debug_api()
