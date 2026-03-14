import os
import json
from datetime import datetime

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
        # Add new columns (onboarding fields)
        new_contractor_cols = [
            ('business_name', 'TEXT'),
            ('owner_name', 'TEXT'),
            ('phone', 'TEXT'),
            ('email', 'TEXT'),
            ('city_state', 'TEXT'),
            ('primary_trade', 'TEXT'),
            ('team_size', 'TEXT'),
            ('logo_url', 'TEXT'),
            ('all_trades', 'TEXT'),
        ]
        for col_name, col_type in new_contractor_cols:
            try:
                c.execute(f'ALTER TABLE contractors ADD COLUMN IF NOT EXISTS {col_name} {col_type}')
            except Exception:
                pass

        c.execute('''CREATE TABLE IF NOT EXISTS quotes (
            id SERIAL PRIMARY KEY,
            quote_id TEXT UNIQUE NOT NULL,
            whop_user_id TEXT,
            quote_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # Add accepted columns
        try:
            c.execute('ALTER TABLE quotes ADD COLUMN IF NOT EXISTS accepted BOOLEAN DEFAULT FALSE')
        except Exception:
            pass
        try:
            c.execute('ALTER TABLE quotes ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP')
        except Exception:
            pass

        # Quote views table
        c.execute('''CREATE TABLE IF NOT EXISTS quote_views (
            id SERIAL PRIMARY KEY,
            quote_id TEXT NOT NULL,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT
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
        # Add new columns (onboarding fields)
        new_contractor_cols = [
            ('business_name', 'TEXT'),
            ('owner_name', 'TEXT'),
            ('phone', 'TEXT'),
            ('email', 'TEXT'),
            ('city_state', 'TEXT'),
            ('primary_trade', 'TEXT'),
            ('team_size', 'TEXT'),
            ('logo_url', 'TEXT'),
            ('all_trades', 'TEXT'),
        ]
        for col_name, col_type in new_contractor_cols:
            try:
                c.execute(f'ALTER TABLE contractors ADD COLUMN {col_name} {col_type}')
            except Exception:
                pass

        c.execute('''CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id TEXT UNIQUE NOT NULL,
            whop_user_id TEXT,
            quote_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # Add accepted columns
        for col_name, col_def in [('accepted', 'INTEGER DEFAULT 0'), ('accepted_at', 'TIMESTAMP')]:
            try:
                c.execute(f'ALTER TABLE quotes ADD COLUMN {col_name} {col_def}')
            except Exception:
                pass

        # Quote views table
        c.execute('''CREATE TABLE IF NOT EXISTS quote_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id TEXT NOT NULL,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT
        )''')

    conn.commit()
    conn.close()


def get_contractor(whop_user_id):
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    c.execute(f'SELECT * FROM contractors WHERE whop_user_id = {p}', (whop_user_id,))
    row = c.fetchone()
    if USE_POSTGRES and row is not None:
        cols = [desc[0] for desc in c.description]
    conn.close()
    if row is None:
        return None
    if USE_POSTGRES:
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
    if USE_POSTGRES and row is not None:
        cols = [desc[0] for desc in c.description]
    conn.close()
    if row is None:
        return None
    if USE_POSTGRES:
        return dict(zip(cols, row))
    return dict(row)


def accept_quote(quote_id):
    """Mark a quote as accepted."""
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    now = datetime.utcnow().isoformat()
    if USE_POSTGRES:
        c.execute(
            f'UPDATE quotes SET accepted = TRUE, accepted_at = {p} WHERE quote_id = {p}',
            (now, quote_id)
        )
    else:
        c.execute(
            f'UPDATE quotes SET accepted = 1, accepted_at = {p} WHERE quote_id = {p}',
            (now, quote_id)
        )
    conn.commit()
    conn.close()


def record_quote_view(quote_id, ip_address=None):
    """Record a client view of a quote."""
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    c.execute(
        f'INSERT INTO quote_views (quote_id, ip_address) VALUES ({p}, {p})',
        (quote_id, ip_address)
    )
    conn.commit()
    conn.close()


def get_quote_views(quote_id):
    """Get view count and last viewed timestamp for a single quote."""
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    c.execute(
        f'SELECT COUNT(*) as cnt, MAX(viewed_at) as last_viewed FROM quote_views WHERE quote_id = {p}',
        (quote_id,)
    )
    row = c.fetchone()
    if USE_POSTGRES and row is not None:
        cols = [desc[0] for desc in c.description]
    conn.close()
    if row is None:
        return {'count': 0, 'last_viewed': None}
    r = dict(zip(cols, row)) if USE_POSTGRES else dict(row)
    return {'count': r.get('cnt', 0) or 0, 'last_viewed': r.get('last_viewed')}


def get_quote_views_batch(quote_ids):
    """Get view counts for a list of quote IDs (avoids N+1 queries)."""
    if not quote_ids:
        return {}
    conn = get_db()
    c = conn.cursor()
    p = '%s' if USE_POSTGRES else '?'
    placeholders = ', '.join([p] * len(quote_ids))
    c.execute(
        f'SELECT quote_id, COUNT(*) as cnt, MAX(viewed_at) as last_viewed FROM quote_views WHERE quote_id IN ({placeholders}) GROUP BY quote_id',
        list(quote_ids)
    )
    rows = c.fetchall()
    if USE_POSTGRES:
        cols = [desc[0] for desc in c.description]
    conn.close()
    result = {}
    for row in rows:
        r = dict(zip(cols, row)) if USE_POSTGRES else dict(row)
        result[r['quote_id']] = {'count': r.get('cnt', 0) or 0, 'last_viewed': r.get('last_viewed')}
    return result


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
    if USE_POSTGRES:
        cols = [desc[0] for desc in c.description]
    conn.close()
    if not rows:
        return []
    if USE_POSTGRES:
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]
