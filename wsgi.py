import os
from app import app, db
from models import BookmakerAccount

with app.app_context():
    db.create_all()
    if BookmakerAccount.query.count() == 0:
        from setup_accounts import LEOS_ACCOUNTS
        from datetime import datetime
        for data in LEOS_ACCOUNTS:
            acc = BookmakerAccount(
                bookmaker=data['bookmaker'],
                user_label=data.get('user_label', ''),
                username=data.get('username', ''),
                status=data.get('status', 'active'),
                current_balance=data.get('current_balance', 0.0),
                deposit_total=data.get('deposit_total', 0.0),
                max_stake=data.get('max_stake', 100.0),
                notes=data.get('notes', ''),
                created_at=datetime.utcnow(),
            )
            db.session.add(acc)
        db.session.commit()
        print(f"[wsgi] Initialized {len(LEOS_ACCOUNTS)} accounts")

if os.environ.get('AUTO_START_SCANNER', '').lower() == 'true':
    import auto_scanner
    auto_scanner.scanner.configure(skip_off_peak=False)
    auto_scanner.scanner.start()
    print("[wsgi] Auto-scanner started")

port = int(os.environ.get('PORT', 5000))
print(f"[wsgi] Starting on port {port}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)
