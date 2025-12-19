"""
BETGO - Arbitrage Dashboard
Flask web server for the betting arbitrage scanner
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from arb_engine import ArbEngine
import config
import simulation

app = Flask(__name__)
CORS(app)

# Initialize the arbitrage engine
engine = ArbEngine()

@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('index.html')

@app.route('/simulation')
def simulation_page():
    """Serve the simulation dashboard"""
    return render_template('simulation.html')

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

if __name__ == '__main__':
    print("🚀 BETGO Dashboard starting...")
    print("📊 Open http://localhost:5000 in your browser")
    print("🎮 Simulation: http://localhost:5000/simulation")
    
    # Show smart scheduling status
    import api_optimizer
    status = api_optimizer.scheduler.get_status()
    print(f"⏰ {status['status']}")
    
    # Show API keys count
    keys_count = len(api_optimizer.key_manager.keys)
    print(f"🔑 The Odds API: {keys_count} keys loaded")
    
    # Check Discord
    import auto_scanner
    if auto_scanner.scanner.notifier.webhook_url:
        print("💬 Discord: Connected")
    else:
        print("💬 Discord: Not configured (POST /api/discord/webhook)")
    
    print("\n📡 To start auto-scanning: POST /api/scanner/start")
    
    app.run(debug=True, port=5000)
