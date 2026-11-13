/* KI-App – kleine Hilfen ohne Seite (kein DOM), damit sie auch in Node getestet werden koennen.
   Genutzt von app.js fuer:
     * Bilder anhaengen (Chat, Feedback): erlaubte Typen, Zielgroesse, PNG oder JPEG, Namen
     * Bilder vom Server: nur eigene Adressen /api/bild/<h|e>/<name> (+ ?t=TOKEN)
     * Feedback: Sterne, Art, Nachfrage-Karte (wann sie erscheinen darf)
     * Bildgenerator-Einstellungen (AI Horde / Cloudflare)
   Im Fenster: window.NovaHelfer. In Node: require('.../helfer.js'). */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module && module.exports) module.exports = api;
  else root.NovaHelfer = api;
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

  // ---------------------------------------------------------------------
  // Bilder anhaengen
  // ---------------------------------------------------------------------
  const ERLAUBT = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
  const ENDUNG = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp' };
  const NACH_ENDUNG = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', jfif: 'image/jpeg', gif: 'image/gif', webp: 'image/webp' };
  const MAX_KANTE = 1568;            // Chat: lange Seite hoechstens (wie [bilder] max_kantenlaenge)
  const MAX_KANTE_FEEDBACK = 1920;   // Feedback: Bildschirmfotos sollen gut lesbar bleiben
  const JPEG_GUETE = 0.85;
  const MAX_DATEI = 30 * 1024 * 1024;   // groessere Dateien gar nicht erst lesen
  const BEHALTEN_BIS = 1536 * 1024;     // kleine Bilder in passender Groesse unveraendert schicken
  const MAX_CHAT = 10;                  // Bilder pro Nachricht (wie [bilder] max_bilder_pro_nachricht)
  const MAX_FEEDBACK = 5;
  const CHAT_GESAMT = 36 * 1000 * 1000;     // Zeichen (data:-Adressen) – Server nimmt hoechstens 40 MB
  const FEEDBACK_GESAMT = 13 * 1000 * 1000; // ca. 10 MB Bilder zusammen (Grenze des Feedback-Postfachs)
  const RE_URL = /^\/api\/bild\/[he]\/[A-Za-z0-9_-]{1,100}\.(?:png|jpe?g|webp|gif)$/;
  const RE_DATA = /^data:(image\/(?:png|jpeg|gif|webp));base64,[A-Za-z0-9+/]+=*$/;

  /** Erlaubter Bild-Typ ("image/png" …) aus dem Dateityp, sonst aus der Endung – sonst "". */
  function typ(mime, name) {
    const m = String(mime == null ? '' : mime).toLowerCase().split(';')[0].trim();
    if (m === 'image/jpg' || m === 'image/pjpeg') return 'image/jpeg';
    if (ERLAUBT.includes(m)) return m;
    if (m && m !== 'application/octet-stream') return ''; // z.B. image/svg+xml, image/heic, text/plain
    const e = String(name == null ? '' : name).toLowerCase().match(/\.([a-z0-9]{1,5})$/);
    return e && own(NACH_ENDUNG, e[1]) ? NACH_ENDUNG[e[1]] : '';
  }

  /** Zielgroesse: lange Seite hoechstens maxKante, Seitenverhaeltnis bleibt, nie groesser als vorher. */
  function zielMass(w, h, maxKante) {
    const W = Math.max(1, Math.round(Number(w) || 1));
    const H = Math.max(1, Math.round(Number(h) || 1));
    const max = Math.max(1, Math.round(Number(maxKante) || MAX_KANTE));
    const lang = Math.max(W, H);
    if (lang <= max) return { w: W, h: H, skala: 1 };
    const s = max / lang;
    return {
      w: Math.min(max, Math.max(1, Math.round(W * s))),
      h: Math.min(max, Math.max(1, Math.round(H * s))),
      skala: s,
    };
  }

  /** Original unveraendert schicken? Nur, wenn es schon passt (Typ, Groesse) – GIF wird immer
   *  zum Standbild (erstes Bild), damit der Server und das Modell keine Animation bekommen. */
  function behalten(info) {
    const i = info || {};
    const t = typ(i.typ);
    const max = Number(i.maxKante) || MAX_KANTE;
    const bytes = Number(i.bytes) || 0;
    return !!t && t !== 'image/gif' && Math.max(Number(i.w) || 0, Number(i.h) || 0) <= max &&
      bytes > 0 && bytes <= (Number(i.maxBytes) || BEHALTEN_BIS);
  }

  /** Nach dem Verkleinern: PNG, wenn das Bild durchsichtige Stellen hat oder PNG kleiner ist – sonst JPEG. */
  function kodierung(transparent, pngLaenge, jpegLaenge) {
    if (transparent) return 'image/png';
    const p = Number(pngLaenge) || 0;
    const j = Number(jpegLaenge) || 0;
    if (j <= 0) return 'image/png';
    return p > 0 && p <= j ? 'image/png' : 'image/jpeg';
  }

  /** Hat das Bild (RGBA-Bytes) durchsichtige Pixel? schritt: nur jedes n-te Pixel ansehen (schnell). */
  function hatTransparenz(rgba, schritt) {
    if (!rgba || !rgba.length) return false;
    const step = Math.max(1, Math.floor(Number(schritt) || 1)) * 4;
    for (let i = 3; i < rgba.length; i += step) if (rgba[i] < 255) return true;
    return false;
  }

  /** Schritt fuer hatTransparenz: hoechstens ca. 250 000 Pixel pruefen. */
  const pruefSchritt = (w, h) => Math.max(1, Math.floor(((Number(w) || 1) * (Number(h) || 1)) / 250000));

  /** Typ einer data:-Adresse ("image/png") oder "". */
  function dataUrlTyp(url) {
    const m = /^data:([a-z0-9.+/-]+);base64,/i.exec(String(url == null ? '' : url));
    return m ? m[1].toLowerCase() : '';
  }

  /** Ungefaehre Groesse der Bytes in einer data:-Adresse. */
  function dataUrlBytes(url) {
    const s = String(url == null ? '' : url);
    const i = s.indexOf(',');
    if (i < 0) return 0;
    let pad = 0;
    if (s.endsWith('==')) pad = 2;
    else if (s.endsWith('=')) pad = 1;
    return Math.max(0, Math.floor(((s.length - i - 1) * 3) / 4) - pad);
  }

  /** data:-Adresse mit dem richtigen Bild-Typ (FileReader schreibt sonst evtl. "application/octet-stream"). */
  function mitTyp(dataUrl, mime) {
    const s = String(dataUrl == null ? '' : dataUrl);
    const i = s.indexOf(';base64,');
    if (!s.startsWith('data:') || i < 0 || !ERLAUBT.includes(mime)) return '';
    return 'data:' + mime + s.slice(i);
  }

  /** Ist das eine Bild-data:-Adresse, wie der Server sie annimmt? */
  const istBildDaten = (url) => RE_DATA.test(String(url == null ? '' : url));

  /** Dateiname fuer den Server/das Modell: ohne Pfad und Steuerzeichen, passende Endung. */
  function dateiName(name, mime) {
    let n = String(name == null ? '' : name).split(/[\\/]/).pop();
    n = n.replace(/\s+/g, ' ').replace(/[\u0000-\u001f\u007f"<>|:*?]/g, '').trim();
    let base = n.replace(/\.[A-Za-z0-9]{1,5}$/, '').trim();
    if (!base || /^image$/i.test(base)) base = 'bild';
    if (base.length > 80) base = base.slice(0, 80).trim();
    return base + '.' + (own(ENDUNG, mime) ? ENDUNG[mime] : 'png');
  }

  /** Name zum Anzeigen (kurz, ohne Steuerzeichen); sonst der Dateiname aus der Adresse. */
  function anzeigeName(name, url) {
    let n = String(name == null ? '' : name).split(/[\\/]/).pop();
    n = n.replace(/\s+/g, ' ').replace(/[\u0000-\u001f\u007f]/g, '').trim();
    if (!n && url) n = String(url).split(/[?#]/)[0].split('/').pop() || '';
    if (n.length > 120) n = n.slice(0, 119) + '…';
    return n || 'Bild';
  }

  /** Eigene Bild-Adresse des Servers mit Zugangsschluessel – sonst "" (fremde Adressen nie). */
  function bildUrl(url, token) {
    const s = String(url == null ? '' : url).split(/[?#]/)[0];
    if (!RE_URL.test(s)) return '';
    return s + '?t=' + encodeURIComponent(String(token == null ? '' : token));
  }

  /** Bilder-Liste vom Server ([{url, name}]) pruefen: nur eigene Adressen, hoechstens max Stueck. */
  function normBilder(list, max) {
    if (!Array.isArray(list)) return [];
    const lim = Math.max(1, Number(max) || 20);
    const out = [];
    for (const it of list) {
      if (!it || typeof it !== 'object') continue;
      const url = String(it.url == null ? '' : it.url).split(/[?#]/)[0];
      if (!RE_URL.test(url)) continue;
      out.push({ url, name: anzeigeName(it.name, url) });
      if (out.length >= lim) break;
    }
    return out;
  }

  /** Anzahl Bilder einer wartenden Nachricht: Liste oder Zahl (state.queue[].images). */
  function anzahlBilder(v) {
    if (Array.isArray(v)) return v.length;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  }

  const bildText = (n) => (n === 1 ? '1 Bild' : n + ' Bilder');

  /** "350 KB" / "1,4 MB" */
  function groesseText(bytes) {
    const b = Math.max(0, Number(bytes) || 0);
    if (b < 1024 * 1024) return Math.max(1, Math.round(b / 1024)) + ' KB';
    return (b / (1024 * 1024)).toLocaleString('de-DE', { maximumFractionDigits: 1 }) + ' MB';
  }

  /** Zusammen zu gross? (Laenge aller data:-Adressen) */
  function gesamtLaenge(items) {
    let n = 0;
    for (const it of items || []) n += it && it.data ? String(it.data).length : 0;
    return n;
  }

  /** Kennung je Nachricht (client_id): damit das Echo vom Server zur eigenen Blase passt. */
  function neueId(zufall) {
    let hex = '';
    const c = typeof crypto !== 'undefined' && crypto && crypto.getRandomValues ? crypto : null;
    if (typeof zufall === 'function') {
      for (let i = 0; i < 8; i++) hex += (Math.floor(zufall() * 256) & 255).toString(16).padStart(2, '0');
    } else if (c) {
      const a = new Uint8Array(8);
      c.getRandomValues(a);
      for (const x of a) hex += x.toString(16).padStart(2, '0');
    } else {
      for (let i = 0; i < 8; i++) hex += Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
    }
    return 'c' + Date.now().toString(36) + '-' + hex;
  }

  /** Schluessel fuer "schon im Verlauf?" (Nachspielen nach dem Laden): Text + Bild-Adressen. */
  function echoSchluessel(text, images) {
    const urls = normBilder(images).map((b) => b.url);
    return String(text == null ? '' : text).trim() + (urls.length ? '\u0001' + urls.join('|') : '');
  }

  /** Text aus der Zwischenablage, der wichtiger ist als ein Bild darin (z.B. Excel: Text UND Bild). */
  const textGewinnt = (text) => !!String(text == null ? '' : text).trim();

  // ---------------------------------------------------------------------
  // Feedback & Bewertung
  // ---------------------------------------------------------------------
  /** Art-Chips: [Wert fuer den Server, Beschriftung, Symbol] */
  const FEEDBACK_ARTEN = [
    ['bewertung', 'Lob/Bewertung', 'star'],
    ['bug', 'Fehler', 'bug'],
    ['idee', 'Idee', 'brain'],
    ['feedback', 'Sonstiges', 'chat'],
  ];
  const STERNE_TEXT = ['', 'Gefällt mir gar nicht', 'Eher nicht so', 'Geht so', 'Gut', 'Super!'];

  /** Sterne 1–5, sonst null */
  function sterne(v) {
    const n = Number(v);
    return Number.isInteger(n) && n >= 1 && n <= 5 ? n : null;
  }

  /** Art fuer den Server (bewertung|bug|idee|feedback) */
  function feedbackArt(v) {
    const s = String(v == null ? '' : v).toLowerCase();
    return FEEDBACK_ARTEN.some((a) => a[0] === s) ? s : 'feedback';
  }

  /** Ist etwas zum Senden da? (Sterne, Text oder Bilder) */
  const feedbackLeer = (stars, text, bilder) => !sterne(stars) && !String(text == null ? '' : text).trim() && !(bilder > 0);

  /** Nachricht fuer POST /api/feedback (Bilder: [{name, data}]). */
  function feedbackDaten(f) {
    const x = f || {};
    const contact = String(x.contact == null ? '' : x.contact).replace(/\s+/g, ' ').trim().slice(0, 200);
    return {
      kind: feedbackArt(x.kind),
      stars: sterne(x.stars),
      text: String(x.text == null ? '' : x.text).trim().slice(0, 20000),
      contact,
      images: (Array.isArray(x.images) ? x.images : []).filter((b) => b && istBildDaten(b.data))
        .slice(0, MAX_FEEDBACK).map((b) => ({ name: dateiName(b.name, dataUrlTyp(b.data)), data: b.data })),
      trigger: x.trigger === 'popup' ? 'popup' : 'menue',
      public: x.public === true && sterne(x.stars) !== null,
      name: x.public === true ? String(x.name == null ? '' : x.name).replace(/\s+/g, ' ').trim().slice(0, 40) : '',
    };
  }

  /** Antwort von GET /api/bewertungen -> {anzahl, schnitt, text, rezensionen} oder null */
  function bewertungAnzeige(r) {
    const b = r && typeof r === 'object' && r.bewertungen && typeof r.bewertungen === 'object' ? r.bewertungen : null;
    if (!b) return null;
    const anzahl = Number(b.anzahl);
    const schnitt = Number(b.schnitt);
    if (!Number.isInteger(anzahl) || anzahl < 1 || !(schnitt >= 1 && schnitt <= 5)) return null;
    const voll = Math.max(0, Math.min(5, Math.round(schnitt)));
    const rezensionen = (Array.isArray(b.oeffentlich) ? b.oeffentlich : []).filter((x) => x && typeof x === 'object'
      && sterne(x.sterne) !== null && typeof x.text === 'string' && x.text.trim()).slice(0, 30).map((x) => ({
      sterne: sterne(x.sterne), text: x.text.trim().slice(0, 600), name: String(x.name || 'Anonym').slice(0, 40),
      datum: /^\d{4}-\d{2}-\d{2}$/.test(String(x.datum || '')) ? String(x.datum) : '' }));
    return {
      anzahl, schnitt, sterne: '★'.repeat(voll) + '☆'.repeat(5 - voll),
      schnittText: schnitt.toFixed(1).replace('.', ','),
      anzahlText: anzahl === 1 ? '1 Bewertung' : anzahl + ' Bewertungen',
      rezensionen,
    };
  }

  /** Antwort von POST /api/feedback -> {art: gesendet|gespeichert|fehler, text} */
  function feedbackErgebnis(r) {
    const o = r && typeof r === 'object' ? r : {};
    const msg = String(o.message == null ? '' : o.message).trim();
    if (o.ok === true && o.status === 'gespeichert') {
      return { art: 'gespeichert', text: msg || 'Dein Feedback ist gespeichert und wird später automatisch gesendet.' };
    }
    if (o.ok === true) return { art: 'gesendet', text: msg || 'Danke! Dein Feedback wurde gesendet.' };
    const err = String(o.error == null ? '' : o.error).trim() || msg;
    return { art: 'fehler', text: err || 'Das Senden hat nicht geklappt. Versuch es bitte gleich noch einmal.' };
  }

  /** Darf die Nachfrage-Karte ("Wie gefällt dir Nova?") jetzt erscheinen?
   *  Nur, wenn sie faellig ist und Nova gerade frei ist: keine Antwort, kein AFK, kein Jarvis,
   *  kein offener Dialog, Schluessel da, Tour erledigt – und du tippst nicht gerade. */
  function nachfrageFrei(z) {
    const s = z || {};
    return s.faellig === true && !s.gezeigt && !s.beendet && !s.busy && !s.afk && !s.jarvis && !s.dialog &&
      !s.tippt && s.schluessel !== false && s.tour !== false && s.bereit === true;
  }

  // ---------------------------------------------------------------------
  // Bildgenerator (Einstellungen in "Gehirn & Schlüssel")
  // ---------------------------------------------------------------------
  const ANBIETER = [
    ['auto', 'Automatisch', 'Cloudflare, wenn es eingerichtet ist – sonst AI Horde.'],
    ['horde', 'AI Horde', 'Kostenlos und ohne Anmeldung. Freiwillige Rechner malen – manchmal mit kurzer Wartezeit.'],
    ['cloudflare', 'Cloudflare', 'Schnell, mit deinem eigenen kostenlosen Schlüssel (mit Tageslimit).'],
  ];
  const AKTIV_TEXT = {
    'AI Horde': 'AI Horde – kostenlos, ohne Anmeldung, manchmal kurze Wartezeit',
    Cloudflare: 'Cloudflare – schnell, mit deinem kostenlosen Schlüssel',
  };

  /** "bilder" aus /api/setup -> {anbieter, cloudflare, aktiv} oder null (aeltere KI ohne Bilder). */
  function normBilderSetup(b) {
    if (!b || typeof b !== 'object' || Array.isArray(b)) return null;
    const a = String(b.anbieter == null ? '' : b.anbieter).toLowerCase();
    const aktiv = String(b.aktiv == null ? '' : b.aktiv).trim();
    return {
      anbieter: ANBIETER.some((x) => x[0] === a) ? a : 'auto',
      cloudflare: b.cloudflare === true,
      aktiv: aktiv === 'Cloudflare' ? 'Cloudflare' : 'AI Horde',
    };
  }

  const aktivText = (aktiv) => (own(AKTIV_TEXT, aktiv) ? AKTIV_TEXT[aktiv] : AKTIV_TEXT['AI Horde']);

  /** Cloudflare-Konto-ID: 32 Zeichen 0-9/a-f (nur ein Hinweis, kein hartes Verbot). */
  const kontoIdOk = (v) => /^[0-9a-f]{32}$/i.test(String(v == null ? '' : v).trim());
  /** API-Token: lang, ohne Leerzeichen (Cloudflare: meist 40 Zeichen). */
  const tokenOk = (v) => /^[A-Za-z0-9_-]{30,200}$/.test(String(v == null ? '' : v).trim());

  /** Was an POST /api/bilder/einstellen geht (nur Felder, die gesetzt sind). */
  function cloudflareDaten(konto, token) {
    const body = {};
    const k = String(konto == null ? '' : konto).trim();
    const t = String(token == null ? '' : token).trim();
    if (k) body.cloudflare_account_id = k;
    if (t) body.cloudflare_token = t;
    return body;
  }

  // ---------------------------------------------------------------------
  // Ollama (kostenlos, auf dem PC) – Daten aus GET /api/ollama und Ereignisse "ollama_pull"
  // ---------------------------------------------------------------------
  const OLLAMA_DOWNLOAD = 'https://ollama.com/download';
  const OLLAMA_MODELLE_SEITE = 'https://ollama.com/search?c=tools';
  const RE_OLLAMA_NAME = /^[A-Za-z0-9][A-Za-z0-9._\-/:]{0,150}$/;
  const ollamaName = (v) => {
    const n = String(v == null ? '' : v).trim();
    return RE_OLLAMA_NAME.test(n) && !n.includes('..') ? n : '';
  };
  const txt = (v, max) => String(v == null ? '' : v).trim().slice(0, max || 200);
  const jaNein = (v) => (v === true ? true : v === false ? false : null);
  const zahl = (v) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Math.round(Number(v)) : 0);

  /** Bytes -> "3,4 GB" / "512 MB" (leer bei 0). */
  function ollamaGroesse(bytes) {
    const b = zahl(bytes);
    if (!b) return '';
    if (b >= 1e9) return (b / 1e9).toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' GB';
    return Math.max(1, Math.round(b / 1e6)).toLocaleString('de-DE') + ' MB';
  }

  /** Fortschritt in Prozent (0–100) oder null (unbekannt). */
  function prozent(v) {
    if (v == null || v === '' || !Number.isFinite(Number(v))) return null;
    return Math.max(0, Math.min(100, Number(v)));
  }

  /** Ereignis "ollama_pull" bzw. "laden" aus /api/ollama -> sauberes Objekt (oder null). */
  function normPull(ev) {
    if (!ev || typeof ev !== 'object' || Array.isArray(ev)) return null;
    const model = ollamaName(ev.model);
    if (!model) return null;
    return {
      model, text: txt(ev.text, 160), prozent: prozent(ev.prozent), erledigt: zahl(ev.erledigt), gesamt: zahl(ev.gesamt),
      fertig: ev.fertig === true, ok: ev.ok === true, abgebrochen: ev.abgebrochen === true, fehler: txt(ev.fehler, 300),
    };
  }

  /** "Lade herunter … 45 % (1,5 GB von 3,4 GB)" */
  function pullText(p) {
    if (!p) return '';
    const base = p.text || 'Lade herunter …';
    if (p.prozent == null || !p.gesamt) return base;
    const pz = Math.floor(p.prozent).toLocaleString('de-DE') + ' %';
    return base + ' ' + pz + ' (' + (ollamaGroesse(p.erledigt) || '0 MB') + ' von ' + ollamaGroesse(p.gesamt) + ')';
  }

  /** GET /api/ollama -> {laeuft, version, installiert, adresse, openai, modelle, empfohlen, modell, ...} oder null. */
  function normOllama(d) {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const adresse = txt(d.adresse, 200);
    const seen = new Set();
    const modelle = (Array.isArray(d.modelle) ? d.modelle : []).filter((m) => m && typeof m === 'object').map((m) => {
      const name = ollamaName(m.name);
      return {
        name, anzeige: txt(m.anzeige, 80) || name, groesse: txt(m.groesse_text, 20) || ollamaGroesse(m.groesse),
        werkzeuge: jaNein(m.werkzeuge), bilder: jaNein(m.sieht_bilder), denkt: jaNein(m.denkt), aktiv: m.aktiv === true,
      };
    }).filter((m) => m.name && !seen.has(m.name) && seen.add(m.name)).slice(0, 60);
    const empfohlen = (Array.isArray(d.empfohlen) ? d.empfohlen : []).filter((m) => m && typeof m === 'object').map((m) => ({
      id: ollamaName(m.id), name: txt(m.name, 60), info: txt(m.info, 140), groesse: txt(m.groesse, 20), ram: txt(m.ram, 60),
      werkzeuge: m.werkzeuge === true, bilder: m.sieht_bilder === true, installiert: m.installiert === true,
    })).filter((m) => m.id).slice(0, 12);
    return {
      laeuft: d.laeuft === true, version: txt(d.version, 30), installiert: jaNein(d.installiert),
      adresse: /^https?:\/\/[^\s"'<>\\]+$/.test(adresse) ? adresse : '', openai: d.openai === true,
      modelle, empfohlen, modell: ollamaName(d.modell), modellDa: d.modell_da === true, fehler: txt(d.fehler, 400),
      laden: normPull(d.laden), aktiv: d.aktiv === true, modelName: txt(d.model_name, 80), kontext: zahl(d.kontext),
    };
  }

  return {
    OLLAMA_DOWNLOAD, OLLAMA_MODELLE_SEITE, ollamaName, ollamaGroesse, normPull, pullText, normOllama,
    ERLAUBT, MAX_KANTE, MAX_KANTE_FEEDBACK, JPEG_GUETE, MAX_DATEI, BEHALTEN_BIS, MAX_CHAT, MAX_FEEDBACK,
    CHAT_GESAMT, FEEDBACK_GESAMT,
    typ, zielMass, behalten, kodierung, hatTransparenz, pruefSchritt, dataUrlTyp, dataUrlBytes, mitTyp,
    istBildDaten, dateiName, anzeigeName, bildUrl, normBilder, anzahlBilder, bildText, groesseText,
    gesamtLaenge, neueId, echoSchluessel, textGewinnt,
    FEEDBACK_ARTEN, STERNE_TEXT, sterne, feedbackArt, feedbackLeer, feedbackDaten, feedbackErgebnis, nachfrageFrei,
    bewertungAnzeige,
    ANBIETER, normBilderSetup, aktivText, kontoIdOk, tokenOk, cloudflareDaten,
  };
}));
