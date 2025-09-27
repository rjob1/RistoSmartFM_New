# reset_db_zero.py  —  AZZERA i dati applicativi mantenendo il tuo utente admin
# - Cancella: incassi, spese_fisse, clienti, licenze
# - Mantiene/crea l'admin e (opz.) resetta la sua password
# - Reimposta gli AUTOINCREMENT e fa VACUUM

import sqlite3
from werkzeug.security import generate_password_hash

DB = r"C:\Users\Fio\OneDrive\Desktop\RistoSmartFM_New\ristosmart.db"

ADMIN_EMAIL = "ristoconsulenze@gmail.com"
ADMIN_NOME  = "Admin"
ADMIN_COGNOME = "RistoSmart"
RESET_ADMIN_PASSWORD = True
NEW_ADMIN_PW = "Admin-Temp!2025"   # modifica se vuoi

TABLES_TO_WIPE = ["incassi", "spese_fisse", "clienti", "licenze"]

def rc(cur, table):
    return cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
cur.execute("PRAGMA foreign_keys=ON")

# --- assicurati che l'admin esista
row = cur.execute("SELECT id, email FROM utenti WHERE lower(email)=lower(?)", (ADMIN_EMAIL,)).fetchone()
if not row:
    cur.execute("""
        INSERT INTO utenti (nome, cognome, email, password_hash, newsletter_opt_in, ruolo)
        VALUES (?, ?, ?, ?, 0, 'admin')
    """, (ADMIN_NOME, ADMIN_COGNOME, ADMIN_EMAIL.lower(), generate_password_hash(NEW_ADMIN_PW)))
    con.commit()
    row = cur.execute("SELECT id, email FROM utenti WHERE lower(email)=lower(?)", (ADMIN_EMAIL,)).fetchone()
    print(f"[INFO] Creato admin {ADMIN_EMAIL} con password temporanea: {NEW_ADMIN_PW}")

ADMIN_ID = row["id"]

# --- (opz) reset password admin anche se esiste già
if RESET_ADMIN_PASSWORD:
    cur.execute("UPDATE utenti SET password_hash=? WHERE id=?", (generate_password_hash(NEW_ADMIN_PW), ADMIN_ID))
    print(f"[INFO] Password admin reimpostata a: {NEW_ADMIN_PW}")

# --- cancella TUTTI i dati applicativi
before = {t: rc(cur, t) for t in TABLES_TO_WIPE}
for t in TABLES_TO_WIPE:
    cur.execute(f"DELETE FROM {t}")

# --- elimina eventuali altri utenti (tieni solo admin)
cur.execute("DELETE FROM utenti WHERE id<>?", (ADMIN_ID,))

# --- reset AUTOINCREMENT
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
if cur.fetchone():
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN (%s)" % ",".join("?"* (len(TABLES_TO_WIPE)+1)),
                (*TABLES_TO_WIPE, "utenti"))

con.commit()

# --- VACUUM per compattare
try:
    cur.execute("VACUUM")
except Exception:
    pass
con.commit()
con.close()

print("\n=== RIEPILOGO ===")
for t in TABLES_TO_WIPE:
    print(f"{t:12s}: {before[t]:5d} -> {0:5d}")
print(f"utenti      :      ? ->   1   (solo admin {ADMIN_EMAIL})")
print("\nFatto. Puoi riavviare Flask e fare login con l'admin.")
