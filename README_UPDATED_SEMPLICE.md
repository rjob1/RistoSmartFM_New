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
- `/personale.html` *(CRUD completo, campi Assunzione/Rapporto/Fine)*

**⚠️ WIP:** `percentuali.html`

---

## 💾 Backup
- Pulsante → ZIP in `C:\RISTO\BACKUP`  
- Retention via `BACKUP_MAX_COUNT` / `BACKUP_MAX_AGE_DAYS`

---

## 💸 Stipendi
### Stato attuale (`stipendi.html`)
- **UI OK**: full-width responsivo; popup QR centrato e chiudibile (lock scroll); pulsante **Pagato** verde acceso persistente; importi verdi e **readonly** dopo conferma; placeholder **“Lordo / Contributi / Netto”** al posto di `0.00`.
- **Persistenza attuale: SOLO LocalStorage. _NON_ salva in DB.**  
  In modalità **incognito** i dati stipendi possono non comparire (comportamento atteso del browser perché la fonte attuale è LS).

### API Stipendi (tutte filtrate per `_uid()`; mutate con CSRF)
- `GET  /api/stipendi/dettaglio/<anno>` → **OK** (dettaglio per dipendente/mese — fonte server)
- `PUT  /api/stipendi/<personale_id>` → **DA FIXARE** (write path non operativo: **normalizzare `mese` a INT `1..12`** prima di INSERT/UPDATE)
- `GET  /api/stipendi/<anno>/<mese>` → **OK** (aggregato mese per ruolo)
- `GET  /api/stipendi/<int:anno>` → **OK** (aggregato annuale)
- `POST /api/stipendi/<personale_id>/qr` → **OK** (QR SEPA)
- `DELETE /api/stipendi` → **OK** (pulizia dati utente corrente – dev/testing)

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

## ✅ TODO / Next Steps
- **PRIORITÀ:** ripristinare **salvataggio in DB** per stipendi
  - Normalizzare `mese` → **INT `1..12`** lato server
  - `ON CONFLICT (user_id, personale_id, anno, mese)` → `UPDATE`
  - Verificare join multi-tenant: `... AND p.user_id = sp.user_id`
  - Test cross-browser (normale/incognito): **fonte verità = DB**
- `percentuali.html` (nuova)  
- Pulizia profilo bancario utente (superfluo con QR)  
- Decimali: parsing virgola/punto ovunque (coerente lato server)  
- Collegare stipendi all’annuale (totali per ruolo/mese)  
- Test end-to-end multi-tenant: fixture con utenti A/B che **non si vedono mai**

---

## 🧪 Checklist PR (Sicurezza & Qualità)
- [ ] Ogni SELECT/UPDATE/DELETE filtra `user_id = _uid()`  
- [ ] Nessun `user_id` accettato/derivato dal client  
- [ ] `mese` normalizzato `1..12` **prima** del DB  
- [ ] Mutazioni: `@require_csrf`, `@require_login`, `@require_license`  
- [ ] Join multi-tenant: `... AND <tabA>.user_id = <tabB>.user_id`  
- [ ] Test rapido su browser: normale/incognito (DB fonte verità)  
- [ ] Migrazioni schema: vincoli/indici preservati

---

## 🔌 Script utili (DEV)
**Svuota LocalStorage** (console browser):
```js
localStorage.removeItem("STIPENDI_DETTAGLIO");
localStorage.removeItem("STIPENDI_AGGREGATO");
localStorage.removeItem("stipendi_update_trigger");
console.log("✅ LocalStorage stipendi pulito");

curl -X DELETE http://127.0.0.1:5000/api/stipendi \
  -H "Cookie: session=<tua-sessione>" \
  -H "X-CSRFToken: <token>"
