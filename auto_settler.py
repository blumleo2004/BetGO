"""
BETGO Auto Settler
Fetches real match results and settles pending simulation bets automatically.
"""
import requests
from datetime import datetime, timezone
import config
import simulation


def fetch_scores(sport_key: str, api_key: str) -> list:
    """Fetch completed game scores from The Odds API"""
    try:
        url = f"{config.API_BASE_URL}/sports/{sport_key}/scores"
        r = requests.get(url, params={
            'api_key': api_key,
            'daysFrom': 1,  # scores from last 1 day
        }, timeout=10)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception:
        return []


def determine_winner(game: dict) -> str | None:
    """
    Determine the winning outcome from a completed game.
    Returns the winning team name, or None if game not complete.
    """
    if not game.get('completed'):
        return None

    scores = game.get('scores')
    if not scores or len(scores) < 2:
        return None

    home = game.get('home_team')
    away = game.get('away_team')

    # Find home and away scores
    home_score = None
    away_score = None
    for s in scores:
        if s.get('name') == home:
            home_score = float(s.get('score', 0))
        elif s.get('name') == away:
            away_score = float(s.get('score', 0))

    if home_score is None or away_score is None:
        return None

    if home_score > away_score:
        return home
    elif away_score > home_score:
        return away
    else:
        return 'Draw'


def try_settle_pending_bets(api_key: str = None) -> dict:
    """
    Try to settle all pending simulation bets using real results.
    Returns summary of settled bets.
    """
    if not api_key:
        api_key = config.API_KEY
    if not api_key:
        return {'error': 'No API key configured'}

    try:
        pending = simulation.get_pending_bets()
    except Exception as e:
        return {'error': f'Could not load pending bets: {e}'}

    if not pending:
        return {'settled': 0, 'message': 'No pending bets'}

    settled = []
    errors = []

    # Get unique sports from pending bets
    sports = set(b.get('sport') for b in pending if b.get('sport'))

    # Fetch scores per sport
    all_scores = {}
    for sport in sports:
        try:
            scores = fetch_scores(sport, api_key)
            for game in scores:
                key = f"{game.get('home_team')}_{game.get('away_team')}"
                all_scores[key] = game
        except Exception as e:
            errors.append(f'Score fetch error for {sport}: {e}')

    for bet in pending:
        try:
            home = bet.get('home_team', '')
            away = bet.get('away_team', '')
            key = f"{home}_{away}"

            game = all_scores.get(key)
            if not game:
                continue

            winner = determine_winner(game)
            if not winner:
                continue

            # Find matching outcome in bet legs
            winning_outcome = None
            for leg in bet.get('legs', []):
                outcome = leg.get('outcome', '')
                if (winner in outcome or outcome in winner
                        or (winner == 'Draw' and 'Draw' in outcome)):
                    winning_outcome = outcome
                    break

            if not winning_outcome:
                # Try case-insensitive partial match
                outcomes = [l.get('outcome', '') for l in bet.get('legs', [])]
                for outcome in outcomes:
                    if winner.lower() in outcome.lower():
                        winning_outcome = outcome
                        break

            if winning_outcome:
                result = simulation.settle_bet(bet['id'], winning_outcome)
                if result.get('success'):
                    settled.append({
                        'bet_id': bet['id'],
                        'event': f"{home} vs {away}",
                        'winner': winner,
                        'profit': result.get('profit', 0),
                    })
                else:
                    errors.append(str(result.get('error', '')))
        except Exception as e:
            errors.append(f'Error settling bet {bet.get("id")}: {e}')

    return {
        'settled': len(settled),
        'bets': settled,
        'errors': errors,
        'checked_games': len(all_scores),
        'pending_before': len(pending),
    }
