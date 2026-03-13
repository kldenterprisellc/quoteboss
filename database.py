import os
import json

# Database configuration
# If DATABASE_URL is set (Postgres), uses psycopg2
# Otherwise falls back to SQLite at DB_PATH
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    def get_db():
        conn = psycopg2.connect(DATABASE_URL)
        return conn

    def _placeholder():
        return '%s'

    def _returning():
        return 'RETURNING id'

    USE_POSTGRES = True
else:
    import sqlite3
    DB_PATH = os.environ.get('DB_PATH', '/data/quoteboss.db')

    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _placeholder():
        return '?'

    def _returning():
        return ''

    USE_POSTGRES = False


def init_db():
    conn = get_db()
    c = conn.cursor()

    if USE_POSTGRES:
        c.execute('''CREATE TABLE IF NOT EXISTS contractors (
            id SERIAL PRIMARY KEY,
            whop_user_id TEXT UNIQUE NOT NULL,
            stripe_account_id TEXT,
            stripe_onboarding_complete INTEGER DEFAULT 0,
            zelle_handle TEXT,
            fee_mode TEXT DEFAULT 'pass_to_client',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS quotes (
            id SERIAL PRIMARY KEY,
            quote_id TEXT UNIQUE NOT NULL,
            whop_user_id TEXT,
            quote_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS contractors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            whop_user_id TEXT UNIQUE NOT NULL,
            stripe_account_id TEXT,
            stripe_onboarding_complete INTEGER DEFAULT 0,
            zelle_handle TEXT,
            fee_mode TEXT DEFAULT 'pass_to_client',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id TEXT UNIQUE NOT NULL,
            whop_user_id TEXT,
            quote_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

    conn.commit()
    conn.close()


def get_contractor(whop_user_id):
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    c.execute(f'SELECT * FROM contractors WHERE whop_user_id = {p}', (whop_user_id,))
    row = c.fetchone()
    conn.close()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [desc[0] for desc in c.description]
        return dict(zip(cols, row))
    return dict(row)


def upsert_contractor(whop_user_id, **kwargs):
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'

    c.execute(f'SELECT id FROM contractors WHERE whop_user_id = {p}', (whop_user_id,))
    existing = c.fetchone()

    if existing:
        fields = ', '.join([f'{k} = {p}' for k in kwargs])
        values = list(kwargs.values()) + [whop_user_id]
        c.execute(f'UPDATE contractors SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE whop_user_id = {p}', values)
    else:
        kwargs['whop_user_id'] = whop_user_id
        fields = ', '.join(kwargs.keys())
        placeholders = ', '.join([p for _ in kwargs])
        c.execute(f'INSERT INTO contractors ({fields}) VALUES ({placeholders})', list(kwargs.values()))

    conn.commit()
    conn.close()


def save_quote(quote_id, whop_user_id, quote_data_json):
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    if USE_POSTGRES:
        c.execute(
            f'INSERT INTO quotes (quote_id, whop_user_id, quote_data) VALUES ({p},{p},{p}) ON CONFLICT (quote_id) DO UPDATE SET quote_data = EXCLUDED.quote_data',
            (quote_id, whop_user_id, quote_data_json)
        )
    else:
        c.execute(
            'INSERT OR REPLACE INTO quotes (quote_id, whop_user_id, quote_data) VALUES (?, ?, ?)',
            (quote_id, whop_user_id, quote_data_json)
        )
    conn.commit()
    conn.close()


def get_quote(quote_id):
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    c.execute(f'SELECT * FROM quotes WHERE quote_id = {p}', (quote_id,))
    row = c.fetchone()
    conn.close()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [desc[0] for desc in c.description]
        return dict(zip(cols, row))
    return dict(row)


def init_feedback_table():
    conn = get_db()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute('''CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY,
            whop_user_id TEXT,
            rating INTEGER,
            category TEXT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            whop_user_id TEXT,
            rating INTEGER,
            category TEXT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
    conn.commit()
    conn.close()


def save_feedback(whop_user_id, rating, category, message):
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    c.execute(f'INSERT INTO feedback (whop_user_id, rating, category, message) VALUES ({p},{p},{p},{p})',
              (whop_user_id, rating, category, message))
    conn.commit()
    conn.close()


def get_all_feedback():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM feedback ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    if not rows:
        return []
    if USE_POSTGRES:
        cols = [desc[0] for desc in c.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]
