"""
BETGO Stealth Engine
Stake rounding, timing delays, account rotation.
Pure functions — no side effects, easy to test.
"""

import random
from datetime import datetime, timedelta


def round_stake_natural(raw_stake: float) -> float:
    """
    Round stake to a natural-looking amount.
    < €20  → nearest €1
    €20-100 → nearest €5
    €100+   → nearest €10
    """
    if raw_stake < 20:
        return float(round(raw_stake))
    elif raw_stake < 100:
        return float(round(raw_stake / 5) * 5)
    else:
        return float(round(raw_stake / 10) * 10)


def get_leg_placement_delays(num_legs: int) -> list:
    """
    Returns cumulative delay offsets in seconds for each leg.
    Leg 0: always 0s
    Leg 1: 45-180s after leg 0
    Leg 2+: 30-120s after previous leg
    Never < 30s between any two legs.
    """
    if num_legs <= 0:
        return []

    delays = [0]
    cumulative = 0
    for i in range(1, num_legs):
        gap = random.randint(45, 180) if i == 1 else random.randint(30, 120)
        cumulative += gap
        delays.append(cumulative)

    return delays


def get_graduated_max_stake(account_dict: dict) -> float:
    """
    Returns max stake based on account maturity.
    New account (<30d or <20 bets): €50
    Established (<100 bets): €150
    Mature (100+ bets): €300
    Never exceeds account's configured max_stake.
    """
    bets_total = account_dict.get('bets_placed_total', 0)
    configured_max = account_dict.get('max_stake', 100.0)
    created_at_str = account_dict.get('created_at')

    age_days = 9999
    if created_at_str:
        try:
            created = datetime.fromisoformat(created_at_str.replace('Z', ''))
            age_days = (datetime.utcnow() - created).days
        except Exception:
            pass

    if age_days < 30 or bets_total < 20:
        graduated = 50.0
    elif bets_total < 100:
        graduated = 150.0
    else:
        graduated = 300.0

    return min(graduated, configured_max)


def select_account_for_leg(bookmaker_key: str, available_accounts: list,
                            recent_usage: dict = None) -> dict | None:
    """
    Pick the best account for a bookmaker leg.
    Prefers accounts not used in the last 2 hours.
    Falls back to lowest weekly_bet_count.

    recent_usage: {account_id: last_used_datetime_iso_str}
    """
    if not available_accounts:
        return None

    recent_usage = recent_usage or {}
    two_hours_ago = datetime.utcnow() - timedelta(hours=2)

    fresh, stale = [], []
    for acc in available_accounts:
        last_used_str = recent_usage.get(acc['id'])
        if last_used_str:
            try:
                last_used = datetime.fromisoformat(last_used_str)
                if last_used > two_hours_ago:
                    stale.append(acc)
                    continue
            except Exception:
                pass
        fresh.append(acc)

    pool = fresh if fresh else stale
    pool.sort(key=lambda a: a.get('weekly_bet_count', 0))

    # Small jitter: pick randomly from the top 2 least-used accounts
    top = pool[:2]
    return random.choice(top)


def should_place_mug_bet(account_dict: dict, arb_bets_since_last_mug: int = 0) -> bool:
    """Returns True if account needs a mug bet to look recreational."""
    if account_dict.get('status') not in ('active', 'new'):
        return False
    if account_dict.get('bets_placed_total', 0) == 0:
        return True
    return arb_bets_since_last_mug >= 5


# ─── Kelly Criterion Stake Sizing ─────────────────────────────────────────────

def kelly_stake(bankroll: float, odds: float, prob_estimate: float,
                fraction: float = 0.25) -> float:
    """
    Fractional Kelly criterion stake.

    For arb betting prob_estimate is always 1.0 (guaranteed profit).
    fraction=0.25 = quarter-Kelly (standard conservative setting).
    Returns 0.0 if Kelly formula yields a non-positive stake.

    Formula: f* = (b*p - q) / b  where b = odds-1, p = prob_win, q = 1-p
    Fractional: stake = bankroll * fraction * f*
    """
    if odds <= 1.0 or bankroll <= 0:
        return 0.0
    b = odds - 1.0
    p = prob_estimate
    q = 1.0 - p
    kelly_fraction = (b * p - q) / b
    if kelly_fraction <= 0:
        return 0.0
    return bankroll * fraction * kelly_fraction


def kelly_investment(bankroll: float, arb_result: dict,
                     fraction: float = 0.25) -> float:
    """
    Optimal total investment for an arb opportunity using fractional Kelly.

    Uses the ROI as the guaranteed edge.  Since arb is risk-free, we treat
    the entire arb as a single bet: odds = 1 + roi/100, prob = 1.0.
    Caps at 5% of bankroll to limit exposure.
    """
    roi = arb_result.get('roi', 0)
    if roi <= 0 or bankroll <= 0:
        return 0.0
    # Effective decimal odds of the guaranteed return
    effective_odds = 1.0 + roi / 100.0
    raw = kelly_stake(bankroll, effective_odds, 1.0, fraction)
    max_allowed = bankroll * 0.05
    return round(min(raw, max_allowed), 2)


def get_recommended_investment(bankroll: float, roi: float,
                                base_investment: float = 500.0) -> float:
    """
    Returns a recommended total investment based on ROI tier.

    ROI < 1%   → 60% of base_investment  (thin margin, stay small)
    ROI 1-2%   → base_investment          (sweet spot)
    ROI 2-4%   → 120% of base_investment  (good edge, size up)
    ROI > 4%   → 80% of base_investment   (suspicious, scale back)

    Hard cap: never exceeds 10% of bankroll.
    """
    if roi < 1.0:
        investment = base_investment * 0.60
    elif roi < 2.0:
        investment = base_investment
    elif roi <= 4.0:
        investment = base_investment * 1.20
    else:
        investment = base_investment * 0.80

    max_allowed = bankroll * 0.10
    return round(min(investment, max_allowed), 2)


def jitter_stake(raw_stake: float, pct: float = 0.06) -> float:
    if raw_stake <= 0.0:
        return 0.0
    variation = random.uniform(-pct, pct)
    return raw_stake * (1.0 + variation)


def mug_bet_due(arb_count_since_last_mug: int, threshold: int = 5) -> bool:
    return arb_count_since_last_mug >= threshold
