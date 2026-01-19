from flask import Blueprint, url_for, redirect, session, flash, render_template, current_app
from authlib.integrations.flask_client import OAuth
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User

auth_bp = Blueprint('auth', __name__)
oauth = OAuth()

def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        access_token_url='https://accounts.google.com/o/oauth2/token',
        access_token_params=None,
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        authorize_params=None,
        api_base_url='https://www.googleapis.com/oauth2/v1/',
        client_kwargs={'scope': 'openid email profile'},
    )

@auth_bp.route('/login')
def login():
    """Render login page"""
    if current_user.is_authenticated:
        return redirect('/')
    return render_template('login.html')

@auth_bp.route('/google-login')
def google_login():
    """Initiate Google OAuth flow"""
    if not current_app.config.get('GOOGLE_CLIENT_ID'):
        flash('Google Login not configured. Check .env', 'error')
        return redirect(url_for('auth.login'))
    google = oauth.create_client('google')
    redirect_uri = url_for('auth.authorize', _external=True)
    return google.authorize_redirect(redirect_uri)
@auth_bp.route('/authorize')
def authorize():
    google = oauth.create_client('google')
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()
    
    # Check if user exists
    user = User.query.filter_by(email=user_info['email']).first()
    if not user:
        user = User(
            email=user_info['email'],
            name=user_info['name'],
            profile_pic=user_info['picture']
        )
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    return redirect('/')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')
