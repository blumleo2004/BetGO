# Design: Stealth Improvements, Admiral Scraper, Telegram Buttons
**Date:** 2026-06-08  
**Status:** Approved

## Context
BetGO läuft auf Railway und sendet Telegram-Alerts bei Arb-Chancen. Drei Erweiterungen:
1. Stealth-Verbesserungen damit Wetteinsätze nicht mechanisch wirken
2. Admiral.at-Quoten per interner API scrapen (€215 Kapital ungenutzt)
3. Telegram-Alerts mit direkten Bookmaker-Links als Inline-Buttons

---

## 1. Stealth-Verbesserungen (`stealth.py`)

### Neue Funktionen

**`jitter_stake(stake: float, pct: float = 0.06) -> float`**
- Fügt ±6% zufällige Variation hinzu *vor* `round_stake_natural()`
- Beispiel: €32.47 → zufällig €30.52–€34.42 → gerundet €30 oder €35
- Verhindert dass immer derselbe mathematisch exakte Betrag erscheint
- Wird in `auto_scanner.py` direkt nach Arb-Berechnung aufgerufen

**`mug_bet_due(arb_count_since_last_mug: int, threshold: int = 5) -> bool`**
- Gibt `True` wenn Account ≥5 Arb-Wetten ohne Tarnwette hat
- Pure function, kein DB-Zugriff — Caller übergibt den Zähler

### Scan-Intervall-Jitter (`auto_scanner.py`)
- `peak_interval` wird vor jedem Sleep um ±5 Minuten randomisiert
- Statt exakt alle 30min → 25–35min zufällig
- Verhindert Bot-ähnliches Timing-Muster

### Mug-Bet-Alert
- Nach jedem platzierten Arb: `arb_count` per `bookmaker_key` inkrementieren (in-memory `dict[str, int]` im `AutoScanner`, Reset bei Neustart ist ok)
- Wenn `mug_bet_due()` → separater Telegram-Alert (kein Arb nötig):
  ```
  🎭 [Bookmaker]: Tarnwette fällig!
  Bet auf klaren Favoriten (Odds 1.40–1.70)
  [Bookmaker WM →]
  ```
- Counter wird nach dem Alert zurückgesetzt

---

## 2. Admiral API Scraper (`admiral_scraper.py`)

### API-Discovery
Beim ersten Start werden folgende Kambi-Endpunkt-Muster probiert (Admiral nutzt wahrscheinlich Kambi):
```
https://eu-offering-api.kambicdn.com/offering/v2018/admiral/listView/football.json
https://eu-offering-api.kambicdn.com/offering/v2018/admiralatlet/listView/football.json
https://api.bettingapi.admiral.at/...
```
Der erste funktionierende Endpunkt wird in einer Instanzvariable gecacht.

### Canary-Check
- Nach jedem Fetch: SHA-256-Hash der Response-Keys (nicht Werte) berechnen
- Erster erfolgreicher Fetch → Hash als Baseline speichern (`schema_hash`)
- Spätere Fetches: Hash vergleichen
- Abweichung → Telegram-Alert + Scraper pausiert bis Railway-Neustart:
  ```
  ⚠️ Admiral API Schema geändert — Scraper pausiert
  Bitte admiral_scraper.py prüfen und Railway neu deployen
  ```
- Hash = SHA-256 über rekursiv sortierte JSON-Keys (nicht Werte)

### Arb-Erkennung
- Vergleicht Admiral-Quoten mit aktuell gecachten Betfair-Exchange-Quoten (via `arb_engine.ArbEngine().fetch_odds('betfair_ex_eu', ...)` — nutzt bestehenden Cache, kein Extra-API-Credit)
- Schwellwert: ROI ≥ 0.3% (tiefer als Hauptscanner wegen manueller Ausführung)
- Alert-Format identisch zum Hauptscanner inkl. Inline-Buttons

### Threading
- Eigener Daemon-Thread in `AutoScanner`, startet mit dem Hauptscanner
- Intervall: alle 10 Minuten (unabhängig von Peak-Hours)
- Fehler (Timeout, 404, etc.) → Warnung ins Log, kein Crash

---

## 3. Telegram Inline Buttons (`auto_scanner.py`)

### Bookmaker-URL-Mapping
```python
BOOKMAKER_URLS = {
    'bet365':        'https://www.bet365.com/#/AC/B1/C1/D13/',
    'bwin':          'https://sports.bwin.com/de/sports/fussball-4/wm-2026',
    'betfair_ex_eu': 'https://www.betfair.com/exchange/plus/football/event/{event_id}',
    'tipico_de':     'https://www.tipico.at/de/sportwetten/fussball/wm-2026/',
    'betatHome':     'https://www.bet-at-home.com/de/sport/fussball',
    'betway':        'https://www.betway.com/sports/evt/football',
    'admiral':       'https://www.admiral.at/de/sport/fussball/wm',
    'merkur':        'https://www.merkur.com/sports/',
}
```
Betfair: Event-ID aus Odds-API-Response extrahieren für direkten Match-Link.
Alle anderen: WM-Sektion als Fallback.

### Alert-Format
```
send_message(text, reply_markup={
    "inline_keyboard": [[
        {"text": "Bet365 WM →", "url": "..."},
        {"text": "Betfair Match →", "url": "..."}
    ]]
})
```
Jeder Leg = ein Button in derselben Zeile. Bei >3 Legs: zwei Zeilen.

---

## Dateien

| Datei | Änderung |
|-------|----------|
| `stealth.py` | `jitter_stake()`, `mug_bet_due()` hinzufügen |
| `auto_scanner.py` | Jitter im Sleep, Mug-Bet-Counter, `notify_arb_found()` mit Buttons, Admiral-Thread starten |
| `admiral_scraper.py` | Neu: API-Discovery, Scraper, Canary-Check |
| `config.py` | `BOOKMAKER_URLS` dict hinzufügen |

---

## Nicht im Scope
- Playwright/Selenium (kein Headless-Browser)
- Automatisches Platzieren von echten Wetten
- Persistenter Mug-Bet-Zähler (in-memory reicht, Reset bei Neustart ist ok)
