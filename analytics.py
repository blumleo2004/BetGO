"""
BETGO Analytics
P&L queries, account health dashboard, WM 2026 readiness report.
"""

from datetime import datetime, timedelta
import config


def get_pnl_by_bookmaker(days: int = 30) -> list:
    """P&L breakdown per bookmaker account (last N days)."""
    from models import BookmakerAccount, ArbitrageRecord, ArbitrageLeg

    since = datetime.utcnow() - timedelta(days=days)
    accounts = BookmakerAccount.query.all()
    results = []

    for acc in accounts:
        legs = (ArbitrageLeg.query
                .filter_by(account_id=acc.id)
                .join(ArbitrageRecord)
                .filter(ArbitrageRecord.placed_at >= since)
                .all())

        if not legs:
            continue

        total_staked = sum(l.rounded_stake or l.stake or 0 for l in legs)
        total_returned = sum(l.actual_return or 0 for l in legs)
        arb_ids = set(l.arb_record_id for l in legs)

        results.append({
            'account_id': acc.id,
            'account_label': acc.user_label or acc.bookmaker,
            'bookmaker': acc.bookmaker,
            'bet_count': len(arb_ids),
            'total_staked': round(total_staked, 2),
            'total_returned': round(total_returned, 2),
            'profit': round(total_returned - total_staked, 2),
            'roi': round(((total_returned - total_staked) / total_staked * 100)
                         if total_staked > 0 else 0, 2),
            'current_balance': acc.current_balance,
            'status': acc.status,
        })

    results.sort(key=lambda x: x['profit'], reverse=True)
    return results


def get_pnl_timeline(days: int = 30, granularity: str = 'day') -> list:
    """Daily/weekly cumulative P&L for charting."""
    from models import ArbitrageRecord

    since = datetime.utcnow() - timedelta(days=days)
    records = (ArbitrageRecord.query
               .filter(ArbitrageRecord.placed_at >= since,
                       ArbitrageRecord.status == 'settled')
               .order_by(ArbitrageRecord.placed_at)
               .all())

    timeline = {}
    for rec in records:
        key = (rec.placed_at.strftime('%Y-%m-%d')
               if granularity == 'day'
               else rec.placed_at.strftime('%Y-W%W'))
        if key not in timeline:
            timeline[key] = {'staked': 0, 'returned': 0, 'bets': 0}
        timeline[key]['staked'] += rec.total_stake or 0
        timeline[key]['returned'] += rec.actual_return or 0
        timeline[key]['bets'] += 1

    result = []
    cumulative_profit = 0.0
    for date_key in sorted(timeline.keys()):
        d = timeline[date_key]
        profit = d['returned'] - d['staked']
        cumulative_profit += profit
        result.append({
            'date': date_key,
            'staked': round(d['staked'], 2),
            'returned': round(d['returned'], 2),
            'profit': round(profit, 2),
            'cumulative_profit': round(cumulative_profit, 2),
            'roi': round((profit / d['staked'] * 100) if d['staked'] > 0 else 0, 2),
            'bets': d['bets'],
        })

    return result


def get_account_health_dashboard() -> dict:
    """All accounts with health summary."""
    import account_manager
    accounts = account_manager.get_accounts()

    return {
        'total': len(accounts),
        'active': sum(1 for a in accounts if a['status'] == 'active'),
        'restricted': sum(1 for a in accounts if a['status'] == 'restricted'),
        'gubbed': sum(1 for a in accounts if a['status'] == 'gubbed'),
        'new': sum(1 for a in accounts if a['status'] == 'new'),
        'high_risk': sum(1 for a in accounts if a['ban_risk']['score'] > 50),
        'total_balance': round(sum(a['current_balance'] for a in accounts), 2),
        'accounts': accounts,
    }


def get_wm2026_readiness_report() -> dict:
    """Check how ready the system is for WM 2026."""
    import tournament_filter
    from models import BookmakerAccount

    wm = config.WM2026
    priority_books = wm['priority_bookmakers']
    report = {
        'days_until_wm': tournament_filter.days_until_wm2026(),
        'phase': tournament_filter.get_wm2026_phase(),
        'bookmakers': {},
    }

    for book_key in priority_books:
        accounts = BookmakerAccount.query.filter_by(bookmaker=book_key).all()
        active = [a for a in accounts if a.status == 'active']
        total_balance = sum(a.current_balance for a in active)

        issues = []
        if not accounts:
            issues.append('Kein Konto vorhanden')
        elif not active:
            issues.append('Konto vorhanden, aber nicht aktiv')
        elif total_balance < 50:
            issues.append(f'Guthaben zu niedrig (€{total_balance:.0f})')

        report['bookmakers'][book_key] = {
            'name': config.BOOKMAKERS.get(book_key, {}).get('name', book_key),
            'has_account': len(accounts) > 0,
            'active_accounts': len(active),
            'total_balance': round(total_balance, 2),
            'ready': len(active) > 0 and total_balance >= 50,
            'issues': issues,
        }

    ready = sum(1 for b in report['bookmakers'].values() if b['ready'])
    total = len(priority_books)
    report.update({
        'ready_count': ready,
        'total_priority_books': total,
        'readiness_pct': round(ready / total * 100) if total else 0,
        'overall_ready': ready >= max(1, total // 2),
    })

    return report


def get_opportunity_summary(days: int = 7) -> dict:
    """Summary of recent opportunities placed as simulation bets."""
    try:
        from models import ArbitrageRecord

        since = datetime.utcnow() - timedelta(days=days)
        records = ArbitrageRecord.query.filter(
            ArbitrageRecord.placed_at >= since
        ).all()

        if not records:
            return {'total': 0, 'days': days}

        avg_roi = sum(r.expected_roi or 0 for r in records) / len(records)
        avg_quality = sum(r.quality_score or 0 for r in records) / len(records)
        best = max(records, key=lambda r: r.expected_roi or 0)

        return {
            'total': len(records),
            'days': days,
            'avg_roi': round(avg_roi, 2),
            'avg_quality_score': round(avg_quality, 1),
            'settled': sum(1 for r in records if r.status == 'settled'),
            'pending': sum(1 for r in records if r.status == 'pending'),
            'best_opportunity': {
                'event': (f"{best.home_team} vs {best.away_team}"
                          if best.home_team else None),
                'roi': best.expected_roi,
                'sport': best.sport_title,
            } if records else None,
            'total_staked': round(sum(r.total_stake or 0 for r in records), 2),
            'expected_profit': round(
                sum(r.expected_profit or 0 for r in records), 2
            ),
        }
    except Exception as e:
        return {'error': str(e), 'total': 0, 'days': days}


def get_full_dashboard() -> dict:
    """Combined dashboard for the analytics page."""
    return {
        'pnl_by_bookmaker': get_pnl_by_bookmaker(30),
        'pnl_timeline': get_pnl_timeline(30),
        'account_health': get_account_health_dashboard(),
        'wm2026_readiness': get_wm2026_readiness_report(),
        'generated_at': datetime.utcnow().isoformat(),
    }
