# BetGO

Automated betting bot and dashboard.

## Setup on a New Device

### Prerequisites
- Python 3.8+
- Git

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/blumleo2004/BetGO.git
   cd BetGO
   ```

2. **Create and activate a virtual environment:**
   
   *Windows:*
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
   
   *macOS/Linux:*
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration:**
   - Copy `.env.example` to `.env` (if it exists) or ensure you have your API keys set up.
   - You may need to configure `api_keys.json` if used.

### Running the Application

Start the Flask application:
```bash
python app.py
```

Access the dashboard at `http://localhost:5000`.
