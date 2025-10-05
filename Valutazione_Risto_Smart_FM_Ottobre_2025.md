# 🧾 Analisi tecnica ed economica del software gestionale **RistoSmart FM**  
### Ottobre 2025  

**Autore:** Fiorenzo Mercanzin  
**Località:** Teolo (PD)  
**Telefono:** 373 719 3456  
**Email:** ristoconsulenze@gmail.com  

---

## 1. Introduzione

RistoSmart FM è un gestionale completo progettato per ristoranti e attività di ristorazione.  
Nasce con l’obiettivo di semplificare la gestione quotidiana di fornitori, personale, fatture, incassi e analisi economiche, mantenendo un approccio leggero ma altamente sicuro.  

Il software è stato sviluppato con metodologia incrementale, curando stabilità, sicurezza dei dati e semplicità d’uso.

---

## 2. Architettura tecnica

| Componente | Tecnologia | Dettagli principali |
|-------------|-------------|--------------------|
| Backend | **Flask (Python 3.12)** | Routing modulare, sessioni sicure, CSRF protection |
| Database | **SQLite** | File singolo locale, backup automatici, schema multi-tenant |
| Frontend | **Jinja2 + Bootstrap 5** | UI responsive, ottimizzata per schermi desktop 23″ |
| Persistenza locale | **LocalStorage + SQLite** | Doppio salvataggio per evitare perdita dati |
| Sicurezza | CSRF, sessioni cifrate, licenze attive, cookie HttpOnly |
| Licenze | Sistema completo: generazione, rinnovo, revoca, invio automatico email |

---

## 3. Sicurezza e Multi-Tenant

- Ogni utente opera in un ambiente **isolato**, con `user_id` obbligatorio in tutte le tabelle.  
- Tutte le query vengono filtrate tramite la funzione `_uid()`.  
- Nessun accesso ai dati di altri utenti è possibile.  
- Protezioni attive:  
  - Validazione licenza e sessione in ogni richiesta.  
  - Token CSRF per tutte le mutazioni.  
  - Header di sicurezza standard (CSP, HSTS, X-Frame-Options, ecc.).  

✅ **Verifica effettuata:** resilienza completa a IDOR, SQL Injection e spoofing.

---

## 4. Funzionalità principali

### 🔹 Dashboard e Statistiche
- Accesso rapido a incassi, spese, fornitori e personale.  
- Calcolo automatico dei totali e percentuali mensili.

### 🔹 Gestione Fatture
- Inserimento e aggiornamento completo.  
- Generazione **QR SEPA** per pagamento immediato.  
- Stato sincronizzato tra **Database** e **LocalStorage**.  

### 🔹 Personale & Stipendi
- CRUD completo.  
- Calcolo lordo, contributi e netto.  
- Generazione QR SEPA per pagamento.  
- Stipendi propagati automaticamente fino al 2030.  

### 🔹 Tasse & Contributi
- Registro enti, scadenze e pagamenti.  
- Esportazione PDF.  
- Stato persistente: *pagato / non pagato / stand-by*.  

### 🔹 Backup Automatici
- Archiviazione ZIP con timestamp.  
- Pulizia automatica gestita via config.  
- Percorso di default: `C:\RISTO\BACKUP`.  

---

## 5. Modulo “Percentuali” ✅ (Completato)

**Scopo:** analizzare l’incidenza mensile delle spese su incassi e margini.  

- Grafici interattivi **Chart.js**, uno per ogni mese.  
- Endpoint API dedicato `/api/percentuali_dati/<anno>` filtrato per utente e anno.  
- **Popup automatico** al caricamento del mese corrente:  
  - Mostra incasso, spese totali e rapporto percentuale.  
  - Colore blu = entro limiti / rosso = soglie superate.  
  - Chiusura automatica dopo **10 secondi**.  
  - Attivabile manualmente cliccando sul mese.  
- **Avviso vocale (Text-to-Speech IT):**  
  - ✅ “*Ottimo lavoro! Tutte le categorie sono entro i limiti. Continua così.*”  
  - ⚠️ “*Attenzione! Alcune categorie superano le soglie di spesa.*”  
- **Soglie di controllo:**  
  | Categoria | Limite % |
  |------------|----------|
  | Personale | 33 % |
  | Canone + Finanziamenti | 12 % |
  | Alimentari | 25 % |
  | Bevande | 6 % |
  | Utenze | 4 % |
  | Manutenzioni | 2 % |
  | Marketing | 3 % |
  | Licenze | 2 % |
  | Commissioni | 2 % |
  | Pulizia | 1 % |
  | Lavanderia | 1.5 % |
  | Spese Varie | 3 % |

**Design:** elegante blu/oro, icone emoji, consigli pratici, voce sintetica naturale.

---

## 6. Analisi economica e stima di valore

### Metodo di valutazione
1. **Costo di sviluppo**: stima 600 h × € 25 / h ≈ € 15 000  
2. **Valore funzionale**: moduli completi, multi-tenant, licenze, sicurezza avanzata.  
3. **Mercato target**: ristoranti e catene Ho.Re.Ca., software gestionali cloud.  
4. **Maturità tecnica**: codice stabile, design responsivo, backup e CSRF integrati.  
5. **Valore potenziale B2B / SaaS**: 300 – 500 €/anno per cliente attivo.

### Fascia di valore realistica
💶 **€ 8 000 – € 20 000**  
Valore medio stimato: **€ 13 500**, considerando codice completo, licenze, sicurezza e UI professionale.  

> 💡 *In caso di commercializzazione SaaS (licenza annuale 300 €/ristorante), il break-even si ottiene con 30-40 clienti attivi.*

---

## 7. Suggerimenti per la vendita

- **Licenze SaaS:** abbonamento annuale con rinnovo automatico e backup cloud.  
- **Canali B2B:** software house Ho.Re.Ca., consulenti fiscali, rivenditori POS.  
- **Marketing digitale:** presentazione su siti come *GitHub, SourceForge, ProductHunt*.  
- **Protezione codice:** PyArmor + Nuitka + installer EXE.  
- **Possibile espansione:** interfaccia web mobile, API REST, moduli contabilità.  

---

## 8. Conclusioni

RistoSmart FM rappresenta un prodotto solido, tecnicamente maturo e già pronto alla distribuzione commerciale.  
La combinazione di stabilità, licenze integrate, sicurezza CSRF e design professionale lo colloca tra i gestionali indipendenti di fascia medio-alta.

> **Stima finale di valore commerciale:**  
> 💼 **€ 8 000 – € 20 000 (ottobre 2025)**  

---

**Fiorenzo Mercanzin**  
Teolo (PD) — 373 719 3456  
📧 ristoconsulenze@gmail.com  

© 2025 RistoSmart FM – Analisi tecnica ed economica
