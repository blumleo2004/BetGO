"""
BETGO - Arbitrage Dashboard
Flask web server for the betting arbitrage scanner
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from arb_engine import ArbEngine
import config
import simulation
import threading
import uuid
import logging
import traceback
from collections import deque
from datetime import datetime


from auth import auth_bp, init_oauth
from models import db, User
from flask_login import LoginManager, current_user

app = Flask(__name__)
CORS(app)

# ─── Debug Logging ────────────────────────────────────────────────────────────
# Ring buffer for recent logs (accessible via /api/debug)
_debug_log = deque(maxlen=200)

def _log(level, msg, **extra):
    entry = {
        'ts': datetime.utcnow().isoformat(),
        'level': level,
        'msg': msg,
        **extra
    }
    _debug_log.append(entry)
    # Also print (safe for Windows cp1252)
    safe = msg.encode('ascii', 'replace').decode()
    print(f'[{level}] {safe}')

@app.before_request
def _log_request():
    _log('REQ', f'{request.method} {request.path}', args=dict(request.args))

@app.after_request
def _log_response(response):
    if response.status_code >= 400:
        body = response.get_data(as_text=True)[:500]
        _log('ERR', f'{request.method} {request.path} -> {response.status_code}', body=body)
    return response

@app.errorhandler(Exception)
def _handle_error(e):
    tb = traceback.format_exc()
    _log('CRASH', f'{request.method} {request.path}: {e}', traceback=tb)
    return jsonify({'error': str(e), 'traceback': tb}), 500

# Initialize Extensions
app.config.from_object('config') # Load config from config.py
db.init_app(app)
init_oauth(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create DB Tables
with app.app_context():
    db.create_all()

# Start daily counter reset scheduler (resets account daily bet counters at midnight)
try:
    import auto_scanner as _auto_scanner
    _auto_scanner.scanner._start_daily_reset_scheduler(app)
except Exception as _e:
    print(f'[app] Could not start daily reset scheduler: {_e}')

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')

# Initialize the arbitrage engine
engine = ArbEngine()


# Background scan jobs (in-memory job queue)
scan_jobs = {}

@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('index.html')

@app.route('/simulation')
def simulation_page():
    """Serve the simulation dashboard"""
    return render_template('simulation.html')

@app.route('/settings')
def settings_page():
    """Serve the settings page"""
    return render_template('settings.html')

@app.route('/history')
def history_page():
    """Serve the history/performance page"""
    return render_template('history.html')

@app.route('/api/sports')
def get_sports():
    """Get list of available sports"""
    sports = engine.get_sports()
    return jsonify(sports)

@app.route('/api/bookmakers')
def get_bookmakers():
    """Get configured bookmakers"""
    return jsonify(config.BOOKMAKERS)

@app.route('/api/scan')
def scan_arbitrage():
    """
    Scan for arbitrage opportunities with filters
    Query params:
    - sports: comma-separated sport keys
    - markets: comma-separated market types (h2h,spreads,totals)
    - bookmakers: comma-separated bookmaker keys
    - min_roi: minimum ROI percentage
    - investment: total investment amount
    - hours: max hours into future
    - live: 1 for live only
    """
    # Parse query parameters
    sports = request.args.get('sports', '').split(',') if request.args.get('sports') else None
    markets = request.args.get('markets', 'h2h,spreads,totals')
    bookmakers = request.args.get('bookmakers', '').split(',') if request.args.get('bookmakers') else None
    min_roi = float(request.args.get('min_roi', 0.5))
    investment = float(request.args.get('investment', 500))
    max_hours = int(request.args.get('hours')) if request.args.get('hours') else None
    live_only = request.args.get('live', '0') == '1'
    
    # Clean up empty strings in lists
    if sports:
        sports = [s for s in sports if s]
    if bookmakers:
        bookmakers = [b for b in bookmakers if b]
    
    # Scan for opportunities
    opportunities = engine.scan_for_arbitrage(
        sports=sports if sports else None,
        markets=markets,
        bookmakers=bookmakers if bookmakers else None,
        min_roi=min_roi,
        investment=investment,
        max_hours=max_hours,
        live_only=live_only
    )
    
    # Get API usage
    usage = engine.get_api_usage()
    
    return jsonify({
        'opportunities': opportunities,
        'count': len(opportunities),
        'api_usage': usage
    })

@app.route('/api/usage')
def get_usage():
    """Get current API usage"""
    return jsonify(engine.get_api_usage())

# ============ ASYNC SCAN ENDPOINTS ============

def _run_scan_job(job_id: str, params: dict):
    """Background worker for async scans"""
    try:
        opportunities = engine.scan_for_arbitrage(
            sports=params.get('sports'),
            markets=params.get('markets', 'h2h,spreads,totals'),
            bookmakers=params.get('bookmakers'),
            min_roi=params.get('min_roi', 0.5),
            investment=params.get('investment', 500),
            max_hours=params.get('max_hours'),
            live_only=params.get('live_only', False)
        )
        usage = engine.get_api_usage()
        scan_jobs[job_id] = {
            'status': 'done',
            'result': {
                'opportunities': opportunities,
                'count': len(opportunities),
                'api_usage': usage
            }
        }
    except Exception as e:
        scan_jobs[job_id] = {
            'status': 'error',
            'error': str(e)
        }

@app.route('/api/scan/async')
def scan_async():
    """
    Start an async scan in background thread.
    Returns job_id to poll for results.
    Query params: same as /api/scan
    """
    # Parse parameters (same as sync scan)
    sports = request.args.get('sports', '').split(',') if request.args.get('sports') else None
    markets = request.args.get('markets', 'h2h,spreads,totals')
    bookmakers = request.args.get('bookmakers', '').split(',') if request.args.get('bookmakers') else None
    min_roi = float(request.args.get('min_roi', 0.5))
    investment = float(request.args.get('investment', 500))
    max_hours = int(request.args.get('hours')) if request.args.get('hours') else None
    live_only = request.args.get('live', '0') == '1'
    
    # Clean up empty strings
    if sports:
        sports = [s for s in sports if s]
    if bookmakers:
        bookmakers = [b for b in bookmakers if b]
    
    # Create job
    job_id = str(uuid.uuid4())
    scan_jobs[job_id] = {'status': 'running', 'result': None}
    
    params = {
        'sports': sports if sports else None,
        'markets': markets,
        'bookmakers': bookmakers if bookmakers else None,
        'min_roi': min_roi,
        'investment': investment,
        'max_hours': max_hours,
        'live_only': live_only
    }
    
    thread = threading.Thread(target=_run_scan_job, args=(job_id, params))
    thread.start()
    
    return jsonify({'job_id': job_id, 'status': 'running'})

@app.route('/api/scan/status/<job_id>')
def scan_status(job_id):
    """Get status of an async scan job"""
    job = scan_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/api/config')
def get_config():
    """Get frontend configuration"""
    return jsonify({
        'bookmakers': config.BOOKMAKERS,
        'markets': config.MARKETS,
        'sports': config.SPORT_CATEGORIES,
        'timeframes': config.TIMEFRAMES,
        'default_investment': config.DEFAULT_INVESTMENT,
        'default_min_roi': config.DEFAULT_MIN_ROI
    })

# ============ SIMULATION API ENDPOINTS ============

@app.route('/api/simulation/stats')
def get_simulation_stats():
    """Get simulation statistics"""
    return jsonify(simulation.get_simulation_stats())

@app.route('/api/simulation/place', methods=['POST'])
def place_virtual_bet():
    """Place a virtual bet"""
    data = request.get_json()
    result = simulation.place_virtual_bet(data)
    return jsonify(result)

@app.route('/api/simulation/settle', methods=['POST'])
def settle_bet():
    """Settle a pending bet"""
    data = request.get_json()
    bet_id = data.get('bet_id')
    winning_outcome = data.get('winning_outcome')
    result = simulation.settle_bet(bet_id, winning_outcome)
    return jsonify(result)

@app.route('/api/simulation/pending')
def get_pending_bets():
    """Get pending bets"""
    return jsonify(simulation.get_pending_bets())

@app.route('/api/simulation/history')
def get_bet_history():
    """Get bet history"""
    limit = request.args.get('limit', 50, type=int)
    return jsonify(simulation.get_bet_history(limit))

@app.route('/api/simulation/analytics')
def get_analytics():
    """Get strategy analytics"""
    return jsonify(simulation.get_analytics())

@app.route('/api/simulation/reset', methods=['POST'])
def reset_simulation():
    """Reset simulation"""
    data = request.get_json() or {}
    starting_bankroll = data.get('starting_bankroll', 1000)
    simulation.reset_simulation(starting_bankroll)
    return jsonify({'success': True, 'message': f'Simulation reset with €{starting_bankroll} bankroll'})

@app.route('/api/simulation/export')
def export_simulation():
    """Export simulation to CSV"""
    path = simulation.export_to_csv()
    return jsonify({'success': True, 'path': path})

# ============ API OPTIMIZER ENDPOINTS ============

@app.route('/api/optimizer/stats')
def get_optimizer_stats():
    """Get optimizer statistics (cache, keys, scheduler)"""
    import api_optimizer
    return jsonify(api_optimizer.get_optimizer_stats())

@app.route('/api/optimizer/keys', methods=['GET', 'POST'])
def manage_api_keys():
    """Get or add API keys"""
    import api_optimizer
    
    if request.method == 'POST':
        data = request.get_json()
        keys = data.get('keys', [])
        if isinstance(keys, str):
            keys = [keys]
        api_optimizer.key_manager.save_keys(keys)
        return jsonify({'success': True, 'message': f'Saved {len(keys)} API keys'})
    
    return jsonify(api_optimizer.key_manager.get_stats())

@app.route('/api/optimizer/keys/add', methods=['POST'])
def add_api_key():
    """Add a single API key"""
    import api_optimizer
    data = request.get_json()
    key = data.get('key')
    if key:
        api_optimizer.key_manager.add_key(key)
        return jsonify({'success': True, 'message': 'API key added'})
    return jsonify({'success': False, 'error': 'No key provided'})

@app.route('/api/optimizer/cache/clear', methods=['POST'])
def clear_cache():
    """Clear all cached data"""
    import api_optimizer
    api_optimizer.cache_manager.clear()
    return jsonify({'success': True, 'message': 'Cache cleared'})

@app.route('/api/optimizer/schedule')
def get_schedule_status():
    """Get smart scheduler status"""
    import api_optimizer
    return jsonify(api_optimizer.scheduler.get_status())

@app.route('/api/optimizer/api-sports-key', methods=['GET', 'POST'])
def manage_api_sports_key():
    """Get or set API-Sports key"""
    import api_optimizer
    
    if request.method == 'POST':
        data = request.get_json()
        key = data.get('key')
        if key:
            api_optimizer.key_manager.set_api_sports_key(key)
            return jsonify({'success': True, 'message': 'API-Sports key saved'})
        return jsonify({'success': False, 'error': 'No key provided'})
    
    # GET - return masked key
    key = api_optimizer.key_manager.get_api_sports_key()
    return jsonify({
        'has_key': key is not None,
        'key_preview': key[:8] + '...' if key else None
    })

# ============== AUTO SCANNER ==============

@app.route('/api/scanner/status')
def get_scanner_status():
    """Get auto scanner status"""
    import auto_scanner
    return jsonify(auto_scanner.get_status())

@app.route('/api/scanner/start', methods=['POST'])
def start_scanner():
    """Start auto scanner"""
    import auto_scanner
    return jsonify(auto_scanner.start_scanner())

@app.route('/api/scanner/stop', methods=['POST'])
def stop_scanner():
    """Stop auto scanner"""
    import auto_scanner
    return jsonify(auto_scanner.stop_scanner())

@app.route('/api/scanner/config', methods=['POST'])
def configure_scanner():
    """Configure auto scanner"""
    import auto_scanner
    data = request.get_json()
    return jsonify(auto_scanner.configure(**data))

@app.route('/api/scanner/scan', methods=['POST'])
def manual_scan():
    """Run a single manual scan"""
    import auto_scanner
    result = auto_scanner.scanner.scan_once()
    return jsonify(result)

@app.route('/api/discord/webhook', methods=['GET', 'POST'])
def manage_discord_webhook():
    """Get or set Discord webhook URL"""
    import auto_scanner
    
    if request.method == 'POST':
        data = request.get_json()
        url = data.get('url')
        if url:
            auto_scanner.set_discord_webhook(url)
            return jsonify({'success': True, 'message': 'Discord webhook configured'})
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    return jsonify({
        'configured': bool(auto_scanner.scanner.notifier.webhook_url)
    })

@app.route('/api/discord/test', methods=['POST'])
def test_discord():
    """Test Discord notification"""
    import auto_scanner
    success = auto_scanner.test_discord()
    return jsonify({'success': success})

# Alias for settings page
@app.route('/api/scanner/discord', methods=['GET', 'POST'])
def scanner_discord_settings():
    """Get or set Discord webhook URL (alias for settings page)"""
    import auto_scanner
    
    if request.method == 'POST':
        data = request.get_json()
        url = data.get('webhook_url') or data.get('url')
        if url:
            auto_scanner.set_discord_webhook(url)
            return jsonify({'success': True, 'message': 'Discord webhook configured'})
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    webhook = auto_scanner.scanner.notifier.webhook_url
    return jsonify({
        'configured': bool(webhook),
        'webhook_url': webhook if webhook else None
    })

@app.route('/api/scanner/discord/test', methods=['POST'])
def scanner_discord_test():
    """Test Discord notification (alias)"""
    import auto_scanner
    success = auto_scanner.test_discord()
    return jsonify({'success': success})


# ============ ACCOUNT MANAGER ENDPOINTS ============

@app.route('/api/accounts', methods=['GET'])
def list_accounts():
    import account_manager
    status = request.args.get('status')
    bookmaker = request.args.get('bookmaker')
    return jsonify(account_manager.get_accounts(status_filter=status, bookmaker_filter=bookmaker))


@app.route('/api/accounts', methods=['POST'])
def create_account():
    import account_manager
    data = request.get_json() or {}
    bookmaker_key = data.get('bookmaker')
    if not bookmaker_key:
        return jsonify({'error': 'bookmaker field required'}), 400
    result = account_manager.add_account(
        bookmaker_key=bookmaker_key,
        label=data.get('label'),
        initial_balance=float(data.get('initial_balance', 0)),
        username=data.get('username'),
        max_daily_bets=int(data.get('max_daily_bets', 5)),
        max_weekly_bets=int(data.get('max_weekly_bets', 20)),
        min_stake=float(data.get('min_stake', 5.0)),
        max_stake=float(data.get('max_stake', 100.0)),
        notes=data.get('notes'),
    )
    return jsonify(result), 201


@app.route('/api/accounts/<int:account_id>', methods=['GET'])
def get_account_endpoint(account_id):
    import account_manager
    account = account_manager.get_account(account_id)
    if not account:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(account)


@app.route('/api/accounts/<int:account_id>', methods=['PATCH'])
def update_account_endpoint(account_id):
    import account_manager
    data = request.get_json() or {}
    if 'status' in data:
        result = account_manager.set_status(account_id, data['status'], data.get('notes'))
        if not result:
            return jsonify({'error': 'Invalid status or account not found'}), 400
        return jsonify(result)
    if 'current_balance' in data:
        result = account_manager.update_balance(account_id, float(data['current_balance']), data.get('notes'))
        if not result:
            return jsonify({'error': 'Account not found'}), 404
        return jsonify(result)
    result = account_manager.update_account(account_id, **data)
    if not result:
        return jsonify({'error': 'Account not found'}), 404
    return jsonify(result)


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account_endpoint(account_id):
    import account_manager
    if account_manager.delete_account(account_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/accounts/<int:account_id>/activity')
def account_activity(account_id):
    import account_manager
    limit = request.args.get('limit', 50, type=int)
    return jsonify(account_manager.get_account_activity(account_id, limit))


@app.route('/api/accounts/<int:account_id>/ban-risk')
def account_ban_risk(account_id):
    import account_manager
    return jsonify(account_manager.get_ban_risk_score(account_id))


@app.route('/api/accounts/<int:account_id>/mug-suggestion')
def account_mug_suggestion(account_id):
    import account_manager
    import mug_bet_advisor
    account = account_manager.get_account(account_id)
    if not account:
        return jsonify({'error': 'Not found'}), 404
    arb_count = mug_bet_advisor.get_arb_count_since_last_mug(account_id)
    return jsonify(mug_bet_advisor.get_mug_suggestion(account, arb_count))


@app.route('/api/accounts/<int:account_id>/mug-record', methods=['POST'])
def record_mug_bet_endpoint(account_id):
    import mug_bet_advisor
    data = request.get_json() or {}
    stake = float(data.get('stake', 0))
    if stake <= 0:
        return jsonify({'error': 'stake required'}), 400
    return jsonify(mug_bet_advisor.record_mug_bet(account_id, stake, data.get('notes')))


@app.route('/api/accounts/bookmaker/<bookmaker_key>')
def accounts_for_bookmaker(bookmaker_key):
    import account_manager
    return jsonify(account_manager.get_usable_accounts_for_bookmaker(bookmaker_key))


@app.route('/api/accounts/reset-daily', methods=['POST'])
def reset_daily_counters():
    import account_manager
    account_manager.reset_daily_counters()
    return jsonify({'success': True, 'message': 'Daily counters reset'})


# ============ STEALTH ENDPOINTS ============

@app.route('/api/stealth/round-stakes')
def preview_rounded_stakes():
    """Preview how a stake amount would be rounded"""
    import stealth
    raw = request.args.get('amount', type=float)
    if raw is None:
        return jsonify({'error': 'amount param required'}), 400
    return jsonify({'raw': raw, 'rounded': stealth.round_stake_natural(raw)})


@app.route('/api/stealth/timing')
def preview_leg_timing():
    """Preview timing delays for N legs"""
    import stealth
    legs = request.args.get('legs', 2, type=int)
    return jsonify({'legs': legs, 'delay_seconds': stealth.get_leg_placement_delays(legs)})


# ============ WM 2026 ENDPOINTS ============

@app.route('/api/wm2026/status')
def wm2026_status():
    import tournament_filter
    return jsonify(tournament_filter.get_status())


@app.route('/api/wm2026/scan')
def wm2026_scan():
    import tournament_filter
    wm_sport = config.WM2026['sport_key']
    min_roi = float(request.args.get('min_roi', config.WM2026['min_roi_wm']))
    investment = float(request.args.get('investment', config.DEFAULT_INVESTMENT))
    opportunities = engine.scan_for_arbitrage(
        sports=[wm_sport], markets='h2h', min_roi=min_roi, investment=investment,
    )
    return jsonify({
        'opportunities': opportunities,
        'count': len(opportunities),
        'wm_phase': tournament_filter.get_wm2026_phase(),
        'api_usage': engine.get_api_usage(),
    })


@app.route('/api/quality/config', methods=['GET', 'POST'])
def quality_config():
    """Get or update quality filter thresholds at runtime"""
    if request.method == 'POST':
        data = request.get_json() or {}
        allowed = {'max_roi', 'min_bookmakers_in_market', 'max_odds_per_leg',
                   'min_stake', 'require_all_accounts_available'}
        for k, v in data.items():
            if k in allowed:
                config.QUALITY_CONFIG[k] = v
        return jsonify({'success': True, 'config': config.QUALITY_CONFIG})
    return jsonify(config.QUALITY_CONFIG)


# ============ ANALYTICS ENDPOINTS ============

@app.route('/api/analytics/dashboard')
def analytics_dashboard():
    import analytics
    return jsonify(analytics.get_full_dashboard())


@app.route('/api/analytics/pnl/bookmaker')
def analytics_pnl_bookmaker():
    import analytics
    days = request.args.get('days', 30, type=int)
    return jsonify(analytics.get_pnl_by_bookmaker(days))


@app.route('/api/analytics/pnl/timeline')
def analytics_pnl_timeline():
    import analytics
    days = request.args.get('days', 30, type=int)
    granularity = request.args.get('granularity', 'day')
    return jsonify(analytics.get_pnl_timeline(days, granularity))


@app.route('/api/analytics/wm2026-readiness')
def analytics_wm2026_readiness():
    import analytics
    return jsonify(analytics.get_wm2026_readiness_report())


@app.route('/api/analytics/opportunities')
def analytics_opportunities():
    """Summary of recent arb opportunities placed as simulation bets"""
    import analytics
    days = request.args.get('days', 7, type=int)
    return jsonify(analytics.get_opportunity_summary(days))


@app.route('/api/simulation/auto-settle', methods=['POST'])
def auto_settle():
    """Auto-settle pending bets using real match results"""
    import auto_settler
    import api_optimizer
    key = api_optimizer.get_api_key() or config.API_KEY
    return jsonify(auto_settler.try_settle_pending_bets(key))


@app.route('/accounts')
def accounts_page():
    """Account manager dashboard"""
    return render_template('accounts.html')


# ============ DEBUG ENDPOINTS ============

@app.route('/api/debug')
def debug_logs():
    """Recent server logs — use this to diagnose issues remotely"""
    level = request.args.get('level')  # filter: ERR, CRASH, REQ
    limit = request.args.get('limit', 50, type=int)
    logs = list(_debug_log)
    if level:
        logs = [l for l in logs if l['level'] == level.upper()]
    return jsonify(logs[-limit:])


@app.route('/api/debug/js-error', methods=['POST'])
def js_error():
    """Receive JavaScript errors from the browser"""
    data = request.get_json() or {}
    _log('JS', data.get('message', 'unknown'), source=data.get('source'), line=data.get('line'), stack=data.get('stack'))
    return jsonify({'ok': True})


@app.route('/api/debug/health')
def health_check():
    """Quick health check of all subsystems"""
    from models import BookmakerAccount, ArbitrageRecord
    import tournament_filter
    checks = {}
    try:
        checks['db'] = {'ok': True, 'accounts': BookmakerAccount.query.count(), 'arbs': ArbitrageRecord.query.count()}
    except Exception as e:
        checks['db'] = {'ok': False, 'error': str(e)}
    try:
        checks['wm2026'] = tournament_filter.get_status()
    except Exception as e:
        checks['wm2026'] = {'ok': False, 'error': str(e)}
    checks['recent_errors'] = [l for l in list(_debug_log)[-20:] if l['level'] in ('ERR', 'CRASH', 'JS')]
    return jsonify(checks)


if __name__ == '__main__':
    print("BETGO Dashboard starting...")
    print("Open http://localhost:5000 in your browser")
    print("Simulation: http://localhost:5000/simulation")
    print("Accounts: http://localhost:5000/accounts")
    print("Debug: http://localhost:5000/api/debug/health")

    import api_optimizer
    try:
        status = api_optimizer.scheduler.get_status()
        print(f"Scheduler: {str(status.get('status','')).encode('ascii','replace').decode()}")
    except Exception:
        pass
    keys_count = len(api_optimizer.key_manager.keys)
    print(f"The Odds API: {keys_count} keys loaded")

    import auto_scanner
    print(f"Discord: {'Connected' if auto_scanner.scanner.notifier.webhook_url else 'Not configured'}")
    print("To start auto-scanning: POST /api/scanner/start")

    app.run(debug=True, port=5000)
