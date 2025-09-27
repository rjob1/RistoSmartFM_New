# 📁 RistoSmartFM — Documentazione di Progresso & Pianificazione

> *Ultimo aggiornamento: 18 Settembre 2025*  
> *Autore: Fio / Ingegneria Web Flask + SQLite*

---

## ✅ Stato Attuale del Progetto (Aggiornato al 18/09/2025)

### 🔒 **1. Privacy & Sicurezza — COMPLETATO**
- **Isolamento multi-tenant** → Ogni utente ha il proprio `user_id` su tutte le tabelle.
- **Dati locali** → Il database è un singolo file `ristosmart.db` sul PC dell’utente. Nessun cloud.
- **Accesso controllato** → Tutte le API richiedono:
  - `@require_login`
  - `@require_license`
  - `@require_csrf`
- **Cookie sicuri** → `HttpOnly`, `SameSite=Lax`, `Secure=True` (su HTTPS)
- **CSP in Report-Only** → Configurato per evitare blocchi durante lo sviluppo.
- **Audit log** → Log email (`log_email.csv`) e WhatsApp (`log_whatsapp.csv`) scaricabili solo dall’admin.

### 🔐 **2. Autenticazione & Licenza — COMPLETATO**
- Registrazione utente con password complessa (min. 12 caratteri, maiuscole, numeri, simboli).
- Login con validazione CSRF e blocco tentativi (5 falliti in 10 minuti).
- Licenza attivata tramite chiave univoca (`RSFM-XXXX-XXXX-XXXX-XXXX`).
- Licenze generate dall’admin via `/admin/licenses`.
- Attivazione licenza richiesta prima dell’accesso alle funzioni (eccetto admin).
- **Admin fisso**: `ristoconsulenze@gmail.com` → ruolo admin automatico.
- Email di conferma inviate al login, all’attivazione e al rinnovo.

### 💾 **3. Backup & Recovery — COMPLETATO**
- Backup automatico giornaliero ZIP del DB (`RistoSmartFM_DB_YYYYMMDD_HHMMSS.zip`).
- Cartella backup: `C:\RISTO\BACKUP`
- Retention configurabile:
  - `BACKUP_MAX_COUNT=15` (massimo 15 backup)
  - `BACKUP_MAX_AGE_DAYS=90` (elimina dopo 90 giorni)
- Backup scaricabile dall’admin via `/admin/backup/db`

### 🧩 **4. Funzionalità Implementate — COMPLETATE**
| Modulo | Stato |
|--------|-------|
| **Clienti** | ✅ Gestione completa (CRUD) |
| **Fornitori** | ✅ Gestione completa (CRUD) |
| **Fatture** | ✅ CRUD + scadenze + report mensile |
| **Incassi & Spese fisse** | ✅ CRUD + totale mensile |
| **Personale** | ✅ CRUD completo con localStorage + sincronizzazione DB |
| **Licenze (admin)** | ✅ Generazione, invio, revoca, esportazione CSV |
| **Newsletter & WhatsApp** | ✅ Invio personalizzato con log CSV |
| **Drip Email (promemoria)** | ✅ Invio automatico a -10/-5/-1 giorni dalla scadenza |
| **Rinnovo licenza** | ✅ URL firmato (`/renew?token=...`) per self-service |
| **Backup DB** | ✅ Scaricabile con un click |
| **Dashboard / Home** | ✅ Con anno selezionabile |

### 🖥️ **5. Architettura — COMPLETATA**
- **Backend**: Flask (Python 3.12), SQLite (file singolo)
- **Frontend**: Jinja2 + Bootstrap 5 (senza framework JS pesanti)
- **API RESTful** → Tutti i dati sono gestiti via `/api/...`
- **Multi-tenant** → Tutto filtrato da `_uid()` → `session["user_id"]`
- **CSRF protetto** → Token verificato in ogni richiesta PUT/POST/DELETE
- **Security Headers** → CSP, HSTS, X-Frame-Options, Referrer-Policy
- **No external dependencies** → Niente CDN esterni (tutti gli asset locali)

### 📄 **6. File HTML Pronti**
| File | Posizione | Stato |
|------|-----------|-------|
| `personale.html` | `templates/` | ✅ Corretto, con CSRF integrato, `localStorage="personale"`, validazione data obbligatoria |
| `privacy.html` | `templates/` | ⚠️ Da generare (vedi sotto) |
| `condizioni_generali.html` | `templates/` | ⚠️ Da generare (vedi sotto) |
| `license.html` | `templates/` | ✅ Funzionante |
| `login.html`, `register.html`, `logout_confirm.html` | `templates/` | ✅ Funzionanti |

### 🛠️ **7. Configurazioni Chiave (app.py)**
```python
# --- VARIABILI AMBIENTE (consigliate in .env) ---
FLASK_SECRET_KEY = "CHIAVE_LUNGA_RANDOM"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "la-tua-email@gmail.com"
SMTP_PASS = "LA_TUA_APP_PASSWORD"
ADMIN_EMAIL = "ristoconsulenze@gmail.com"

# --- OPZIONALI ---
BACKUP_MAX_COUNT = 15
BACKUP_MAX_AGE_DAYS = 90
RENEW_URL = "http://127.0.0.1:5000/renew"

# --- PERCORSO DB (NON MODIFICARE) ---
DB_PATH = "C:/RISTO/data/ristosmart.db"  # o qualsiasi path assoluto