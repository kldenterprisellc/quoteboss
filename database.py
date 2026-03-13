import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH', '/tmp/quoteboss.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # Contractor profiles
    c.execute('''CREATE TABLE IF NOT EXISTS contractors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        whop_user_id TEXT UNIQUE NOT NULL,
        stripe_account_id TEXT,
        zelle_handle TEXT,
        fee_mode TEXT DEFAULT 'pass_to_client',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Persistent quotes
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
    row = c.execute('SELECT * FROM contractors WHERE whop_user_id = ?', (whop_user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_contractor(whop_user_id, **kwargs):
    conn = get_db()
    c = conn.cursor()
    existing = c.execute('SELECT id FROM contractors WHERE whop_user_id = ?', (whop_user_id,)).fetchone()
    if existing:
        fields = ', '.join([f'{k} = ?' for k in kwargs])
        values = list(kwargs.values()) + [whop_user_id]
        c.execute(f'UPDATE contractors SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE whop_user_id = ?', values)
    else:
        kwargs['whop_user_id'] = whop_user_id
        fields = ', '.join(kwargs.keys())
        placeholders = ', '.join(['?' for _ in kwargs])
        c.execute(f'INSERT INTO contractors ({fields}) VALUES ({placeholders})', list(kwargs.values()))
    conn.commit()
    conn.close()


def save_quote(quote_id, whop_user_id, quote_data_json):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO quotes (quote_id, whop_user_id, quote_data) VALUES (?, ?, ?)',
              (quote_id, whop_user_id, quote_data_json))
    conn.commit()
    conn.close()


def get_quote(quote_id):
    conn = get_db()
    c = conn.cursor()
    row = c.execute('SELECT * FROM quotes WHERE quote_id = ?', (quote_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
