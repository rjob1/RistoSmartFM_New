# 📑 Changelog – RistoSmartFM

Tutte le modifiche principali registrate in ordine cronologico.

---

## [2025-09-14] – Fatture: notifiche cross-anno
- **Nuovo endpoint API:**  
  - `/api/fatture_scadenze/<anno>`  
  - Restituisce le fatture dell’anno corrente **+ anno precedente**.  
  - Filtrate per `user_id`, ordinate per `data_scadenza`.
- **Frontend (fatture.html):**  
  - Script aggiornato per mostrare le scadenze anche se inserite l’anno prima ma in scadenza entro 60 giorni.  
  - Inclusa tolleranza arretrata di 5 giorni.  
  - Es.: fattura inserita a dicembre 2025 con scadenza 2 febbraio 2026 → appare correttamente nelle notifiche di febbraio 2026.
- **Stato attuale:**  
  - Popup non invasivo → aggiunta nel box notifiche esistente.  
  - Avviso vocale rimane limitato alle scadenze entro 5 giorni.

---

## [2025-09-13] – Stabilizzazione fatture
- Fix rendering tabella: sostituito formatter errato `€(...)` con `fmtEuro(...)`.  
- Creato helper `fmtEuro()` per output in formato `it-IT` con due decimali.  
- Aggiornato `aggiungiRiga()` e `renderTabella()` per usare formatter unificato.

---

## [2025-09-12] – Fatture CRUD
- Implementato inserimento, modifica ed eliminazione fatture (DB + LocalStorage).  
- Toast verde conferma per ogni azione.  
- Notifiche automatiche in testata pagina (entro 5 giorni dalla scadenza).  
- Aggiunto pulsante “Test voce” visibile solo all’admin.  
- Avviso vocale giornaliero con cache `ultimo_avviso_vocale` in LocalStorage.

---

## [2025-09-05] – Fornitori (CHIUSO)
- CRUD completo DB + LocalStorage.  
- Tabella con icone (modifica, salva, elimina).  
- Popup conferma verde con `showToast`.

---

## [2025-09-02] – Clienti (CHIUSO)
- CRUD completo DB + LocalStorage.  
- Sincronizzazione automatica senza pulsanti manuali.  
- Tutti i dati sempre persistenti.

---

## [2025-08-30] – Mese (CHIUSO)
- Gestione incassi e spese mensili.  
- Percentuali e calcoli live.  
- Doppia persistenza (DB + LocalStorage).  
- Nessun tasto “Sincronizza” → tutto automatico.

---

## [2025-08-25] – Base.html (CHIUSO)
- Navbar unificata con selezione anno e pulsante “Ricarica”.  
- Orologio `last-reload` aggiornato automaticamente.

---
