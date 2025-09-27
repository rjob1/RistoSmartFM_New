import sqlite3
from pathlib import Path

# Percorso al DB (usa lo stesso che hai in app.config["DB_PATH"])
DB_PATH = r"C:\Users\Fio\OneDrive\Desktop\RistoSmartFM_New\ristosmart.db"

def ensure_userid_column(table: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Controlla colonne esistenti
    cur.execute(f"PRAGMA table_info({table})")
    cols = [c[1].lower() for c in cur.fetchall()]
    if "user_id" not in cols:
        print(f"➕ Aggiungo user_id a {table}...")
        cur.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)")
        con.commit()
    else:
        print(f"✔ {table} già ha user_id")
    con.close()

if __name__ == "__main__":
    # Controlliamo SOLO le tabelle che potrebbero mancare
    for t in ["fornitori", "personale", "fatture"]:
        ensure_userid_column(t)

    print("✅ Controllo completato.")
