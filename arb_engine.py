"""
BETGO Arbitrage Engine
Handles odds fetching, arbitrage detection, and stake calculations
With integrated caching, multi-key support, and smart scheduling
"""

import requests
from datetime import datetime, timezone
from typing import Optional
import config
import api_optimizer

class ArbEngine:
    def __init__(self):
        self.base_url = config.API_BASE_URL
        self.remaining_requests = None
        self.used_requests = None
        self.cache_hits = 0
        self.api_calls = 0
        
    def _get_api_key(self) -> str:
        """Get best available API key"""
        key = api_optimizer.get_api_key()
        if key:
            return key
        # Fallback to config key
        return config.API_KEY
        
    def get_api_usage(self) -> dict:
        """Return current API usage stats"""
        optimizer_stats = api_optimizer.get_optimizer_stats()
        return {
            'remaining': self.remaining_requests,
            'used': self.used_requests,
            'cache_hits': self.cache_hits,
            'api_calls': self.api_calls,
            'optimizer': optimizer_stats
        }
    
    def _update_usage(self, response, api_key: str):
        """Update API usage from response headers"""
        if 'x-requests-remaining' in response.headers:
            self.remaining_requests = int(response.headers['x-requests-remaining'])
            api_optimizer.update_key_usage(api_key, self.remaining_requests)
        if 'x-requests-used' in response.headers:
            self.used_requests = int(response.headers['x-requests-used'])
    
    def get_sports(self) -> list:
        """Fetch all active sports (with caching)"""
        # Check cache first
        cached = api_optimizer.get_cached_sports()
        if cached:
            self.cache_hits += 1
            return cached
        
        try:
            api_key = self._get_api_key()
            response = requests.get(
                f'{self.base_url}/sports',
                params={'api_key': api_key}
            )
            self._update_usage(response, api_key)
            self.api_calls += 1
            
            if response.status_code == 200:
                sports = response.json()
                active_sports = [s for s in sports if s.get('active', False)]
                # Cache the result
                api_optimizer.cache_sports(active_sports)
                return active_sports
            return []
        except Exception as e:
            print(f"Error fetching sports: {e}")
            return []
    
    def get_odds(self, sport: str, markets: str = 'h2h,spreads,totals', 
                 bookmakers: Optional[list] = None) -> list:
        """Fetch odds for a specific sport (with caching)"""
        # Check cache first
        cached = api_optimizer.get_cached_odds(sport, markets)
        if cached:
            self.cache_hits += 1
            return cached
        
        try:
            api_key = self._get_api_key()
            params = {
                'api_key': api_key,
                'regions': 'eu,uk',
                'markets': markets,
                'oddsFormat': 'decimal'
            }
            
            if bookmakers:
                params['bookmakers'] = ','.join(bookmakers)
            
            response = requests.get(
                f'{self.base_url}/sports/{sport}/odds',
                params=params
            )
            self._update_usage(response, api_key)
            self.api_calls += 1
            
            if response.status_code == 200:
                odds = response.json()
                # Cache the result
                api_optimizer.cache_odds(sport, markets, odds)
                return odds
            return []
        except Exception as e:
            print(f"Error fetching odds for {sport}: {e}")
            return []
    
    def calculate_arbitrage(self, odds_data: dict, total_investment: float) -> Optional[dict]:
        """
        Calculate if arbitrage opportunity exists and return stake distribution
        odds_data = {'outcome_name': {'price': 2.10, 'book': 'bet365'}, ...}
        """
        if len(odds_data) < 2:
            return None
            
        # Calculate implied probabilities
        implied_probs = {k: 1/v['price'] for k, v in odds_data.items()}
        total_implied = sum(implied_probs.values())
        
        # No arbitrage if total implied probability >= 100%
        if total_implied >= 1.0:
            return None
        
        # Calculate stakes for guaranteed profit
        stakes = {}
        for outcome, prob in implied_probs.items():
            stake = (total_investment * prob) / total_implied
            stakes[outcome] = {
                'stake': round(stake, 2),
                'odds': odds_data[outcome]['price'],
                'book': odds_data[outcome]['book'],
                'book_key': odds_data[outcome].get('book_key', ''),
                'potential_return': round(stake * odds_data[outcome]['price'], 2)
            }
        
        # All returns should be equal (guaranteed profit)
        total_return = list(stakes.values())[0]['potential_return']
        profit = total_return - total_investment
        roi = (profit / total_investment) * 100
        
        return {
            'stakes': stakes,
            'profit': round(profit, 2),
            'roi': round(roi, 2),
            'total_return': round(total_return, 2),
            'total_investment': total_investment
        }
    
    def find_best_odds(self, game: dict, market_key: str) -> dict:
        """Find the best odds for each outcome across all bookmakers"""
        best_odds = {}
        
        for bookmaker in game.get('bookmakers', []):
            book_key = bookmaker.get('key', '')
            book_name = bookmaker.get('title', '')
            
            for market in bookmaker.get('markets', []):
                if market.get('key') != market_key:
                    continue
                
                for outcome in market.get('outcomes', []):
                    if market_key == 'h2h':
                        # For moneyline, use outcome name as key
                        key = outcome.get('name', '')
                    else:
                        # For spreads/totals, combine name and point
                        point = outcome.get('point')
                        if point is None:
                            continue
                        key = f"{outcome.get('name', '')} {point:+g}" if point >= 0 else f"{outcome.get('name', '')} {point:g}"
                    
                    price = outcome.get('price', 0)
                    
                    if key not in best_odds or price > best_odds[key]['price']:
                        best_odds[key] = {
                            'price': price,
                            'book': book_name,
                            'book_key': book_key
                        }
        
        return best_odds
    
    def scan_for_arbitrage(self, sports: Optional[list] = None, 
                          markets: str = 'h2h,spreads,totals',
                          bookmakers: Optional[list] = None,
                          min_roi: float = 0.5,
                          investment: float = 500.0,
                          max_hours: Optional[int] = None,
                          live_only: bool = False) -> list:
        """
        Scan for arbitrage opportunities across sports
        Returns list of opportunities with all details
        """
        opportunities = []
        
        # Get sports if not provided
        if sports is None:
            all_sports = self.get_sports()
            sports = [s['key'] for s in all_sports if 'winner' not in s['key'] and 'championship' not in s['key']]
        
        for sport in sports:
            games = self.get_odds(sport, markets, bookmakers)
            
            for game in games:
                # Filter by time if specified
                if max_hours:
                    commence_time = game.get('commence_time')
                    if commence_time:
                        try:
                            game_time = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            hours_until = (game_time - now).total_seconds() / 3600
                            if hours_until > max_hours or hours_until < 0:
                                continue
                        except:
                            pass
                
                # Check each market type
                for market_type in markets.split(','):
                    best_odds = self.find_best_odds(game, market_type)
                    
                    if len(best_odds) < 2:
                        continue
                    
                    # For spreads/totals, group by point value
                    if market_type in ['spreads', 'totals']:
                        # Group outcomes by their opposite (e.g., Over 2.5 and Under 2.5)
                        point_groups = {}
                        for key, data in best_odds.items():
                            parts = key.rsplit(' ', 1)
                            if len(parts) == 2:
                                name, point = parts[0], parts[1]
                                # Normalize point for grouping
                                point_val = abs(float(point))
                                if point_val not in point_groups:
                                    point_groups[point_val] = {}
                                point_groups[point_val][key] = data
                        
                        for point_val, group in point_groups.items():
                            if len(group) >= 2:
                                arb = self.calculate_arbitrage(group, investment)
                                if arb and arb['roi'] >= min_roi:
                                    opportunities.append({
                                        'sport': game.get('sport_key', ''),
                                        'sport_title': game.get('sport_title', ''),
                                        'home_team': game.get('home_team', ''),
                                        'away_team': game.get('away_team', ''),
                                        'commence_time': game.get('commence_time', ''),
                                        'market': market_type,
                                        'line': point_val,
                                        **arb
                                    })
                    else:
                        # For H2H markets
                        arb = self.calculate_arbitrage(best_odds, investment)
                        if arb and arb['roi'] >= min_roi:
                            opportunities.append({
                                'sport': game.get('sport_key', ''),
                                'sport_title': game.get('sport_title', ''),
                                'home_team': game.get('home_team', ''),
                                'away_team': game.get('away_team', ''),
                                'commence_time': game.get('commence_time', ''),
                                'market': market_type,
                                'line': None,
                                **arb
                            })
        
        # Sort by ROI descending
        opportunities.sort(key=lambda x: x['roi'], reverse=True)
        return opportunities


# For CLI usage
if __name__ == '__main__':
    engine = ArbEngine()
    print("🔍 Scanning for arbitrage opportunities...")
    
    opps = engine.scan_for_arbitrage(min_roi=0.5, investment=500)
    
    if opps:
        print(f"\n✅ Found {len(opps)} opportunities!\n")
        for opp in opps[:10]:
            print(f"🚨 {opp['home_team']} vs {opp['away_team']}")
            print(f"   Sport: {opp['sport_title']} | Market: {opp['market']}")
            print(f"   ROI: {opp['roi']}% | Profit: €{opp['profit']}")
            for outcome, data in opp['stakes'].items():
                print(f"   → Bet €{data['stake']} on {outcome} @ {data['odds']} ({data['book']})")
            print()
    else:
        print("No arbitrage opportunities found at this time.")
    
    usage = engine.get_api_usage()
    print(f"\n📊 API Usage: {usage['used']} used, {usage['remaining']} remaining")
