# RistoSmartFM

Gestionale leggero per ristoranti — **Flask + SQLite**.  
Versione *multi-tenant* con licenze.

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

## 🔒 Sicurezza dati (non negoziabile)
**Isolamento totale per utente (multi-tenant):**
- **OGNI TABELLA** ha `user_id NOT NULL`  
- **OGNI QUERY** filtra per `_uid()`  
- Nessun utente può vedere o scrivere dati di un altro

**Vincoli consigliati:**
- Chiavi composte con `user_id`  
- FK: tabelle figlie puntano al padre con lo stesso `user_id`  
- API mutate: **CSRF obbligatorio**, sessione valida, licenza valida  
- Vietato: join senza `... AND p.user_id = sp.user_id`, select senza `WHERE user_id=?`

---

## 🔑 Licenze
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
Tabelle principali:  
`utenti`, `licenze`, `clienti`, `incassi`, `spese_fisse`, `fatture`, `personale`, `stipendi_personale`, `tasse` …

### `stipendi_personale`
- **Colonne:** `user_id`, `personale_id`, `anno`, `mese`, `lordo`, `netto`, `contributi`, `totale`, `stato_pagamento`  
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
- `/personale.html` *(CRUD completo)*  
- `/stipendi.html` *(CRUD, QR, pagamenti, DB sync)*  
- `/tasse.html` *(completata con enti.json e tooltip)*  
- `/pagamento-tasse.html` *(flusso completo: inserimento, QR SEPA, conferma, stato persistente, localStorage sync)*

> ✅ **AVVISO LEGALE DI PROGETTO**  
> I template **`tasse.html`** e **`pagamento-tasse.html`** sono ora **definitivamente chiusi e stabili**.  
> Ogni modifica futura a questi file **richiede espressamente il consenso scritto del proprietario del progetto**.  
> Questo per garantire coerenza, sicurezza e affidabilità del flusso di pagamento tasse.

---

## 💾 Backup
- Pulsante → ZIP in `C:\RISTO\BACKUP`  
- Retention via `BACKUP_MAX_COUNT` / `BACKUP_MAX_AGE_DAYS`

---

## 💸 Stipendi
- UI con pulsanti “Pagato” persistenti e placeholder “Lordo/Contributi/Netto”  
- Conferma eliminazione a doppio step  
- Persistenza: DB + LocalStorage  
- QR SEPA testato con banca reale  

---

## 📱 Pagamento Fatture via QR Code
- IBAN/BIC da tabella fornitori  
- API: `GET /api/fattura/<id>/qr`  
- Popup con conferma → stato “Pagato” sync DB/LS

---

## 🧭 Git & GitHub
1. `.gitignore` → ignora venv, cache, DB, backup, segreti  
2. `git init && git add . && git commit`  
3. `git remote add origin <URL>` + `git push -u origin main`  
4. Flusso: `pull --rebase`, `add -A`, `commit`, `push`  
5. Branch feature → PR → merge  
6. Clonare su altro PC → `git clone` + `pip install -r requirements.txt`  
7. Rimuovere file già tracciati → `git rm -r --cached ...`  
8. Cambiare URL → `git remote set-url origin <URL>`

---

## ✅ TODO / Next Steps
- [ ] `percentuali.html`  
- [ ] Integrazione completa stipendi → annuale (totali per ruolo/mese)  
- [ ] Uniformare gestione decimali tra frontend e backend  
- [ ] Report mensile esportabile (PDF/CSV)

---

## 🧪 Checklist PR
- [x] Ogni query filtra `user_id = _uid()`  
- [x] Nessun `user_id` accettato dal client  
- [x] `mese` normalizzato `1..12`  
- [x] Mutazioni: `@require_csrf`, `@require_login`, `@require_license`  
- [x] Join multi-tenant sempre presenti  
- [x] Test su browser incognito con DB come fonte verità  
- [x] Migrazioni schema con vincoli/indici preservati