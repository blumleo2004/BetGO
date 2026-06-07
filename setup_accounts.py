"""
Einmaliges Setup-Skript: Leos 6 österreichische Buchmacher-Konten in die DB eintragen.
Ausführen nach dem ersten Start von app.py (damit DB-Tabellen existieren):

    python app.py &   # oder einmal starten und stoppen
    python setup_accounts.py
"""

from app import app
from models import db, BookmakerAccount
from datetime import datetime

LEOS_ACCOUNTS = [
    {
        'bookmaker':       'admiral',
        'user_label':      'Admiral AT',
        'username':        'smartleoblum@gmail.com',
        'status':          'active',
        'current_balance': 215.0,
        'deposit_total':   215.0,
        'max_stake':       50.0,   # Neues Konto → graduated limit
        'notes':           'Österreichischer Softbook. Kein The-Odds-API-Key — manuell gegen Betfair vergleichen.',
    },
    {
        'bookmaker':       'bwin',
        'user_label':      'bwin',
        'username':        'blumleo@outlook.com',
        'status':          'active',
        'current_balance': 145.0,
        'deposit_total':   145.0,
        'max_stake':       100.0,
        'notes':           'Softbook. Gut für WM-Arbs gegen Betfair.',
    },
    {
        'bookmaker':       'bet365',
        'user_label':      'Bet365',
        'username':        'blumleo3@gmail.com',
        'status':          'active',
        'current_balance': 0.0,
        'max_stake':       100.0,
        'notes':           'Einzahlung ausstehend. Top Softbook für Arbs.',
    },
    {
        'bookmaker':       'betfair_ex_eu',
        'user_label':      'Betfair Exchange',
        'username':        'blumleo3@gmail.com',
        'status':          'active',
        'current_balance': 0.0,
        'max_stake':       200.0,
        'notes':           'Sharp-Referenz. Exchange — kein Limit, nie gebannt. Immer einbeziehen.',
    },
    {
        'bookmaker':       'tipico_de',
        'user_label':      'Tipico AT',
        'username':        'blumleo3@gmail.com',
        'status':          'active',
        'current_balance': 1.0,
        'deposit_total':   1.0,
        'max_stake':       50.0,
        'notes':           'Österreichischer Softbook.',
    },
    {
        'bookmaker':       'betatHome',
        'user_label':      'bet-at-home',
        'username':        'blumleo3@gmail.com',
        'status':          'active',
        'current_balance': 0.0,
        'max_stake':       100.0,
        'notes':           'Einzahlung ausstehend.',
    },
    {
        'bookmaker':       'betway',
        'user_label':      'Betway',
        'username':        '',
        'status':          'new',
        'current_balance': 0.0,
        'max_stake':       50.0,
        'notes':           'Neues Konto. Einzahlung ausstehend.',
    },
    {
        'bookmaker':       'merkur',
        'user_label':      'Merkur Bets',
        'username':        '',
        'status':          'new',
        'current_balance': 0.0,
        'max_stake':       50.0,
        'notes':           'Kein The-Odds-API-Key. Manuell gegen Betfair vergleichen.',
    },
]


def run():
    with app.app_context():
        existing = {a.bookmaker for a in BookmakerAccount.query.all()}
        added = 0
        for data in LEOS_ACCOUNTS:
            if data['bookmaker'] in existing:
                print(f"  SKIP  {data['user_label']} (already exists)")
                continue
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
            added += 1
            print(f"  ADD   {data['user_label']} (€{data.get('current_balance', 0):.0f})")

        db.session.commit()
        total_balance = sum(a.get('current_balance', 0) for a in LEOS_ACCOUNTS)
        print(f"\nFertig. {added} Konten angelegt. Gesamtkapital: €{total_balance:.0f}")
        print("Tipp: Einzahlungen für Bet365, Betfair, bet-at-home noch ausstehend.")


if __name__ == '__main__':
    run()
