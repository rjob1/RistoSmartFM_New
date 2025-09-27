# audit_and_rebind.py
import sqlite3

DB = r"C:\Users\Fio\OneDrive\Desktop\RistoSmartFM_New\ristosmart.db"
ADMIN_EMAIL = "ristoconsulenze@gmail.com"

# === MODALITÀ ===
# Di default SOLO AUDIT (non modifica nulla).
# Per provare a rilegare SOLO un mese/anno, imposta qui i filtri e REASSIGN=True.
REASSIGN = False                # <<< metti True solo quando vuoi applicare
FILTER_ANNO = None              # es. 2025 oppure None
FILTER_MESE = None              # es. "settembre" (minuscolo) oppure None

def q(cur, sql, *args):
    cur.execute(sql, args)
    return cur.fetchall()

def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys=ON")

    # 1) Trova UID admin
    row = cur.execute(
        "SELECT id,email FROM utenti WHERE lower(email)=lower(?)",
        (ADMIN_EMAIL,)
    ).fetchone()
    if not row:
        raise SystemExit(f"Admin {ADMIN_EMAIL} non trovato in 'utenti'")
    UID = int(row["id"])
    print(f"UID admin: {UID}  ({row['email']})")

    # 2) AUDIT: distribuzione incassi / spese_fisse per user_id
    print("\n=== Distribuzione INCASSI per user_id ===")
    rows = q(cur, "SELECT user_id, COUNT(*) AS n FROM incassi GROUP BY user_id ORDER BY n DESC")
    for r in rows:
        uemail = cur.execute("SELECT email FROM utenti WHERE id=?", (r["user_id"],)).fetchone()
        mail = (uemail["email"] if uemail else "—")
        print(f"user_id={r['user_id']:>3}  righe={r['n']:>5}   email={mail}")

    print("\n=== Distribuzione SPESE_FISSE per user_id ===")
    rows = q(cur, "SELECT user_id, COUNT(*) AS n FROM spese_fisse GROUP BY user_id ORDER BY n DESC")
    for r in rows:
        uemail = cur.execute("SELECT email FROM utenti WHERE id=?", (r["user_id"],)).fetchone()
        mail = (uemail["email"] if uemail else "—")
        print(f"user_id={r['user_id']:>3}  righe={r['n']:>5}   email={mail}")

    # 3) Esempi: righe di settembre 2025 NON del tuo UID (se esistono)
    print("\n=== Esempi INCASSI 2025/settembre con user_id != admin ===")
    rows = q(cur, """
        SELECT user_id, anno, mese, giorno, valore
          FROM incassi
         WHERE anno=2025 AND lower(mese)='settembre' AND user_id <> ?
         ORDER BY user_id, giorno
         LIMIT 20
    """, UID)
    if rows:
        for r in rows:
            print(dict(r))
    else:
        print("(nessuna riga trovata)")

    # 4) Rebind (opzionale)
    if not REASSIGN:
        print("\n[SOLO AUDIT] Nessuna modifica applicata. Imposta REASSIGN=True per rilegare.")
        con.close()
        return

    where_extra = []
    args_inc = [UID, UID]
    args_sp  = [UID, UID]

    if FILTER_ANNO is not None:
        where_extra.append("AND anno=?")
        args_inc.append(FILTER_ANNO)
        args_sp.append(FILTER_ANNO)
    if FILTER_MESE is not None:
        where_extra.append("AND lower(mese)=lower(?)")
        args_inc.append(FILTER_MESE)
        args_sp.append(FILTER_MESE)

    where = " ".join(where_extra)

    # Contatori prima del cambio
    cnt_inc = cur.execute(f"SELECT COUNT(*) FROM incassi WHERE user_id<>? {where}", tuple(args_inc[1:])).fetchone()[0]
    cnt_sp  = cur.execute(f"SELECT COUNT(*) FROM spese_fisse WHERE user_id<>? {where}", tuple(args_sp[1:])).fetchone()[0]
    print(f"\n[REASSIGN] Candidati da rilegare → incassi: {cnt_inc}, spese_fisse: {cnt_sp}")

    # Applica
    n1 = cur.execute(f"""
        UPDATE incassi
           SET user_id=?
         WHERE user_id<>? {where}
    """, tuple(args_inc)).rowcount
    n2 = cur.execute(f"""
        UPDATE spese_fisse
           SET user_id=?
         WHERE user_id<>? {where}
    """, tuple(args_sp)).rowcount
    con.commit()
    print(f"[REASSIGN] Aggiornati → incassi: {n1}, spese_fisse: {n2}")

    con.close()
    print("Fatto.")

if __name__ == "__main__":
    main()
