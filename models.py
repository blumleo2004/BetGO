from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    profile_pic = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    accounts = db.relationship('BookmakerAccount', backref='user', lazy=True)


class BookmakerAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user_label = db.Column(db.String(100))          # e.g. "Mein Bet365"
    bookmaker = db.Column(db.String(50), nullable=False)  # API key, e.g. 'bet365'
    username = db.Column(db.String(100), default='')
    encrypted_password = db.Column(db.String(255), default='')

    # Account status
    status = db.Column(db.String(20), default='new')  # new, active, restricted, gubbed, dormant
    is_active = db.Column(db.Boolean, default=True)   # kept for backwards compat

    # Financials
    current_balance = db.Column(db.Float, default=0.0)
    deposit_total = db.Column(db.Float, default=0.0)
    withdrawal_total = db.Column(db.Float, default=0.0)

    # Bet tracking
    bets_placed_total = db.Column(db.Integer, default=0)
    stake_total = db.Column(db.Float, default=0.0)
    daily_bet_count = db.Column(db.Integer, default=0)
    weekly_bet_count = db.Column(db.Integer, default=0)

    # Limits (configurable per account)
    max_daily_bets = db.Column(db.Integer, default=5)
    max_weekly_bets = db.Column(db.Integer, default=20)
    min_stake = db.Column(db.Float, default=5.0)
    max_stake = db.Column(db.Float, default=100.0)

    last_verified = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Bonus tracking (supports multiple bonuses via JSON list)
    bonus_balance = db.Column(db.Float, default=0.0)          # aktuelles Bonus-Guthaben gesamt
    bonus_wagering_req = db.Column(db.Float, default=0.0)     # Umsatzbedingung (z.B. 5x) — legacy
    bonus_wagered = db.Column(db.Float, default=0.0)          # bereits umgesetzt gesamt
    bonus_target = db.Column(db.Float, default=0.0)           # Gesamtziel (bonus * req) — legacy
    bonus_details_json = db.Column(db.Text, default='[]')     # JSON: [{amount, target, wagered, min_odds, expires_at, label}]
    deposit_pending = db.Column(db.Float, default=0.0)        # noch nicht verfügbare Einzahlung

    # Relationships
    activity = db.relationship('AccountActivity', backref='account', lazy=True,
                                cascade='all, delete-orphan')
    legs = db.relationship('ArbitrageLeg', backref='account', lazy=True)


class AccountActivity(db.Model):
    """Append-only event log for each account."""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('bookmaker_account.id'), nullable=False)
    # Types: bet_placed, balance_updated, status_changed, mug_bet, verified
    activity_type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ArbitrageRecord(db.Model):
    """One arb opportunity that was (simulated or real) placed."""
    id = db.Column(db.Integer, primary_key=True)
    placed_at = db.Column(db.DateTime, default=datetime.utcnow)
    # pending, settled, voided, cancelled
    status = db.Column(db.String(20), default='pending')

    sport_key = db.Column(db.String(50))
    sport_title = db.Column(db.String(100))
    home_team = db.Column(db.String(100))
    away_team = db.Column(db.String(100))
    commence_time = db.Column(db.String(50))
    market_type = db.Column(db.String(20))
    line = db.Column(db.Float)

    expected_roi = db.Column(db.Float)
    expected_profit = db.Column(db.Float)
    total_stake = db.Column(db.Float)
    actual_return = db.Column(db.Float)
    actual_profit = db.Column(db.Float)
    winning_outcome = db.Column(db.String(100))
    settled_at = db.Column(db.DateTime)

    quality_score = db.Column(db.Float)
    is_mug_bet = db.Column(db.Boolean, default=False)

    legs = db.relationship('ArbitrageLeg', backref='arb_record', lazy=True,
                            cascade='all, delete-orphan')


class ArbitrageLeg(db.Model):
    """One bookmaker leg of an arbitrage bet."""
    id = db.Column(db.Integer, primary_key=True)
    arb_record_id = db.Column(db.Integer, db.ForeignKey('arbitrage_record.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('bookmaker_account.id'), nullable=True)

    outcome = db.Column(db.String(100))
    odds = db.Column(db.Float)
    stake = db.Column(db.Float)           # raw calculated stake
    rounded_stake = db.Column(db.Float)   # after stealth rounding
    bookmaker_key = db.Column(db.String(50))
    bookmaker_name = db.Column(db.String(100))
    potential_return = db.Column(db.Float)
    actual_return = db.Column(db.Float)
    # pending, won, lost
    status = db.Column(db.String(20), default='pending')
    placed_at_offset_seconds = db.Column(db.Integer, default=0)
