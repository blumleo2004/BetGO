"""
BETGO Auto Scanner with Telegram Notifications
Runs in background, scans for arbitrage, auto-places simulation bets, and notifies via Telegram
"""

import time
import json
import hashlib
import requests
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Import our modules
import arb_engine
import simulation
import tournament_filter
import stealth


class TelegramNotifier:
    """Send notifications via Telegram Bot API"""

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self):
        self.bot_token = None
        self.chat_id = None
        self._load_config()

    def _load_config(self):
        import config as _cfg
        self.bot_token = getattr(_cfg, 'TELEGRAM_BOT_TOKEN', None)
        self.chat_id = getattr(_cfg, 'TELEGRAM_CHAT_ID', None)

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.configured:
            print("[Telegram] not configured — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env")
            return False
        try:
            url = self.API_URL.format(token=self.bot_token)
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
            return resp.ok
        except Exception as e:
            print(f"[Telegram] error: {e}")
            return False

    def notify_arb_found(self, opp: dict) -> bool:
        bets = opp.get('bets', [])
        delays = stealth.get_leg_placement_delays(len(bets))

        lines = [
            f"*ARB GEFUNDEN* — {opp.get('roi', 0):.2f}% ROI",
            f"*{opp.get('home_team', '?')} vs {opp.get('away_team', '?')}*",
            "",
        ]
        for i, bet in enumerate(bets):
            rounded = stealth.round_stake_natural(bet.get('stake', 0))
            timing = "sofort" if delays[i] == 0 else f"+{delays[i]}s"
            lines.append(
                f"Leg {i+1}: *{bet.get('bookmaker','?')}* | "
                f"{bet.get('outcome','?')} @ {bet.get('odds',0):.2f} | "
                f"*€{rounded:.0f}* ({timing})"
            )

        lines += ["", f"_BETGO WM 2026_"]
        return self.send("\n".join(lines))

    def notify_scan_summary(self, opportunities_found: int, bets_placed: int) -> bool:
        return self.send(
            f"Scan: *{opportunities_found}* Arbs gefunden, *{bets_placed}* platziert"
        )

    def test(self) -> bool:
        return self.send("*BETGO* Telegram-Verbindung OK!")


class OpportunityDeduplicator:
    """Prevent the same opportunity from triggering multiple Discord pings."""

    def __init__(self, window_hours: int = 2):
        self.window_hours = window_hours
        self._seen: dict = {}  # hash -> datetime

    def _hash(self, opp: dict) -> str:
        key = (
            opp.get('home_team', ''),
            opp.get('away_team', ''),
            opp.get('market', ''),
            tuple(sorted(opp.get('stakes', {}).keys())),
        )
        return hashlib.md5(str(key).encode()).hexdigest()

    def is_new(self, opp: dict) -> bool:
        """Returns True if this opportunity hasn't been seen in the dedup window."""
        h = self._hash(opp)
        cutoff = datetime.now() - timedelta(hours=self.window_hours)
        # Prune old entries
        self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        if h in self._seen:
            return False
        self._seen[h] = datetime.now()
        return True


class AutoScanner:
    """Automatic arbitrage scanner with simulation betting"""

    def __init__(self):
        self.engine = arb_engine.ArbEngine()
        self.notifier = TelegramNotifier()
        self.deduplicator = OpportunityDeduplicator(window_hours=2)
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
        self.min_quality_for_discord = 50  # Only ping Discord for quality_score >= this
        self.thread = None
        self.last_scan = None
        self.next_scan = None
        self.stats = {
            'scans': 0,
            'opportunities_found': 0,
            'bets_placed': 0,
            'total_invested': 0,
            'credits_used': 0,
            'discord_pings': 0,
            'dedup_skipped': 0,
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
        if 'telegram_token' in kwargs:
            self.notifier.bot_token = kwargs['telegram_token']
        if 'telegram_chat_id' in kwargs:
            self.notifier.chat_id = kwargs['telegram_chat_id']
        if 'skip_off_peak' in kwargs:
            self.skip_off_peak = kwargs['skip_off_peak']
        if 'min_quality_for_discord' in kwargs:
            self.min_quality_for_discord = kwargs['min_quality_for_discord']
    
    def scan_once(self) -> dict:
        """Run a single scan"""
        print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] Starting scan...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'opportunities': [],
            'bets_placed': []
        }
        
        try:
            # Run the scan — nur eigene Bookmaker (spart Credits, relevanter)
            import config as _cfg
            opportunities = self.engine.scan_for_arbitrage(
                min_roi=self.min_roi,
                investment=self.max_investment,
                bookmakers=_cfg.MY_BOOKMAKERS,
            )
            results['opportunities'] = opportunities
            self.stats['scans'] += 1
            self.stats['opportunities_found'] += len(opportunities)
            
            print(f"   Found {len(opportunities)} arbitrage opportunities")
            
            # Apply WM 2026 mode if active
            if tournament_filter.is_wm2026_active():
                wm_conf = tournament_filter.get_wm2026_scanner_config()
                effective_min_roi = wm_conf.get('min_roi', self.min_roi)
                print(f"   🏆 WM 2026 mode: {tournament_filter.get_wm2026_phase()}")
            else:
                effective_min_roi = self.min_roi

            # Auto-place simulation bets
            if self.auto_bet and opportunities:
                for opp in opportunities:
                    if opp.get('roi', 0) < effective_min_roi:
                        continue

                    # Apply stealth stake rounding before simulation
                    for bet in opp.get('bets', []):
                        if 'stake' in bet:
                            bet['stake'] = stealth.round_stake_natural(bet['stake'])

                    bet_result = simulation.place_virtual_bet(
                        opp,
                        investment=min(self.max_investment, 100)
                    )

                    if bet_result.get('success'):
                        results['bets_placed'].append(bet_result)
                        self.stats['bets_placed'] += 1
                        self.stats['total_invested'] += bet_result.get('total_investment', 0)

                        # Telegram: only for high-quality new opportunities
                        quality = opp.get('quality_score', 0)
                        if quality >= self.min_quality_for_discord and self.deduplicator.is_new(opp):
                            self.notifier.notify_arb_found(opp)
                            self.stats['discord_pings'] += 1
                            print(f"   ✅ Placed bet: {opp.get('home_team')} vs {opp.get('away_team')} "
                                  f"({opp.get('roi'):.2f}% ROI, quality {quality:.0f})")
                        else:
                            self.stats['dedup_skipped'] += 1
            
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
        print(f"   Telegram: {'Connected' if self.notifier.configured else 'Not configured'}\n")
        
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
    
    def _start_daily_reset_scheduler(self, flask_app):
        """Resets daily bet counters at midnight every day."""
        import account_manager
        def _loop():
            while self.running:
                now = datetime.now()
                # seconds until midnight
                seconds_until_midnight = ((24 - now.hour - 1) * 3600 + (60 - now.minute - 1) * 60 + (60 - now.second))
                time.sleep(seconds_until_midnight + 5)
                try:
                    with flask_app.app_context():
                        account_manager.reset_daily_counters()
                    print('[AutoScanner] Daily counters reset')
                except Exception as e:
                    print(f'[AutoScanner] Daily reset error: {e}')
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

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
            'telegram_configured': self.notifier.configured,
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


def test_telegram():
    """Test Telegram notification"""
    return scanner.notifier.test()


if __name__ == "__main__":
    print("BETGO Auto Scanner")
    print("==================")
    if not scanner.notifier.configured:
        print("Telegram not configured — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env")
    scanner.scan_once()
