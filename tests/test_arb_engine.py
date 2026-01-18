"""
BETGO Unit Tests - Arbitrage Engine
Tests for the core arbitrage calculation and odds finding logic
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from arb_engine import ArbEngine


class TestCalculateArbitrage:
    """Tests for the calculate_arbitrage method"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.engine = ArbEngine()
    
    def test_arbitrage_opportunity_exists(self):
        """Test detection of a valid arbitrage opportunity"""
        # These odds should create an arbitrage opportunity
        # Implied probability < 100%
        odds_data = {
            'Team A': {'price': 2.20, 'book': 'Bet365', 'book_key': 'bet365'},
            'Team B': {'price': 2.15, 'book': 'Pinnacle', 'book_key': 'pinnacle'}
        }
        
        result = self.engine.calculate_arbitrage(odds_data, 1000)
        
        assert result is not None
        assert 'roi' in result
        assert result['roi'] > 0
        assert 'stakes' in result
        assert 'profit' in result
        assert result['profit'] > 0
    
    def test_no_arbitrage_when_odds_too_low(self):
        """Test that no arbitrage is found when odds are unfavorable"""
        # These odds should NOT create an arbitrage opportunity
        # Implied probability > 100%
        odds_data = {
            'Team A': {'price': 1.80, 'book': 'Bet365', 'book_key': 'bet365'},
            'Team B': {'price': 1.90, 'book': 'Pinnacle', 'book_key': 'pinnacle'}
        }
        
        result = self.engine.calculate_arbitrage(odds_data, 1000)
        
        assert result is None
    
    def test_insufficient_outcomes(self):
        """Test that arbitrage returns None with less than 2 outcomes"""
        odds_data = {
            'Team A': {'price': 2.50, 'book': 'Bet365', 'book_key': 'bet365'}
        }
        
        result = self.engine.calculate_arbitrage(odds_data, 1000)
        
        assert result is None
    
    def test_stake_calculation_accuracy(self):
        """Test that stakes are calculated correctly for guaranteed profit"""
        odds_data = {
            'Team A': {'price': 2.10, 'book': 'Bet365', 'book_key': 'bet365'},
            'Team B': {'price': 2.10, 'book': 'Pinnacle', 'book_key': 'pinnacle'}
        }
        
        result = self.engine.calculate_arbitrage(odds_data, 1000)
        
        assert result is not None
        
        # Verify total stake equals investment
        total_stake = sum(s['stake'] for s in result['stakes'].values())
        assert abs(total_stake - 1000) < 0.01
        
        # Verify all potential returns are approximately equal (guaranteed profit)
        returns = [s['potential_return'] for s in result['stakes'].values()]
        assert abs(returns[0] - returns[1]) < 0.01
    
    def test_three_way_arbitrage(self):
        """Test arbitrage calculation with 3 outcomes (e.g., soccer 1X2)"""
        odds_data = {
            'Home': {'price': 3.50, 'book': 'Bet365', 'book_key': 'bet365'},
            'Draw': {'price': 3.60, 'book': 'Pinnacle', 'book_key': 'pinnacle'},
            'Away': {'price': 3.40, 'book': 'Bwin', 'book_key': 'bwin'}
        }
        
        result = self.engine.calculate_arbitrage(odds_data, 1000)
        
        assert result is not None
        assert len(result['stakes']) == 3
        assert result['roi'] > 0


class TestFindBestOdds:
    """Tests for the find_best_odds method"""
    
    def setup_method(self):
        self.engine = ArbEngine()
    
    def test_finds_best_odds_across_bookmakers(self):
        """Test that the best odds are selected from multiple bookmakers"""
        game = {
            'bookmakers': [
                {
                    'key': 'bet365',
                    'title': 'Bet365',
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Team A', 'price': 2.00},
                                {'name': 'Team B', 'price': 1.80}
                            ]
                        }
                    ]
                },
                {
                    'key': 'pinnacle',
                    'title': 'Pinnacle',
                    'markets': [
                        {
                            'key': 'h2h',
                            'outcomes': [
                                {'name': 'Team A', 'price': 2.10},  # Better for Team A
                                {'name': 'Team B', 'price': 1.75}
                            ]
                        }
                    ]
                }
            ]
        }
        
        best_odds = self.engine.find_best_odds(game, 'h2h')
        
        assert 'Team A' in best_odds
        assert 'Team B' in best_odds
        assert best_odds['Team A']['price'] == 2.10  # From Pinnacle
        assert best_odds['Team A']['book'] == 'Pinnacle'
        assert best_odds['Team B']['price'] == 1.80  # From Bet365
        assert best_odds['Team B']['book'] == 'Bet365'
    
    def test_empty_game_returns_empty_dict(self):
        """Test that empty game data returns empty dict"""
        game = {'bookmakers': []}
        
        best_odds = self.engine.find_best_odds(game, 'h2h')
        
        assert best_odds == {}


class TestAPIUsage:
    """Tests for API usage tracking"""
    
    def test_initial_usage_is_none(self):
        """Test that initial API usage stats are None"""
        engine = ArbEngine()
        usage = engine.get_api_usage()
        
        assert usage['remaining'] is None
        assert usage['used'] is None
        assert usage['cache_hits'] == 0
        assert usage['api_calls'] == 0
