# reset_admin_pw.py
import sqlite3
from werkzeug.security import generate_password_hash

DB = r"C:\Users\Fio\OneDrive\Desktop\RistoSmartFM_New\ristosmart.db"
EMAIL = "ristoconsulenze@gmail.com"
NEW_PW = "Tripp0709!"  # puoi cambiarla qui

con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("PRAGMA foreign_keys=ON")

cur.execute("SELECT id FROM utenti WHERE lower(email)=lower(?)", (EMAIL,))
row = cur.fetchone()

if not row:
    # se non esiste, crealo come admin
    cur.execute("""
        INSERT INTO utenti (nome,cognome,email,password_hash,newsletter_opt_in,ruolo)
        VALUES (?,?,?,?,?,?)
    """, ("Admin","RSFM", EMAIL, generate_password_hash(NEW_PW), 0, "admin"))
    print("Creato nuovo utente admin:", EMAIL)
else:
    # se esiste, aggiorna password e ruolo
    cur.execute("""
        UPDATE utenti
           SET password_hash=?, ruolo='admin'
         WHERE lower(email)=lower(?)
    """, (generate_password_hash(NEW_PW), EMAIL))
    print("Password aggiornata per:", EMAIL)

con.commit()
con.close()
print("OK.")
