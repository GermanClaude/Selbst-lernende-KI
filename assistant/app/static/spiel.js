/* KI-App – Spielmodus: Dialog (Ziel, Modus, Grenzen, Zustimmung), Band „Nova spielt …“ mit Stopp
   und die Berichtskarte mit Bildern. Bekommt den Zustand von app.js (NovaSpiel.zustand(state)) und
   spricht selbst mit /api/spiel. Nova steuert Maus und Tastatur nur, solange das Spielfenster vorne ist. */
(() => {
  'use strict';

  const TOKEN = new URLSearchParams(location.search).get('t') || '';
  const byId = (id) => document.getElementById(id);
  const app = () => window.NovaApp || { toast: () => {}, name: () => 'Nova', providerName: () => '', card: () => null };

  const ZUSTAND = {
    sucht: 'wartet, bis du ins Spiel wechselst',
    startet: 'startet …',
    spielt: 'schaut hin und handelt',
    laeuft: 'lässt das Spiel laufen',
    wartet: 'wartet, bis das Spiel wieder vorne ist',
    endet: 'hört auf …',
  };

  async function post(body) {
    try {
      const r = await fetch('/api/spiel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-KI-Token': TOKEN },
        body: JSON.stringify(body || {}),
      });
      let data = null;
      try { data = await r.json(); } catch (_) { data = null; }
      return data && typeof data === 'object' ? data : { ok: false, error: 'Unerwartete Antwort von der KI.' };
    } catch (_) {
      return { ok: false, error: 'Keine Verbindung zur KI.' };
    }
  }

  let st = null;        // state.spiel vom Server
  let modus = 'normal';
  let busy = false;
  let zurueck = null;   // Fokus nach dem Schließen des Dialogs

  function eur(v) {
    return (Math.max(0, Number(v) || 0)).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }
  function zahl(text) {
    const t = String(text || '').trim().replace(',', '.');
    if (!t) return null;
    const n = Number(t);
    return Number.isFinite(n) && n > 0 ? n : NaN;
  }
  function deutsch(n) { return String(n).replace('.', ','); }

  // ---------------------------------------------------------------------
  // Band und Seitenleiste
  // ---------------------------------------------------------------------
  function render() {
    const name = app().name();
    const an = !!(st && st.aktiv);
    const band = byId('spiel-band');
    if (band) {
      band.hidden = !an;
      if (an) {
        band.dataset.mode = st.zustand === 'wartet' || st.zustand === 'sucht' ? 'pause' : 'spielt';
        const spiel = st.spiel ? ' ' + st.spiel : '';
        byId('sp-title').textContent = (st.modus === 'nacht' ? name + ' spielt über Nacht' : name + ' spielt') + spiel +
          (ZUSTAND[st.zustand] ? ' – ' + ZUSTAND[st.zustand] : '');
        byId('sp-zug').textContent = 'Zug ' + (Number(st.zuege) || 0) + (st.max_zuege ? ' von ' + st.max_zuege : '');
        byId('sp-zeit').textContent = (Number(st.minuten) || 0) + ' von ' + (Number(st.max_minuten) || 0) + ' Min.';
        byId('sp-kosten').textContent = st.kostenlos ? 'kostenlos' : eur(st.eur) + ' von ' + eur(st.max_eur);
        byId('sp-last').textContent = st.letztes || ('Anhalten: ' + (st.stopp_taste || 'Stopp') + ' oder Maus bewegen');
      }
    }
    const titel = byId('sb-spiel-title');
    const sub = byId('sb-spiel-sub');
    const knopf = byId('sb-spiel');
    if (knopf) knopf.classList.toggle('on', an);
    if (titel) titel.textContent = an ? 'Spiel anhalten' : 'Spielmodus';
    if (sub) sub.textContent = an ? (st.spiel || 'wartet aufs Spiel') + ' – Zug ' + (Number(st.zuege) || 0)
      : name + ' spielt selbst, z. B. Manor Lords';
  }

  // ---------------------------------------------------------------------
  // Dialog
  // ---------------------------------------------------------------------
  const modal = byId('spiel-modal');

  function setModus(m) {
    modus = m === 'nacht' ? 'nacht' : 'normal';
    for (const b of document.querySelectorAll('#spd-modus [data-modus]')) {
      b.setAttribute('aria-checked', b.dataset.modus === modus ? 'true' : 'false');
    }
    const g = st && st.grenzen && st.grenzen[modus] ? st.grenzen[modus] : null;
    if (g) {
      byId('spd-stunden').value = deutsch(g.stunden);
      byId('spd-euro').value = deutsch(Number(g.euro).toFixed(2));
      byId('spd-schritte').value = String(g.schritte);
    }
  }

  function fehler(text) {
    const el = byId('spd-err');
    if (!el) return;
    el.textContent = text || '';
    el.hidden = !text;
  }

  async function oeffnen(opts) {
    if (!modal) return;
    if (st && st.aktiv) { anhalten(); return; }
    zurueck = document.activeElement;
    const o = opts || {};
    fehler('');
    if (o.ziel) byId('spd-ziel').value = o.ziel;
    byId('spd-erkannt').textContent = 'Einen Moment …';
    modal.hidden = false;
    byId('spd-ziel').focus();
    const r = await post({ aktion: 'status' });
    if (r && r.spiel) st = r.spiel;
    setModus(o.modus || modus);
    const laufend = r && Array.isArray(r.laufend) ? r.laufend : [];
    const erlaubt = st && Array.isArray(st.spiele) ? st.spiele : [];
    byId('spd-erkannt').textContent = !(st && st.windows) ? 'Der Spielmodus geht nur unter Windows.'
      : laufend.length ? 'Erkannt: ' + laufend.join(', ') + ' läuft. Nach dem Start einfach ins Spiel wechseln.'
        : 'Ich sehe gerade kein freigegebenes Spiel (' + (erlaubt.join(', ') || 'keins') + '). Starte es – ich warte nach dem Start bis zu 2 Minuten.';
    byId('spd-taste').textContent = (st && st.stopp_taste) || 'Strg+Alt+Umschalt+P';
    byId('spd-euro-box').hidden = !!(r && r.kostenlos);
    const z = byId('spd-zustimmung');
    z.hidden = !(st && st.zustimmung_noetig);
    if (!z.hidden) {
      byId('spd-warnung').textContent = String((r && r.warnung) || '').replace(/\*\*/g, '');
      byId('spd-ok').checked = false;
    }
    if (o.vorschlag) app().toast(app().name() + ' schlägt den Spielmodus vor – du entscheidest.', 'info', 5000);
  }

  function schliessen(abgelehnt) {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    if (abgelehnt && st && st.vorschlag) post({ aktion: 'ablehnen' });
    if (zurueck && typeof zurueck.focus === 'function') zurueck.focus();
    zurueck = null;
  }

  async function starten() {
    if (busy) return;
    const stunden = zahl(byId('spd-stunden').value);
    const euro = zahl(byId('spd-euro').value);
    const schritte = zahl(byId('spd-schritte').value);
    if ([stunden, euro, schritte].some((v) => Number.isNaN(v))) { fehler('Bitte nur positive Zahlen bei den Grenzen.'); return; }
    const zustimmung = !byId('spd-zustimmung').hidden;
    if (zustimmung && !byId('spd-ok').checked) { fehler('Bitte erst lesen und das Häkchen setzen.'); return; }
    busy = true;
    try {
      const r = await post({
        aktion: 'start', ziel: byId('spd-ziel').value.trim(), modus,
        stunden, euro, schritte: schritte == null ? null : Math.round(schritte), einverstanden: zustimmung,
      });
      if (r && r.ok) {
        if (r.spiel) st = r.spiel;
        render();
        schliessen(false);
        app().toast('Jetzt ins Spiel wechseln (z. B. Alt+Tab).', 'ok', 6000);
      } else if (r && r.zustimmung) {
        byId('spd-zustimmung').hidden = false;
        byId('spd-warnung').textContent = String(r.warnung || '').replace(/\*\*/g, '');
        fehler('Bitte erst lesen und zustimmen.');
      } else fehler((r && r.error) || 'Der Spielmodus ging nicht.');
    } finally {
      busy = false;
    }
  }

  async function anhalten() {
    const r = await post({ aktion: 'stopp' });
    if (r && r.spiel) { st = r.spiel; render(); }
    app().toast((r && (r.text || r.error)) || 'Angehalten.', r && r.ok ? 'ok' : 'error');
  }

  if (modal) {
    byId('spd-cancel').addEventListener('click', () => schliessen(true));
    byId('spd-go').addEventListener('click', () => starten());
    byId('spd-kalibrieren').addEventListener('click', async () => {
      const r = await post({ aktion: 'kalibrieren' });
      app().toast((r && (r.text || r.error)) || 'Erledigt.', r && r.ok ? 'ok' : 'error', 6000);
    });
    byId('spd-modus').addEventListener('click', (e) => {
      const b = e.target.closest('[data-modus]');
      if (b) setModus(b.dataset.modus);
    });
    modal.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); schliessen(true); }
    });
    modal.addEventListener('click', (e) => { if (e.target === modal) schliessen(true); });
  }
  const sbKnopf = byId('sb-spiel');
  if (sbKnopf) sbKnopf.addEventListener('click', () => (st && st.aktiv ? anhalten() : oeffnen({})));
  const stopKnopf = byId('sp-stop');
  if (stopKnopf) stopKnopf.addEventListener('click', () => anhalten());

  // ---------------------------------------------------------------------
  // Bericht: Karte (von app.js) + bis zu 5 Bilder des Spielfensters
  // ---------------------------------------------------------------------
  function bericht(text, bilder) {
    const karte = app().card('ok', text);
    const liste = (Array.isArray(bilder) ? bilder : []).filter((b) => b && /^\/api\/bild\/s\/[A-Za-z0-9_-]{1,100}\.(png|jpe?g|webp|gif)$/.test(String(b.url || '')));
    if (!karte || !liste.length) return;
    const ziel = karte.querySelector('.card-body') || karte;
    const leiste = document.createElement('div');
    leiste.className = 'spiel-bilder';
    for (const b of liste.slice(0, 5)) {
      const a = document.createElement('a');
      a.href = b.url + '?t=' + encodeURIComponent(TOKEN);
      a.target = '_blank';
      a.rel = 'noopener';
      const img = document.createElement('img');
      img.src = a.href;
      img.alt = 'Bild aus dem Spiel';
      img.loading = 'lazy';
      a.append(img);
      leiste.append(a);
    }
    ziel.append(leiste);
  }

  // ---------------------------------------------------------------------
  // Von app.js aufgerufen
  // ---------------------------------------------------------------------
  window.NovaSpiel = Object.freeze({
    zustand(state) {
      if (!state || typeof state !== 'object') return;
      st = state.spiel && typeof state.spiel === 'object' ? state.spiel : null;
      render();
    },
    oeffnen(opts) { oeffnen(opts || {}); },
    bericht(text, bilder) { bericht(String(text || ''), bilder); },
  });
})();
