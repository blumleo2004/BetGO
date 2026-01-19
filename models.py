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
    
    # Relationships
    accounts = db.relationship('BookmakerAccount', backref='user', lazy=True)

class BookmakerAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bookmaker = db.Column(db.String(50), nullable=False)  # e.g., 'tipico', 'bet365'
    username = db.Column(db.String(100), nullable=False)
    encrypted_password = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_verified = db.Column(db.DateTime)
