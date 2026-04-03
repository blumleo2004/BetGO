"""
BETGO Mug Bet Advisor
Suggests small recreational bets to disguise arbitrage activity.
All suggestions are advisory — never automated.
"""

import random
from datetime import datetime, timedelta


_SUGGESTIONS = [
    {'description': 'Heimsieg im nächsten Topspiel', 'market': 'h2h', 'min': 5, 'max': 20},
    {'description': 'Beide Teams treffen (BTTS)', 'market': 'btts', 'min': 5, 'max': 15},
    {'description': 'Über 2.5 Tore', 'market': 'totals', 'min': 5, 'max': 20},
    {'description': 'Favorit gewinnt', 'market': 'h2h', 'min': 10, 'max': 30},
    {'description': 'Heimsieg der lokalen Mannschaft', 'market': 'h2h', 'min': 5, 'max': 15},
    {'description': 'Unentschieden im Derby', 'market': 'h2h', 'min': 5, 'max': 15},
    {'description': 'Top-Torjäger trifft', 'market': 'player_props', 'min': 5, 'max': 10},
]


def get_mug_suggestion(account_dict: dict, arb_bets_since_last_mug: int = 0) -> dict:
    """
    Generate a mug bet suggestion for a given account dict.
    account_dict: output of account_manager.get_account()
    """
    if not account_dict:
        return {'error': 'Account not found'}

    bets_total = account_dict.get('bets_placed_total', 0)

    if bets_total == 0:
        urgency = 'required'
        reason = 'Erster Tipp sollte kein Arb-Tipp sein — als normaler Tipper starten'
    elif arb_bets_since_last_mug >= 8:
        urgency = 'urgent'
        reason = f'{arb_bets_since_last_mug} Arb-Tipps seit letztem Freizeittipp — dringend'
    elif arb_bets_since_last_mug >= 5:
        urgency = 'recommended'
        reason = f'{arb_bets_since_last_mug} Arb-Tipps seit letztem Freizeittipp'
    else:
        urgency = 'optional'
        reason = f'Nur {arb_bets_since_last_mug} Arb-Tipps seit letztem Freizeittipp'

    s = random.choice(_SUGGESTIONS)
    stake = round(random.randint(s['min'], s['max']))

    return {
        'account_id': account_dict.get('id'),
        'bookmaker': account_dict.get('bookmaker'),
        'account_label': account_dict.get('user_label', account_dict.get('bookmaker')),
        'urgency': urgency,
        'reason': reason,
        'arb_bets_since_last_mug': arb_bets_since_last_mug,
        'suggestion': s['description'],
        'market': s['market'],
        'suggested_stake': stake,
        'note': 'Absichtlich als normaler Tipper agieren. NIE automatisch platziert.'
    }


def get_arb_count_since_last_mug(account_id: int) -> int:
    """Count arb bets placed since last recorded mug bet for this account."""
    try:
        from models import AccountActivity
        last_mug = AccountActivity.query.filter_by(
            account_id=account_id,
            activity_type='mug_bet'
        ).order_by(AccountActivity.created_at.desc()).first()

        if last_mug:
            count = AccountActivity.query.filter(
                AccountActivity.account_id == account_id,
                AccountActivity.activity_type == 'bet_placed',
                AccountActivity.created_at > last_mug.created_at
            ).count()
        else:
            from models import BookmakerAccount
            acc = BookmakerAccount.query.get(account_id)
            count = acc.bets_placed_total if acc else 0
        return count
    except Exception:
        return 0


def record_mug_bet(account_id: int, stake: float, notes: str = None) -> dict:
    """Record that a mug bet was manually placed."""
    try:
        from models import db, AccountActivity
        activity = AccountActivity(
            account_id=account_id,
            activity_type='mug_bet',
            amount=stake,
            notes=notes or 'Manueller Freizeittipp'
        )
        db.session.add(activity)
        db.session.commit()
        return {'success': True, 'message': f'Mug bet €{stake:.2f} aufgezeichnet'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
