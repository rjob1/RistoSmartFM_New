# RistoSmartFM

Gestionale leggero per ristoranti — **Flask + SQLite**  
Versione *multi-tenant* con licenze.

📂 **Percorso progetto:**  
`C:\Users\Fio\OneDrive\Desktop\0001_NUOVO_RISTO_3_OTTOBRE\RistoSmartFM_New`

---

## 👤 Ruolo & Stile
- Ingegneria: Flask (Python 3.12), UI Bootstrap 5 + Jinja2  
- Modifiche **chirurgiche**: non rompere ciò che funziona  
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
- Ogni tabella ha `user_id NOT NULL`
- Tutte le query filtrano con `_uid()`
- Nessun utente può accedere ai dati di un altro

**Vincoli consigliati:**
- Chiavi composte con `user_id`
- FK: tabelle figlie puntano al padre con lo stesso `user_id`
- API mutate: `CSRF` obbligatorio + sessione e licenza valide
- Nessuna `JOIN` o `SELECT` senza `WHERE user_id=?`

✅ **Verifica completa eseguita:** sistema resiliente a IDOR, injection e spoofing.

---

## 🔑 Licenze
- Flusso: Registrazione/Login → Attivazione licenza → Accesso  
- **Scadenza = blocco immediato**
- Admin: genera, invia, revoca, rinnova
- **Email automatiche:** promemoria scadenza (3, 5, 9 giorni), conferma attivazione/rinnovo

---

## 🔧 Variabili d’ambiente
- `FLASK_SECRET_KEY`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
- `ADMIN_EMAIL`
- Opzionali:
  - `RENEW_URL` (default: `http://127.0.0.1:5000/license`)
  - `BACKUP_MAX_COUNT`, `BACKUP_MAX_AGE_DAYS`

### Hardening
- `MAX_CONTENT_LENGTH = 2 MB`
- Cookie sicuri (`HttpOnly`, `SameSite=Lax`, `Secure` su HTTPS)
- Headers di sicurezza:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: SAMEORIGIN`
  - `Content-Security-Policy: default-src 'self'`
  - `Strict-Transport-Security: max-age=31536000`
  - `Permissions-Policy: camera=(), microphone=()`

---

## 🗄️ Database
Tabelle principali:  
`utenti`, `licenze`, `clienti`, `incassi`, `spese_fisse`, `fatture`, `personale`, `stipendi_personale`, `tasse`, `enti`, `fornitori`

---

## 📄 Pagine chiuse (stabili)
- `/clienti`
- `/mese`
- `/fornitori`
- `/fatture` → QR SEPA (con blocco doppio pagamento)
- `/personale` → CRUD completo + stipendi
- `/stipendi` → QR SEPA pagamento e sincronizzazione DB
- `/tasse` e `/pagamento-tasse` → QR SEPA, export PDF, stato persistente
- `/annuale` → riepilogo incassi/spese
- `/percentuali` ✅ *(nuova, completata)*

---

## 🎯 Modulo “Percentuali” — **Completato**
Pagina: `/percentuali`  
Analizza l’incidenza mensile di ogni categoria di spesa rispetto all’incasso.

### Funzionalità
- Grafici a torta per ciascun mese (Chart.js)
- Dati aggregati da `/api/percentuali_dati/<anno>`
- Popup automatico al caricamento del mese corrente  
  - Mostra incasso, spese, percentuali e consigli mirati  
  - Colore blu (✅ Tutto sotto controllo) o rosso (⚠️ Soglie superate)
  - Chiusura automatica dopo **10 secondi**
  - Riapertura manuale cliccando sul mese
- **Voce automatica (Text-to-Speech)**:
  - ✅ “Ottimo lavoro! Tutte le categorie sono entro i limiti. Continua così.”
  - ⚠️ “Attenzione! Nel mese selezionato alcune categorie superano le soglie di spesa.”
- **Soglie di controllo (configurate in JS):**
  - Personale → 33%  
  - Canone/Finanziamenti → 12%  
  - Alimentari → 25%  
  - Bevande → 6%  
  - Utenze → 4%  
  - Manutenzioni → 2%  
  - Marketing → 3%  
  - Licenze → 2%  
  - Commissioni → 2%  
  - Pulizia → 1%  
  - Lavanderia → 1.5%  
  - Spese Varie → 3%

### Tecnologia
Popup dinamico in pure **JavaScript**, voce italiana `SpeechSynthesis`, Chart.js responsive e interattivo.

---

## 💾 Backup
- Pulsante → crea ZIP in `C:\RISTO\BACKUP`
- Pulizia automatica gestita da `_cleanup_backups()`
- Configurabile via:
  - `BACKUP_MAX_COUNT`
  - `BACKUP_MAX_AGE_DAYS`

---

## 💸 Stipendi
- QR SEPA per pagamento diretto
- Stato “Pagato” persistente in DB + LS
- Calcolo lordo/contributi/netto mensile
- Riepilogo annuale automatico

---

## 🧾 Tasse
- Gestione enti e collegamento automatico
- Stato persistente (`pagato`, `non_pagato`, `standby`)
- QR SEPA generato dinamicamente (IBAN/BIC)
- Export PDF “Pagamenti Tasse”

---

## 📱 Pagamento Fatture
- QR SEPA generato da tabella fornitori
- Stato sincronizzato DB + LocalStorage
- Doppio salvataggio (DB + LS)

---

## 🧭 Git & GitHub
1. `.gitignore` → ignora `venv`, cache, DB, backup, segreti  
2. `git init && git add . && git commit`  
3. `git remote add origin <URL>` + `git push -u origin main`  
4. Branch feature → PR → merge  
5. `git pull --rebase` per aggiornare  
6. Rimuovere file tracciati: `git rm -r --cached <file>`  
7. Cambio remoto: `git remote set-url origin <URL>`

---

## ✅ Checklist PR
- [x] Tutte le query filtrano `user_id = _uid()`
- [x] Nessun `user_id` accettato dal client
- [x] `mese` normalizzato 1–12
- [x] Tutte le mutazioni protette con `@require_csrf`, `@require_login`, `@require_license`
- [x] Join multi-tenant sempre filtrate
- [x] Migrazioni con vincoli/indici preservati
- [x] Sincronizzazione automatica LS ↔ DB
- [x] Popup percentuali e voce testati

---

## 📦 Versione
**Release:** 3.10  
**Data:** 4 ottobre 2025  
**Stato:** ✅ Tutti i moduli completati e stabili  
**Prossimo step:** ottimizzazione performance e creazione installer `.exe`

---
