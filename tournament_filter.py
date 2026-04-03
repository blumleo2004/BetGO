"""
BETGO Tournament Filter
WM 2026 (FIFA World Cup) awareness, scanner config overrides, readiness checks.
"""

from datetime import date, datetime
import config


def is_wm2026_active() -> bool:
    """Check if WM 2026 is currently running."""
    wm = config.WM2026
    today = date.today()
    return date.fromisoformat(wm['start_date']) <= today <= date.fromisoformat(wm['end_date'])


def get_wm2026_phase() -> str:
    """Return the current WM 2026 tournament phase."""
    wm = config.WM2026
    today = date.today()
    start = date.fromisoformat(wm['start_date'])
    group_end = date.fromisoformat(wm['group_stage_end'])
    r32_start = date.fromisoformat(wm['round_of_32_start'])
    knockout_start = date.fromisoformat(wm['knockout_start'])
    end = date.fromisoformat(wm['end_date'])

    if today < start:
        return 'pre_tournament'
    elif today <= group_end:
        return 'group_stage'
    elif today < knockout_start:
        return 'round_of_32'
    elif today < end:
        return 'knockout'
    elif today == end:
        return 'final'
    else:
        return 'post_tournament'


def days_until_wm2026() -> int:
    """Days until WM 2026 starts (0 if already active or past)."""
    start = date.fromisoformat(config.WM2026['start_date'])
    delta = start - date.today()
    return max(0, delta.days)


def get_wm2026_scanner_config() -> dict:
    """Scanner config overrides during WM 2026."""
    phase = get_wm2026_phase()
    wm = config.WM2026

    base = {
        'sport_filter': [wm['sport_key']],
        'min_roi': wm['min_roi_wm'],
        'markets': 'h2h',
    }

    if phase == 'group_stage':
        base.update({
            'peak_start': 17, 'peak_end': 3,  # US kickoffs late Vienna time
            'peak_interval': 900,              # 15 min
            'note': 'Gruppenphase: viele Spiele, 15-Minuten-Intervall'
        })
    elif phase in ('round_of_32', 'knockout'):
        base.update({
            'peak_start': 18, 'peak_end': 2,
            'peak_interval': 600,
            'note': 'KO-Phase: 10-Minuten-Intervall, höhere Liquidität'
        })
    elif phase == 'final':
        base.update({
            'peak_start': 20, 'peak_end': 23,
            'peak_interval': 300,
            'max_investment': 300,
            'note': 'Finale: maximal konservativ, Buchmacher sehr aufmerksam'
        })

    return base


def filter_for_wm2026(opportunities: list) -> list:
    """Return only WM 2026 opportunities from a list."""
    sport_key = config.WM2026['sport_key']
    return [o for o in opportunities if o.get('sport') == sport_key]


def get_stage_aware_investment(phase: str, base_investment: float) -> float:
    """Adjust investment amount based on WM phase risk."""
    multipliers = {
        'pre_tournament': 1.0,
        'group_stage': 1.0,
        'round_of_32': 1.1,
        'knockout': 1.2,
        'final': 0.6,    # Very conservative — bookmakers watch the final closely
        'post_tournament': 1.0,
    }
    return base_investment * multipliers.get(phase, 1.0)


def get_status() -> dict:
    """Full WM 2026 status overview."""
    phase = get_wm2026_phase()
    days_left = days_until_wm2026()
    active = is_wm2026_active()

    phase_messages = {
        'pre_tournament': f'WM 2026 startet in {days_left} Tagen (11. Juni 2026)',
        'group_stage': 'WM 2026 läuft — Gruppenphase',
        'round_of_32': 'WM 2026 — Achtelfinale',
        'knockout': 'WM 2026 — KO-Phase',
        'final': 'WM 2026 FINALE',
        'post_tournament': 'WM 2026 ist vorbei',
    }

    return {
        'active': active,
        'phase': phase,
        'days_until_start': days_left,
        'start_date': config.WM2026['start_date'],
        'end_date': config.WM2026['end_date'],
        'sport_key': config.WM2026['sport_key'],
        'priority_bookmakers': config.WM2026['priority_bookmakers'],
        'min_roi_wm': config.WM2026['min_roi_wm'],
        'scanner_config': get_wm2026_scanner_config() if active else None,
        'message': phase_messages.get(phase, ''),
    }
