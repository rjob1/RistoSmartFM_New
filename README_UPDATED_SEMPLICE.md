# RistoSmartFM

Gestionale leggero per ristoranti — **Flask + SQLite**. Versione *multi-tenant* con licenze.

---

## 👤 Ruolo & Stile
- Ingegneria: Flask (Python 3.12), UI Bootstrap 5 + Jinja2  
- Modifiche **chirurgiche**: non rompere ciò che funziona; patch mirate  
- Commit/issue **sintetici**: una cosa alla volta, chiaro e verificabile

---

## 🧰 Stack & Avvio
- **Backend:** Flask (Python 3.12), **SQLite** (file singolo)  
- **Frontend:** Jinja2 + Bootstrap 5  
- **Dev run:** `python app.py` (porta 5000)  
- **Percorso DB (dev):**  
  `app.config["DB_PATH"] = C:\Users\Fio\OneDrive\Desktop\RistoSmartFM_New\ristosmart.db`  
- **Prod:** percorso via env; backup pianificati

---

## 🔒 IMPORTANTE — SICUREZZA DATI (NON NEGOZIABILE)
**Isolamento totale per utente (multi-tenant):**
- **OGNI TABELLA** ha `user_id` **NOT NULL**  
- **OGNI QUERY** che legge/scrive **filtra per `_uid()`** (mai fidarsi di `user_id` dal client)  
- Nessun utente può vedere/scrivere dati di un altro

**Vincoli consigliati:**
- Chiavi composte con `user_id` (es. `UNIQUE(user_id, personale_id, anno, mese)`)  
- FK: tabelle figlie puntano al padre **con lo stesso `user_id`**  
- API mutate: **CSRF obbligatorio**, sessione valida, licenza valida  
- **Da evitare:** join senza `... AND p.user_id = sp.user_id`, select senza `WHERE user_id=?`  
- **Gate PR:** rifiutare qualsiasi patch che infrange uno di questi punti

---

## 🔑 Licenze (blocco accesso)
- Flusso: Registrazione/Login → Attivazione licenza → Accesso  
- **Scadenza = blocco immediato**  
- Admin: genera, invia, revoca, rinnova  
- **Mai disattivare** i controlli licenza

---

## 🔧 Variabili d’ambiente
- `FLASK_SECRET_KEY`  
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`  
- `ADMIN_EMAIL`  
- Opz.: `RENEW_URL` (default `http://127.0.0.1:5000/license`)  
- Opz. backup: `BACKUP_MAX_COUNT`, `BACKUP_MAX_AGE_DAYS`

### Hardening
- `MAX_CONTENT_LENGTH = 2 MB`  
- Cookie: `HttpOnly`, `SameSite=Lax`, `Secure` su HTTPS  
- Anti-CSRF su form e API mutate  
- Security headers + CSP (Report-Only)

---

## 🗄️ Database (multi-tenant)
Tabelle principali: `utenti`, `licenze`, `clienti`, `incassi`, `spese_fisse`, `fatture`, `personale`, `stipendi_personale` …

### `stipendi_personale` (chiave & stato)
- **Colonne:** `user_id`, `personale_id`, `anno`, `mese` *(INTEGER 1..12)*, `lordo`, `netto`, `contributi`, `totale`, `stato_pagamento` *(pagato/non_pagato)*
- **Vincoli:**
  - `CHECK(mese BETWEEN 1 AND 12)`
  - `UNIQUE(user_id, personale_id, anno, mese)`
  - FK su `personale(user_id, id)`

---

## 📄 Pagine chiuse (stabili)
- `/clienti`  
- `/mese`  
- `/base.html`  
- `/fornitori`  
- `/fatture` *(QR SEPA testato; blocco doppio pagamento)*  
- `/annuale.html`  
- `/personale.html` *(CRUD completo, campi Assunzione/Rapporto/Fine)* — **CHIUSA DEFINITIVAMENTE (no ulteriori modifiche)**

**⚠️ WIP:** `percentuali.html`

---

## 💾 Backup
- Pulsante → ZIP in `C:\RISTO\BACKUP`  
- Retention via `BACKUP_MAX_COUNT` / `BACKUP_MAX_AGE_DAYS`

---

## 💸 Stipendi
### Stato attuale (`stipendi.html`)
- **UI OK**: full-width responsivo; popup QR centrato e chiudibile (lock scroll); pulsante **Pagato** verde acceso persistente; importi verdi e **readonly** dopo conferma; placeholder **“Lordo / Contributi / Netto”** al posto di `0.00`.  
- Conferma eliminazione **a doppio step** (due modali).  
- **Persistenza attuale:** dati su **LocalStorage** lato client; API server pronte per integrazione DB.

### API Stipendi (tutte filtrate per `_uid()`; mutate con CSRF)
- `GET  /api/stipendi/dettaglio/<anno>` → dettaglio per dipendente/mese (fonte server)  
- `PUT  /api/stipendi/<personale_id>` → aggiornamento mesi (normalizzare `mese` a INT `1..12`)  
- `GET  /api/stipendi/<anno>/<mese>` → aggregato mese per ruolo  
- `GET  /api/stipendi/<int:anno>` → aggregato annuale  
- `POST /api/stipendi/<personale_id>/qr` → QR SEPA  
- `DELETE /api/stipendi` → pulizia dati utente corrente (dev/testing)

### Invarianti (non negoziabili)
- **Mai** scrivere `mese` come testo nel DB; **sempre INT 1..12**  
- Join sempre con `AND p.user_id = sp.user_id`  
- Nessuna rotta che esponga dati senza `user_id = _uid()`

---

## 📱 Pagamento Fatture via QR Code
- IBAN/BIC da tabella fornitori  
- `GET /api/fattura/<id>/qr`  
- Popup con **Conferma pagamento** → stato “Pagato”, blocco bottone, sync DB/LS

---

## 🧭 Git & GitHub — Guida pratica

### 0) `.gitignore` minimo
Crea/aggiorna `.gitignore` con:
venv/
pycache/
*.pyc
*.pyo
*.pyd
*.db
.sqlite
backup/
*.zip
.env
.flaskenv
*.log
.DS_Store

csharp
Copia codice

> Se alcuni di questi sono già tracciati, vedi “Rimuovere file già tracciati”.

### 1) Configurazione Git (una volta per PC)
```powershell
git config --global user.name  "Il Tuo Nome"
git config --global user.email "tua-email@esempio.it"
git config --global core.autocrlf true   # consigliato su Windows
2) Crea il repo su GitHub (una volta)
Vai su GitHub → New

Nome: RistoSmartFM_New (o quello che usi)

Lascia NON spuntati: Add a README, Add .gitignore, Choose a license

Create repository

Nella pagina del repo: Code → HTTPS → copia l’URL che finisce con .git (es. https://github.com/tuoutente/RistoSmartFM_New.git)

3) Collega il progetto locale e fai il primo push
powershell
Copia codice
# nella cartella del progetto
git init
git add .
git commit -m "init: progetto pulito (ignora venv/DB/segreti)"
git branch -M main
git remote add origin "https://github.com/tuoutente/RistoSmartFM_New.git"
git push -u origin main
4) Flusso quotidiano
powershell
Copia codice
git pull --rebase origin main   # aggiornati prima
git add -A
git commit -m "descrizione chiara"
git push
5) Nuova funzionalità su branch
powershell
Copia codice
git checkout -b feature/nome-funzionalita
# lavori...
git add -A
git commit -m "implementa nome-funzionalita"
git push -u origin feature/nome-funzionalita
Poi apri una Pull Request su GitHub verso main.

6) Clonare su un altro PC
bash
Copia codice
git clone https://github.com/tuoutente/RistoSmartFM_New.git
cd RistoSmartFM_New
python -m venv venv
# Windows:
.\venv\Scripts\activate
pip install -r requirements.txt
7) Rimuovere file già tracciati (ora ignorati)
powershell
Copia codice
git rm -r --cached venv backup *.db *.sqlite* *.zip .env .flaskenv
git commit -m "gitignore: rimuovi artefatti/DB/segreti dal tracking"
git push
8) Remote esistente / Cambiare URL
powershell
Copia codice
git remote -v
git remote set-url origin "https://github.com/tuoutente/RistoSmartFM_New.git"
9) Errori comuni (fix rapidi)
Author identity unknown
Configura nome/email (vedi punto 1).

src refspec main does not match any
Fai almeno un commit prima del push: git add . && git commit -m "first commit".

origin already exists
Usa git remote set-url origin "<nuovo-URL>.git".

Avvisi CRLF/LF su Windows
git config --global core.autocrlf true.

✅ TODO / Next Steps
PRIORITÀ: integrazione completa salvataggio Stipendi su DB

Normalizzare mese → INT 1..12 lato server

ON CONFLICT (user_id, personale_id, anno, mese) → UPDATE

Verifica join multi-tenant (... AND p.user_id = sp.user_id)

Test incognito: fonte verità = DB

percentuali.html

Decimali server (virgola/punto) coerenti con front-end

Collegare stipendi all’annuale (totali per ruolo/mese)

🧪 Checklist PR (Sicurezza & Qualità)
 Ogni SELECT/UPDATE/DELETE filtra user_id = _uid()

 Nessun user_id accettato/derivato dal client

 mese normalizzato 1..12 prima del DB

 Mutazioni: @require_csrf, @require_login, @require_license

 Join multi-tenant: ... AND <tabA>.user_id = <tabB>.user_id

 Test rapido su browser (normale/incognito) con DB come fonte verità

 Migrazioni schema: vincoli/indici preservati

🔌 Script utili (DEV)
Svuota LocalStorage (console browser):

js
Copia codice
localStorage.removeItem("STIPENDI_DETTAGLIO");
localStorage.removeItem("STIPENDI_AGGREGATO");
localStorage.removeItem("stipendi_update_trigger");
console.log("✅ LocalStorage stipendi pulito");