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
  const QUELLE_TEXT = { bildschirm: 'Bildschirm', webcam: 'Webcam', handy: 'Handy-Kamera' };
  const HANDY_ZUSTAND = { wartet: 'wartet aufs Handy', verbunden: 'verbunden', getrennt: 'getrennt', fehler: 'Fehler' };

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
        const handy = st.handy && typeof st.handy === 'object' ? st.handy : null;
        byId('sb2-quelle').textContent = quellen.join(' + ') +
          (handy && HANDY_ZUSTAND[handy.zustand] ? ' (' + HANDY_ZUSTAND[handy.zustand] + ')' : '');
        const hb = byId('sb2-handy');
        if (hb) hb.hidden = !(st.quellen || []).includes('handy');
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
    const q = quelle || (st && st.wunsch) || '';
    if (q === 'handy') { handyDialog(true); return; } // das Handy braucht den QR-Code
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
      if (quelle === 'handy') { handyDialog(true); return; }
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
      'Bildschirm (oder durch deine Webcam bzw. die Kamera deines Handys). Ein kleines Programm auf deinem PC erkennt Veränderungen sofort. ' +
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
      if (quelle === 'handy') { handyKoppeln(true); return; }
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
  // Handy als Kamera: QR-Code, Code, Ablauf, Zustand. Link/Code kommen NUR aus der Antwort auf
  // "handy_koppeln" und werden beim Schließen oder Verbinden sofort wieder aus der Seite entfernt.
  // ---------------------------------------------------------------------
  const hModal = byId('handy-modal');
  const handy = { ablauf: 0, timer: 0, zurueck: null, fwLaeuft: false };

  function handyGeheimnisWeg() {
    const bild = byId('hd-qr-bild');
    if (bild) { bild.removeAttribute('src'); bild.hidden = true; }
    if (byId('hd-link')) byId('hd-link').value = '';
    if (byId('hd-code')) byId('hd-code').textContent = '';
    if (byId('hd-qr')) byId('hd-qr').hidden = true;
    handy.ablauf = 0;
  }

  function handyRender() {
    if (!hModal || hModal.hidden) return;
    const name = app().name();
    const h = st && st.handy && typeof st.handy === 'object' ? st.handy : null;
    const zustand = h ? String(h.zustand || '') : '';
    const status = byId('hd-status');
    let text = 'Noch nicht gekoppelt.';
    if (zustand === 'wartet') text = 'Wartet auf dein Handy – Code scannen.';
    else if (zustand === 'verbunden') text = 'Verbunden – ' + name + ' sieht durch dein Handy.';
    else if (zustand === 'getrennt') text = 'Getrennt.' + (h && h.fehler ? ' ' + satz(h.fehler) : '') + ' „Neu koppeln“ startet von vorn.';
    else if (zustand === 'fehler') text = h && h.gescheitert ? 'Keine Verbindung zum Handy.' : 'Fehler: ' + satz(h && h.fehler ? h.fehler : 'unbekannt');
    if (zustand === 'verbunden') handyGeheimnisWeg(); // gekoppelt: Link/QR nicht mehr zeigen
    const rest = handy.ablauf ? Math.max(0, Math.round(handy.ablauf - Date.now() / 1000)) : 0;
    const cd = byId('hd-countdown');
    if (handy.ablauf && zustand !== 'verbunden') {
      cd.textContent = rest > 0 ? 'Noch ' + Math.floor(rest / 60) + ':' + String(rest % 60).padStart(2, '0') +
        ' Minuten gültig.' : 'Abgelaufen – bitte „Neu koppeln“.';
      if (rest <= 0) { handyGeheimnisWeg(); text = 'Die Kopplung ist abgelaufen.'; }
    } else cd.textContent = '';
    status.textContent = text;
    byId('hd-beenden').hidden = !(st && (st.quellen || []).includes('handy'));
    // Genauer Grund (von Nova am PC ermittelt) + ein konkreter Tipp
    const gescheitert = !!(h && h.gescheitert && zustand === 'fehler');
    byId('hd-grund').hidden = !gescheitert;
    byId('hd-grund-text').textContent = gescheitert ? satz(h.fehler || '') : '';
    byId('hd-tipp').textContent = gescheitert && h.tipp ? 'Tipp: ' + satz(h.tipp) : '';
    const fw = h && h.firewall && typeof h.firewall === 'object' ? h.firewall : {};
    const fwBtn = byId('hd-firewall');
    fwBtn.hidden = !(fw.anbieten && (gescheitert || zustand === 'wartet' || zustand === 'getrennt'));
    if (!handy.fwLaeuft) fwBtn.disabled = false;
    fwBtn.classList.toggle('primary', gescheitert);
    fwBtn.classList.toggle('ghost', !gescheitert);
    const fwOk = byId('hd-firewall-ok');
    fwOk.hidden = !(fw.frei && zustand !== 'verbunden');
    fwOk.textContent = fw.frei ? '✓ Windows-Firewall ist für ' + name + ' freigegeben.' : '';
  }

  function satz(text) {
    const t = String(text || '').trim();
    return !t || /[.!?…)“]$/.test(t) ? t : t + '.';
  }

  async function handyFirewall() {
    const btn = byId('hd-firewall');
    if (handy.fwLaeuft) return;
    handy.fwLaeuft = true;
    btn.disabled = true;
    handyFehler('');
    const alt = btn.textContent;
    btn.textContent = 'Bitte die Windows-Abfrage bestätigen …';
    try {
      const r = await post('/api/kamera/firewall', {});
      if (r && r.sehen) { st = r.sehen; render(); }
      if (!r || !r.ok) handyFehler((r && r.error) || 'Die Firewall-Freigabe ging nicht.');
    } finally {
      handy.fwLaeuft = false;
      btn.textContent = alt;
      btn.disabled = false;
      handyRender();
    }
  }

  function handyFehler(text) {
    const el = byId('hd-fehler');
    if (!el) return;
    el.textContent = text || '';
    el.hidden = !text;
  }

  async function handyKoppeln(einverstanden) {
    handyFehler('');
    byId('hd-status').textContent = 'Kopplung wird vorbereitet …';
    const r = await post('/api/sehen', { aktion: 'handy_koppeln', einverstanden: einverstanden === true ? true : undefined });
    if (r && r.sehen) { st = r.sehen; render(); }
    if (r && r.zustimmung) { handySchliessen(); oeffneZustimmung('handy'); return; }
    if (!r || !r.ok) { handyFehler((r && r.error) || 'Die Handy-Kamera ging nicht.'); handyRender(); return; }
    if (hModal.hidden) return; // inzwischen geschlossen: nichts mehr zeigen
    const bild = byId('hd-qr-bild');
    if (typeof r.svg === 'string' && r.svg.trim().startsWith('<svg')) {
      // als Bild (data:-Adresse) – nie als HTML in die Seite
      bild.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(r.svg);
      bild.hidden = false;
    } else bild.hidden = true;
    byId('hd-hinweis').textContent = String(r.hinweis || '');
    byId('hd-code').textContent = String(r.code || '–');
    byId('hd-link').value = String(r.link || '');
    byId('hd-qr').hidden = false;
    handy.ablauf = Number(r.ablauf) || 0;
    handyRender();
  }

  function handyDialog(koppeln) {
    if (!hModal) return;
    if (hModal.hidden) {
      handy.zurueck = document.activeElement;
      handyGeheimnisWeg();
      handyFehler('');
      hModal.hidden = false;
      clearInterval(handy.timer);
      handy.timer = setInterval(handyRender, 1000);
      const neu = byId('hd-neu');
      if (neu) neu.focus();
    }
    handyRender();
    const h = st && st.handy;
    if (koppeln && !(h && h.zustand === 'verbunden')) handyKoppeln(false);
  }

  function handySchliessen() {
    if (!hModal || hModal.hidden) return;
    hModal.hidden = true;
    clearInterval(handy.timer);
    handyGeheimnisWeg();
    if (handy.zurueck && typeof handy.zurueck.focus === 'function') handy.zurueck.focus();
    handy.zurueck = null;
  }

  if (hModal) {
    byId('hd-neu').addEventListener('click', () => handyKoppeln(false));
    byId('hd-firewall').addEventListener('click', () => handyFirewall());
    byId('hd-schliessen').addEventListener('click', () => handySchliessen());
    byId('hd-beenden').addEventListener('click', async () => {
      handySchliessen();
      await anfrage({ aktion: 'handy_beenden' });
    });
    byId('hd-link').addEventListener('focus', (e) => e.target.select());
    hModal.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); handySchliessen(); }
    });
    hModal.addEventListener('click', (e) => { if (e.target === hModal) handySchliessen(); });
  }
  const handyBtn = byId('sb2-handy');
  if (handyBtn) handyBtn.addEventListener('click', () => handyDialog(false));

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
      handyRender();
    },
    handyDialog(koppeln) { handyDialog(koppeln === true); },
  });
})();
