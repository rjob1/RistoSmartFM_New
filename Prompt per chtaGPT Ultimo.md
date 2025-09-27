📖 RistoSmartFM – Regole di Sviluppo & Guida Operativa
🎯 Obiettivo

Gestionale ristorazione (Flask + SQLite) con:

Invio Newsletter via Email (SMTP Gmail) e WhatsApp (link wa.me)

Anteprima con personalizzazione ({{nome}}, {{note}}, {{email}}) e prefisso fisso automatico

Log CSV per Email/WhatsApp (+ download)

Dati sempre salvi (DB + LocalStorage)

Distribuzione .exe (PyInstaller) con configurazione via .env

Login + Attivazione Licenza (da implementare subito dopo; specifiche incluse sotto)

👤 Ruolo & Stile

Agisci come Ingegnere Senior Flask (Python 3.12), UI Bootstrap 5 + Jinja2.

Modifiche chirurgiche: non rompere ciò che funziona; patch mirate nel punto esatto.

Risposte/commit sintetici: una cosa alla volta, chiaro e verificabile.

🔒 Principio fondamentale (Dati)

Zero perdita dati.

Ogni operazione aggiorna Database (persistenza) e LocalStorage (reattività/offline).

Feature nuove non devono rompere quelle esistenti.

🏗 Architettura

Backend: Flask (Python 3.12), smtplib per email, sqlite3

Frontend: HTML Jinja2 + Bootstrap 5, JS vanilla

DB: SQLite (ristosmart.db)

Config: file .env (sviluppo e produzione/.exe)

Distribuzione: PyInstaller (.exe) + .env a fianco

📄 Pagine/Moduli confermati
base.html (🔒 stabile)

Header con logo/titolo, navbar, footer.

Colori aziendali coerenti.

home.html (🔒 stabile)

Navigazione per anno/mesi, layout responsivo.

mese.html (🔒 stabile)

Incassi giornalieri, Spese fisse, calcoli riepilogativi.

Persistenza LocalStorage + sync DB via API whitelisted.

Nota sempre visibile: “Le percentuali sono calcolate sull’incasso mensile.”

clienti.html (✅)

CRUD completo (Nome obbl., Email/Telefono/Note opz.).

Ricerca live, badge stato online/offline, toast.

Sync LS↔DB.

newsletter.html (✅)

Canali: Email, WhatsApp, Entrambi.

Oggetto (solo Email), Corpo (comune).

Prefisso fisso automatico:
Ciao {{nome}}, oggi promo speciale per te.

Personalizzazione per destinatario: {{nome}}, {{note}}, {{email}}.

Anteprima corretta (Jinja-safe tokens) + lista destinatari.

WhatsApp: apertura link wa.me sfalsata (150ms) per evitare blocco pop-up.

🗄️ Schema Tabelle DB (attuali)
-- Incassi giornalieri
CREATE TABLE IF NOT EXISTS incassi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  anno INTEGER NOT NULL,
  mese TEXT NOT NULL,
  giorno INTEGER NOT NULL,
  valore REAL NOT NULL DEFAULT 0
);

-- Spese fisse (whitelist server-side)
CREATE TABLE IF NOT EXISTS spese_fisse (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  anno INTEGER NOT NULL,
  mese TEXT NOT NULL,
  categoria TEXT NOT NULL,
  valore REAL NOT NULL DEFAULT 0
);

-- Clienti
CREATE TABLE IF NOT EXISTS clienti (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  telefono TEXT,
  email TEXT,
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);


Whitelist spese_fisse attiva lato server: {"canone","finanziamento1","finanziamento2","finanziamento-altro"}.

🔐 Login + Licenza (SPEC DA IMPLEMENTARE)

Obbligatorio per il cliente finale: login e attivazione licenza prima dell’uso.

DB (nuove tabelle)
-- Utenti locali (minimo)
CREATE TABLE IF NOT EXISTS utenti (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  ruolo TEXT DEFAULT 'user',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Licenze
CREATE TABLE IF NOT EXISTS licenze (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  license_key TEXT UNIQUE NOT NULL,
  intestatario TEXT,
  scadenza TEXT,          -- ISO date (opzionale)
  attiva INTEGER NOT NULL DEFAULT 0, -- 0/1
  meta TEXT,              -- JSON opzionale (piano, limiti, note)
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

Flusso (minimo, da implementare)

/login (form, sessione Flask).

/logout (clear session).

/license (pagina attivazione):

Input: license_key.

Verifica lato server (es. firma HMAC o lookup su tabella licenze).

Se valida → set attiva=1 e memorizza in sessione “license_ok”.

Protezione rotte: decorator @require_license + @require_login su tutte le pagine (escluse /login, /license, statici).

Messaggi: se non loggato → redirect /login; se no-licenza → redirect /license.

Nota: generazione licenze lato tuo backoffice (anche CLI), consigliato formato firmato (es. base64(payload).signature). In prima fase puoi usare tabella licenze con chiavi “semplici” e attivarle manualmente.

✉️ Newsletter – Dettagli tecnici
Email (SMTP Gmail)

Porta 587, STARTTLS.

Necessario App Password a 16 caratteri (account Google con 2FA).

Ogni destinatario riceve oggetto e corpo personalizzati:

Oggetto: template con {{nome}} (es. “Promo per {{nome}}”).

Corpo: prefisso fisso + testo newsletter.

WhatsApp (gratuito, senza Twilio)

Link https://wa.me/<numero>?text=<msg>

Numero senza “+” (es. 39333...). Se manca il prefisso, si aggiunge +39 (Italia), poi si rimuove + per wa.me.

Apertura a raffica con setTimeout(..., i*150) per evitare blocco pop-up.

Non invia automaticamente: si apre la chat con messaggio precompilato → l’utente conferma.

Personalizzazione

Variabili supportate: {{nome}}, {{note}}, {{email}}.

Prefisso fisso aggiunto automaticamente da backend all’invio (sia Email che WhatsApp).

Anteprima: usa token Jinja-safe per mostrare correttamente le variabili prima dell’invio.

Log CSV + download

backup/log_email.csv: ts,to_email,subject,body,ok,error

backup/log_whatsapp.csv: ts,to_phone,url,text,status (status=prepared)

Rotte download:

/logs/email.csv

/logs/whatsapp.csv

⚙️ Configurazione
Requisiti
Python 3.12
pip

requirements.txt (minimo)
Flask>=3.0
python-dotenv>=1.0


smtplib, sqlite3, email sono nella stdlib.

.env (sviluppo e .exe)

Crea .env accanto a app.py (in .exe: accanto all’eseguibile):

FLASK_SECRET_KEY=chiave-segreta-lunga
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=ristoconsulenze@gmail.com
SMTP_PASS=LA_TUA_PASSWORD_APP_16_CARATTERI


Caricamento robusto (app.py):

from dotenv import load_dotenv
import sys
from pathlib import Path

def _load_env():
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    load_dotenv(base / ".env", override=False)
_load_env()


Così funziona sia in dev che nell’.exe (il .env sta vicino all’eseguibile).
Aggiungi .env a .gitignore.

▶️ Avvio (dev)
# dalla cartella progetto
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# crea/compila .env come sopra
python app.py
# apri: http://127.0.0.1:5000

🧭 API principali (backend)

GET /api/clienti – lista clienti

POST /api/clienti – crea cliente

PUT /api/clienti/<id> – aggiorna cliente

DELETE /api/clienti/<id> – elimina cliente

GET /api/incassi/<anno>/<mese> – incassi mese

POST /api/salva-incasso – crea/aggiorna incasso giorno

GET /api/spese/<anno>/<mese> – spese fisse mese

POST /api/salva-spesa – crea/aggiorna spesa fissa (categorie whitelisted)

POST /api/newsletter/send – invio newsletter

Input:

{
  "channel": "email" | "whatsapp" | "entrambi",
  "subject": "oggetto (se email)",
  "body": "testo",
  "recipients": [{ "nome": "...", "email": "...", "telefono": "...", "note": "..." }]
}


Output:

{ "ok": true, "email_results": [...], "wa_links": [...] }


GET /logs/email.csv – download log email

GET /logs/whatsapp.csv – download log WhatsApp

🧪 Newsletter – Note UI/JS

Anteprima: mostra prefisso fisso + testo, con personalizzazione usando il primo destinatario come esempio (Jinja-safe tokens).

Apertura WhatsApp:

links.forEach((l,i)=>{ if(l.url) setTimeout(()=>window.open(l.url,"_blank"), i*150) })


Errori JSON: backend ora risponde sempre JSON anche sugli errori (jsonify(...), 4xx/5xx), evitando Unexpected token '<'.

🛠 Build .exe (PyInstaller)

Comando base:

pyinstaller --noconfirm --onefile --add-data "templates;templates" --add-data "static;static" app.py


Consegna al cliente:

dist/app.exe

templates/, static/ sono inclusi nel binario (usando l’opzione sopra)

.env nella stessa cartella dell’.exe (SMTP loro + FLASK_SECRET_KEY)

Al primo avvio dovrà:

/license → inserire la licenza

/login → credenziali utente

Suggerito fornire anche un .env.example.

🧯 Troubleshooting (casi reali risolti)

SyntaxError: from urllib.parse import
→ Import incompleto. Usare: from urllib.parse import quote_plus.

TypeError: The view function ... did not return a valid response
→ Route non ritorna JSON in tutti i rami → funzione api_newsletter_send() ora garantisce return jsonify(...) sempre.

Unexpected token '<', "<!doctype "... is not valid JSON
→ Backend ha risposto HTML 500; ora catturiamo eccezioni e rispondiamo JSON con codice 4xx/5xx.

WhatsApp non apre / numero errato
→ wa.me non vuole +. Normalizza: aggiungi +39 se manca → poi rimuovi + → 3933....

Popup bloccati
→ Apri link WA con piccoli delay (setTimeout(..., i*150)).

SMTP Gmail
→ Usa App Password (16 caratteri), porta 587/STARTTLS.

🗺️ Roadmap (prossimi step)

Login & Licenza (PRIORITÀ)

Tabelle utenti, licenze (schema sopra)

Rotte: /login, /logout, /license

Decorator: @require_login, @require_license

Proteggi tutte le pagine (tranne login/license/static)

Stipendi

Tabella stipendi_mensili (schema già indicato in bozza)

Pagina personale.html + API

Fatture

Tabella spese_fatture (schema già indicato)

Pagina fatture.html + API

Backup DB

Job periodico copia ristosmart.db in backup/

📦 Struttura progetto (suggerita)
RistoSmartFM_New/
├─ app.py
├─ requirements.txt
├─ .env              # non in git
├─ templates/
│  ├─ base.html
│  ├─ home.html
│  ├─ mese.html
│  ├─ clienti.html
│  └─ newsletter.html
├─ static/
│  ├─ logoristosmart.png
│  └─ (css/js vari)
├─ backup/
│  ├─ log_email.csv
│  └─ log_whatsapp.csv
└─ ristosmart.db

✅ Stato attuale (oggi)

✅ SMTP Gmail funzionante (Email OK)

✅ WhatsApp via wa.me con personalizzazione e prefisso fisso

✅ Anteprima corretta (Jinja-safe)

✅ Log CSV + download

✅ Caricamento .env robusto (dev + .exe)

⏭ Login + Licenza → da implementare subito (spec pronte sopra)


Domani implementiamo:

Login: tabella utenti, hash password (werkzeug.security), /login e /logout con sessione.

Licenza: tabella licenze, pagina /license, verifica chiave e decorator @require_license.

Protezione: @require_login su tutte le pagine (tranne login/license/static).

Navbar/redirect: stato utente + redirect automatici se non loggato/licenza non attiva.

✅ .env: lo usiamo come già descritto (loader robusto che funziona anche nell’.exe).
Se vuoi, domattina posso anche preparare i comandi PyInstaller finali con login/licenza inclusi.



{% extends "base.html" %}
{% block title %}Gestione Fatture{% endblock %}

{% block content %}
<div class="container-fluid mt-4 px-4 fatture-container">
  <h2 class="mb-3">Gestione Fatture</h2>

  <!-- 🔔 Notifiche -->
  <div id="notifiche" class="alert alert-info d-none mb-3"></div>

  <!-- Riga inserimento -->
  <div class="row g-3 align-items-end mb-3">
    <div class="col-lg-2 col-md-4"><label class="form-label">Data inserimento</label>
      <input type="date" id="dataInserimento" class="form-control">
    </div>
    <div class="col-lg-2 col-md-4"><label class="form-label">Fornitore</label>
      <select id="fornitore" class="form-select"></select>
    </div>
    <div class="col-lg-2 col-md-4"><label class="form-label">Categoria</label>
      <select id="categoria" class="form-select"></select>
    </div>
    <div class="col-lg-2 col-md-4"><label class="form-label">Data scadenza</label>
      <input type="date" id="dataScadenza" class="form-control">
    </div>
    <div class="col-lg-1 col-md-3"><label class="form-label">Importo</label>
      <input type="number" id="importo" class="form-control" step="0.01">
    </div>
    <div class="col-lg-1 col-md-3"><label class="form-label">Stato</label>
      <select id="stato" class="form-select">
        <option value="Pagato">Pagato</option>
        <option value="Non pagato" selected>Non pagato</option>
        <option value="Stand by">Stand by</option>
      </select>
    </div>
    <div class="col-lg-1 col-md-3"><label class="form-label">Numero fattura</label>
      <input type="text" id="numero" class="form-control">
    </div>
    <div class="col-lg-auto col-md-3 d-flex align-items-end">
      <button id="btnAggiungi" class="btn btn-primary w-100">Aggiungi</button>
    </div>
  </div>

  <!-- 🔽 FILTRO STATO + ESPORTA CSV -->
  <div class="row g-3 mb-3 align-items-end">
    <div class="col-lg-2 col-md-4">
      <label class="form-label">Filtra per stato</label>
      <select id="filtroStato" class="form-select">
        <option value="">Tutti</option>
        <option value="Pagato">Pagato</option>
        <option value="Non pagato">Non pagato</option>
        <option value="Stand by">Stand by</option>
      </select>
    </div>
    <div class="col-lg-auto col-md-4">
      <button id="btnEsportaCSV" class="btn btn-outline-secondary w-100">
        <i class="bi bi-download me-1"></i> Esporta CSV
      </button>
    </div>
  </div>

  <!-- Ricovero fatture -->
  <div class="table-responsive">
    <table class="table table-striped table-hover" id="tabellaFatture">
      <thead class="table-light">
        <tr>
          <th style="min-width: 120px;">Data</th>
          <th style="min-width: 160px;">Fornitore</th>
          <th style="min-width: 160px;">Categoria</th>
          <th style="min-width: 120px;">Scadenza</th>
          <th style="min-width: 100px;">Importo</th>
          <th style="min-width: 150px;">Stato</th> <!-- ✅ allargata -->
          <th style="min-width: 120px;">Numero</th>
          <th style="width: 150px;">Azioni</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<!-- Toast -->
<div class="position-fixed bottom-0 end-0 p-3" style="z-index:11">
  <div id="toast" class="toast align-items-center text-white bg-success border-0" role="alert">
    <div class="d-flex">
      <div class="toast-body" id="toastMsg">Salvato!</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>
  </div>
</div>

<!-- Animazione lampeggio (ogni 10s, non continuo) -->
<style>
@keyframes blink-10s {
    0%, 90% { opacity: 1; }
    91%, 100% { opacity: 0.6; }
}

/* Contenitore principale: regola la larghezza max della pagina */
.fatture-container {
  max-width: 1700px;
  margin: 0 auto;
}

/* Tabella: evita che si stringa troppo */
#tabellaFatture th,
#tabellaFatture td {
  white-space: nowrap;
  vertical-align: middle;
}
</style>

<script>
// 🔊 Notifica vocale giornaliera
function checkDailyVoiceAlert(fatture) {
    const oggi = new Date().toDateString();
    const ultimoAvviso = localStorage.getItem("ultimo_avviso_vocale");
    const utterance = new SpeechSynthesisUtterance();

    const inScadenza = fatture.some(f => {
        const scad = new Date(f.data_scadenza);
        const giorni = Math.ceil((scad - new Date()) / (1000*60*60*24));
        return f.stato !== "Pagato" && giorni <= 5 && giorni >= 0;
    });

    if (inScadenza && ultimoAvviso !== oggi) {
        utterance.text = "Attenzione, hai delle fatture che scadono entro i prossimi 5 giorni.";
        utterance.lang = "it-IT";
        utterance.volume = 1;
        utterance.rate = 0.9;
        speechSynthesis.speak(utterance);
        localStorage.setItem("ultimo_avviso_vocale", oggi);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
  const toast = new bootstrap.Toast(document.getElementById("toast"));
  let fornitoriCache = [];
  const categorie = [
    "Alimentari (Food Cost)","Bevande","Utilità (Luce, acqua, gas)","Manutenzioni e riparazioni",
    "Marketing e pubblicità","Licenze e assicurazioni","Commissioni (The Fork)","Lavanderia",
    "Pulizia e igiene","Spese Varie","Varie"
  ];
  let tutteFatture = [];

  // 🔽 Carica fornitori + categorie
  async function caricaFornitoriCategorie(){
    const selF = document.getElementById("fornitore");
    const selC = document.getElementById("categoria");
    selF.innerHTML = `<option value="">-- Seleziona --</option>`;
    selC.innerHTML = `<option value="">-- Seleziona --</option>`;
    try {
      const resp = await csrfFetch("/api/fornitori");
      fornitoriCache = await resp.json();
      fornitoriCache.forEach(f => {
        const opt = document.createElement("option");
        opt.value = f.nomeFornitore;
        opt.textContent = f.nomeFornitore;
        opt.dataset.categoria = f.categoria;
        selF.appendChild(opt);
      });
      selF.addEventListener("change", () => {
        const selectedOpt = selF.options[selF.selectedIndex];
        selC.value = selectedOpt.dataset.categoria || "";
      });
    } catch(e) { console.error(e); }

    categorie.forEach(cat => {
      const opt = document.createElement("option");
      opt.value = cat; opt.textContent = cat;
      selC.appendChild(opt);
    });
  }
  caricaFornitoriCategorie();

  // 🔔 Mostra notifica scadenze
  function mostraNotifiche(fatture) {
    const notificheDiv = document.getElementById("notifiche");
    const oggi = new Date();
    const inScadenza = fatture.filter(f => {
      const scad = new Date(f.data_scadenza);
      const giorni = Math.ceil((scad - oggi) / (1000 * 60 * 60 * 24));
      return f.stato !== "Pagato" && giorni <= 5 && giorni >= 0;
    });

    if (inScadenza.length === 0) {
      notificheDiv.className = "alert alert-success";
      notificheDiv.textContent = "✅ Perfetto! Non hai fatture in scadenza.";
    } else {
      notificheDiv.className = "alert alert-warning";
      notificheDiv.innerHTML = `
        <strong>Attenzione!</strong> Hai ${inScadenza.length} fattura(e) in scadenza:
        <ul>${inScadenza.map(f =>
          `<li><strong>${f.fornitore || "Senza nome"}</strong>: €${parseFloat(f.importo).toFixed(2)} 
           (scade il ${new Date(f.data_scadenza).toLocaleDateString()})</li>`
        ).join("")}</ul>
      `;
    }
    notificheDiv.classList.remove("d-none");
  }

  // ... [resto identico al tuo file] ...

});

// 🔄 aggiorna notifiche ogni 10 secondi senza ricaricare
setInterval(async () => {
  try {
    const res = await csrfFetch("/api/fatture");
    if (res.ok) {
      const fatture = await res.json();
      mostraNotifiche(fatture);

      // ✅ ripristina i fornitori salvati
      const rows = document.querySelectorAll("#tabellaFatture tbody tr");
      rows.forEach(tr => {
        const id = tr.dataset.id;
        if (!id) return;
        const key = `fattura_${id}_fornitore`;
        const savedValue = localStorage.getItem(key);
        if (savedValue) {
          const input = tr.querySelector(".fornitore-input");
          if (input) input.value = savedValue;
        }
      });
    }
  } catch (e) {
    console.error("Errore aggiornamento notifiche", e);
  }
}, 10000);
</script>
{% endblock %}
