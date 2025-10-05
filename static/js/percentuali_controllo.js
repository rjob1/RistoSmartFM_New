/**
 * Converte uno slug in un nome leggibile.
 */
function formattaNome(slug) {
  return slug
    .replaceAll('-', ' ')
    .replace('staff', 'Staff')
    .replace('pulizie', 'Pulizie')
    .replace('lavapiatti', 'Lavapiatti')
    .replace('lavanderia', 'Lavanderia')        // nuova mappatura
    .replace('cucina', 'Cucina')
    .replace('sala', 'Sala')
    .replace('varie', 'Varie')
    .replace('utilita', 'Utilità')
    .replace('manutenzioni', 'Manutenzioni')
    .replace('licenze', 'Licenze e assicurazioni')
    .replace('commissioni', 'Commissioni')
    .replace('marketing', 'Marketing')
    .replace('alimentari', 'Alimentari')
    .replace('bevande', 'Bevande')
    .replace('canone', 'Canone e/o Mutuo')
    .replace('amministrazione', 'Amministrazione')
    .replace('finanziamento1', 'Finanziamento 1')
    .replace('finanziamento2', 'Finanziamento 2')
    .replace(/\b\w/g, l => l.toUpperCase());
}

/**
 * Text-to-speech in italiano.
 */
function leggiAvvisoVocale(testo) {
  if (!('speechSynthesis' in window)) return;
  const msg = new SpeechSynthesisUtterance(testo);
  msg.lang = 'it-IT';
  window.speechSynthesis.speak(msg);
}

/**
 * Mostra un popup full-screen con contenuto HTML.
 */
function mostraPopup(htmlContent, isWarning) {
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position:fixed;top:0;left:0;width:100vw;height:100vh;
    background:rgba(0,0,0,0.4);display:flex;
    justify-content:center;align-items:center;z-index:9999;
  `;
  const box = document.createElement('div');
  box.style.cssText = `
    background:white;border-radius:12px;
    width:90%;max-width:700px;max-height:85vh;
    display:flex;flex-direction:column;overflow:hidden;
    box-shadow:0 0 20px rgba(0,0,0,0.3);
  `;
  box.innerHTML = `
    <div style="padding:20px;overflow-y:auto;flex:1;">
      <h2 style="margin-top:0;color:${isWarning ? '#cc0000' : '#0066cc'}">
        ${isWarning ? '⚠️ Attenzione!' : '✅ Tutto sotto controllo'}
      </h2>
      <div style="font-size:16px;line-height:1.5;">${htmlContent}</div>
    </div>
    <div style="padding:15px;border-top:1px solid #ccc;text-align:right;">
      <button style="
        padding:8px 16px;background:#0066cc;color:white;
        border:none;border-radius:5px;cursor:pointer;font-weight:bold;">
        OK
      </button>
    </div>
  `;
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  box.querySelector('button').onclick = () => document.body.removeChild(overlay);
}

/**
 * Parsa stringhe euro italiane ("1.234,56", "–1.234,56") in Number.
 */
function parseEuro(val) {
  const s = (val || '').trim().replace('–', '-');
  if (!s) return 0;
  const cleaned = s.includes(',')
    ? s.replace(/\./g, '').replace(',', '.')
    : s;
  return parseFloat(cleaned) || 0;
}

/**
 * Mostra le percentuali di spesa per categoria.
 */
window.mostraPercentuali = function () {
  const MESI = ['gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre'];
  const ANNOcorr = (typeof ANNO !== 'undefined') ? ANNO : new Date().getFullYear();

  // soglie
  const soglieSingole = {
    alimentari: 25, bevande: 6, utilita: 4, manutenzioni: 2, marketing: 3,
    licenze: 2, commissioni: 2, pulizia: 1, lavanderia: 1.5,
    'spese-varie': 3, amministrazione: 2
  };
  const CATS_FATTURE = new Set(['alimentari','bevande','utilita','manutenzioni','marketing','licenze','commissioni','lavanderia','pulizia','spese-varie','varie']);
  const PERSONALE = ['amministrazione','staff-cucina','staff-sala','staff-lavapiatti','staff-pulizie'];
  const FINANZ = ['canone','finanziamento1','finanziamento2'];

  // helper
  const sel = document.getElementById('mese-selezionato');
  const mese = sel?.value;
  if (!mese || !MESI.includes(mese)) { alert('Seleziona un mese valido.'); return; }

  const parseEuro = (val) => {
    const s = String(val || '').trim().replace('–','-');
    if (!s) return 0;
    return s.includes(',') ? (parseFloat(s.replace(/\./g,'').replace(',', '.')) || 0) : (parseFloat(s) || 0);
  };
  const fmtPct = n => (isFinite(n) ? n.toFixed(2).replace('.', ',') + '%' : '--');

  // incasso/spese del mese dalla tabella annuale
  const idx = MESI.indexOf(mese) + 1;
  const inc = parseEuro(document.getElementById(`incasso-${idx}`)?.textContent);
  const spTot = parseEuro(document.getElementById(`spese-${idx}`)?.textContent);
  const totPct = inc > 0 ? (spTot / inc * 100) : 0;

  // letture LS corrette
  const getSpesa = (id) => {
    const key = `${ANNOcorr}_${mese}_spese_${id}`;
    return parseEuro(localStorage.getItem(key));
  };
  const getFatturaCat = (id) => {
    const key = `${ANNOcorr}_${mese}_fatture_${id}`;
    return parseEuro(localStorage.getItem(key));
  };

  // totali aggregati
  const personaleTot = PERSONALE.reduce((a,id)=>a+getSpesa(id),0);
  const finanziTot   = FINANZ.reduce((a,id)=>a+getSpesa(id),0);

  // HTML base
  let hasWarning = false;
  let html = `
    <p><strong>📅 Mese:</strong> ${mese.charAt(0).toUpperCase() + mese.slice(1)}</p>
    <p><strong>💰 Incasso:</strong> € ${inc.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</p>
    <p><strong>💸 Spese totali:</strong> € ${spTot.toLocaleString('it-IT', { minimumFractionDigits: 2 })}</p>
    <p><strong>📊 Spese / Incasso:</strong> ${fmtPct(totPct)}</p>
  `;

  // check Personale 33%
  const pctPersonale = inc > 0 ? (personaleTot / inc * 100) : 0;
  if (pctPersonale > 33) {
    hasWarning = true;
    html += `
      <div style="margin:10px 0;padding:10px;border:2px solid #cc0000;border-radius:8px;">
        <strong>Spese del Personale:</strong> ${fmtPct(pctPersonale)} (limite 33%)<br>
        <em>Controlla i turni, evita straordinari e rivedi l'organico.</em>
      </div>`;
  }

  // check Canone+Finanziamenti 12%
  const pctFinanz = inc > 0 ? (finanziTot / inc * 100) : 0;
  if (pctFinanz > 12) {
    hasWarning = true;
    html += `
      <div style="margin:10px 0;padding:10px;border:2px solid #cc0000;border-radius:8px;">
        <strong>Canone e Finanziamenti:</strong> ${fmtPct(pctFinanz)} (limite 12%)<br>
        <em>Rinegozia affitto o valuta rifinanziamento.</em>
      </div>`;
  }

  // check soglie singole (fatture vs spese)
  Object.keys(soglieSingole).forEach(cat => {
    const val = CATS_FATTURE.has(cat) ? getFatturaCat(cat) : getSpesa(cat);
    const pct = inc > 0 ? (val / inc * 100) : 0;
    if (pct > soglieSingole[cat]) {
      hasWarning = true;
      html += `
        <div style="margin:10px 0;padding:10px;border:2px solid #cc0000;border-radius:8px;">
          <strong>${formattaNome(cat)}:</strong> ${fmtPct(pct)} (limite ${soglieSingole[cat]}%)
        </div>`;
    }
  });

  // somma percentuali per nota finale
  let sommaTotale = 0;
  Object.keys(soglieSingole).forEach(cat => {
    const val = CATS_FATTURE.has(cat) ? getFatturaCat(cat) : getSpesa(cat);
    sommaTotale += inc > 0 ? (val / inc * 100) : 0;
  });
  sommaTotale += pctPersonale + pctFinanz;

  if (sommaTotale > 100) leggiAvvisoVocale("Attenzione! Le spese totali superano il cento per cento dell’incasso.");

  html += `
    <hr>
    <p style="font-size:1.1rem;"><strong>📉 Totale spese su incasso:</strong>
      <span style="color:${sommaTotale > 100 ? 'red' : '#006600'};font-weight:bold;">
        ${fmtPct(sommaTotale)}
      </span>
    </p>`;

  if (hasWarning) {
    mostraPopup(html, true);
    leggiAvvisoVocale("Attenzione: alcune categorie superano le soglie di spesa.");
  } else {
    mostraPopup(html + `<p style="margin-top:15px;">👏 Tutto entro i limiti. Ottimo lavoro!</p>`, false);
    leggiAvvisoVocale("Ottimo lavoro! Tutte le categorie sono entro i limiti.");
  }
};

