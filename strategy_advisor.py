"""
BETGO Strategy Advisor
Gibt pro Konto konkrete Handlungsempfehlungen:
- Bonus-Clearing Plan
- Mug-Bet Timing
- Arb-Frequenz Limits
- Portfolio-Übersicht
"""

from datetime import datetime, timedelta
import random


# ─── Bonus Wagering ───────────────────────────────────────────────────────────

def get_bonus_status(account: dict) -> dict:
    """Berechnet den Bonus-Clearing Status."""
    bonus = account.get('bonus_balance', 0.0)
    wagered = account.get('bonus_wagered', 0.0)
    target = account.get('bonus_target', 0.0)
    req = account.get('bonus_wagering_req', 0.0)

    if bonus <= 0 and target <= 0:
        return {'has_bonus': False}

    # Falls target noch nicht gesetzt aber req schon
    if target <= 0 and bonus > 0 and req > 0:
        target = bonus * req

    remaining = max(0, target - wagered)
    pct = round((wagered / target * 100) if target > 0 else 0, 1)

    return {
        'has_bonus': True,
        'bonus_balance': bonus,
        'wagering_req': req,
        'wagered': round(wagered, 2),
        'target': round(target, 2),
        'remaining': round(remaining, 2),
        'pct_done': pct,
        'cleared': remaining <= 0,
    }


def get_bonus_clearing_plan(account: dict) -> dict:
    """
    Safe-Bet Plan zum Freiwetten des Bonus.
    Strategie: kleine Wetten auf Favoriten (Odds 1.5-1.9), nie auf Arb-Basis.
    """
    bonus_status = get_bonus_status(account)
    if not bonus_status['has_bonus'] or bonus_status['cleared']:
        return {'needed': False}

    remaining = bonus_status['remaining']
    balance = account.get('current_balance', 0)

    # Empfohlene Einsatzgröße: 5-8% des verbleibenden Umsatzziels pro Wette
    suggested_stake = round(max(5.0, min(remaining * 0.07, 30.0)), 0)
    bets_needed = max(1, int(remaining / suggested_stake))

    # Safe bet Vorschläge (Favoriten, niedrige Odds)
    safe_bets = [
        {'description': 'Heimfavorit gewinnt (Odds 1.5-1.7)', 'odds_range': '1.50-1.70', 'risk': 'niedrig'},
        {'description': 'Über 1.5 Tore im Spiel', 'odds_range': '1.45-1.65', 'risk': 'sehr niedrig'},
        {'description': 'Klarer Favorit gewinnt (Top-Liga)', 'odds_range': '1.60-1.80', 'risk': 'niedrig'},
        {'description': 'Beide Teams treffen (populäres Spiel)', 'odds_range': '1.70-1.90', 'risk': 'mittel'},
        {'description': 'Favorit gewinnt oder Unentschieden (1X)', 'odds_range': '1.40-1.55', 'risk': 'sehr niedrig'},
    ]

    warning = None
    if balance < suggested_stake:
        warning = f'Guthaben (€{balance:.0f}) zu niedrig — erst Einzahlung freischalten'

    return {
        'needed': True,
        'remaining_to_wager': remaining,
        'suggested_stake_per_bet': suggested_stake,
        'estimated_bets_needed': bets_needed,
        'suggested_bets': safe_bets,
        'warning': warning,
        'tip': (
            'Wette auf klare Favoriten mit Odds 1.5-1.9. '
            'KEINE Arb-Wetten während Bonus-Clearing — Buchmacher sperren Bonus bei Arb-Verdacht. '
            f'Ziel: {bets_needed} Wetten à €{suggested_stake:.0f} in den nächsten Tagen.'
        ),
    }


# ─── Account Strategie ────────────────────────────────────────────────────────

def get_account_strategy(account: dict, arb_count_since_mug: int = 0) -> dict:
    """
    Komplette Strategie-Empfehlung für ein Konto.
    Gibt an was als nächstes zu tun ist und warum.
    """
    status = account.get('status', 'new')
    bets_total = account.get('bets_placed_total', 0)
    balance = account.get('current_balance', 0)
    deposit_pending = account.get('deposit_pending', 0)
    ban_risk = account.get('ban_risk', {})
    risk_score = ban_risk.get('score', 0) if isinstance(ban_risk, dict) else 0
    bonus_status = get_bonus_status(account)
    bonus_plan = get_bonus_clearing_plan(account)

    actions = []  # Priorisierte Aktionsliste
    phase = 'unknown'

    # ── Phase 1: Einzahlung ausstehend ────────────────────────────────────────
    if deposit_pending > 0:
        actions.append({
            'priority': 1,
            'type': 'wait',
            'title': f'Einzahlung ausstehend (€{deposit_pending:.0f})',
            'detail': 'Warte bis die Einzahlung verfügbar ist (meist 1-3 Werktage bei Kreditkarte).',
            'icon': 'hourglass_empty',
        })
        phase = 'waiting_deposit'

    # ── Phase 2: Bonus freiwetten ─────────────────────────────────────────────
    if bonus_status.get('has_bonus') and not bonus_status.get('cleared'):
        actions.append({
            'priority': 2,
            'type': 'bonus',
            'title': f'Bonus freiwetten ({bonus_status["pct_done"]}% erledigt)',
            'detail': (
                f'Noch €{bonus_status["remaining"]:.0f} umsetzen. '
                f'Empfehlung: {bonus_plan.get("estimated_bets_needed", "?")} Safe-Bets '
                f'à €{bonus_plan.get("suggested_stake_per_bet", "?"):.0f} auf Favoriten.'
            ),
            'icon': 'card_giftcard',
            'bonus_plan': bonus_plan,
        })
        phase = 'bonus_clearing'

    # ── Phase 3: Neues Konto aufwärmen ────────────────────────────────────────
    elif bets_total < 5:
        actions.append({
            'priority': 2,
            'type': 'warmup',
            'title': 'Konto aufwärmen (noch kein Arb)',
            'detail': (
                f'Erst {5 - bets_total} normale Freizeittipps platzieren bevor Arb beginnt. '
                'Wähle populäre Spiele, verschiedene Sportarten, Beträge €5-20.'
            ),
            'icon': 'whatshot',
        })
        phase = 'warmup'

    # ── Phase 4: Mug Bet fällig ───────────────────────────────────────────────
    elif arb_count_since_mug >= 5:
        actions.append({
            'priority': 1,
            'type': 'mug_bet',
            'title': f'Freizeittipp jetzt! ({arb_count_since_mug} Arb-Wetten ohne Tarnwette)',
            'detail': 'Platziere 1-2 normale Wetten auf populäre Spiele (€5-15) bevor du weitere Arbs machst.',
            'icon': 'sports_soccer',
            'urgent': arb_count_since_mug >= 8,
        })
        phase = 'mug_needed'

    # ── Phase 5: Ban Risk hoch ────────────────────────────────────────────────
    if risk_score >= 70:
        actions.insert(0, {
            'priority': 0,
            'type': 'danger',
            'title': f'Hohes Gubbing-Risiko ({risk_score}/100)',
            'detail': 'Sofort aufhören mit Arb-Wetten auf diesem Konto. Mehrere Freizeittipps platzieren.',
            'icon': 'warning',
        })
        phase = 'high_risk'

    # ── Phase 6: Alles OK — Arb möglich ──────────────────────────────────────
    if not actions or (phase not in ('high_risk', 'bonus_clearing', 'warmup', 'waiting_deposit', 'mug_needed')):
        actions.append({
            'priority': 3,
            'type': 'arb_ready',
            'title': 'Bereit fur Arb-Wetten',
            'detail': (
                f'Konto sieht unauffällig aus (Risk {risk_score}/100). '
                f'Max Einsatz: €{account.get("max_stake", 100):.0f} pro Leg.'
            ),
            'icon': 'check_circle',
        })
        phase = 'arb_ready'

    # Tägliches Limit prüfen
    daily = account.get('daily_bet_count', 0)
    max_daily = account.get('max_daily_bets', 5)
    if daily >= max_daily:
        actions.insert(0, {
            'priority': 0,
            'type': 'limit',
            'title': f'Tageslimit erreicht ({daily}/{max_daily})',
            'detail': 'Heute nicht mehr wetten auf diesem Konto.',
            'icon': 'block',
        })

    actions.sort(key=lambda a: a['priority'])

    return {
        'account_id': account.get('id'),
        'account_label': account.get('user_label', account.get('bookmaker')),
        'bookmaker': account.get('bookmaker'),
        'phase': phase,
        'balance': balance,
        'deposit_pending': deposit_pending,
        'risk_score': risk_score,
        'risk_level': ban_risk.get('level', 'green') if isinstance(ban_risk, dict) else 'green',
        'bonus_status': bonus_status,
        'actions': actions,
        'arb_count_since_mug': arb_count_since_mug,
    }


# ─── Portfolio Übersicht ──────────────────────────────────────────────────────

def get_portfolio_overview(accounts: list) -> dict:
    """Gesamtübersicht über alle Konten."""
    total_balance = sum(a.get('current_balance', 0) for a in accounts)
    total_pending = sum(a.get('deposit_pending', 0) for a in accounts)
    total_bonus = sum(a.get('bonus_balance', 0) for a in accounts)
    total_available = total_balance  # Bonus ist meist nicht auszahlbar bis Wagering

    active = [a for a in accounts if a.get('status') == 'active']
    arb_ready = []
    needs_action = []

    for acc in accounts:
        arb_count = 0
        strategy = get_account_strategy(acc, arb_count)
        if strategy['phase'] == 'arb_ready':
            arb_ready.append(acc.get('user_label', acc.get('bookmaker')))
        elif strategy['phase'] != 'waiting_deposit':
            needs_action.append({
                'label': acc.get('user_label', acc.get('bookmaker')),
                'phase': strategy['phase'],
                'top_action': strategy['actions'][0]['title'] if strategy['actions'] else '',
            })

    # Gesamtstrategie-Empfehlung
    if len(arb_ready) >= 2:
        recommendation = f'{len(arb_ready)} Konten bereit für Arb. Starte Scanner.'
    elif any(a['phase'] == 'bonus_clearing' for a in [get_account_strategy(a, 0) for a in accounts]):
        recommendation = 'Erst Boni freiwetten, dann Arb starten.'
    else:
        recommendation = 'Konten aufwärmen — noch zu wenig Wetthistorie.'

    return {
        'total_balance': round(total_balance, 2),
        'total_pending': round(total_pending, 2),
        'total_bonus': round(total_bonus, 2),
        'total_available': round(total_available, 2),
        'total_accounts': len(accounts),
        'active_accounts': len(active),
        'arb_ready_accounts': arb_ready,
        'needs_action': needs_action,
        'recommendation': recommendation,
    }


# ─── Hedge / Gegenwette ───────────────────────────────────────────────────────

def get_hedge_suggestion(open_bets: list) -> list:
    """
    Wenn mehrere Legs offen sind und eine Seite verliert → Gegenwette vorschlagen.
    open_bets: Liste von dicts mit {outcome, odds, stake, bookmaker}
    """
    suggestions = []
    for bet in open_bets:
        stake = bet.get('stake', 0)
        odds = bet.get('odds', 2.0)
        outcome = bet.get('outcome', '')
        potential_loss = stake  # bei Arb kein wirklicher Verlust, aber bei Einzelwetten

        # Hedge: genug auf Gegenereignis setzen um Verlust abzudecken
        hedge_stake = round(stake / (odds - 1), 2) if odds > 1 else 0
        suggestions.append({
            'original_outcome': outcome,
            'original_stake': stake,
            'original_odds': odds,
            'hedge_stake': hedge_stake,
            'note': f'Setze €{hedge_stake:.2f} auf Gegenereignis um Einsatz abzusichern',
        })
    return suggestions
