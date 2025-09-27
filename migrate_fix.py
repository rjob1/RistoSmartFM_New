# migrate_fix.py  — adozione dati orfani + normalizzazione mesi
import sqlite3

DB = r"C:\Users\Fio\OneDrive\Desktop\RistoSmartFM_New\ristosmart.db"
ADMIN_EMAIL = "ristoconsulenze@gmail.com"

map_mese = {
    '1':'gennaio','01':'gennaio',
    '2':'febbraio','02':'febbraio',
    '3':'marzo','03':'marzo',
    '4':'aprile','04':'aprile',
    '5':'maggio','05':'maggio',
    '6':'giugno','06':'giugno',
    '7':'luglio','07':'luglio',
    '8':'agosto','08':'agosto',
    '9':'settembre','09':'settembre',
    '10':'ottobre','11':'novembre','12':'dicembre'
}
mesi_it = {'gennaio','febbraio','marzo','aprile','maggio','giugno',
           'luglio','agosto','settembre','ottobre','novembre','dicembre'}

def table_has_column(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1].lower()==col.lower() for r in cur.fetchall())

def adopt_orphans(cur, table, uid):
    if not table_has_column(cur, table, "user_id"):
        print(f"[WARN] {table}: nessuna colonna user_id → salto.")
        return 0
    n = cur.execute(
        f"""UPDATE {table}
               SET user_id=?
             WHERE user_id IS NULL OR TRIM(CAST(user_id AS TEXT)) IN ('','0')""",
        (uid,)
    ).rowcount
    print(f"[OK] {table}: adottati {n} record orfani (user_id impostato a {uid})")
    return n

def normalize_months(cur, table):
    if not table_has_column(cur, table, "mese"):
        print(f"[WARN] {table}: nessuna colonna mese → salto.")
        return
    # numerico → testuale
    for k,v in map_mese.items():
        cur.execute(f"UPDATE {table} SET mese=? WHERE TRIM(LOWER(mese))=?", (v, k))
    # testuale maiuscolo/misto → minuscolo canonico
    for v in mesi_it:
        cur.execute(f"UPDATE {table} SET mese=? WHERE LOWER(mese)=?", (v, v))
    # conteggio diagnostico
    bad = cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE LOWER(mese) NOT IN ({','.join('?'*12)})",
        tuple(mesi_it)
    ).fetchone()[0]
    if bad:
        print(f"[WARN] {table}: {bad} righe con 'mese' non canonico")
    else:
        print(f"[OK] {table}: mesi normalizzati")

def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys=ON")

    # — UID amministratore (fallback al primo utente se non trovato)
    row = cur.execute(
        "SELECT id FROM utenti WHERE lower(email)=lower(?)",
        (ADMIN_EMAIL,)
    ).fetchone()
    if not row:
        print(f"[WARN] Admin {ADMIN_EMAIL} non trovato. Uso il primo utente disponibile.")
        row = cur.execute("SELECT id FROM utenti ORDER BY id ASC LIMIT 1").fetchone()
        if not row:
            raise SystemExit("Nessun utente in tabella 'utenti'. Interrompo.")
    UID = int(row[0])
    print(f"UID admin usato: {UID}")

    # — Adozione orfani
    adopt_orphans(cur, "incassi", UID)
    adopt_orphans(cur, "spese_fisse", UID)

    # — Normalizza mesi
    normalize_months(cur, "incassi")
    normalize_months(cur, "spese_fisse")

    con.commit()

    # — Piccola verifica: mostra qualche riga di settembre 2025
    rows = cur.execute("""
        SELECT anno, mese, giorno, valore
          FROM incassi
         WHERE user_id=? AND anno=2025 AND LOWER(mese)='settembre'
         ORDER BY giorno
         LIMIT 10
    """, (UID,)).fetchall()
    print(f"Esempio incassi 2025/settembre ({len(rows)} righe, max 10 mostrate):")
    for r in rows:
        print(dict(r))

    con.close()
    print("Migrazione completata con successo.")

if __name__ == "__main__":
    main()
