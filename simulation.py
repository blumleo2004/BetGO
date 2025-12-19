"""
BETGO Simulation System
Paper trading for arbitrage betting - track bets without real money
"""

import json
import os
from datetime import datetime
from pathlib import Path

# Database file path
DB_PATH = Path(__file__).parent / 'simulation_data.json'

def load_db():
    """Load simulation database"""
    if DB_PATH.exists():
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'settings': {
            'starting_bankroll': 1000.0,
            'created_at': datetime.now().isoformat()
        },
        'bankroll': {
            'total': 1000.0,
            'available': 1000.0,
            'in_play': 0.0
        },
        'bookmaker_balances': {},
        'bets': [],
        'settled_bets': [],
        'statistics': {
            'total_bets': 0,
            'won': 0,
            'lost': 0,
            'pending': 0,
            'total_staked': 0.0,
            'total_returns': 0.0,
            'profit_loss': 0.0,
            'roi': 0.0
        }
    }

def save_db(db):
    """Save simulation database"""
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def reset_simulation(starting_bankroll=1000.0):
    """Reset the simulation with a fresh bankroll"""
    db = {
        'settings': {
            'starting_bankroll': starting_bankroll,
            'created_at': datetime.now().isoformat()
        },
        'bankroll': {
            'total': starting_bankroll,
            'available': starting_bankroll,
            'in_play': 0.0
        },
        'bookmaker_balances': {},
        'bets': [],
        'settled_bets': [],
        'statistics': {
            'total_bets': 0,
            'won': 0,
            'lost': 0,
            'pending': 0,
            'total_staked': 0.0,
            'total_returns': 0.0,
            'profit_loss': 0.0,
            'roi': 0.0
        }
    }
    save_db(db)
    return db

def get_simulation_stats():
    """Get current simulation statistics"""
    db = load_db()
    return {
        'bankroll': db['bankroll'],
        'statistics': db['statistics'],
        'pending_bets': len([b for b in db['bets'] if b['status'] == 'pending']),
        'bookmaker_balances': db['bookmaker_balances']
    }

def place_virtual_bet(arb_opportunity, investment=None):
    """
    Place a virtual bet on an arbitrage opportunity
    arb_opportunity = {
        'sport': 'ice_hockey',
        'home_team': 'Boston Bruins',
        'away_team': 'Edmonton Oilers',
        'commence_time': '2025-12-19T02:00:00Z',
        'market': 'totals',
        'line': 6.5,
        'stakes': {
            'Over +6.5': {'stake': 465.17, 'odds': 2.15, 'book': 'Tipico'},
            'Under +6.5': {'stake': 534.83, 'odds': 1.87, 'book': 'Pinnacle'}
        },
        'roi': 0.01,
        'profit': 0.12,
        'total_investment': 1000
    }
    """
    db = load_db()
    
    total_stake = sum(s['stake'] for s in arb_opportunity['stakes'].values())
    
    # Check if enough bankroll
    if total_stake > db['bankroll']['available']:
        return {
            'success': False,
            'error': f"Insufficient bankroll. Need €{total_stake:.2f}, have €{db['bankroll']['available']:.2f}"
        }
    
    # Create bet record
    bet_id = len(db['bets']) + 1
    bet = {
        'id': bet_id,
        'placed_at': datetime.now().isoformat(),
        'status': 'pending',
        'sport': arb_opportunity.get('sport', ''),
        'sport_title': arb_opportunity.get('sport_title', ''),
        'event': f"{arb_opportunity.get('home_team', '')} vs {arb_opportunity.get('away_team', '')}",
        'home_team': arb_opportunity.get('home_team', ''),
        'away_team': arb_opportunity.get('away_team', ''),
        'commence_time': arb_opportunity.get('commence_time', ''),
        'market': arb_opportunity.get('market', ''),
        'line': arb_opportunity.get('line'),
        'expected_roi': arb_opportunity.get('roi', 0),
        'expected_profit': arb_opportunity.get('profit', 0),
        'total_stake': total_stake,
        'legs': []
    }
    
    # Add each leg of the bet
    for outcome, data in arb_opportunity['stakes'].items():
        leg = {
            'outcome': outcome,
            'odds': data['odds'],
            'stake': data['stake'],
            'bookmaker': data['book'],
            'potential_return': round(data['stake'] * data['odds'], 2),
            'status': 'pending',
            'result': None
        }
        bet['legs'].append(leg)
        
        # Update bookmaker balance
        book = data['book']
        if book not in db['bookmaker_balances']:
            db['bookmaker_balances'][book] = {'deposited': 0, 'balance': 0, 'in_play': 0}
        db['bookmaker_balances'][book]['in_play'] += data['stake']
    
    # Update bankroll
    db['bankroll']['available'] -= total_stake
    db['bankroll']['in_play'] += total_stake
    
    # Update statistics
    db['statistics']['total_bets'] += 1
    db['statistics']['pending'] += 1
    db['statistics']['total_staked'] += total_stake
    
    # Save bet
    db['bets'].append(bet)
    save_db(db)
    
    return {
        'success': True,
        'bet_id': bet_id,
        'message': f"Virtual bet #{bet_id} placed! Staked €{total_stake:.2f}",
        'bet': bet
    }

def settle_bet(bet_id, winning_outcome):
    """
    Settle a pending bet with the actual result
    winning_outcome = the outcome that won (e.g., 'Over +6.5' or 'Under +6.5')
    """
    db = load_db()
    
    # Find the bet
    bet = None
    bet_index = None
    for i, b in enumerate(db['bets']):
        if b['id'] == bet_id:
            bet = b
            bet_index = i
            break
    
    if not bet:
        return {'success': False, 'error': f'Bet #{bet_id} not found'}
    
    if bet['status'] != 'pending':
        return {'success': False, 'error': f'Bet #{bet_id} already settled'}
    
    # Calculate returns
    total_return = 0
    for leg in bet['legs']:
        if leg['outcome'] == winning_outcome:
            leg['status'] = 'won'
            leg['result'] = leg['potential_return']
            total_return += leg['potential_return']
            
            # Update bookmaker balance
            book = leg['bookmaker']
            db['bookmaker_balances'][book]['in_play'] -= leg['stake']
            db['bookmaker_balances'][book]['balance'] += leg['potential_return']
        else:
            leg['status'] = 'lost'
            leg['result'] = 0
            
            book = leg['bookmaker']
            db['bookmaker_balances'][book]['in_play'] -= leg['stake']
    
    # Update bet status
    bet['status'] = 'settled'
    bet['settled_at'] = datetime.now().isoformat()
    bet['winning_outcome'] = winning_outcome
    bet['actual_return'] = total_return
    bet['actual_profit'] = total_return - bet['total_stake']
    
    # Update bankroll
    db['bankroll']['in_play'] -= bet['total_stake']
    db['bankroll']['available'] += total_return
    db['bankroll']['total'] = db['bankroll']['available'] + db['bankroll']['in_play']
    
    # Update statistics
    db['statistics']['pending'] -= 1
    db['statistics']['total_returns'] += total_return
    db['statistics']['profit_loss'] = db['statistics']['total_returns'] - db['statistics']['total_staked']
    
    if bet['actual_profit'] > 0:
        db['statistics']['won'] += 1
    else:
        db['statistics']['lost'] += 1
    
    if db['statistics']['total_staked'] > 0:
        db['statistics']['roi'] = (db['statistics']['profit_loss'] / db['statistics']['total_staked']) * 100
    
    # Move to settled bets
    db['settled_bets'].append(bet)
    db['bets'][bet_index] = bet
    
    save_db(db)
    
    return {
        'success': True,
        'bet_id': bet_id,
        'profit': bet['actual_profit'],
        'message': f"Bet #{bet_id} settled. {'Won' if bet['actual_profit'] > 0 else 'Lost'}: €{bet['actual_profit']:.2f}"
    }

def get_pending_bets():
    """Get all pending bets"""
    db = load_db()
    return [b for b in db['bets'] if b['status'] == 'pending']

def get_bet_history(limit=50):
    """Get bet history"""
    db = load_db()
    all_bets = sorted(db['bets'], key=lambda x: x['placed_at'], reverse=True)
    return all_bets[:limit]

def get_analytics():
    """Get detailed analytics for strategy optimization"""
    db = load_db()
    
    settled = [b for b in db['bets'] if b['status'] == 'settled']
    
    if not settled:
        return {
            'total_bets': 0,
            'message': 'No settled bets yet'
        }
    
    # Analytics by sport
    by_sport = {}
    for bet in settled:
        sport = bet.get('sport_title', 'Unknown')
        if sport not in by_sport:
            by_sport[sport] = {'bets': 0, 'profit': 0, 'staked': 0}
        by_sport[sport]['bets'] += 1
        by_sport[sport]['profit'] += bet['actual_profit']
        by_sport[sport]['staked'] += bet['total_stake']
    
    for sport in by_sport:
        if by_sport[sport]['staked'] > 0:
            by_sport[sport]['roi'] = (by_sport[sport]['profit'] / by_sport[sport]['staked']) * 100
    
    # Analytics by market
    by_market = {}
    for bet in settled:
        market = bet.get('market', 'Unknown')
        if market not in by_market:
            by_market[market] = {'bets': 0, 'profit': 0, 'staked': 0}
        by_market[market]['bets'] += 1
        by_market[market]['profit'] += bet['actual_profit']
        by_market[market]['staked'] += bet['total_stake']
    
    for market in by_market:
        if by_market[market]['staked'] > 0:
            by_market[market]['roi'] = (by_market[market]['profit'] / by_market[market]['staked']) * 100
    
    # Analytics by ROI range
    by_roi_range = {
        '0-1%': {'bets': 0, 'profit': 0, 'wins': 0},
        '1-2%': {'bets': 0, 'profit': 0, 'wins': 0},
        '2-5%': {'bets': 0, 'profit': 0, 'wins': 0},
        '5%+': {'bets': 0, 'profit': 0, 'wins': 0}
    }
    
    for bet in settled:
        roi = bet.get('expected_roi', 0)
        if roi < 1:
            range_key = '0-1%'
        elif roi < 2:
            range_key = '1-2%'
        elif roi < 5:
            range_key = '2-5%'
        else:
            range_key = '5%+'
        
        by_roi_range[range_key]['bets'] += 1
        by_roi_range[range_key]['profit'] += bet['actual_profit']
        if bet['actual_profit'] > 0:
            by_roi_range[range_key]['wins'] += 1
    
    return {
        'total_settled': len(settled),
        'by_sport': by_sport,
        'by_market': by_market,
        'by_roi_range': by_roi_range,
        'statistics': db['statistics'],
        'bankroll': db['bankroll']
    }

def export_to_csv():
    """Export all bets to CSV"""
    import csv
    db = load_db()
    
    csv_path = Path(__file__).parent / 'simulation_export.csv'
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'ID', 'Placed At', 'Status', 'Event', 'Sport', 'Market', 
            'Expected ROI', 'Expected Profit', 'Total Stake',
            'Actual Return', 'Actual Profit', 'Winning Outcome'
        ])
        
        for bet in db['bets']:
            writer.writerow([
                bet['id'],
                bet['placed_at'],
                bet['status'],
                bet['event'],
                bet.get('sport_title', ''),
                bet['market'],
                bet['expected_roi'],
                bet['expected_profit'],
                bet['total_stake'],
                bet.get('actual_return', ''),
                bet.get('actual_profit', ''),
                bet.get('winning_outcome', '')
            ])
    
    return str(csv_path)


# CLI for testing
if __name__ == '__main__':
    print("🎮 BETGO Simulation System")
    print("=" * 40)
    
    stats = get_simulation_stats()
    print(f"💰 Bankroll: €{stats['bankroll']['total']:.2f}")
    print(f"   Available: €{stats['bankroll']['available']:.2f}")
    print(f"   In Play: €{stats['bankroll']['in_play']:.2f}")
    print(f"📊 Total Bets: {stats['statistics']['total_bets']}")
    print(f"   Pending: {stats['pending_bets']}")
    print(f"   Won: {stats['statistics']['won']}")
    print(f"   Lost: {stats['statistics']['lost']}")
    print(f"📈 P/L: €{stats['statistics']['profit_loss']:.2f}")
    print(f"   ROI: {stats['statistics']['roi']:.2f}%")
