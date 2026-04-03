"""
BETGO Account Manager
CRUD + logic for bookmaker accounts, bet recording, ban risk scoring.
All Flask routes go through this module — never touch models directly.
"""

from datetime import datetime, timedelta
from models import db, BookmakerAccount, AccountActivity, ArbitrageRecord, ArbitrageLeg


# ─── CRUD ────────────────────────────────────────────────────────────────────

def add_account(bookmaker_key: str, label: str = None, initial_balance: float = 0.0,
                username: str = None, max_daily_bets: int = 5, max_weekly_bets: int = 20,
                min_stake: float = 5.0, max_stake: float = 100.0, notes: str = None) -> dict:
    """Add a new bookmaker account."""
    account = BookmakerAccount(
        bookmaker=bookmaker_key,
        user_label=label or bookmaker_key,
        username=username or '',
        status='new',
        current_balance=initial_balance,
        deposit_total=initial_balance,
        max_daily_bets=max_daily_bets,
        max_weekly_bets=max_weekly_bets,
        min_stake=min_stake,
        max_stake=max_stake,
        notes=notes,
    )
    db.session.add(account)
    db.session.flush()  # get ID before commit

    if initial_balance > 0:
        db.session.add(AccountActivity(
            account_id=account.id,
            activity_type='balance_updated',
            amount=initial_balance,
            notes='Initiales Guthaben'
        ))

    db.session.commit()
    return _to_dict(account)


def get_accounts(status_filter: str = None, bookmaker_filter: str = None) -> list:
    """List all accounts with derived health indicators."""
    q = BookmakerAccount.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    if bookmaker_filter:
        q = q.filter_by(bookmaker=bookmaker_filter)
    return [_to_dict(a) for a in q.all()]


def get_account(account_id: int) -> dict | None:
    """Get single account with stats."""
    a = BookmakerAccount.query.get(account_id)
    return _to_dict(a) if a else None


def update_balance(account_id: int, new_balance: float, notes: str = None) -> dict | None:
    """Update balance and log the change."""
    a = BookmakerAccount.query.get(account_id)
    if not a:
        return None
    old = a.current_balance
    a.current_balance = new_balance
    a.updated_at = datetime.utcnow()
    db.session.add(AccountActivity(
        account_id=account_id,
        activity_type='balance_updated',
        amount=new_balance - old,
        notes=notes or f'Guthaben: €{old:.2f} → €{new_balance:.2f}'
    ))
    db.session.commit()
    return _to_dict(a)


def set_status(account_id: int, new_status: str, notes: str = None) -> dict | None:
    """Change account status and log it."""
    valid = {'active', 'restricted', 'gubbed', 'dormant', 'new'}
    if new_status not in valid:
        return None
    a = BookmakerAccount.query.get(account_id)
    if not a:
        return None
    old = a.status
    a.status = new_status
    a.is_active = new_status == 'active'
    a.updated_at = datetime.utcnow()
    db.session.add(AccountActivity(
        account_id=account_id,
        activity_type='status_changed',
        notes=notes or f'Status: {old} → {new_status}'
    ))
    db.session.commit()
    return _to_dict(a)


def update_account(account_id: int, **kwargs) -> dict | None:
    """Update editable account fields."""
    a = BookmakerAccount.query.get(account_id)
    if not a:
        return None
    allowed = {'user_label', 'username', 'max_daily_bets', 'max_weekly_bets',
               'min_stake', 'max_stake', 'notes', 'deposit_total'}
    for k, v in kwargs.items():
        if k in allowed:
            setattr(a, k, v)
    a.updated_at = datetime.utcnow()
    db.session.commit()
    return _to_dict(a)


def delete_account(account_id: int) -> bool:
    """Delete an account and all its activity."""
    a = BookmakerAccount.query.get(account_id)
    if not a:
        return False
    db.session.delete(a)
    db.session.commit()
    return True


# ─── BET PLACEMENT LOGIC ─────────────────────────────────────────────────────

def can_place_bet(account_id: int, stake: float) -> tuple[bool, str]:
    """
    Check if a bet can be placed on this account.
    Returns (allowed: bool, reason: str).
    """
    a = BookmakerAccount.query.get(account_id)
    if not a:
        return False, 'Konto nicht gefunden'
    if a.status in ('restricted', 'gubbed', 'dormant'):
        return False, f'Konto ist {a.status}'
    if stake < a.min_stake:
        return False, f'Einsatz €{stake:.2f} unter Minimum €{a.min_stake:.2f}'
    if stake > a.max_stake:
        return False, f'Einsatz €{stake:.2f} über Maximum €{a.max_stake:.2f}'
    if a.daily_bet_count >= a.max_daily_bets:
        return False, f'Tageslimit erreicht ({a.daily_bet_count}/{a.max_daily_bets})'
    if a.weekly_bet_count >= a.max_weekly_bets:
        return False, f'Wochenlimit erreicht ({a.weekly_bet_count}/{a.max_weekly_bets})'
    return True, 'OK'


def get_usable_accounts_for_bookmaker(bookmaker_key: str) -> list:
    """Return accounts for a bookmaker that currently pass can_place_bet."""
    accounts = BookmakerAccount.query.filter_by(bookmaker=bookmaker_key).all()
    result = []
    for acc in accounts:
        ok, reason = can_place_bet(acc.id, acc.min_stake)
        if ok:
            result.append(_to_dict(acc))
    return result


def record_bet_placed(account_id: int, stake: float, arb_record_id: int = None):
    """Increment counters and deduct stake from balance."""
    a = BookmakerAccount.query.get(account_id)
    if not a:
        return
    a.daily_bet_count += 1
    a.weekly_bet_count += 1
    a.bets_placed_total += 1
    a.stake_total += stake
    a.current_balance = max(0, a.current_balance - stake)
    a.updated_at = datetime.utcnow()
    db.session.add(AccountActivity(
        account_id=account_id,
        activity_type='bet_placed',
        amount=stake,
        notes=f'Arb #{arb_record_id}' if arb_record_id else 'Wette platziert'
    ))
    db.session.commit()


# ─── BAN RISK ─────────────────────────────────────────────────────────────────

def get_ban_risk_score(account_id: int) -> dict:
    """
    Calculate ban risk score 0-100 for an account.
    Higher = more likely to get gubbed/restricted.
    """
    a = BookmakerAccount.query.get(account_id)
    if not a:
        return {'score': 0, 'level': 'green', 'breakdown': {}}

    score = 0
    breakdown = {}

    # High ROI in last 30 days → +20
    thirty_ago = datetime.utcnow() - timedelta(days=30)
    recent_legs = (ArbitrageLeg.query
                   .filter_by(account_id=account_id)
                   .join(ArbitrageRecord)
                   .filter(ArbitrageRecord.placed_at >= thirty_ago,
                           ArbitrageRecord.status == 'settled')
                   .all())
    if recent_legs:
        staked = sum(l.rounded_stake or l.stake or 0 for l in recent_legs)
        returned = sum(l.actual_return or 0 for l in recent_legs)
        if staked > 0:
            roi = (returned - staked) / staked * 100
            if roi > 2:
                score += 20
                breakdown['high_roi'] = f'+20 (ROI {roi:.1f}% letzte 30 Tage)'

    # Too many bets this week → +15
    if a.weekly_bet_count > 15:
        score += 15
        breakdown['high_frequency'] = f'+15 ({a.weekly_bet_count} Wetten diese Woche)'

    # Already restricted → +20
    if a.status == 'restricted':
        score += 20
        breakdown['restricted'] = '+20 (Konto bereits eingeschränkt)'

    # No mug bets in 14 days → +10
    fourteen_ago = datetime.utcnow() - timedelta(days=14)
    mug = (AccountActivity.query
           .filter_by(account_id=account_id, activity_type='mug_bet')
           .filter(AccountActivity.created_at >= fourteen_ago)
           .first())
    if not mug and a.bets_placed_total > 3:
        score += 10
        breakdown['no_mug_bets'] = '+10 (kein Freizeittipp in 14 Tagen)'

    # New account with already many bets → +10
    age_days = (datetime.utcnow() - a.created_at).days if a.created_at else 9999
    if age_days < 30 and a.bets_placed_total > 10:
        score += 10
        breakdown['new_account'] = f'+10 (neues Konto, {a.bets_placed_total} Wetten)'

    final_score = min(score, 100)
    return {
        'score': final_score,
        'level': ('green' if final_score <= 25
                  else 'yellow' if final_score <= 50
                  else 'orange' if final_score <= 75
                  else 'red'),
        'breakdown': breakdown,
    }


# ─── SCHEDULER HELPERS ───────────────────────────────────────────────────────

def reset_daily_counters():
    """Reset daily bet counters for all accounts (call at midnight)."""
    db.session.query(BookmakerAccount).update({BookmakerAccount.daily_bet_count: 0})
    db.session.commit()


def reset_weekly_counters():
    """Reset weekly bet counters for all accounts (call on Monday)."""
    db.session.query(BookmakerAccount).update({BookmakerAccount.weekly_bet_count: 0})
    db.session.commit()


# ─── ACTIVITY LOG ─────────────────────────────────────────────────────────────

def get_account_activity(account_id: int, limit: int = 50) -> list:
    """Fetch the activity log for an account."""
    activities = (AccountActivity.query
                  .filter_by(account_id=account_id)
                  .order_by(AccountActivity.created_at.desc())
                  .limit(limit)
                  .all())
    return [{
        'id': a.id,
        'type': a.activity_type,
        'amount': a.amount,
        'notes': a.notes,
        'created_at': a.created_at.isoformat(),
    } for a in activities]


# ─── INTERNAL ─────────────────────────────────────────────────────────────────

def _to_dict(a: BookmakerAccount) -> dict:
    """Serialize account model to dict with derived fields."""
    return {
        'id': a.id,
        'user_label': a.user_label or a.bookmaker,
        'bookmaker': a.bookmaker,
        'username': a.username,
        'status': a.status,
        'current_balance': a.current_balance,
        'deposit_total': a.deposit_total,
        'bets_placed_total': a.bets_placed_total,
        'stake_total': a.stake_total,
        'daily_bet_count': a.daily_bet_count,
        'weekly_bet_count': a.weekly_bet_count,
        'max_daily_bets': a.max_daily_bets,
        'max_weekly_bets': a.max_weekly_bets,
        'min_stake': a.min_stake,
        'max_stake': a.max_stake,
        'notes': a.notes,
        'last_verified': a.last_verified.isoformat() if a.last_verified else None,
        'created_at': a.created_at.isoformat() if a.created_at else None,
        'updated_at': a.updated_at.isoformat() if a.updated_at else None,
        'ban_risk': get_ban_risk_score(a.id),
    }
