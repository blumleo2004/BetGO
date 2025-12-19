"""
BETGO Auto Scanner with Discord Notifications
Runs in background, scans for arbitrage, auto-places simulation bets, and notifies via Discord
"""

import time
import json
import requests
import threading
from datetime import datetime
from pathlib import Path

# Import our modules
import arb_engine
import simulation


class DiscordNotifier:
    """Send notifications to Discord via webhook"""
    
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url
        self._load_webhook()
    
    def _load_webhook(self):
        """Load webhook URL from config"""
        config_path = Path(__file__).parent / 'discord_config.json'
        if config_path.exists():
            with open(config_path, 'r') as f:
                data = json.load(f)
                self.webhook_url = data.get('webhook_url')
    
    def set_webhook(self, url: str):
        """Set and save webhook URL"""
        self.webhook_url = url
        config_path = Path(__file__).parent / 'discord_config.json'
        with open(config_path, 'w') as f:
            json.dump({'webhook_url': url}, f, indent=2)
    
    def send(self, title: str, description: str, color: int = 0x00FF00, fields: list = None):
        """Send embed message to Discord"""
        if not self.webhook_url:
            print("⚠️ Discord webhook not configured")
            return False
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "BETGO Auto Scanner"}
        }
        
        if fields:
            embed["fields"] = fields
        
        payload = {"embeds": [embed]}
        
        try:
            response = requests.post(self.webhook_url, json=payload)
            return response.status_code == 204
        except Exception as e:
            print(f"Discord error: {e}")
            return False
    
    def notify_bet_placed(self, bet_data: dict):
        """Send notification for placed simulation bet"""
        opp = bet_data.get('opportunity', {})
        
        fields = [
            {"name": "🏆 Sport", "value": opp.get('sport', 'Unknown'), "inline": True},
            {"name": "📈 ROI", "value": f"{opp.get('roi', 0):.2f}%", "inline": True},
            {"name": "💰 Investment", "value": f"€{bet_data.get('total_investment', 0):.2f}", "inline": True},
            {"name": "🎯 Match", "value": f"{opp.get('home_team', '?')} vs {opp.get('away_team', '?')}", "inline": False},
        ]
        
        # Add bet details
        bets = opp.get('bets', [])
        for i, bet in enumerate(bets):
            fields.append({
                "name": f"Bet {i+1}: {bet.get('bookmaker', '?')}",
                "value": f"{bet.get('outcome', '?')} @ {bet.get('odds', 0):.2f} - €{bet.get('stake', 0):.2f}",
                "inline": True
            })
        
        return self.send(
            title="🎲 New Simulation Bet Placed!",
            description=f"Found arbitrage opportunity with {opp.get('roi', 0):.2f}% ROI",
            color=0x00FF00,  # Green
            fields=fields
        )
    
    def notify_scan_summary(self, opportunities_found: int, bets_placed: int):
        """Send scan summary"""
        return self.send(
            title="📊 Scan Complete",
            description=f"Found {opportunities_found} opportunities, placed {bets_placed} simulation bets",
            color=0x3498DB  # Blue
        )


class AutoScanner:
    """Automatic arbitrage scanner with simulation betting"""
    
    def __init__(self):
        self.engine = arb_engine.ArbEngine()
        self.notifier = DiscordNotifier()
        self.running = False
        
        # Smart scheduling - only scan during peak betting hours
        self.peak_start = 17  # 17:00 - Games starting
        self.peak_end = 22    # 22:00 - Last games
        self.peak_interval = 1800  # 30 minutes - ~10 scans/day = 120 credits
        self.off_peak_interval = 3600  # 1 hour outside peak (or skip)
        self.skip_off_peak = True  # Don't scan at all outside peak hours
        
        self.min_roi = 0.5  # Minimum ROI to place bet
        self.max_investment = 100  # Max investment per opportunity
        self.auto_bet = True  # Automatically place simulation bets
        self.thread = None
        self.last_scan = None
        self.next_scan = None
        self.stats = {
            'scans': 0,
            'opportunities_found': 0,
            'bets_placed': 0,
            'total_invested': 0,
            'credits_used': 0
        }
    
    def is_peak_hours(self) -> bool:
        """Check if current time is within peak betting hours"""
        current_hour = datetime.now().hour
        return self.peak_start <= current_hour < self.peak_end
    
    def get_scan_interval(self) -> int:
        """Get appropriate scan interval based on time"""
        if self.is_peak_hours():
            return self.peak_interval
        return self.off_peak_interval
    
    def get_time_until_peak(self) -> int:
        """Get seconds until peak hours start"""
        now = datetime.now()
        current_hour = now.hour
        
        if current_hour >= self.peak_end:
            # After peak - wait until tomorrow
            hours_until = (24 - current_hour) + self.peak_start
        elif current_hour < self.peak_start:
            # Before peak today
            hours_until = self.peak_start - current_hour
        else:
            return 0  # Already in peak
        
        # Subtract current minutes for accuracy
        return (hours_until * 3600) - (now.minute * 60)
    
    def configure(self, **kwargs):
        """Configure scanner settings"""
        if 'peak_start' in kwargs:
            self.peak_start = kwargs['peak_start']
        if 'peak_end' in kwargs:
            self.peak_end = kwargs['peak_end']
        if 'peak_interval' in kwargs:
            self.peak_interval = kwargs['peak_interval']
        if 'min_roi' in kwargs:
            self.min_roi = kwargs['min_roi']
        if 'max_investment' in kwargs:
            self.max_investment = kwargs['max_investment']
        if 'auto_bet' in kwargs:
            self.auto_bet = kwargs['auto_bet']
        if 'webhook_url' in kwargs:
            self.notifier.set_webhook(kwargs['webhook_url'])
        if 'skip_off_peak' in kwargs:
            self.skip_off_peak = kwargs['skip_off_peak']
    
    def scan_once(self) -> dict:
        """Run a single scan"""
        print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] Starting scan...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'opportunities': [],
            'bets_placed': []
        }
        
        try:
            # Run the scan
            opportunities = self.engine.scan_all_sports()
            results['opportunities'] = opportunities
            self.stats['scans'] += 1
            self.stats['opportunities_found'] += len(opportunities)
            
            print(f"   Found {len(opportunities)} arbitrage opportunities")
            
            # Auto-place simulation bets
            if self.auto_bet and opportunities:
                for opp in opportunities:
                    if opp.get('roi', 0) >= self.min_roi:
                        bet_result = simulation.place_virtual_bet(
                            opp, 
                            investment=min(self.max_investment, 100)
                        )
                        
                        if bet_result.get('success'):
                            results['bets_placed'].append(bet_result)
                            self.stats['bets_placed'] += 1
                            self.stats['total_invested'] += bet_result.get('total_investment', 0)
                            
                            # Send Discord notification
                            self.notifier.notify_bet_placed(bet_result)
                            print(f"   ✅ Placed bet: {opp.get('home_team')} vs {opp.get('away_team')} ({opp.get('roi'):.2f}% ROI)")
            
            self.last_scan = datetime.now()
            
        except Exception as e:
            print(f"   ❌ Scan error: {e}")
            results['error'] = str(e)
        
        return results
    
    def _run_loop(self):
        """Background scanning loop with smart scheduling"""
        print(f"\n🚀 Auto Scanner started!")
        print(f"   ⏰ Peak hours: {self.peak_start}:00 - {self.peak_end}:00")
        print(f"   ⏱️ Scan interval: {self.peak_interval // 60} minutes")
        print(f"   💰 Min ROI: {self.min_roi}% | Max Investment: €{self.max_investment}")
        print(f"   💬 Discord: {'Connected' if self.notifier.webhook_url else 'Not configured'}\n")
        
        while self.running:
            # Check if in peak hours
            if self.is_peak_hours():
                self.scan_once()
                wait_time = self.peak_interval
                self.next_scan = datetime.now().timestamp() + wait_time
                print(f"   ⏰ Next scan in {wait_time // 60} minutes")
            else:
                if self.skip_off_peak:
                    # Wait until peak hours
                    wait_time = self.get_time_until_peak()
                    hours = wait_time // 3600
                    mins = (wait_time % 3600) // 60
                    print(f"\n💤 Off-peak hours. Sleeping until {self.peak_start}:00 ({hours}h {mins}m)")
                    self.next_scan = datetime.now().timestamp() + wait_time
                else:
                    # Scan less frequently off-peak
                    self.scan_once()
                    wait_time = self.off_peak_interval
                    self.next_scan = datetime.now().timestamp() + wait_time
            
            # Wait with periodic checks (allows clean shutdown)
            for _ in range(wait_time):
                if not self.running:
                    break
                time.sleep(1)
        
        print("\n⏹️ Auto Scanner stopped")
    
    def start(self):
        """Start background scanning"""
        if self.running:
            return {"success": False, "message": "Already running"}
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        return {"success": True, "message": f"Auto scanner started (peak hours: {self.peak_start}:00-{self.peak_end}:00)"}
    
    def stop(self):
        """Stop background scanning"""
        self.running = False
        return {"success": True, "message": "Auto scanner stopping..."}
    
    def get_status(self) -> dict:
        """Get scanner status"""
        return {
            'running': self.running,
            'is_peak_hours': self.is_peak_hours(),
            'peak_hours': f"{self.peak_start}:00 - {self.peak_end}:00",
            'scan_interval_minutes': self.peak_interval // 60,
            'min_roi': self.min_roi,
            'max_investment': self.max_investment,
            'auto_bet': self.auto_bet,
            'discord_configured': bool(self.notifier.webhook_url),
            'last_scan': self.last_scan.isoformat() if self.last_scan else None,
            'next_scan': datetime.fromtimestamp(self.next_scan).isoformat() if self.next_scan else None,
            'stats': self.stats
        }


# Global scanner instance
scanner = AutoScanner()


def start_scanner():
    """Start the auto scanner"""
    return scanner.start()


def stop_scanner():
    """Stop the auto scanner"""
    return scanner.stop()


def get_status():
    """Get scanner status"""
    return scanner.get_status()


def configure(**kwargs):
    """Configure scanner"""
    scanner.configure(**kwargs)
    return get_status()


def set_discord_webhook(url: str):
    """Set Discord webhook URL"""
    scanner.notifier.set_webhook(url)
    return {"success": True, "message": "Discord webhook configured"}


def test_discord():
    """Test Discord notification"""
    return scanner.notifier.send(
        title="🔔 Test Notification",
        description="BETGO Discord notifications are working!",
        color=0x9B59B6,
        fields=[
            {"name": "Status", "value": "Connected ✅", "inline": True},
            {"name": "Time", "value": datetime.now().strftime("%H:%M:%S"), "inline": True}
        ]
    )


if __name__ == "__main__":
    # Test run
    print("BETGO Auto Scanner")
    print("==================")
    
    # Check if Discord is configured
    if not scanner.notifier.webhook_url:
        print("\n⚠️ Discord not configured!")
        print("Set webhook with: auto_scanner.set_discord_webhook('YOUR_WEBHOOK_URL')")
    
    # Run single scan
    scanner.scan_once()
