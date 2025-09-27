# === IMPORT UNICI E CORRETTI ===
import os, csv, smtplib, sqlite3, calendar, base64, json, hmac, hashlib, secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from email.mime.text import MIMEText
from collections import deque
from types import SimpleNamespace
from time import time
from functools import wraps

# Se usi matplotlib altrove, tieni questa riga PRIMA di qualunque "import matplotlib"
os.environ.setdefault("MPLBACKEND", "Agg")

from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import generate_csrf, validate_csrf

from utils.crypto import encrypt_data

OPEN_PATHS = ("/login", "/logout", "/register", "/attiva", "/privacy", "/condizioni", "/heartbeat", "/static/")

MONTH_SLUGS = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"
]

MONTH_LABELS = dict(zip(
    MONTH_SLUGS,
    ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
     "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]
))

MONTH_SET = set(MONTH_SLUGS)

# slug -> numero (1..12)
MONTH_MAP = {slug: i + 1 for i, slug in enumerate(MONTH_SLUGS)}

# numero -> slug
MONTH_NUM_TO_SLUG = {i + 1: slug for i, slug in enumerate(MONTH_SLUGS)}

# alias usato dal PUT/QR
MONTH_SLUG_TO_NUM = MONTH_MAP

def _normalize_amount(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return 0.0
    if isinstance(value, str):
        cleaned = value.replace('EUR', '').replace('€', '').strip()
        if not cleaned:
            return 0.0
        cleaned = cleaned.replace('.', '').replace(',', '.')
        try:
            return round(float(cleaned), 2)
        except (TypeError, ValueError):
            return 0.0
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0

def _format_periodo(mese_slug: str, anno: int) -> str:
    label = MONTH_LABELS.get(mese_slug, (mese_slug or '').strip().capitalize())
    return f"{label} {anno}"

# Helper sostituzione variabili
def _render_vars(testo: str, c: dict) -> str:
    return (testo or "").replace("{{nome}}", (c.get("nome") or "")) \
                        .replace("{{note}}", (c.get("note") or "")) \
                        .replace("{{email}}", (c.get("email") or ""))

# Inizializza Flask + cartella static
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chiave-di-ripiego-non-sicura")
app.config["SECRET_KEY"] = app.secret_key  # allinea per sign/verify_renew_token
# Limita la dimensione massima del body (evita richieste enormi)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB

# 👇 Aggiungi QUI (Primo Passaggio)
app.config["BACKUP_MAX_COUNT"] = int(os.getenv("BACKUP_MAX_COUNT", "15"))     # quanti backup tenere
app.config["BACKUP_MAX_AGE_DAYS"] = int(os.getenv("BACKUP_MAX_AGE_DAYS", "0"))  # 0 = disattivato; es. 90 per 90 giorni

# Cookie di sessione (dev su http => niente Secure)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,   # <— forza OFF in locale
    REMEMBER_COOKIE_SECURE=False,  # <— se usi remember-me
)

# Timeout sessione (auto-logout dopo 8 ore)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

@app.get("/heartbeat")
def heartbeat():
    return jsonify(ok=True, now=datetime.now(timezone.utc).isoformat())


# Sostituisci SOLO il valore del cookie in set_csrf_cookie
@app.after_request
def set_csrf_cookie(resp):
    resp.set_cookie(
        "csrf_token",
        get_csrf(),            # <- prima era generate_csrf()
        httponly=False,
        samesite="Lax",
        secure=app.config.get("SESSION_COOKIE_SECURE", False),
        path="/",
    )
    return resp

# === DB PATH (CANONICO) ===
db_path_env = os.getenv("DB_PATH")
if db_path_env:
    app.config["DB_PATH"] = db_path_env.replace("\\", "/")
else:
    # Solo per sviluppo: fallback al vecchio percorso
    app.config["DB_PATH"] = r"C:\Users\Fio\OneDrive\Desktop\RistoSmartFM_New\ristosmart.db"

# Alias legacy per compatibilità con codice esistente (non toccare altre funzioni)
DB_PATH = app.config['DB_PATH']

# Crea la directory del DB se non esiste (PASSO 4 OBBLIGATORIO)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Log di avvio utile in console
print(f"DB_PATH: {DB_PATH}")

# === PROTEZIONE PAGINE ===
def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if _wants_json():
                return jsonify({"ok": False, "msg": "Login richiesto"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper

def require_license(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Admin bypass
        if (session.get("user_email") or "").strip().lower() == (ADMIN_EMAIL or "").strip().lower():
            return f(*args, **kwargs)

        email = session.get("user_email")
        if not email or not has_active_license(email):
            if _wants_json():
                return jsonify({"ok": False, "msg": "Licenza richiesta"}), 403
            return redirect(url_for("license_page"))
        return f(*args, **kwargs)
    return wrapper


def _wants_json():
    a = (request.headers.get("Accept") or "").lower()
    x = (request.headers.get("X-Requested-With") or "").lower()
    c = (request.headers.get("Content-Type") or "").lower()
    return "application/json" in a or x == "xmlhttprequest" or "application/json" in c

def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if _wants_json():
                return jsonify({"ok": False, "msg": "Login richiesto"}), 401
            return redirect(url_for("login", next=request.path))

        email = (session.get("user_email") or "").strip().lower()
        if email != (ADMIN_EMAIL or "").strip().lower():
            if _wants_json():
                return jsonify({"ok": False, "msg": "Solo admin"}), 403
            return redirect(url_for("home"))

        session["user_role"] = "admin"
        return f(*args, **kwargs)
    return wrapper

def require_csrf(f):
    @wraps(f)
    def wrapper(*a, **kw):
        token = (
            request.headers.get("X-CSRF-Token")
            or request.headers.get("X-CSRFToken")
            or request.form.get("csrf_token")
            or (request.get_json(silent=True) or {}).get("csrf_token")
        )
        cookie = request.cookies.get("csrf_token")
        app.logger.debug(f"[CSRF] hdr={bool(token)} cookie={bool(cookie)} eq={token==cookie} sess={bool(session.get('_csrf'))}")
        if not token or not cookie or token != cookie:
            return jsonify({"ok": False, "msg": "CSRF mancante o non valido"}), 400
        try:
            validate_csrf(token)
        except Exception:
            return jsonify({"ok": False, "msg": "CSRF mancante o non valido"}), 400
        return f(*a, **kw)
    return wrapper

# === SMTP CONFIG (personalizza o usa env) ===

SMTP_HOST = (os.getenv("SMTP_HOST", "smtp.gmail.com") or "").strip()
SMTP_PORT = int((os.getenv("SMTP_PORT", "587") or "587").strip())
SMTP_USER = (os.getenv("SMTP_USER", "tua-email@gmail.com") or "").strip()
SMTP_PASS = (os.getenv("SMTP_PASS", "LA_TUA_PASSWORD_APP") or "").strip()

# ❗ Admin fisso: usa SEMPRE questa email
ADMIN_EMAIL = "ristoconsulenze@gmail.com"

@app.before_request
def _capture_selected_year_from_route():
    # Se la route ha un parametro 'anno' o arriva come querystring, salvalo in sessione
    va = (getattr(request, "view_args", None) or {})
    y = va.get("anno") or request.args.get("anno", type=int)
    if y:
        _set_selected_year(y)

@app.before_request
def _ensure_admin_role():
    # Se l'email in sessione è l'admin, forza il ruolo ad 'admin'
    admin_email = ADMIN_EMAIL.strip().lower()  # niente fallback, usiamo la costante sopra
    if session.get("user_email", "").lower() == admin_email:
        if session.get("user_role") != "admin":
            session["user_role"] = "admin"

@app.before_request
def _refresh_license_expiry_in_session():
    """Aggiorna ad ogni richiesta la scadenza licenza in sessione leggendo dal DB."""
    uid = session.get("user_id")
    if not uid:
        # utente non loggato → evita mostrare dati stantii
        session.pop("license_expiry", None)
        return

    db_exp = _get_license_expiry_from_db(uid)  # usa l'helper già definito
    if db_exp:
        iso = db_exp.isoformat()
        if session.get("license_expiry") != iso:
            session["license_expiry"] = iso
    else:
        # nessuna licenza valida trovata → rimuovi valore vecchio
        session.pop("license_expiry", None)

@app.before_request
def log_csrf_status():
    if request.endpoint and 'api' in request.endpoint:
        print(f"[DEBUG] CSRF Token presente: {bool(session.get('_csrf'))}")
        print(f"[DEBUG] User logged in: {session.get('user_id')}")

def send_emails(recipients, subject, body, from_name="RistoSmart FM"):
    import ssl, re, smtplib
    from email.mime.text import MIMEText

    results = []
    if not recipients:
        return results

    # Sanifica host (niente http/https/smtp://) e porta
    host = (SMTP_HOST or "").strip()
    host = re.sub(r"^\s*(?:smtp://|smtps://|https?://)", "", host, flags=re.I)
    port = 587  # forziamo STARTTLS standard

    # DEBUG utile: vedrai questi in console
    print(f"[SMTP DEBUG] host={host!r} port={port} user={SMTP_USER!r} pass_len={len(SMTP_PASS or '')}")

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.login((SMTP_USER or "").strip(), (SMTP_PASS or "").strip())

        for r in recipients:
            to_email = (r.get("email") or "").strip()
            if not to_email:
                results.append({"email": "", "ok": False, "err": "no email"})
                continue
            subtype = "html" if ("<html" in (body or "").lower() or "<!doctype" in (body or "").lower()) else "plain"
            msg = MIMEText(body, subtype, "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"{from_name} <{(SMTP_USER or '').strip()}>"
            msg["To"] = to_email
            try:
                smtp.sendmail((SMTP_USER or "").strip(), [to_email], msg.as_string())
                results.append({"email": to_email, "ok": True})
            except Exception as e:
                results.append({"email": to_email, "ok": False, "err": str(e)})

    return results  # ✅ AGGIUNTO

def send_emails_personalized(items, from_name="RistoSmart FM"):
    """
    items: lista di dict con chiavi:
      - email  (destinatario)
      - subject
      - body
    Invia aprendo UNA sola sessione SMTP.
    Ritorna: [{"email":..., "ok": True/False, "err": "..."}]
    """
    import ssl, re, smtplib
    from email.mime.text import MIMEText

    results = []
    if not items:
        return results

    host = (SMTP_HOST or "").strip()
    host = re.sub(r"^\s*(?:smtp://|smtps://|https?://)", "", host, flags=re.I)
    port = 587  # STARTTLS

    print(f"[SMTP DEBUG] host={host!r} port={port} user={SMTP_USER!r} pass_len={len(SMTP_PASS or '')}")

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.login((SMTP_USER or "").strip(), (SMTP_PASS or "").strip())

        for it in items:
            to_email = (it.get("email") or "").strip()
            subject  = it.get("subject") or ""
            body     = it.get("body") or ""
            if not to_email:
                results.append({"email": "", "ok": False, "err": "no email"})
                continue

            subtype = "html" if ("<html" in (body or "").lower() or "<!doctype" in (body or "").lower()) else "plain"
            msg = MIMEText(body, subtype, "utf-8")
            msg["Subject"] = subject
            msg["From"]    = f"{from_name} <{(SMTP_USER or '').strip()}>"
            msg["To"]      = to_email

            try:
                smtp.sendmail((SMTP_USER or "").strip(), [to_email], msg.as_string())
                results.append({"email": to_email, "ok": True})
            except Exception as e:
                results.append({"email": to_email, "ok": False, "err": str(e)})

    return results

# --- Wrapper semplice per compatibilità con vecchie chiamate ---
def invia_email(to: str, oggetto: str, corpo: str):
    """Invio best-effort di una singola email (HTML o testo).
       Non solleva eccezioni: logga l'errore e continua.
    """
    try:
        items = [{
            "email": (to or "").strip(),
            "subject": oggetto or "",
            "body": corpo or ""
        }]
        send_emails_personalized(items)
    except Exception as e:
        print("[MAIL WARN]", e)


# === CONFIGURAZIONE DB ===
BASE_DIR = Path(__file__).resolve().parent

# === LOG CSV ===
LOG_DIR = Path(r"C:\RISTO\BACKUP")
LOG_DIR.mkdir(exist_ok=True)
LOG_EMAIL_CSV = LOG_DIR / "log_email.csv"
LOG_WA_CSV    = LOG_DIR / "log_whatsapp.csv"

def _log_rows(csv_path, fieldnames, rows):
    if not rows:
        return
    write_header = not Path(csv_path).exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

@app.get("/logs/email.csv")
@require_admin
def download_log_email():
    if LOG_EMAIL_CSV.exists():
        return send_file(LOG_EMAIL_CSV, as_attachment=True, download_name="log_email.csv")
    return jsonify({"ok": False, "msg": "Nessun log email"}), 404

@app.get("/logs/whatsapp.csv")
@require_admin
def download_log_wa():
    if LOG_WA_CSV.exists():
        return send_file(LOG_WA_CSV, as_attachment=True, download_name="log_whatsapp.csv")
    return jsonify({"ok": False, "msg": "Nessun log WhatsApp"}), 404


def get_db():
    # Garantisce cartella esistente e connessione solida
    db_path = app.config["DB_PATH"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row

    # Stabilità e integrità (PRAGMA sono per-connessione)
    conn.execute("PRAGMA foreign_keys = ON")   # valida FK su ogni query
    conn.execute("PRAGMA journal_mode = WAL")  # letture non bloccano scritture
    conn.execute("PRAGMA synchronous = NORMAL")# bilancia durabilità/velocità in WAL
    conn.execute("PRAGMA busy_timeout = 5000") # attende lock fino a 5s

    return conn

def init_db():
    """Crea le tabelle se non esistono già (versione multi-tenant)"""
    with get_db() as conn:
        cur = conn.cursor()

        # --- INCASSI (multi-tenant) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS incassi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                anno INTEGER NOT NULL,
                mese TEXT NOT NULL,
                giorno INTEGER NOT NULL,
                valore REAL NOT NULL DEFAULT 0
            )
        """)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_incassi_user ON incassi(user_id, anno, mese, giorno)")

        # --- SPESE FISSE (multi-tenant) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS spese_fisse (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                anno INTEGER NOT NULL,
                mese TEXT NOT NULL,
                categoria TEXT NOT NULL,
                valore REAL NOT NULL DEFAULT 0
            )
        """)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_spese_fisse_user ON spese_fisse(user_id, anno, mese, categoria)")

        # --- SPESE FATTURE (multi-tenant) --- (SPOSTATA QUI)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS spese_fatture (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                anno INTEGER NOT NULL,
                mese TEXT NOT NULL,
                categoria TEXT NOT NULL,
                valore REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES utenti (id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_spese_fatture_user_anno_mese ON spese_fatture(user_id, anno, mese)")

        # --- CLIENTI (multi-tenant) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clienti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                telefono TEXT,
                email TEXT,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clienti_user ON clienti(user_id)")

        # --- PERSONALE (multi-tenant) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS personale (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                ruolo TEXT,
                data_assunzione TEXT,
                rapporto TEXT,
                data_fine TEXT,
                telefono TEXT,
                email TEXT,
                iban TEXT,
                riposo TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES utenti (id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_personale_user ON personale(user_id)")

        # --- STIPENDI PERSONALE (mensilita dipendente) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stipendi_personale (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                personale_id INTEGER NOT NULL,
                anno INTEGER NOT NULL,
                mese TEXT NOT NULL,
                lordo REAL NOT NULL DEFAULT 0,
                netto REAL NOT NULL DEFAULT 0,
                contributi REAL NOT NULL DEFAULT 0,
                totale REAL NOT NULL DEFAULT 0,
                stato_pagamento TEXT NOT NULL DEFAULT 'non_pagato',
                UNIQUE(user_id, personale_id, anno, mese),
                FOREIGN KEY (user_id) REFERENCES utenti (id) ON DELETE CASCADE,
                FOREIGN KEY (personale_id) REFERENCES personale (id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_stipendi_personale_key ON stipendi_personale(user_id, personale_id, anno, mese)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stipendi_personale_user ON stipendi_personale(user_id)")
        cur.execute("PRAGMA table_info(stipendi_personale)")
        cols = {row[1] for row in cur.fetchall()}
        if 'lordo' not in cols:
            cur.execute("ALTER TABLE stipendi_personale ADD COLUMN lordo REAL NOT NULL DEFAULT 0")
        if 'netto' not in cols:
            cur.execute("ALTER TABLE stipendi_personale ADD COLUMN netto REAL NOT NULL DEFAULT 0")
        if 'contributi' not in cols:
            cur.execute("ALTER TABLE stipendi_personale ADD COLUMN contributi REAL NOT NULL DEFAULT 0")
        if 'totale' not in cols:
            cur.execute("ALTER TABLE stipendi_personale ADD COLUMN totale REAL NOT NULL DEFAULT 0")
        if 'stato_pagamento' not in cols:
            cur.execute("ALTER TABLE stipendi_personale ADD COLUMN stato_pagamento TEXT NOT NULL DEFAULT 'non_pagato'")

        # --- FORNITORI (multi-tenant) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fornitori (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nomeFornitore TEXT NOT NULL,
                nomeAgente TEXT,
                categoria TEXT,
                telAgente TEXT,
                telAzienda TEXT,
                indirizzo TEXT,
                iban TEXT,

                bic TEXT,

                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fornitori_user ON fornitori(user_id)")

        cur.execute("PRAGMA table_info(fornitori)")

        fornitori_cols = {row[1] for row in cur.fetchall()}

        if 'bic' not in fornitori_cols:

            cur.execute("ALTER TABLE fornitori ADD COLUMN bic TEXT")


        # --- PROFILI BANCARI (multi-tenant) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS profili_bancari (
                user_id INTEGER PRIMARY KEY,
                nome_titolare TEXT NOT NULL,
                indirizzo_titolare TEXT NOT NULL,
                iban_cipher TEXT NOT NULL,
                bic_cipher TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES utenti (id) ON DELETE CASCADE
            )
        """)

        # --- FATTURE (multi-tenant) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fatture (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                data_inserimento TEXT NOT NULL,
                fornitore TEXT NOT NULL,
                categoria TEXT NOT NULL,
                data_scadenza TEXT NOT NULL,
                importo REAL NOT NULL,
                stato TEXT NOT NULL DEFAULT 'Non pagato',
                numero TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES utenti (id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fatture_user ON fatture(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fatture_scadenza ON fatture(data_scadenza)")

        # --- UTENTI ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utenti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cognome TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                newsletter_opt_in INTEGER NOT NULL DEFAULT 0,
                ruolo TEXT NOT NULL DEFAULT 'user',
                registered_at TEXT NOT NULL DEFAULT (datetime('now')),
                promo_last_sent TEXT
            )
        """)

        # --- LICENZE ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS licenze (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                license_key TEXT NOT NULL UNIQUE,
                intestatario TEXT,
                scadenza TEXT,
                attiva INTEGER NOT NULL DEFAULT 0,
                meta TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_licenze_email ON licenze(email)")

        # NON chiamare conn.commit() - il context manager lo fa automaticamente
        # NON chiamare conn.close() - il context manager lo fa automaticamente

# Inizializza DB all'avvio
init_db()

def get_csrf():
    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_hex(32)
        session["_csrf"] = tok
    return tok

def validate_csrf(token: str) -> bool:
    return bool(token) and hmac.compare_digest(token, session.get("_csrf", ""))

# === VARIABILI GLOBALI ===
@app.context_processor
def inject_globals():
    from datetime import datetime, timedelta
    return {
        "anno_corrente": datetime.now().year,
        "selected_year": _get_selected_year(),  # 👈 aggiungi questo
        "datetime": datetime,
        "timedelta": timedelta,
        "csrf_token": get_csrf(),
    }

# === Banner utente (email + licenza) ===
from datetime import date, datetime, timedelta

_MESE_IT = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
            "luglio","agosto","settembre","ottobre","novembre","dicembre"]

def _parse_iso_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").date()
        except Exception:
            return None

def _fmt_data_it(d: date | None):
    if not d: 
        return None
    return f"{d.day} {_MESE_IT[d.month-1]} {d.year}"

def _coerce_to_date(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v)
    d = _parse_iso_date(s)
    if d:
        return d
    # dd/mm/YYYY
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except Exception:
        return None

def _current_license_expiry():
    # Chiavi dirette comuni
    for k in (
        "license_expiry", "license_expires_at", "license_expiry_date",
        "license_valid_to", "license_valid_until",
        "licenza_scadenza", "scadenza_licenza", "scadenza",
        "expires_at", "expires", "valid_to"
    ):
        d = _coerce_to_date(session.get(k))
        if d:
            return d

# === Fallback: carica scadenza licenza dal DB se manca in sessione ===
import sqlite3
import json

def _get_license_expiry_from_db(user_id: int | str):
    try:
        conn = sqlite3.connect(app.config['DB_PATH'])
        cur = conn.cursor()

        # Trova tabella licenze: 'licenses' o 'licenze'
        for table in ("licenses", "licenze"):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if not cur.fetchone():
                continue

            # Colonne disponibili
            cur.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in cur.fetchall()]
            if not cols:
                continue

            expiry_candidates = [c for c in cols if c in ("expires_at","expiry","valid_to","scadenza","scadenza_licenza")]
            user_candidates   = [c for c in cols if c in ("user_id","utente_id","email")]
            if not expiry_candidates or not user_candidates:
                continue

            expiry_col = expiry_candidates[0]

            # Colonna utente: preferisci id; fallback email
            if "user_id" in user_candidates:
                ucol, uval = "user_id", user_id
            elif "utente_id" in user_candidates:
                ucol, uval = "utente_id", user_id
            elif "email" in user_candidates:
                ucol = "email"
                uval = session.get("email") or session.get("user_email") or session.get("utente_email")
                if not uval:
                    continue
            else:
                continue

            cur.execute(f"SELECT {expiry_col} FROM {table} WHERE {ucol}=? ORDER BY {expiry_col} DESC LIMIT 1", (uval,))
            row = cur.fetchone()
            if row and row[0]:
                return _coerce_to_date(row[0])
    except Exception as e:
        app.logger.warning(f"license lookup failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return None

@app.before_request
def _ensure_license_in_session():
    # Popola sessione solo se loggato e manca la scadenza
    if session.get("user_id") and not _current_license_expiry():
        d = _get_license_expiry_from_db(session.get("user_id"))
        if d:
            session["license_expiry"] = d.isoformat()


    # Oggetto licenza annidato (dict o JSON string)
    lic = session.get("license") or session.get("licenza")
    if lic:
        if isinstance(lic, str):
            try:
                lic = json.loads(lic)
            except Exception:
                lic = None
        if isinstance(lic, dict):
            for k in ("expiry", "expires", "expires_at", "valid_to", "scadenza"):
                d = _coerce_to_date(lic.get(k))
                if d:
                    return d

    # Pattern "giorni residui"
    days_left = session.get("license_days_left")
    if isinstance(days_left, int) and days_left >= 0:
        return date.today() + timedelta(days=days_left)

    # UNIX timestamp
    ts = session.get("license_expiry_ts")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts)).date()
        except Exception:
            pass

    return None

@app.context_processor
def inject_user_banner():
    email = session.get("email") or session.get("user_email") or session.get("utente_email")
    exp = _current_license_expiry()
    today = date.today()
    msg = None
    if exp:
        if exp >= today:
            giorni = (exp - today).days
            msg = f"La tua licenza scade tra {giorni} giorni (scadenza: {_fmt_data_it(exp)})"
        else:
            giorni = (today - exp).days
            msg = f"Licenza scaduta da {giorni} giorni (scadenza: {_fmt_data_it(exp)})"
    return {"banner_email": email, "banner_licenza_msg": msg}

# === HOME ===
@app.route("/home")
@app.route("/")
@app.route("/home/<int:anno>")
@require_login
@require_license
def home(anno=None):    
    current_year = datetime.now().year

    # Se non viene passato, usa quello in sessione (o anno corrente)
    if anno is None:
        anno = _get_selected_year()

    # Memorizza sempre l’ultimo anno visitato
    _set_selected_year(anno)

    mesi = [
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"
    ]
    mese_corrente = mesi[datetime.now().month - 1]

    return render_template(
        "home.html",
        anno=anno,
        mesi=mesi,
        mese_corrente=mese_corrente,
        current_year=current_year
    )

# --- LOGOUT (GET = conferma, POST = esegue) ---
@app.get("/logout")
@require_login
def logout_confirm():
    # mostra la pagina con il form di conferma
    return render_template("logout_confirm.html")

@app.post("/logout")
@require_login
@require_csrf
def logout_post():
    session.clear()
    return redirect(url_for("login"))

# === PAGINA MESE ===
@app.route("/mese/<int:anno>/<mese>")
@require_login
@require_license
def mese_html(anno, mese):
    mesi = [
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"
    ]
    mese_norm, mese_num = _normalize_mese(mese)
    if not mese_num:
        return f"Mese '{mese}' non valido.", 404

    _set_selected_year(anno)   # <<< INSERITA QUI

    giorni_nel_mese = calendar.monthrange(anno, mese_num)[1]

    uid = _uid()
    conn = get_db()
    cur = conn.cursor()
    
        # --- Incassi ---
    cur.execute(
        "SELECT giorno, valore FROM incassi "
        "WHERE user_id=? AND anno=? "
        "AND LOWER(TRIM(mese)) IN (LOWER(TRIM(?)), LOWER(TRIM(?)), LOWER(TRIM(?))) "
        "ORDER BY giorno",
        (uid, anno, mese_norm, str(mese_num), f"{mese_num:02d}")
    )
    incassi = {int(r["giorno"]): float(r["valore"]) for r in cur.fetchall()}
    tot_incassi = sum(incassi.values())

    # --- Spese ---
    cur.execute(
        "SELECT categoria, valore FROM spese_fisse "
        "WHERE user_id=? AND anno=? "
        "AND LOWER(TRIM(mese)) IN (LOWER(TRIM(?)), LOWER(TRIM(?)), LOWER(TRIM(?)))",
        (uid, anno, mese_norm, str(mese_num), f"{mese_num:02d}")
    )
    spese = {r["categoria"]: float(r["valore"]) for r in cur.fetchall()}
    tot_spese = sum(spese.values())

    conn.close()

    ricavo = tot_incassi - tot_spese

    return render_template(
        "mese.html",
        anno=anno,
        mese=mese_norm.capitalize(),
        giorni=giorni_nel_mese,
        incassi=incassi,
        spese=spese,
        tot_incassi=tot_incassi,
        tot_spese=tot_spese,
        ricavo=ricavo
    )

@app.get("/whoami")
@require_login
@require_admin
def whoami():
    # Abilitata solo in debug
    if not app.debug:
        return jsonify({"error": "Route non disponibile"}), 404

    return jsonify({
        "email": session.get("user_email"),
        "role": session.get("user_role"),
        "logged_at": session.get("logged_at")
    })

# === HELPER: utenti/licenze ===
def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()

def hash_password(plain: str) -> str:
    return generate_password_hash(plain or "")

def verify_password(pw_hash: str, plain: str) -> bool:
    try:
        return check_password_hash(pw_hash or "", plain or "")
    except Exception:
        return False

def _fetchone_dict(cur):
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))

def get_user_by_email(email: str):
    email = _normalize_email(email)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nome, cognome, email, password_hash, newsletter_opt_in, ruolo, registered_at, promo_last_sent
        FROM utenti WHERE email = ?
    """, (email,))
    data = _fetchone_dict(cur)
    conn.close()
    return data

def create_user(nome: str, cognome: str, email: str, password: str, newsletter_opt_in: int = 0, ruolo: str = "user"):
    email_n = _normalize_email(email)
    if not (nome and cognome and email_n and password):
        return {"ok": False, "msg": "Dati mancanti"}
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO utenti (nome, cognome, email, password_hash, newsletter_opt_in, ruolo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome.strip(), cognome.strip(), email_n, hash_password(password), int(bool(newsletter_opt_in)), ruolo))
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    except sqlite3.IntegrityError:
        return {"ok": False, "msg": "Email già registrata"}
    finally:
        conn.close()

def has_active_license(email: str) -> bool:
    email_n = _normalize_email(email)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1
        FROM licenze
        WHERE email = ?
          AND attiva = 1
          AND (scadenza IS NULL OR date(scadenza) >= date('now'))
        LIMIT 1
    """, (email_n,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok

def get_license_by_key(key: str):
    key = (key or "").strip()
    if not key:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, email, license_key, intestatario, scadenza, attiva, meta, created_at
        FROM licenze WHERE license_key = ?
    """, (key,))
    data = _fetchone_dict(cur)
    conn.close()
    return data

def activate_license(email: str, key: str):
    """
    Attiva SOLO licenze già esistenti in tabella (generate dall'admin).
    Regole:
      - key deve esistere in licenze. Se non esiste → errore (no auto-insert).
      - se scaduta → errore.
      - se già attiva per un altro email → errore (monouso).
      - se già attiva per lo stesso email → ok idempotente.
      - altrimenti: bind email + attiva=1.
    """
    email_n = _normalize_email(email)
    key = (key or "").strip()
    if not (email_n and key):
        return {"ok": False, "msg": "Dati mancanti"}

    conn = get_db()
    try:
        cur = conn.cursor()
        row = cur.execute("""
            SELECT id, email AS bound_email, license_key, scadenza, attiva
            FROM licenze WHERE license_key = ?
        """, (key,)).fetchone()

        if not row:
            return {"ok": False, "msg": "Codice licenza non valido"}

        # scadenza (se presente) non deve essere nel passato
        scad = row["scadenza"]
        if scad and cur.execute("SELECT date(?) < date('now')", (scad,)).fetchone()[0]:
            return {"ok": False, "msg": "Licenza scaduta"}

        # già attiva per altro utente?
        if row["attiva"] == 1 and row["bound_email"] and row["bound_email"] != email_n:
            return {"ok": False, "msg": "Licenza già attivata su un altro account"}

        # idempotente: se già attiva per lo stesso utente → OK
        if row["attiva"] == 1 and (row["bound_email"] or "") == email_n:
            return {"ok": True}

        # attiva e vincola all'email
        cur.execute("UPDATE licenze SET email = ?, attiva = 1 WHERE id = ?", (email_n, row["id"]))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

        # _______________________________________________________________________

from flask import session

def _set_selected_year(anno):
    """Salva in sessione l'anno attuale di lavoro (int)"""
    try:
        y = int(anno)
        if 2000 <= y <= 2035:  # guardrail
            session["selected_year"] = y
    except Exception:
        pass

def _get_selected_year():
    """Ritorna l'anno in sessione o l'anno corrente come fallback"""
    y = session.get("selected_year")
    if isinstance(y, int) and 2000 <= y <= 2035:
        return y    
    return datetime.now().year



# === DRIP EMAIL (helper) ===

def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z","").strip())
    except Exception:
        try:
            # fallback "YYYY-MM-DD HH:MM:SS"
            return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def _stage_from_days(d: int) -> int:
    # 2 = +3g, 3 = +6g, 4 = +9g, 5 = +12g
    if d >= 12: return 5
    if d >= 9:  return 4
    if d >= 6:  return 3
    if d >= 3:  return 2
    return 0

def _drip_subject(stage: int) -> str:
    return {
        2: "Hai già scoperto cosa può fare RistoSmartFM per te?",
        3: "Un regalo per te: il manuale per aprire il tuo ristorante",
        4: "Vuoi costruire un ristorante di successo? Ti aiutiamo noi.",
        5: "Ultima offerta: 20% di sconto + il Foodcost Calculator",
    }[stage]

def _drip_body_html(stage: int, nome: str) -> str:
    nm = nome or "Ristoratore"
    if stage == 2:
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Scopri RistoSmartFM</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <h2 style="color:#0d6efd;margin:0 0 8px">Ciao {nm}, hai visto come RistoSmartFM ti aiuta davvero?</h2>
  <p>Ordine, numeri chiari e decisioni rapide.</p>
  <ul>
    <li><strong>Incassi &amp; Spese</strong> sotto controllo</li>
    <li><strong>Clienti/Fornitori/Personale</strong> in un unico posto</li>
    <li><strong>Report</strong> immediati</li>
    <li><strong>Backup &amp; sicurezza</strong> integrati</li>
  </ul>
  <p><a href="http://127.0.0.1:5000/license" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">Attiva la licenza</a></p>
  <p style="font-size:12px;color:#666">Domande? <a href="mailto:ristoconsulenze@gmail.com">ristoconsulenze@gmail.com</a></p>
</body></html>"""
    if stage == 3:
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Regalo per te</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <h2 style="color:#0d6efd;margin:0 0 8px">{nm}, un regalo per iniziare</h2>
  <p>Con l’attivazione ricevi il libro <em>“Aprire un Ristorante da Zero: Il Manuale Essenziale per Realizzare il Tuo Sogno Culinario”</em>.</p>
  <p><a href="http://127.0.0.1:5000/license" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">Attiva ora e ricevi il libro</a></p>
</body></html>"""
    if stage == 4:
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Costruisci un ristorante di successo</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <h2 style="color:#0d6efd;margin:0 0 8px">Vuoi costruire un ristorante di successo? Ti aiutiamo noi, {nm}.</h2>
  <p>Omaggio: <em>“Comprendere e padroneggiare il concetto di food cost e il monitoraggio dei costi aziendali”</em>.</p>
  <p><a href="http://127.0.0.1:5000/license" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">Attiva la licenza</a></p>
</body></html>"""
    # stage 5 (+12 giorni)
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Ultima offerta</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <h2 style="color:#dc3545;margin:0 0 8px">Ultima offerta per te, {nm}</h2>
  <p><strong>20% di sconto</strong> sulla licenza.</p>
  <p>Aggiungendo <strong>€19,90</strong> ricevi anche il programma Excel <strong>“Foodcost Calculator”</strong>.</p>
  <p style="background:#fff3cd;padding:10px;border-radius:8px"><strong>Foodcost Calculator</strong>: inserisci ingredienti e rese; ottieni costo piatto, markup e margine per il menù engineering.</p>
  <p><a href="http://127.0.0.1:5000/license" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">Attiva ora</a></p>
  <p style="font-size:12px;color:#666">Supporto: <a href="mailto:ristoconsulenze@gmail.com">ristoconsulenze@gmail.com</a></p>
</body></html>"""

# Password policy (SOSTITUISCI questo blocco)
COMMON_PASSWORDS = {
    "password","123456","12345678","123456789","qwerty","admin",
    "ristosmart","ristosmartfm","password1","iloveyou","welcome"
}
FORBIDDEN_SUBSTRINGS = {"password","ristosmart","ristosmartfm","admin","qwerty","iloveyou"}
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?/\\|`~"

def _is_strong_password(p: str):
    s = p or ""
    if len(s) < 12:
        return False, "La password deve avere almeno 12 caratteri."
    has_low = any(c.islower() for c in s)
    has_up  = any(c.isupper() for c in s)
    has_dig = any(c.isdigit() for c in s)
    has_sym = any(c in SYMBOLS for c in s)
    if not (has_low and has_up and has_dig and has_sym):
        return False, "Usa minuscole, MAIUSCOLE, numeri e simboli."
    # normalizza togliendo i numeri per beccare 'password123' → 'password'
    s_norm = "".join(ch for ch in s.lower() if ch.isalpha())
    if any(bad in s_norm for bad in FORBIDDEN_SUBSTRINGS):
        return False, "Password troppo prevedibile."
    if s.lower() in COMMON_PASSWORDS:
        return False, "Password troppo comune."
    return True, ""

# === REGISTRAZIONE (GET/POST) ===
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # ⬇️ Verifica CSRF PRIMA di leggere i campi
        if not validate_csrf(request.form.get("csrf_token", "")):
            return render_template(
                "register.html",
                error="Sessione scaduta. Riprova.",
                preset={
                    "nome": (request.form.get("nome") or "").strip(),
                    "cognome": (request.form.get("cognome") or "").strip(),
                    "email": (request.form.get("email") or "").strip(),
                    "newsletter": 1 if request.form.get("newsletter") else 0,
                },
            ), 400

        nome = (request.form.get("nome") or "").strip()
        cognome = (request.form.get("cognome") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        newsletter = 1 if (request.form.get("newsletter") in ("on","1","true","True")) else 0

        if not all([nome, cognome, email, password, password2]):
            return render_template("register.html",
                                   error="Compila tutti i campi.",
                                   preset={"nome":nome,"cognome":cognome,"email":email,"newsletter":newsletter})

        if password != password2:
            return render_template("register.html",
                                   error="Le password non coincidono.",
                                   preset={"nome":nome,"cognome":cognome,"email":email,"newsletter":newsletter})

        ok_pw, pw_err = _is_strong_password(password)
        if not ok_pw:
            return render_template("register.html",
                                   error=pw_err,
                                   preset={"nome":nome,"cognome":cognome,"email":email,"newsletter":newsletter})

        res = create_user(nome, cognome, email, password, newsletter)
        if not res.get("ok"):
            return render_template("register.html",
                                   error=res.get("msg","Errore di registrazione"),
                                   preset={"nome":nome,"cognome":cognome,"email":email,"newsletter":newsletter})

        # Email 1 post-registrazione (utente HTML + admin plain) — best effort
        try:
            welcome_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Benvenuto! Scopri RistoSmartFM</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <h2 style="color:#0d6efd;margin:0 0 8px">Benvenuto in RistoSmartFM, {nome}!</h2>
  <p>Hai creato l’account. Per utilizzare tutte le funzioni, attiva la licenza.</p>
  <p>Per procedere scrivi a <a href="mailto:ristoconsulenze@gmail.com">ristoconsulenze@gmail.com</a>:
     ti guidiamo noi passo-passo.</p>
  <p style="margin-top:12px">
    <a href="http://127.0.0.1:5000/license"
       style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">
       Attiva la licenza
    </a>
  </p>
  <p style="font-size:12px;color:#666">Se non hai richiesto questa registrazione, ignora questo messaggio.</p>
</body></html>"""

            admin_plain = (
                "Nuovo utente registrato:\n"
                f"Nome: {nome} {cognome}\n"
                f"Email: {email}\n"
                f"Newsletter: {'SI' if newsletter else 'NO'}\n"
                f"Quando: {datetime.now().isoformat(timespec='seconds')}"
            )

            items = [
                {"email": _normalize_email(email),
                 "subject": "Benvenuto! Scopri RistoSmartFM",
                 "body": welcome_html},
                {"email": ADMIN_EMAIL,
                 "subject": "Nuova registrazione RistoSmart FM",
                 "body": admin_plain}
            ]
            send_emails_personalized(items)
        except Exception as e:
            print("[REGISTER EMAIL ERROR]", e)

        return render_template("register_done.html", email=_normalize_email(email))

    # GET
    return render_template("register.html")

from collections import deque
import time

FAILED_LOGINS = {}  # ip -> deque[timestamps]

def _client_ip():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()

def is_login_blocked(ip, window=600, limit=5):
    q = FAILED_LOGINS.get(ip)
    if not q:
        return False
    now = time.time()
    # ripulisce fuori finestra
    while q and now - q[0] > window:
        q.popleft()
    return len(q) >= limit

def register_login_failure(ip):
    q = FAILED_LOGINS.setdefault(ip, deque())
    now = time.time()
    q.append(now)

def clear_login_failures(ip):
    FAILED_LOGINS.pop(ip, None)

# === LOGIN (GET/POST) ===
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token", "")):
            return render_template("login.html", error="Sessione scaduta. Riprova."), 400
        ip = _client_ip()
        if is_login_blocked(ip):
            return render_template("login.html",
                                   error="Troppi tentativi. Riprova tra qualche minuto."), 429
        
        email = (request.form.get("email") or "").strip()
        password = (request.form.get("password") or "")

        user = get_user_by_email(email)
        if not user or not verify_password(user["password_hash"], password):
            register_login_failure(ip)  # <-- registra tentativo fallito
            return render_template("login.html",
                                   error="Credenziali non valide.",
                                   preset={"email": email})

        # --- LOGIN RIUSCITO ---
        session.clear()
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["user_role"] = user["ruolo"]
        session["logged_at"] = datetime.now().isoformat(timespec="seconds")
        session.permanent = True

        clear_login_failures(ip)  # <-- QUI, DOPO il successo

        # 🔒 Forza ADMIN se email corrisponde (fallback se .env non è caricato)
        admin_email = ((ADMIN_EMAIL or "ristoconsulenze@gmail.com").strip().lower())
        if session["user_email"].lower() == admin_email:
            session["user_role"] = "admin"
            # allinea anche il DB (best effort)
            try:
                conn = get_db()
                conn.execute(
                    "UPDATE utenti SET ruolo='admin' WHERE lower(email)=lower(?)",
                    (session["user_email"],)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print("[ADMIN PROMOTE WARN]", e)

        # Redirect: l'ADMIN entra ovunque anche senza licenza
        role = session.get("user_role")
        next_url = request.args.get("next") or url_for("home")
        if role != "admin" and not has_active_license(session["user_email"]):
            return redirect(url_for("license_page"))
        if not str(next_url).startswith("/"):
            next_url = url_for("home")
        return redirect(next_url)

    # GET
    return render_template("login.html")

# === ATTIVAZIONE LICENZA (GET/POST) ===
@app.route("/license", methods=["GET", "POST"])
def license_page():
    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token", "")):
            return render_template(
                "license.html",
                error="Sessione scaduta. Riprova.",
                preset={
                    "email": (request.form.get("email") or "").strip(),
                    "license_key": (request.form.get("license_key") or "").strip(),
                },
            ), 400
        
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        license_key = (request.form.get("license_key") or "").strip()

        user = get_user_by_email(email)
        if not user or not verify_password(user["password_hash"], password):
            return render_template("license.html",
                                   error="Credenziali non valide.",
                                   preset={"email": email, "license_key": license_key})

        res = activate_license(email, license_key)
        if not res.get("ok"):
            return render_template("license.html",
                                   error=res.get("msg","Licenza non valida."),
                                   preset={"email": email, "license_key": license_key})

        # garantisco sessione attiva
        session.clear()
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["user_role"] = user["ruolo"]
        session["logged_at"] = datetime.now().isoformat(timespec="seconds")
        session.permanent = True

        # --- Email di conferma attivazione (utente HTML + admin plain) ---
        try:
            nome = user.get("nome") or "Cliente"
            ok_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Licenza attivata</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <h2 style="color:#0d6efd;margin:0 0 8px;">Grazie {nome}! La tua licenza è attiva</h2>
  <p>Ora hai accesso completo alla dashboard di <strong>RistoSmart FM</strong>.</p>
  <ul>
    <li>Inserisci <strong>Incassi</strong> e <strong>Spese</strong> nei rispettivi mesi</li>
    <li>Gestisci <strong>Clienti</strong>, <strong>Fornitori</strong> e <strong>Personale</strong></li>
    <li>Usa la <strong>Newsletter</strong> per campagne email/WhatsApp</li>
  </ul>
  <p>Ti siamo vicini: per qualsiasi domanda rispondi a questa email.</p>
  <p style="margin-top:12px"><a href="http://127.0.0.1:5000/" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px">Vai alla dashboard</a></p>
</body></html>"""

            admin_plain = (
                "Licenza attivata:\n"
                f"Email: {email}\n"
                f"Key: {license_key}\n"
                f"Quando: {datetime.now().isoformat(timespec='seconds')}"
            )

            items = [
                { "email": _normalize_email(email), "subject": "Licenza attivata — RistoSmart FM", "body": ok_html },
                { "email": ADMIN_EMAIL, "subject": "Licenza attivata (notifica admin)", "body": admin_plain },
            ]
            send_emails_personalized(items)
        except Exception as e:
            print("[LICENSE OK EMAIL WARN]", e)

        return redirect(url_for("home"))

    # GET
    return render_template("license.html", preset={"email": session.get("user_email","")})


# === ADMIN: ESECUZIONE DRIP (3/5/10 giorni) ===
@app.get("/admin/drip")
@require_admin
def admin_drip():
    now = datetime.now()
    conn = get_db()
    cur = conn.cursor()

    users = cur.execute("""
        SELECT id, nome, cognome, email, registered_at, promo_last_sent, newsletter_opt_in
        FROM utenti
        ORDER BY id ASC
    """).fetchall()

    items = []
    to_update = []  # (user_id, email)
    for u in users:
        if not u["newsletter_opt_in"]:
            continue

        email = (u["email"] or "").strip().lower()
        if not email or has_active_license(email):
            continue

        reg_dt = _parse_dt(u["registered_at"])
        last_dt = _parse_dt(u["promo_last_sent"])
        if not reg_dt:
            continue

        days = (now.date() - reg_dt.date()).days
        stage = _stage_from_days(days)      # 0 / 2 / 3 / 4  → (3,5,10 giorni)
        if stage == 0:
            continue

        last_stage = _stage_from_days((last_dt.date() - reg_dt.date()).days) if last_dt else 0
        if stage <= last_stage:
            continue  # già inviato questo step (o successivo)

        subject = _drip_subject(stage)
        body = _drip_body_html(stage, u["nome"] or "")
        items.append({"email": email, "subject": subject, "body": body})
        to_update.append((u["id"], email))

    results = []
    if items:
        results = send_emails_personalized(items) or []
        ok_emails = {r.get("email") for r in results if r.get("ok")}
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        for uid, em in to_update:
            if em in ok_emails:
                cur.execute("UPDATE utenti SET promo_last_sent = ? WHERE id = ?", (ts, uid))
        conn.commit()

    conn.close()
    return jsonify({
        "ok": True,
        "checked_users": len(users),
        "sent": sum(1 for r in results if r.get("ok")),
        "errors": [r for r in results if not r.get("ok")]
    })

@app.route("/admin/licenses", methods=["GET", "POST"])
@require_admin
def admin_licenses():
    import secrets, sqlite3
    from datetime import datetime, date, timedelta

    def _gen_license_key():
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(16))
        return "RSFM-" + "-".join([raw[i:i+4] for i in range(0, 16, 4)])

    # Messaggi one–shot
    msg = session.pop("one_time_msg", None)
    new_key = session.pop("one_time_new_key", None)

    if request.method == "POST":
        tok = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not validate_csrf(tok):
            return "CSRF mancante o non valido", 400
        intestatario = (request.form.get("intestatario") or "").strip()
        scadenza = (request.form.get("scadenza") or "").strip() or None
        license_key = (request.form.get("license_key") or "").strip() or _gen_license_key()

        # Validazione scadenza (se presente)
        if scadenza:
            try:
                d = datetime.strptime(scadenza, "%Y-%m-%d").date()
                if d < (date.today() + timedelta(days=1)) or d > date(2030, 12, 31):
                    session["one_time_msg"] = "Data scadenza non valida (min: domani, max: 2030-12-31)"
                    return redirect(url_for("admin_licenses"))
            except Exception:
                session["one_time_msg"] = "Formato data scadenza non valido (YYYY-MM-DD)"
                return redirect(url_for("admin_licenses"))

        # INSERT licenza
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO licenze (email, license_key, intestatario, scadenza, attiva, meta)
                    VALUES ('', ?, ?, ?, 0, NULL)
                """, (license_key, intestatario or None, scadenza))
            session["one_time_msg"] = "Licenza creata"
            session["one_time_new_key"] = license_key
            return redirect(url_for("admin_licenses"))

        except sqlite3.IntegrityError:
            # Collisione: prova a rigenerare fino a 3 volte
            for _ in range(3):
                license_key = _gen_license_key()
                try:
                    with get_db() as conn:
                        conn.execute("""
                            INSERT INTO licenze (email, license_key, intestatario, scadenza, attiva, meta)
                            VALUES ('', ?, ?, ?, 0, NULL)
                        """, (license_key, intestatario or None, scadenza))
                    session["one_time_msg"] = "Licenza creata"
                    session["one_time_new_key"] = license_key
                    return redirect(url_for("admin_licenses"))
                except sqlite3.IntegrityError:
                    pass
            session["one_time_msg"] = "Errore: collisione chiave, riprova"
            return redirect(url_for("admin_licenses"))

    # --- GET: carica lista e RITORNA sempre ---
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, email, license_key, intestatario, scadenza, attiva, created_at, meta
            FROM licenze
            ORDER BY id DESC
            LIMIT 50
        """).fetchall()

    return render_template(
        "admin_licenses.html",
        licenze=[dict(r) for r in rows],
        msg=msg,
        new_key=new_key
    )

def run_expiry_reminders():
    """
    Invia promemoria di scadenza licenze attive a -10 / -5 / -1 giorni.
    Segna invii in licenze.meta con chiavi: exp10_sent_at / exp5_sent_at / exp1_sent_at.
    Ritorna un riepilogo dict.
    """
    import json, os
    from datetime import datetime, date

    def _parse_meta(s):
        try:
            return json.loads(s or "{}")
        except Exception:
            return {}

    # URL per il rinnovo (puoi sovrascrivere da .env)
    renew_url = os.getenv("RENEW_URL", "http://127.0.0.1:5000/license")

    today = date.today()
    items = []          # per send_emails_personalized
    updates = []        # [(id, stage_key, meta_dict)]

    # Prendi licenze ATTIVE con scadenza impostata (oggi..+10d)
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, email, license_key, intestatario, scadenza, meta
            FROM licenze
            WHERE attiva = 1
              AND scadenza IS NOT NULL
              AND date(scadenza) >= date('now')
              AND date(scadenza) <= date('now','+10 day')
        """).fetchall()

    for r in rows:
        lid   = r["id"]
        key   = (r["license_key"] or "").strip()
        name  = (r["intestatario"] or "Cliente").strip()
        scad  = (r["scadenza"] or "").strip()
        meta  = _parse_meta(r["meta"])

        try:
            scad_date = datetime.strptime(scad, "%Y-%m-%d").date()
        except Exception:
            continue

        days_left = (scad_date - today).days
        if days_left not in (10, 5, 1):
            continue

        stage_key = {10:"exp10_sent_at", 5:"exp5_sent_at", 1:"exp1_sent_at"}[days_left]
        if meta.get(stage_key):  # già inviato questo step
            continue

        # destinatario: email attivazione o ship_email da meta
        to_email = (r["email"] or meta.get("ship_email") or "").strip().lower()
        if not to_email:
            continue

        # soggetto + corpo HTML (con CTA "Rinnova licenza")
        if days_left == 10:
            subject = "Promemoria: la tua licenza RistoSmartFM scade tra 10 giorni"
            body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Scadenza tra 10 giorni</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <div style="max-width:620px;margin:auto;padding:16px;border:1px solid #eee;border-radius:8px">
    <h2 style="color:#0d6efd;margin:0 0 8px">Ciao {name},</h2>
    <p>ti ricordiamo che la tua licenza <strong>RistoSmartFM</strong> scadrà il <strong>{scad_date.strftime('%d/%m/%Y')}</strong>.</p>
    <p>Per evitare interruzioni del servizio, ti invitiamo a rinnovarla per tempo.</p>
    <p style="margin-top:14px">
      <a href="{renew_url}" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">
        Rinnova licenza
      </a>
    </p>
    <p style="margin-top:12px">Se hai bisogno di supporto per il rinnovo, rispondi a questa email: siamo a tua disposizione.</p>
    <p>Grazie,<br><strong>RistoSmartFM – Ufficio tecnico</strong></p>
  </div>
</body></html>"""
        elif days_left == 5:
            subject = "Attenzione: mancano 5 giorni alla scadenza della licenza"
            body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Scadenza tra 5 giorni</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <div style="max-width:620px;margin:auto;padding:16px;border:1px solid #eee;border-radius:8px">
    <h2 style="color:#0d6efd;margin:0 0 8px">Ciao {name},</h2>
    <p>la tua licenza <strong>RistoSmartFM</strong> scadrà il <strong>{scad_date.strftime('%d/%m/%Y')}</strong>.</p>
    <p>Rinnova ora per continuare a usare il gestionale senza interruzioni.</p>
    <p style="margin-top:14px">
      <a href="{renew_url}" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">
        Rinnova licenza
      </a>
    </p>
    <p>Serve aiuto? Siamo qui per accompagnarti nel rinnovo.</p>
    <p>Grazie,<br><strong>RistoSmartFM – Ufficio tecnico</strong></p>
  </div>
</body></html>"""
        else:  # days_left == 1
            subject = "Ultimo avviso: la licenza scade domani (+ regalo)"
            body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Scadenza domani</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.6">
  <div style="max-width:620px;margin:auto;padding:16px;border:1px solid #eee;border-radius:8px">
    <h2 style="color:#dc3545;margin:0 0 8px">Ciao {name},</h2>
    <p><strong>Domani</strong> scadrà la tua licenza <strong>RistoSmartFM</strong> (scadenza: <strong>{scad_date.strftime('%d/%m/%Y')}</strong>).</p>
    <p>Per ringraziarti della fiducia, con il rinnovo ti regaliamo <em><strong>Excel “FmM Calculator”</strong></em>: il tuo alleato per un foodcost perfetto.</p>
    <p style="margin-top:14px">
      <a href="{renew_url}" style="background:#0d6efd;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px;display:inline-block">
        Rinnova licenza
      </a>
    </p>
    <p>Contattaci per rinnovare subito e ricevere il regalo.</p>
    <p>Grazie,<br><strong>RistoSmartFM – Ufficio tecnico</strong></p>
  </div>
</body></html>"""

        items.append({"email": to_email, "subject": subject, "body": body})
        updates.append((lid, stage_key, meta))

    # invia in un colpo solo
    sent_ok = 0
    if items:
        res = send_emails_personalized(items) or []
        sent_ok = sum(1 for r in res if r.get("ok"))

    # marca invii
    if updates:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            for lid, stage_key, meta in updates:
                meta[stage_key] = ts
                try:
                    conn.execute("UPDATE licenze SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), lid))
                except Exception:
                    pass

    return {"checked": len(rows), "queued": len(items), "sent": sent_ok}

def _cleanup_backups():
    """Elimina i vecchi ZIP in C:\\RISTO\\BACKUP in base a conteggio e/o età."""
    import re
    from datetime import datetime, timedelta

    max_count   = int(app.config.get("BACKUP_MAX_COUNT", 15) or 0)       # quante copie tenere (0 = disattivo)
    max_age_days= int(app.config.get("BACKUP_MAX_AGE_DAYS", 0) or 0)     # 0 = disattivo
    keep_latest = True  # safety: non eliminare mai il più recente

    pattern = re.compile(r"^RistoSmartFM_DB_\d{8}_\d{6}\.zip$")
    files = [p for p in LOG_DIR.glob("RistoSmartFM_DB_*.zip") if pattern.match(p.name)]
    if not files:
        return 0

    # ordina per mtime (più nuovi prima)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = files[0]
    removed = 0

    # 1) taglio per età
    if max_age_days > 0:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        keep = []
        for p in files:
            try:
                if keep_latest and p == latest:
                    keep.append(p); continue
                if datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
                    p.unlink()
                    removed += 1
                else:
                    keep.append(p)
            except Exception as e:
                app.logger.warning("[BACKUP CLEANUP age] %s -> %s", p, e)
                keep.append(p)
        files = keep

    # 2) taglio per quantità (tieni i più recenti)
    if max_count > 0 and len(files) > max_count:
        # files è già ordinato; se keep_latest è True, assicuriamoci comunque di non toccare 'latest'
        start = max_count
        if keep_latest and latest in files and files.index(latest) >= max_count:
            # se per qualche motivo il più recente cadrebbe fuori, tienilo e sposta il taglio di uno
            start = max_count - 1
        for p in files[start:]:
            if keep_latest and p == latest:
                continue
            try:
                p.unlink()
                removed += 1
            except Exception as e:
                app.logger.warning("[BACKUP CLEANUP count] %s -> %s", p, e)

    return removed

@app.route("/admin/backup/db", methods=["GET", "POST"])
@require_admin
def admin_backup_db():
    # Richieste POST: richiedi il token CSRF
    if request.method == "POST":
        tok = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not validate_csrf(tok):
            return "CSRF mancante o non valido", 400

    from pathlib import Path
    import zipfile
    
    db_path = Path(app.config["DB_PATH"])
    out_dir = Path(LOG_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with get_db() as c:
            c.execute("PRAGMA wal_checkpoint(FULL);")
    except Exception as e:
        print("[BACKUP WARN] wal_checkpoint:", e)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = out_dir / f"RistoSmartFM_DB_{ts}.zip"

    files = [db_path]
    for ext in (".wal", ".shm"):
        p = Path(str(db_path) + ext)
        if p.exists():
            files.append(p)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, arcname=p.name)

    deleted = _cleanup_backups()
    app.logger.info("BACKUP CLEANUP: rimossi %s vecchi backup", deleted)
    app.logger.info("BACKUP creato: %s", zip_path)
    return send_file(str(zip_path), as_attachment=True, download_name=zip_path.name)

@app.get("/admin/licenses/export.csv")
@require_admin
def admin_licenses_export_csv():
    import csv
    from io import StringIO, BytesIO    

    # Prepara CSV in memoria (UTF-8 con BOM per Excel)
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id","email","license_key","intestatario","scadenza","attiva","created_at","meta"])

    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, email, license_key, intestatario, scadenza, attiva, created_at, meta
            FROM licenze
            ORDER BY id DESC
        """).fetchall()
        for r in rows:
            w.writerow([
                r["id"], r["email"], r["license_key"], r["intestatario"],
                r["scadenza"], r["attiva"], r["created_at"], (r["meta"] or "")
            ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM per Excel
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        BytesIO(csv_bytes),
        as_attachment=True,
        download_name=f"licenses_{ts}.csv",
        mimetype="text/csv"
    )

# === ADMIN LICENZE: endpoint AJAX (send_email / mark_sent / revoke) ===========

@app.post("/admin/licenses/send_email")
@require_admin
@require_csrf
def admin_license_send_email():
    data = request.get_json(silent=True) or {}
    license_key  = (data.get("license_key") or "").strip()
    intestatario = (data.get("intestatario") or "").strip()
    to_email     = (data.get("email") or "").strip().lower()

    if not license_key or not to_email:
        return jsonify({"ok": False, "msg": "Dati mancanti (license_key, email)"}), 400

    subject = "La tua licenza RistoSmartFM"
    body = (
        f"Ciao {intestatario or 'Cliente'},\n\n"
        f"Chiave licenza: {license_key}\n\n"
        "Istruzioni: accedi al gestionale, vai su 'Licenza' e incolla la chiave.\n\n"
        "RistoSmartFM — Ufficio tecnico"
    )

    try:
        res = send_emails([{"email": to_email}], subject, body) or []
        ok = bool(res and res[0].get("ok"))
        if not ok:
            err = (res[0].get("err") if res else "Invio non riuscito")
            return jsonify({"ok": False, "msg": f"Errore invio email: {err}"}), 500
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Errore invio email: {e}"}), 500

@app.post("/admin/licenses/mark_sent")
@require_admin
@require_csrf
def admin_license_mark_sent():
    import json
    
    data = request.get_json() or {}
    license_key = (data.get("license_key") or "").strip()
    email       = (data.get("email") or "").strip()
    wa_phone    = (data.get("wa_phone") or "").strip()
    channel     = (data.get("channel") or "").strip().lower()  # opzionale dal client

    if not license_key:
        return jsonify({"ok": False, "msg": "license_key mancante"}), 400

    # normalizza/ricava il canale
    if channel not in ("email", "wa", ""):
        channel = ""
    if not channel:
        channel = "email" if email else ("wa" if wa_phone else "unknown")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, meta FROM licenze WHERE license_key=?",
            (license_key,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "msg": "Licenza non trovata"}), 404

        try:
            meta = json.loads(row["meta"] or "{}")
        except Exception:
            meta = {}

        if email:
            meta["ship_email"] = email
        if wa_phone:
            meta["wa_phone"] = wa_phone
        meta["sent_at"] = ts
        meta["last_channel"] = channel

        conn.execute(
            "UPDATE licenze SET meta=? WHERE id=?",
            (json.dumps(meta, ensure_ascii=False), row["id"])
        )
        conn.commit()

    # utile al frontend per aggiornare subito la tabella
    return jsonify({"ok": True, "sent_at": ts, "channel": channel})

@app.post("/admin/licenses/revoke")
@require_admin
@require_csrf
def admin_license_revoke():
    data = request.get_json(silent=True) or {}
    try:
        lic_id = int(data.get("id", 0))
    except Exception:
        return jsonify({"ok": False, "msg": "ID non valido"}), 400
    if lic_id <= 0:
        return jsonify({"ok": False, "msg": "ID mancante"}), 400

    with get_db() as conn:
        row = conn.execute("SELECT id FROM licenze WHERE id=?", (lic_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "msg": "Licenza non trovata"}), 404
        conn.execute("DELETE FROM licenze WHERE id=?", (lic_id,))
        conn.commit()

    return jsonify({"ok": True})

# === ADMIN: Ripulisci test (tieni solo 1 email o 1 key) ======================
@app.post("/admin/licenses/cleanup")
@require_admin
@require_csrf
def admin_licenses_cleanup():
    mode        = (request.form.get("mode") or "").strip()     # "keep_email" | "keep_key"
    value       = (request.form.get("value") or "").strip()
    only_active = (request.form.get("only_active") in ("1","true","on","yes"))

    if not value:
        session["one_time_msg"] = "Valore mancante."
        return redirect(url_for("admin_licenses"))

    kept = 0
    deleted = 0

    with get_db() as conn:
        cur = conn.cursor()

        if mode == "keep_email":
            # prendi gli id da TENERE (per email) — se spunti "solo attive", tieni solo attive
            if only_active:
                ids = [r["id"] for r in cur.execute(
                    "SELECT id FROM licenze WHERE lower(email)=lower(?) AND attiva=1",
                    (value,)
                ).fetchall()]
            else:
                ids = [r["id"] for r in cur.execute(
                    "SELECT id FROM licenze WHERE lower(email)=lower(?)",
                    (value,)
                ).fetchall()]

            if not ids:
                session["one_time_msg"] = "Nessuna licenza trovata per quell'email."
                return redirect(url_for("admin_licenses"))

            kept = len(ids)
            qmarks = ",".join("?" for _ in ids)
            # elimina tutto il resto
            deleted = cur.execute(
                f"DELETE FROM licenze WHERE id NOT IN ({qmarks})",
                ids
            ).rowcount

        elif mode == "keep_key":
            # tieni SOLO questa key
            kept = 1
            deleted = cur.execute(
                "DELETE FROM licenze WHERE license_key <> ?",
                (value,)
            ).rowcount

        else:
            session["one_time_msg"] = "Modo non valido."
            return redirect(url_for("admin_licenses"))

        # allinea eventuale log rinnovi (se esiste)
        has_log = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='renewals_log'"
        ).fetchone()
        if has_log:
            cur.execute(
                "DELETE FROM renewals_log WHERE lic_key NOT IN (SELECT license_key FROM licenze)"
            )

        conn.commit()

    session["one_time_msg"] = f"Ripulito: tenute {kept}, eliminate {deleted}."
    return redirect(url_for("admin_licenses"))
# =============================================================================

# =============================================================================

@app.before_request
def _daily_expiry_cron():
    """
    Esegue i promemoria scadenza al primo hit del giorno (qualsiasi pagina).
    Salva un marker in backup/expiry_cron.txt per non ripetere.
    """
    try:        
        mark_path = LOG_DIR / "expiry_cron.txt"
        today = datetime.now().date().isoformat()
        last = ""
        if mark_path.exists():
            last = (mark_path.read_text(encoding="utf-8") or "").strip()
        if last != today:
            summary = run_expiry_reminders()
            mark_path.write_text(today, encoding="utf-8")
            print("[EXPIRY CRON]", summary)
    except Exception as e:
        print("[EXPIRY CRON WARN]", e)

@app.get("/admin/licenses/reminders")
@require_admin
def admin_licenses_reminders_now():
    summary = run_expiry_reminders()
    return jsonify({"ok": True, **summary})

# === RINNOVO LICENZA (PUBLIC + ADMIN) ========================================
from datetime import datetime, timedelta, date
from flask import render_template, request, redirect, url_for, jsonify

# --- Token HMAC: firmiamo {k,email,exp}
def _b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def sign_renew_token(key: str, email: str, hours: int = 48) -> str:
    payload = {"k": key, "e": (email or "").strip().lower(), "exp": int(time.time()) + hours*3600}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    p = _b64u_encode(raw)  # payload b64url
    sig = hmac.new(app.config["SECRET_KEY"].encode(), raw, hashlib.sha256).digest()
    s = _b64u_encode(sig)  # signature b64url
    return f"{p}.{s}"

def verify_renew_token(token: str):
    try:
        p, s = token.split(".", 1)                 # split testuale
        raw_payload = _b64u_decode(p)              # decode payload
        given_sig   = _b64u_decode(s)              # decode firma
        good_sig = hmac.new(app.config["SECRET_KEY"].encode(), raw_payload, hashlib.sha256).digest()
        if not hmac.compare_digest(given_sig, good_sig):
            return None, "Token non valido"
        payload = json.loads(raw_payload.decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            return None, "Token scaduto"
        return payload, None
    except Exception:
        return None, "Token non valido"

def _add_months(d: date, months: int) -> date:
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last_day))

# --- DB helpers (schema: licenze)
def _load_license(conn, key: str):
    return conn.execute("""
        SELECT license_key, intestatario, email, scadenza, attiva, meta
        FROM licenze
        WHERE license_key = ?
    """, (key,)).fetchone()

def _renew_license_core(key: str, email: str, months: int, actor: str):
    if months not in (1, 12, 24):
        raise ValueError("Durata non ammessa")
    with get_db() as conn:
        lic = _load_license(conn, key)
        if not lic:
            raise ValueError("Licenza non trovata")
        if (lic["email"] or "").strip().lower() != (email or "").strip().lower():
            raise ValueError("Email non corrisponde alla licenza")
        if not lic["scadenza"]:
            raise ValueError("Scadenza attuale assente")

        old = datetime.strptime(lic["scadenza"], "%Y-%m-%d").date()
        base = max(old, date.today())
        new_exp = _add_months(base, months)

        # azzera marker promemoria in meta (verranno rigenerati dal tuo cron)
        try:
            m = json.loads(lic["meta"] or "{}")
        except Exception:
            m = {}
        for k in ("exp10_sent_at", "exp5_sent_at", "exp1_sent_at"):
            m.pop(k, None)

        conn.execute("""
            UPDATE licenze
               SET scadenza = ?, attiva = 1, meta = ?
             WHERE license_key = ?
        """, (new_exp.isoformat(), json.dumps(m, ensure_ascii=False), key))

        # log rinnovo
        conn.execute("""
            CREATE TABLE IF NOT EXISTS renewals_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lic_key TEXT NOT NULL,
                email   TEXT NOT NULL,
                months  INTEGER NOT NULL,
                old_expiry TEXT NOT NULL,
                new_expiry TEXT NOT NULL,
                actor   TEXT NOT NULL,
                ts      TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO renewals_log(lic_key, email, months, old_expiry, new_expiry, actor, ts)
            VALUES (?,?,?,?,?,?,?)
        """, (key, email.strip().lower(), months, old.isoformat(), new_exp.isoformat(),
              actor, datetime.now().isoformat(timespec="seconds")))

        return old, new_exp, lic

def build_renew_url(key: str, email: str):
    tok = sign_renew_token(key, email, hours=48)
    return url_for('renew_get', token=tok, _external=True)

# -------- PUBLIC FLOW ---------------------------------------------------------
@app.get("/renew")
def renew_get():
    token = request.args.get("token", "")
    payload, err = verify_renew_token(token)
    if err:
        return render_template("renew.html", error=err, token_valid=False), 400
    key, email = payload["k"], payload["e"]
    with get_db() as conn:
        lic = _load_license(conn, key)
        if not lic or (lic["email"] or "").strip().lower() != email:
            return render_template("renew.html", error="Licenza non trovata o email non corretta", token_valid=False), 404
        stato = "Attiva" if (lic["attiva"] == 1) else "Non attiva"
        return render_template("renew.html",
                               token_valid=True,
                               token=token,
                               key=key,
                               intestatario=lic["intestatario"],
                               email=email,
                               scadenza=lic["scadenza"],
                               stato=stato)

@app.post("/renew")
@require_csrf
def renew_post():
    token = request.form.get("token", "")
    months = int(request.form.get("months", "0") or "0")
    payload, err = verify_renew_token(token)
    if err:
        return render_template("renew.html", error=err, token_valid=False), 400
    key, email = payload["k"], payload["e"]
    try:
        old_exp, new_exp, lic = _renew_license_core(key, email, months, actor="self-service")
        # notifica best-effort
        try:
            invia_email(
                to=email,
                oggetto="RistoSmart FM — Conferma rinnovo licenza",
                corpo=f"Ciao {lic['intestatario']},\n\nLa tua licenza {key} è stata rinnovata fino al {new_exp.isoformat()}.\nGrazie!\n"
            )
        except Exception:
            pass
        return redirect(url_for("renew_success", key=key, new_exp=new_exp.isoformat()))
    except Exception as e:
        return render_template("renew.html", error=str(e), token_valid=False), 400

@app.get("/renew/success")
def renew_success():
    return render_template("renew.html",
                           success=True,
                           key=request.args.get("key"),
                           new_exp=request.args.get("new_exp"))

# -------- ADMIN FLOW ----------------------------------------------------------
@app.get("/admin/licenses/renew/<key>")
@require_admin
def admin_renew_get(key):
    with get_db() as conn:
        lic = _load_license(conn, key)
        if not lic:
            return "Licenza non trovata", 404
        stato = "Attiva" if (lic["attiva"] == 1) else "Non attiva"
        return render_template("renew.html",
                               admin_mode=True,
                               key=lic["license_key"],
                               intestatario=lic["intestatario"],
                               email=lic["email"],
                               scadenza=lic["scadenza"],
                               stato=stato)

@app.post("/admin/licenses/renew/<key>")
@require_admin
@require_csrf
def admin_renew_post(key):
    email  = (request.form.get("email") or "").strip().lower()
    months = int(request.form.get("months", "0") or "0")
    try:
        old_exp, new_exp, lic = _renew_license_core(key, email, months, actor="admin")
        # notifica best-effort
        try:
            invia_email(
                to=email,
                oggetto="RistoSmart FM — Rinnovo licenza effettuato dall'amministrazione",
                corpo=f"Ciao {lic['intestatario']},\n\nLa tua licenza {key} è stata rinnovata fino al {new_exp.isoformat()}.\n"
            )
        except Exception:
            pass
        return redirect(url_for("renew_success", key=key, new_exp=new_exp.isoformat()))
    except Exception as e:
        return render_template("renew.html", admin_mode=True, error=str(e), key=key, email=email), 400

# =============================================================================


@app.route("/newsletter")
@require_login
@require_license
def newsletter_page():
    return render_template("newsletter.html")

# -----------------------------------------------------------------------------------

# --- API: Incassi (unica versione) ---
@app.get("/api/incassi/<int:anno>/<mese>")
@require_login
@require_license
def api_incassi(anno, mese):
    uid = _uid()
    m_norm, m_num = _normalize_mese(mese)  # es. ("settembre", 9)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT giorno, valore
              FROM incassi
             WHERE user_id=? AND anno=? AND (mese=? OR mese=? OR mese=?)
             ORDER BY giorno
        """, (uid, anno, m_norm, str(m_num), f"{m_num:02d}"))
        rows = [{"giorno": r["giorno"], "valore": r["valore"]} for r in cur.fetchall()]
    return jsonify(rows)

# --- API: Spese (unica versione) ---
@app.get("/api/spese/<int:anno>/<mese>")
@require_login
@require_license
def api_get_spese(anno, mese):
    uid = _uid()
    m_norm, m_num = _normalize_mese(mese)
    if not m_num:
        return jsonify({"error": "Mese non valido"}), 400

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT categoria, valore FROM spese_fisse 
            WHERE user_id=? AND anno=? AND (mese=? OR mese=? OR mese=?)
        """, (uid, anno, m_norm, str(m_num), f"{m_num:02d}"))
        rows = [{"categoria": r["categoria"], "valore": r["valore"]} for r in cur.fetchall()]

    return jsonify(rows)

@app.post("/api/salva-incasso")
@require_login
@require_license
@require_csrf
def salva_incasso():
    data = request.get_json() or {}
    anno = data.get("anno")
    mese_in = (data.get("mese") or "").strip().lower()
    giorno = data.get("giorno")
    valore = data.get("valore")

    # Validazione input
    if not (anno and mese_in and giorno is not None and valore is not None):
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        anno = int(anno)
        giorno = int(giorno)
        valore = float(valore)
    except (TypeError, ValueError):
        return jsonify({"error": "Dati numerici non validi"}), 400

    mese_norm, mese_num = _normalize_mese(mese_in)
    if not mese_num:
        return jsonify({"error": "Mese non valido"}), 400

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO incassi (user_id, anno, mese, giorno, valore)
            VALUES (?, ?, ?, ?, ?)
        """, (_uid(), anno, mese_norm, giorno, valore))
        conn.commit()

    return jsonify({"success": True})

# === API: Spese ===
SPESI_FISSE_WHITELIST = {"canone", "finanziamento1", "finanziamento2", "finanziamento-altro"}

@app.post("/api/salva-spesa")
@require_login
@require_license
@require_csrf
def salva_spesa():
    data = request.get_json(silent=True) or {}
    anno = data.get("anno")
    mese_in = data.get("mese") or ""
    categoria = (data.get("categoria") or "").strip().lower()
    valore = data.get("valore")

    # Validazioni
    try:
        anno = int(anno)
        valore = float(valore)
    except (TypeError, ValueError):
        return jsonify({"error": "Anno o valore non validi"}), 400

    if not categoria:
        return jsonify({"error": "Categoria richiesta"}), 400

    if categoria not in SPESI_FISSE_WHITELIST:
        return jsonify({"error": "Categoria non consentita"}), 400

    mese_norm, mese_num = _normalize_mese(mese_in)
    if not mese_num:
        return jsonify({"error": "Mese non valido"}), 400

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO spese_fisse (user_id, anno, mese, categoria, valore)
            VALUES (?, ?, ?, ?, ?)
        """, (_uid(), anno, mese_norm, categoria, valore))
        conn.commit()

    return jsonify({"success": True})

from flask import abort

def _uid():
    uid = session.get("user_id")
    if not uid:
        abort(401)
    return int(uid)

def _normalize_mese(m: str):
    m = (m or "").strip().lower()
    mesi = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
            "luglio","agosto","settembre","ottobre","novembre","dicembre"]
    aliases = {
        "gen":"gennaio","feb":"febbraio","mar":"marzo","apr":"aprile","mag":"maggio","giu":"giugno",
        "lug":"luglio","ago":"agosto","set":"settembre","sett":"settembre","sep":"settembre",
        "ott":"ottobre","nov":"novembre","dic":"dicembre"
    }
    if m.isdigit():
        i = int(m)
        if 1 <= i <= 12:
            return mesi[i-1], i
    if m in aliases:
        m = aliases[m]
    if m in mesi:
        return m, mesi.index(m)+1
    return m, None

# ---------------------------------------------------------------------------------------------------------------

# === API: Clienti ===
@app.get("/api/clienti")
@require_login
@require_license
def api_get_clienti():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, nome, telefono, email, note FROM clienti WHERE user_id=? ORDER BY id DESC",
        (_uid(),)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/clienti")
@require_login
@require_license
@require_csrf
def api_add_cliente():
    data = request.get_json(silent=True) or {}
    nome = str(data.get("nome") or "").strip()
    telefono = str(data.get("telefono") or "").strip()
    email = str(data.get("email") or "").strip()
    note = str(data.get("note") or "").strip()
    if not nome:
        return jsonify({"error": "Nome obbligatorio"}), 400

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO clienti (nome, telefono, email, note, user_id) VALUES (?,?,?,?,?)",
                   (nome, telefono, email, note, _uid()))
        new_id = cur.lastrowid
        conn.commit()

        row = cur.execute("SELECT id, nome, telefono, email, note FROM clienti WHERE id=? AND user_id=?",
                         (new_id, _uid())).fetchone()
        if not row:
            return jsonify({"error": "Cliente creato ma non leggibile"}), 500

        return jsonify(dict(row))

@app.put("/api/clienti/<int:cliente_id>")
@require_login
@require_license
@require_csrf
def api_update_cliente(cliente_id):
    data = request.get_json(silent=True) or {}
    nome = str(data.get("nome") or "").strip()
    telefono = str(data.get("telefono") or "").strip()
    email = str(data.get("email") or "").strip()
    note = str(data.get("note") or "").strip()
    if not nome:
        return jsonify({"error": "Nome obbligatorio"}), 400

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE clienti SET nome=?, telefono=?, email=?, note=?
            WHERE id=? AND user_id=?
        """, (nome, telefono, email, note, cliente_id, _uid()))

        if cur.rowcount == 0:
            return jsonify({"error": "Cliente non trovato o non autorizzato"}), 404

        conn.commit()

        row = cur.execute("SELECT id, nome, telefono, email, note FROM clienti WHERE id=? AND user_id=?",
                         (cliente_id, _uid())).fetchone()
        if not row:
            return jsonify({"error": "Cliente non trovato dopo aggiornamento"}), 500

        return jsonify(dict(row))

@app.delete("/api/clienti/<int:cliente_id>")
@require_login
@require_license
@require_csrf
def api_delete_cliente(cliente_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM clienti WHERE id=? AND user_id=?", (cliente_id, _uid()))
        if cur.rowcount == 0:
            return jsonify({"error": "Cliente non trovato o non autorizzato"}), 404
        conn.commit()
    return jsonify({"success": True})

# ----------------------------------------------------------------------------------------

# --- PERSONALE (multi-tenant) ---

@app.get("/api/personale")
@require_login
def api_list_personale():
    user_id = _uid()
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute("""
            SELECT id, nome, ruolo, data_assunzione, rapporto, data_fine,
                   telefono, email, iban, riposo
            FROM personale
            WHERE user_id=?
            ORDER BY nome COLLATE NOCASE
        """, (user_id,)).fetchall()
    return jsonify({"success": True, "personale": [dict(r) for r in rows]})

@app.post("/api/personale")
@require_login
@require_csrf
def api_add_personale():
    user_id = _uid()
    data = request.get_json(silent=True) or {}

    # normalizzazione
    nome = (data.get("nome") or "").strip()
    ruolo = (data.get("ruolo") or "").strip()
    data_assunzione = data.get("dataAssunzione") or data.get("data_assunzione")
    rapporto = data.get("tipoRapporto") or data.get("rapporto")
    data_fine = data.get("dataFine") or data.get("data_fine")
    telefono = (data.get("telefono") or "").strip()
    email = (data.get("email") or "").strip()
    iban = (data.get("iban") or "").strip()
    riposo = (data.get("riposo") or "").strip()

    if not nome:
        return jsonify({"success": False, "error": "Nome richiesto"}), 400

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO personale
                (user_id, nome, ruolo, data_assunzione, rapporto, data_fine,
                 telefono, email, iban, riposo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                user_id, nome, ruolo, data_assunzione, rapporto, data_fine,
                telefono, email, iban, riposo
            ))
            new_id = cur.lastrowid
            conn.commit()
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        app.logger.error(f"Errore POST personale: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.put("/api/personale/<int:pid>")
@require_login
@require_csrf
def api_update_personale(pid):
    user_id = _uid()
    data = request.get_json(silent=True) or {}

    nome = (data.get("nome") or "").strip()
    ruolo = (data.get("ruolo") or "").strip()
    data_assunzione = data.get("dataAssunzione") or data.get("data_assunzione")
    rapporto = data.get("tipoRapporto") or data.get("rapporto")
    data_fine = data.get("dataFine") or data.get("data_fine")
    telefono = (data.get("telefono") or "").strip()
    email = (data.get("email") or "").strip()
    iban = (data.get("iban") or "").strip()
    riposo = (data.get("riposo") or "").strip()

    if not nome:
        return jsonify({"success": False, "error": "Nome richiesto"}), 400

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE personale
                SET nome=?, ruolo=?, data_assunzione=?, rapporto=?, data_fine=?,
                    telefono=?, email=?, iban=?, riposo=?
                WHERE id=? AND user_id=?
            """, (
                nome, ruolo, data_assunzione, rapporto, data_fine,
                telefono, email, iban, riposo,
                pid, user_id
            ))
            if cur.rowcount == 0:
                return jsonify({"success": False, "error": "Non autorizzato o non trovato"}), 404
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Errore PUT personale: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.delete("/api/personale/<int:pid>")
@require_login
@require_csrf
def api_delete_personale(pid):
    user_id = _uid()
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM personale WHERE id=? AND user_id=?", (pid, user_id))
            if not cur.fetchone():
                return jsonify({"success": False, "error": "Personale non trovato"}), 404

            cur.execute("DELETE FROM personale WHERE id=? AND user_id=?", (pid, user_id))
            conn.commit()
        return jsonify({"success": True, "deleted_id": pid})
    except Exception as e:
        app.logger.error(f"Errore DELETE personale {pid}: {e}")
        return jsonify({"success": False, "error": "Errore eliminazione dipendente"}), 500

#------------------------------------------------------------------------------------------------

# =========================
#         STIPENDI
# =========================

# --- GET STIPENDI MENSILI ---
@app.get("/api/stipendi/<int:anno>/<int:mese>")
@require_login
@require_license
def api_stipendi_mese(anno, mese):
    """Restituisce il totale stipendi per ruolo in un dato mese (mese=1..12)"""
    user_id = _uid()
    if mese < 1 or mese > 12:
        return jsonify(success=False, error="Mese non valido"), 400

    mappa = {
        "Amministrazione": "amministrazione",
        "Staff Cucina": "staff-cucina",
        "Staff Sala": "staff-sala",
        "Staff Lavapiatti": "staff-lavapiatti",
        "Staff Pulizie": "staff-pulizie",
        "Altro": "altro"
    }
    totali = {key: 0 for key in mappa.values()}

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute("""
            SELECT sp.lordo, p.ruolo
            FROM stipendi_personale sp
            JOIN personale p ON p.id = sp.personale_id AND p.user_id = sp.user_id
            WHERE sp.user_id = ? AND sp.anno = ? AND sp.mese = ?
        """, (user_id, anno, mese)).fetchall()

        for r in rows:
            ruolo = r["ruolo"] or "Altro"
            key = mappa.get(ruolo, "altro")
            totali[key] += r["lordo"] or 0.0

    return jsonify(success=True, stipendi=totali)

# --- GET STIPENDI ANNUALI ---
@app.get("/api/stipendi/<int:anno>")
@require_login
@require_license
def api_stipendi_anno(anno):
    """Restituisce i totali stipendi per ruolo in un anno intero"""
    user_id = _uid()
    mappa = {
        "Amministrazione": "amministrazione",
        "Staff Cucina": "staff-cucina",
        "Staff Sala": "staff-sala",
        "Staff Lavapiatti": "staff-lavapiatti",
        "Staff Pulizie": "staff-pulizie",
        "Altro": "altro"
    }
    totali = {key: 0 for key in mappa.values()}

    try:
        with get_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rows = cur.execute("""
                SELECT sp.lordo, p.ruolo
                FROM stipendi_personale sp
                JOIN personale p ON p.id = sp.personale_id AND p.user_id = sp.user_id
                WHERE sp.user_id = ? AND sp.anno = ?
            """, (user_id, anno)).fetchall()

            for r in rows:
                ruolo = r["ruolo"] or "Altro"
                key = mappa.get(ruolo, "altro")
                totali[key] += r["lordo"] or 0.0

        return jsonify(success=True, stipendi=totali)
    except Exception as e:
        app.logger.error(f"Errore GET stipendi anno {anno}: {e}")
        return jsonify(success=False, error=str(e)), 500

# --- PUT STIPENDI DIPENDENTE ---
@app.put("/api/stipendi/<int:personale_id>")
@require_login
@require_license
@require_csrf
def api_upsert_stipendi(personale_id):
    """Aggiorna i valori stipendio di un dipendente per più mesi (DB: mese=1..12)"""
    payload = request.get_json(silent=True) or {}
    try:
        anno = int(payload.get("anno"))
    except (TypeError, ValueError):
        return jsonify(success=False, error="Anno non valido"), 400

    mesi = payload.get("mesi") or {}
    if not isinstance(mesi, dict):
        return jsonify(success=False, error="Formato mesi non valido"), 400

    uid = _uid()
    with get_db() as conn:
        cur = conn.cursor()

        # autorizzazione: il dipendente deve appartenere all'utente corrente
        owner = cur.execute(
            "SELECT 1 FROM personale WHERE id=? AND user_id=?",
            (personale_id, uid)
        ).fetchone()
        if not owner:
            return jsonify(success=False, error="Dipendente non trovato"), 404

        for raw_month, raw_values in mesi.items():
            token = (str(raw_month or "").strip().lower())

            # accetta sia "gennaio" che "1"/"01"
            if token.isdigit():
                m = int(token)
                if 1 <= m <= 12:
                    mese_num = m
                else:
                    continue
            else:
                mese_num = MONTH_SLUG_TO_NUM.get(token)
                if not mese_num:
                    continue

            values = raw_values or {}
            lordo = round(max(_normalize_amount(values.get("lordo")), 0.0), 2)
            netto = round(max(_normalize_amount(values.get("netto")), 0.0), 2)
            contributi = round(max(lordo - netto, 0.0), 2)
            totale = lordo
            stato = "pagato" if values.get("pagato") else "non_pagato"

            if lordo == 0 and netto == 0 and stato == "non_pagato":
                cur.execute(
                    "DELETE FROM stipendi_personale "
                    "WHERE user_id=? AND personale_id=? AND anno=? AND mese=?",
                    (uid, personale_id, anno, mese_num)
                )
            else:
                cur.execute("""
                    INSERT INTO stipendi_personale
                        (user_id, personale_id, anno, mese, lordo, netto, contributi, totale, stato_pagamento)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, personale_id, anno, mese) DO UPDATE SET
                        lordo=excluded.lordo,
                        netto=excluded.netto,
                        contributi=excluded.contributi,
                        totale=excluded.totale,
                        stato_pagamento=excluded.stato_pagamento
                """, (uid, personale_id, anno, mese_num,
                      lordo, netto, contributi, totale, stato))

        conn.commit()

    return jsonify(success=True)

@app.get("/api/stipendi/dettaglio/<int:anno>")
@require_login
@require_license
def api_stipendi_dettaglio(anno):
    uid = _uid()
    result = {}
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute("""
            SELECT sp.personale_id, p.nome, p.ruolo, sp.mese, sp.lordo, sp.netto,
                   sp.contributi, sp.totale, sp.stato_pagamento
            FROM stipendi_personale sp
            JOIN personale p ON p.id = sp.personale_id AND p.user_id = sp.user_id
            WHERE sp.user_id=? AND sp.anno=?
        """, (uid, anno)).fetchall()

    for r in rows:
        pid = str(r["personale_id"])
        m = int(r["mese"]) if str(r["mese"]).strip().isdigit() else None
        mese_slug = MONTH_NUM_TO_SLUG.get(m, str(r["mese"]).strip().lower())

        rec = result.setdefault(pid, {"id": r["personale_id"], "nome": r["nome"], "ruolo": r["ruolo"], "mesi": {}})
        rec["mesi"][mese_slug] = {
            "lordo": float(r["lordo"] or 0.0),
            "netto": float(r["netto"] or 0.0),
            "contributi": float(r["contributi"] or 0.0),
            "totale": float(r["totale"] or 0.0),
            "pagato": (r["stato_pagamento"] == "pagato")
        }

    return jsonify({"success": True, "stipendi": result})

# --- DELETE TUTTI GLI STIPENDI DELL'UTENTE CORRENTE ---
@app.delete("/api/stipendi")
@require_login
@require_license
@require_csrf
def api_delete_all_stipendi():
    uid = _uid()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM stipendi_personale WHERE user_id=?", (uid,))
        deleted = cur.rowcount or 0
        conn.commit()
    return jsonify(success=True, deleted=deleted)

# --- QR PAGAMENTO STIPENDI ---
@app.post("/api/stipendi/<int:personale_id>/qr")
@require_login
@require_license
@require_csrf
def api_stipendi_qr(personale_id):
    """Genera un QR SEPA per il pagamento stipendio di un dipendente"""
    payload = request.get_json(silent=True) or {}
    mese_slug = (payload.get("mese") or "").strip().lower()
    try:
        anno = int(payload.get("anno"))
    except (TypeError, ValueError):
        return jsonify(error="Anno non valido"), 400
    if mese_slug not in MONTH_SET:
        return jsonify(error="Mese non valido"), 400

    # normalizza mese: slug -> INT 1..12
    mese_num = MONTH_SLUG_TO_NUM.get(mese_slug)
    if not mese_num:
        return jsonify(error="Mese non valido"), 400

    netto = max(_normalize_amount(payload.get("netto")), 0.0)
    uid = _uid()
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        persona = cur.execute("""
            SELECT nome, ruolo, iban
            FROM personale
            WHERE id=? AND user_id=?
        """, (personale_id, uid)).fetchone()
        if not persona:
            return jsonify(error="Dipendente non trovato"), 404

        stored = cur.execute("""
            SELECT netto FROM stipendi_personale
            WHERE user_id=? AND personale_id=? AND anno=? AND mese=?
        """, (uid, personale_id, anno, mese_num)).fetchone()

    if stored and stored["netto"] is not None:
        try:
            netto = max(float(stored["netto"]), netto)
        except Exception:
            netto = max(netto, 0.0)

    if netto <= 0:
        return jsonify(error="Importo netto non disponibile"), 400

    import qrcode, base64
    from io import BytesIO

    iban = (persona["iban"] or "").strip().replace(" ", "").upper()
    if not iban or len(iban) < 15:
        return jsonify(error="IBAN non valido"), 400

    nome = (persona["nome"] or "Dipendente").strip()[:70]
    categoria = (persona["ruolo"] or "Altro").strip()
    periodo = _format_periodo(mese_slug, anno)

    remittance = f"Stipendio {periodo}"[:140]
    info = f"Categoria: {categoria}"[:140]

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data("\n".join([
        "BCD", "002", "1", "SCT", "",
        nome, iban, f"EUR{netto:.2f}", "",
        remittance, info
    ]))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return jsonify({
        "qr_image": f"data:image/png;base64,{qr_b64}",
        "periodo": periodo,
        "nome": nome,
        "categoria": categoria,
        "netto": round(netto, 2),
        "iban": iban
    })

# ------------------------------------------------------------------------------------------

# --- API FORNITORI ---
@app.route("/api/fornitori", methods=["GET", "POST"])
@require_login
@require_license
def api_fornitori():
    uid = _uid()

    # --- LISTA ---
    if request.method == "GET":
        with get_db() as conn:
            cur = conn.execute(
                """SELECT id, nomeFornitore, nomeAgente, categoria, 
                          telAgente, telAzienda, indirizzo, iban_beneficiario, bic_beneficiario, note
                   FROM fornitori 
                   WHERE user_id = ? 
                   ORDER BY id DESC""",
                (uid,)
            )
            rows = [dict(r) for r in cur.fetchall()]
        return jsonify(rows)

    # --- CREAZIONE ---
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO fornitori
                   (user_id, nomeFornitore, nomeAgente, categoria, telAgente, telAzienda, indirizzo, 
                    iban_beneficiario, bic_beneficiario, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uid,
                    data.get("nomeFornitore"),
                    data.get("nomeAgente"),
                    data.get("categoria"),
                    data.get("telAgente"),
                    data.get("telAzienda"),
                    data.get("indirizzo"),
                    data.get("iban_beneficiario"),
                    data.get("bic_beneficiario"),
                    data.get("note"),
                ),
            )
            new_id = cur.lastrowid
            conn.commit()

            # ritorna i dati appena inseriti
            row = conn.execute(
                """SELECT id, nomeFornitore, nomeAgente, categoria, 
                          telAgente, telAzienda, indirizzo, iban_beneficiario, bic_beneficiario, note
                   FROM fornitori WHERE id=? AND user_id=?""",
                (new_id, uid)
            ).fetchone()

        return jsonify(dict(row)), 201


# --- UPDATE fornitore ---
@app.put("/api/fornitori/<int:fid>")
@require_login
@require_license
@require_csrf
def api_update_fornitore(fid):
    uid = _uid()
    data = request.get_json(silent=True) or {}
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE fornitori
               SET nomeFornitore=?, nomeAgente=?, categoria=?, telAgente=?, 
                   telAzienda=?, indirizzo=?, iban_beneficiario=?, bic_beneficiario=?, note=?
               WHERE id=? AND user_id=?""",
            (
                data.get("nomeFornitore"),
                data.get("nomeAgente"),
                data.get("categoria"),
                data.get("telAgente"),
                data.get("telAzienda"),
                data.get("indirizzo"),
                data.get("iban_beneficiario"),
                data.get("bic_beneficiario"),
                data.get("note"),
                fid,
                uid,
            )
        )
        conn.commit()

        row = cur.execute(
            """SELECT id, nomeFornitore, nomeAgente, categoria, 
                      telAgente, telAzienda, indirizzo, iban_beneficiario, bic_beneficiario, note
               FROM fornitori WHERE id=? AND user_id=?""",
            (fid, uid)
        ).fetchone()

    if not row:
        return jsonify({"error": "Fornitore non trovato"}), 404
    return jsonify(dict(row))


# --- DELETE fornitore ---
@app.delete("/api/fornitori/<int:fid>")
@require_login
@require_license
@require_csrf
def api_delete_fornitore(fid):
    uid = _uid()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM fornitori WHERE id=? AND user_id=?", (fid, uid))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Fornitore non trovato"}), 404
    return jsonify({"success": True})

@app.get("/api/dettaglio_fornitori")
@require_login
@require_license
def api_dettaglio_fornitori():
    uid = _uid()
    anno = request.args.get("anno", type=int) or datetime.now().year

    with get_db() as conn:
        cur = conn.cursor()

        # Query principale: somma per fornitore, categoria e mese
        query = """
            SELECT 
                fornitore,
                categoria,
                CAST(strftime('%m', data_inserimento) AS INTEGER) as mese_num,
                SUM(importo) as totale_mensile
            FROM fatture
            WHERE user_id = ? 
              AND CAST(strftime('%Y', data_inserimento) AS INTEGER) = ?
            GROUP BY fornitore, categoria, mese_num
            ORDER BY fornitore, categoria
        """
        cur.execute(query, [uid, anno])
        rows = cur.fetchall()

        # Costruisci struttura dati
        result = {}
        for row in rows:
            key = (row["fornitore"], row["categoria"])
            if key not in result:
                result[key] = {
                    "fornitore": row["fornitore"],
                    "categoria": row["categoria"],
                    "mesi": [0.0] * 12,  # Gennaio a Dicembre
                    "totaleAnnuale": 0.0
                }
            mese_idx = row["mese_num"] - 1  # 1→0, 2→1, ..., 12→11
            importo = row["totale_mensile"]
            result[key]["mesi"][mese_idx] += importo
            result[key]["totaleAnnuale"] += importo

        return jsonify(list(result.values()))

import werkzeug.utils
import pathlib

# cartella base dove salvare i PDF (una per ogni utente)
USER_FILES_DIR = app.config.get(
    "USER_FILES_DIR",
    os.path.join(os.path.dirname(app.config["DB_PATH"]), "user_files")
)
os.makedirs(USER_FILES_DIR, exist_ok=True)


@app.post("/api/fornitori/<int:fid>/upload_pdf")
@require_login
@require_license
@require_csrf
def api_upload_fornitore_pdf(fid):
    uid = _uid()  # id utente loggato → garantisce isolamento
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "msg": "Nessun file inviato"}), 400
    if f.mimetype != "application/pdf":
        return jsonify({"ok": False, "msg": "Solo PDF accettati"}), 400

    # nome sicuro + timestamp per evitare conflitti
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dest_name = f"fornitore_{fid}_{timestamp}.pdf"

    user_folder = os.path.join(USER_FILES_DIR, str(uid), "fornitori")
    os.makedirs(user_folder, exist_ok=True)

    dest_path = os.path.join(user_folder, dest_name)
    f.save(dest_path)

    # salva percorso nel DB
    with get_db() as conn:
        conn.execute(
            "UPDATE fornitori SET pdf_path=? WHERE id=? AND user_id=?",
            (dest_path, fid, uid)
        )
        conn.commit()

    return jsonify({"ok": True, "pdf_path": dest_path})

@app.get("/fornitori/<int:fid>/pdf")
@require_login
@require_license
def download_fornitore_pdf(fid):
    uid = _uid()
    with get_db() as conn:
        row = conn.execute(
            "SELECT pdf_path FROM fornitori WHERE id=? AND user_id=?",
            (fid, uid)
        ).fetchone()

    if not row or not row["pdf_path"]:
        return "File non trovato", 404

    path = row["pdf_path"]

    # sicurezza: il file deve stare nella cartella USER_FILES_DIR
    if not os.path.abspath(path).startswith(os.path.abspath(USER_FILES_DIR)):
        return "Accesso negato", 403

    return send_file(path, as_attachment=True, download_name=os.path.basename(path))
        
# ---------------------------------------------------------------------------------------------

# === API: Fatture ===
@app.get("/api/fatture")
@require_login
@require_license
def api_get_fatture():
    # Forza sempre un anno valido
    anno = request.args.get("anno", type=int)
    if anno is None:
        anno = _get_selected_year()
        if anno is None:
            anno = datetime.now().year  # fallback all'anno corrente

    uid = _uid()
    with get_db() as conn:
        cur = conn.cursor()
        rows = cur.execute("""
            SELECT id, data_inserimento, fornitore, categoria,
                   data_scadenza, importo, stato, numero
            FROM fatture
            WHERE user_id = ?
              AND CAST(strftime('%Y', data_inserimento) AS INTEGER) = ?
            ORDER BY date(data_inserimento) DESC
        """, (uid, anno)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/dettaglio_fornitori")
@require_login
@require_license
def dettaglio_fornitori():
    return render_template("dettaglio_fornitori.html")

@app.post("/api/fatture")
@require_login
@require_license
@require_csrf
def api_add_fattura():
    data = request.get_json() or {}
    required = ["data_inserimento", "fornitore", "categoria", "data_scadenza", "importo", "stato"]
    if not all(data.get(k) is not None for k in required):
        return jsonify({"error": "Dati mancanti"}), 400

    uid = _uid()
    with get_db() as conn:
        cur = conn.cursor()

        # 🔎 Recupera id_fornitore corrispondente (se esiste)
        id_fornitore = cur.execute(
            "SELECT id FROM fornitori WHERE nomeFornitore = ? AND user_id = ? LIMIT 1",
            (data["fornitore"], uid)
        ).fetchone()
        id_fornitore = id_fornitore["id"] if id_fornitore else None

        # ➕ Inserimento fattura con id_fornitore
        cur.execute("""
            INSERT INTO fatture (user_id, data_inserimento, fornitore, categoria,
                                 data_scadenza, importo, stato, numero, id_fornitore)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uid,
            data["data_inserimento"],
            data["fornitore"],
            data["categoria"],
            data["data_scadenza"],
            float(data["importo"]),
            data["stato"],
            data.get("numero", ""),
            id_fornitore
        ))

        new_id = cur.lastrowid
        conn.commit()

        row = cur.execute("""
            SELECT id, data_inserimento, fornitore, categoria, data_scadenza,
                   importo, stato, numero, id_fornitore
            FROM fatture
            WHERE id = ? AND user_id = ?
        """, (new_id, uid)).fetchone()

        if not row:
            return jsonify({"error": "Fattura creata ma non leggibile"}), 500

        return jsonify(dict(row))

@app.put("/api/fatture/<int:fattura_id>")
@require_login
@require_license
@require_csrf
def api_update_fattura(fattura_id):
    data = request.get_json() or {}
    required = ["data_inserimento", "fornitore", "categoria", "data_scadenza", "importo", "stato"]
    if not all(k in data for k in required):
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        importo = float(data["importo"])
    except (TypeError, ValueError):
        return jsonify({"error": "Importo non valido"}), 400

    uid = _uid()
    with get_db() as conn:
        cur = conn.cursor()

        # 🔎 Recupera id_fornitore corrispondente (può essere cambiato)
        id_fornitore = cur.execute(
            "SELECT id FROM fornitori WHERE nomeFornitore = ? AND user_id = ? LIMIT 1",
            (data["fornitore"], uid)
        ).fetchone()
        id_fornitore = id_fornitore["id"] if id_fornitore else None

        # 🔄 Aggiorna fattura
        cur.execute("""
            UPDATE fatture SET
                data_inserimento = ?,
                fornitore = ?,
                categoria = ?,
                data_scadenza = ?,
                importo = ?,
                stato = ?,
                numero = ?,
                id_fornitore = ?
            WHERE id = ? AND user_id = ?
        """, (
            data["data_inserimento"],
            data["fornitore"],
            data["categoria"],
            data["data_scadenza"],
            importo,
            data["stato"],
            data.get("numero", ""),
            id_fornitore,
            fattura_id,
            uid
        ))

        if cur.rowcount == 0:
            return jsonify({"error": "Fattura non trovata o non autorizzata"}), 404

        conn.commit()

        row = cur.execute("""
            SELECT id, data_inserimento, fornitore, categoria, data_scadenza,
                   importo, stato, numero, id_fornitore
            FROM fatture
            WHERE id = ? AND user_id = ?
        """, (fattura_id, uid)).fetchone()

        return jsonify(dict(row)) if row else (jsonify({"error": "Errore interno"}), 500)        
        

@app.delete("/api/fatture/<int:fattura_id>") 
@require_login
@require_license
@require_csrf
def api_delete_fattura(fattura_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM fatture WHERE id=? AND user_id=?", (fattura_id, _uid()))
        if cur.rowcount == 0:
            return jsonify({"error": "Fattura non trovata o non autorizzata"}), 404
        conn.commit()
    return jsonify({"success": True})

# --- QR Code per pagamento fattura ---
@app.get("/api/fattura/<int:fid>/qr")
@require_login
@require_license
def api_fattura_qr(fid):
    uid = _uid()
    with get_db() as conn:
        # JOIN fatture + fornitori → recupero IBAN e BIC
        row = conn.execute("""
            SELECT f.id, f.fornitore, f.categoria, f.importo, f.numero, f.data_scadenza,
                   fo.iban_beneficiario AS iban, fo.bic_beneficiario AS bic
            FROM fatture f
            LEFT JOIN fornitori fo ON fo.id = f.id_fornitore AND fo.user_id = f.user_id
            WHERE f.id = ? AND f.user_id = ?
        """, (fid, uid)).fetchone()

    if not row:
        return jsonify({"error": "Fattura non trovata"}), 404

    # --- Dati per il QR ---
    importo = f"{row['importo']:.2f}"
    iban = row['iban'] or "IT00X0000000000000000000000"
    bic = row['bic'] or ""   # opzionale, può restare vuoto
    beneficiario = row['fornitore'] or "Sconosciuto"
    causale = f"Fattura {row['numero'] or row['id']} - {row['categoria'] or ''}"

    # --- Stringa EPC QR (standard europeo) ---
    sepa_string = f"""BCD
002
1
SCT
{bic}
{beneficiario}
{iban}
EUR{importo}
{causale}"""

    import qrcode, base64, io
    buf = io.BytesIO()
    qrcode.make(sepa_string.strip()).save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return jsonify({
        "ok": True,
        "id": row["id"],
        "fornitore": row["fornitore"],
        "categoria": row["categoria"],
        "numero": row["numero"],
        "importo": importo,
        "data_scadenza": row["data_scadenza"],
        "iban": iban,
        "bic": bic,
        "sepa": sepa_string.strip(),
        "qr_image": f"data:image/png;base64,{qr_b64}"
    })

@app.route("/api/spese_fatture/<int:anno>/<mese>")
@require_login
@require_license
def api_spese_fatture(anno, mese):
    try:
        user_id = _uid()
        _, mese_num = _normalize_mese(mese)
        if not mese_num:
            return jsonify({}), 400

        mapping = {
            'alimentari (food cost)': 'alimentari',
            'bevande': 'bevande',
            'utilità (luce, acqua, gas)': 'utilita',
            'manutenzioni e riparazioni': 'manutenzioni',
            'marketing e pubblicità': 'marketing',
            'licenze e assicurazioni': 'licenze',
            'commissioni (the fork)': 'commissioni',
            'lavanderia': 'lavanderia',
            'pulizia e igiene': 'pulizia',
            'spese varie': 'spese-varie',
            'varie': 'varie'
        }

        query = """
            SELECT 
                LOWER(categoria) as cat,
                SUM(importo) as totale
            FROM fatture
            WHERE 
                user_id = ? 
                AND CAST(strftime('%Y', data_inserimento) AS INTEGER) = ?
                AND CAST(strftime('%m', data_inserimento) AS INTEGER) = ?
            GROUP BY cat
        """

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(query, [user_id, anno, mese_num])
            rows = cur.fetchall()

        result = {}
        for row in rows:
            cat = row['cat']
            totale = row['totale']
            mapped_id = mapping.get(cat, 'spese-varie')
            result[mapped_id] = round(result.get(mapped_id, 0) + totale, 2)

        return jsonify(result)

    except Exception as e:
        print(f"[API SPESE_FATTURE] Errore: {e}")
        return jsonify({"error": "Internal error"}), 500

@app.get("/api/fatture_scadenze/<int:anno>")
@require_login
@require_license
def api_fatture_scadenze(anno: int):
    """
    Restituisce tutte le fatture con scadenza nell'anno richiesto
    + quelle dell'anno precedente (cross-anno).
    """
    uid = _uid()
    anno_prec = anno - 1
    with get_db() as conn:
        cur = conn.cursor()
        rows = cur.execute("""
            SELECT id, data_inserimento, fornitore, categoria,
                   data_scadenza, importo, stato, numero
            FROM fatture
            WHERE user_id = ?
              AND (
                   CAST(strftime('%Y', data_scadenza) AS INTEGER) = ?
                   OR CAST(strftime('%Y', data_scadenza) AS INTEGER) = ?
              )
            ORDER BY date(data_scadenza) ASC
        """, (uid, anno, anno_prec)).fetchall()
    return jsonify([dict(r) for r in rows])
    
# ------------------------------------------------------------------------------------------------

# === API: Incassi Annuali ===
@app.get("/api/incassi/<int:anno>/")
@require_login
@require_license
def api_incassi_annuali(anno):
    """Restituisce totali incassi mensili per l'anno specificato"""
    user_id = _uid()
    
    with get_db() as conn:
        cur = conn.cursor()
        
        # Calcola totale incassi per ogni mese
        cur.execute("""
            SELECT mese, SUM(valore) as valore 
            FROM incassi 
            WHERE user_id = ? AND anno = ?
            GROUP BY mese 
            ORDER BY CASE 
                WHEN mese = 'gennaio' THEN 1
                WHEN mese = 'febbraio' THEN 2
                WHEN mese = 'marzo' THEN 3
                WHEN mese = 'aprile' THEN 4
                WHEN mese = 'maggio' THEN 5
                WHEN mese = 'giugno' THEN 6
                WHEN mese = 'luglio' THEN 7
                WHEN mese = 'agosto' THEN 8
                WHEN mese = 'settembre' THEN 9
                WHEN mese = 'ottobre' THEN 10
                WHEN mese = 'novembre' THEN 11
                WHEN mese = 'dicembre' THEN 12
            END
        """, (user_id, anno))
        
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows])


# === API: Spese Annuali ===
@app.get("/api/spese/<int:anno>/")
@require_login
@require_license
def api_spese_annuali(anno):
    """Restituisce totali spese mensili per l'anno specificato"""
    user_id = _uid()
    
    with get_db() as conn:
        cur = conn.cursor()
        
        # Calcola totale spese fisse per ogni mese
        cur.execute("""
            SELECT mese, SUM(valore) as valore 
            FROM spese_fisse 
            WHERE user_id = ? AND anno = ?
            GROUP BY mese 
            ORDER BY CASE 
                WHEN mese = 'gennaio' THEN 1
                WHEN mese = 'febbraio' THEN 2
                WHEN mese = 'marzo' THEN 3
                WHEN mese = 'aprile' THEN 4
                WHEN mese = 'maggio' THEN 5
                WHEN mese = 'giugno' THEN 6
                WHEN mese = 'luglio' THEN 7
                WHEN mese = 'agosto' THEN 8
                WHEN mese = 'settembre' THEN 9
                WHEN mese = 'ottobre' THEN 10
                WHEN mese = 'novembre' THEN 11
                WHEN mese = 'dicembre' THEN 12
            END
        """, (user_id, anno))
        
        spese_fisse = cur.fetchall()
        
        # Calcola totale spese fatture per ogni mese
        cur.execute("""
            SELECT mese, SUM(valore) as valore 
            FROM spese_fatture 
            WHERE user_id = ? AND anno = ?
            GROUP BY mese 
            ORDER BY CASE 
                WHEN mese = 'gennaio' THEN 1
                WHEN mese = 'febbraio' THEN 2
                WHEN mese = 'marzo' THEN 3
                WHEN mese = 'aprile' THEN 4
                WHEN mese = 'maggio' THEN 5
                WHEN mese = 'giugno' THEN 6
                WHEN mese = 'luglio' THEN 7
                WHEN mese = 'agosto' THEN 8
                WHEN mese = 'settembre' THEN 9
                WHEN mese = 'ottobre' THEN 10
                WHEN mese = 'novembre' THEN 11
                WHEN mese = 'dicembre' THEN 12
            END
        """, (user_id, anno))
        
        spese_fatture = cur.fetchall()
        
        # Combina i totali per mese
        totali_mensili = {}
        
        # Aggiungi spese fisse
        for row in spese_fisse:
            mese = row['mese']
            if mese not in totali_mensili:
                totali_mensili[mese] = 0
            totali_mensili[mese] += row['valore']
        
        # Aggiungi spese fatture
        for row in spese_fatture:
            mese = row['mese']
            if mese not in totali_mensili:
                totali_mensili[mese] = 0
            totali_mensili[mese] += row['valore']
        
        # Formatta il risultato
        result = []
        ordine_mesi = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
                      'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']
        
        for mese in ordine_mesi:
            valore = totali_mensili.get(mese, 0)
            result.append({
                'mese': mese,
                'valore': valore
            })
        
        return jsonify(result)

#-------------------------------------------------------------------------------------------------

@app.post("/api/newsletter/send")
@require_login
@require_license
@require_csrf
def api_newsletter_send():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "msg": "JSON non valido"}), 400

    channel = (data.get("channel") or "email").lower().strip()
    subject = data.get("subject") or ""
    body    = (data.get("body") or "").strip()
    ids     = data.get("recipients") or []

    if not body:
        return jsonify({"ok": False, "msg": "Testo mancante"}), 400
    if channel in ("email", "entrambi") and not subject:
        return jsonify({"ok": False, "msg": "Oggetto mancante"}), 400
    if not isinstance(ids, list) or not ids:
        return jsonify({"ok": False, "msg": "Nessun destinatario"}), 400

    # --- Recupera dal DB i clienti corrispondenti ---
    try:
        db = get_db()
        placeholders = ",".join("?"*len(ids))
        cur = db.execute(
            f"SELECT id, nome, email, telefono, note FROM clienti WHERE id IN ({placeholders}) AND user_id=?",
            (*ids, session["user_id"])
        )
        recipients = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Errore DB: {e}"}), 500

    if not recipients:
        return jsonify({"ok": False, "msg": "Nessun destinatario valido"}), 400

    # --- EMAIL personalizzate + LOG ---
    email_results = []
    if channel in ("email", "entrambi"):
        try:
            prefisso = "Ciao {{nome}}, "
            items = []
            for r in recipients:
                to_email = (r.get("email") or "").strip()
                if not to_email:
                    continue
                subj_personale = _render_vars(subject, r)
                body_personale = _render_vars(prefisso + body, r)
                items.append({
                    "email": to_email,
                    "subject": subj_personale,
                    "body": body_personale
                })

            email_results = send_emails_personalized(items) if items else []

            # LOG email
            try:
                ts = datetime.now().isoformat(timespec="seconds")
                res_map = {rec.get("email"): rec for rec in (email_results or [])}
                rows = []
                for it in items:
                    rec = res_map.get(it["email"], {})
                    rows.append({
                        "ts": ts,
                        "to_email": it["email"],
                        "subject": it["subject"],
                        "body": it["body"],
                        "ok": bool(rec.get("ok")),
                        "error": rec.get("err", "")
                    })
                _log_rows(LOG_EMAIL_CSV, ["ts","to_email","subject","body","ok","error"], rows)
            except Exception as e:
                print("[LOG EMAIL ERROR]", e)

        except Exception as e:
            return jsonify({"ok": False, "msg": f"Errore SMTP: {e}"}), 500

    # --- Link WhatsApp personalizzati (wa.me) ---
    wa_links = []
    if channel in ("whatsapp", "entrambi"):
        try:
            prefisso = "Ciao {{nome}}, "
            ts = datetime.now().isoformat(timespec="seconds")
            wa_rows = []

            for r in recipients:
                tel = (r.get("telefono") or "").strip()
                if not tel:
                    continue

                testo_personale = _render_vars(prefisso + body, r)
                testo_enc = quote_plus(testo_personale)

                digits = "".join(ch for ch in tel if ch.isdigit() or ch == "+")
                if digits and not digits.startswith("+"):
                    if len(digits) >= 9:
                        digits = "+39" + digits
                wa_number = digits.lstrip("+")

                url = f"https://wa.me/{wa_number}?text={testo_enc}"
                wa_links.append({"telefono": tel, "url": url})

                wa_rows.append({
                    "ts": ts,
                    "to_phone": tel,
                    "url": url,
                    "text": testo_personale,
                    "status": "prepared"
                })

            try:
                _log_rows(LOG_WA_CSV, ["ts","to_phone","url","text","status"], wa_rows)
            except Exception as e:
                print("[LOG WA ERROR]", e)

        except Exception as e:
            return jsonify({"ok": False, "msg": f"Errore WA: {e}"}), 500

    return jsonify({
        "ok": True,
        "email_results": email_results,
        "wa_links": wa_links
    })
 
    
#=== ALTRE  PAGINE PLACEHOLDER ===
@app.route("/clienti")
@require_login
@require_license
def lista_clienti():
    return render_template("clienti.html")

@app.route("/personale")
@require_login
@require_license
def gestione_personale():
    anno = request.args.get("anno", type=int)
    if anno:
        _set_selected_year(anno)
    else:
        anno = _get_selected_year()
    return render_template("personale.html", anno=anno)


@app.route("/stipendi")
@require_login
@require_license
def stipendi():
    anno = request.args.get("anno", type=int)
    if anno:
        _set_selected_year(anno)
    else:
        anno = _get_selected_year()
    return render_template("stipendi.html", anno=anno)


@app.route("/fornitori")
@require_login
@require_license
def fornitori_page():
    return render_template("fornitori.html")

@app.route("/fatture/<int:anno>")
@require_login
@require_license
def fatture_page(anno):
    _set_selected_year(anno)  # salva l’anno in sessione
    return render_template("fatture.html", anno=anno)

# alias: se manca l’anno, lo prende dalla sessione o dal default
@app.route("/fatture")
def fatture_alias():
    anno = _get_selected_year()
    return redirect(url_for("fatture_page", anno=anno))

# --- Api -- ANNO

@app.route("/situazione-annuale/<int:anno>")
@require_login
@require_license
def situazione_annuale(anno):
    uid = _uid()
    db = get_db()
    anni = set()

    # raccogli gli anni presenti per l'utente
    for sql in (
        "SELECT DISTINCT strftime('%Y', data) y FROM incassi WHERE user_id=?",
        "SELECT DISTINCT substr(mese,1,4) y FROM spese_fisse WHERE user_id=?",
        "SELECT DISTINCT strftime('%Y', data_inserimento) y FROM fatture WHERE user_id=?",
        "SELECT DISTINCT strftime('%Y', mese) y FROM stipendi_mensili WHERE user_id=?",
    ):
        try:
            cur = db.execute(sql, (uid,))
            for r in cur.fetchall():
                y = (r[0] or "").strip()
                if y.isdigit():
                    anni.add(int(y))
        except Exception:
            pass  # tabella mancante: ignora

    if not anni:
        anni = {datetime.now().year}

    if anno not in anni:
        anno = max(anni)

    # Assicurati che l'elenco arrivi almeno fino al 2030
    current_year = datetime.now().year
    for y in range(current_year, 2031):
        anni.add(y)

    anni_disponibili = sorted(anni, reverse=True)
    return render_template("annuale.html", anno=anno, anni_disponibili=anni_disponibili)

# === API: Situazione annuale ===
@app.get("/api/annuale/<int:anno>")
@require_login
@require_license
def api_annuale(anno):
    uid = _uid()
    db = get_db()

    # Mesi in formato testuale (come salvati nel DB)
    mesi = [
        "gennaio","febbraio","marzo","aprile","maggio","giugno",
        "luglio","agosto","settembre","ottobre","novembre","dicembre"
    ]

    dati = []
    tot_inc = tot_spe = 0.0

    for m in mesi:
        # Incassi
        inc = db.execute("""
            SELECT COALESCE(SUM(valore),0)
            FROM incassi
            WHERE user_id=? AND anno=? AND mese=?
        """, (uid, anno, m)).fetchone()[0] or 0.0

        # Spese fisse
        spese_fisse = db.execute("""
            SELECT COALESCE(SUM(valore),0)
            FROM spese_fisse
            WHERE user_id=? AND anno=? AND mese=?
        """, (uid, anno, m)).fetchone()[0] or 0.0

        # Stipendi
        try:
            stipendi = db.execute("""
                SELECT COALESCE(SUM(lordo),0)
                FROM stipendi_mensili
                WHERE user_id=? AND strftime('%Y', mese)=? AND lower(strftime('%m', mese))=?
            """, (uid, str(anno), f"{mesi.index(m)+1:02d}")).fetchone()[0] or 0.0
        except Exception:
            stipendi = 0.0

        # Fatture
        fatture = db.execute("""
            SELECT COALESCE(SUM(importo),0)
            FROM fatture
            WHERE user_id=? AND strftime('%Y', data_inserimento)=? AND strftime('%m', data_inserimento)=?
        """, (uid, str(anno), f"{mesi.index(m)+1:02d}")).fetchone()[0] or 0.0

        spese = spese_fisse + stipendi + fatture
        ricavo = inc - spese
        perc = (ricavo / inc * 100.0) if inc else 0.0

        dati.append({
            "mese": m,
            "incassi": round(inc, 2),
            "spese": round(spese, 2),
            "ricavo": round(ricavo, 2),
            "incidenza": round(perc, 2)
        })

        tot_inc += inc
        tot_spe += spese

    tot_ric = tot_inc - tot_spe
    tot_incidenza = (tot_ric / tot_inc * 100.0) if tot_inc else 0.0

    return jsonify({
        "dati": dati,
        "totali": {
            "incassi": round(tot_inc, 2),
            "spese": round(tot_spe, 2),
            "ricavo": round(tot_ric, 2),
            "incidenza": round(tot_incidenza, 2)
        }
    })

# Redirect da /report verso /situazione-annuale
@app.route("/report")
@require_login
@require_license
def annual_report():
    anno = request.args.get("anno", type=int)
    if not anno:
        anno = datetime.now().year
    return redirect(url_for("situazione_annuale", anno=anno))

# --- Fine -- API -- ANNO


@app.route("/percentuali")
@require_login
@require_license
def percentuali():
    return render_template("percentuali.html")

def _empty_bank_profile():
    return SimpleNamespace(
        nome_titolare="",
        iban="",
        bic="",
        indirizzo_titolare=""
    )

def _format_iban_readable(value: str) -> str:
    cleaned = (value or "").replace(" ", "").strip()
    if not cleaned:
        return ""
    return " ".join([cleaned[i:i + 4] for i in range(0, len(cleaned), 4)]).strip()


def _load_bank_profile(user_id: int):
    profilo = _empty_bank_profile()
    error = None
    with get_db() as conn:
        row = conn.execute(
            "SELECT nome_titolare, indirizzo_titolare, iban_cipher, bic_cipher FROM profili_bancari WHERE user_id=?",
            (user_id,),
        ).fetchone()
    if not row:
        return profilo, None

    profilo.nome_titolare = (row["nome_titolare"] or "").strip()
    profilo.indirizzo_titolare = (row["indirizzo_titolare"] or "").strip()

    iban_plain = ""
    if row["iban_cipher"]:
        try:
            iban_plain = decrypt_data(row["iban_cipher"])
        except Exception as exc:
            app.logger.exception(
                "Errore durante la decifratura dell'IBAN per l'utente %s", user_id, exc_info=exc
            )
            error = "Impossibile leggere l'IBAN salvato. Reinseriscilo e salva nuovamente."
    profilo.iban = _format_iban_readable(iban_plain)

    bic_plain = ""
    if row["bic_cipher"]:
        try:
            bic_plain = decrypt_data(row["bic_cipher"])
        except Exception as exc:
            app.logger.warning(
                "Errore durante la decifratura del BIC per l'utente %s: %s", user_id, exc
            )
    profilo.bic = (bic_plain or "").strip().upper()
    return profilo, error

@app.route("/profilo-bancario")
@require_login
@require_license
def profilo_bancario():
    user_id = _uid()
    dati, decrypt_error = _load_bank_profile(user_id)
    success_msg = "Dati bancari salvati correttamente." if request.args.get("salvato") else None
    error_msg = decrypt_error
    return render_template(
        "profilo_bancario.html",
        dati=dati,
        success_msg=success_msg,
        error_msg=error_msg,
    )

@app.post("/profilo/bancario")
@require_login
@require_license
@require_csrf
def salva_profilo_bancario():
    user_id = _uid()
    nome = (request.form.get("nome_titolare") or "").strip()
    indirizzo = (request.form.get("indirizzo") or "").strip()
    iban_input = (request.form.get("iban") or "").strip()
    bic_input = (request.form.get("bic") or "").strip()

    dati = SimpleNamespace(
        nome_titolare=nome,
        indirizzo_titolare=indirizzo,
        iban=iban_input,
        bic=bic_input,
    )

    if not nome or not indirizzo or not iban_input:
        return render_template(
            "profilo_bancario.html",
            dati=dati,
            error_msg="Compila tutti i campi obbligatori.",
        ), 400

    import re

    iban_clean = re.sub(r"\s+", "", iban_input).upper()
    if len(iban_clean) < 15:
        return render_template(
            "profilo_bancario.html",
            dati=dati,
            error_msg="IBAN non valido.",
        ), 400

    bic_clean = re.sub(r"\s+", "", bic_input).upper()
    if bic_clean and not (6 <= len(bic_clean) <= 11):
        return render_template(
            "profilo_bancario.html",
            dati=dati,
            error_msg="BIC/SWIFT non valido.",
        ), 400

    try:
        iban_cipher = encrypt_data(iban_clean)
        bic_cipher = encrypt_data(bic_clean) if bic_clean else None
    except Exception as exc:
        app.logger.exception(
            "Errore nella cifratura dei dati bancari per l'utente %s", user_id, exc_info=exc
        )
        return render_template(
            "profilo_bancario.html",
            dati=dati,
            error_msg="Impossibile salvare i dati bancari in questo momento.",
        ), 500

    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO profili_bancari (user_id, nome_titolare, indirizzo_titolare, iban_cipher, bic_cipher, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                nome_titolare=excluded.nome_titolare,
                indirizzo_titolare=excluded.indirizzo_titolare,
                iban_cipher=excluded.iban_cipher,
                bic_cipher=excluded.bic_cipher,
                updated_at=excluded.updated_at
            """,
            (user_id, nome, indirizzo, iban_cipher, bic_cipher, now, now),
        )
    return redirect(url_for("profilo_bancario", salvato=1))


@app.get("/_debug/routes")
@require_admin
def _debug_routes():
    lines = [f"{r.rule}  ->  {r.endpoint}" for r in app.url_map.iter_rules()]
    return "<pre>" + "\n".join(sorted(lines)) + "</pre>"

@app.get("/_debug/boom")
@require_admin
def _debug_boom():
    raise RuntimeError("BOOM")

# --- ping "verifica-licenza" per evitare 404 rumorosi

@app.get("/verifica-licenza")
def verifica_licenza():
    if request.args.get("json") == "1":
        return jsonify(ok=True, msg="RistoSmartFM up"), 200
    return "OK", 200

@app.get("/favicon.ico")
def favicon():
    return send_file(os.path.join(app.static_folder, "logoristosmart.png"), mimetype="image/png")

@app.after_request
def add_security_headers(resp):
    p = request.path or ""

    # No-cache per pagine sensibili
    if p.startswith(("/login", "/logout", "/license", "/renew", "/admin")):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"

    # Hardening base
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    # ✅ CSP reale (self + jsDelivr). Manteniamo 'unsafe-inline' finché hai JS inline.
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "frame-ancestors 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    if request.is_secure:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return resp

@app.errorhandler(404)
def handle_404(e):
    if _wants_json() or request.path.startswith("/api/"):
        return jsonify(ok=False, error="Not found", path=request.path), 404
    return "Pagina non trovata", 404

@app.errorhandler(405)
def handle_405(e):
    if _wants_json() or request.path.startswith("/api/"):
        return jsonify(ok=False, error="Method not allowed", path=request.path), 405
    return "Metodo non consentito", 405

@app.errorhandler(500)
def handle_500(e):
    import uuid, traceback
    err_id = uuid.uuid4().hex[:8]
    app.logger.error(f"[ERR {err_id}] {request.method} {request.path}\n{traceback.format_exc()}")
    if _wants_json() or request.path.startswith("/api/"):
        return jsonify(ok=False, error="Server error", id=err_id), 500
    return f"Errore interno (ID {err_id})", 500

@app.errorhandler(413)
def handle_413(e):
    if _wants_json() or request.path.startswith("/api/"):
        return jsonify(ok=False, error="Payload troppo grande (max 2MB)"), 413
    return "Payload troppo grande (max 2MB).", 413

# route: grafico totale annuale per categorie (bar left + pie right)
from io import BytesIO
import sqlite3
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import send_file, current_app

@app.route('/report_spese_plot/<int:anno>')
def report_spese_plot(anno):
    try:
        db_path = globals().get('DB_PATH') or globals().get('DBFILE') or 'ristosmart.db'
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # 1) spese fisse (somma anno)
        cur.execute("SELECT SUM(valore) FROM spese_fisse WHERE anno = ?", (int(anno),))
        tot_fisse = float(cur.fetchone()[0] or 0.0)

        # 2) spese_fatture (somma anno)
        cur.execute("SELECT SUM(valore) FROM spese_fatture WHERE anno = ?", (int(anno),))
        tot_spese_fatture = float(cur.fetchone()[0] or 0.0)

        # 3) fatture importo (somma per anno dalla data)
        cur.execute("SELECT SUM(importo) FROM fatture WHERE strftime('%Y', data_inserimento) = ?", (str(anno),))
        tot_fatture_importo = float(cur.fetchone()[0] or 0.0)

        # unisco le due sorgenti invoice-like
        tot_fatture = tot_spese_fatture + tot_fatture_importo

        # 4) personale: somma (netto + contributi)
        # ASSUNZIONE: i valori in 'personale' sono mensili -> moltiplico per 12 per ottenere annuo
        cur.execute("SELECT SUM(COALESCE(netto,0) + COALESCE(contributi,0)) FROM personale")
        personale_mensile_sum = float(cur.fetchone()[0] or 0.0)
        tot_personale = personale_mensile_sum * 12.0

        conn.close()

        # prepara dati per grafico (tre categorie)
        labels = ['Spese fisse', 'Personale (annuo)', 'Spese fatture']
        values = [tot_fisse, tot_personale, tot_fatture]

        # evita torta vuota
        if sum(values) == 0:
            values = [1.0, 0.0, 0.0]

        # subplot 1x2 (bar + pie), sharey=True per allineare l'altezza dei plot
        fig, (ax_bar, ax_pie) = plt.subplots(1, 2, figsize=(12,5), sharey=True)
        fig.patch.set_facecolor('white')

        # barre (sinistra)
        colors = ['#4e79a7','#59a14f','#f28e2c']
        ax_bar.bar(labels, values, color=colors, edgecolor='none')
        ax_bar.set_title(f"Costi annuali per categoria — {anno}")
        ax_bar.set_ylabel("€")
        ax_bar.tick_params(axis='x', rotation=15)
        ax_bar.grid(axis='y', linestyle='--', alpha=0.25)

        # torta (destra)
        ax_pie.pie(values, labels=labels, autopct=lambda p: f"{p:.1f}%" if p>0 else '', colors=colors, textprops={'fontsize':9})
        ax_pie.set_title("Distribuzione")

        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return send_file(buf, mimetype='image/png')

    except Exception:
        current_app.logger.exception("Errore generazione plot spese")
        return ("", 500)

from datetime import datetime, date
import sqlite3

DB_PATH = r"C:\RISTO\data\ristosmart.db"

def rigenera_stipendi_tutti():
    """Rigenera gli stipendi mensili di tutti i dipendenti in base a personale"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # Svuota stipendi_personale per rigenerare da zero
        cur.execute("DELETE FROM stipendi_personale")

        # Recupera tutti i dipendenti
        cur.execute("SELECT * FROM personale")
        dipendenti = cur.fetchall()

        for d in dipendenti:
            dip_id = d["id"]
            user_id = d["user_id"]
            lordo = d["lordo"] or 0.0
            rapporto = (d["rapporto"] or "").lower()
            data_assunzione = d["data_assunzione"]
            data_fine = d["data_fine"]

            # Data inizio (default oggi se nulla)
            if data_assunzione:
                start = datetime.strptime(data_assunzione, "%Y-%m-%d").date()
            else:
                start = date.today()

            # Data fine (se indeterminato → 2030-12-31)
            if rapporto == "indeterminato" or not data_fine:
                end = date(2030, 12, 31)
            else:
                end = datetime.strptime(data_fine, "%Y-%m-%d").date()

            # Genera mensilmente
            year, month = start.year, start.month
            while (year < end.year) or (year == end.year and month <= end.month):
                netto = round(lordo * 0.77, 2)        # esempio: 23% contributi
                contributi = round(lordo - netto, 2)
                totale = lordo

                cur.execute("""
                    INSERT INTO stipendi_personale
                    (user_id, personale_id, anno, mese, lordo, netto, contributi, totale, stato_pagamento)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'non_pagato')
                """, (user_id, dip_id, year, month, lordo, netto, contributi, totale))

                # Passa al mese successivo
                month += 1
                if month > 12:
                    month = 1
                    year += 1

        conn.commit()
        print("Rigenerazione stipendi completata.")
    finally:
        conn.close()

# --- one-off migration: indice unico per upsert stipendi ---
try:
    with get_db() as conn:
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_stipendi_personale
            ON stipendi_personale(user_id, personale_id, anno, mese)
        """)
except Exception as e:
    app.logger.warning(f"ux_stipendi_personale non creato: {e}")

        
# === MAIN ===
if __name__ == "__main__":
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.run(debug=False)