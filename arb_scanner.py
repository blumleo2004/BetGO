import requests
import time

# --- CONFIGURATION ---
API_KEY = '8a14240e95657e1f1461e763796ff40a' # <--- PASTE KEY HERE
TOTAL_INVESTMENT = 500.00          # <--- How much you want to bet TOTAL (in Euros)
REGIONS = 'eu'
ODDS_FORMAT = 'decimal'
# ---------------------

def get_active_sports():
    try:
        response = requests.get(
            f'https://api.the-odds-api.com/v4/sports',
            params={'api_key': API_KEY}
        )
        if response.status_code == 200:
            return [s['key'] for s in response.json() if s['active']]
        return []
    except:
        return []

def get_odds(sport, markets):
    try:
        response = requests.get(
            f'https://api.the-odds-api.com/v4/sports/{sport}/odds',
            params={
                'api_key': API_KEY,
                'regions': REGIONS,
                'markets': markets,
                'oddsFormat': ODDS_FORMAT,
            }
        )
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def calculate_stakes(odds_data):
    """
    Calculates the exact stake for each outcome to guarantee profit.
    odds_data = {'Home': 2.10, 'Away': 2.10} or similar
    """
    implied_probs = {k: 1/v for k, v in odds_data.items()}
    total_implied_prob = sum(implied_probs.values())
    
    if total_implied_prob >= 1.0:
        return None # No Arb

    stakes = {}
    total_return = 0
    
    # The Magic Formula: Stake = (Total_Investment * Implied_Prob) / Total_Implied_Prob
    for outcome, prob in implied_probs.items():
        stake = (TOTAL_INVESTMENT * prob) / total_implied_prob
        stakes[outcome] = stake
        # Calculate return (should be same for all)
        total_return = stake * odds_data[outcome]

    profit = total_return - TOTAL_INVESTMENT
    roi = (profit / TOTAL_INVESTMENT) * 100
    
    return {
        'stakes': stakes,
        'profit': profit,
        'roi': roi,
        'total_return': total_return
    }

def analyze_arb(game, market_key):
    best_opportunities = {} 

    for bookie in game['bookmakers']:
        for market in bookie['markets']:
            if market['key'] != market_key: continue
            
            for outcome in market['outcomes']:
                if market_key == 'h2h':
                    key = 'match'
                    identifier = outcome['name']
                else:
                    if 'point' not in outcome: continue
                    identifier = outcome['name'] 
                    key = outcome['point']

                if key not in best_opportunities:
                    best_opportunities[key] = {}
                
                if identifier not in best_opportunities[key] or outcome['price'] > best_opportunities[key][identifier]['price']:
                    best_opportunities[key][identifier] = {
                        'price': outcome['price'],
                        'book': bookie['title']
                    }

    for key, outcomes in best_opportunities.items():
        if len(outcomes) < 2: continue
        
        # Prepare data for calculator
        odds_map = {k: v['price'] for k, v in outcomes.items()}
        
        # Run Calculation
        result = calculate_stakes(odds_map)
        
        if result and result['profit'] > 0:
            print(f"\n🚨 {market_key.upper()} ARBITRAGE FOUND! 🚨")
            print(f"   ⚔️ {game['home_team']} vs {game['away_team']}")
            if market_key != 'h2h': print(f"   🎯 LINE: {key}")
            print(f"   💰 GUARANTEED PROFIT: €{result['profit']:.2f} ({result['roi']:.2f}%)")
            print(f"   ---------------------------------------------")
            print(f"   🛑 ACTION PLAN (Total Invest: €{TOTAL_INVESTMENT}):")
            
            for side, stake in result['stakes'].items():
                book = outcomes[side]['book']
                odd = outcomes[side]['price']
                print(f"      👉 BET €{stake:.2f} on {side} [{odd}] @ {book}")
            
            print(f"   ---------------------------------------------")
            return True 
    return False

def run_shotgun():
    print(f"💥 TESAVEK EXECUTIONER ONLINE...")
    print(f"💶 Bankroll Locked: €{TOTAL_INVESTMENT}")
    
    sports = get_active_sports()
    total_found = 0
    markets_to_scan = 'h2h,spreads,totals'

    for sport in sports:
        if 'winner' in sport or 'championship' in sport: continue
        print(f"   👉 Scanning {sport}...", end='\r')
        games = get_odds(sport, markets_to_scan)
        
        for game in games:
            if analyze_arb(game, 'h2h'): total_found += 1
            if analyze_arb(game, 'totals'): total_found += 1
            if analyze_arb(game, 'spreads'): total_found += 1
            
        time.sleep(0.5)

    print(f"\n✅ Scan Complete. Found {total_found} money printers.")

run_shotgun()