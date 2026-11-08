/* KI-App – Live-Sehen: Band „Nova sieht zu“, Schalter, Zustimmung und die Webcam.
   Bekommt den Zustand von app.js (NovaSehen.zustand(state)) und spricht selbst mit
   /api/sehen und /api/kamera/bild. Die Webcam läuft nur, solange der Server es will
   (state.sehen.kamera_gewuenscht) – Bilder gehen nur in den Arbeitsspeicher der KI,
   nie auf die Festplatte. Kein Bild verlässt den PC, außer an dein KI-Gehirn. */
(() => {
  'use strict';

  const TOKEN = new URLSearchParams(location.search).get('t') || '';
  const byId = (id) => document.getElementById(id);
  const app = () => window.NovaApp || { toast: () => {}, name: () => 'Nova', providerName: () => '' };

  const KAMERA_TAKT = 1000;        // ein Bild pro Sekunde
  const KAMERA_BREITE = 640;       // verkleinert (spart Rechenzeit und Kosten)
  const KAMERA_GUETE = 0.7;
  const QUELLE_TEXT = { bildschirm: 'Bildschirm', webcam: 'Webcam' };

  async function post(path, body) {
    try {
      const r = await fetch(path, {
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

  let st = null;          // state.sehen vom Server
  let provider = '';
  let busy = false;       // ein Klick nach dem anderen

  function eur(v) {
    return (Math.max(0, Number(v) || 0)).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }

  function setSwitch(el, on) { if (el) el.setAttribute('aria-checked', on ? 'true' : 'false'); }

  // ---------------------------------------------------------------------
  // Anzeige
  // ---------------------------------------------------------------------
  function render() {
    const name = app().name();
    const an = !!(st && st.aktiv);
    const band = byId('sehen-band');
    if (band) {
      band.hidden = !an;
      if (an) {
        const mode = st.pausiert || st.abwesend ? 'pause' : st.privat ? 'privat' : 'an';
        band.dataset.mode = mode;
        byId('sb2-title').textContent = st.pausiert ? name + ' schaut gerade nicht hin'
          : st.abwesend ? name + ' schaut nicht hin, solange du weg bist'
            : st.privat ? 'Privates Fenster – ' + name + ' schaut weg' : name + ' sieht zu';
        const quellen = (Array.isArray(st.quellen) ? st.quellen : []).map((q) => QUELLE_TEXT[q] || q);
        byId('sb2-quelle').textContent = quellen.join(' + ');
        const n = Number(st.weckungen_stunde) || 0;
        byId('sb2-anzahl').textContent = (n === 1 ? '1 Hinweis' : n + ' Hinweise') + ' diese Stunde';
        byId('sb2-kosten').textContent = st.kostenlos ? 'kostenlos' : eur(st.eur_stunde) + ' diese Stunde';
        byId('sb2-last').textContent = st.letztes ? 'Zuletzt: ' + st.letztes : (st.hinweis || '');
        const pause = byId('sb2-pause');
        pause.textContent = st.pausiert ? 'Weiter' : 'Pause';
        pause.title = st.pausiert ? 'Wieder hinschauen (F4)' : 'Sofort wegschauen (F4' +
          (st.hotkey && (st.quellen || []).includes('bildschirm') ? ' oder ' + st.hotkey : '') + ')';
      }
    }
    setSwitch(byId('sw-sehen'), an);
    setSwitch(byId('sec-sw-sehen'), an);
    const sub = byId('sub-sehen');
    if (sub) sub.textContent = an ? (st.pausiert ? 'Pause – schaut gerade nicht hin' : 'schaut gerade zu')
      : 'schaut zu und meldet sich von selbst';
    const card = byId('sec-sehen');
    if (card) {
      card.dataset.state = an ? 'an' : 'aus';
      byId('sec-sehen-badge').textContent = an ? (st.pausiert ? 'Pause' : 'An') : 'Aus';
      const wunsch = st && st.wunsch ? String(st.wunsch) : 'auto';
      for (const b of byId('sec-sehen-quelle').querySelectorAll('[data-quelle]')) {
        b.setAttribute('aria-checked', b.dataset.quelle === wunsch ? 'true' : 'false');
        if (b.dataset.quelle === 'bildschirm' || b.dataset.quelle === 'beides') {
          b.disabled = !!(st && st.bildschirm_moeglich === false);
        }
        if (b.dataset.quelle === 'webcam' || b.dataset.quelle === 'beides') {
          b.title = kamera.vorhanden === false ? 'Keine Webcam gefunden' : '';
        }
      }
      const hint = byId('sec-sehen-hint');
      let text = st && st.hinweis ? String(st.hinweis) : '';
      if (!text && st && st.bildschirm_moeglich === false) {
        text = 'Den Bildschirm kann ' + name + ' nur unter Windows sehen – hier geht nur die Webcam.';
      }
      hint.textContent = text;
      hint.hidden = !text;
    }
  }

  // ---------------------------------------------------------------------
  // Ein / Aus / Pause / Quelle
  // ---------------------------------------------------------------------
  async function anfrage(body) {
    if (busy) return null;
    busy = true;
    try {
      const r = await post('/api/sehen', body);
      if (r && r.sehen) { st = r.sehen; render(); kameraAbgleich(); }
      return r;
    } finally {
      busy = false;
    }
  }

  async function einschalten(quelle) {
    if (st && st.zustimmung_noetig) { oeffneZustimmung(quelle); return; }
    const r = await anfrage({ aktion: 'an', quelle: quelle || undefined });
    if (r && r.zustimmung) { oeffneZustimmung(quelle); return; }
    if (r && !r.ok) app().toast(r.error || 'Live-Sehen ging nicht.', 'error', 6000);
  }

  async function umschalten() {
    if (st && st.aktiv) {
      const r = await anfrage({ aktion: 'aus' });
      if (r && r.ok) app().toast('Live-Sehen ist aus.', 'ok');
    } else einschalten(null);
  }

  async function pauseUmschalten() {
    if (!st || !st.aktiv) return;
    await anfrage({ aktion: st.pausiert ? 'weiter' : 'pause' });
  }

  for (const id of ['sw-sehen', 'sec-sw-sehen']) {
    const el = byId(id);
    if (el) el.addEventListener('click', (e) => { e.stopPropagation(); umschalten(); });
  }
  const row = byId('row-sehen');
  if (row) row.addEventListener('click', () => umschalten());
  const pauseBtn = byId('sb2-pause');
  if (pauseBtn) pauseBtn.addEventListener('click', () => pauseUmschalten());
  const stopBtn = byId('sb2-stop');
  if (stopBtn) stopBtn.addEventListener('click', () => { if (st && st.aktiv) umschalten(); });
  const seg = byId('sec-sehen-quelle');
  if (seg) {
    seg.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-quelle]');
      if (!b || b.disabled) return;
      const quelle = b.dataset.quelle;
      if (st && st.aktiv) {
        const r = await anfrage({ aktion: 'quelle', quelle });
        if (r && !r.ok) app().toast(r.error || 'Das ging nicht.', 'error', 6000);
      } else {
        await anfrage({ aktion: 'quelle', quelle });
      }
    });
  }

  // F4 = sofort wegschauen / wieder hinschauen (F3 ist die Suche des Fensters)
  document.addEventListener('keydown', (e) => {
    if (e.key === 'F4' && !e.altKey && !e.ctrlKey && st && st.aktiv) {
      e.preventDefault();
      pauseUmschalten();
    }
  });

  // ---------------------------------------------------------------------
  // Zustimmung (beim ersten Mal und nach einem Gehirn-Wechsel)
  // ---------------------------------------------------------------------
  const zModal = byId('sehen-modal');
  let zQuelle = null;
  let zZurueck = null;

  function li(text, fett) {
    const el = document.createElement('li');
    if (fett) { const b = document.createElement('b'); b.textContent = fett; el.append(b, ' '); }
    el.append(text);
    return el;
  }

  function oeffneZustimmung(quelle) {
    if (!zModal) return;
    zQuelle = quelle || null;
    zZurueck = document.activeElement;
    const name = app().name();
    provider = app().providerName();
    const lokal = /ollama/i.test(provider);
    const gehirn = provider || 'dein KI-Gehirn';
    byId('sd-intro').textContent = 'Wenn du Live-Sehen einschaltest, schaut ' + name + ' ständig auf deinen ' +
      'Bildschirm (oder durch deine Webcam). Ein kleines Programm auf deinem PC erkennt Veränderungen sofort. ' +
      'Wenn etwas Wichtiges passiert, schickt ' + name + ' einen verkleinerten Ausschnitt oder den erkannten ' +
      'Text an dein KI-Gehirn (' + gehirn + ').' + (lokal ? ' Mit Ollama bleibt alles auf deinem PC.'
      : ' Dort gelten die Datenschutzregeln des Anbieters.');
    const taste = st && st.hotkey ? st.hotkey : 'Strg+Alt+Umschalt+S';
    const liste = byId('sd-list');
    liste.replaceChildren(
      li(name + ' speichert keine Bilder auf deinem PC und nichts davon in ihrem Gedächtnis. Was sie nur sieht, ' +
        'vergisst sie nach einer Minute. Wozu sie sich meldet (Text und ggf. der Ausschnitt), bleibt bis zum Ende ' +
        'des Gesprächs im Gesprächsverlauf (/neu leert ihn).', 'Nichts gespeichert:'),
      li('Passwortfelder, Passwort-Manager, private Browserfenster und ' + name + 's eigenes Fenster werden nicht ' +
        'angesehen. Weitere Programme kannst du in den Einstellungen ausschließen.', 'Tabu:'),
      li('Solange ' + name + ' zusieht, steht oben „' + name + ' sieht zu“. Mit „Pause“, F4 oder ' + taste +
        ' (überall in Windows) schaut sie sofort weg.', 'Immer sichtbar:'),
      li('Zeig keine Bankdaten, Gesundheitsdaten oder Geheimnisse anderer Menschen, während Live-Sehen an ist.', 'Bitte:'),
      li(lokal || (st && st.kostenlos) ? 'Mit Ollama kostet es nichts – nur etwas Rechenleistung.'
        : 'Es kostet etwas Geld (höchstens ' + eur(st && st.max_eur != null ? st.max_eur : 0.3) +
          ' pro Stunde, einstellbar) und etwas Rechenleistung.', 'Kosten:'),
      li(name + ' handelt nicht von selbst auf deinem PC. Sie sagt dir nur, was ihr auffällt.', 'Nur Worte:'),
    );
    zModal.hidden = false;
    const ok = byId('sd-ok');
    if (ok) ok.focus();
  }

  function schliesseZustimmung() {
    if (!zModal || zModal.hidden) return;
    zModal.hidden = true;
    if (zZurueck && typeof zZurueck.focus === 'function') zZurueck.focus();
    zZurueck = null;
  }

  if (zModal) {
    byId('sd-cancel').addEventListener('click', () => { schliesseZustimmung(); app().toast('Live-Sehen bleibt aus.', 'info'); });
    byId('sd-ok').addEventListener('click', async () => {
      const quelle = zQuelle;
      schliesseZustimmung();
      const r = await anfrage({ aktion: 'an', einverstanden: true, quelle: quelle || undefined });
      if (r && !r.ok) app().toast(r.error || 'Live-Sehen ging nicht.', 'error', 6000);
    });
    zModal.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); schliesseZustimmung(); }
    });
    zModal.addEventListener('click', (e) => { if (e.target === zModal) schliesseZustimmung(); });
  }

  // ---------------------------------------------------------------------
  // Webcam (getUserMedia – die Seite http://127.0.0.1:<port> ist ein sicherer Ursprung)
  // ---------------------------------------------------------------------
  const kamera = { vorhanden: null, gemeldet: null, stream: null, startet: false, timer: 0, unterwegs: false,
    video: null, canvas: null, fehlerZeit: 0 };

  async function kameraSuchen() {
    const md = navigator.mediaDevices;
    let da = false;
    if (md && typeof md.enumerateDevices === 'function') {
      try {
        const geraete = await md.enumerateDevices();
        da = geraete.some((g) => g && g.kind === 'videoinput');
      } catch (_) { da = false; }
    }
    kamera.vorhanden = da;
    if (kamera.gemeldet !== da) {
      kamera.gemeldet = da;
      post('/api/sehen', { aktion: 'kamera', vorhanden: da });
    }
  }

  function kameraFehlerText(err) {
    const n = err && err.name ? String(err.name) : '';
    if (n === 'NotFoundError' || n === 'OverconstrainedError') return 'Ich finde keine Webcam.';
    if (n === 'NotReadableError' || n === 'AbortError') {
      return 'Die Webcam lässt sich nicht öffnen – benutzt sie gerade ein anderes Programm? Oder Windows ' +
        'blockiert sie: Einstellungen → Datenschutz und Sicherheit → Kamera → „Kamerazugriff“ und ' +
        '„Desktop-Apps den Zugriff auf die Kamera erlauben“ einschalten.';
    }
    if (n === 'NotAllowedError' || n === 'SecurityError') {
      return 'Die Webcam ist blockiert. Prüfe in Windows: Einstellungen → Datenschutz und Sicherheit → Kamera → ' +
        '„Kamerazugriff“ und „Desktop-Apps den Zugriff auf die Kamera erlauben“ einschalten. (Im Browser-Fenster: ' +
        'die Kamera für diese Seite erlauben.)';
    }
    return 'Die Webcam ging nicht (' + (n || 'unbekannter Fehler') + ').';
  }

  async function kameraStarten() {
    const md = navigator.mediaDevices;
    if (!md || typeof md.getUserMedia !== 'function') {
      post('/api/sehen', { aktion: 'kamera', fehler: 'Dieses Fenster kann keine Webcam benutzen.' });
      return;
    }
    kamera.startet = true;
    try {
      const stream = await md.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 10, max: 15 } }, audio: false,
      });
      if (!(st && st.kamera_gewuenscht)) { // inzwischen wieder aus
        for (const t of stream.getTracks()) t.stop();
        return;
      }
      kamera.stream = stream;
      if (!kamera.video) {
        kamera.video = document.createElement('video');
        kamera.video.muted = true;
        kamera.video.playsInline = true;
        kamera.video.setAttribute('aria-hidden', 'true');
      }
      kamera.video.srcObject = stream;
      try { await kamera.video.play(); } catch (_) { /* spielt trotzdem */ }
      clearInterval(kamera.timer);
      kamera.timer = setInterval(kameraBild, KAMERA_TAKT);
      for (const t of stream.getVideoTracks()) {
        t.addEventListener('ended', () => {
          kameraStoppen();
          post('/api/sehen', { aktion: 'kamera', fehler: 'Die Webcam wurde getrennt.' });
        });
      }
    } catch (err) {
      const text = kameraFehlerText(err);
      app().toast(text, 'error', 9000);
      post('/api/sehen', { aktion: 'kamera', fehler: text });
    } finally {
      kamera.startet = false;
    }
  }

  function kameraStoppen() {
    clearInterval(kamera.timer);
    kamera.timer = 0;
    if (kamera.stream) {
      for (const t of kamera.stream.getTracks()) { try { t.stop(); } catch (_) { /* schon aus */ } }
    }
    kamera.stream = null;
    if (kamera.video) kamera.video.srcObject = null;
  }

  function kameraBild() {
    const v = kamera.video;
    if (!kamera.stream || !v || kamera.unterwegs || v.readyState < 2 || !v.videoWidth) return;
    const f = Math.min(1, KAMERA_BREITE / v.videoWidth);
    const w = Math.max(16, Math.round(v.videoWidth * f));
    const hgt = Math.max(16, Math.round(v.videoHeight * f));
    if (!kamera.canvas) kamera.canvas = document.createElement('canvas');
    const c = kamera.canvas;
    c.width = w;
    c.height = hgt;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(v, 0, 0, w, hgt);
    kamera.unterwegs = true;
    c.toBlob(async (blob) => {
      try {
        if (!blob || !kamera.stream) return;
        const r = await fetch('/api/kamera/bild', {
          method: 'POST', headers: { 'Content-Type': 'image/jpeg', 'X-KI-Token': TOKEN }, body: blob,
        });
        let data = null;
        try { data = await r.json(); } catch (_) { data = null; }
        if (data && data.ok === false && data.weiter === false) kameraStoppen();
      } catch (_) {
        /* Verbindung kurz weg - naechstes Bild */
      } finally {
        kamera.unterwegs = false;
      }
    }, 'image/jpeg', KAMERA_GUETE);
  }

  function kameraAbgleich() {
    const will = !!(st && st.kamera_gewuenscht);
    if (will && !kamera.stream && !kamera.startet) kameraStarten();
    else if (!will && kamera.stream) kameraStoppen();
  }

  if (navigator.mediaDevices && typeof navigator.mediaDevices.addEventListener === 'function') {
    navigator.mediaDevices.addEventListener('devicechange', () => kameraSuchen());
  }
  window.addEventListener('pagehide', () => kameraStoppen());

  // ---------------------------------------------------------------------
  // Von app.js aufgerufen
  // ---------------------------------------------------------------------
  let gesucht = false;
  window.NovaSehen = Object.freeze({
    zustand(state) {
      if (!state || typeof state !== 'object') return;
      st = state.sehen && typeof state.sehen === 'object' ? state.sehen : null;
      provider = String(state.provider_name || '');
      if (!gesucht) { gesucht = true; kameraSuchen(); }
      render();
      kameraAbgleich();
    },
  });
})();
