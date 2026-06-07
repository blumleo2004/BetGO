import os
from app import app, db
from models import BookmakerAccount

# DB-Tabellen anlegen + Accounts initialisieren falls DB leer
with app.app_context():
    db.create_all()
    if BookmakerAccount.query.count() == 0:
        import setup_accounts
        setup_accounts.run()

# Auto-Scanner starten
if os.environ.get('AUTO_START_SCANNER', '').lower() == 'true':
    import auto_scanner
    auto_scanner.scanner.configure(skip_off_peak=False)
    auto_scanner.scanner.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
