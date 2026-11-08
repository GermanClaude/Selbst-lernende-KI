/* KI-App – Oberflaeche im Browserfenster.
   Reines JavaScript ohne Bibliotheken. Spricht ueber /api/... mit dem Python-Teil.
   Sicherheit: Texte vom Server werden NIE direkt als HTML eingesetzt – der
   Markdown-Renderer unten escaped zuerst alles und baut dann nur eigene Tags. */
(() => {
  'use strict';

  // =====================================================================
  // Grundlagen
  // =====================================================================
  const TOKEN = new URLSearchParams(location.search).get('t') || '';
  const byId = (id) => document.getElementById(id);
  /** Nur eigene Eintraege einer Tabelle (Namen vom Server wie "constructor" sind harmlos). */
  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const pick = (obj, key) => (own(obj, key) ? obj[key] : undefined);

  /** Element bauen; Text immer per textContent (sicher). */
  function h(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = String(text);
    return e;
  }

  /** POST mit JSON und Schluessel; liefert immer ein Objekt mit ok. */
  async function post(path, body) {
    try {
      const r = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-KI-Token': TOKEN },
        body: JSON.stringify(body || {}),
      });
      let data = null;
      try { data = await r.json(); } catch (_) { data = null; }
      if (!data || typeof data !== 'object') {
        return { ok: false, error: r.ok ? 'Unerwartete Antwort von der KI.' : `Fehler ${r.status}` };
      }
      if (!r.ok && data.ok === undefined) data.ok = false;
      return data;
    } catch (_) {
      return { ok: false, error: 'Keine Verbindung zur KI.' };
    }
  }

  async function getJson(path) {
    try {
      const r = await fetch(path, { headers: { 'X-KI-Token': TOKEN } });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) {
      return null;
    }
  }

  // =====================================================================
  // Symbole (feste, eigene SVG-Zeichnungen – kein Fremdtext)
  // =====================================================================
  const ICONS = {
    send: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" stroke="none"/>',
    queue: '<path d="M4 6h12M4 12h8M4 18h8"/><path d="M18 13v8M14 17h8"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="M12 18v4"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>',
    trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    terminal: '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    search: '<circle cx="11" cy="11" r="7.5"/><path d="m21 21-4.3-4.3"/>',
    bookmark: '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>',
    monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    mouse: '<rect x="6" y="3" width="12" height="18" rx="6"/><path d="M12 7v4"/>',
    keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    cpu: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2M15 20v2M2 15h2M2 9h2M20 15h2M20 9h2M9 2v2M9 20v2"/>',
    bot: '<rect x="3" y="8" width="18" height="12" rx="3"/><path d="M12 8V4"/><circle cx="12" cy="3" r="1"/><path d="M9 13v2M15 13v2"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    alertCircle: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    shieldAlert: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4M12 16h.01"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    coins: '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>',
    refresh: '<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    power: '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    contrast: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    arrowDown: '<path d="M12 5v14M19 12l-7 7-7-7"/>',
    sparkles: '<path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/><path d="M19 3v4M17 5h4"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
    brain: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    plusSquare: '<path d="M12 20h7a2 2 0 0 0 2-2v-7"/><path d="M18.4 2.6a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/><path d="M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
    userCog: '<circle cx="10" cy="8" r="4"/><path d="M2 21v-1a6 6 0 0 1 6-6h3"/><circle cx="18" cy="17" r="2.5"/><path d="M18 12.5v2M18 19.5v2M13.5 17h2M20.5 17h2M14.8 13.8l1.4 1.4M19.8 18.8l1.4 1.4M14.8 20.2l1.4-1.4M19.8 15.2l1.4-1.4"/>',
    sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    idCard: '<rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="8.5" cy="11" r="2.5"/><path d="M5 17a3.5 3.5 0 0 1 7 0"/><path d="M15 9h4M15 13h4"/>',
    scale: '<path d="M12 3v18M7 21h10"/><path d="M5 7h14"/><path d="m5 7-3 7a3 3 0 0 0 6 0z"/><path d="m19 7-3 7a3 3 0 0 0 6 0z"/>',
    chevronRight: '<path d="m9 6 6 6-6 6"/>',
    smile: '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01M15 9h.01"/>',
    briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><path d="M2 13h20"/>',
    bowtie: '<path d="M3 7v10l7-3.2v-3.6z"/><path d="M21 7v10l-7-3.2v-3.6z"/><rect x="10" y="10" width="4" height="4" rx="1"/>',
    cap: '<path d="M22 10 12 5 2 10l10 5z"/><path d="M6 12v5c3 2.5 9 2.5 12 0v-5"/><path d="M22 10v6"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    palette: '<circle cx="13.5" cy="6.5" r="1.2"/><circle cx="17.5" cy="10.5" r="1.2"/><circle cx="8.5" cy="7.5" r="1.2"/><circle cx="6.5" cy="12.5" r="1.2"/><path d="M12 2a10 10 0 0 0 0 20c.9 0 1.6-.7 1.6-1.6 0-.4-.2-.8-.4-1.1-.3-.3-.4-.7-.4-1.1 0-.9.7-1.6 1.6-1.6h2A5.6 5.6 0 0 0 22 11c0-5-4.5-9-10-9z"/>',
    flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.4-.5-2-1-3-1.1-2.1-.2-4 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.2.4-2.3 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    tag: '<path d="M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.7 8.7a2.4 2.4 0 0 0 3.4 0l6.6-6.6a2.4 2.4 0 0 0 0-3.4z"/><circle cx="7.5" cy="7.5" r="1.2"/>',
    compass: '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36z"/>',
    chat: '<path d="M21 12a8.5 8.5 0 0 1-12.4 7.5L3 21l1.5-5.6A8.5 8.5 0 1 1 21 12z"/>',
    play: '<path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none"/>',
    shieldOff: '<path d="M19.7 14a6.9 6.9 0 0 0 .3-2V5l-8-3-3.2 1.2"/><path d="m2 2 20 20"/><path d="M4.7 4.7 4 5v7c0 6 8 10 8 10a20.3 20.3 0 0 0 5.6-4.4"/>',
    zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    eyeOff: '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.16 3.19"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3.5 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/><path d="m2 2 20 20"/>',
    external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  };

  function icon(name, cls) {
    const span = document.createElement('span');
    span.className = 'ic' + (cls ? ' ' + cls : '');
    span.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (pick(ICONS, name) || ICONS.info) + '</svg>';
    return span;
  }

  // Platzhalter data-icon im HTML mit Symbolen fuellen. Ein leeres <span> ohne Klasse
  // wird durch das Symbol ersetzt (damit Regeln wie ".suggestion > .ic" greifen).
  for (const el of document.querySelectorAll('[data-icon]')) {
    const ic = icon(el.dataset.icon);
    if (el.tagName === 'SPAN' && !el.className && !el.childNodes.length) el.replaceWith(ic);
    else {
      el.prepend(ic);
      el.removeAttribute('data-icon');
    }
  }

  // =====================================================================
  // Markdown – sicher: zuerst escapen, dann nur eigene Tags erzeugen
  // =====================================================================
  const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC_MAP[c]);
  const COPY_SVG = '<span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS.copy + '</svg></span>';

  function link(url, htmlText) {
    // url ist bereits escaped und beginnt garantiert mit http:// oder https://
    return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + htmlText + '</a>';
  }

  /** Fett, kursiv, durchgestrichen – auf bereits escaptem Text. */
  function emph(s) {
    return s
      .replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^\p{L}\p{N}_])__(?=\S)([\s\S]*?\S)__(?![\p{L}\p{N}_])/gu, '$1<strong>$2</strong>')
      .replace(/(^|[^*\p{L}\p{N}_])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![*\p{L}\p{N}_])/gu, '$1<em>$2</em>')
      .replace(/(^|[^\p{L}\p{N}_])_(?=[^\s_])([^_\n]*?[^\s_])_(?![\p{L}\p{N}_])/gu, '$1<em>$2</em>')
      .replace(/~~(?=\S)([\s\S]*?\S)~~/g, '<del>$1</del>');
  }

  /** Inline-Formatierung einer Zeile/eines Absatzes. */
  function mdInline(raw) {
    const parts = [];
    const keep = (html) => '\u0001' + (parts.push(html) - 1) + '\u0002';
    let s = String(raw);
    // 1. Code-Spannen roh herausziehen (Inhalt wird nicht formatiert)
    s = s.replace(/(`+)(?!`)([\s\S]*?[^`])\1(?!`)/g, (m, ticks, code) => keep('<code>' + esc(code) + '</code>'));
    // 2. alles andere escapen
    s = esc(s);
    // 3. Links [Text](http...) – nur http/https
    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/(?:[^\s()\u0001\u0002]|\([^\s()\u0001\u0002]*\))+)\)/g,
      (m, text, url) => keep(link(url, emph(text))));
    // 4. nackte Adressen
    s = s.replace(/https?:\/\/[^\s\u0001\u0002]+/g, (m) => {
      let url = m;
      let tail = '';
      const cut = url.search(/&(?:lt|gt|quot|#39);/);
      if (cut >= 0) { tail = url.slice(cut); url = url.slice(0, cut); }
      const t = url.match(/[.,;:!?)\]*_~]+$/);
      if (t) { tail = t[0] + tail; url = url.slice(0, -t[0].length); }
      // ")" am Ende gehoert zur Adresse, wenn sie eine "(" enthaelt, z.B. Wikipedia
      while (tail.startsWith(')') && (url.split('(').length > url.split(')').length)) {
        url += ')';
        tail = tail.slice(1);
      }
      if (!/^https?:\/\/[^/]/.test(url)) return m;
      return keep(link(url, url)) + tail;
    });
    // 5. Hervorhebungen
    s = emph(s);
    // 6. Platzhalter zurueck (auch verschachtelte)
    for (let i = 0; i < 4 && s.indexOf('\u0001') >= 0; i++) {
      s = s.replace(/\u0001(\d+)\u0002/g, (m, n) => parts[Number(n)] || '');
    }
    return s;
  }

  // Sprache = erstes Wort nach dem Zaun (z.B. ```python title="main.py" oder ```py:main.py)
  const RE_FENCE = /^(\s*)(`{3,}|~{3,})\s*([^\s`]*)[^`]*$/;
  const RE_HEAD = /^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
  const RE_HR = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
  const RE_QUOTE = /^\s{0,3}>\s?/;
  const RE_LIST = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/;
  const RE_TSEP = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;

  const isTableStart = (lines, i) =>
    lines[i].includes('|') && i + 1 < lines.length && lines[i + 1].includes('|') && RE_TSEP.test(lines[i + 1]);

  function startsBlock(lines, i) {
    const l = lines[i];
    return RE_FENCE.test(l) || RE_HEAD.test(l) || RE_HR.test(l) || RE_QUOTE.test(l) ||
      RE_LIST.test(l) || isTableStart(lines, i);
  }

  function indentWidth(s) {
    let n = 0;
    for (const c of s) n += c === '\t' ? 4 : 1;
    return n;
  }

  function stripIndent(line, n) {
    let k = 0;
    while (k < n && line[k] === ' ') k++;
    return line.slice(k);
  }

  function codeBlock(code, lang) {
    return '<div class="code"><div class="code-head"><span class="code-lang">' + esc(lang || 'code') +
      '</span><button type="button" class="code-copy" data-copy>' + COPY_SVG +
      '<span>Kopieren</span></button></div><pre><code>' + esc(code) + '</code></pre></div>';
  }

  function splitRow(line) {
    let t = line.trim();
    if (t.startsWith('|')) t = t.slice(1);
    if (t.endsWith('|') && !t.endsWith('\\|')) t = t.slice(0, -1);
    return t.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'));
  }

  function mdTable(lines, i) {
    const head = splitRow(lines[i]);
    const align = splitRow(lines[i + 1]).map((c) => (/^:-+:$/.test(c) ? 'c' : /-:$/.test(c) ? 'r' : ''));
    i += 2;
    const rows = [];
    while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
      rows.push(splitRow(lines[i]));
      i++;
    }
    const cell = (tag, text, k) =>
      '<' + tag + (align[k] ? ' class="al-' + align[k] + '"' : '') + '>' + mdInline(text) + '</' + tag + '>';
    let html = '<div class="table-wrap"><table><thead><tr>' +
      head.map((c, k) => cell('th', c, k)).join('') + '</tr></thead><tbody>';
    for (const r of rows) html += '<tr>' + head.map((_, k) => cell('td', r[k] || '', k)).join('') + '</tr>';
    return { html: html + '</tbody></table></div>', next: i };
  }

  function mdList(lines, i) {
    const items = [];
    while (i < lines.length) {
      const line = lines[i];
      const m = line.match(RE_LIST);
      if (m && !RE_HR.test(line)) {
        items.push({ ind: indentWidth(m[1]), ord: /\d/.test(m[2]), num: parseInt(m[2], 10) || 1, text: m[3] });
        i++;
        continue;
      }
      if (!line.trim()) {
        // Leerzeile: Liste geht weiter, wenn ein Punkt oder eingerueckter Text folgt
        let j = i + 1;
        while (j < lines.length && !lines[j].trim()) j++;
        if (j < lines.length && !RE_FENCE.test(lines[j]) &&
            (RE_LIST.test(lines[j]) || /^\s{2,}\S/.test(lines[j]))) { i = j; continue; }
        break;
      }
      if (items.length && /^\s+\S/.test(line) && !RE_FENCE.test(line)) {
        items[items.length - 1].text += '\n' + line.trim();
        i++;
        continue;
      }
      break;
    }
    // verschachtelte Listen nach Einrueckung bauen
    let html = '';
    const stack = [];
    const open = (it) => (it.ord ? '<ol' + (it.num !== 1 ? ' start="' + it.num + '"' : '') + '>' : '<ul>');
    for (const it of items) {
      const tag = it.ord ? 'ol' : 'ul';
      const top = stack[stack.length - 1];
      if (!top || it.ind > top.ind) {
        html += open(it);
        stack.push({ ind: it.ind, tag });
      } else {
        while (stack.length > 1 && it.ind < stack[stack.length - 1].ind) html += '</li></' + stack.pop().tag + '>';
        html += '</li>';
        const cur = stack[stack.length - 1];
        if (cur.tag !== tag) {
          html += '</' + cur.tag + '>' + open(it);
          cur.tag = tag;
        }
      }
      const task = it.text.match(/^\[([ xX])\]\s+([\s\S]*)$/);
      if (task) {
        const done = task[1] !== ' ';
        html += '<li class="task' + (done ? ' done-item' : '') + '"><span class="task-box' + (done ? ' done' : '') +
          '" role="img" aria-label="' + (done ? 'erledigt' : 'offen') + '"></span>' + mdInline(task[2]);
      } else {
        html += '<li>' + mdInline(it.text);
      }
    }
    while (stack.length) html += '</li></' + stack.pop().tag + '>';
    return { html, next: i };
  }

  function mdBlocks(src, depth) {
    const lines = src.split('\n');
    let out = '';
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      let m;
      if ((m = line.match(RE_FENCE))) {
        // Codeblock (auch unvollstaendig waehrend des Streamens)
        const ind = m[1].length;
        const ch = m[2][0];
        const len = m[2].length;
        const buf = [];
        i++;
        while (i < lines.length) {
          const t = lines[i].trim();
          if (t.length >= len && t === ch.repeat(t.length)) { i++; break; }
          buf.push(stripIndent(lines[i], ind));
          i++;
        }
        out += codeBlock(buf.join('\n'), m[3]);
        continue;
      }
      if ((m = line.match(RE_HEAD))) {
        const n = m[1].length;
        out += '<h' + n + '>' + mdInline(m[2]) + '</h' + n + '>';
        i++;
        continue;
      }
      if (RE_HR.test(line)) { out += '<hr>'; i++; continue; }
      if (RE_QUOTE.test(line)) {
        const buf = [];
        while (i < lines.length && RE_QUOTE.test(lines[i])) { buf.push(lines[i].replace(RE_QUOTE, '')); i++; }
        const inner = depth < 3 ? mdBlocks(buf.join('\n'), depth + 1) : '<p>' + mdInline(buf.join('\n')) + '</p>';
        out += '<blockquote>' + inner + '</blockquote>';
        continue;
      }
      if (isTableStart(lines, i)) {
        const r = mdTable(lines, i);
        out += r.html;
        i = r.next;
        continue;
      }
      if (RE_LIST.test(line)) {
        const r = mdList(lines, i);
        out += r.html;
        i = r.next;
        continue;
      }
      // Absatz: bis Leerzeile oder neuer Block
      const buf = [line];
      i++;
      while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) { buf.push(lines[i]); i++; }
      out += '<p>' + mdInline(buf.join('\n')) + '</p>';
    }
    return out;
  }

  function renderMarkdown(text) {
    const src = String(text == null ? '' : text)
      .replace(/\r\n?/g, '\n')
      .replace(/[\u0001\u0002]/g, ''); // Platzhalter-Zeichen gehoeren uns
    return mdBlocks(src, 0);
  }

  // =====================================================================
  // Novas Sphaere – ihr lebendiges Gesicht (Leinwand, ohne Bibliotheken)
  //  * EINE gemeinsame requestAnimationFrame-Schleife fuer alle Sphaeren. Sie ruht,
  //    wenn das Fenster verborgen ist oder keine lebende Sphaere zu sehen ist.
  //  * Alle Sphaeren zeigen denselben Zustand ("Gemuet"): atmen, nachdenken,
  //    arbeiten (Ring), schreiben (Pulse), sprechen, zuhoeren (Pegel), Rueckfrage ...
  //  * Pro Bild nur Zeichnen auf den Leinwaenden – kein Layout, kein DOM. Die Leinwand-
  //    groesse wird nur nach einer Groessenaenderung neu gesetzt (ResizeObserver).
  //  * Ruhige Stellen (aeltere Antworten, weniger Bewegung) zeigen ein Standbild, das
  //    einmal gezeichnet und als CSS-Bild (--orb-still) benutzt wird.
  // =====================================================================
  const sphere = (() => {
    const TAU = Math.PI * 2;
    const clampN = (v, a, b) => Math.min(b, Math.max(a, v));
    const root = document.documentElement;
    const motionQ = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
    const darkQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    const canvasOk = (() => {
      try { return !!document.createElement('canvas').getContext('2d'); } catch (_) { return false; }
    })();
    const F = 1.8;      // Leinwand = 1,8 x Platz der Sphaere: das Leuchten laeuft weich aus
    const FILL = 0.42;  // Radius der Kugel im Verhaeltnis zum Platz
    // amp/speed = Form, breathe/rate = Atmen, gain = Pegel, glow/bright = Leuchten,
    // spin = kreisende Boegen, ring = Arbeits-Ring, wander = wanderndes Licht, talk = Sprechen,
    // hue = Farbverschiebung, warn = Richtung Warnfarbe (Rueckfrage)
    const PRESET = {
      idle: { amp: 0.03, speed: 0.5, breathe: 0.075, rate: 1.45, gain: 0.3, glow: 0.52, bright: 0, spin: 0, ring: 0, wander: 0, talk: 0, hue: 0, warn: 0 },
      starting: { amp: 0.022, speed: 0.5, breathe: 0.03, rate: 1.7, gain: 0.25, glow: 0.45, bright: 0, spin: 0.6, ring: 0, wander: 0, talk: 0, hue: 0, warn: 0 },
      listening: { amp: 0.026, speed: 0.55, breathe: 0.04, rate: 1.7, gain: 0.6, glow: 0.55, bright: 0, spin: 0, ring: 0, wander: 0, talk: 0, hue: 0, warn: 0 },
      hearing: { amp: 0.045, speed: 1.15, breathe: 0.012, rate: 2, gain: 1.2, glow: 0.9, bright: 0.1, spin: 0, ring: 0, wander: 0, talk: 0, hue: -46, warn: 0 },
      recognizing: { amp: 0.03, speed: 0.9, breathe: 0.02, rate: 2, gain: 0.25, glow: 0.62, bright: 0.04, spin: 1, ring: 0, wander: 0, talk: 0, hue: -18, warn: 0 },
      thinking: { amp: 0.036, speed: 0.78, breathe: 0.035, rate: 2.1, gain: 0.2, glow: 0.74, bright: 0.12, spin: 0, ring: 0, wander: 1, talk: 0, hue: 30, warn: 0 },
      working: { amp: 0.036, speed: 0.88, breathe: 0.035, rate: 2.1, gain: 0.2, glow: 0.78, bright: 0.12, spin: 0, ring: 1, wander: 1, talk: 0, hue: 46, warn: 0 },
      writing: { amp: 0.032, speed: 0.72, breathe: 0.03, rate: 1.8, gain: 0.2, glow: 0.7, bright: 0.07, spin: 0, ring: 0, wander: 0.45, talk: 0, hue: 12, warn: 0 },
      speaking: { amp: 0.04, speed: 1, breathe: 0.02, rate: 1.8, gain: 0.1, glow: 0.88, bright: 0.08, spin: 0, ring: 0, wander: 0, talk: 1, hue: -62, warn: 0 },
      asking: { amp: 0.03, speed: 0.6, breathe: 0.11, rate: 3.1, gain: 0.2, glow: 0.74, bright: 0.04, spin: 0, ring: 0, wander: 0, talk: 0, hue: 0, warn: 1 },
    };
    const KEYS = Object.keys(PRESET.idle);
    const MOTION = {
      ruhig: { sp: 0.6, am: 0.55, ki: 0.6 },
      normal: { sp: 1, am: 1, ki: 1 },
      lebhaft: { sp: 1.45, am: 1.6, ki: 1.35 },
    };
    const look = { mode: 'sphaere', color: '', motion: 'normal', hue: 243, sat: 1, shift: 1, spread: 1, dl: 0, light: true, sp: 1, am: 1, ki: 1 };
    const S = {
      P: Object.assign({}, PRESET.idle), T: PRESET.idle, mood: 'idle',
      t: 0, tb: 0, tw: 0, ph: 0, lvl: 0, lvlT: 0, lvlAt: 0, prevLvl: 0,
      talkL: false, talkS: false, talkEnv: 0, kick: 0, pulseAt: 0, flinch: 0, flinchV: 0, flash: 0,
      err: 0, errV: 0, ripples: [], lastRipple: 0, e: 0, hue: 243, sat: 1, spread: 1,
    };
    const slots = new Map();   // Platz-Element -> Sphaere
    const byCanvas = new Map(); // Leinwand -> Sphaere
    let reduce = !!motionQ.matches;
    let raf = 0;
    let last = 0;
    let dirty = true;           // weniger Bewegung: nur bei Aenderung zeichnen
    let covered = false;        // Jarvis-Modus liegt ueber allem: andere Sphaeren nicht zeichnen
    let scopeEl = null;         // offenes Fenster (Einrichtung, Profil): nur Sphaeren darin zeichnen
    let latestEl = null;
    let stillKey = '';
    let lastDpr = window.devicePixelRatio || 1;

    const io = canvasOk && window.IntersectionObserver ? new IntersectionObserver((entries) => {
      for (const en of entries) {
        const s = byCanvas.get(en.target);
        if (!s) continue;
        s.vis = en.isIntersecting;
        if (s.vis) { s.need = true; wake(); }
      }
    }) : null;
    const ro = canvasOk && window.ResizeObserver ? new ResizeObserver((entries) => {
      for (const en of entries) {
        const s = byCanvas.get(en.target);
        if (!s) continue;
        s.cssW = en.contentRect.width;
        s.cssH = en.contentRect.height;
        s.need = true;
      }
      dirty = true;
      wake();
    }) : null;

    const hsla = (hh, s, l, a) => 'hsla(' + hh.toFixed(1) + ',' + clampN(s, 0, 100).toFixed(1) + '%,' +
      clampN(l, 0, 100).toFixed(1) + '%,' + clampN(a, 0, 1).toFixed(3) + ')';
    /** Farbton a -> b auf dem kuerzeren Weg (k = 0..1). */
    function mixHue(a, b, k) {
      if (k <= 0) return a;
      const d = ((((b - a) % 360) + 540) % 360) - 180;
      return a + d * clampN(k, 0, 1);
    }

    // ---------- Zeichnen ----------
    const XS = new Float32Array(96);
    const YS = new Float32Array(96);
    function outline(ctx, n, cx, cy, R, amp, tt) {
      ctx.beginPath();
      if (amp < 0.0004) { ctx.arc(cx, cy, R, 0, TAU); return; }
      for (let i = 0; i < n; i++) {
        const a = (i / n) * TAU;
        const d = 1 + amp * (0.5 * Math.sin(3 * a + tt * 1.3) + 0.32 * Math.sin(5 * a - tt * 1.75 + 1.7) +
          0.18 * Math.sin(2 * a + tt * 0.9 + 4.1));
        XS[i] = cx + Math.cos(a) * R * d;
        YS[i] = cy + Math.sin(a) * R * d;
      }
      // weich: Kurven durch die Mittelpunkte
      ctx.moveTo((XS[n - 1] + XS[0]) / 2, (YS[n - 1] + YS[0]) / 2);
      for (let i = 0; i < n; i++) {
        const j = (i + 1) % n;
        ctx.quadraticCurveTo(XS[i], YS[i], (XS[i] + XS[j]) / 2, (YS[i] + YS[j]) / 2);
      }
      ctx.closePath();
    }

    function lobe(ctx, x, y, r, color) {
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, color);
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }

    /** Eine Sphaere zeichnen. s = Leinwand + Masse, M = Zustand (gemeinsam oder Standbild). */
    function paint(s, M) {
      const ctx = s.ctx;
      const W = s.W;
      const H = s.H;
      const dpr = s.dpr;
      const cx = W / 2;
      const cy = H / 2;
      const half = Math.min(W, H) / 2;
      const R0 = (Math.min(W, H) / s.f) * s.fill;
      const P = M.P;
      const b = s.boost;
      const e = M.e;
      const light = !s.dark && look.light;
      const sat = M.sat;
      const hue = M.hue;
      const hs = M.spread; // wie weit die Farben im Inneren auseinanderlaufen
      const dl = look.dl;   // helle Farbtoene (Gelb, Gruen) etwas dunkler – sonst wirken sie blass
      const R = R0 * (1 + Math.min(0.34, e * 0.42 * b) + M.flinch * Math.min(b, 1.4));
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalCompositeOperation = 'source-over';
      ctx.clearRect(0, 0, W, H);

      // 1. Leuchten (hell: zarter, dafuer ein weicher, farbiger Schatten)
      const ga = light ? 0.6 : 1;
      let g = ctx.createRadialGradient(cx, cy, R * 0.7, cx, cy, Math.min(half, R0 * (2.25 + e * 0.6 * b)));
      g.addColorStop(0, hsla(hue + 6 * hs, 92 * sat, (light ? 60 : 64) + dl * 0.5, (0.42 * P.glow + 0.32 * e) * ga));
      g.addColorStop(0.35, hsla(hue + 20 * hs, 90 * sat, 60 + dl * 0.5, (0.16 * P.glow + 0.14 * e) * ga));
      g.addColorStop(1, hsla(hue + 30 * hs, 85 * sat, 56, 0));
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
      if (M.flash > 0.02) {
        g = ctx.createRadialGradient(cx, cy, R * 0.8, cx, cy, Math.min(half, R * 1.7));
        g.addColorStop(0, 'hsla(24,95%,62%,' + (0.45 * M.flash).toFixed(3) + ')');
        g.addColorStop(1, 'hsla(24,95%,62%,0)');
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
      }
      if (light) {
        ctx.save();
        ctx.translate(cx, cy + R * 0.86);
        ctx.scale(1, 0.3);
        g = ctx.createRadialGradient(0, 0, 0, 0, 0, R * 1.0);
        g.addColorStop(0, hsla(hue + 24 * hs, 60 * sat, 30, 0.36));
        g.addColorStop(0.6, hsla(hue + 24 * hs, 60 * sat, 34, 0.12));
        g.addColorStop(1, hsla(hue + 24 * hs, 60 * sat, 34, 0));
        ctx.fillStyle = g;
        ctx.fillRect(-R * 1.1, -R * 1.1, R * 2.2, R * 2.2);
        ctx.restore();
      }

      // 2. Wellen (beim Sprechen, bei lauter Stimme, nach einer Antwort)
      for (const rp of M.ripples) {
        const k = rp.age / rp.life;
        if (k >= 1) continue;
        ctx.beginPath();
        ctx.arc(cx, cy, R0 * (1.04 + k * 0.75), 0, TAU);
        ctx.lineWidth = Math.max(0.6 * dpr, R0 * 0.0085 * (1 + 1.6 * (1 - k)));
        ctx.strokeStyle = hsla(hue + rp.shift * hs, 90 * sat, light ? 52 : 72, rp.s * (1 - k) * (1 - k) * 0.55);
        ctx.stroke();
      }

      // 3. Koerper: tiefer Verlauf, das Licht wandert beim Nachdenken
      const amp = P.amp * (0.7 + e * 1.6) * look.am * (1 + (b - 1) * 0.6);
      outline(ctx, s.n, cx, cy, R, amp, M.tb);
      const wx = cx + (Math.cos(M.tw * 0.8) * 0.34 * P.wander - 0.2 * (1 - P.wander)) * R;
      const wy = cy + (Math.sin(M.tw * 1.1) * 0.3 * P.wander - 0.26 * (1 - P.wander)) * R;
      const lift = P.bright * 7 + M.kick * 6;
      const dk = light ? 3 : 0;
      g = ctx.createRadialGradient(wx, wy, R * 0.02, cx + R * 0.06, cy + R * 0.08, R * 1.1);
      g.addColorStop(0, hsla(hue - 14 * hs, 95 * sat, 80 + lift * 0.6 + dl * 0.4, 1));
      g.addColorStop(0.28, hsla(hue - 4 * hs, 90 * sat, 64 + lift - dk + dl, 1));
      g.addColorStop(0.68, hsla(hue + 16 * hs, 84 * sat, 48 - dk + dl, 1));
      g.addColorStop(1, hsla(hue + 30 * hs, 82 * sat, 30 - dk + dl * 0.6, 1));
      ctx.fillStyle = g;
      ctx.fill();

      // 4. im Inneren: wirbelnde Lichter, Fehler-Schimmer, Volumen, Gegenlicht am Rand, Glanz
      ctx.save();
      ctx.clip();
      ctx.globalCompositeOperation = 'lighter';
      const tl = M.tb;
      lobe(ctx, cx + Math.cos(tl * 0.63 + 1) * R * 0.34, cy + Math.sin(tl * 0.81) * R * 0.3, R * 0.72,
        hsla(hue - 52 * hs, 96 * sat, 58 + dl * 0.5, 0.34 + 0.3 * e));
      lobe(ctx, cx + Math.cos(tl * 0.47 + 3.4) * R * 0.38, cy + Math.sin(tl * 0.59 + 2) * R * 0.34, R * 0.66,
        hsla(hue + 58 * hs, 92 * sat, 60 + dl * 0.5, 0.28 + 0.26 * e));
      lobe(ctx, cx + Math.cos(tl * 0.36 + 5.1) * R * 0.18, cy + Math.sin(tl * 0.44 + 4) * R * 0.2, R * 0.5,
        hsla(hue - 18 * hs, 100 * sat, 72, 0.16 + 0.22 * e + M.kick * 0.18));
      ctx.globalCompositeOperation = 'source-over';
      if (M.errV > 0.02) {
        ctx.fillStyle = 'hsla(354,86%,54%,' + (0.5 * M.errV).toFixed(3) + ')';
        ctx.fillRect(cx - R * 1.4, cy - R * 1.4, R * 2.8, R * 2.8);
      }
      // Volumen: unten rechts dunkler
      g = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.36, R * 0.2, cx, cy, R * 1.1);
      g.addColorStop(0, 'rgba(0,0,0,0)');
      g.addColorStop(0.7, light ? 'rgba(14,8,48,0.08)' : 'rgba(6,6,24,0.1)');
      g.addColorStop(1, light ? 'rgba(14,8,48,0.36)' : 'rgba(6,6,24,0.48)');
      ctx.fillStyle = g;
      ctx.fillRect(cx - R * 1.4, cy - R * 1.4, R * 2.8, R * 2.8);
      // Gegenlicht: feine, helle Sichel am Rand unten rechts (wie Glas)
      ctx.globalCompositeOperation = 'lighter';
      g = ctx.createRadialGradient(cx - R * 0.1, cy - R * 0.13, R * 0.97, cx - R * 0.1, cy - R * 0.13, R * 1.15);
      g.addColorStop(0, hsla(hue - 40 * hs, 100 * sat, 70, 0));
      g.addColorStop(0.5, hsla(hue - 40 * hs, 100 * sat, 72, 0.08));
      g.addColorStop(1, hsla(hue - 40 * hs, 100 * sat, 78, 0.34 + 0.2 * P.glow));
      ctx.fillStyle = g;
      ctx.fillRect(cx - R * 1.4, cy - R * 1.4, R * 2.8, R * 2.8);
      ctx.globalCompositeOperation = 'source-over';
      // Glanz: weich und breit, dazu ein klarer Lichtpunkt
      lobe(ctx, cx - R * 0.34, cy - R * 0.42, R * 0.56, 'rgba(255,255,255,0.32)');
      ctx.save();
      ctx.translate(cx - R * 0.38, cy - R * 0.46);
      ctx.rotate(-0.7);
      ctx.scale(1, 0.62);
      g = ctx.createRadialGradient(0, 0, 0, 0, 0, R * 0.2);
      g.addColorStop(0, 'rgba(255,255,255,0.85)');
      g.addColorStop(0.45, 'rgba(255,255,255,0.35)');
      g.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = g;
      ctx.fillRect(-R * 0.2, -R * 0.2, R * 0.4, R * 0.4);
      ctx.restore();
      ctx.restore();
      ctx.lineWidth = Math.max(0.5 * dpr, R0 * 0.0052);
      ctx.strokeStyle = light ? hsla(hue + 24 * hs, 60 * sat, 30, 0.2) : hsla(hue - 30 * hs, 80 * sat, 82, 0.18);
      ctx.stroke();

      // 5. Kreisen (erkennt Sprache)
      if (P.spin > 0.02) {
        const rr = R0 * 1.2;
        ctx.lineCap = 'round';
        ctx.lineWidth = Math.max(1.1 * dpr, R0 * 0.0102);
        const l = light ? 50 : 78;
        for (let k = 0; k < 2; k++) {
          const a0 = M.t * 3.1 + k * Math.PI;
          ctx.beginPath();
          ctx.arc(cx, cy, rr, a0, a0 + 1.05);
          if (ctx.createConicGradient) {
            const cg = ctx.createConicGradient(a0, cx, cy);
            cg.addColorStop(0, hsla(hue, 90 * sat, l, 0));
            cg.addColorStop(0.167, hsla(hue, 90 * sat, l, 0.75 * P.spin));
            cg.addColorStop(0.17, hsla(hue, 90 * sat, l, 0));
            ctx.strokeStyle = cg;
          } else ctx.strokeStyle = hsla(hue, 90 * sat, l, 0.5 * P.spin);
          ctx.stroke();
        }
      }
      // 6. feiner, umlaufender Ring (arbeitet mit Werkzeugen)
      if (P.ring > 0.02) {
        const rr = R0 * (s.small ? 1.25 : 1.3);
        const l = light ? 48 : 82;
        const lw = Math.max(0.9 * dpr, R0 * 0.0064);
        ctx.save();
        ctx.translate(cx, cy);
        ctx.lineWidth = lw;
        if (!s.small) ctx.setLineDash([1.6 * dpr, 7 * dpr]);
        ctx.strokeStyle = hsla(hue + 20 * hs, 85 * sat, l, (s.small ? 0.22 : 0.5) * P.ring);
        ctx.beginPath();
        ctx.arc(0, 0, rr, 0, TAU);
        ctx.stroke();
        ctx.setLineDash([]);
        const ba = M.t * 1.5;
        if (ctx.createConicGradient) {
          // Schweif hinter dem Lichtpunkt
          const tail = 1.8;
          const cg = ctx.createConicGradient(ba - tail, 0, 0);
          cg.addColorStop(0, hsla(hue + 20 * hs, 95 * sat, l, 0));
          cg.addColorStop(tail / TAU, hsla(hue + 20 * hs, 95 * sat, l, 0.85 * P.ring));
          cg.addColorStop(tail / TAU + 0.002, hsla(hue + 20 * hs, 95 * sat, l, 0));
          ctx.strokeStyle = cg;
          ctx.lineWidth = lw * 1.5;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.arc(0, 0, rr, ba - tail, ba);
          ctx.stroke();
        }
        ctx.fillStyle = hsla(hue + 20 * hs, 95 * sat, light ? 52 : 86, 0.95 * P.ring);
        if (!s.small) {
          ctx.shadowColor = hsla(hue + 20 * hs, 95 * sat, 70, 0.9 * P.ring);
          ctx.shadowBlur = 10 * dpr;
        }
        ctx.beginPath();
        ctx.arc(Math.cos(ba) * rr, Math.sin(ba) * rr, clampN(R0 * 0.022, 1.1 * dpr, 2.6 * dpr), 0, TAU);
        ctx.fill();
        ctx.restore();
      }
    }

    // ---------- Zustand pro Bild (einmal fuer alle Sphaeren) ----------
    function step(dt, now) {
      const P = S.P;
      const T = S.T;
      if (reduce) {
        for (const key of KEYS) P[key] = T[key];
        S.lvl = S.lvlT = 0;
        S.talkEnv = S.kick = S.flinch = S.flinchV = S.flash = S.err = 0;
        S.ripples.length = 0;
      } else {
        const k = 1 - Math.exp(-dt * 4.5);
        for (const key of KEYS) P[key] += (T[key] - P[key]) * k;
        S.t += dt;
        S.tb += dt * P.speed * look.sp;   // Form und innere Lichter (eigene Uhr: kein Ruck bei Tempowechsel)
        S.tw += dt * look.sp;             // wanderndes Licht
        S.ph += dt * P.rate * look.sp;    // Atmen
        if (now - S.lvlAt > 320) S.lvlT *= Math.exp(-dt * 5);
        S.lvl += (S.lvlT - S.lvl) * (1 - Math.exp(-dt * (S.lvlT > S.lvl ? 22 : 5)));
        const talking = S.talkL || S.talkS;
        S.talkEnv += ((talking ? 1 : P.talk > 0.5 ? 0.35 : 0) - S.talkEnv) * (1 - Math.exp(-dt * 6));
        S.kick *= Math.exp(-dt * 5.5);
        const acc = -150 * S.flinch - 13 * S.flinchV;
        S.flinchV += acc * dt;
        S.flinch += S.flinchV * dt;
        S.flash *= Math.exp(-dt * 3.2);
        S.err *= Math.exp(-dt * 2.4);
        if (S.err < 0.01) S.err = 0;
        for (let i = S.ripples.length - 1; i >= 0; i--) {
          const rp = S.ripples[i];
          rp.age += dt;
          if (rp.age >= rp.life) S.ripples.splice(i, 1);
        }
        // Wellen: beim Sprechen im Rhythmus, beim Zuhoeren bei lauter Stimme
        if (talking && now - S.lastRipple > 560) { ripple(1.5, 0.8, -20); S.lastRipple = now; }
        if (P.gain > 0.9 && S.lvl > 0.42 && S.prevLvl <= 0.42 && now - S.lastRipple > 220) {
          ripple(1.2, Math.min(1, S.lvl + 0.2), 0);
          S.lastRipple = now;
        }
      }
      S.prevLvl = S.lvl;
      const syl = S.talkEnv * Math.max(0, 0.55 + 0.45 * Math.sin(S.t * 10.6) * Math.sin(S.t * 3.7 + 1.1));
      S.e = P.breathe * (0.5 + 0.5 * Math.sin(S.ph)) + S.lvl * P.gain * 0.5 + syl * 0.13 * P.talk + S.kick * 0.16 * look.ki;
      let hue = look.hue + P.hue * look.shift;
      if (!reduce) hue += 7 * Math.sin(S.t * 0.21); // sanftes Farbschimmern
      hue = mixHue(hue, 38, P.warn * 0.92);
      S.errV = S.err > 0 ? S.err * (0.62 + 0.38 * Math.sin(S.t * 38)) : 0;
      S.hue = mixHue(hue, 354, S.errV * 0.85);
      S.sat = look.sat + (1 - look.sat) * Math.max(P.warn, S.errV);
      S.spread = look.spread * (1 - 0.55 * Math.max(P.warn, S.errV));
    }

    function ripple(life, strength, shift) {
      if (reduce) return;
      S.ripples.push({ age: 0, life, s: strength, shift });
      if (S.ripples.length > 6) S.ripples.shift();
    }

    // ---------- Leinwaende ----------
    function size(s) {
      s.need = false;
      if (!ro) {
        const r = s.cv.getBoundingClientRect(); // ohne ResizeObserver (alt): selten
        s.cssW = r.width;
        s.cssH = r.height;
      }
      const slotCss = Math.min(s.cssW, s.cssH) / s.f;
      s.boost = s.small ? clampN(56 / Math.max(1, slotCss), 1, 2) : 1;
      s.dpr = Math.min(s.small ? 3 : 2, window.devicePixelRatio || 1);
      // Jarvis: bis 688 CSS-px Leinwand (430 px Platz x 1,6) -> bei 2-facher Pixeldichte 1376 Pixel
      const cap = s.small ? 900 : 1400;
      const w = Math.max(0, Math.min(cap, Math.round(s.cssW * s.dpr)));
      const hh = Math.max(0, Math.min(cap, Math.round(s.cssH * s.dpr)));
      if (w !== s.W || hh !== s.H) { s.W = s.cv.width = w; s.H = s.cv.height = hh; }
    }

    function frame(now) {
      raf = 0;
      if (document.hidden) return;
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 1 / 60;
      last = now;
      const dpr = window.devicePixelRatio || 1;
      if (dpr !== lastDpr) { lastDpr = dpr; for (const s of slots.values()) s.need = true; }
      step(dt, now);
      let any = false;
      for (const s of slots.values()) {
        if (!s.live || !s.vis || (covered && !s.jarvis)) continue;
        if (scopeEl && !s.jarvis && !scopeEl.contains(s.el)) continue; // liegt hinter dem Fenster
        any = true;
        if (s.need) size(s);
        if (!s.W || !s.H) continue;
        paint(s, S);
        if (!s.drawn) {
          s.drawn = true;
          if (!s.jarvis) s.el.classList.add('drawn');
        }
      }
      dirty = false;
      if (any && !reduce) raf = requestAnimationFrame(frame);
    }

    function wake() {
      if (raf || document.hidden) return;
      last = 0;
      raf = requestAnimationFrame(frame);
    }

    /** Lebt die Sphaere an diesem Platz gerade (Leinwand) – oder zeigt sie ein Standbild? */
    function apply(s) {
      const eff = canvasOk && s.want && (s.jarvis || (look.mode === 'sphaere' && !reduce));
      if (eff === s.live) return;
      s.live = eff;
      if (eff) {
        if (!s.cv) {
          s.cv = document.createElement('canvas');
          s.cv.className = 'orb-cv';
          s.cv.setAttribute('aria-hidden', 'true');
          s.el.append(s.cv);
        }
        if (!s.ctx) s.ctx = s.cv.getContext('2d');
        if (!s.ctx) { s.live = false; return; }
        s.need = true;
        s.drawn = false;
        s.vis = !io;
        byCanvas.set(s.cv, s);
        if (io) io.observe(s.cv);
        if (ro) ro.observe(s.cv);
        if (!s.jarvis) s.el.classList.add('live');
        dirty = true;
        wake();
      } else if (s.cv) {
        if (io) io.unobserve(s.cv);
        if (ro) ro.unobserve(s.cv);
        byCanvas.delete(s.cv);
        if (!s.jarvis) {
          s.cv.remove();
          s.cv = null;
          s.ctx = null;
          s.W = s.H = 0;
          s.el.classList.remove('live', 'drawn');
        }
      }
    }

    function slot(el, o) {
      if (!el || slots.has(el)) return;
      o = o || {};
      const jarvis = !!o.jarvis;
      const s = {
        el, cv: jarvis ? el : null, ctx: null, want: o.live !== false, jarvis, small: !jarvis,
        f: jarvis ? 1.6 : F, fill: jarvis ? 0.272 : FILL, dark: jarvis, n: jarvis ? 72 : 48,
        boost: 1, vis: !io, cssW: 0, cssH: 0, W: 0, H: 0, dpr: 1, need: true, drawn: false, live: false,
      };
      slots.set(el, s);
      apply(s);
    }

    function unslot(el) {
      const s = slots.get(el);
      if (!s) return;
      s.want = false;
      apply(s);
      slots.delete(el);
    }

    // ---------- Farbe, Thema, Standbild ----------
    function readLook() {
      const bg = hexRgb(cssColor('--bg', '#f7f7f9'));
      look.light = lum(bg) > 0.35;
      const own = look.color;
      const hex = own || cssColor('--accent', '#4f46e5');
      const [hh, s, l] = rgbHsl(hexRgb(hex));
      if (own) {
        look.hue = s < 0.04 ? 225 : hh;       // reines Grau: kuehles Silber statt rotstichig (Farbton 0)
        look.sat = clampN(s / 0.55, 0.06, 1); // eigene Farbe: auch Silber/Grau moeglich
      } else {
        look.hue = s < 0.12 ? 243 : hh;    // grau -> Standard (Indigo)
        look.sat = 1;
      }
      // Indigo: volle Farbwechsel wie im Jarvis-Modus; eigene Farben behalten ihren Charakter
      const indigo = Math.abs(mixHue(look.hue, 243, 1) - look.hue) < 25 && !own;
      look.shift = indigo ? 1 : 0.6;
      // Farbverlauf im Inneren: beim Indigo bunt (wie im Jarvis-Modus), eigene Farben bleiben bei sich
      look.spread = indigo ? 1 : own ? 0.38 : 0.55;
      // gleiche Helligkeit wirkt bei Gelb/Gruen viel heller als bei Indigo: ausgleichen
      const bright = lum(hslRgb(look.hue, 0.9 * look.sat, 0.6)) - lum(hslRgb(243, 0.9, 0.6));
      look.dl = clampN(-bright * 30, -13, 0);
      // eigene Farbe: auch ihre Helligkeit zaehlt (Schwarz, Dunkelblau -> dunkler; Weiss, Hellblau -> heller)
      if (own) look.dl = clampN(look.dl + (l - 0.5) * 60, -26, 20);
      const m = pick(MOTION, look.motion) || MOTION.normal;
      look.sp = m.sp;
      look.am = m.am;
      look.ki = m.ki;
      root.style.setProperty('--orb-a', hsla(look.hue, 86 * look.sat, 64 + look.dl * 0.8, 1));
      root.style.setProperty('--orb-b', hsla(look.hue + 30 * look.spread, 78 * look.sat, 42 + look.dl * 0.8, 1));
    }

    function stillState() {
      const P = Object.assign({}, PRESET.idle);
      return {
        P, e: 0.03, hue: look.hue, sat: look.sat, spread: look.spread, flinch: 0, flash: 0, errV: 0, kick: 0, ripples: [],
        t: 0, tb: 2.3, tw: 0,
      };
    }

    function makeStill() {
      if (!canvasOk) return;
      const key = look.hue.toFixed(1) + '|' + look.sat.toFixed(2) + '|' + look.spread + '|' + look.dl.toFixed(1) + '|' + (look.light ? 'l' : 'd');
      if (key === stillKey) return;
      const px = 140 * 2;
      const w = Math.round(px * F);
      const cv = document.createElement('canvas');
      cv.width = cv.height = w;
      const ctx = cv.getContext('2d');
      if (!ctx) return;
      const s = { ctx, W: w, H: w, dpr: 2, f: F, fill: FILL, dark: false, small: true, n: 72, boost: 1 };
      paint(s, stillState());
      let url = '';
      try {
        url = cv.toDataURL('image/webp', 0.92);
        if (!/^data:image\/webp/.test(url)) url = cv.toDataURL('image/png');
      } catch (_) { url = ''; }
      if (!url) return;
      stillKey = key;
      root.style.setProperty('--orb-still', 'url("' + url + '")');
      root.classList.add('orb-img');
    }

    function refresh() {
      readLook();
      makeStill();
      dirty = true;
      wake();
    }

    function relayout() {
      reduce = !!motionQ.matches;
      root.classList.toggle('orb-on', look.mode === 'sphaere');
      root.classList.toggle('orb-calm', reduce);
      for (const s of slots.values()) apply(s);
      dirty = true;
      wake();
    }

    const onMq = (q, fn) => {
      if (!q) return;
      if (typeof q.addEventListener === 'function') q.addEventListener('change', fn);
      else if (typeof q.addListener === 'function') q.addListener(fn);
    };
    onMq(motionQ, relayout);
    onMq(darkQ, () => refresh());
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { if (raf) cancelAnimationFrame(raf); raf = 0; } else { dirty = true; wake(); }
    });
    root.classList.add('orb-on');
    root.dataset.nova = 'idle';
    if (reduce) root.classList.add('orb-calm');

    return {
      canvasOk,
      slot,
      unslot,
      /** Nur die Sphaere der neuesten Antwort lebt; aeltere zeigen das Standbild. */
      latest(el) {
        if (el === latestEl) return;
        if (latestEl) unslot(latestEl);
        latestEl = el || null;
        if (latestEl) slot(latestEl, { live: true });
      },
      mood(name) {
        const m = own(PRESET, name) ? name : 'idle';
        if (m === S.mood) return;
        S.mood = m;
        S.T = PRESET[m];
        root.dataset.nova = m; // auch fuer eigenes CSS: :root[data-nova="thinking"] …
        dirty = true;
        wake();
      },
      get current() { return S.mood; },
      level(v) {
        v = Number(v);
        if (!Number.isFinite(v)) return;
        S.lvlT = clampN(v, 0, 1);
        S.lvlAt = performance.now();
        wake();
      },
      kick(v) { S.kick = Math.min(1.4, S.kick + (v || 1) * 0.7); wake(); },
      /** Schreiben: kurzer Puls je Text-Stueck – ruhig, hoechstens ~3x pro Sekunde. */
      pulse() {
        const now = performance.now();
        if (now - S.pulseAt < 280) return;
        S.pulseAt = now;
        S.kick = Math.min(1, S.kick + 0.5);
        wake();
      },
      talk(src, on) {
        if (src === 'local') S.talkL = !!on; else S.talkS = !!on;
        wake();
      },
      /** Angehalten / unterbrochen: kurzes Zucken (mit Aufleuchten im Jarvis-Modus). */
      flinch(withFlash) {
        S.flinchV -= 2.4;
        if (withFlash) S.flash = 1;
        wake();
      },
      /** Fehler: kurzes roetliches Flackern. */
      flicker() { S.err = 1; wake(); },
      /** Fertig: sanftes Ausklingen. */
      settle() { ripple(1.7, 0.55, 12); S.kick = Math.min(1.2, S.kick + 0.35); wake(); },
      cover(on) { covered = !!on; dirty = true; wake(); },
      /** Ein Fenster liegt ueber dem Chat: Sphaeren dahinter ruhen (Standbild bis es zu ist). */
      scope(el) {
        el = el || null;
        if (el === scopeEl) return;
        scopeEl = el;
        dirty = true;
        wake();
      },
      jarvis(cv, on) {
        if (!slots.has(cv)) slot(cv, { jarvis: true, live: false });
        const s = slots.get(cv);
        if (on && !s.live) {
          S.lvl = S.lvlT = 0;
          S.ripples.length = 0;
        }
        s.want = !!on;
        apply(s);
        if (!on) S.talkL = false;
      },
      /** Aussehen: avatar sphaere|buchstabe, sphaere_farbe (Hex), bewegung ruhig|normal|lebhaft. */
      setLook(o) {
        o = o || {};
        look.mode = o.mode === 'buchstabe' ? 'buchstabe' : 'sphaere';
        look.color = o.color || '';
        look.motion = own(MOTION, o.motion) ? o.motion : 'normal';
        readLook();
        relayout();
        makeStill();
      },
      refresh,
      get mode() { return look.mode; },
    };
  })();

  // =====================================================================
  // Zustand & Seitenleiste
  // =====================================================================
  let state = {};
  let busy = false;
  let connected = false;
  let everConnected = false;
  let ended = false; // Ereignis "bye": die KI wurde beendet
  const pendingToggle = {};
  const pendingVal = {};   // Schalter, deren Aenderung gerade gesendet wird (Wert schon anzeigen)

  // Ebenen ueber dem Chat (Jarvis-Modus, Tour, Bestaetigung) – frueh, weil updateInert sie kennt
  const jvEl = byId('jarvis');
  const tourEl = byId('tour');
  const cmodal = byId('cmodal');
  const amodal = byId('amodal'); // AFK-Modus starten ("Ich bin weg")
  const jv = {
    open: false, starting: false, cancelStart: false, closing: false, closeTimer: 0, closeWaiters: [], left: false,
    leaveTimer: 0, openedAt: 0, state: 'starting', label: '', labelTimer: 0, working: false,
    live: null, setupText: '', setupFailed: false, focusBack: null, noteTimer: 0,
    words: [], heardFinal: false, heardStale: false, heardTimer: 0, subsTimer: 0,
  };
  const tour = {
    open: false, paused: false, loading: false, steps: [], i: 0, demo: false, waiting: false, sawBusy: false,
    waitTimer: 0, target: null, follow: 0, sbOpened: false, doneSent: false,
  };

  const app = byId('app');
  const msgs = byId('messages');
  const scroller = byId('chat-scroll');
  const emptyEl = byId('empty');
  const input = byId('input');
  const sendBtn = byId('send-btn');
  const stopBtn = byId('stop-btn');
  const hintNow = byId('hint-now');
  const micBtn = byId('mic-btn');
  const composer = byId('composer');

  const PROVIDERS = { deepseek: 'DeepSeek', anthropic: 'Claude (Anthropic)', claude: 'Claude (Anthropic)' };
  const fmtInt = (n) => (Number(n) || 0).toLocaleString('de-DE');
  function fmtEur(v) {
    v = Number(v) || 0;
    const d = v > 0 && v < 0.1 ? 4 : 2;
    return '≈ ' + v.toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d }) + ' €';
  }
  const kiName = () => (state.name ? String(state.name) : 'KI');
  const initial = () => (kiName().trim().charAt(0) || 'K').toUpperCase();

  function setSwitch(btn, on) { btn.setAttribute('aria-checked', on ? 'true' : 'false'); }

  /** Bedeutung des Namens; ergeben die Anfangsbuchstaben den Namen (N-O-V-A), werden sie betont. */
  function fillMeaning(el, name, meaning) {
    el.replaceChildren();
    meaning = String(meaning || '').trim();
    el.hidden = !meaning;
    if (!meaning) return;
    const words = meaning.match(/[\p{L}\p{N}][\p{L}\p{N}'\u2019-]*/gu) || [];
    const letters = String(name || '').replace(/[^\p{L}\p{N}]/gu, '').toLowerCase();
    const spells = words.length > 1 && letters && words.map((w) => w.charAt(0)).join('').toLowerCase() === letters;
    if (!spells) { el.textContent = meaning; return; }
    // Text Stueck fuer Stueck als Textknoten (sicher), Anfangsbuchstaben in <b>
    const re = /[\p{L}\p{N}][\p{L}\p{N}'\u2019-]*/gu;
    let pos = 0;
    let m;
    while ((m = re.exec(meaning))) {
      if (m.index > pos) el.append(meaning.slice(pos, m.index));
      el.append(h('b', null, m[0].charAt(0)), m[0].slice(1));
      pos = m.index + m[0].length;
    }
    if (pos < meaning.length) el.append(meaning.slice(pos));
  }

  /** Farbe einer CSS-Variable als "#rrggbb" (fuer das Symbol im Fensterrahmen). */
  function cssColor(name, fallback) {
    const probe = h('span');
    probe.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;color:var(' + name + ')';
    document.body.append(probe);
    const c = getComputedStyle(probe).color || '';
    probe.remove();
    let m = c.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/);
    let rgb = m ? [+m[1], +m[2], +m[3]] : null;
    if (!rgb && (m = c.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/))) rgb = [m[1] * 255, m[2] * 255, m[3] * 255];
    if (!rgb) return fallback;
    return '#' + rgb.map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, '0')).join('');
  }

  function setFavicon(letter) {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="' + cssColor('--grad-a', '#6366f1') + '"/><stop offset="1" stop-color="' +
      cssColor('--grad-b', '#a855f7') + '"/></linearGradient></defs>' +
      '<rect width="64" height="64" rx="18" fill="url(#g)"/><text x="32" y="43" font-family="Segoe UI,Arial,sans-serif" font-size="32" font-weight="700" fill="#fff" text-anchor="middle">' +
      esc(letter) + '</text></svg>';
    byId('favicon').href = 'data:image/svg+xml,' + encodeURIComponent(svg);
  }

  function applyState(s) {
    if (!s || typeof s !== 'object') return;
    state = s;
    const name = kiName();
    const letter = initial();
    document.title = name;
    byId('sb-name').textContent = name;
    byId('tb-name').textContent = name;
    renderGreeting();
    byId('tour-cta-title').textContent = 'Tour starten – ' + name + ' zeigt dir alles';
    byId('jv-name').textContent = name;
    // optional: Bedeutung des Namens (z.B. "Neugierige, Offene, Vernetzte Assistenz")
    const meaning = s.meaning ? String(s.meaning).trim() : '';
    fillMeaning(byId('empty-meaning'), name, meaning);
    fillMeaning(byId('sb-meaning'), name, meaning);
    byId('sb-name').title = meaning ? name + ' – ' + meaning : name;
    byId('sb-meaning').title = meaning;
    for (const a of document.querySelectorAll('.ai-avatar:not([data-own-letter]) > .av-l')) a.textContent = letter;
    setFavicon(letter);
    input.placeholder = 'Schreib ' + name + ' eine Nachricht …';
    byId('sb-version').textContent = s.version ? 'Version ' + s.version : '';

    // Gehirn (Karte in der Seitenleiste oeffnet "Gehirn & Schluessel")
    const prov = String(s.provider || '');
    const keyMissing = s.api_key_missing === true;
    byId('sb-provider').textContent = (s.provider_name ? String(s.provider_name) : '') ||
      pick(PROVIDERS, prov.toLowerCase()) || prov || '–';
    byId('sb-provider').title = byId('sb-provider').textContent;
    // Modell fuer Menschen ("Claude Opus 5.5 - ausgewogen"), sonst die rohe Kennung
    const modelId = s.model == null ? '' : String(s.model).trim();
    const modelName = (s.model_name == null ? '' : String(s.model_name).trim()) || modelId;
    const modelTip = modelName ? 'Modell & Denk-Tiefe: ' + modelName +
      (modelId && modelId !== modelName ? ' (' + modelId + ')' : '') + ' – klicken zum Ändern' : '';
    byId('sb-model').textContent = keyMissing ? 'Schlüssel fehlt – hier einrichten' : modelName || '–';
    byId('sb-model').title = keyMissing ? '' : modelTip;
    byId('sb-brain').classList.toggle('nokey', keyMissing);
    byId('tab-gehirn').classList.toggle('nokey', keyMissing);
    byId('key-bar').hidden = !keyMissing || ended;
    setupState(prov, keyMissing, modelId + '|' + modelName);
    const chip = byId('tb-model');
    byId('tb-model-text').textContent = modelName;
    chip.hidden = !modelName;
    chip.title = modelTip;
    chip.setAttribute('aria-label', modelTip || 'Modell & Denk-Tiefe');
    fitTopbar();

    // Kosten
    byId('sb-eur').textContent = fmtEur(s.eur);
    byId('sb-tokens').textContent = fmtInt(s.tokens) + ' Token';

    // Schalter (Seitenleiste und Reiter "Sicherheit")
    renderSwitches();

    // Fusszeile: sicherer Modus
    const foot = byId('sb-foot');
    foot.classList.toggle('safe', !!s.safe_mode);
    byId('sb-foot-text').textContent = s.safe_mode
      ? 'Sicherer Modus: gefährliche Aktionen gesperrt'
      : 'Läuft lokal auf deinem PC';

    // Mikrofon-Hinweis
    micBtn.classList.toggle('warn-dot', !!s.voice_problem);
    micBtn.title = s.voice_problem
      ? 'Spracheingabe: ' + s.voice_problem
      : 'Sprechen – gedrückt halten oder kurz drücken (F2)' + (s.voice_autosend === true ? ' · sendet sofort' : '');

    // Update: Anzeige in der Seitenleiste ("Auf dem neuesten Stand") und Knopf in der Kopfzeile
    onUpdateState();
    const newV = newVersion();
    byId('tb-update').hidden = !newV;
    byId('tb-update-text').textContent = newV ? 'Update ' + newV : '';
    byId('tb-update').title = newV ? 'Update auf ' + newV + ' installieren (/update)' : '';

    renderAlerts();
    commands = Array.isArray(s.commands) ? s.commands.filter((c) => c && typeof c.cmd === 'string') : [];
    setBusy(!!s.busy);
    // Platzhalter-Blase vom Neuladen ("schreibt …"), aber es kam nichts mehr (z.B. AFK-Modus endete
    // genau dabei): die KI ist frei -> weg damit, sonst bliebe sie fuer immer stehen
    if (!s.busy && reply && reply.placeholder && reply.isEmpty()) {
      reply.dispose();
      reply.row.remove();
      reply = null;
      updateEmpty();
      moodSync();
    }
    renderQueue();
    renderAfk();
    profileNames();
    updateEmpty();
    // Jarvis-Modus laeuft beim Server (z.B. zweites Fenster, Neuverbinden), Fenster zeigt ihn nicht – oder umgekehrt
    if (s.jarvis === true && !jv.open && !jv.left && !ended) {
      const st = String(s.jarvis_state || '');
      openJarvisView(false, JV_STATES.has(st) ? st : 'listening');
      jv.live = !!s.jarvis_live;
      renderLive();
    } else if (s.jarvis === true && jv.open && s.jarvis_live === true && jv.live !== true) {
      jv.live = true;
      jv.setupFailed = false;
      renderLive();
    } else if (s.jarvis === false && jv.open && !jv.starting && performance.now() - jv.openedAt > 2500) closeJarvisView();
  }

  const WHEELS_SUB = {
    an: 'fragt vor Änderungen, nur Arbeitsordner',
    aus: 'darf am ganzen PC alles ohne Fragen',
    teilweise: 'Teilweise – klicken zum Wählen',
  };
  const WHEELS_TIP = {
    an: 'Stützräder sind dran – klicken zum Abnehmen',
    aus: 'Stützräder sind ab – klicken zum Anlegen',
    teilweise: 'Stützräder teilweise – klicken zum Auswählen (anlegen oder abnehmen)',
  };
  const WHEELS_BADGE = { an: 'An', aus: 'Abgenommen', teilweise: 'Teilweise' };

  function wheelsState() {
    if (own(pendingVal, 'stuetzraeder')) return pendingVal.stuetzraeder ? 'an' : 'aus';
    const w = String(state.stuetzraeder || '');
    return own(WHEELS_SUB, w) ? w : '';
  }

  function renderSwitches() {
    const s = state;
    const val = (key) => (own(pendingVal, key) ? !!pendingVal[key] : !!s[key]);
    for (const id of ['sw-erlauben', 'sec-sw-erlauben']) setSwitch(byId(id), val('auto_confirm'));
    setSwitch(byId('sw-vorlesen'), val('speak'));
    // "Gesprochenes sofort senden" (nur, wenn die KI den Schalter kennt)
    byId('row-sofort').hidden = typeof s.voice_autosend !== 'boolean';
    setSwitch(byId('sw-sofort'), val('voice_autosend'));
    byId('sub-sofort').textContent = val('voice_autosend')
      ? 'nach dem Loslassen von Mikrofon/F2 – ohne Enter'
      : 'erst prüfen, dann Enter';
    const w = wheelsState();
    const row = document.querySelector('.switch-row[data-toggle="stuetzraeder"]');
    row.hidden = !w;
    row.dataset.state = w;
    byId('sec-wheels').dataset.state = w || 'teilweise';
    byId('sec-wheels').hidden = !w; // aeltere KI ohne Stuetzraeder
    row.title = WHEELS_TIP[w] || '';
    for (const id of ['sw-stuetzraeder', 'sec-sw-stuetzraeder']) {
      const b = byId(id);
      setSwitch(b, w === 'an');
      b.classList.toggle('mixed', w === 'teilweise');
      b.title = WHEELS_TIP[w] || '';
    }
    if (w) byId('sub-stuetzraeder').textContent = WHEELS_SUB[w];
    syncWheelsDialog(w);
    const n = kiName();
    byId('sec-wheels-badge').textContent = WHEELS_BADGE[w] || '–';
    byId('sec-wheels-text').textContent = w === 'an'
      ? 'Sind dran: ' + n + ' fragt vor jeder Änderung und bleibt im Arbeitsordner.'
      : w === 'aus' ? 'Sind ab: ' + n + ' darf am ganzen PC alles ohne Rückfrage.'
        : 'Teilweise: Einzelne Schutzfunktionen sind anders eingestellt. Klick auf den Schalter – dann kannst du sie ganz anlegen oder ganz abnehmen.';
    byId('sec-title').textContent = 'Was ' + n + ' ohne Nachfrage darf';
    const facts = byId('sec-facts');
    facts.replaceChildren();
    const fact = (k, v, cls, ic) => {
      const d = h('div', 'sec-fact');
      const vv = h('div', 'sf-v ' + cls);
      vv.append(icon(ic), h('span', null, v));
      d.append(h('div', 'sf-k', k), vv);
      facts.append(d);
    };
    fact('Sicherer Modus', s.safe_mode ? 'An' : 'Aus', s.safe_mode ? 'good' : 'bad', s.safe_mode ? 'shield' : 'shieldOff');
    fact('Zugriff', s.full_access ? 'Ganzer PC' : 'Nur Arbeitsordner', s.full_access ? 'bad' : 'good', s.full_access ? 'monitor' : 'folder');
    fact('Rückfragen', val('auto_confirm') ? 'Aus – fragt nicht' : 'An – fragt vorher', val('auto_confirm') ? 'mid' : 'good',
      val('auto_confirm') ? 'zap' : 'checkCircle');
  }

  function renderAlerts() {
    const box = byId('sb-alerts');
    box.replaceChildren();
    const s = state;
    const add = (cls, ic, title, text, btnLabel, cmd) => {
      const a = h('div', 'alert ' + cls);
      a.append(icon(ic), h('div', 'alert-title', title));
      if (text) {
        const t = h('div', 'alert-text');
        if (text instanceof Node) t.append(text); else t.textContent = text;
        a.append(t);
      }
      if (btnLabel) {
        const b = h('button', 'btn small ' + (cls === 'update' ? 'primary' : 'secondary'), btnLabel);
        b.type = 'button';
        b.addEventListener('click', () => {
          closeSidebar();
          if (typeof cmd === 'function') cmd(); else send(cmd);
        });
        a.append(b);
      }
      box.append(a);
    };
    // aeltere KI ohne Update-Anzeige: Hinweis als Karte (sonst steht es oben bei der Version)
    if (s.update && s.update.new && !updStatus()) {
      add('update', 'download', 'Update verfügbar', 'Version ' + s.update.new + ' ist bereit.', 'Jetzt aktualisieren', '/update');
    }
    if (s.api_key_missing) {
      add('danger', 'key', 'API-Schlüssel fehlt', 'Ohne Schlüssel kann ich nicht denken. Er ist in einer Minute eingerichtet.',
        'Jetzt einrichten', () => openSetup(true));
    }
    if (s.started_by) {
      add('warn', 'power', 'Automatisch gestartet', 'Ich wurde automatisch gestartet – ' + s.started_by + '.',
        'Autostart prüfen', '/autostart');
    }
    byId('menu-dot').hidden = !box.childElementCount && !newVersion();
  }

  // Senden geht immer – auch waehrend die KI arbeitet: dann kommt die Nachricht in die
  // Warteschlange (Enter) oder unterbricht die laufende Antwort (Strg+Enter). Anhalten hat
  // einen eigenen Knopf ("Stopp", Esc).
  function setBusy(b) {
    busy = !!b;
    // Fokus liegt auf "Stopp", der gleich verschwindet -> zurueck ins Eingabefeld
    const refocus = document.activeElement === stopBtn && (!busy || ended);
    stopBtn.hidden = !busy || ended;
    if (refocus) focusInput();
    byId('hint').classList.toggle('busy', busy);
    updateSendBtn();
    updateStatus();
    tourBusy(busy);
    if (!busy) rs.phase = '';
    moodSync();
  }

  function updateSendBtn() {
    const has = !!input.value.trim();
    sendBtn.disabled = ended || !has;
    hintNow.disabled = ended || !has;
    // AFK-Modus laeuft: jede Nachricht heisst "ich bin zurueck" (sie wartet nicht);
    // startet er gleich, wartet sie – und der AFK-Modus startet dann nicht
    const away = ended ? '' : afkRunning() ? 'afk' : busy && state.afk_pending === true ? 'afkpending' : '';
    byId('hint').classList.toggle('afk', away === 'afk');
    const mode = away || (busy ? 'queue' : 'send');
    if (sendBtn.dataset.mode === mode) return;
    sendBtn.dataset.mode = mode;
    sendBtn.replaceChildren(icon(mode === 'afk' ? 'send' : mode === 'afkpending' ? 'queue' : mode));
    let tip = 'Senden (Enter)';
    let label = tip;
    if (mode === 'afk') {
      tip = 'Senden (Enter) – du bist zurück: der AFK-Modus endet und ich antworte dir gleich';
      label = 'Senden (Enter) – du bist zurück, der AFK-Modus endet';
    } else if (mode === 'afkpending') {
      tip = 'In die Warteschlange (Enter) – kommt dran, sobald ich fertig bin; der AFK-Modus startet dann nicht. Strg+Enter: unterbrechen & senden';
      label = 'In die Warteschlange (Enter), der AFK-Modus startet dann nicht. Strg+Enter: unterbrechen und sofort senden';
    } else if (mode === 'queue') {
      tip = 'In die Warteschlange (Enter) – kommt dran, sobald ich fertig bin. Strg+Enter: unterbrechen & senden';
      label = 'In die Warteschlange (Enter). Strg+Enter: unterbrechen und sofort senden';
    }
    sendBtn.title = tip;
    sendBtn.setAttribute('aria-label', label);
  }

  function updateStatus() {
    const st = byId('status');
    let s = 'ready';
    let t = 'Bereit';
    if (ended) { s = 'off'; t = 'Beendet'; }
    else if (!connected) { s = everConnected ? 'off' : 'connecting'; t = everConnected ? 'Getrennt' : 'Verbinde …'; }
    else if (voice.phase === 'recording' || voice.phase === 'starting' || voice.phase === 'remote') { s = 'rec'; t = 'Hört zu …'; }
    else if (voice.phase === 'stopping' || voice.phase === 'remote-rec') { s = 'busy'; t = 'Erkennt Sprache …'; }
    else if (busy) { s = 'busy'; t = 'Arbeitet …'; }
    else if (speakingOn) { s = 'busy'; t = 'Liest vor …'; }
    st.dataset.s = s;
    byId('status-text').textContent = t;
  }

  // Schalter (Seitenleiste und Reiter "Sicherheit")
  const TOGGLES = {
    erlauben: 'auto_confirm', vorlesen: 'speak', stuetzraeder: 'stuetzraeder', sofort_senden: 'voice_autosend',
  };
  async function toggleSetting(name) {
    const key = pick(TOGGLES, name);
    if (!key || ended || pendingToggle[key]) return;
    let value;
    if (key === 'stuetzraeder') {
      // aus -> an (sofort); an -> ab (erst warnen); teilweise -> Auswahl: anlegen / abnehmen (mit Warnung)
      pendingToggle[key] = true; // waehrend Auswahl/Warnung kein zweiter Klick
      if (state.stuetzraeder === 'teilweise') {
        const choice = await wheelsChoice();
        value = choice === 'an' ? true : choice === 'aus' && await wheelsWarning() ? false : null;
      } else if (state.stuetzraeder === 'an') value = await wheelsWarning() ? false : null;
      else value = true;
      pendingToggle[key] = false;
      if (value === null || ended) return;
    } else value = !state[key];
    pendingToggle[key] = true;
    pendingVal[key] = value;
    renderSwitches();
    const r = await post('/api/toggle', { name, value });
    pendingToggle[key] = false;
    delete pendingVal[key];
    if (r.ok && r.state) applyState(r.state);
    else {
      if (r.ok && key !== 'stuetzraeder') state[key] = value;
      renderSwitches();
      if (!r.ok) toast(r.error || 'Die Einstellung konnte nicht geändert werden.', 'error');
    }
    if (r.ok && key === 'stuetzraeder') {
      toast(value ? 'Stützräder sind dran – ich frage vor Änderungen.' : 'Stützräder sind ab – ich darf jetzt alles ohne Rückfrage.',
        value ? 'ok' : 'info', 4200);
    }
    if (r.ok && key === 'voice_autosend') {
      toast(value ? 'Gesprochenes schicke ich jetzt sofort ab – ohne Enter.'
        : 'Gesprochenes landet wieder erst im Eingabefeld – Enter schickt es ab.', 'ok');
    }
  }
  for (const row of document.querySelectorAll('[data-toggle]')) {
    row.addEventListener('click', () => toggleSetting(row.dataset.toggle));
  }
  for (const b of document.querySelectorAll('[data-switch]')) {
    b.addEventListener('click', () => toggleSetting(b.dataset.switch));
  }

  // Befehls-Knoepfe
  for (const b of document.querySelectorAll('[data-cmd]')) {
    b.addEventListener('click', () => { closeSidebar(); send(b.dataset.cmd); });
  }
  byId('tb-update').addEventListener('click', () => send('/update'));

  // =====================================================================
  // Update-Anzeige in der Seitenleiste ("Auf dem neuesten Stand")
  //  state.update_status = {state: aktuell|neu|pruefe|unbekannt|aus, current, latest, checked, error}
  //  "Jetzt pruefen" -> POST /api/update (prueft nur), Ergebnis kommt als state-Ereignis.
  // =====================================================================
  const UPD_STATES = new Set(['aktuell', 'neu', 'pruefe', 'unbekannt', 'aus']);
  const upd = {
    local: false,  // Klick auf "Jetzt pruefen": schon "Pruefe …" zeigen, bis der Server es bestaetigt
    manual: false, // vom Nutzer ausgeloest -> Ergebnis als Meldung
    saw: false,    // Server hat "pruefe" gemeldet
    since: 0,      // Zeitpunkt des Klicks (ms)
    posted: false, // Server hat den Auftrag angenommen
    rehello: false, // seit dem Klick neu verbunden (frischer Stand, "pruefe" evtl. verpasst)
    timer: 0,
    late: 0,
  };

  /** Update-Stand vom Server (null = aeltere KI ohne Anzeige). */
  function updStatus() {
    const us = state.update_status;
    if (!us || typeof us !== 'object') return null;
    const st = String(us.state || '');
    return {
      state: UPD_STATES.has(st) ? st : 'unbekannt',
      current: String(us.current || state.version || ''),
      latest: us.latest ? String(us.latest) : '',
      checked: us.checked ? String(us.checked) : '',
      error: us.error ? String(us.error) : '',
    };
  }

  /** Technischen Fehler der Update-Pruefung in einfache Worte fassen ('' = keiner). */
  function updErrorText(err) {
    const e = String(err || '');
    if (!e) return '';
    if (/11001|11002|11004|getaddrinfo|name or service|name resolution|resolve host|nodename|no address|10051|10065|unreachable/i.test(e)) {
      return 'Keine Internetverbindung.';
    }
    if (/timed? ?out|10060|zeitüberschreitung/i.test(e)) return 'GitHub hat nicht rechtzeitig geantwortet.';
    if (/10061|10054|refused|reset by peer|connection (?:aborted|closed)|remote end closed/i.test(e)) {
      return 'Die Verbindung zu GitHub ist abgebrochen.';
    }
    if (/ssl|certificate|zertifikat/i.test(e)) return 'Die sichere Verbindung zu GitHub hat nicht geklappt.';
    if (/HTTP Error 40[39]|HTTP Error 429|rate limit/i.test(e)) return 'GitHub lässt gerade keine Abfrage zu – versuch es später nochmal.';
    if (/HTTP Error 404/i.test(e)) return 'Die Update-Quelle wurde nicht gefunden.';
    if (/HTTP Error 5\d\d/i.test(e)) return 'GitHub hat gerade Probleme – versuch es später nochmal.';
    return e.length > 160 ? e.slice(0, 157) + ' …' : e; // unbekannt: so, wie er kam (nur als Text)
  }

  /** Neuere Version, die installiert werden kann ('' = keine). */
  function newVersion() {
    if (state.update && state.update.new) return String(state.update.new);
    const us = updStatus();
    return us && us.state === 'neu' ? us.latest || '?' : '';
  }

  /** "2026-11-08T01:00:00" (lokale Zeit) -> Date oder null. */
  function parseWhen(v) {
    const d = v ? new Date(v) : null;
    return d && !Number.isNaN(d.getTime()) ? d : null;
  }

  function relTime(d) {
    const min = Math.floor((Date.now() - d.getTime()) / 60000);
    if (min < 1) return 'gerade eben';
    if (min < 60) return 'vor ' + min + ' Min.';
    const hrs = Math.floor(min / 60);
    if (hrs < 24) return 'vor ' + hrs + ' Std.';
    const days = Math.round(hrs / 24);
    if (days <= 1) return 'gestern';
    if (days < 7) return 'vor ' + days + ' Tagen';
    return 'am ' + d.toLocaleDateString('de-DE');
  }

  function renderUpdate() {
    const box = byId('sb-upd');
    const us = updStatus();
    box.hidden = !us;
    if (!us) return;
    const st = upd.local ? 'pruefe' : us.state;
    const when = parseWhen(us.checked);
    const whenText = when ? 'geprüft ' + relTime(when) : '';
    const whenFull = when ? 'Zuletzt geprüft ' + relTime(when) + ' (' +
      when.toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' }) + ').' : '';
    const failed = !!us.error && st !== 'pruefe' && st !== 'neu';
    let ic = 'refresh';
    let title = 'Noch nicht geprüft';
    let sub = 'Version ' + us.current;
    let tip = 'Du hast Version ' + us.current + '.';
    let btn = 'check';
    if (st === 'aktuell') {
      ic = 'checkCircle';
      title = 'Auf dem neuesten Stand';
      sub = whenText || sub;
      tip = 'Version ' + us.current + ' ist die neueste.' + (whenFull ? '\n' + whenFull : '');
    } else if (st === 'neu') {
      const v = us.latest || newVersion();
      ic = 'download';
      title = v && v !== '?' ? 'Update auf ' + v + ' verfügbar' : 'Update verfügbar';
      sub = 'du hast ' + us.current;
      tip = 'Neue Version ' + v + ' – du hast ' + us.current + '.' + (whenFull ? '\n' + whenFull : '');
      btn = 'install';
    } else if (st === 'pruefe') {
      ic = '';
      title = 'Prüfe …';
      sub = 'schaue nach einer neuen Version';
      tip = '';
      btn = '';
    } else if (st === 'aus') {
      ic = 'pause';
      title = 'Automatische Updates aus';
      sub = whenText || 'nur auf Wunsch';
      tip = 'Ich schaue nicht von selbst nach neuen Versionen.' + (whenFull ? '\n' + whenFull : '');
    }
    if (failed) {
      ic = 'alertCircle';
      title = 'Prüfen hat nicht geklappt';
      sub = 'Version ' + us.current;
      const plain = updErrorText(us.error);
      tip = 'Prüfen hat nicht geklappt: ' + plain + (plain !== us.error ? '\nDetails: ' + us.error : '') + (whenFull ? '\n' + whenFull : '');
    }
    box.dataset.state = st;
    box.classList.toggle('err', failed);
    box.title = tip;
    // nur Geaendertes neu setzen: kein erneutes Vorlesen (role=status), Spinner laeuft weiter
    const icEl = byId('upd-ic');
    if (icEl.dataset.ic !== (ic || 'spin')) {
      icEl.dataset.ic = ic || 'spin';
      icEl.replaceChildren(ic ? icon(ic) : h('span', 'spinner'));
    }
    if (byId('upd-title').textContent !== title) byId('upd-title').textContent = title;
    if (byId('upd-sub').textContent !== sub) byId('upd-sub').textContent = sub;
    const b = byId('upd-btn');
    b.hidden = !btn;
    b.dataset.act = btn;
    b.disabled = ended;
    b.className = 'btn small upd-btn ' + (btn === 'install' ? 'primary' : 'secondary');
    b.textContent = btn === 'install' ? 'Installieren' : 'Jetzt prüfen';
    b.title = btn === 'install' ? 'Update installieren (/update)' : 'Jetzt nach einer neuen Version schauen';
  }

  /** Ist dieser Stand schon das Ergebnis von "Jetzt pruefen"? */
  function updIsResult(us) {
    if (upd.saw) return true; // "pruefe" gesehen -> der naechste andere Stand ist das Ergebnis
    if (!upd.posted) return false;
    if (upd.rehello) return true; // neu verbunden: der Stand ist frisch, "pruefe" ging verloren
    const d = parseWhen(us.checked); // erfolgreich geprueft nach dem Klick (Zeit nur auf Sekunden genau)
    return !!d && d.getTime() >= upd.since - 1500;
  }

  /** Neuer Stand vom Server: Anzeige erneuern; nach "Jetzt pruefen" das Ergebnis melden. */
  function onUpdateState() {
    const us = updStatus();
    if (us && us.state === 'pruefe') {
      upd.saw = true;
      upd.local = false;
    } else if (us && upd.manual && updIsResult(us)) {
      upd.manual = false;
      upd.local = false;
      clearTimeout(upd.timer);
      clearTimeout(upd.late);
      if (us.error) toast('Prüfen hat nicht geklappt: ' + updErrorText(us.error), 'error', 6500);
      else if (us.state === 'neu') toast('Update auf ' + (us.latest || newVersion()) + ' verfügbar – „Installieren“ holt es.', 'ok', 5000);
      else toast('Du hast die neueste Version (' + us.current + ').', 'ok');
    }
    renderUpdate();
  }

  /** Neu verbunden (hello): Stand ist frisch – falls "Jetzt pruefen" laeuft, zaehlt er als Ergebnis. */
  function updHello() {
    if (upd.manual) upd.rehello = true;
  }

  async function checkUpdateNow() {
    const us = updStatus();
    if (!us || ended || upd.local || us.state === 'pruefe') return;
    upd.manual = true;
    upd.saw = false;
    upd.local = true;
    upd.since = Date.now();
    upd.posted = false;
    upd.rehello = false;
    clearTimeout(upd.late);
    renderUpdate();
    const r = await post('/api/update', { action: 'check' });
    if (!upd.manual) return; // schon erledigt (z.B. beendet)
    if (!r.ok) {
      upd.local = false;
      upd.manual = false;
      renderUpdate();
      toast(r.error || 'Prüfen hat nicht geklappt.', 'error');
      return;
    }
    upd.posted = true;
    // Neu verbunden, bevor die Antwort kam: der Stand ist evtl. schon das Ergebnis.
    // Kurz warten – kommt noch "pruefe", laeuft alles wie gewohnt.
    if (upd.rehello && !upd.saw) upd.late = setTimeout(() => { if (upd.manual && !upd.saw) onUpdateState(); }, 400);
    // Falls das "pruefe"-Ereignis ausbleibt (Verbindung weg): nicht ewig "Prüfe …" zeigen
    clearTimeout(upd.timer);
    upd.timer = setTimeout(() => {
      if (!upd.local) return;
      upd.local = false;
      upd.manual = false;
      renderUpdate();
    }, 20000);
  }

  byId('upd-btn').addEventListener('click', (e) => {
    if (e.currentTarget.dataset.act === 'install') {
      closeSidebar();
      send('/update');
    } else checkUpdateNow();
  });
  setInterval(() => { if (!byId('sb-upd').hidden) renderUpdate(); }, 30000); // "vor 5 Min." aktuell halten
  const newChat = () => { closeSidebar(); if (!afkBlocksNew()) send('/neu'); };
  byId('sb-new').addEventListener('click', newChat);
  byId('tb-new').addEventListener('click', newChat);
  byId('sb-profile').addEventListener('click', () => openProfile());

  // Seitenleiste als Schublade (schmale Fenster)
  const menuBtn = byId('menu-btn');
  function openSidebar(noFocus) {
    app.classList.add('sb-open');
    menuBtn.setAttribute('aria-expanded', 'true');
    if (noFocus !== true) setTimeout(() => byId('sb-close').focus(), 50);
  }
  function closeSidebar() {
    if (!app.classList.contains('sb-open')) return;
    app.classList.remove('sb-open');
    menuBtn.setAttribute('aria-expanded', 'false');
  }
  menuBtn.addEventListener('click', () => openSidebar());
  byId('sb-close').addEventListener('click', () => { closeSidebar(); menuBtn.focus(); });
  byId('scrim').addEventListener('click', closeSidebar);

  // Design: automatisch / hell / dunkel
  const THEMES = ['auto', 'light', 'dark'];
  const THEME_INFO = {
    auto: ['contrast', 'Design: automatisch (wie Windows)'],
    light: ['sun', 'Design: hell'],
    dark: ['moon', 'Design: dunkel'],
  };
  let theme = 'auto';
  try { theme = localStorage.getItem('ki-theme') || 'auto'; } catch (_) { /* egal */ }
  if (!THEMES.includes(theme)) theme = 'auto';
  function applyTheme(t) {
    theme = t;
    if (t === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = t;
    const btn = byId('theme-btn');
    btn.replaceChildren(icon(THEME_INFO[t][0]));
    btn.title = THEME_INFO[t][1] + ' – klicken zum Wechseln';
    btn.setAttribute('aria-label', THEME_INFO[t][1] + ', wechseln');
    try { localStorage.setItem('ki-theme', t); } catch (_) { /* egal */ }
    sphere.refresh(); // Sphaere im hellen Thema satter, mit Schatten
  }
  byId('theme-btn').addEventListener('click', () => applyTheme(THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]));
  applyTheme(theme);

  // =====================================================================
  // Meldungen (Toasts)
  // =====================================================================
  function toast(text, kind, ms) {
    const t = h('div', 'toast ' + (kind || 'info'));
    t.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    t.append(icon(kind === 'error' ? 'alertCircle' : kind === 'ok' ? 'checkCircle' : 'info'), h('span', null, text));
    const box = byId('toasts');
    box.append(t);
    while (box.childElementCount > 3) box.firstElementChild.remove();
    setTimeout(() => {
      t.classList.add('leaving');
      setTimeout(() => t.remove(), 250);
    }, ms || 3800);
  }

  // =====================================================================
  // Scrollen: unten bleiben, ausser der Nutzer hat hochgescrollt
  // =====================================================================
  let stick = true;
  let lastTop = 0;
  let userUpAt = -Infinity; // wann der Nutzer zuletzt nach oben gescrollt hat (Rad, Tasten)
  let dragging = false;  // Bildlaufleiste oder Finger wird gerade gezogen
  const jumpBtn = byId('jump');
  const distBottom = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  const userActive = () => dragging || performance.now() - userUpAt < 350;
  function userUp() { userUpAt = performance.now(); stick = false; }
  scroller.addEventListener('scroll', () => {
    // Jedes Hochscrollen loest das Mitlaufen (auch kleine Touchpad-Schritte). Schrumpft nur
    // der Inhalt (Browser schiebt die Position nach oben, bleibt aber ganz unten), bleibt es an.
    const top = scroller.scrollTop;
    const d = distBottom();
    const active = userActive();
    if (top < lastTop - 0.5 && (d >= 2 || active)) stick = false;
    else if (!active && d < 2) stick = true;
    else if (!active && top > lastTop && d < 70) stick = true; // selbst wieder nach unten gescrollt
    lastTop = top;
    if (stick) jumpBtn.hidden = true;
  }, { passive: true });
  scroller.addEventListener('wheel', (e) => {
    if (e.ctrlKey) return; // Zoomen (auch Touchpad-Spreizen) ist kein Hochscrollen
    if (e.deltaY < 0 && scroller.scrollTop > 0) userUp();
  }, { passive: true });
  scroller.addEventListener('keydown', (e) => {
    if (['ArrowUp', 'PageUp', 'Home'].includes(e.key)) userUp();
  });
  scroller.addEventListener('mousedown', (e) => {
    // Klick auf die Bildlaufleiste
    if (e.offsetX >= scroller.clientWidth) { dragging = true; stick = false; }
  });
  scroller.addEventListener('touchstart', () => { dragging = true; }, { passive: true });
  const endDrag = () => {
    if (!dragging) return;
    dragging = false;
    if (distBottom() < 2) stick = true;
  };
  window.addEventListener('mouseup', endDrag);
  window.addEventListener('touchend', endDrag, { passive: true });
  window.addEventListener('touchcancel', endDrag, { passive: true });
  let scrollQueued = false;
  function toBottom(force) {
    if (force) { stick = true; jumpBtn.hidden = true; }
    if (scrollQueued) return;
    scrollQueued = true;
    requestAnimationFrame(() => {
      scrollQueued = false;
      if (stick) {
        // Begruessung sichtbar (noch kein Gespraech, hoechstens Systemkarten wie "Neues Gespraech"):
        // nur so weit nach unten, dass die Sphaere oben nicht abgeschnitten wird
        let top = scroller.scrollHeight;
        if (!emptyEl.hidden) {
          let heroTop = -14;
          for (let el = byId('hero'); el && el !== scroller; el = el.offsetParent) heroTop += el.offsetTop;
          top = Math.max(0, Math.min(scroller.scrollHeight - scroller.clientHeight, heroTop));
        }
        scroller.scrollTop = top;
        lastTop = scroller.scrollTop;
      }
    });
  }
  function keepBottom() {
    if (stick) toBottom();
    else if (distBottom() < 2) { stick = true; jumpBtn.hidden = true; } // nichts zum Scrollen da
    else if (msgs.childElementCount) jumpBtn.hidden = false;
  }
  jumpBtn.addEventListener('click', () => { jumpBtn.hidden = true; toBottom(true); });
  if (window.ResizeObserver) {
    // auch wenn der Chat selbst kleiner wird (z.B. Warteliste/Eingabefeld darunter waechst)
    const ro = new ResizeObserver(() => { if (stick) toBottom(); });
    ro.observe(msgs);
    ro.observe(scroller);
  }

  // Kopfzeile: der Modell-Chip wird bei Platzmangel schmaler (CSS, mit "…"). Reicht es selbst dafuer
  // nicht (z.B. "Update verfuegbar" + grosse Schrift + "Arbeitet …"), faellt er weg – der Modellname
  // steht auch auf der Gehirn-Karte in der Seitenleiste. Nie waagerecht scrollen.
  const topbarEl = document.querySelector('.topbar');
  function fitTopbar() {
    if (!topbarEl) return;
    topbarEl.classList.remove('tight');
    if (topbarEl.scrollWidth > topbarEl.clientWidth + 1) topbarEl.classList.add('tight');
  }
  if (window.ResizeObserver && topbarEl) {
    const tro = new ResizeObserver(() => fitTopbar());
    for (const el of [topbarEl, byId('status'), byId('tb-update'), byId('tb-new'), byId('tb-jarvis')]) if (el) tro.observe(el);
  }

  // =====================================================================
  // Chat-Elemente
  // =====================================================================
  let historyReady = false;

  function updateEmpty() {
    // Begruessung, solange noch niemand etwas gesagt hat (Systemkarten allein zaehlen nicht)
    const talked = !!msgs.querySelector('.msg');
    emptyEl.hidden = !historyReady || talked;
    byId('tb-new').hidden = !talked || ended;
    byId('tour-offer').hidden = !historyReady || state.tutorial_done !== false || tourLater || tour.open || ended;
    markLatest();
  }
  function added() { updateEmpty(); keepBottom(); }

  function aiAvatar() {
    const a = h('div', 'avatar ai-avatar');
    a.setAttribute('aria-hidden', 'true');
    a.append(h('span', 'av-l', initial()));
    return a;
  }

  // ---------- Novas Gemuet: alle Sphaeren zeigen, was sie gerade tut ----------
  let histBuilding = false;  // Verlauf wird aufgebaut: erst am Ende die neueste Antwort beleben
  let speakingOn = false;    // Vorlesen am PC (Ereignis "speaking")
  const rs = { phase: '' };  // laufende Antwort: thinking | working | writing

  /** Nur die Sphaere der neuesten Antwort ist lebendig; aeltere sind ein ruhiges Standbild. */
  function markLatest() {
    if (histBuilding) return;
    let el = msgs.lastElementChild;
    while (el && !(el.classList.contains('msg') && el.classList.contains('ai'))) el = el.previousElementSibling;
    sphere.latest(el ? el.querySelector('.ai-avatar') : null);
  }

  function moodSync() {
    let m = 'idle';
    const vp = voice.phase;
    if (jv.open) m = jv.state === 'thinking' && jv.working ? 'working' : jv.state || 'starting';
    else if (askCur && !modal.hidden) m = 'asking';
    else if (vp === 'starting' || vp === 'recording' || vp === 'remote') m = 'hearing';
    else if (vp === 'stopping' || vp === 'remote-rec') m = 'recognizing';
    else if (su.checking) m = 'thinking';
    else if (speakingOn) m = 'speaking';
    else if (reply || (busy && !afkResting())) m = rs.phase || 'thinking';
    sphere.mood(m);
  }

  /** Vorlesen am PC an/aus (Ereignis "speaking"; nach Trennung/Ende zuruecksetzen, das "aus" fehlt evtl.). */
  function setSpeaking(on) {
    speakingOn = !!on;
    sphere.talk('server', speakingOn);
    moodSync();
    updateStatus();
  }

  function addUser(text) {
    const row = h('div', 'msg user' + (String(text).trim().startsWith('/') ? ' cmd' : ''));
    row.append(h('div', 'bubble', text));
    msgs.append(row);
    added();
    return row;
  }

  // Ausgaben der Befehle (/status, /kosten, /hilfe) haben eingerueckte Spalten:
  //   "  Provider:        deepseek"  oder  "  /hilfe              - Hilfe anzeigen"
  const RE_KV_STRICT = /^\s{2,}([^\s:\-*+\u2022>|#`\d][^:]{0,40}?):\s{2,}(\S.*)$/;
  const RE_KV = /^\s{2,}([^\s:\-*+\u2022>|#`\d][^:]{0,40}?):\s+(\S.*)$/;
  const RE_CMDROW = /^\s{2,}(\/[^\s-]\S*(?: [^\s-]\S*)*?)\s+-\s+(\S.*)$/;

  /** Zerlegt den Text in Markdown-Teile und Spalten-Bloecke. */
  function splitColumns(text) {
    const lines = String(text == null ? '' : text).replace(/\r\n?/g, '\n').split('\n');
    const parts = [];
    let md = [];
    let fence = false;
    let i = 0;
    const flushMd = () => { if (md.length) parts.push({ md: md.join('\n') }); md = []; };
    while (i < lines.length) {
      const l = lines[i];
      if (RE_FENCE.test(l)) fence = !fence;
      if (fence || !/^\s{2,}\S/.test(l)) { md.push(l); i++; continue; }
      // eingerueckter Abschnitt: nur umbauen, wenn er wirklich nach Spalten aussieht
      let j = i;
      let strong = 0;
      while (j < lines.length && /^\s{2,}\S/.test(lines[j]) && !RE_FENCE.test(lines[j])) {
        if (RE_KV_STRICT.test(lines[j]) || RE_CMDROW.test(lines[j])) strong++;
        j++;
      }
      if (strong < 2) { md.push(...lines.slice(i, j)); i = j; continue; }
      const rows = [];
      let cmds = 0;
      for (const row of lines.slice(i, j)) {
        let m;
        if ((m = row.match(RE_CMDROW))) { rows.push({ k: m[1], v: m[2], cmd: true }); cmds++; }
        else if ((m = row.match(RE_KV))) rows.push({ k: m[1].trim(), v: m[2] });
        else rows.push({ note: row.trim() });
      }
      // "Status:" direkt davor wird zur Ueberschrift des Blocks
      let title = '';
      const prev = md.length ? md[md.length - 1] : '';
      if (prev && /^\S.{0,60}:\s*$/.test(prev)) { title = prev.trim().replace(/:$/, ''); md.pop(); }
      flushMd();
      parts.push({ rows, title, cmds: cmds > rows.length / 2 });
      i = j;
    }
    flushMd();
    return parts;
  }

  const RE_ONOFF = /^(AN|AUS|ja|nein|an|aus)\b/;
  function kvValue(v) {
    const el = h('div', 'kv-v');
    const m = v.match(RE_ONOFF);
    if (m) {
      const on = /^(AN|ja|an)$/.test(m[1]);
      el.append(h('span', 'kv-pill' + (on ? ' on' : ''), m[1]), v.slice(m[1].length));
    } else {
      if (/^(\/|[A-Za-z]:\\|~\/)/.test(v)) el.classList.add('path');
      el.textContent = v;
    }
    return el;
  }

  function columnsBlock(part) {
    const wrap = h('div', 'kv-block');
    if (part.title) wrap.append(h('div', 'kv-title', part.title));
    const grid = h('div', 'kv' + (part.cmds ? ' cmds' : ''));
    for (const r of part.rows) {
      if (r.note != null) { grid.append(h('div', 'kv-note', r.note)); continue; }
      if (r.cmd) {
        const b = h('button', 'kv-k kv-cmd', r.k);
        b.type = 'button';
        b.title = 'In die Eingabe übernehmen';
        b.addEventListener('click', () => {
          let v = r.k;
          const ph = v.search(/\s[<[]/);
          if (ph > 0) v = v.slice(0, ph);
          input.value = v + (v !== r.k ? ' ' : '');
          autosize();
          focusInput();
          input.setSelectionRange(input.value.length, input.value.length);
          updateCmdPop();
        });
        grid.append(b, h('div', 'kv-v', r.v));
      } else {
        grid.append(h('div', 'kv-k', r.k), kvValue(r.v));
      }
    }
    wrap.append(grid);
    return wrap;
  }

  /** Markdown einer Systemkarte (mit Spalten-Bloecken) sicher einsetzen. */
  function fillCardBody(body, text) {
    const parts = splitColumns(text);
    if (parts.length === 1 && parts[0].md != null) {
      body.innerHTML = renderMarkdown(parts[0].md); // renderMarkdown escaped alles
      return;
    }
    for (const part of parts) {
      if (part.md != null) {
        if (!part.md.trim()) continue;
        const d = h('div', 'md');
        d.innerHTML = renderMarkdown(part.md); // escaped
        body.append(d);
      } else {
        body.append(columnsBlock(part));
      }
    }
  }

  function addCard(level, mdText, opts) {
    const lv = ['info', 'warn', 'ok'].includes(level) ? level : 'info';
    const card = h('div', 'card ' + lv);
    card.setAttribute('role', 'note');
    card.append(icon(lv === 'warn' ? 'alert' : lv === 'ok' ? 'checkCircle' : 'info', 'card-ic'));
    const body = h('div', 'card-body md');
    fillCardBody(body, mdText);
    if (opts && opts.button) {
      const b = h('button', 'btn small primary', opts.button.label);
      b.type = 'button';
      b.addEventListener('click', opts.button.onClick);
      body.append(b);
    }
    card.append(body);
    msgs.append(card);
    added();
    return card;
  }

  function addError(text) {
    const card = h('div', 'card error');
    card.setAttribute('role', 'alert');
    card.append(icon('alertCircle', 'card-ic'));
    const body = h('div', 'card-body');
    body.append(h('div', 'card-title', 'Fehler'), h('div', 'card-text', text || 'Unbekannter Fehler.'));
    card.append(body);
    msgs.append(card);
    added();
  }

  function addSysLine(ic, text) {
    const d = h('div', 'sys-line');
    d.append(icon(ic), h('span', null, text));
    msgs.append(d);
    added();
  }

  // Werkzeug-Namen freundlich anzeigen
  const TOOL_INFO = {
    datei_lesen: ['file', 'Datei lesen'],
    datei_schreiben: ['pen', 'Datei schreiben'],
    datei_bearbeiten: ['pen', 'Datei bearbeiten'],
    datei_loeschen: ['trash', 'Datei löschen'],
    ordner_auflisten: ['folder', 'Ordner ansehen'],
    shell_befehl: ['terminal', 'Befehl ausführen'],
    web_suche: ['search', 'Websuche'],
    web_abrufen: ['globe', 'Webseite abrufen'],
    merken: ['bookmark', 'Merken'],
    erinnern: ['brain', 'Erinnern'],
    vergessen: ['trash', 'Vergessen'],
    system_info: ['cpu', 'System-Info'],
    bildschirmfoto: ['monitor', 'Bildschirmfoto'],
    maus_klick: ['mouse', 'Mausklick'],
    tastatur_tippen: ['keyboard', 'Tippen'],
    tastenkombination: ['keyboard', 'Tastenkombination'],
    agent_beauftragen: ['bot', 'Agent beauftragen'],
    abwesenheit: ['moon', 'AFK-Modus'],
  };
  function toolInfo(name) {
    const n = String(name || 'werkzeug');
    const known = pick(TOOL_INFO, n);
    if (known) return known;
    const label = n.replace(/_/g, ' ').trim() || 'Werkzeug';
    return ['wrench', label.charAt(0).toUpperCase() + label.slice(1)];
  }
  const ROLE_NAMES = { recherche: 'Recherche', helfer: 'Helfer', pruefer: 'Prüfer', 'prüfer': 'Prüfer' };
  const roleLabel = (r) => pick(ROLE_NAMES, String(r).toLowerCase()) ||
    (String(r).charAt(0).toUpperCase() + String(r).slice(1));

  function addChip(host, name) {
    let row = host.lastElementChild;
    if (!row || !row.classList.contains('tools')) {
      row = h('div', 'tools');
      host.append(row);
    }
    const last = row.lastElementChild;
    if (last && last.dataset.name === String(name)) {
      const n = (Number(last.dataset.count) || 1) + 1;
      last.dataset.count = String(n);
      last.querySelector('.chip-count').textContent = '×' + n;
      return;
    }
    const [ic, label] = toolInfo(name);
    const chip = h('span', 'chip');
    chip.dataset.name = String(name);
    chip.title = 'Werkzeug: ' + name;
    chip.append(icon(ic), h('span', 'chip-label', label), h('span', 'chip-count'));
    row.append(chip);
  }

  function makeAgentBlock(role, task) {
    const el = h('details', 'agent running');
    el.open = true;
    const sum = h('summary');
    const st = h('span', 'agent-state');
    st.append(h('span', 'spinner'));
    const badge = h('span', 'agent-role');
    badge.append(icon('bot'), document.createTextNode('Agent ' + roleLabel(role)));
    const taskEl = h('span', 'agent-task', task || '');
    if (task) taskEl.title = task;
    const cnt = h('span', 'agent-count', 'arbeitet …');
    sum.append(st, badge, taskEl, cnt, icon('chevron', 'agent-chev'));
    const body = h('div', 'agent-body');
    el.append(sum, body);
    let touched = false;
    sum.addEventListener('click', () => { touched = true; });
    return {
      el, body, role, steps: 0, done: false,
      step() {
        this.steps++;
        cnt.textContent = this.steps === 1 ? '1 Schritt' : this.steps + ' Schritte';
      },
      /** kind: 'done' (Standard) oder 'stopped' (Antwort angehalten) */
      finish(kind) {
        if (this.done) return;
        this.done = true;
        const stopped = kind === 'stopped';
        el.classList.remove('running');
        el.classList.add(stopped ? 'stopped' : 'done');
        st.replaceChildren(icon(stopped ? 'pause' : 'check'));
        const word = stopped ? 'angehalten' : 'fertig';
        cnt.textContent = !this.steps ? word : (this.steps === 1 ? '1 Schritt' : this.steps + ' Schritte') + ' · ' + word;
        if (!touched) el.open = false;
      },
    };
  }

  /** Eine KI-Antwort (Sprechblase) mit Text-Abschnitten, Chips, Agenten. */
  class Reply {
    constructor() {
      this.row = h('div', 'msg ai');
      this.row.append(aiAvatar());
      const col = h('div', 'ai-col');
      this.bubble = h('div', 'bubble');
      this.content = h('div', 'content');
      this.live = h('div', 'live');
      this.bubble.append(this.content, this.live);
      this.meta = h('div', 'meta');
      col.append(this.bubble, this.meta);
      this.row.append(col);
      this.seg = null;
      this.segs = [];
      this.agents = [];
      this.think = null;
      this.active = false;
      msgs.append(this.row);
      added();
    }

    begin() {
      this.active = true;
      this.row.setAttribute('aria-busy', 'true');
      this.updateLive();
    }

    text(t) {
      if (!t) return;
      if (!this.seg) {
        const el = h('div', 'md seg');
        this.content.append(el);
        this.seg = { el, raw: '', timer: 0, last: 0, dirty: false };
        this.segs.push(this.seg);
      }
      const seg = this.seg;
      seg.raw += t;
      seg.dirty = true;
      if (!seg.timer) {
        // Neu-Rendern gedrosselt (hoechstens ca. 12x pro Sekunde)
        const wait = Math.max(0, 80 - (performance.now() - seg.last));
        seg.timer = setTimeout(() => { seg.timer = 0; this.paint(seg); }, wait);
      }
    }

    paint(seg) {
      seg.last = performance.now();
      seg.dirty = false;
      seg.el.innerHTML = renderMarkdown(seg.raw); // sicher: escaped
      keepBottom();
    }

    flush() {
      for (const s of this.segs) {
        if (s.timer) { clearTimeout(s.timer); s.timer = 0; }
        if (s.dirty) this.paint(s);
      }
    }

    agentFor(role) {
      return this.agents.find((b) => b.role === role && !b.done) ||
        [...this.agents].reverse().find((b) => b.role === role) || null;
    }

    tool(name, agent) {
      const blk = agent ? this.agentFor(agent) : null;
      if (blk) {
        addChip(blk.body, name);
        blk.step();
      } else {
        addChip(this.content, name);
        this.seg = null;
      }
      keepBottom();
    }

    agent(phase, role, task) {
      role = String(role || 'agent');
      if (phase === 'start') {
        const blk = makeAgentBlock(role, task);
        this.content.append(blk.el);
        this.agents.push(blk);
        this.seg = null;
      } else {
        const blk = this.agents.find((b) => b.role === role && !b.done);
        if (blk) blk.finish();
      }
      keepBottom();
    }

    info(text) {
      const d = h('div', 'info-line');
      d.append(icon('info'), h('span', null, text || ''));
      this.content.append(d);
      this.seg = null;
      keepBottom();
    }

    thinking(on) {
      if (on && !this.think) {
        const el = h('div', 'thinking');
        const time = h('span', 'thinking-time');
        el.append(h('span', 'spinner'), h('span', 'thinking-text', 'Denkt nach …'), time);
        const t0 = Date.now();
        const tick = () => { time.textContent = '(' + Math.floor((Date.now() - t0) / 1000) + ' s)'; };
        tick();
        this.think = { el, iv: setInterval(tick, 1000) };
      } else if (!on && this.think) {
        clearInterval(this.think.iv);
        this.think.el.remove();
        this.think = null;
      }
      this.updateLive();
    }

    updateLive() {
      // Denk-Anzeige oder Tipp-Punkte am Ende der Blase (nur bei Aenderung neu)
      const want = this.think ? this.think.el : this.active ? 'dots' : '';
      if (want === this.liveKind) return;
      this.liveKind = want;
      this.live.replaceChildren();
      if (this.think) this.live.append(this.think.el);
      else if (this.active) {
        const d = h('span', 'dots');
        d.setAttribute('aria-label', 'schreibt');
        d.append(h('i'), h('i'), h('i'));
        this.live.append(d);
      }
      keepBottom();
    }

    rawText() {
      return this.segs.map((s) => s.raw.trim()).filter(Boolean).join('\n\n');
    }

    isEmpty() {
      return !this.content.childElementCount || (!this.rawText() && !this.content.querySelector('.chip, .agent, .info-line'));
    }

    /** Timer anhalten, wenn die Blase verworfen wird (z.B. neues Gespraech). */
    dispose() {
      for (const s of this.segs) if (s.timer) { clearTimeout(s.timer); s.timer = 0; }
      this.thinking(false);
      this.active = false;
    }

    /** kind: 'done' | 'stopped' | 'error' */
    finish(kind) {
      this.flush();
      this.thinking(false);
      for (const b of this.agents) b.finish(kind === 'stopped' ? 'stopped' : 'done');
      this.active = false;
      this.row.removeAttribute('aria-busy');
      this.updateLive();
      if (this.isEmpty()) {
        this.row.remove();
        updateEmpty();
        if (kind === 'stopped') addSysLine('pause', 'Antwort angehalten');
        return;
      }
      this.meta.replaceChildren();
      if (kind === 'stopped') {
        const b = h('span', 'badge stopped');
        b.append(icon('pause'), document.createTextNode('angehalten'));
        this.meta.append(b);
      }
      const raw = this.rawText();
      if (raw) {
        const c = h('button', 'meta-btn');
        c.type = 'button';
        c.append(icon('copy'), h('span', null, 'Kopieren'));
        c.addEventListener('click', () => copyText(raw, c));
        this.meta.append(c);
      }
      keepBottom();
    }
  }

  let reply = null;

  function ensureReply() {
    if (!reply) {
      reply = new Reply();
      reply.begin();
    }
    return reply;
  }

  function endReply(kind) {
    if (!reply) {
      if (kind === 'stopped') addSysLine('pause', 'Antwort angehalten');
      return;
    }
    reply.finish(kind);
    reply = null;
  }

  // Kopieren (Codebloecke und ganze Antworten)
  async function copyText(text, btn) {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (_) {
      const ta = h('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.className = 'sr-only';
      document.body.append(ta);
      ta.select();
      try { ok = document.execCommand('copy'); } catch (__) { ok = false; }
      ta.remove();
    }
    if (!btn) return;
    const label = btn.querySelector('span:not(.ic)');
    if (!ok) { toast('Kopieren hat nicht geklappt.', 'error'); return; }
    btn.classList.add('done');
    if (label) label.textContent = 'Kopiert';
    btn.querySelector('.ic').replaceWith(icon('check'));
    setTimeout(() => {
      btn.classList.remove('done');
      if (label) label.textContent = 'Kopieren';
      btn.querySelector('.ic').replaceWith(icon('copy'));
    }, 1600);
  }
  msgs.addEventListener('click', (e) => {
    const b = e.target.closest('[data-copy]');
    if (!b) return;
    const code = b.closest('.code');
    if (code) copyText(code.querySelector('code').textContent, b);
  });

  // =====================================================================
  // Senden & Stopp
  // =====================================================================
  const pendingSent = []; // lokal schon angezeigt, Echo vom Server steht noch aus
  const ownMsgs = [];     // fuer Pfeil hoch
  let recallIdx = -1;

  function rememberOwn(text) {
    if (text.startsWith('\u{1F511} Schlüssel ')) return; // gekuerzter Schluessel: nutzlos fuer Pfeil hoch
    if (ownMsgs[ownMsgs.length - 1] !== text) ownMsgs.push(text);
    if (ownMsgs.length > 100) ownMsgs.shift();
  }

  // Eingefuegter API-Schluessel: nie voll anzeigen. Gleiche Regel wie der Server
  // (schluessel.find_key/mask), damit die gekuerzte Blase zum Echo passt.
  const RE_CHAT_KEY = /(^|[^A-Za-z0-9_-])(sk-[A-Za-z0-9_-]{20,})(?![A-Za-z0-9_-])/;
  const maskKey = (k) => (k.length > 12 ? k.slice(0, 6) + '…' + k.slice(-4) : '…');
  /** Was der Server als Echo zeigen wird – null, wenn kein Schluessel im Text steckt. */
  function keyShown(text) {
    const m = RE_CHAT_KEY.exec(text);
    if (!m) return null;
    const key = m[2];
    if (!text.startsWith('/')) return '\u{1F511} Schlüssel ' + maskKey(key);
    return text.split(key).join(maskKey(key));
  }

  /** interrupt: die laufende Antwort anhalten und diese Nachricht sofort beantworten (Strg+Enter). */
  async function send(text, fromInput, interrupt) {
    text = String(text || '').trim();
    if (!text || ended) return false;
    // /jarvis und /tutorial oeffnen die Ansichten direkt im Fenster (nicht senden)
    const low = text.toLowerCase();
    if (low === '/jarvis' || low === '/tutorial' || low === '/tour') {
      if (fromInput) {
        input.value = '';
        autosize();
        closeCmdPop();
      }
      rememberOwn(text);
      recallIdx = -1;
      if (low === '/jarvis') startJarvis(); else startTour();
      return true;
    }
    // "/neu" waehrend AFK: erst der Bericht (sonst loescht das neue Gespraech ihn ungesehen)
    if (/^\/neu(\s|$)/.test(low) && afkBlocksNew()) return false;
    // Schluessel: Blase nur gekuerzt (wie das Echo) und nicht fuer Pfeil hoch merken
    const masked = keyShown(text);
    const shown = masked || text;
    // Arbeitet die KI noch, wartet die Nachricht – ihre Blase kommt erst, wenn sie drankommt
    // (Ereignis "user"). Sonst gleich anzeigen.
    let row = null;
    let p = null;
    if (!busy) {
      row = addUser(shown);
      p = { text: shown, row, t: Date.now() };
      pendingSent.push(p);
    }
    if (!masked) rememberOwn(text);
    recallIdx = -1;
    if (fromInput) {
      input.value = '';
      autosize();
      closeCmdPop();
    }
    if (row) toBottom(true);
    const r = await post('/api/send', { text, interrupt: !!interrupt });
    if (!r.ok) {
      if (p) {
        const k = pendingSent.indexOf(p);
        if (k >= 0) pendingSent.splice(k, 1);
        row.remove();
        updateEmpty();
      }
      if (fromInput && !input.value) { input.value = text; autosize(); }
      toast(r.error || 'Senden hat nicht geklappt.', 'error');
      return false;
    }
    if (r.queued) {
      // Die KI war doch beschaeftigt: die Nachricht wartet. Eine schon gezeigte Blase wieder
      // wegnehmen (ausser ihr Echo kam schon – dann ist sie bereits dran).
      const k = p ? pendingSent.indexOf(p) : -1;
      if (k >= 0) {
        pendingSent.splice(k, 1);
        row.remove();
        updateEmpty();
      }
      if (!p || k >= 0) {
        queuedOwn.push(shown);
        if (queuedOwn.length > 40) queuedOwn.shift();
        // Schluessel: der Server gibt ihn nach "Stopp" nie zurueck (er geht nie ueber die Ereignisse) –
        // den Text nur hier im Fenster merken, damit er dann nicht spurlos verschwindet
        if (masked && r.id != null) {
          ownKeys.set(String(r.id), { raw: text, shown });
          if (ownKeys.size > 20) ownKeys.delete(ownKeys.keys().next().value);
        }
      }
      if (r.interrupt && r.id != null) {
        qs.now.set(String(r.id), Date.now()); // kommt gleich – nicht mit "Jetzt"/"✕" anbieten
        renderQueue();
      }
    }
    if (r.afk_ended) afkBack(); // du bist zurueck: Band zeigt "Willkommen zurueck", bis state.afk weg ist
    return true;
  }

  /** Ereignis "retract": die letzte Frage wurde mit einem Nachtrag zusammengefasst –
   *  ihre Blase und die angefangene (leere) Antwort verschwinden; die neue Frage kommt gleich. */
  function onRetract() {
    let el;
    if (reply) {
      el = reply.row.previousElementSibling;
      reply.dispose();
      reply.row.remove();
      reply = null;
    } else el = msgs.lastElementChild;
    // nur ueber Systemkarten/-zeilen hinweg suchen, nie eine aeltere Antwort ueberspringen
    while (el && !el.classList.contains('msg')) el = el.previousElementSibling;
    if (el && el.classList.contains('user')) {
      const text = el.querySelector('.bubble') ? el.querySelector('.bubble').textContent.trim() : '';
      const k = pendingSent.findIndex((p) => p.row === el);
      if (k >= 0) pendingSent.splice(k, 1);
      if (ownMsgs[ownMsgs.length - 1] === text) ownMsgs.pop();
      el.remove();
    }
    updateEmpty();
  }

  /** Info-Zeile ausserhalb einer Antwort (z.B. "Live-Mitschrift: 40 % geladen") – keine leere Blase. */
  function addInfoLine(text) {
    const progress = /^Live-Mitschrift:\s*\d+\s*%/i.test(text);
    const lastEl = msgs.lastElementChild;
    if (progress && lastEl && lastEl.dataset.kind === 'live-progress') {
      lastEl.querySelector('span:not(.ic)').textContent = text;
      return;
    }
    addSysLine('info', text);
    if (progress) msgs.lastElementChild.dataset.kind = 'live-progress';
  }

  function onUserEcho(text) {
    const t = String(text || '').trim();
    queueStarted();
    // eigener wartender Schluessel ist dran (wird jetzt eingerichtet): nicht mehr merken
    for (const [id, o] of ownKeys) if (o.shown === t) { ownKeys.delete(id); break; }
    // aeltere Eintraege (ohne Echo) aufraeumen
    while (pendingSent.length && Date.now() - pendingSent[0].t > 60000) pendingSent.shift();
    const k = pendingSent.findIndex((p) => p.text === t);
    if (k >= 0) { pendingSent.splice(k, 1); return; }
    addUser(t);
    // eigene wartende Nachricht kommt dran: schon fuer Pfeil hoch gemerkt
    const q = queuedOwn.indexOf(t);
    if (q >= 0) queuedOwn.splice(q, 1);
    else rememberOwn(t);
  }

  async function stop() {
    const keyIds = queueAll().map((it) => it.id).filter((id) => ownKeys.has(id));
    const r = await post('/api/stop', {});
    if (!r.ok) { toast(r.error || 'Anhalten hat nicht geklappt.', 'error'); return; }
    // wartende Schluessel kommen vom Server nicht zurueck: kurz auf das Echo warten (war er schon dran?),
    // sonst lokal wieder ins Feld
    if (keyIds.length) setTimeout(() => keysBack(keyIds), 700);
  }

  function keysBack(ids) {
    const waiting = new Set(queueAll().map((it) => it.id));
    const raws = [];
    for (const id of ids) {
      const o = ownKeys.get(id);
      if (!o || waiting.has(id)) continue;
      ownKeys.delete(id);
      raws.push(o.raw);
    }
    if (!raws.length || ended) return;
    const v = input.value.replace(/^\s+|\s+$/g, '');
    input.value = (v ? v + '\n' : '') + raws.join('\n');
    autosize();
    recallIdx = -1;
    closeCmdPop();
    if (focusInput()) {
      input.setSelectionRange(input.value.length, input.value.length);
      input.scrollTop = input.scrollHeight;
    }
    toast(raws.length > 1 ? 'Deine Schlüssel sind noch nicht eingerichtet – sie stehen wieder im Feld. Zum Einrichten einfach senden.'
      : 'Dein Schlüssel ist noch nicht eingerichtet – er steht wieder im Feld. Zum Einrichten einfach senden.', 'info', 6500);
  }

  sendBtn.addEventListener('click', (e) => {
    send(input.value, true, e.ctrlKey || e.metaKey);
    focusInput();
  });
  stopBtn.addEventListener('click', () => stop());
  hintNow.addEventListener('click', () => {
    send(input.value, true, true);
    focusInput();
  });

  // =====================================================================
  // Warteschlange (state.queue): Nachrichten, die warten, bis die KI fertig ist
  //  "Jetzt" = POST /api/queue {action:"now", id} (unterbricht die laufende Antwort),
  //  "✕" = {action:"remove", id}, "Alle entfernen" = {action:"clear"}.
  // =====================================================================
  const queuedOwn = [];  // eigene wartende Nachrichten (fuer Pfeil hoch schon gemerkt)
  const ownKeys = new Map(); // Warteschlangen-Nummer -> {raw, shown}: eigener wartender Schluessel (nur lokal)
  const qs = {
    now: new Map(),      // Nummer -> Zeitpunkt: "Jetzt" gedrueckt / Strg+Enter: kommt gleich
    removing: new Set(), // "✕" / "Alle entfernen" gedrueckt: schon ausblenden
    sig: '',
    startAt: 0,          // wann zuletzt eine Nachricht drankam (Ereignis "user")
    timer: 0,
  };
  const qBox = byId('queue');
  const qList = byId('q-list');
  const qClear = byId('q-clear');

  function queueAll() {
    const list = Array.isArray(state.queue) ? state.queue : [];
    return list.filter((it) => it && typeof it === 'object' && it.id != null)
      .map((it) => ({ id: String(it.id), text: String(it.text == null ? '' : it.text) }));
  }

  function renderQueue() {
    const all = queueAll();
    // Merker aufraeumen: was nicht mehr wartet, braucht keinen mehr
    const ids = new Set(all.map((it) => it.id));
    for (const set of [qs.now, qs.removing]) for (const id of [...set.keys()]) if (!ids.has(id)) set.delete(id);
    const items = ended ? [] : all.filter((it) => !qs.removing.has(it.id));
    // "kommt gleich …" (ohne Knoepfe) nur fuer die erste wartende Nachricht – und nur, solange sie
    // wirklich gleich kommt (siehe queueGoing)
    const goingId = items.length && queueGoing(items[0].id) ? items[0].id : null;
    const sig = JSON.stringify([items, goingId]);
    if (sig === qs.sig) return;
    qs.sig = sig;
    // Fokus in der Liste merken (gleicher Knopf derselben Nachricht, sonst der Nachbar)
    const ae = document.activeElement;
    let fId = null;
    let fAct = '';
    let fIdx = -1;
    if (ae && qBox.contains(ae)) {
      const li = ae.closest('[data-qid]');
      fId = li ? li.dataset.qid : null;
      fAct = ae.dataset.qact || (ae === qClear ? 'clear' : '');
      fIdx = li ? [...qList.children].indexOf(li) : -1;
    }
    qList.replaceChildren();
    items.forEach((it, k) => {
      const one = it.text.replace(/\s+/g, ' ').trim() || '…';
      const short = one.length > 60 ? one.slice(0, 59) + '…' : one;
      const going = it.id === goingId;
      const li = h('li', 'q-item' + (going ? ' going' : ''));
      li.dataset.qid = it.id;
      const txt = h('span', 'q-text', one);
      txt.title = it.text.length > 600 ? it.text.slice(0, 599) + '…' : it.text;
      li.append(h('span', 'q-num', String(k + 1)), txt);
      if (going) {
        const g = h('span', 'q-going');
        g.append(h('span', 'spinner'), h('span', null, 'kommt gleich …'));
        li.append(g);
      } else {
        const now = h('button', 'q-btn q-now', 'Jetzt');
        now.type = 'button';
        now.dataset.qact = 'now';
        now.title = 'Jetzt senden – unterbricht die laufende Antwort';
        now.setAttribute('aria-label', 'Jetzt senden (unterbricht die laufende Antwort): ' + short);
        const del = h('button', 'q-btn q-del');
        del.type = 'button';
        del.dataset.qact = 'remove';
        del.append(icon('x'));
        del.title = 'Entfernen – wird nicht gesendet';
        del.setAttribute('aria-label', 'Entfernen: ' + short);
        li.append(now, del);
      }
      qList.append(li);
    });
    byId('q-title').textContent = 'Wartet (' + items.length + ')';
    qClear.hidden = items.length < 2;
    qBox.hidden = !items.length; // der Chat bleibt unten (ResizeObserver am Chat)
    // Fokus wiederherstellen
    if (fId !== null || fAct === 'clear') {
      let target = null;
      const li = fId !== null ? qList.querySelector('[data-qid="' + CSS.escape(fId) + '"]') : null;
      if (li) target = li.querySelector('[data-qact="' + fAct + '"]') || li.querySelector('button');
      if (!target && fAct === 'clear' && !qClear.hidden) target = qClear;
      if (!target && qList.children.length) {
        const n = qList.children[Math.min(Math.max(fIdx, 0), qList.children.length - 1)];
        target = n.querySelector('[data-qact="' + fAct + '"]') || n.querySelector('button');
      }
      if (target) target.focus();
      else if (qBox.contains(ae) || !document.activeElement || document.activeElement === document.body) focusInput();
    }
  }

  async function queueAct(action, id) {
    if (ended) return;
    const ids = action === 'clear' ? queueAll().map((it) => it.id) : [id];
    for (const x of ids) {
      if (action === 'now') qs.now.set(x, Date.now());
      else qs.removing.add(x);
    }
    renderQueue();
    const body = action === 'clear' ? { action } : { action, id: Number.isFinite(Number(id)) ? Number(id) : id };
    const r = await post('/api/queue', body);
    if (!r.ok) {
      for (const x of ids) (action === 'now' ? qs.now : qs.removing).delete(x);
      qs.sig = '';
      renderQueue();
      toast(r.error || 'Das hat nicht geklappt.', 'error');
    } else if (action !== 'now') for (const x of ids) ownKeys.delete(x); // bewusst entfernt
  }

  /** Kommt diese (vorne wartende) Nachricht wirklich gleich? Hat nach dem "Jetzt"/Strg+Enter (oder
   *  kurz davor) eine ANDERE Nachricht angefangen und diese wartet danach immer noch, kommt sie erst
   *  nach jener dran (z.B. zweimal schnell Strg+Enter) – dann wieder "Jetzt"/"✕" anbieten. */
  function queueGoing(id) {
    const t = qs.now.get(id);
    if (t == null) return false;
    if (qs.startAt && qs.startAt > t - 250 && Date.now() - qs.startAt > 1500) {
      qs.now.delete(id);
      return false;
    }
    return true;
  }
  /** Ereignis "user": eine Nachricht ist dran – gleich pruefen, ob die naechste noch "kommt gleich" ist. */
  function queueStarted() {
    qs.startAt = Date.now();
    clearTimeout(qs.timer);
    qs.timer = setTimeout(() => { qs.sig = ''; renderQueue(); }, 1600);
  }

  qList.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-qact]');
    const li = b && b.closest('[data-qid]');
    if (li) queueAct(b.dataset.qact, li.dataset.qid);
  });
  qClear.addEventListener('click', () => queueAct('clear'));

  /** Ereignis "queue_returned": nach "Stopp" kommen die wartenden Nachrichten zurueck ins Feld. */
  function onQueueReturned(text) {
    const t = String(text == null ? '' : text).replace(/^\s+|\s+$/g, '');
    if (!t || ended) return;
    const v = input.value.replace(/^\s+|\s+$/g, '');
    // zuerst die zurueckgekommenen (frueher geschrieben), dann das, was schon im Feld stand
    input.value = v ? t + '\n' + v : t;
    autosize();
    recallIdx = -1;
    closeCmdPop();
    if (focusInput()) {
      input.setSelectionRange(input.value.length, input.value.length);
      input.scrollTop = input.scrollHeight;
    }
    toast('Wartende Nachrichten sind zurück im Feld', 'info', 4200);
  }

  // =====================================================================
  // AFK-Modus ("Ich bin weg"): Nova arbeitet allein weiter und berichtet danach
  //  state.afk = null | {active, auftrag, since, minutes, rounds, max_rounds, max_minutes, eur, max_eur,
  //                      notes, proposals, questions, last, ended};  state.afk_pending = bool
  //  Start: POST /api/afk {action:"start", auftrag, minuten, budget}; zurueck: {action:"stop"}.
  //  Schritte kommen als notice level "afk" (dezente Trennzeile im Chat). Am Ende kommt der
  //  Bericht ZWEIMAL (notice level "afk" und Ereignis afk_report) – gezeigt wird EINE Karte:
  //  die Notice baut sie (so auch beim Neuladen aus dem Verlauf), afk_report "bestaetigt" sie nur.
  // =====================================================================
  const AFK_DUR = [[30, '30 Min'], [60, '1 Std'], [120, '2 Std'], [240, '4 Std']];
  const AFK_BUD = [[0.2, '0,20 €'], [0.5, '0,50 €'], [1, '1 €'], [2, '2 €']];
  const AFK_TALK = 'Lass uns die Vorschläge durchgehen.';
  const RE_AFK_REPORT = /^\s*\*\*W(?:ä|ae)hrend du weg warst\*\*/i;
  const afk = {
    dur: 120, bud: 1,     // Auswahl im Dialog (Standard: 2 Std, 1 €)
    back: null,           // Fokus vor dem Dialog
    sending: false, at: 0,
    endingSince: null,    // "Ich bin zurueck" / Nachricht geschrieben: Sitzung (since), die gerade endet
    lastSince: null,      // zuletzt gezeigte Sitzung
    goneSince: null,      // Sitzung, die schon vorbei ist (state.afk war danach null)
    stopping: false,      // Anfrage "stop" laeuft
    base: null,           // {since, minutes, at}: Minuten lokal weiterzaehlen
    timer: 0,
  };
  const afkBand = byId('afk-band');
  const adialog = byId('adialog');
  const afkTask = byId('afk-task');
  const afkErr = byId('afk-err');

  /** Laeuft eine AFK-Sitzung (oder endet sie gerade)? Ein verspaeteter Stand einer schon beendeten
   *  Sitzung zaehlt nicht (Zustands-Ereignisse koennen sich ueberholen). */
  function afkRunning() {
    const a = state.afk;
    if (!a || typeof a !== 'object') return false; // (auch vor dem ersten Stand: "afk" noch nicht angelegt)
    return !(afk.goneSince !== null && a.since === afk.goneSince);
  }
  /** Pause zwischen zwei AFK-Schritten (keine Antwort laeuft): die Sphaere atmet ruhig. */
  function afkResting() { return afkRunning() && !reply; }

  // ---------- Dialog ----------
  function afkSegs(host, list, onPick) {
    for (const [v, label] of list) {
      const b = h('button', 'segctl-btn', label);
      b.type = 'button';
      b.setAttribute('role', 'radio');
      b.dataset.value = String(v);
      b.addEventListener('click', () => onPick(v));
      host.append(b);
    }
    host.addEventListener('keydown', (e) => {
      if (e.key === 'Home' || e.key === 'End') {
        const all = [...host.children];
        const b = all[e.key === 'Home' ? 0 : all.length - 1];
        e.preventDefault();
        b.focus();
        onPick(Number(b.dataset.value));
        return;
      }
      arrowRadio(e, host, (b) => onPick(Number(b.dataset.value)));
    });
  }
  function afkMark(host, cur) {
    for (const b of host.children) {
      const on = Number(b.dataset.value) === cur;
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    }
  }
  const afkDur = byId('afk-dur');
  const afkBud = byId('afk-bud');
  afkSegs(afkDur, AFK_DUR, (v) => { afk.dur = v; afkMark(afkDur, v); });
  afkSegs(afkBud, AFK_BUD, (v) => { afk.bud = v; afkMark(afkBud, v); });

  function openAfk() {
    if (ended || !amodal.hidden) return;
    closeSidebar();
    closeCmdPop();
    afk.back = document.activeElement;
    afk.dur = 120;
    afk.bud = 1;
    afkMark(afkDur, afk.dur);
    afkMark(afkBud, afk.bud);
    afkErr.hidden = true;
    afkSending(false);
    byId('afk-sub').textContent = 'Du bist weg – ich arbeite allein weiter und berichte dir, wenn du zurück bist.';
    amodal.hidden = false;
    afk.at = performance.now();
    updateInert();
    afkTask.focus();
    afkTask.setSelectionRange(afkTask.value.length, afkTask.value.length);
  }

  function closeAfk() {
    if (amodal.hidden) return;
    amodal.hidden = true;
    afk.sending = false;
    updateInert();
    const back = afk.back;
    afk.back = null;
    // Rueckfrage kam, waehrend der Dialog offen war: danach nicht auf den (versteckten) Dialog zurueck
    if (askFocusBack && amodal.contains(askFocusBack)) askFocusBack = back;
    if (!modal.hidden) { dialog.focus(); return; }
    if (!cmodal.hidden) return;
    if (jv.open) { jvEl.focus(); return; } // Jarvis kam waehrend des Dialogs (z.B. aus einem anderen Fenster)
    if (back && back !== document.body && document.contains(back) && !back.closest('[inert]') &&
        back.offsetParent !== null) back.focus();
    else focusInput();
  }

  function afkSending(on) {
    afk.sending = !!on;
    const go = byId('afk-go');
    go.disabled = afk.sending;
    byId('afk-cancel').disabled = false;
    go.replaceChildren(afk.sending ? h('span', 'spinner') : icon('moon'),
      h('span', null, afk.sending ? 'Starte …' : "Los geht's"));
  }

  async function submitAfk() {
    if (afk.sending || amodal.hidden) return;
    afkErr.hidden = true;
    afkSending(true);
    const r = await post('/api/afk', { action: 'start', auftrag: afkTask.value.trim(), minuten: afk.dur, budget: afk.bud });
    if (amodal.hidden) { // inzwischen geschlossen (z.B. KI beendet)
      afk.sending = false;
      if (r.ok) afkTask.value = '';
      return;
    }
    afkSending(false);
    if (!r.ok && (afkRunning() || state.afk_pending === true)) { // inzwischen anderswo gestartet
      renderAfk(); // schliesst den Dialog (mit Hinweis)
      return;
    }
    if (!r.ok) {
      let err = String(r.error || '').trim() || 'Der AFK-Modus konnte nicht starten.';
      if (/^Der AFK-Modus laeuft schon\.?$/.test(err)) err = 'Der AFK-Modus läuft schon.';
      afkErr.replaceChildren(icon('alertCircle'), h('span', null, err));
      afkErr.hidden = false;
      afkTask.focus();
      return;
    }
    afkTask.value = '';
    afk.back = null; // der Knopf verschwindet gleich – Fokus ins Eingabefeld
    closeAfk();
    // Bestaetigung ist das Band oben ("AFK-Modus – … arbeitet allein" bzw. "startet gleich …") – kein Toast davor
    renderAfk();
  }

  function afkKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeAfk(); return; }
    if (e.key === 'F2') { e.preventDefault(); return; }
    if (e.key === 'Tab') { trapTab(e, adialog); return; }
    // Enter im Textfeld = "Los geht's" (Shift+Enter = neue Zeile), Strg+Enter ueberall
    const inTask = e.target === afkTask;
    if (e.key === 'Enter' && !e.isComposing && ((inTask && !e.shiftKey && !e.altKey) || e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (!e.repeat) submitAfk();
    }
  }
  /** Maus-Klick zu kurz nach dem Oeffnen oder Teil eines Doppelklicks? (Tastatur zaehlt immer) */
  const afkTooSoon = (e) => !!(e && e.detail) && (e.detail > 1 || performance.now() - afk.at < 400);
  byId('afk-go').addEventListener('click', (e) => { if (!afkTooSoon(e)) submitAfk(); });
  byId('afk-cancel').addEventListener('click', () => closeAfk());
  amodal.addEventListener('mousedown', (e) => {
    if (e.target !== amodal) return;
    e.preventDefault(); // Fokus bleibt im Dialog (auch beim ignorierten zweiten Klick eines Doppelklicks)
    if (!afkTooSoon(e)) closeAfk();
  });
  byId('afk-btn').addEventListener('click', () => openAfk());
  byId('sb-afk').addEventListener('click', () => {
    if (afkRunning() || state.afk_pending === true) { closeSidebar(); afkStop(); }
    else openAfk();
  });

  // ---------- Band "AFK-Modus – Nova arbeitet allein" ----------
  /** Minuten seit dem Start: lokal hochzaehlen (die KI laeuft auf demselben PC – sonst ab dem letzten Stand). */
  function afkMinutes() {
    const b = afk.base;
    if (!b) return 0;
    const est = b.minutes + Math.floor((Date.now() - b.at) / 60000);
    const local = Date.now() / 1000 - b.since;
    if (!Number.isFinite(local) || !b.since) return est;
    const m = Math.floor(local / 60);
    return Math.abs(m - est) <= 1 ? Math.max(m, b.minutes) : est;
  }
  function afkSince(m) {
    if (m < 1) return 'seit gerade eben';
    if (m < 60) return 'seit ' + m + ' Min';
    const hh = Math.floor(m / 60);
    const mm = m % 60;
    return 'seit ' + hh + ' Std' + (mm ? ' ' + mm + ' Min' : '');
  }
  const afkLimit = (m) => (m % 60 === 0 && m >= 60 ? m / 60 + ' Std' : m + ' Min');
  /** 1 -> "1 €", 0.2 -> "0,20 €"; exact=true: immer zwei Stellen ("0,01 €"). */
  function afkEur(v, exact) {
    v = Math.max(0, Number(v) || 0);
    const whole = Math.abs(v - Math.round(v)) < 1e-9;
    return (whole && !exact ? String(Math.round(v))
      : v.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })) + ' €';
  }
  const afkCount = (n, one, many) => (n === 1 ? '1 ' + one : n + ' ' + many);

  function renderAfkTime() {
    byId('ab-time').textContent = afkBand.dataset.mode === 'active' ? afkSince(afkMinutes()) : '';
  }

  function renderAfk() {
    const a = afkRunning() ? state.afk : null;
    const pending = !a && state.afk_pending === true;
    const show = !ended && (!!a || pending);
    if (a) afk.lastSince = a.since;
    else {
      if (afk.lastSince !== null && !(state.afk && typeof state.afk === 'object')) afk.goneSince = afk.lastSince;
      afk.lastSince = null;
      afk.endingSince = null;
      afk.base = null;
    }
    // AFK kam anderswo in Gang (anderes Fenster, Nova selbst): den offenen Dialog hier schliessen –
    // "Los geht's" ginge nicht mehr bzw. wuerde die Wahl des anderen Starts ueberschreiben.
    // (Der eigene Start schliesst ihn selbst: waehrenddessen ist afk.sending gesetzt.)
    if (show && !amodal.hidden && !afk.sending) {
      closeAfk();
      toast(pending ? 'Der AFK-Modus startet schon gleich.' : 'Der AFK-Modus läuft schon.', 'info');
    }
    const n = kiName();
    const job = a ? String(a.auftrag || '').trim() : '';
    // Knoepfe "Ich bin weg" (neben dem Feld und in der Seitenleiste)
    byId('afk-btn').hidden = show || ended;
    const sb = byId('sb-afk');
    const sbMode = !show ? 'off' : pending ? 'pending' : 'on';
    sb.classList.toggle('on', sbMode === 'on');
    sb.setAttribute('aria-haspopup', sbMode === 'off' ? 'dialog' : 'false');
    byId('sb-afk-title').textContent = sbMode === 'off' ? 'Ich bin weg' : sbMode === 'pending' ? 'Startet gleich …' : 'Ich bin zurück';
    byId('sb-afk-sub').textContent = sbMode === 'off' ? n + ' arbeitet allein weiter'
      : sbMode === 'pending' ? 'AFK-Modus – klicken zum Abbrechen' : 'AFK-Modus läuft – beenden';
    sb.title = sbMode === 'off' ? 'AFK-Modus: ' + n + ' arbeitet allein weiter, während du weg bist, und berichtet dir danach'
      : sbMode === 'on' ? 'AFK-Modus beenden – ' + n + ' hört auf und berichtet dir' : '';
    app.classList.toggle('afk-on', !!a && !ended);

    afkBand.hidden = !show;
    updateSendBtn(); // Senden-Knopf und Hinweis: waehrend AFK heisst Enter "ich bin zurueck"
    if (!show) {
      clearInterval(afk.timer);
      afk.timer = 0;
      moodSync();
      return;
    }
    // endet gerade: einmal gesehen, bleibt es so (ein verspaeteter aelterer Stand holt das Band nicht zurueck)
    if (a && a.active === false) afk.endingSince = a.since;
    const ending = !!a && afk.endingSince !== null && afk.endingSince === a.since;
    const mode = pending ? 'pending' : ending ? 'ending' : 'active';
    afkBand.dataset.mode = mode;
    const btn = byId('ab-btn');
    const note = byId('ab-note');
    const counts = byId('ab-counts');
    let title;
    let noteText = '';
    let countText = '';
    if (mode === 'pending') {
      title = 'AFK-Modus startet gleich …';
      noteText = 'sobald ich mit der laufenden Antwort fertig bin';
      btn.textContent = 'Abbrechen';
      btn.title = 'Doch nicht weg – der AFK-Modus startet nicht';
    } else if (mode === 'ending') {
      title = 'Willkommen zurück!';
      noteText = 'Ich höre auf und fasse zusammen, was ich gemacht habe …';
      btn.textContent = 'Ich bin zurück';
      btn.title = '';
    } else {
      title = 'AFK-Modus – ' + n + ' arbeitet allein';
      const last = String(a.last || '').trim();
      noteText = last ? 'Zuletzt: ' + last : job ? 'Auftrag: ' + job
        : 'Ohne festen Auftrag – ich mache da weiter, wo wir aufgehört haben.';
      const p = Number(a.proposals) || 0;
      const q = Number(a.questions) || 0;
      countText = [p ? afkCount(p, 'Vorschlag', 'Vorschläge') : '', q ? afkCount(q, 'Frage', 'Fragen') : '']
        .filter(Boolean).join(' · ');
      btn.textContent = 'Ich bin zurück';
      btn.title = 'AFK-Modus beenden – ' + n + ' hört auf und berichtet dir, was in der Zeit passiert ist';
    }
    btn.hidden = mode === 'ending';
    btn.disabled = afk.stopping;
    const t = byId('ab-title');
    if (t.textContent !== title) t.textContent = title;
    note.textContent = noteText;
    note.title = noteText.length > 60 ? noteText : '';
    counts.textContent = countText;
    counts.title = countText ? 'Wartet auf dich, wenn du zurück bist' : '';
    byId('ab-last').hidden = !noteText && !countText;
    if (a && mode === 'active') {
      const since = Number(a.since);
      afk.base = { since: Number.isFinite(since) ? since : 0, minutes: Math.max(0, Number(a.minutes) || 0), at: Date.now() };
      const max = Math.max(1, Number(a.max_rounds) || 1);
      byId('ab-step').textContent = 'Schritt ' + Math.min(max, Math.max(1, Number(a.rounds) || 0)) + '/' + max;
      byId('ab-cost').textContent = 'ca. ' + afkEur(a.eur, true) + ' von ' + afkEur(a.max_eur);
      const lim = [];
      if (job) lim.push('Auftrag: ' + job);
      lim.push('Höchstens ' + afkLimit(Math.max(1, Number(a.max_minutes) || 0)) + ' · ' + afkEur(a.max_eur) + ' · ' + max + ' Schritte');
      afkBand.title = lim.join('\n');
      if (!afk.timer) afk.timer = setInterval(renderAfkTime, 10000);
    } else {
      byId('ab-step').textContent = '';
      byId('ab-cost').textContent = '';
      afkBand.title = '';
      clearInterval(afk.timer);
      afk.timer = 0;
    }
    renderAfkTime();
    moodSync();
  }
  /** Du bist zurueck (Nachricht geschrieben): Band zeigt "Willkommen zurueck", bis state.afk weg ist. */
  function afkBack() {
    if (!afkRunning()) return;
    afk.endingSince = state.afk.since;
    renderAfk();
  }

  /** "Neues Gespraech" waehrend AFK: das wuerde den Bericht gleich wieder loeschen, bevor man ihn
   *  sieht. Stattdessen AFK beenden (der Bericht kommt) – danach geht ein neues Gespraech. */
  function afkBlocksNew() {
    if (!afkRunning() || ended) return false;
    const ending = afk.endingSince !== null && afk.endingSince === state.afk.since;
    if (!ending) afkStop();
    toast(ending ? 'Einen Moment – gleich kommt dein Bericht. Danach kannst du ein neues Gespräch beginnen.'
      : 'AFK-Modus beendet – hier ist erst dein Bericht. Danach kannst du ein neues Gespräch beginnen.', 'info', 6000);
    return true;
  }

  /** "Ich bin zurueck" (laeuft) bzw. "Abbrechen" (startet gleich): POST /api/afk {action:"stop"}. */
  async function afkStop() {
    if (afk.stopping || ended) return;
    const running = afkRunning();
    const before = running ? state.afk.since : null;
    afk.stopping = true;
    if (running) afk.endingSince = before;
    const hadFocus = afkBand.contains(document.activeElement);
    renderAfk();
    const r = await post('/api/afk', { action: 'stop' });
    afk.stopping = false;
    if (!r.ok) {
      if (afk.endingSince === before) afk.endingSince = null;
      renderAfk();
      toast(r.error || 'Das hat nicht geklappt.', 'error');
      return;
    }
    if (!running) toast('AFK-Modus abgebrochen – ich bleibe hier.', 'info');
    renderAfk();
    if (hadFocus && (afkBand.hidden || byId('ab-btn').hidden)) focusInput();
  }
  byId('ab-btn').addEventListener('click', () => afkStop());

  // ---------- Im Chat: Schritte als Trennzeile, Bericht als Karte ----------
  function addAfkNotice(text) {
    const t = String(text == null ? '' : text).trim();
    if (!t) return null;
    if (RE_AFK_REPORT.test(t)) return addAfkReport(t, false);
    const row = h('div', 'afk-note' + (t.length > 70 ? ' long' : ''));
    row.setAttribute('role', 'note');
    row.dataset.text = t;
    const chip = h('span', 'an-chip');
    chip.append(icon('moon'), h('span', 'an-text', t.replace(/\*\*/g, '')));
    row.append(h('span', 'an-line'), chip, h('span', 'an-line'));
    msgs.append(row);
    added();
    return row;
  }

  /** Bericht zerlegen: "**Während du weg warst** (3 Min., 2 Schritte, ca. 0,01 EUR). Grund" + Abschnitte. */
  function parseAfkReport(text) {
    const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
    const first = lines.shift() || '';
    const m = first.match(/^\s*\*\*[^*]+\*\*\s*(?:\(([^)]*)\))?\.?\s*(.*)$/);
    const meta = m && m[1] ? m[1].split(/,\s+/).map((x) => x.replace(/\bEUR\b/g, '€').replace(/^1 Schritte$/, '1 Schritt').trim()).filter(Boolean) : [];
    const reason = m ? m[2].trim() : first.replace(/\*\*/g, '').trim();
    const secs = [];
    let cur = { title: '', lines: [] };
    const push = () => { if (cur.title || cur.lines.join('').trim()) secs.push(cur); };
    for (const l of lines) {
      const s = l.match(/^\s*\*\*([^*\n]+?):?\*\*:?\s*(.*)$/); // "**Ergebnis:** …" / "**Fragen an dich:**"
      if (s) {
        push();
        cur = { title: s[1].trim(), lines: s[2] ? [s[2]] : [] };
      } else cur.lines.push(l);
    }
    push();
    return { meta, reason, secs, ok: !!m };
  }
  const AFK_SEC = [
    [/^ergebnis/i, 'result', 'checkCircle'],
    [/erledigt|notiz/i, 'notes', 'pen'],
    [/vorschl/i, 'proposals', 'brain'],
    [/frage/i, 'questions', 'help'],
  ];

  function addAfkReport(text, claimed) {
    const t = String(text).trim();
    const rep = parseAfkReport(t);
    const card = h('section', 'afk-report');
    card.setAttribute('aria-label', 'Während du weg warst');
    card.dataset.text = t;
    if (claimed) card.dataset.claimed = '1';
    const head = h('div', 'ar-head');
    const ic = h('span', 'ar-ic');
    ic.setAttribute('aria-hidden', 'true');
    ic.append(icon('moon'));
    const titles = h('div', 'ar-titles');
    titles.append(h('h3', 'ar-title', 'Während du weg warst'));
    if (rep.meta.length) {
      const meta = h('div', 'ar-meta');
      for (const x of rep.meta) meta.append(h('span', null, x));
      titles.append(meta);
    }
    head.append(ic, titles);
    card.append(head);
    if (!rep.ok) { // unbekanntes Format: einfach als Markdown (sicher: escaped)
      const body = h('div', 'md ar-sec-body');
      body.innerHTML = renderMarkdown(t);
      card.append(body);
    } else if (rep.reason) card.append(h('p', 'ar-reason', rep.reason));
    let talk = false;
    if (rep.ok) {
      for (const s of rep.secs) {
        const kind = AFK_SEC.find(([re]) => re.test(s.title)) || [null, s.title ? 'other' : 'plain', 'info'];
        if (kind[1] === 'proposals' || kind[1] === 'questions') talk = true;
        const sec = h('div', 'ar-sec ' + kind[1]);
        if (s.title) {
          const st = h('h4', 'ar-sec-title');
          st.append(icon(kind[2]), h('span', null, s.title));
          sec.append(st);
        }
        const body = h('div', 'md ar-sec-body');
        body.innerHTML = renderMarkdown(s.lines.join('\n').trim()); // sicher: escaped
        sec.append(body);
        card.append(sec);
      }
    }
    if (talk) {
      const foot = h('div', 'ar-foot');
      const b = h('button', 'btn small ar-talk');
      b.type = 'button';
      b.append(icon('chat'), h('span', null, 'Vorschläge besprechen'));
      b.title = '„' + AFK_TALK + '“ ins Eingabefeld setzen';
      b.addEventListener('click', () => {
        const v = input.value.replace(/\s+$/, '');
        if (!v.includes(AFK_TALK)) input.value = v ? v + '\n' + AFK_TALK : AFK_TALK;
        autosize();
        recallIdx = -1;
        closeCmdPop();
        if (focusInput()) input.setSelectionRange(input.value.length, input.value.length);
      });
      foot.append(b, h('span', 'ar-hint', 'Nichts davon passiert ohne dein Okay.'));
      card.append(foot);
    }
    msgs.append(card);
    added();
    return card;
  }

  /** Ereignis afk_report: die Karte kam schon mit der Notice – dann nur bestaetigen (nie doppelt). */
  function onAfkReport(ev) {
    const t = String(ev.text == null ? '' : ev.text).trim();
    if (!t || ended) return;
    const reason = String(ev.reason || '');
    const cards = msgs.querySelectorAll('.afk-report');
    const last = cards[cards.length - 1];
    if (last && !last.dataset.claimed && last.dataset.text === t) {
      last.dataset.claimed = '1';
      last.dataset.reason = reason;
      return;
    }
    // Bericht-Notice kam in anderem Format (als Trennzeile): durch die Karte ersetzen
    const notes = msgs.querySelectorAll('.afk-note');
    const ln = notes[notes.length - 1];
    const card = addAfkReport(t, true);
    card.dataset.reason = reason;
    if (ln && ln.dataset.text === t) { ln.replaceWith(card); added(); }
  }

  for (const b of document.querySelectorAll('[data-prompt]')) {
    b.addEventListener('click', () => send(b.dataset.prompt));
  }

  // =====================================================================
  // Eingabefeld
  // =====================================================================
  function autosize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 220) + 'px';
    updateSendBtn();
  }

  /** Eingabefeld fokussieren – aber nie einem offenen Dialog den Fokus wegnehmen. */
  function focusInput() {
    if (!modal.hidden) { askFocusBack = input; return false; }
    if (!pmodal.hidden || ended || jv.open || !cmodal.hidden || !smodal.hidden || !amodal.hidden) return false;
    input.focus();
    return true;
  }

  function appendToInput(text) {
    const t = String(text || '').trim();
    if (!t) return;
    const v = input.value;
    input.value = v + (v && !/\s$/.test(v) ? ' ' : '') + t;
    autosize();
    if (focusInput()) {
      input.setSelectionRange(input.value.length, input.value.length);
      updateCmdPop();
    }
  }

  // Befehlsvorschlaege bei "/"
  let commands = [];
  let cmdList = [];
  let cmdSel = 0;
  const cmdPop = byId('cmd-pop');

  function closeCmdPop() {
    cmdPop.hidden = true;
    cmdList = [];
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  }

  function updateCmdPop() {
    const v = input.value;
    if (!v.startsWith('/') || v.includes('\n') || !commands.length) { closeCmdPop(); return; }
    const q = v.toLowerCase();
    const list = commands.filter((c) => c.cmd.toLowerCase().startsWith(q));
    if (!list.length) { closeCmdPop(); return; }
    const prev = cmdList[cmdSel] && cmdList[cmdSel].cmd;
    cmdList = list;
    const keepIdx = list.findIndex((c) => c.cmd === prev);
    cmdSel = keepIdx >= 0 ? keepIdx : 0;
    renderCmdPop();
  }

  function renderCmdPop() {
    cmdPop.replaceChildren(h('div', 'cmd-head', 'Befehle'));
    cmdList.forEach((c, k) => {
      const it = h('div', 'cmd-item');
      it.id = 'cmd-' + k;
      it.setAttribute('role', 'option');
      it.setAttribute('aria-selected', k === cmdSel ? 'true' : 'false');
      it.append(h('span', 'cmd-name', c.cmd), h('span', 'cmd-help', c.help || ''));
      it.addEventListener('mousedown', (e) => { e.preventDefault(); cmdSel = k; completeCmd(); });
      it.addEventListener('mousemove', () => {
        if (cmdSel !== k) { cmdSel = k; markCmdSel(); }
      });
      cmdPop.append(it);
    });
    cmdPop.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    markCmdSel();
  }

  function markCmdSel() {
    cmdPop.querySelectorAll('.cmd-item').forEach((it, k) => {
      it.setAttribute('aria-selected', k === cmdSel ? 'true' : 'false');
      if (k === cmdSel) it.scrollIntoView({ block: 'nearest' });
    });
    input.setAttribute('aria-activedescendant', 'cmd-' + cmdSel);
  }

  /** Gewaehlten Befehl ins Feld uebernehmen (ohne Platzhalter wie <nr>). */
  function completeCmd() {
    const c = cmdList[cmdSel];
    if (!c) return;
    let v = c.cmd;
    const ph = v.search(/[<[]/);
    if (ph > 0) v = v.slice(0, ph);
    input.value = v;
    autosize();
    input.focus();
    input.setSelectionRange(v.length, v.length);
    updateCmdPop();
  }

  input.addEventListener('input', () => {
    autosize();
    updateCmdPop();
    if (recallIdx >= 0 && input.value !== ownMsgs[recallIdx]) recallIdx = -1;
  });
  input.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== input) closeCmdPop(); }, 120));

  input.addEventListener('keydown', (e) => {
    if (e.isComposing) return;
    if (!cmdPop.hidden && cmdList.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        cmdSel = (cmdSel + (e.key === 'ArrowDown' ? 1 : cmdList.length - 1)) % cmdList.length;
        markCmdSel();
        return;
      }
      if (e.key === 'Tab') { e.preventDefault(); completeCmd(); return; }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeCmdPop(); return; }
      if (e.key === 'Enter' && !e.shiftKey) {
        const c = cmdList[cmdSel];
        if (c && input.value.trim() !== c.cmd) { e.preventDefault(); completeCmd(); return; }
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      // Strg+Enter: laufende Antwort unterbrechen und gleich das hier beantworten
      send(input.value, true, e.ctrlKey || e.metaKey);
      return;
    }
    // Pfeil hoch/runter: eigene letzte Nachrichten
    if (e.key === 'ArrowUp' && !e.shiftKey && ownMsgs.length) {
      const recalling = recallIdx >= 0 && input.value === ownMsgs[recallIdx];
      if (!input.value || (recalling && (input.selectionStart === 0 || !input.value.includes('\n')))) {
        e.preventDefault();
        recallIdx = recalling ? Math.max(0, recallIdx - 1) : ownMsgs.length - 1;
        input.value = ownMsgs[recallIdx];
        autosize();
        input.setSelectionRange(input.value.length, input.value.length);
        updateCmdPop();
        closeCmdPop();
      }
      return;
    }
    if (e.key === 'ArrowDown' && !e.shiftKey && recallIdx >= 0 && input.value === ownMsgs[recallIdx] &&
        (input.selectionStart === input.value.length || !input.value.includes('\n'))) {
      e.preventDefault();
      recallIdx++;
      input.value = recallIdx < ownMsgs.length ? ownMsgs[recallIdx] : '';
      if (recallIdx >= ownMsgs.length) recallIdx = -1;
      autosize();
      closeCmdPop();
    }
  });

  // =====================================================================
  // Spracheingabe: Knopf oder F2 – halten = sprechen, kurz = an/aus
  // =====================================================================
  const voice = {
    phase: 'idle',   // idle | starting | recording | stopping | remote | remote-rec
    mode: null,      // null (noch gedrueckt) | 'hold' | 'toggle'
    pressed: false,
    pressAt: 0,
    session: 0,
    startP: null,
    t0: 0,
    timer: 0,
    quietUntil: 0,   // Server-Ereignisse mit Text kurz ignorieren (kein doppelter Text)
  };
  const HOLD_MS = 400;

  function fmtTime(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  function renderVoice() {
    const recording = voice.phase === 'starting' || voice.phase === 'recording' || voice.phase === 'remote';
    const recognizing = voice.phase === 'stopping' || voice.phase === 'remote-rec';
    micBtn.classList.toggle('rec', recording);
    micBtn.classList.toggle('busy', recognizing);
    micBtn.setAttribute('aria-pressed', recording ? 'true' : 'false');
    composer.classList.toggle('rec', recording);
    const bar = byId('voice-bar');
    byId('hint').hidden = recording || recognizing;
    bar.hidden = !(recording || recognizing);
    bar.classList.toggle('recognizing', recognizing);
    if (recording) {
      byId('voice-label').textContent = 'Aufnahme';
      byId('voice-time').textContent = fmtTime(Date.now() - voice.t0);
      const done = autosendOn() ? 'senden' : 'fertig';
      byId('voice-help').textContent = voice.mode === 'toggle' || voice.phase === 'remote'
        ? 'Nochmal drücken (oder F2) = ' + done + ' · Esc bricht ab'
        : 'Loslassen = ' + done + ' · Esc bricht ab';
      bar.querySelector('.rec-dot').hidden = false;
      bar.querySelector('.rec-spin').hidden = true;
    } else if (recognizing) {
      byId('voice-label').textContent = 'Ich erkenne, was du gesagt hast …';
      byId('voice-time').textContent = '';
      byId('voice-help').textContent = '';
      bar.querySelector('.rec-dot').hidden = true;
      bar.querySelector('.rec-spin').hidden = false;
    }
    if ((recording || recognizing) && !voice.timer) {
      voice.timer = setInterval(() => {
        if (voice.phase === 'idle') return;
        if (voice.phase !== 'stopping' && voice.phase !== 'remote-rec') byId('voice-time').textContent = fmtTime(Date.now() - voice.t0);
      }, 250);
    } else if (!recording && !recognizing && voice.timer) {
      clearInterval(voice.timer);
      voice.timer = 0;
    }
    updateStatus();
    moodSync();
  }

  function voiceReset() {
    voice.phase = 'idle';
    voice.mode = null;
    voice.pressed = false;
    voice.startP = null;
    voice.session++;
    renderVoice();
  }

  let voiceSetupCard = null;
  function voiceFailed(r) {
    if (r.setup) {
      // nur eine Einrichten-Karte: die alte verschwindet, die neue steht unten
      if (voiceSetupCard) voiceSetupCard.remove();
      voiceSetupCard = addCard('warn', 'Die Spracheingabe ist noch nicht eingerichtet.' + (r.error ? '\n\n' + r.error : ''), {
        button: { label: 'Spracheingabe einrichten', onClick: () => send('/sprache einrichten') },
      });
      updateEmpty();
    } else {
      toast(r.error || 'Das Mikrofon konnte nicht gestartet werden.', 'error', 5000);
    }
  }

  async function voiceStart() {
    voice.phase = 'starting';
    voice.t0 = Date.now();
    const my = ++voice.session;
    renderVoice();
    const p = post('/api/voice', { action: 'start' });
    voice.startP = p;
    const r = await p;
    if (my !== voice.session || voice.phase !== 'starting') return; // inzwischen gestoppt/abgebrochen
    if (!r.ok) { voiceReset(); voiceFailed(r); return; }
    voice.phase = 'recording';
    renderVoice();
  }

  async function voiceStop() {
    const my = voice.session;
    const startP = voice.startP;
    voice.phase = 'stopping';
    renderVoice();
    if (startP) {
      const r0 = await startP;
      if (my !== voice.session) return;
      if (!r0.ok) { voiceReset(); voiceFailed(r0); return; }
    }
    const r = await post('/api/voice', { action: 'stop' });
    if (my !== voice.session) return;
    voice.quietUntil = Date.now() + 3000;
    voiceReset();
    if (!r.ok) { toast(r.error || 'Die Spracherkennung hat nicht geklappt.', 'error', 5000); return; }
    const text = String(r.text || '').trim();
    if (!text) { toast('Ich habe nichts verstanden – versuch es noch einmal.'); focusInput(); return; }
    voiceText(text);
  }

  /** Schalter "Gesprochenes sofort senden" (waehrend des Umschaltens schon der neue Wert). */
  function autosendOn() {
    return own(pendingVal, 'voice_autosend') ? !!pendingVal.voice_autosend : state.voice_autosend === true;
  }

  /** Erkannter Text (Mikrofon-Knopf/F2): gleich senden (Schalter an) oder ins Eingabefeld setzen. */
  function voiceText(text) {
    if (!autosendOn() || ended) { appendToInput(text); return; }
    // (arbeitet die KI noch, kommt es in die Warteschlange)
    // schon getippter Text bleibt vorne – alles zusammen geht raus
    const typed = input.value.replace(/\s+$/, '');
    send(typed ? typed + ' ' + text : text, true);
    focusInput();
  }

  async function voiceCancel(quiet) {
    const startP = voice.startP;
    const wasRemote = voice.phase === 'remote';
    voice.quietUntil = Date.now() + 3000;
    voiceReset();
    if (!quiet) toast('Aufnahme abgebrochen');
    if (startP) await startP;
    if (startP || wasRemote) post('/api/voice', { action: 'cancel' });
  }

  function voicePress() {
    if (voice.phase === 'stopping' || voice.phase === 'remote-rec') return;
    if (voice.phase === 'remote') {
      // vom Server gestartete Aufnahme: Druecken beendet sie
      voice.phase = 'recording';
      voice.mode = 'toggle';
      voice.startP = null;
      voice.ignoreUp = true;
      voiceStop();
      return;
    }
    if (voice.phase === 'starting' || voice.phase === 'recording') {
      if (voice.mode === 'toggle') { voice.ignoreUp = true; voiceStop(); }
      return;
    }
    voice.pressed = true;
    voice.pressAt = performance.now();
    voice.mode = null;
    voice.ignoreUp = false;
    voiceStart();
  }

  function voiceRelease() {
    if (voice.ignoreUp) { voice.ignoreUp = false; return; }
    if (!voice.pressed) return;
    voice.pressed = false;
    if (voice.phase !== 'starting' && voice.phase !== 'recording') return;
    if (performance.now() - voice.pressAt >= HOLD_MS) {
      voice.mode = 'hold';
      voiceStop();
    } else {
      voice.mode = 'toggle';
      renderVoice();
    }
  }

  // Ereignisse vom Server (z.B. Aufnahme in einem anderen Fenster)
  function onVoiceEvent(ev) {
    const local = voice.phase === 'starting' || voice.phase === 'recording' || voice.phase === 'stopping';
    if (local) return; // eigene Aufnahme – Ergebnis kommt ueber die Antwort
    if (ev.state === 'recording') {
      if (Date.now() < voice.quietUntil) return;
      voice.phase = 'remote';
      voice.t0 = Date.now();
      renderVoice();
    } else if (ev.state === 'recognizing') {
      if (Date.now() < voice.quietUntil) return;
      voice.phase = 'remote-rec';
      renderVoice();
    } else {
      const quiet = Date.now() < voice.quietUntil;
      if (voice.phase === 'remote' || voice.phase === 'remote-rec') voiceReset();
      if (quiet) return;
      if (ev.error) toast(String(ev.error), 'error', 5000);
      // Aufnahme aus einem anderen Fenster: mit "sofort senden" schickt jenes Fenster den Text ab
      else if (ev.text && !autosendOn()) appendToInput(ev.text);
    }
  }

  // Maus / Finger
  micBtn.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    try { micBtn.setPointerCapture(e.pointerId); } catch (_) { /* egal */ }
    voicePress();
  });
  micBtn.addEventListener('contextmenu', (e) => e.preventDefault());
  micBtn.addEventListener('pointerup', () => voiceRelease());
  micBtn.addEventListener('pointercancel', () => voiceRelease());
  // Tastatur auf dem Knopf (Leertaste/Enter)
  let micKeyAt = 0;
  micBtn.addEventListener('keydown', (e) => {
    if (e.key !== ' ' && e.key !== 'Enter') return;
    e.preventDefault();
    e.stopPropagation();
    if (e.repeat) return;
    micKeyAt = Date.now();
    voicePress();
  });
  micBtn.addEventListener('keyup', (e) => {
    if (e.key !== ' ' && e.key !== 'Enter') return;
    e.preventDefault();
    voiceRelease();
  });
  // Bildschirmleser loesen nur "click" aus
  micBtn.addEventListener('click', (e) => {
    if (e.detail !== 0 || Date.now() - micKeyAt < 1000) return;
    voicePress();
    voiceRelease();
  });
  // Fenster verliert den Fokus, waehrend F2 gehalten wird
  window.addEventListener('blur', () => { if (voice.pressed) voiceRelease(); });

  // =====================================================================
  // Dialoge (Rueckfragen)
  // =====================================================================
  const modal = byId('modal');
  const dialog = byId('dialog');
  let askQueue = [];
  let askCur = null;
  let askAt = 0;
  let askSending = false;
  let askFocusBack = null;

  const RISKS = {
    MODERATE: { cls: 'risk-moderate', label: 'Verändert etwas', ic: 'shieldAlert' },
    DANGEROUS: { cls: 'risk-dangerous', label: 'Weitreichende Aktion', ic: 'alert' },
    AUTOSTART: { cls: 'risk-autostart', label: 'Automatischer Start', ic: 'power' },
  };

  const findOpt = (pred) => (askCur ? (askCur.options || []).find(pred) : null);
  const optAlways = () => findOpt((o) => o.value === 'immer' || /immer/i.test(o.label || ''));
  const optNo = () => findOpt((o) => o.value === 'nein' || /^nein/i.test(o.label || ''));

  function showAsk(ev) {
    if (!ev || ev.id == null) return;
    if ((askCur && askCur.id === ev.id) || askQueue.some((a) => a.id === ev.id)) return;
    askQueue.push(ev);
    if (!askCur) nextAsk();
  }

  /** Alles hinter einem offenen Dialog ist nicht bedienbar (auch nicht per Tab oder Fokus). */
  function updateInert() {
    const askOpen = !modal.hidden;
    const confOpen = !cmodal.hidden;
    const profOpen = !pmodal.hidden;
    const jvOpen = jv.open;
    const setupOpen = !smodal.hidden;
    const afkOpen = !amodal.hidden;
    app.inert = askOpen || confOpen || profOpen || jvOpen || setupOpen || afkOpen;
    pmodal.inert = askOpen || confOpen || jvOpen || setupOpen; // Jarvis liegt ueber dem Profil-Fenster
    smodal.inert = askOpen || confOpen || jvOpen;
    jvEl.inert = askOpen || confOpen || afkOpen;  // Rueckfragen und der AFK-Dialog liegen ueber Jarvis
    tourEl.inert = askOpen || confOpen || profOpen || jvOpen || setupOpen || afkOpen;
    amodal.inert = askOpen || confOpen; // Rueckfragen liegen ueber dem AFK-Dialog
    modal.inert = confOpen;
    // Sphaeren hinter dem obersten grossen Fenster nicht weiter zeichnen
    sphere.scope(setupOpen ? smodal : profOpen ? pmodal : null);
  }

  function nextAsk() {
    askCur = askQueue.shift() || null;
    askSending = false;
    if (!askCur) {
      const wasOpen = !modal.hidden;
      modal.hidden = true;
      updateInert();
      if (wasOpen) {
        if (askFocusBack && document.contains(askFocusBack) && !askFocusBack.closest('[inert]')) askFocusBack.focus();
        else if (jv.open) jvEl.focus();
        else if (!smodal.hidden) sdialog.focus();
        else if (!pmodal.hidden) panel.focus();
        else focusInput();
      }
      askFocusBack = null;
      moodSync();
      return;
    }
    if (!askFocusBack) askFocusBack = document.activeElement;
    if (!Array.isArray(askCur.options) || !askCur.options.length) {
      askCur.options = [{ value: 'ok', label: 'OK' }];
    }
    const risk = (askCur.risk != null && pick(RISKS, String(askCur.risk))) || null;
    dialog.className = 'dialog ' + (risk ? risk.cls : 'risk-none');
    byId('dlg-icon').replaceChildren(icon(risk ? risk.ic : askCur.kind === 'permission' ? 'shield' : 'help'));
    byId('dlg-title').textContent = askCur.kind === 'permission' ? 'Darf ich das tun?' : 'Kurze Rückfrage';
    byId('dlg-risk').textContent = risk ? risk.label : askCur.kind === 'permission' ? 'Erlaubnis nötig' : '';
    byId('dlg-text').textContent = String(askCur.text || ''); // reiner Text, keine Formatierung
    updateDlgVoice();

    const foot = byId('dlg-foot');
    foot.replaceChildren();
    const always = optAlways();
    const no = optNo();
    const keys = [];
    askCur.options.forEach((o, k) => {
      const kind = k === 0 ? 'primary' : o === no ? 'ghost' : 'secondary';
      const b = h('button', 'btn ' + kind);
      b.type = 'button';
      b.append(document.createTextNode(String(o.label || o.value)));
      let key = '';
      if (k === 0) key = 'J';
      else if (o === always) key = 'A';
      else if (o === no) key = 'N';
      if (key) b.append(h('kbd', null, key));
      b.addEventListener('click', () => answer(o.value));
      foot.append(b);
    });
    // Reihenfolge: Nein links, Hauptknopf rechts (gewohnt unter Windows: rechts = Bestaetigen)
    foot.prepend(...[...foot.children].reverse());
    if (askCur.options[0]) keys.push('J = ' + (askCur.options[0].label || askCur.options[0].value));
    if (always && always !== askCur.options[0]) keys.push('A = ' + (always.label || 'immer'));
    if (no) keys.push('N oder Esc = ' + (no.label || 'Nein'));
    byId('dlg-keys').textContent = keys.length ? 'Tasten: ' + keys.join(' · ') : '';

    modal.hidden = false;
    updateInert();
    askAt = performance.now();
    closeCmdPop();
    dialog.focus();
    moodSync();
  }

  function closeAsk(id) {
    if (askCur && askCur.id === id) nextAsk();
    else askQueue = askQueue.filter((a) => a.id !== id);
  }

  /** Alle offenen Fragen sind hinfaellig (z.B. neu verbunden und der Server arbeitet nicht mehr –
   *  das "ask_done" ging waehrend der Trennung verloren). */
  function dropAsks() {
    askQueue = [];
    if (askCur) nextAsk();
  }

  async function answer(value) {
    if (!askCur || askSending) return;
    const id = askCur.id;
    askSending = true;
    for (const b of byId('dlg-foot').querySelectorAll('button')) b.disabled = true;
    const r = await post('/api/answer', { id, value });
    if (!askCur || askCur.id !== id) return; // inzwischen anderswo erledigt
    if (!r.ok) {
      askSending = false;
      for (const b of byId('dlg-foot').querySelectorAll('button')) b.disabled = false;
      toast(r.error || 'Die Frage ist nicht mehr offen.', 'error');
      if (r.error == null) nextAsk(); // Server kennt die Frage nicht mehr
      return;
    }
    nextAsk();
  }

  function modalKey(e) {
    if (e.key === 'Tab') {
      // Fokus im Dialog halten
      const btns = [...byId('dlg-foot').querySelectorAll('button:not(:disabled)')];
      if (!btns.length) { e.preventDefault(); return; }
      const i = btns.indexOf(document.activeElement);
      e.preventDefault();
      const n = e.shiftKey ? (i <= 0 ? btns.length - 1 : i - 1) : (i + 1) % btns.length;
      btns[n].focus();
      return;
    }
    if (e.key === 'F2') { e.preventDefault(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    const hot = k === 'j' || k === 'a' || k === 'n' || k === 'escape';
    if (!hot) return;
    e.preventDefault();
    // kurz nach dem Oeffnen keine Tasten (man tippt evtl. gerade noch)
    if (e.repeat || performance.now() - askAt < 400) return;
    let opt = null;
    if (k === 'j') opt = askCur.options[0];
    else if (k === 'a') opt = optAlways();
    else opt = optNo();
    if (opt) answer(opt.value);
  }

  // =====================================================================
  // Charakter & Profil (eigenes Fenster mit Reitern)
  // Alle Texte vom Server kommen nur per textContent / value hinein.
  // =====================================================================
  const pmodal = byId('pmodal');
  const panel = byId('panel');
  const pfName = byId('pf-name');
  const pfMeaning = byId('pf-meaning');
  const pfPersona = byId('pf-persona');
  const pfValues = byId('pf-values');
  const memNew = byId('mem-new');
  const memCat = byId('mem-cat');
  const memSearch = byId('mem-search');
  const memAddBtn = byId('mem-add-btn');
  const pconfirm = byId('pn-confirm');
  const TABS = ['charakter', 'stil', 'ueber', 'werte', 'gedaechtnis', 'sicherheit', 'gehirn'];
  const NO_PROFILE_TABS = new Set(['gedaechtnis', 'sicherheit', 'gehirn']); // brauchen das geladene Profil nicht
  const LONG_ABOUT = new Set(['interessen', 'projekte', 'wichtig', 'nicht', 'sonstiges']);
  const CHAR_ICONS = {
    freundlich: 'smile', sachlich: 'briefcase', butler: 'bowtie', mentor: 'cap',
    kumpel: 'users', kreativ: 'palette', coach: 'flame', eigen: 'pen',
  };
  const STYLE_INFO = {
    anrede: ['Anrede', 'Wie sie dich anspricht'],
    laenge: ['Antwortlänge', 'Wie ausführlich ihre Antworten sind'],
    humor: ['Humor', 'Wie viel Witz darf sein?'],
    emojis: ['Emojis', 'Bunte Symbole in den Antworten'],
  };
  const MEM_CATS = ['notiz', 'vorliebe', 'person', 'projekt', 'regel', 'technik'];

  const dict = () => Object.create(null);
  const str = (v) => (v == null ? '' : String(v));
  const nl = (v) => str(v).replace(/\r\n?/g, '\n');

  let prof = null;                 // Stand vom Server (Original)
  let pSel = { character: '', style: dict() };
  let profTab = 'charakter';
  let panelState = 'loading';      // loading | error | ready
  let profFocusBack = null;
  let profOpenedAt = 0; // wann das Profil-Fenster aufging (Doppelklick-Schutz)
  let profSaving = false;
  let profError = '';
  let savedNote = false;
  let profLoadGen = 0;
  let aboutEls = dict();
  const mem = { facts: [], count: 0, loaded: false, loading: false, error: false, gen: 0 };
  let memConfirm = null;
  let memFlash = '';
  let memAdding = false;

  function normProfile(p) {
    p = p && typeof p === 'object' ? p : {};
    const arr = (v) => (Array.isArray(v) ? v.filter((x) => x && typeof x === 'object') : []);
    const obj = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {});
    const style = dict();
    for (const k of Object.keys(obj(p.style))) style[k] = str(p.style[k]);
    const styleOptions = dict();
    for (const k of Object.keys(obj(p.style_options))) {
      const opts = arr(p.style_options[k])
        .map((o) => ({ value: str(o.value), label: str(o.label || o.value) }))
        .filter((o) => o.value);
      if (opts.length) styleOptions[k] = opts;
    }
    const about = dict();
    for (const k of Object.keys(obj(p.about))) about[k] = str(p.about[k]);
    return {
      name: str(p.name).trim(),
      meaning: str(p.meaning).trim(),
      character: str(p.character) || 'eigen',
      characters: arr(p.characters)
        .map((c) => ({ id: str(c.id), name: str(c.name || c.id), description: str(c.description) }))
        .filter((c) => c.id && c.id !== 'eigen'),
      persona: nl(p.persona_text),
      style,
      styleOptions,
      about,
      aboutFields: arr(p.about_fields)
        .map((f) => ({ key: str(f.key), label: str(f.label || f.key), placeholder: str(f.placeholder) }))
        .filter((f) => f.key),
      values: nl(p.values_text),
    };
  }

  // ---------- Oeffnen / Schliessen ----------
  function openProfile(tab) {
    closeSidebar();
    closeCmdPop();
    if (ended) return;
    if (!pmodal.hidden) { if (tab) showTab(tab, true); return; }
    profFocusBack = document.activeElement;
    pmodal.hidden = false;
    profOpenedAt = performance.now();
    updateInert();
    profError = '';
    savedNote = false;
    hideConfirm();
    showTab(tab && TABS.includes(tab) ? tab : profTab, false);
    loadProfile();
    loadMemory();
    renderSwitches();
    requestAnimationFrame(() => { byId('tab-' + profTab).focus(); updateTabFade(); });
  }

  function requestClose() {
    if (profSaving) return;
    if (prof && Object.keys(profChanges()).length) { showConfirm(); return; }
    closeProfile();
  }

  function closeProfile() {
    hideConfirm();
    memConfirmReset();
    if (su.where === 'pane') { su.where = ''; clearKey(); }
    pmodal.hidden = true;
    updateInert();
    const back = profFocusBack;
    profFocusBack = null;
    if (!modal.hidden) return;
    if (back && back !== document.body && document.contains(back)) back.focus();
    if (document.activeElement !== back) focusInput();
  }

  function showConfirm() {
    pconfirm.hidden = false;
    for (const el of panel.children) if (el !== pconfirm) el.inert = true;
    byId('pc-save').focus();
  }
  function hideConfirm() {
    if (pconfirm.hidden) return;
    pconfirm.hidden = true;
    for (const el of panel.children) el.inert = false;
  }

  // ---------- Laden ----------
  async function loadProfile() {
    const gen = ++profLoadGen;
    prof = null;
    panelState = 'loading';
    renderPanes();
    updateDirty();
    const data = await getJson('/api/profile');
    if (gen !== profLoadGen || pmodal.hidden) return;
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      panelState = 'error';
      renderPanes();
      return;
    }
    fillProfile(data);
    panelState = 'ready';
    renderPanes();
  }

  function fillProfile(data) {
    prof = normProfile(data);
    pSel = { character: prof.character, style: Object.assign(dict(), prof.style) };
    pfName.value = prof.name;
    pfMeaning.value = prof.meaning;
    pfPersona.value = prof.persona;
    pfValues.value = prof.values;
    renderChars();
    renderStyles();
    renderAbout();
    updateIdentity();
    updatePersona();
    profileNames();
    updateDirty();
  }

  // ---------- Reiter ----------
  function showTab(t, focus) {
    if (!TABS.includes(t)) t = 'charakter';
    profTab = t;
    for (const x of TABS) {
      const b = byId('tab-' + x);
      const on = x === t;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    }
    renderPanes();
    panel.dataset.tab = t; // Reiter "Gehirn" speichert selbst: dort ohne die Profil-Knoepfe
    byId('pn-body').scrollTop = 0;
    const tabBtn = byId('tab-' + t);
    if (focus) tabBtn.focus();
    tabBtn.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    updateTabFade();
    if (t === 'gedaechtnis' && !mem.loaded && !mem.loading) loadMemory();
    if (t === 'gehirn') { mountSetup('pane'); loadSetup(); }
    else if (su.where === 'pane') { su.where = ''; clearKey(); }
  }

  function renderPanes() {
    const ready = panelState === 'ready';
    const free = NO_PROFILE_TABS.has(profTab);
    byId('pn-loading').hidden = free || panelState !== 'loading';
    byId('pn-error').hidden = free || panelState !== 'error';
    for (const t of TABS) byId('pane-' + t).hidden = t !== profTab || (!NO_PROFILE_TABS.has(t) && !ready);
    if (ready && profTab === 'ueber') for (const el of Object.values(aboutEls)) grow(el);
  }

  for (const t of TABS) byId('tab-' + t).addEventListener('click', () => showTab(t, false));

  // Reiter-Leiste: weicher Rand, wo es weitergeht (schmale Fenster)
  const tabsEl = byId('pn-tabs');
  function updateTabFade() {
    const max = tabsEl.scrollWidth - tabsEl.clientWidth;
    tabsEl.classList.toggle('fade-l', max > 2 && tabsEl.scrollLeft > 2);
    tabsEl.classList.toggle('fade-r', max > 2 && max - tabsEl.scrollLeft > 2);
  }
  tabsEl.addEventListener('scroll', updateTabFade, { passive: true });
  if (window.ResizeObserver) new ResizeObserver(updateTabFade).observe(tabsEl);
  byId('pn-tabs').addEventListener('keydown', (e) => {
    const i = TABS.indexOf(profTab);
    let n = -1;
    if (e.key === 'ArrowRight') n = (i + 1) % TABS.length;
    else if (e.key === 'ArrowLeft') n = (i + TABS.length - 1) % TABS.length;
    else if (e.key === 'Home') n = 0;
    else if (e.key === 'End') n = TABS.length - 1;
    if (n < 0) return;
    e.preventDefault();
    showTab(TABS[n], true);
  });

  /** Pfeiltasten in einer Knopfgruppe (role=radio) */
  function arrowRadio(e, group, onPick) {
    const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    if (!own(keys, e.key)) return;
    const items = [...group.querySelectorAll('[role="radio"]')];
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const next = items[(i + keys[e.key] + items.length) % items.length];
    next.focus();
    onPick(next);
  }

  // ---------- Charakter ----------
  function updateIdentity() {
    const n = pfName.value.trim() || (prof && prof.name) || 'KI';
    byId('pf-avatar').querySelector('.av-l').textContent = (n.charAt(0) || 'K').toUpperCase();
    byId('pf-name-preview').textContent = n;
    fillMeaning(byId('pf-meaning-preview'), n, pfMeaning.value);
  }

  function charList() {
    return [...prof.characters,
      { id: 'eigen', name: 'Eigener Charakter', description: 'dein eigener Text – unten frei bearbeitbar' }];
  }

  function renderChars() {
    const grid = byId('char-grid');
    grid.replaceChildren();
    charList().forEach((c, k) => {
      const b = h('button', 'char-card t' + (c.id === 'eigen' ? 'e' : k % 7));
      b.type = 'button';
      b.setAttribute('role', 'radio');
      b.dataset.id = c.id;
      const ic = h('span', 'cc-ic');
      ic.append(icon(pick(CHAR_ICONS, c.id) || 'sparkles'));
      const tx = h('span', 'cc-text');
      const nm = h('span', 'cc-name');
      nm.append(h('span', null, c.name));
      if (c.id === prof.character) nm.append(h('span', 'cc-now', 'aktuell'));
      tx.append(nm);
      if (c.description) tx.append(h('span', 'cc-desc', c.description));
      const mark = h('span', 'cc-check');
      mark.append(icon('check'));
      b.append(ic, tx, mark);
      b.addEventListener('click', () => chooseChar(c.id, true));
      grid.append(b);
    });
    markChars();
  }
  byId('char-grid').addEventListener('keydown', (e) => arrowRadio(e, byId('char-grid'), (b) => chooseChar(b.dataset.id, false)));

  function markChars() {
    for (const b of byId('char-grid').children) {
      const on = b.dataset.id === pSel.character;
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
      b.classList.toggle('selected', on);
    }
  }

  function chooseChar(id, byClick) {
    if (!prof) return;
    pSel.character = id;
    if (id === 'eigen' && byClick) {
      // eigener Text: Editor aufklappen (ohne Aenderung bleibt der gespeicherte Charakter)
      byId('persona-details').open = true;
      setTimeout(() => {
        pfPersona.focus();
        pfPersona.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }, 30);
    }
    markChars();
    updatePersona();
    updateDirty();
  }

  /** Hinweis, wenn ein fertiger Charakter den Text beim Speichern ersetzt. */
  function updatePersona() {
    if (!prof) return;
    const preset = pSel.character !== 'eigen' && pSel.character !== prof.character;
    byId('persona-note').hidden = !preset;
    pfPersona.readOnly = preset;
    pfPersona.classList.toggle('replaced', preset);
    if (preset) {
      const c = prof.characters.find((x) => x.id === pSel.character);
      byId('persona-note-text').textContent = 'Beim Speichern wird die Persönlichkeit durch „' +
        (c ? c.name : pSel.character) + '“ ersetzt' +
        (prof.character === 'eigen' ? ' – dein bisheriger Text wird vorher gesichert.' : '.');
    }
    byId('persona-badge').hidden = pSel.character !== 'eigen';
    byId('persona-keep').textContent = prof.character === 'eigen' || pfPersona.value !== prof.persona
      ? 'Doch meinen Text behalten' : 'Auswahl zurücksetzen';
  }

  byId('persona-keep').addEventListener('click', () => {
    pSel.character = pfPersona.value !== prof.persona ? 'eigen' : prof.character;
    markChars();
    updatePersona();
    updateDirty();
  });

  pfPersona.addEventListener('input', () => {
    if (!prof || pfPersona.readOnly) return;
    // Wird der Text geaendert, ist es ein eigener Charakter
    if (pfPersona.value !== prof.persona) pSel.character = 'eigen';
    else pSel.character = prof.character;
    markChars();
    updatePersona();
    updateDirty();
  });
  for (const el of [pfName, pfMeaning]) {
    el.addEventListener('input', () => { profError = ''; updateIdentity(); updateDirty(); });
  }
  pfValues.addEventListener('input', () => updateDirty());

  // ---------- Stil ----------
  function renderStyles() {
    const list = byId('style-list');
    list.replaceChildren();
    const keys = Object.keys(prof.styleOptions);
    keys.forEach((key, idx) => {
      const opts = prof.styleOptions[key];
      const info = pick(STYLE_INFO, key) || [key.charAt(0).toUpperCase() + key.slice(1), ''];
      const row = h('div', 'style-row');
      const lab = h('div', 'style-text');
      const title = h('div', 'style-title', info[0]);
      title.id = 'st-title-' + idx;
      lab.append(title);
      if (info[1]) lab.append(h('div', 'style-sub', info[1]));
      const seg = h('div', 'segctl');
      seg.setAttribute('role', 'radiogroup');
      seg.setAttribute('aria-labelledby', title.id);
      seg.style.setProperty('--n', String(opts.length));
      for (const o of opts) {
        const b = h('button', 'segctl-btn', o.label);
        b.type = 'button';
        b.setAttribute('role', 'radio');
        b.dataset.value = o.value;
        b.dataset.key = key;
        b.addEventListener('click', () => pickStyle(key, o.value, seg));
        seg.append(b);
      }
      seg.addEventListener('keydown', (e) => arrowRadio(e, seg, (b) => pickStyle(key, b.dataset.value, seg)));
      row.append(lab, seg);
      list.append(row);
      markSeg(seg, key);
    });
    if (!keys.length) list.append(h('p', 'pn-desc', 'Keine Stil-Einstellungen verfügbar.'));
    updateStylePreview();
  }

  function pickStyle(key, value, seg) {
    pSel.style[key] = value;
    markSeg(seg, key);
    updateStylePreview();
    updateDirty();
  }

  function markSeg(seg, key) {
    const cur = pick(pSel.style, key);
    const btns = [...seg.children];
    const hasSel = btns.some((b) => b.dataset.value === cur);
    btns.forEach((b, k) => {
      const on = b.dataset.value === cur;
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      b.tabIndex = on || (!hasSel && k === 0) ? 0 : -1;
      b.classList.toggle('changed', on && cur !== pick(prof.style, key));
    });
  }

  function updateStylePreview() {
    const st = pSel.style;
    const sie = pick(st, 'anrede') === 'Sie';
    const emo = pick(st, 'emojis') === 'an';
    const len = pick(st, 'laenge');
    const humor = pick(st, 'humor');
    let t = sie ? 'Guten Tag! Sehr gern helfe ich Ihnen bei Ihrem Projekt.' : 'Hey! Klar, ich helfe dir gern bei deinem Projekt.';
    if (emo) t = t.replace('!', '! 👋');
    if (len === 'kurz') t += sie ? ' Was genau brauchen Sie?' : ' Was brauchst du?';
    else if (len === 'ausfuehrlich') {
      t += sie
        ? ' Ich gehe Schritt für Schritt vor und erkläre Ihnen jeweils, was ich tue und warum – so behalten Sie jederzeit den Überblick. Womit sollen wir anfangen?'
        : ' Ich gehe Schritt für Schritt vor und erkläre dir jeweils, was ich tue und warum – so behältst du jederzeit den Überblick. Womit wollen wir anfangen?';
    } else t += sie ? ' Erzählen Sie mir kurz, worum es geht, dann lege ich los.' : ' Erzähl mir kurz, worum es geht, dann lege ich los.';
    if (humor === 'viel') t += ' Versprochen: Ich beiße nicht – höchstens in Bugs.';
    else if (humor === 'etwas') t += sie ? ' Kaffee steht schon bereit.' : ' Kaffee steht schon bereit.';
    if (emo) t += ' 🚀';
    byId('style-preview-text').textContent = t;
  }

  // ---------- Ueber mich ----------
  function grow(el) {
    if (el.tagName !== 'TEXTAREA' || !el.offsetParent) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight + 2, 260) + 'px';
  }

  function renderAbout() {
    const grid = byId('about-grid');
    grid.replaceChildren();
    aboutEls = dict();
    const fields = prof.aboutFields;
    fields.forEach((f, k) => {
      const long = LONG_ABOUT.has(f.key);
      // ungerade Zahl kurzer Felder: das letzte bekommt die ganze Breite
      let wide = long;
      if (!long && (k === fields.length - 1 || LONG_ABOUT.has(fields[k + 1].key))) {
        let run = 0;
        for (let j = k; j >= 0 && !LONG_ABOUT.has(fields[j].key); j--) run++;
        wide = run % 2 === 1;
      }
      const lab = h('label', 'field' + (wide ? ' field-wide' : ''));
      const el = long ? h('textarea', 'input area') : h('input', 'input');
      if (long) el.rows = 2;
      else el.type = 'text';
      el.id = 'about-' + k;
      el.maxLength = 2000;
      el.placeholder = f.placeholder;
      el.autocomplete = 'off';
      el.value = pick(prof.about, f.key) || '';
      el.addEventListener('input', () => { grow(el); updateAboutCount(); updateDirty(); });
      lab.append(h('span', 'field-label', f.label), el);
      grid.append(lab);
      aboutEls[f.key] = el;
    });
    if (!fields.length) grid.append(h('p', 'pn-desc', 'Keine Felder verfügbar.'));
    updateAboutCount();
  }

  function updateAboutCount() {
    const all = Object.values(aboutEls);
    const filled = all.filter((el) => el.value.trim()).length;
    byId('about-count').textContent = all.length ? filled + ' von ' + all.length + ' ausgefüllt.' : '';
  }

  function readAbout() {
    let changed = false;
    const out = dict();
    for (const k of Object.keys(prof.about)) out[k] = prof.about[k]; // unbekannte Felder behalten
    for (const f of prof.aboutFields) {
      const el = pick(aboutEls, f.key);
      if (!el) continue;
      const v = el.value.trim();
      if (v !== (pick(prof.about, f.key) || '').trim()) changed = true;
      out[f.key] = v;
    }
    return changed ? out : null;
  }

  // ---------- Aenderungen & Speichern ----------
  function profChanges() {
    const ch = {};
    if (!prof) return ch;
    const name = pfName.value.trim();
    const meaning = pfMeaning.value.trim();
    if (name !== prof.name) ch.name = name;
    if (meaning !== prof.meaning) ch.meaning = meaning; // darf auch allein geschickt werden
    if (pSel.character !== prof.character && pSel.character !== 'eigen') ch.character = pSel.character;
    else if (pfPersona.value !== prof.persona) { ch.character = 'eigen'; ch.persona_text = pfPersona.value; }
    const st = dict();
    for (const k of Object.keys(pSel.style)) if (pSel.style[k] !== pick(prof.style, k)) st[k] = pSel.style[k];
    if (Object.keys(st).length) ch.style = st;
    const about = readAbout();
    if (about) ch.about = about;
    if (pfValues.value !== prof.values) ch.values_text = pfValues.value;
    return ch;
  }

  function nameProblem(ch) {
    if (!('name' in ch)) return '';
    if (!ch.name) return 'Bitte gib ihr einen Namen.';
    if (/["\\\n]/.test(ch.name)) return 'Bitte einen Namen ohne Anführungszeichen (") oder Backslash (\\).';
    if (ch.name.length > 40) return 'Der Name ist zu lang (höchstens 40 Zeichen).';
    return '';
  }

  function updateDirty() {
    const ch = profChanges();
    const n = Object.keys(ch).length;
    const td = {
      charakter: 'name' in ch || 'meaning' in ch || 'character' in ch,
      stil: 'style' in ch,
      ueber: 'about' in ch,
      werte: 'values_text' in ch,
    };
    for (const t of TABS) byId('tab-' + t).classList.toggle('dirty', !!pick(td, t));
    if (n) savedNote = false;
    const save = byId('pn-save');
    const saveNew = byId('pn-save-new');
    save.disabled = !prof || !n || profSaving;
    saveNew.disabled = !prof || profSaving || busy || ended;
    saveNew.title = busy ? 'Geht, sobald ' + kiName() + ' mit der Antwort fertig ist.' : 'Speichern und gleich ein neues Gespräch beginnen';
    renderProfStatus(n);
  }

  function renderProfStatus(n) {
    const box = byId('pn-status');
    box.replaceChildren();
    box.className = 'pn-status';
    if (!prof) return;
    if (profSaving) {
      box.append(h('span', 'spinner'), h('span', null, 'Speichere …'));
    } else if (profError) {
      box.classList.add('error');
      box.append(icon('alertCircle'), h('span', null, profError));
    } else if (n) {
      box.classList.add('dirty');
      box.append(h('span', 'pn-dot'), h('span', null, n === 1 ? 'Ungespeicherte Änderung' : 'Ungespeicherte Änderungen'));
    } else if (savedNote) {
      box.classList.add('ok');
      box.append(icon('checkCircle'), h('span', null, 'Gespeichert – gilt ab dem nächsten Gespräch.'));
      if (!busy && !ended) {
        const b = h('button', 'link-btn', 'Jetzt neues Gespräch beginnen');
        b.type = 'button';
        b.addEventListener('click', startNewConversation);
        box.append(b);
      }
    } else {
      box.classList.add('muted');
      box.append(icon('info'), h('span', null, 'Änderungen gelten ab dem nächsten Gespräch.'));
    }
  }

  async function saveProfile(andNew) {
    if (!prof || profSaving) return false;
    const ch = profChanges();
    const problem = nameProblem(ch);
    if (problem) {
      profError = problem;
      showTab('charakter', false);
      pfName.focus();
      updateDirty();
      return false;
    }
    if (andNew && busy) { toast('Ich arbeite noch – ein neues Gespräch geht, sobald ich fertig bin.'); return false; }
    if (!Object.keys(ch).length) {
      if (andNew) startNewConversation();
      return true;
    }
    const focusKey = profFocusKey(); // vor dem Speichern merken (Knoepfe werden kurz gesperrt)
    profSaving = true;
    profError = '';
    updateDirty();
    const r = await post('/api/profile', ch);
    profSaving = false;
    if (!r.ok) {
      profError = r.error || 'Speichern hat nicht geklappt.';
      updateDirty();
      restoreProfFocus(focusKey);
      toast(profError, 'error');
      return false;
    }
    if (r.profile && typeof r.profile === 'object') fillProfile(r.profile);
    else await loadProfile();
    if (andNew) {
      startNewConversation();
    } else {
      savedNote = true;
      updateDirty();
      restoreProfFocus(focusKey);
    }
    return true;
  }

  /** Welches Element im Fenster hat den Fokus? (Karten/Knoepfe werden beim Speichern neu gebaut) */
  function profFocusKey() {
    const a = document.activeElement;
    if (!a || !panel.contains(a)) return null;
    const k = { id: a.id || '', charId: '', styleKey: '', styleVal: '', sel: null };
    if (a.classList.contains('char-card')) k.charId = a.dataset.id || '';
    else if (a.classList.contains('segctl-btn')) { k.styleKey = a.dataset.key || ''; k.styleVal = a.dataset.value || ''; }
    try { if (typeof a.selectionStart === 'number') k.sel = [a.selectionStart, a.selectionEnd]; } catch (_) { k.sel = null; }
    return k;
  }
  function restoreProfFocus(k) {
    if (!k || pmodal.hidden || !pconfirm.hidden) return;
    let el = null;
    if (k.charId) el = [...byId('char-grid').children].find((b) => b.dataset.id === k.charId) || null;
    else if (k.styleKey) {
      el = [...byId('style-list').querySelectorAll('.segctl-btn')]
        .find((b) => b.dataset.key === k.styleKey && b.dataset.value === k.styleVal) || null;
    } else if (k.id) el = byId(k.id);
    if (el && el.id === 'pn-save' && el.disabled) el = byId('pn-save-new');
    if (el && (el.disabled || el.offsetParent === null)) el = null;
    (el || panel).focus();
    if (el && k.sel && typeof el.setSelectionRange === 'function') {
      try { el.setSelectionRange(k.sel[0], k.sel[1]); } catch (_) { /* egal */ }
    }
  }

  function startNewConversation() {
    if (afkBlocksNew()) return;
    if (busy) { toast('Ich arbeite noch – ein neues Gespräch geht, sobald ich fertig bin.'); return; }
    closeProfile();
    send('/neu');
  }

  byId('pn-save').addEventListener('click', () => saveProfile(false));
  byId('pn-save-new').addEventListener('click', () => saveProfile(true));
  byId('pn-close').addEventListener('click', requestClose);
  byId('pn-retry').addEventListener('click', loadProfile);
  pmodal.addEventListener('mousedown', (e) => {
    if (e.target !== pmodal) return;
    e.preventDefault(); // Fokus bleibt im Fenster
    // zweiter Klick eines Doppelklicks auf den Ausloeser (z.B. "Profil") schliesst nicht gleich wieder
    if (e.detail > 1 || performance.now() - profOpenedAt < 400) return;
    requestClose();
  });
  byId('pc-discard').addEventListener('click', closeProfile);
  byId('pc-back').addEventListener('click', () => { hideConfirm(); byId('pn-save').focus(); });
  byId('pc-save').addEventListener('click', async () => {
    hideConfirm();
    if (await saveProfile(false)) closeProfile();
  });

  /** Namen im Fenster aktuell halten (nach Umbenennen, Zustand). */
  function profileNames() {
    const n = (prof && prof.name) || kiName();
    byId('pn-sub').textContent = 'Wie ' + n + ' sein soll – und was sie über dich weiß';
    byId('about-title').textContent = 'Was ' + n + ' über dich wissen soll';
    byId('values-title').textContent = 'Deine Regeln für ' + n;
    byId('mem-title').textContent = 'Was ' + n + ' sich gemerkt hat';
    if (!pmodal.hidden && prof) updateDirty();
  }

  /** Tab-Taste im Fenster halten */
  function trapTab(e, root) {
    const f = [...root.querySelectorAll('button, input, textarea, select, summary, [tabindex]')]
      .filter((el) => !el.disabled && el.tabIndex >= 0 && el.offsetParent !== null && !el.closest('[inert]'));
    if (!f.length) { e.preventDefault(); return; }
    const i = f.indexOf(document.activeElement);
    if (e.shiftKey ? i <= 0 : i === f.length - 1 || i < 0) {
      e.preventDefault();
      f[e.shiftKey ? f.length - 1 : 0].focus();
    }
  }

  function profileKey(e) {
    if (!pconfirm.hidden) {
      if (e.key === 'Escape') { e.preventDefault(); hideConfirm(); byId('pn-save').focus(); }
      else if (e.key === 'Tab') trapTab(e, pconfirm);
      else if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') {
        e.preventDefault(); // nicht "Seite speichern" des Browsers
        byId('pc-save').click();
      }
      return;
    }
    if (e.key === 'F2') { e.preventDefault(); return; }
    if (e.key === 'Escape') {
      e.preventDefault();
      if (memConfirm) { memConfirmReset(); return; }
      if (e.target === memSearch && memSearch.value) { memSearch.value = ''; renderMemory(); return; }
      requestClose();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') {
      e.preventDefault();
      saveProfile(false);
      return;
    }
    if (e.key === 'Tab') trapTab(e, panel);
  }

  // ---------- Gedaechtnis ----------
  async function loadMemory() {
    const gen = ++mem.gen;
    mem.loading = true;
    mem.error = false;
    renderMemory();
    const d = await getJson('/api/memory');
    if (gen !== mem.gen) return;
    mem.loading = false;
    if (!d || !Array.isArray(d.facts)) { mem.error = true; renderMemory(); return; }
    setFacts(d);
  }

  function setFacts(d) {
    mem.facts = d.facts.filter((f) => f && typeof f === 'object' && f.id != null).map((f) => ({
      id: f.id,
      category: str(f.category).trim() || 'allgemein',
      content: str(f.content),
      importance: Math.max(0, Math.min(5, Math.round(Number(f.importance) || 0))),
    }));
    const c = Number(d.count);
    mem.count = Number.isFinite(c) && c >= mem.facts.length ? c : mem.facts.length;
    mem.loaded = true;
    mem.error = false;
    fillCats();
    renderMemory();
  }

  function fillCats() {
    const cur = memCat.value || 'notiz';
    const cats = [...MEM_CATS];
    for (const f of mem.facts) if (!cats.includes(f.category)) cats.push(f.category);
    memCat.replaceChildren();
    for (const c of cats) {
      const o = h('option', null, c.charAt(0).toUpperCase() + c.slice(1));
      o.value = c;
      memCat.append(o);
    }
    memCat.value = cats.includes(cur) ? cur : 'notiz';
  }
  fillCats();

  function catHue(cat) {
    let x = 0;
    for (const ch of cat) x = (x * 31 + ch.codePointAt(0)) >>> 0;
    return x % 6;
  }

  /** Text mit markiertem Suchbegriff (nur Textknoten + <mark>). */
  function appendHighlighted(el, text, q) {
    const low = text.toLowerCase();
    if (!q || low.length !== text.length) { el.textContent = text; return; }
    let pos = 0;
    let k;
    while ((k = low.indexOf(q, pos)) >= 0) {
      if (k > pos) el.append(text.slice(pos, k));
      el.append(h('mark', null, text.slice(k, k + q.length)));
      pos = k + q.length;
    }
    if (pos < text.length) el.append(text.slice(pos));
  }

  function memStateBox(kind, title, sub, btn) {
    const d = h('div', 'mem-empty' + (kind === 'error' ? ' error' : ''));
    if (kind === 'loading') d.append(h('span', 'spinner'));
    else d.append(icon(kind === 'error' ? 'alertCircle' : kind === 'search' ? 'search' : 'brain', 'me-ic'));
    d.append(h('div', 'me-title', title));
    if (sub) d.append(h('div', 'me-sub', sub));
    if (btn) d.append(btn);
    return d;
  }

  function renderMemory() {
    const list = byId('mem-list');
    list.replaceChildren();
    const q = memSearch.value.trim().toLowerCase();
    byId('tab-mem-count').textContent = mem.loaded && mem.count ? String(mem.count) : '';
    const countEl = byId('mem-count');
    countEl.textContent = '';
    if (!mem.loaded) {
      if (mem.error) {
        const b = h('button', 'btn small secondary', 'Nochmal versuchen');
        b.type = 'button';
        b.addEventListener('click', loadMemory);
        list.append(memStateBox('error', 'Das Gedächtnis konnte nicht geladen werden.', '', b));
      } else {
        list.append(memStateBox('loading', 'Lade das Gedächtnis …'));
      }
      return;
    }
    const n = kiName();
    const shown = q ? mem.facts.filter((f) => f.content.toLowerCase().includes(q) || f.category.toLowerCase().includes(q)) : mem.facts;
    if (q) countEl.textContent = shown.length + ' von ' + mem.count + (mem.count === 1 ? ' Eintrag' : ' Einträgen');
    else if (mem.facts.length < mem.count) countEl.textContent = 'die wichtigsten ' + mem.facts.length + ' von ' + mem.count;
    else countEl.textContent = mem.count === 1 ? '1 Eintrag' : mem.count + ' Einträge';
    if (!mem.facts.length) {
      list.append(memStateBox('empty', 'Noch nichts gemerkt',
        'Erzähl ' + n + ' etwas über dich – oder füge oben selbst etwas hinzu.'));
      return;
    }
    if (!shown.length) {
      list.append(memStateBox('search', 'Nichts gefunden', 'Kein Eintrag passt zu „' + memSearch.value.trim() + '“.'));
      return;
    }
    let fresh = null;
    for (const f of shown) {
      const row = factRow(f, q);
      if (memFlash && f.content === memFlash) { row.classList.add('fresh'); fresh = row; }
      list.append(row);
    }
    memFlash = '';
    if (fresh) requestAnimationFrame(() => fresh.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
  }

  function factRow(f, q) {
    const row = h('div', 'fact');
    row.dataset.id = String(f.id);
    const cat = h('span', 'fact-cat c' + catHue(f.category));
    cat.append(icon('tag'), h('span', null, f.category));
    const text = h('div', 'fact-text');
    appendHighlighted(text, f.content, q);
    const imp = h('span', 'fact-imp');
    imp.title = 'Wichtigkeit ' + f.importance + ' von 5';
    imp.setAttribute('role', 'img');
    imp.setAttribute('aria-label', imp.title);
    for (let i = 1; i <= 5; i++) imp.append(h('i', i <= f.importance ? 'on' : null));
    const del = h('button', 'fact-del');
    del.type = 'button';
    del.title = 'Vergessen';
    del.setAttribute('aria-label', 'Vergessen: ' + f.content.slice(0, 80));
    del.append(icon('trash'), h('span', 'fact-del-text', 'Wirklich?'));
    del.addEventListener('click', () => onForget(f, row, del));
    row.append(cat, text, imp, del);
    return row;
  }

  function memConfirmReset() {
    if (!memConfirm) return;
    clearTimeout(memConfirm.timer);
    const d = memConfirm.del;
    d.classList.remove('confirm');
    d.title = 'Vergessen';
    d.setAttribute('aria-label', memConfirm.label);
    memConfirm = null;
  }

  function onForget(f, row, del) {
    if (memConfirm && memConfirm.del === del) { forget(f, row); return; }
    memConfirmReset();
    memConfirm = { del, label: del.getAttribute('aria-label'), timer: setTimeout(memConfirmReset, 4000) };
    del.classList.add('confirm');
    del.title = 'Nochmal klicken zum Vergessen';
    del.setAttribute('aria-label', 'Wirklich vergessen? Nochmal drücken');
  }

  async function forget(f, row) {
    memConfirmReset();
    const rows = [...byId('mem-list').querySelectorAll('.fact')];
    const idx = rows.indexOf(row);
    row.classList.add('removing');
    const r = await post('/api/memory', { action: 'delete', id: f.id });
    if (Array.isArray(r.facts)) setFacts(r);
    else row.classList.remove('removing');
    if (!r.ok) { toast(r.error || 'Das hat nicht geklappt.', 'error'); return; }
    toast('Vergessen', 'ok', 1600);
    // Fokus auf den naechsten Eintrag (oder das Eingabefeld)
    const left = [...byId('mem-list').querySelectorAll('.fact-del')];
    const next = left[Math.min(idx, left.length - 1)];
    if (next) next.focus(); else memNew.focus();
  }

  function updateAddBtn() { memAddBtn.disabled = memAdding || !memNew.value.trim(); }
  memNew.addEventListener('input', updateAddBtn);
  memSearch.addEventListener('input', () => { memConfirmReset(); renderMemory(); });
  byId('mem-add').addEventListener('submit', async (e) => {
    e.preventDefault();
    const content = memNew.value.trim();
    if (!content || memAdding) return;
    memAdding = true;
    updateAddBtn();
    const r = await post('/api/memory', { action: 'add', content, category: memCat.value || 'notiz' });
    memAdding = false;
    if (r.ok) {
      memNew.value = '';
      memSearch.value = '';
      memFlash = content;
    } else {
      toast(r.error || 'Hinzufügen hat nicht geklappt.', 'error');
    }
    if (Array.isArray(r.facts)) setFacts(r);
    updateAddBtn();
    memNew.focus();
  });

  // =====================================================================
  // Aussehen, das Nova anpasst (/api/appearance, /custom.css)
  // Alle Werte werden hier geprueft und selbst formatiert – vom Server kommt
  // nie fertiges CSS in ein <style>; eigenes CSS kommt nur als Datei /custom.css.
  // =====================================================================
  const look = { greeting: '', examples: [], gen: 0, cssGen: 0, cssLoaded: 0 };
  const lookStyle = document.createElement('style');
  lookStyle.id = 'appearance-vars';
  byId('custom-css').before(lookStyle);
  const sugBox = byId('suggestions');
  const defaultSugs = [...sugBox.children];
  const RADII = { eckig: '4px', normal: '12px', rund: '20px' };
  const DENSITY = { kompakt: '.8', normal: '1', luftig: '1.25' };

  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  function hexRgb(hex) {
    let s = hex.slice(1);
    if (s.length === 3) s = s.split('').map((c) => c + c).join('');
    const n = parseInt(s, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgbHsl([r, g, b]) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;
    let hh = 0;
    let s = 0;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) hh = (g - b) / d + (g < b ? 6 : 0);
      else if (max === g) hh = (b - r) / d + 2;
      else hh = (r - g) / d + 4;
      hh *= 60;
    }
    return [hh, s, l];
  }
  function hslRgb(hh, s, l) {
    hh = ((hh % 360) + 360) % 360;
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs(((hh / 60) % 2) - 1));
    const m = l - c / 2;
    const [r, g, b] = hh < 60 ? [c, x, 0] : hh < 120 ? [x, c, 0] : hh < 180 ? [0, c, x]
      : hh < 240 ? [0, x, c] : hh < 300 ? [x, 0, c] : [c, 0, x];
    return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
  }
  function lum(rgb) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
  }
  function contrast(a, b) {
    const x = lum(a);
    const y = lum(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }
  /** Helligkeit schrittweise aendern, bis der Kontrast zum Hintergrund reicht. */
  function withContrast(hh, s, l, bg, min, dir) {
    let rgb = hslRgb(hh, s, l);
    for (let i = 0; i < 40 && contrast(rgb, bg) < min; i++) {
      l = clamp(l + dir * 0.02, 0, 1);
      rgb = hslRgb(hh, s, l);
    }
    return rgb;
  }
  const rgbCss = (c, a) => (a == null ? 'rgb(' + c.join(', ') + ')' : 'rgba(' + c.join(', ') + ', ' + a + ')');
  const onColor = (bg) => (contrast(bg, [255, 255, 255]) >= 2.9 ? '#ffffff' : '#0b0d12');

  function accentVars(hex) {
    const base = hexRgb(hex);
    const [hh, s, l] = rgbHsl(base);
    const white = [255, 255, 255];
    const darkBg = [24, 27, 33];
    const v = (o) => Object.entries(o).map(([k, val]) => '--' + k + ':' + val + ';').join('');
    const hover = hslRgb(hh, s, clamp(l - 0.07, 0, 1));
    const gradB = hslRgb(hh + 34, s, l);
    const light = v({
      accent: rgbCss(base), 'accent-hover': rgbCss(hover),
      'accent-soft': 'color-mix(in srgb, ' + rgbCss(base) + ' 11%, #fff)',
      'accent-text': rgbCss(withContrast(hh, s, l, white, 4.6, -1)),
      'on-accent': onColor(base), 'user-bg': rgbCss(base), 'user-text': onColor(base),
      'grad-a': rgbCss(base), 'grad-b': rgbCss(gradB),
    });
    const accD = withContrast(hh, s, l, darkBg, 3.2, 1);
    const [, , lD] = rgbHsl(accD);
    const dark = v({
      accent: rgbCss(accD), 'accent-hover': rgbCss(hslRgb(hh, s, clamp(lD + 0.06, 0, 1))),
      'accent-soft': rgbCss(accD, 0.18),
      'accent-text': rgbCss(withContrast(hh, s, Math.max(l, 0.62), darkBg, 6, 1)),
      'on-accent': onColor(accD), 'user-bg': rgbCss(base), 'user-text': onColor(base),
      'grad-a': rgbCss(base), 'grad-b': rgbCss(gradB),
    });
    return { light, dark };
  }

  function applyAppearance(s) {
    s = s && typeof s === 'object' && !Array.isArray(s) ? s : {};
    const hex = typeof s.akzentfarbe === 'string' && /^#(?:[0-9a-f]{3}){1,2}$/i.test(s.akzentfarbe.trim())
      ? s.akzentfarbe.trim() : '';
    const size = Number(s.schriftgroesse);
    const scale = Number.isFinite(size) && size > 0 ? clamp(Math.round(size), 80, 140) / 100 : 1;
    const radius = pick(RADII, String(s.ecken || '')) || '';
    const dens = pick(DENSITY, String(s.dichte || '')) || '';
    let root = '';
    if (scale !== 1) root += '--font-scale:' + scale + ';';
    if (radius) root += '--radius:' + radius + ';';
    if (dens) root += '--density:' + dens + ';';
    let css = '';
    let dark = '';
    if (hex) {
      const a = accentVars(hex);
      root += a.light;
      dark = a.dark;
    }
    if (root) css += ':root{' + root + '}';
    if (dark) {
      css += '@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])){' + dark + '}}' +
        ':root:where([data-theme="dark"]){' + dark + '}';
    }
    lookStyle.textContent = css;
    look.greeting = typeof s.begruessung === 'string' ? s.begruessung.trim().slice(0, 300) : '';
    look.examples = (Array.isArray(s.beispiele) ? s.beispiele : [])
      .map((x) => (typeof x === 'string' || typeof x === 'number' ? String(x).trim().slice(0, 160) : ''))
      .filter(Boolean).slice(0, 6);
    renderGreeting();
    renderSuggestions();
    setFavicon(initial());
    // Novas Sphaere: Art, Farbe, Bewegung (unbekannte Werte -> Standard)
    const orbHex = typeof s.sphaere_farbe === 'string' && /^#(?:[0-9a-f]{3}){1,2}$/i.test(s.sphaere_farbe.trim())
      ? s.sphaere_farbe.trim() : '';
    sphere.setLook({
      mode: s.avatar === 'buchstabe' ? 'buchstabe' : 'sphaere',
      color: orbHex,
      motion: ['ruhig', 'normal', 'lebhaft'].includes(s.bewegung) ? s.bewegung : 'normal',
    });
    syncHero();
  }

  function renderGreeting() {
    const t = byId('empty-title');
    const g = look.greeting;
    t.textContent = g || 'Hallo! Ich bin ' + kiName() + '.';
    t.classList.toggle('long', g.length > 48);
  }

  let sugKey = '';
  function renderSuggestions() {
    const ex = look.examples;
    const key = ex.join('\u0001');
    if (key === sugKey) return;
    sugKey = key;
    if (!ex.length) { sugBox.replaceChildren(...defaultSugs); return; }
    const ICS = ['sparkles', 'book', 'globe', 'pen', 'compass', 'brain'];
    sugBox.replaceChildren(...ex.map((text, k) => {
      const b = h('button', 'suggestion custom');
      b.type = 'button';
      const tx = h('span', 'sg-text');
      tx.append(h('span', 'sg-title', text));
      b.append(icon(ICS[k % ICS.length]), tx);
      b.addEventListener('click', () => send(text));
      return b;
    }));
  }

  /** Eigenes CSS neu laden – erst nach dem Laden das alte entfernen (kein Flackern). */
  function reloadCustomCss() {
    const gen = ++look.cssGen;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.className = 'custom-css';
    link.href = '/custom.css?v=' + Date.now();
    const done = () => {
      if (gen < look.cssLoaded) { link.remove(); return; } // ein neueres ist schon da
      look.cssLoaded = gen;
      for (const old of document.querySelectorAll('link#custom-css, link.custom-css')) if (old !== link) old.remove();
      link.id = 'custom-css';
      sphere.refresh();
    };
    link.addEventListener('load', done);
    link.addEventListener('error', done);
    const last = [...document.querySelectorAll('link#custom-css, link.custom-css')].pop();
    if (last) last.after(link); else document.head.append(link);
  }

  async function loadAppearance(reloadCss) {
    const gen = ++look.gen;
    if (reloadCss) reloadCustomCss();
    const d = await getJson('/api/appearance');
    if (gen !== look.gen || !d || typeof d !== 'object') return;
    applyAppearance(d.settings);
  }

  // =====================================================================
  // Bestaetigung (eigener Dialog, z.B. "Stuetzraeder abnehmen?")
  // =====================================================================
  let confirmState = null;
  // So lange nach dem Oeffnen zaehlen Maus-Klicks im Dialog nicht: sonst rutscht der zweite
  // Klick eines Doppelklicks durch (z.B. "Abnehmen" -> gleich auf "Stuetzraeder abnehmen").
  const CONFIRM_GUARD_MS = 500;
  function confirmDialog(opts) {
    if (confirmState) closeConfirm(false);
    return new Promise((resolve) => {
      confirmState = {
        resolve, back: document.activeElement, raw: !!opts.raw, kind: opts.kind || '', at: performance.now(),
      };
      byId('cdialog').className = 'dialog cdialog ' + (opts.cls || 'risk-none');
      byId('cd-icon').replaceChildren(icon(opts.icon || 'alert'));
      byId('cd-title').textContent = opts.title || '';
      byId('cd-risk').textContent = opts.risk || '';
      byId('cd-text').replaceChildren(opts.body || '');
      byId('cd-ok').textContent = opts.ok || 'OK';
      byId('cd-ok').hidden = opts.ok === null; // Auswahl: die Knoepfe stehen im Text
      byId('cd-cancel').textContent = opts.cancel || 'Abbrechen';
      cmodal.hidden = false;
      updateInert();
      byId('cd-cancel').focus(); // sicherer Standard
    });
  }
  function closeConfirm(result) {
    if (!confirmState) return;
    const st = confirmState;
    confirmState = null;
    cmodal.hidden = true;
    updateInert();
    const back = st.back;
    // Rueckfrage kam, waehrend dieser Dialog offen war: nach ihr nicht auf den (versteckten) Dialog zurueck
    if (askFocusBack && cmodal.contains(askFocusBack)) askFocusBack = back;
    if (back && back !== document.body && document.contains(back) && !back.closest('[inert]')) back.focus();
    else if (!modal.hidden) dialog.focus(); // offene Rueckfrage liegt jetzt oben
    else if (jv.open) jvEl.focus();
    else if (!smodal.hidden) sdialog.focus();
    else if (!pmodal.hidden) panel.focus();
    else focusInput();
    st.resolve(st.raw ? result : !!result);
  }
  /** Maus-Klick zu kurz nach dem Oeffnen oder Teil eines Doppelklicks? (Tastatur zaehlt immer: detail 0) */
  function confirmTooSoon(e) {
    if (!confirmState || !e || !e.detail) return false;
    return e.detail > 1 || performance.now() - confirmState.at < CONFIRM_GUARD_MS;
  }
  byId('cd-ok').addEventListener('click', (e) => { if (!confirmTooSoon(e)) closeConfirm(true); });
  byId('cd-cancel').addEventListener('click', (e) => { if (!confirmTooSoon(e)) closeConfirm(false); });
  cmodal.addEventListener('mousedown', (e) => {
    if (e.target !== cmodal) return;
    e.preventDefault(); // Fokus bleibt im Dialog (auch beim ignorierten zweiten Klick eines Doppelklicks)
    if (!confirmTooSoon(e)) closeConfirm(false);
  });
  function confirmKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeConfirm(false); return; }
    if (e.key === 'F2') { e.preventDefault(); return; }
    if (e.key === 'Tab') trapTab(e, byId('cdialog'));
  }

  function wheelsWarning() {
    const n = kiName();
    const body = document.createDocumentFragment();
    const p = h('p');
    p.append('Ohne Stützräder darf ' + n + ' am ', h('b', null, 'GANZEN PC'),
      ' Dateien ändern und löschen, Programme starten, Maus und Tastatur steuern – ohne zu fragen.');
    const caps = h('ul', 'cd-caps');
    for (const [ic, t] of [['trash', 'Dateien ändern und löschen'], ['terminal', 'Programme starten'],
      ['mouse', 'Maus und Tastatur steuern']]) {
      const li = h('li');
      li.append(icon(ic), h('span', null, t));
      caps.append(li);
    }
    const note = h('p', 'cd-note');
    note.append(icon('power'), h('span', null, 'Automatische Starts fragt sie trotzdem.'));
    body.append(p, caps, note);
    return confirmDialog({
      cls: 'risk-wheels', icon: 'shieldOff', title: 'Stützräder abnehmen?', risk: 'Voller Zugriff auf deinen PC',
      body, ok: 'Stützräder abnehmen', cancel: 'Abbrechen', kind: 'wheels-off',
    });
  }

  /** Liste "Gerade gilt" der Auswahl fuellen (nur neu bauen, wenn sich etwas geaendert hat). */
  function wheelsFacts(facts) {
    const n = kiName();
    const s = state;
    const key = [!!s.auto_confirm, !!s.full_access, !!s.safe_mode, n].join('|');
    if (facts.dataset.key === key) return;
    facts.dataset.key = key;
    facts.replaceChildren();
    for (const [good, ic, k, v] of [
      [!s.auto_confirm, s.auto_confirm ? 'zap' : 'checkCircle', 'Rückfragen', s.auto_confirm ? n + ' fragt nicht nach' : n + ' fragt nach'],
      [!s.full_access, s.full_access ? 'monitor' : 'folder', 'Zugriff', s.full_access ? 'ganzer PC' : 'nur Arbeitsordner'],
      [!!s.safe_mode, s.safe_mode ? 'shield' : 'shieldOff', 'Sicherer Modus', s.safe_mode ? 'an' : 'aus'],
    ]) {
      const li = h('li', good ? 'good' : 'bad');
      const t = h('span', 'cdf-text');
      t.append(h('span', 'cdf-k', k), h('span', 'cdf-v', v));
      li.append(icon(ic), t);
      facts.append(li);
    }
  }

  /** Neuer Stand vom Server, waehrend Auswahl oder Warnung offen sind (z.B. im anderen Fenster umgestellt). */
  function syncWheelsDialog(w) {
    const kind = confirmState ? confirmState.kind : '';
    if (kind !== 'wheels-choice' && kind !== 'wheels-off') return;
    if (kind === 'wheels-choice' && w === 'teilweise') {
      const facts = byId('cd-text').querySelector('.cd-facts');
      if (facts) wheelsFacts(facts);
      return;
    }
    // Warnung: gilt weiter, solange noch etwas abzunehmen ist ("an" oder "teilweise")
    if (kind === 'wheels-off' && (w === 'an' || w === 'teilweise')) return;
    closeConfirm(false);
    if (w === 'an') toast('Die Stützräder wurden inzwischen angelegt.', 'info');
    else if (w === 'aus') toast('Die Stützräder wurden inzwischen abgenommen.', 'info');
  }

  /** Stuetzraeder "teilweise": was gerade gilt – anlegen, abnehmen oder abbrechen. Ergebnis 'an' | 'aus' | false. */
  function wheelsChoice() {
    const body = document.createDocumentFragment();
    body.append(h('p', null, 'Ein Teil des Schutzes ist an, ein Teil aus. Gerade gilt:'));
    const facts = h('ul', 'cd-facts');
    wheelsFacts(facts);
    const ask = h('p', 'cd-ask', 'Was möchtest du?');
    const choices = h('div', 'cd-choices');
    for (const [cls, ic, title, sub, val] of [
      ['safe', 'shield', 'Anlegen – sicher', 'fragt vor Änderungen, nur Arbeitsordner, sicherer Modus an', 'an'],
      ['free', 'shieldOff', 'Abnehmen – volle Rechte', 'ganzer PC, ohne Rückfrage – vorher kommt eine Warnung', 'aus'],
    ]) {
      const b = h('button', 'cd-choice ' + cls);
      b.type = 'button';
      const t = h('span', 'cdc-text');
      t.append(h('span', 'cdc-title', title), h('span', 'cdc-sub', sub));
      b.append(icon(ic, 'cdc-ic'), t, icon('chevronRight', 'cdc-chev'));
      b.addEventListener('click', (e) => { if (!confirmTooSoon(e)) closeConfirm(val); });
      choices.append(b);
    }
    body.append(facts, ask, choices);
    return confirmDialog({
      cls: 'risk-moderate wheels-choice', icon: 'shield', title: 'Stützräder: teilweise', risk: 'Gemischte Einstellung',
      body, ok: null, cancel: 'Abbrechen', raw: true, kind: 'wheels-choice',
    });
  }

  // =====================================================================
  // Jarvis-Modus: Vorlesen im Fenster (speechSynthesis)
  //  - jeder Satz eine eigene Utterance (Chrome bricht lange ab)
  //  - nach jedem Satz "spoken" mit seq (Fortschritt), nach say_end + leerer
  //    Warteschlange einmal "spoken" ohne seq
  //  - hush: sofort still, Warteschlange leer, kein "spoken"
  // =====================================================================
  const synth = window.speechSynthesis && typeof window.SpeechSynthesisUtterance === 'function'
    ? window.speechSynthesis : null;
  const tts = {
    voice: null, voices: 0, waiting: false, waitTimer: 0, noVoice: !synth, blocked: false, fails: 0,
    queue: [], cur: null, ends: new Map(), answered: new Set(), maxTurn: 0, cooldown: 0, pumpTimer: 0, followAt: 0,
  };

  function voiceRank(v) {
    const name = String(v.name || '');
    let r = /natural/i.test(name) ? 0 : /online/i.test(name) ? 1 : v.localService === false ? 2 : 3;
    if (!/^de[-_]de$/i.test(String(v.lang || ''))) r += 0.5; // de-DE vor de-AT/de-CH
    return r;
  }
  function loadVoices() {
    if (!synth) return 0;
    let list = [];
    try { list = synth.getVoices() || []; } catch (_) { list = []; }
    tts.voices = list.length;
    if (!list.length) return 0;
    const de = list.filter((v) => /^de(?:$|[-_])/i.test(String(v.lang || '')));
    let best = de.length ? [...de].sort((a, b) => voiceRank(a) - voiceRank(b))[0] : null;
    let saved = '';
    try { saved = localStorage.getItem('ki-stimme') || ''; } catch (_) { /* egal */ }
    const old = saved && de.find((v) => v.voiceURI === saved);
    if (old && best && voiceRank(old) <= voiceRank(best)) best = old; // gemerkte Stimme behalten
    tts.voice = best;
    if (best) { try { localStorage.setItem('ki-stimme', best.voiceURI); } catch (_) { /* egal */ } }
    return list.length;
  }
  if (synth) {
    const onVoices = () => {
      if (!loadVoices()) return;
      tts.noVoice = false;
      if (tts.waiting) { tts.waiting = false; clearTimeout(tts.waitTimer); }
      ttsPump();
    };
    if (typeof synth.addEventListener === 'function') synth.addEventListener('voiceschanged', onVoices);
    else synth.onvoiceschanged = onVoices;
    loadVoices();
  }

  // ---------- Mehrere Fenster: nur eines liest vor ----------
  // Sind zwei Fenster offen (z.B. Browser-Ersatz), liest nur das Fenster vor, in dem Jarvis
  // gestartet wurde – sonst das, das vorne ist. Die anderen zeigen nur Untertitel und melden
  // kein "spoken" (sonst redet Nova doppelt und das schnellere Fenster meldet "fertig").
  const WIN_ID = (() => {
    try { if (window.crypto && typeof crypto.randomUUID === 'function') return crypto.randomUUID(); } catch (_) { /* egal */ }
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  })();
  const lead = { owner: '', rank: -1, timer: 0, silent: new Set() };
  let leadBc = null;
  try { if (typeof BroadcastChannel === 'function') leadBc = new BroadcastChannel('ki-jarvis-stimme'); } catch (_) { leadBc = null; }
  const iSpeak = () => lead.owner === WIN_ID;
  function leadSend(t) {
    if (!leadBc) return;
    try { leadBc.postMessage({ t, id: WIN_ID, rank: lead.rank }); } catch (_) { /* egal */ }
  }
  /** Dieses Fenster liest vor. rank: 2 = hier gestartet, 1 = Fenster ist vorne, 0 = sonst. */
  function leadClaim(rank) {
    clearTimeout(lead.timer);
    lead.timer = 0;
    lead.owner = WIN_ID;
    lead.rank = rank;
    leadSend('own');
    // Was ein anderes (inzwischen weg) Fenster melden sollte: Nova ist hier still
    for (const turn of lead.silent) {
      if (turn >= tts.maxTurn && jv.open && !jv.left) post('/api/jarvis', { action: 'spoken', turn });
    }
    lead.silent.clear();
    if (rank < 2 && !tts.cur && !tts.queue.length) ttsWarmup(); // beim Knopf-Start macht das startJarvis
    ttsPump();
  }
  /** Ein anderes Fenster liest vor: hier still sein, nur noch Untertitel. */
  function leadYield(id, rank) {
    clearTimeout(lead.timer);
    lead.timer = 0;
    lead.owner = id;
    lead.rank = rank;
    const cur = dropCur();
    if (cur) {
      if (!cur.shown) showSub(cur.it.text);
      ttsCancelSynth();
    }
    ttsPump();
  }
  function leadLater(ms) {
    clearTimeout(lead.timer);
    lead.timer = setTimeout(() => {
      lead.timer = 0;
      if (jv.open && !lead.owner) leadClaim(document.hasFocus() ? 1 : 0);
    }, ms);
  }
  /** Beim Oeffnen der Ansicht: wer liest vor? started = hier per Knopf/Befehl gestartet. */
  function leadElect(started) {
    clearTimeout(lead.timer);
    lead.timer = 0;
    lead.silent.clear();
    lead.owner = '';
    lead.rank = -1;
    if (started || !leadBc) { leadClaim(started ? 2 : 1); return; }
    leadSend('who'); // liest schon ein Fenster vor? Es antwortet sofort.
    leadLater(document.hasFocus() ? 150 : 450); // sonst: das vordere Fenster zuerst
  }
  /** Ansicht zu: ein anderes Fenster darf uebernehmen. */
  function leadRelease() {
    clearTimeout(lead.timer);
    lead.timer = 0;
    if (iSpeak()) leadSend('free');
    lead.owner = '';
    lead.rank = -1;
    lead.silent.clear();
  }
  if (leadBc) {
    leadBc.onmessage = (e) => {
      const m = e && e.data;
      if (!m || typeof m !== 'object' || typeof m.id !== 'string' || m.id === WIN_ID) return;
      const rank = Number(m.rank) || 0;
      if (m.t === 'who') { if (jv.open && iSpeak()) leadSend('own'); return; }
      if (!jv.open) return;
      if (m.t === 'free') {
        if (lead.owner === m.id) { lead.owner = ''; lead.rank = -1; leadLater(document.hasFocus() ? 60 : 300); }
        return;
      }
      if (m.t !== 'own') return;
      if (iSpeak()) {
        // beide wollen vorlesen: der hoehere Rang gewinnt, bei Gleichstand die kleinere Kennung
        if (rank > lead.rank || (rank === lead.rank && m.id < WIN_ID)) leadYield(m.id, rank);
        else leadSend('own');
        return;
      }
      clearTimeout(lead.timer);
      lead.timer = 0;
      lead.owner = m.id;
      lead.rank = rank;
      ttsPump();
    };
  }

  /** Beim Start (Nutzer-Geste): stumme Utterance, damit der erste Satz sofort kommt. */
  function ttsWarmup() {
    if (!synth || !iSpeak()) return;
    try {
      synth.cancel();
      const u = new SpeechSynthesisUtterance(' ');
      u.volume = 0;
      u.lang = 'de-DE';
      synth.speak(u);
    } catch (_) { /* egal */ }
  }

  /** Neue Jarvis-Sitzung: Runden fangen beim Server wieder bei 1 an. */
  function ttsSession() {
    ttsStop();
    tts.followAt = 0;
    tts.answered.clear();
    tts.maxTurn = 0;
    tts.blocked = false;
    tts.fails = 0;
    if (!synth) { tts.noVoice = true; return; }
    if (loadVoices()) { tts.noVoice = false; return; }
    // Stimmen laden manchmal erst spaeter (voiceschanged) – kurz warten, dann ohne Stimme
    tts.waiting = true;
    clearTimeout(tts.waitTimer);
    tts.waitTimer = setTimeout(() => {
      tts.waiting = false;
      if (!tts.voices) tts.noVoice = true;
      ttsPump();
    }, 1500);
  }

  function ttsCancelSynth() {
    if (!synth) return;
    try { synth.cancel(); } catch (_) { /* egal */ }
    tts.cooldown = performance.now() + 140; // Chrome verschluckt sonst den naechsten Satz
  }

  function dropCur() {
    const cur = tts.cur;
    if (!cur) return null;
    tts.cur = null;
    clearTimeout(cur.timer);
    clearTimeout(cur.subTimer);
    orb.speaking(false);
    return cur;
  }

  /** Alles anhalten (Fenster zu, neue Sitzung). */
  function ttsStop() {
    tts.queue.length = 0;
    const had = dropCur();
    tts.ends.clear();
    clearTimeout(tts.pumpTimer);
    clearTimeout(tts.waitTimer);
    tts.waiting = false;
    // nur die eigene Sprache abbrechen (cancel() traefe sonst auch das Fenster, das gerade vorliest)
    if (had || (iSpeak() && synth && (synth.speaking || synth.pending))) ttsCancelSynth();
  }

  /** hush: sofort still, Warteschlange leeren – dafuer kein "spoken". */
  function ttsHush() {
    tts.queue.length = 0;
    const had = dropCur();
    tts.ends.clear();
    lead.silent.clear();
    tts.followAt = 0;
    clearTimeout(tts.pumpTimer);
    if (had || iSpeak()) ttsCancelSynth(); // ein Fenster, das nur mitliest, hat nichts abzubrechen
    markSubCut();
  }

  /** speak = vorlesen, show = sofort als Untertitel (und melden), follow = ein anderes Fenster
   *  liest vor: Untertitel ungefaehr im Sprechtempo, ohne Meldung, wait = noch warten. */
  function speakMode(it) {
    if (it.local) return 'show';
    if (!lead.owner) return 'wait'; // noch offen, welches Fenster vorliest (hoechstens ~0,5 s)
    if (!iSpeak()) return 'follow';
    if (!synth || tts.noVoice || tts.blocked) return 'show';
    return tts.waiting ? 'wait' : 'speak';
  }

  function ttsPump() {
    clearTimeout(tts.pumpTimer);
    tts.pumpTimer = 0;
    while (!tts.cur && tts.queue.length) {
      const it = tts.queue[0];
      const mode = speakMode(it);
      if (mode === 'wait') return;
      const now = performance.now();
      const wait = mode === 'speak' ? tts.cooldown - now : mode === 'follow' ? tts.followAt - now : 0;
      if (wait > 0) { tts.pumpTimer = setTimeout(ttsPump, wait + 5); return; }
      tts.queue.shift();
      if (mode === 'show' || mode === 'follow') {
        if (mode === 'follow') tts.followAt = now + clamp(it.text.length * 65, 900, 8000);
        showSub(it.text);
        orb.kick(0.8);
        if (!it.local) reportSeq(it);
        continue;
      }
      ttsSpeak(it);
    }
    ttsDrain();
  }

  function ttsSpeak(it) {
    let u;
    try { u = new SpeechSynthesisUtterance(it.text); } catch (_) { tts.noVoice = true; showSub(it.text); reportSeq(it); return; }
    if (tts.voice) { u.voice = tts.voice; u.lang = tts.voice.lang; } else u.lang = 'de-DE';
    const cur = { it, u, shown: false, timer: 0, subTimer: 0, extended: false };
    tts.cur = cur;
    const show = () => { if (!cur.shown) { cur.shown = true; showSub(it.text); } };
    u.onstart = () => { if (tts.cur !== cur) return; show(); orb.speaking(true); };
    u.onboundary = (e) => { if (tts.cur === cur && (!e.name || e.name === 'word')) orb.kick(1); };
    u.onend = () => ttsDone(cur, '');
    u.onerror = (e) => ttsDone(cur, (e && e.error) || 'error');
    // Untertitel spaetestens nach kurzer Zeit zeigen (manche Stimmen melden "start" spaet)
    cur.subTimer = setTimeout(() => { if (tts.cur === cur) show(); }, 900);
    // Waechter: Chrome meldet "end" manchmal nie
    cur.timer = setTimeout(() => ttsWatch(cur), 6000 + it.text.length * 110);
    try { synth.speak(u); } catch (_) { ttsDone(cur, 'error'); }
  }

  function ttsWatch(cur) {
    if (tts.cur !== cur) return;
    if (!cur.extended && synth.speaking) {
      cur.extended = true;
      cur.timer = setTimeout(() => ttsWatch(cur), 4000 + cur.it.text.length * 60);
      return;
    }
    ttsDone(cur, 'timeout');
  }

  function ttsDone(cur, err) {
    if (tts.cur !== cur) return; // abgebrochen (hush) – Meldungen davon zaehlen nicht
    dropCur();
    if (!cur.shown) { cur.shown = true; showSub(cur.it.text); }
    if (err === 'timeout') ttsCancelSynth();
    if (err === 'not-allowed') {
      // Browser erlaubt Sprache erst nach einem Klick/Tastendruck (z.B. neues Fenster, neu geladen)
      if (!tts.blocked) showNote('Vorlesen ist gerade blockiert – klick einmal ins Fenster, dann lese ich wieder vor.', 'soft', 7000);
      tts.blocked = true;
    } else if (err && err !== 'interrupted' && err !== 'canceled' && err !== 'timeout') {
      if (++tts.fails >= 2) tts.noVoice = true; // Stimme geht nicht: nur noch Untertitel
    } else if (!err) tts.fails = 0;
    reportSeq(cur.it);
    ttsPump();
  }

  /** Fortschritt: dieser Satz ist fertig (die KI weiss so genau, wann Nova still ist). */
  function reportSeq(it) {
    if (!it.seq || !jv.open || jv.left || !iSpeak()) return; // nur das vorlesende Fenster meldet
    post('/api/jarvis', { action: 'spoken', turn: it.turn, seq: it.seq });
  }

  /** Nach say_end: sobald von dieser Runde nichts mehr gesprochen wird oder wartet -> einmal "spoken". */
  function ttsDrain() {
    for (const [turn, key] of [...tts.ends]) {
      const pending = (tts.cur && tts.cur.it.turn === turn) || tts.queue.some((it) => it.turn === turn);
      if (pending) continue;
      tts.ends.delete(turn);
      if (tts.answered.has(key)) continue;
      tts.answered.add(key);
      if (!jv.open || jv.left) continue;
      if (iSpeak()) post('/api/jarvis', { action: 'spoken', turn });
      else lead.silent.add(turn); // meldet das vorlesende Fenster (faellt es weg: siehe leadClaim)
    }
  }

  /** Nach "not-allowed": beim naechsten Klick/Tastendruck im Jarvis-Modus wieder vorlesen. */
  function ttsUnblock() {
    if (!tts.blocked || !jv.open || !iSpeak()) return;
    tts.blocked = false;
    tts.fails = 0;
    ttsWarmup();
  }

  function onSay(ev) {
    if (jv.left || ended) return; // Nutzer hat Jarvis verlassen: bis "off" nichts mehr vorlesen
    const turn = Number(ev.turn) || 0;
    const text = String(ev.text == null ? '' : ev.text).trim();
    if (!jv.open) openJarvisView(false); // Jarvis laeuft (z.B. von woanders gestartet)
    if (turn && turn < tts.maxTurn) return; // veraltete Runde
    if (turn > tts.maxTurn) {
      // neue Runde: Reste der alten nicht mehr vorlesen
      const old = tts.queue.filter((it) => it.turn < turn);
      if (old.length) tts.queue = tts.queue.filter((it) => it.turn >= turn);
      if (tts.cur && tts.cur.it.turn < turn) { dropCur(); ttsCancelSynth(); }
      tts.maxTurn = turn;
      tts.followAt = 0;
    }
    if (!text) return;
    tts.queue.push({ turn, seq: Number(ev.seq) || 0, text, local: !!ev.local });
    ttsPump();
  }

  function onSayEnd(ev) {
    if (jv.left || ended || !jv.open) return;
    const turn = Number(ev.turn) || 0;
    if (turn && turn < tts.maxTurn) return; // veraltete Runde
    const key = turn + ':' + (Number(ev.count) || 0);
    if (tts.answered.has(key)) return; // dieses say_end ist schon beantwortet
    tts.ends.set(turn, key);
    ttsDrain();
  }

  function onHush() {
    if (jv.left || ended || !jv.open) return;
    ttsHush();
  }

  // =====================================================================
  // Jarvis-Modus: die grosse Sphaere – dieselbe wie ueberall (siehe "Novas Sphaere")
  // =====================================================================
  const orb = {
    start() { sphere.jarvis(byId('jv-orb'), true); sphere.cover(true); },
    stop() { sphere.jarvis(byId('jv-orb'), false); sphere.cover(false); },
    uncover() { sphere.cover(false); },
    setState() { moodSync(); },
    level(v) { sphere.level(v); },
    kick(s) { sphere.kick(s); },
    speaking(on) { sphere.talk('local', on); },
    flinch() { sphere.flinch(true); },
  };

  // =====================================================================
  // Jarvis-Modus: Ansicht und Ablauf
  // =====================================================================
  const JV_STATES = new Set(['listening', 'hearing', 'recognizing', 'thinking', 'speaking']);
  const JV_LABELS = {
    starting: 'Starte …', listening: 'Ich höre zu …', hearing: 'Ich höre dich …', recognizing: 'Verstehe …',
    thinking: 'Denke nach …', working: 'Arbeite …', speaking: 'Spreche …',
  };
  const youEl = byId('jv-you');
  const subsEl = byId('jv-subs');

  function jvLabelKey() { return jv.state === 'thinking' && jv.working ? 'working' : jv.state; }

  function renderJvState() {
    jvEl.dataset.state = jv.state;
    jvEl.classList.toggle('working', jv.working);
    const key = jvLabelKey();
    // Zwischen zwei Saetzen nicht flackern: "Spreche" kurz stehen lassen
    clearTimeout(jv.labelTimer);
    const set = () => { byId('jv-state-text').textContent = pick(JV_LABELS, key) || ''; jv.label = key; };
    if (jv.label === 'speaking' && (key === 'thinking' || key === 'listening')) jv.labelTimer = setTimeout(set, 650);
    else set();
  }

  function renderLive() {
    byId('jv-live').hidden = jv.live !== true;
    const setup = byId('jv-setup');
    setup.hidden = jv.live !== false;
    jvEl.classList.toggle('setup-on', !setup.hidden); // schmal: Hinweis darunter statt darueber
    if (jv.live === false) {
      setup.querySelector('.spinner').hidden = jv.setupFailed;
      byId('jv-setup-text').textContent = jv.setupFailed
        ? 'Ohne Live-Mitschrift – ich verstehe dich trotzdem.'
        : jv.setupText || 'Live-Mitschrift wird eingerichtet …';
    }
  }

  /** Fortschritt der Einrichtung (z.B. "Live-Mitschrift: 40 % geladen"). */
  function jvSetupInfo(text, level) {
    if (/bereit/i.test(text) && level !== 'warn') { jv.setupText = 'Live-Mitschrift ist bereit …'; jv.setupFailed = false; }
    else if (level === 'warn' || /nicht|ging nicht|fehl/i.test(text)) jv.setupFailed = true;
    else jv.setupText = text.length > 60 ? 'Live-Mitschrift wird eingerichtet …' : text.replace(/\s*geladen\s*$/i, ' geladen …');
    if (jv.open) renderLive();
  }

  function showNote(text, kind, ms) {
    const n = byId('jv-note');
    clearTimeout(jv.noteTimer);
    n.hidden = true;
    n.className = 'jv-note' + (kind ? ' ' + kind : '');
    n.textContent = text;
    void n.offsetWidth; // Animation neu starten (selten)
    n.hidden = false;
    jv.noteTimer = setTimeout(hideNote, ms || 4500);
  }
  function hideNote() { clearTimeout(jv.noteTimer); byId('jv-note').hidden = true; }

  // ---------- Live-Mitschrift (Woerter blenden weich ein) ----------
  function clearHeard() {
    clearTimeout(jv.heardTimer);
    youEl.replaceChildren();
    youEl.className = 'jv-you';
    jv.words = [];
    jv.heardFinal = false;
    jv.heardStale = false;
  }
  function renderHeard(text, final) {
    clearTimeout(jv.heardTimer);
    if (jv.heardStale || (jv.heardFinal && !final)) clearHeard(); // neue Aeusserung
    youEl.classList.remove('stale', 'gone');
    youEl.classList.toggle('partial', !final);
    jv.heardFinal = !!final;
    const words = text.split(/\s+/).filter(Boolean);
    const cur = jv.words;
    let i = 0;
    while (i < cur.length && i < words.length && cur[i].w === words[i]) i++;
    for (let k = cur.length - 1; k >= i; k--) {
      const el = cur[k].el;
      const sp = el.previousSibling;
      if (sp && sp.nodeType === 3) sp.remove();
      el.remove();
    }
    cur.length = i;
    for (let k = i; k < words.length; k++) {
      if (k > 0) youEl.append(' ');
      const el = h('span', 'w', words[k]);
      if (k > i) el.style.animationDelay = Math.min(260, (k - i) * 55) + 'ms';
      youEl.append(el);
      cur.push({ w: words[k], el });
    }
  }
  function fadeHeard() {
    jv.heardFinal = true;
    youEl.classList.add('gone');
    clearTimeout(jv.heardTimer);
    jv.heardTimer = setTimeout(clearHeard, 420);
  }
  function staleHeard() {
    if (!jv.words.length) return;
    youEl.classList.add('stale');
    jv.heardStale = true;
  }

  // ---------- Untertitel (gesprochener Satz gross, voriger klein) ----------
  function showSub(text) {
    if (!jv.open) return;
    clearTimeout(jv.subsTimer);
    subsEl.classList.remove('fading');
    for (const l of [...subsEl.children]) {
      if (l.classList.contains('out')) continue;
      if (l.classList.contains('prev')) {
        l.classList.add('out');
        setTimeout(() => l.remove(), 420);
      } else l.classList.add('prev');
    }
    subsEl.append(h('p', 'jv-line', text));
    jvEl.classList.add('has-subs');
  }
  function markSubCut() {
    const cur = subsEl.querySelector('.jv-line:not(.prev):not(.out)');
    if (cur) cur.classList.add('cut');
  }
  function fadeSubs() {
    if (!subsEl.childElementCount) { jvEl.classList.remove('has-subs'); return; }
    subsEl.classList.add('fading');
    clearTimeout(jv.subsTimer);
    jv.subsTimer = setTimeout(() => {
      subsEl.replaceChildren();
      subsEl.classList.remove('fading');
      jvEl.classList.remove('has-subs');
    }, 360);
  }
  function clearSubs() {
    clearTimeout(jv.subsTimer);
    subsEl.replaceChildren();
    subsEl.classList.remove('fading');
    jvEl.classList.remove('has-subs');
  }

  // ---------- Oeffnen / Schliessen ----------
  /** guess: Zustand, wenn Jarvis schon laeuft und das naechste Ereignis noch aussteht (z.B. "listening"). */
  function openJarvisView(starting, guess) {
    if (ended) return;
    clearTimeout(jv.leaveTimer);
    jvEl.classList.remove('leaving');
    if (jv.open) return;
    jv.open = true;
    jv.starting = !!starting;
    jv.openedAt = performance.now();
    jv.state = guess && JV_STATES.has(guess) ? guess : 'starting';
    jv.label = '';
    jv.working = false;
    jv.live = null;
    jv.setupFailed = false;
    jv.focusBack = document.activeElement;
    // laufende Aufnahme (F2/Mikrofon-Knopf) abbrechen – das Mikrofon gehoert jetzt Jarvis
    if (voice.phase === 'starting' || voice.phase === 'recording' || voice.phase === 'remote') voiceCancel(true);
    closeSidebar();
    closeCmdPop();
    ttsSession();
    leadElect(!!starting);
    clearHeard();
    clearSubs();
    hideNote();
    byId('jv-name').textContent = kiName();
    renderJvState();
    renderLive();
    jvEl.hidden = false;
    updateInert();
    updateDlgVoice();
    if (tour.open) tourPause(true);
    orb.setState(jv.state, false);
    orb.start();
    // ein offener Dialog darueber (Rueckfrage, Bestaetigung, AFK) behaelt den Fokus – danach kommt er zu Jarvis
    requestAnimationFrame(() => { if (jv.open && modal.hidden && cmodal.hidden && amodal.hidden) jvEl.focus(); });
  }

  function closeJarvisView() {
    if (!jv.open) return;
    jv.open = false;
    jv.starting = false;
    ttsStop();
    leadRelease();
    hideNote();
    clearTimeout(jv.labelTimer);
    jvEl.classList.add('leaving');
    orb.uncover();
    clearTimeout(jv.leaveTimer);
    jv.leaveTimer = setTimeout(() => {
      jvEl.hidden = true;
      jvEl.classList.remove('leaving');
      orb.stop();
      clearHeard();
      clearSubs();
    }, 230);
    updateInert();
    updateDlgVoice();
    moodSync();
    if (tour.open) tourPause(false);
    const back = jv.focusBack;
    jv.focusBack = null;
    if (!amodal.hidden && modal.hidden && cmodal.hidden) { // AFK-Dialog liegt obenauf: dort bleiben
      if (!amodal.contains(document.activeElement)) afkTask.focus();
    } else if (modal.hidden && cmodal.hidden && pmodal.hidden && smodal.hidden) {
      if (back && back !== document.body && document.contains(back) && !back.closest('[inert]') &&
          back.offsetParent !== null) back.focus();
      else focusInput();
    } else if (!smodal.hidden && modal.hidden) sdialog.focus();
    else if (!pmodal.hidden && modal.hidden) panel.focus();
  }

  /** Schliessen lokal: bis "off" kommt, gehoeren Ereignisse noch zur alten Sitzung und werden
   *  ignoriert (jv.left) – auch wenn das dauert (z.B. Umwandeln ohne Live-Mitschrift).
   *  Die 3 s (jv.closing) gelten nur dafuer, wie lange ein neuer Start auf "off" wartet. */
  function beginClosing() {
    jv.closing = true;
    jv.left = true;
    clearTimeout(jv.closeTimer);
    jv.closeTimer = setTimeout(endClosing, 3000);
  }
  function endClosing() {
    clearTimeout(jv.closeTimer);
    jv.closing = false;
    const w = jv.closeWaiters;
    jv.closeWaiters = [];
    for (const f of w) f();
  }
  function waitClosed() {
    if (!jv.closing) return Promise.resolve();
    return new Promise((resolve) => jv.closeWaiters.push(resolve));
  }

  async function startJarvis() {
    if (ended) return;
    if (jv.open) { jvEl.focus(); return; }
    if (jv.closing) await waitClosed(); // alte Sitzung erst ganz beenden
    if (ended || jv.open) return;
    jv.left = false; // neue Sitzung
    openJarvisView(true);
    ttsWarmup(); // nach dem Zuruecksetzen der Warteschlange (das wuerde sie sonst gleich abbrechen)
    jv.cancelStart = false;
    const r = await post('/api/jarvis', { action: 'start', tts: 'client', progress: true });
    const cancelled = jv.cancelStart;
    jv.cancelStart = false;
    jv.starting = false;
    if (cancelled) {
      // schon wieder "Chat-Modus" gedrueckt, waehrend der Start lief
      if (r.ok) { beginClosing(); post('/api/jarvis', { action: 'stop' }); }
      return;
    }
    if (!r.ok) {
      closeJarvisView();
      if (r.setup) voiceFailed(r);
      else toast(r.error || 'Der Jarvis-Modus konnte nicht starten.', 'error', 5000);
      return;
    }
    if (jv.live === null) jv.live = !!r.live;
    renderLive();
  }

  /** Esc, Knopf "Chat-Modus" oder X: zurueck zum Chat. */
  function chatMode() {
    if (!jv.open) return;
    const wasStarting = jv.starting;
    closeJarvisView();
    if (wasStarting) { jv.cancelStart = true; return; }
    beginClosing();
    post('/api/jarvis', { action: 'stop' }).then((r) => {
      if (r.ok) return;
      // Jarvis laeuft weiter: seine Ereignisse wieder zeigen (die Ansicht oeffnet sich dann erneut)
      jv.left = false;
      endClosing();
      toast(r.error || 'Der Jarvis-Modus ließ sich nicht beenden.', 'error');
    });
  }

  /** Knopf "Stopp": Nova hoert auf zu reden und die Antwort wird angehalten. */
  function jvHush() {
    if (!jv.open) return;
    ttsHush();
    orb.kick(0.6);
    post('/api/jarvis', { action: 'hush' });
  }

  function onJarvisEvent(ev) {
    const st = String(ev.state || '');
    if (st === 'off') {
      jv.left = false;
      endClosing();
      if (jv.open) closeJarvisView();
      else ttsStop();
      if (ev.error) addError(String(ev.error));
      return;
    }
    if (jv.left || ended || !JV_STATES.has(st)) return; // verlassen: spaete Ereignisse bis "off" ignorieren
    if (!jv.open) openJarvisView(false, st); // z.B. serverseitig gestartet
    const prev = jv.state;
    jv.state = st;
    jv.working = st === 'thinking' && !!ev.working;
    if (st === 'hearing' && prev !== 'hearing') { staleHeard(); fadeSubs(); }
    if (st === 'thinking' && ev.text) { renderHeard(String(ev.text), true); if (prev !== 'speaking') fadeSubs(); }
    if (ev.interrupted) { orb.flinch(); showNote('Unterbrochen – ich höre dir zu.', 'soft', 1800); }
    if (ev.error) {
      const err = String(ev.error);
      if (/Live-Mitschrift/i.test(err)) { jv.live = false; jv.setupFailed = true; renderLive(); }
      showNote(err, '', 6000);
    }
    renderJvState();
    orb.setState(st, jv.working);
  }

  function onHeard(ev) {
    if (!jv.open || jv.left) return;
    const text = String(ev.text == null ? '' : ev.text).trim();
    if (!ev.final) {
      if (jv.live !== true) { jv.live = true; jv.setupFailed = false; renderLive(); }
      if (text) renderHeard(text, false);
    } else if (!text) fadeHeard();
    else renderHeard(text, true);
  }

  /** Hinweis im Rueckfrage-Dialog: im Jarvis-Modus kann man antworten, indem man spricht. */
  function updateDlgVoice() { byId('dlg-voice').hidden = !jv.open; }

  function jarvisKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); chatMode(); return; }
    if (e.key === 'F2') { e.preventDefault(); return; }
    if (e.key === 'Tab') trapTab(e, jvEl);
  }

  byId('tb-jarvis').addEventListener('click', () => startJarvis());
  byId('jv-chat').addEventListener('click', chatMode);
  byId('jv-close').addEventListener('click', chatMode);
  byId('jv-stop').addEventListener('click', jvHush);
  // Klick/Taste im Jarvis-Modus (auch im Rueckfrage-Dialog darueber): blockiertes Vorlesen wieder erlauben
  const jvGesture = () => { if (jv.open) ttsUnblock(); };
  document.addEventListener('pointerdown', jvGesture, true);
  document.addEventListener('keydown', jvGesture, true);
  window.addEventListener('pagehide', () => {
    const mine = iSpeak() || !!tts.cur;
    leadRelease(); // ein anderes Fenster liest weiter vor
    if (synth && mine) { try { synth.cancel(); } catch (_) { /* egal */ } }
  });
  // aus dem Zwischenspeicher des Browsers zurueck: neu klaeren, wer vorliest
  window.addEventListener('pageshow', (e) => { if (e.persisted && jv.open) leadElect(false); });

  // =====================================================================
  // Tour: Nova zeigt alles (Spotlight auf Elemente mit data-tour)
  // =====================================================================
  const tourCard = byId('tour-card');
  const tourTextEl = byId('tour-text');
  const tourSpot = byId('tour-spot');
  const tourDim = byId('tour-dim');
  const TOUR_TARGETS = new Set(['eingabe', 'mikrofon', 'jarvis', 'profil', 'stuetzraeder']);
  let tourLater = false;
  try { tourLater = sessionStorage.getItem('ki-tour-spaeter') === '1'; } catch (_) { /* egal */ }
  const isDrawer = () => window.matchMedia('(max-width: 800px)').matches;

  async function startTour() {
    if (ended) return;
    if (tour.open) { if (!tour.paused) focusTour(); return; }
    if (tour.loading) return;
    tour.loading = true;
    const d = await getJson('/api/tutorial');
    tour.loading = false;
    const steps = d && Array.isArray(d.steps) ? d.steps.filter((s) => s && typeof s === 'object').map((s) => ({
      titel: str(s.titel).trim(),
      text: str(s.text).trim(),
      ziel: tourZiel(s.ziel),
      zeigen: str(s.zeigen).trim(),
    })).filter((s) => s.titel || s.text) : [];
    if (!steps.length) { toast('Die Tour konnte nicht geladen werden.', 'error'); return; }
    if (ended || tour.open) return;
    closeCmdPop();
    tour.steps = steps;
    tour.open = true;
    tour.paused = jv.open;
    tour.doneSent = false;
    tour.sbOpened = false;
    tourEl.hidden = tour.paused;
    tourCard.classList.add('no-anim');
    updateInert();
    updateEmpty();
    window.addEventListener('resize', tourResize);
    document.addEventListener('scroll', tourReflow, true);
    tourStep(0);
  }

  /** Ziel-Name pruefen; der Server schreibt manchmal Umlaute hinein ("stützräder"). */
  function tourZiel(z) {
    const v = str(z).trim().toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
    return TOUR_TARGETS.has(v) ? v : '';
  }

  function tourTarget(ziel) {
    if (!ziel) return null;
    for (const el of document.querySelectorAll('[data-tour]')) if (el.dataset.tour === ziel) return el;
    return null;
  }

  function tourStep(i) {
    tour.i = clamp(i, 0, tour.steps.length - 1);
    tour.demo = false;
    tour.waiting = false;
    clearTimeout(tour.waitTimer);
    const st = tour.steps[tour.i];
    const target = tourTarget(st.ziel);
    // Ziel beobachten: waechst es (z.B. Eingabefeld beim Tippen), wandert das Spotlight mit
    if (tourRO && tour.target !== target) {
      if (tour.target) tourRO.unobserve(tour.target);
      if (target) tourRO.observe(target);
    }
    tour.target = target;
    const inSidebar = !!target && byId('sidebar').contains(target);
    if (inSidebar && isDrawer()) {
      if (!app.classList.contains('sb-open')) { openSidebar(true); tour.sbOpened = true; }
    } else if (tour.sbOpened) { closeSidebar(); tour.sbOpened = false; }
    if (inSidebar) target.scrollIntoView({ block: 'nearest' });
    if (target) {
      const r = parseFloat(getComputedStyle(target).borderTopLeftRadius) || 10;
      tourSpot.style.borderRadius = Math.min(28, r + 6) + 'px';
    }
    tourCard.style.maxWidth = ''; // evtl. schmaler gemachte Karte (tourPlace) zuruecksetzen
    renderTour();
    tourTextEl.scrollTop = 0;
    tourCard.classList.remove('fresh');
    void tourCard.offsetWidth; // Einblende-Animation neu starten (einmal pro Schritt)
    tourCard.classList.add('fresh');
    tourFollow(520);
    requestAnimationFrame(focusTour);
  }

  function focusTour() {
    if (!tour.open || tour.paused) return;
    const next = byId('tour-next');
    if (!next.disabled) next.focus();
    else tourCard.focus();
  }

  function renderTour() {
    const st = tour.steps[tour.i];
    const n = tour.steps.length;
    const last = tour.i === n - 1;
    byId('tour-step').textContent = 'Schritt ' + (tour.i + 1) + ' von ' + n;
    byId('tour-bar').style.setProperty('--p', String((tour.i + 1) / n));
    byId('tour-title').textContent = st.titel;
    byId('tour-text').textContent = st.text;
    byId('tour-back').hidden = tour.i === 0;
    const show = byId('tour-show');
    show.hidden = !st.zeigen;
    show.disabled = tour.waiting;
    const next = byId('tour-next');
    next.textContent = last ? 'Fertig' : 'Weiter';
    next.disabled = tour.waiting;
    next.title = tour.waiting ? 'Geht weiter, sobald ' + kiName() + ' fertig ist' : '';
    byId('tour-end').hidden = last;
    byId('tour-back').classList.toggle('ghost', tour.demo);
    const wait = byId('tour-wait');
    wait.hidden = !tour.demo;
    if (tour.demo) {
      wait.classList.toggle('done', !tour.waiting);
      wait.replaceChildren(tour.waiting ? h('span', 'spinner') : icon('checkCircle'),
        h('span', null, tour.waiting ? kiName() + ' führt es dir gerade vor …' : 'Vorgeführt – das Ergebnis steht im Chat.'));
    }
    tourCard.classList.toggle('demo', tour.demo);
  }

  let tourQueued = false;
  function tourResize() { tourCard.style.maxWidth = ''; tourReflow(); }
  function tourReflow() {
    if (tourQueued || !tour.open) return;
    tourQueued = true;
    requestAnimationFrame(() => { tourQueued = false; tourPlace(); tourTextFade(); });
  }
  /** Wird der Text gescrollt (wenig Platz), zeigt ein weicher Rand unten: da kommt noch mehr. */
  function tourTextFade() {
    const t = tourTextEl;
    t.classList.toggle('more', t.scrollHeight - t.scrollTop - t.clientHeight > 2);
  }
  tourTextEl.addEventListener('scroll', tourTextFade, { passive: true });
  /** Eine Weile jedem Bild folgen (z.B. waehrend die Seitenleiste hereingleitet). */
  function tourFollow(ms) {
    const until = performance.now() + ms;
    cancelAnimationFrame(tour.follow);
    const step = () => {
      tourPlace();
      if (performance.now() < until && tour.open) tour.follow = requestAnimationFrame(step);
      else tourTextFade();
    };
    tour.follow = requestAnimationFrame(step);
  }

  function tourPlace() {
    if (!tour.open || tour.paused) return;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const narrow = vw <= 600;
    const M = narrow ? 10 : 14;
    // erst alles lesen, dann schreiben (kein Layout-Hin-und-Her)
    let rect = null;
    const t = tour.demo ? null : tour.target;
    if (t && t.isConnected && !t.closest('[hidden]')) {
      const r = t.getBoundingClientRect();
      if (r.width && r.height && r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw) rect = r;
    }
    if (tour.demo && tourCard.style.maxWidth) tourCard.style.maxWidth = '';
    let cw = tourCard.offsetWidth;
    // volle Hoehe der Karte – auch wenn sie gerade begrenzt ist (dann scrollt nur der Text)
    const full = tourCard.offsetHeight - tourTextEl.clientHeight + tourTextEl.scrollHeight;
    const pad = 6;
    const gap = pad + 14;
    let maxH = vh - 2 * M;
    let x;
    let y;
    if (tour.demo) {
      // zur Seite ruecken, damit man Nova bei der Arbeit sieht
      x = narrow ? (vw - cw) / 2 : vw - cw - 20;
      y = narrow ? 62 : 70;
    } else if (rect) {
      const inSb = byId('sidebar').contains(t);
      const side = vw - M - (rect.right + pad + 18); // Platz rechts neben der Seitenleiste
      const below = vh - M - (rect.bottom + gap);
      const above = rect.top - gap - M;
      const fitsV = full <= below || full <= above;
      if (inSb && !narrow && (cw <= side || (!fitsV && side >= 300))) {
        // neben die Seitenleiste – notfalls etwas schmaler (grosse Schrift, niedriges Fenster);
        // die Grenze bleibt fuer diesen Schritt (tourStep/Groessenaenderung nehmen sie zurueck)
        if (cw > side) { tourCard.style.maxWidth = Math.floor(side) + 'px'; cw = Math.floor(side); }
        x = rect.right + pad + 18;
        y = rect.top + rect.height / 2 - Math.min(full, maxH) / 2;
      } else {
        x = rect.left + rect.width / 2 - cw / 2;
        if (full <= below) y = rect.bottom + gap;
        else if (full <= above) y = rect.top - gap - full;
        else if (above >= below) {
          // passt weder darueber noch darunter: auf die groessere Seite, Text scrollt – nie ueber das Ziel
          maxH = Math.max(150, above);
          y = rect.top - gap - Math.min(full, maxH);
        } else {
          maxH = Math.max(150, below);
          y = rect.bottom + gap;
        }
      }
    } else {
      x = (vw - cw) / 2;
      y = narrow ? vh - Math.min(full, maxH) - M : (vh - Math.min(full, maxH)) / 2;
    }
    maxH = Math.max(120, Math.round(maxH));
    const ch = Math.min(full, maxH);
    x = clamp(x, M, Math.max(M, vw - cw - M));
    y = clamp(y, M, Math.max(M, vh - ch - M));
    if (tourCard.style.maxHeight !== maxH + 'px') tourCard.style.maxHeight = maxH + 'px';
    tourSpot.hidden = !rect;
    tourDim.hidden = !!rect || tour.demo;
    if (rect) {
      tourSpot.style.transform = 'translate(' + Math.round(rect.left - pad) + 'px,' + Math.round(rect.top - pad) + 'px)';
      tourSpot.style.width = Math.round(rect.width + pad * 2) + 'px';
      tourSpot.style.height = Math.round(rect.height + pad * 2) + 'px';
    }
    tourCard.style.transform = 'translate(' + Math.round(x) + 'px,' + Math.round(y) + 'px)';
    if (tourCard.classList.contains('no-anim')) requestAnimationFrame(() => tourCard.classList.remove('no-anim'));
  }
  // Karte (Text, Schriftgroesse) und das aktuelle Ziel beobachten
  const tourRO = window.ResizeObserver ? new ResizeObserver(tourReflow) : null;
  if (tourRO) { tourRO.observe(tourCard); tourRO.observe(tourTextEl); }

  function tourNext() {
    if (!tour.open || tour.waiting) return;
    if (tour.i >= tour.steps.length - 1) endTour(true);
    else tourStep(tour.i + 1);
  }
  function tourBack() { if (tour.open && tour.i > 0) tourStep(tour.i - 1); }

  /** "Zeig es mir": den Auftrag wirklich an Nova schicken. */
  async function tourShow() {
    const st = tour.steps[tour.i];
    if (!tour.open || !st || !st.zeigen || tour.waiting) return;
    if (busy) { toast('Moment – ich bin noch mit der letzten Antwort beschäftigt.'); return; }
    const idx = tour.i;
    tour.demo = true;
    tour.waiting = true;
    tour.sawBusy = false;
    renderTour();
    tourFollow(450);
    const ok = await send(st.zeigen);
    if (!tour.open || tour.i !== idx) return;
    if (!ok) { tour.demo = false; tour.waiting = false; renderTour(); tourFollow(450); return; }
    // Faellt "busy" nie (sehr schnelle Antwort), nicht ewig warten
    clearTimeout(tour.waitTimer);
    tour.waitTimer = setTimeout(() => { if (tour.waiting && !tour.sawBusy && !busy) tourDemoDone(); }, 8000);
  }
  function tourDemoDone() {
    clearTimeout(tour.waitTimer);
    tour.waiting = false;
    renderTour();
    tourReflow();
    if (document.activeElement === document.body || tourCard.contains(document.activeElement)) focusTour();
  }
  /** Aus setBusy: die vorgefuehrte Antwort ist fertig. */
  function tourBusy(b) {
    if (!tour.open || !tour.waiting) return;
    if (b) tour.sawBusy = true;
    else if (tour.sawBusy) tourDemoDone();
  }

  function tourPause(p) {
    if (!tour.open) return;
    tour.paused = p;
    tourEl.hidden = p;
    updateInert();
    if (!p) { tourFollow(300); requestAnimationFrame(focusTour); }
  }

  /** Tour schliessen; markDone: dem Server melden, dass sie erledigt ist. */
  function endTour(finished, markDone = true) {
    if (!tour.open) return;
    tour.open = false;
    tour.paused = false;
    tour.waiting = false;
    clearTimeout(tour.waitTimer);
    cancelAnimationFrame(tour.follow);
    tourEl.hidden = true;
    tourSpot.hidden = true;
    if (tourRO && tour.target) tourRO.unobserve(tour.target);
    tour.target = null;
    window.removeEventListener('resize', tourResize);
    document.removeEventListener('scroll', tourReflow, true);
    if (tour.sbOpened) { closeSidebar(); tour.sbOpened = false; }
    updateInert();
    if (markDone && !tour.doneSent) {
      tour.doneSent = true;
      state.tutorial_done = true;
      post('/api/tutorial', { action: 'done' });
    }
    updateEmpty();
    if (finished) toast('Viel Spaß mit ' + kiName() + '! Die Tour findest du jederzeit in der Seitenleiste.', 'ok', 4500);
    if (tourCard.contains(document.activeElement) || document.activeElement === document.body) focusInput();
  }

  byId('tour-next').addEventListener('click', tourNext);
  byId('tour-back').addEventListener('click', tourBack);
  byId('tour-show').addEventListener('click', tourShow);
  byId('tour-end').addEventListener('click', () => endTour(false));
  byId('tour-start').addEventListener('click', () => startTour());
  byId('sb-tour').addEventListener('click', () => { closeSidebar(); startTour(); });
  byId('tour-later').addEventListener('click', () => {
    tourLater = true;
    try { sessionStorage.setItem('ki-tour-spaeter', '1'); } catch (_) { /* egal */ }
    updateEmpty();
    toast('Die Tour findest du jederzeit in der Seitenleiste.');
    focusInput();
  });
  tourCard.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'BUTTON' && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      e.preventDefault();
      if (e.key === 'ArrowRight') tourNext(); else tourBack();
    }
  });

  // =====================================================================
  // Gehirn & Schluessel – Einrichtung in der App (eigenes Fenster und Reiter "Gehirn")
  // Der Schluessel geht NUR an /api/setup: nie in den Chat, nie in localStorage, nie
  // ins Protokoll. Nach dem Speichern (und beim Schliessen) wird das Feld geleert.
  // =====================================================================
  const smodal = byId('smodal');
  const sdialog = byId('sdialog');
  const setupEl = byId('setup');
  const suInput = byId('su-input');
  const suGo = byId('su-go');
  const SU_FALLBACK = [
    { id: 'deepseek', name: 'DeepSeek', info: 'sehr günstig, gut für jeden Tag', url: 'https://platform.deepseek.com/api_keys' },
    { id: 'claude', name: 'Claude (Anthropic)', info: 'sehr stark, teurer', url: 'https://console.anthropic.com/settings/keys' },
  ];
  const SU_TOPUP = { deepseek: 'https://platform.deepseek.com/top_up', claude: 'https://console.anthropic.com/settings/billing' };
  const SU_ICON = { deepseek: 'zap', claude: 'sparkles' };
  const su = {
    where: '',          // '' | 'modal' | 'pane'
    welcome: false, data: null, sel: '', loading: false, gen: 0, reqGen: 0, checking: false, result: null,
    note: '', closeTimer: 0, focusBack: null, autoShown: false, lastProv: null, lastMissing: null, lastModel: null,
    jump: '',           // 'modell' = nach dem Laden zum Bereich "Modell & Denk-Tiefe" springen
    openedAt: 0,        // wann das Fenster aufging (Doppelklick auf den Ausloeser schliesst es nicht gleich)
    refreshTimer: 0, pointer: false,
  };
  const suShort = (p) => String(p && p.name ? p.name : p || '').replace(/\s*\(.*\)\s*$/, '') || 'KI';
  const suSel = () => (su.data ? su.data.providers.find((p) => p.id === su.sel) || null : null);
  const suVisible = () => (su.where === 'modal' && !smodal.hidden) ||
    (su.where === 'pane' && !pmodal.hidden && profTab === 'gehirn');

  function normSetup(d) {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const list = (Array.isArray(d.providers) ? d.providers : []).filter((p) => p && typeof p === 'object').map((p) => {
      const id = str(p.id).trim().toLowerCase();
      const fb = SU_FALLBACK.find((x) => x.id === id);
      const url = str(p.url).trim();
      return {
        id,
        name: str(p.name).trim().slice(0, 60) || (fb ? fb.name : id),
        info: str(p.info).trim().slice(0, 120) || (fb ? fb.info : ''),
        url: /^https:\/\/[^\s"'<>\\]+$/.test(url) ? url : fb ? fb.url : '',
        hasKey: p.has_key === true,
        hint: str(p.key_hint).trim().slice(0, 40),
        modelName: str(p.model_name).trim().slice(0, 80),
      };
    }).filter((p) => /^[a-z0-9_-]{1,30}$/.test(p.id));
    if (!list.length) return null;
    return {
      provider: str(d.provider).trim().toLowerCase(), providers: list, missing: d.key_missing === true,
      modelle: normModelle(d.modelle, list.map((p) => p.id)),
    };
  }

  /** "modelle" aus /api/setup: je Gehirn {model, denken, models:[{id,name,info,tempo,preis}], depths:[{id,name,info}]}.
      Fehlt es (aeltere KI), bleibt der Bereich "Modell & Denk-Tiefe" einfach weg. */
  function normModelle(raw, ids) {
    const out = Object.create(null);
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out;
    const items = (arr, keys) => {
      const seen = new Set();
      return (Array.isArray(arr) ? arr : []).filter((x) => x && typeof x === 'object').map((x) => {
        const o = { id: str(x.id).trim() };
        for (const k of keys) o[k] = str(x[k]).trim().slice(0, 140);
        if (!o.name) o.name = o.id;
        return o;
      }).filter((o) => /^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$/.test(o.id) && !seen.has(o.id) && seen.add(o.id)).slice(0, 12);
    };
    for (const id of ids) {
      const g = pick(raw, id);
      if (!g || typeof g !== 'object' || Array.isArray(g)) continue;
      const models = items(g.modelle, ['name', 'info', 'tempo', 'preis']);
      const depths = items(g.denktiefen, ['name', 'info']);
      if (models.length || depths.length) out[id] = { model: str(g.model).trim(), denken: str(g.denken).trim(), models, depths };
    }
    return out;
  }

  /** Ohne Antwort vom Server: die beiden bekannten Gehirne (aus dem Zustand). */
  function fallbackSetup() {
    const cur = String(state.provider || '').toLowerCase() === 'deepseek' ? 'deepseek' : 'claude';
    return {
      provider: cur,
      providers: SU_FALLBACK.map((p) => Object.assign({}, p, { hasKey: p.id === cur && state.api_key_missing === false, hint: '' })),
      missing: state.api_key_missing === true,
    };
  }

  function suDefaultSel() {
    const d = su.data;
    if (!d) return '';
    const cur = d.providers.find((p) => p.id === d.provider);
    if (cur && cur.hasKey) return cur.id;
    const withKey = d.providers.find((p) => p.hasKey);
    if (withKey) return withKey.id;
    return (d.providers.find((p) => p.id === 'deepseek') || cur || d.providers[0]).id; // empfohlen
  }

  // ---------- Oeffnen / Schliessen ----------
  /** jump 'modell': gleich beim Bereich "Modell & Denk-Tiefe" des aktiven Gehirns oeffnen. */
  function openSetup(welcome, jump) {
    closeSidebar();
    closeCmdPop();
    if (ended) return;
    su.jump = jump === 'modell' && !welcome ? 'modell' : '';
    const active = String(state.provider || '').toLowerCase();
    if (!pmodal.hidden) { // Profil-Fenster offen: dort der Reiter
      if (su.jump && !su.checking) su.sel = active;
      showTab('gehirn', !su.jump);
      return;
    }
    if (!smodal.hidden) { suFocus(); return; }
    su.focusBack = document.activeElement;
    su.welcome = !!welcome;
    su.result = null;
    su.note = '';
    su.sel = su.jump ? active : '';
    clearTimeout(su.closeTimer);
    mountSetup('modal');
    smodal.hidden = false;
    su.openedAt = performance.now();
    updateInert();
    loadSetup();
    moodSync();
    requestAnimationFrame(suFocus);
  }

  function closeSetup() {
    if (smodal.hidden) return;
    clearTimeout(su.closeTimer);
    clearKey();
    smodal.hidden = true;
    su.where = '';
    su.result = null;
    updateInert();
    moodSync();
    const back = su.focusBack;
    su.focusBack = null;
    if (!modal.hidden || !cmodal.hidden) return;
    if (jv.open) { jvEl.focus(); return; }
    if (back && back !== document.body && document.contains(back) && !back.closest('[inert]')) back.focus();
    if (document.activeElement !== back) focusInput();
  }

  /** Schluessel aus dem Feld nehmen (nach dem Speichern, beim Schliessen). */
  function clearKey() {
    suInput.value = '';
    showKey(false);
    su.note = '';
  }

  function suFocus() {
    if (!suVisible()) return;
    if (su.jump) { // springen erst mit dem frischen Stand (sonst nach dem Laden); bis dahin im Fenster
      if (su.data && !su.loading) suJump();
      else if (su.where === 'modal' && !sdialog.contains(document.activeElement)) sdialog.focus();
      return;
    }
    const ae = document.activeElement;
    if (ae && ae !== sdialog && setupEl.contains(ae)) return; // schon drin (z.B. nach dem Sprung)
    const p = suSel();
    if (su.where === 'modal' && (!p || !p.hasKey || su.welcome)) suInput.focus();
    else if (su.where === 'modal') sdialog.focus();
  }

  function mountSetup(where) {
    const host = where === 'pane' ? byId('pane-gehirn') : sdialog;
    if (setupEl.parentElement !== host) host.append(setupEl);
    su.where = where;
    if (where === 'pane') su.welcome = false;
    setupEl.classList.toggle('in-pane', where === 'pane');
    renderSetup();
  }

  async function loadSetup() {
    const gen = ++su.gen;
    su.loading = true; // (auch mit alten Daten: ein Sprung zum Modell wartet auf den frischen Stand)
    if (!su.data) renderSetup();
    const d = normSetup(await getJson('/api/setup'));
    if (gen !== su.gen) return;
    su.loading = false;
    su.data = d || su.data || fallbackSetup();
    if (!su.sel || !su.data.providers.some((p) => p.id === su.sel)) su.sel = suDefaultSel();
    renderSetup();
    if (su.jump) suJump();
  }

  /** Aus applyState: beim ersten Start ohne Schluessel begruessen; offenes Fenster aktuell halten
      (auch wenn das Modell anderswo gewechselt wurde, z.B. per /modell im Chat). */
  function setupState(prov, missing, modelSig) {
    const changed = su.lastProv !== null &&
      (su.lastProv !== prov || su.lastMissing !== missing || su.lastModel !== modelSig);
    su.lastProv = prov;
    su.lastMissing = missing;
    su.lastModel = modelSig;
    if (changed && suVisible() && !su.checking) loadSetup();
    // Auch das NICHT aktive Gehirn kann anderswo geaendert worden sein (anderes Fenster) – das sieht
    // man am Zustand nicht: offenes Fenster nach jedem Zustand kurz darauf frisch laden.
    else if (suVisible()) suRefreshSoon();
    if (missing && !su.autoShown && !ended) {
      su.autoShown = true;
      setTimeout(() => {
        const free = modal.hidden && cmodal.hidden && pmodal.hidden && smodal.hidden && !jv.open && !tour.open;
        if (free && !ended && state.api_key_missing === true) openSetup(true);
      }, 300);
    }
  }

  /** Offenes Fenster frisch laden – aber nicht mitten in einem Klick, waehrend geprueft wird oder
      eine eigene Modell-Wahl unterwegs ist (deren Antwort bringt den Stand ohnehin mit). */
  function suRefreshSoon(ms) {
    clearTimeout(su.refreshTimer);
    su.refreshTimer = setTimeout(() => {
      if (!suVisible() || su.checking || ended) return;
      if (su.pointer || Object.keys(sm.busy).length || Object.keys(sm.timer).length) { suRefreshSoon(400); return; }
      loadSetup();
    }, ms == null ? 450 : ms);
  }
  setupEl.addEventListener('pointerdown', () => { su.pointer = true; });
  for (const t of ['pointerup', 'pointercancel']) window.addEventListener(t, () => { su.pointer = false; }, true);
  // zurueck in dieses Fenster (z.B. nach einer Aenderung im anderen): Stand auffrischen
  window.addEventListener('focus', () => { if (suVisible()) suRefreshSoon(0); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && suVisible()) suRefreshSoon(0); });

  // ---------- Darstellen ----------
  function renderSetup() {
    const n = kiName();
    const d = su.data;
    const pane = su.where === 'pane';
    setupEl.classList.toggle('welcome', su.welcome);
    byId('su-hero').hidden = !su.welcome;
    byId('su-ic').hidden = su.welcome;
    byId('su-title').textContent = su.welcome ? 'Hallo! Ich bin ' + n + '.' : 'Gehirn & Schlüssel';
    byId('su-sub').textContent = su.welcome
      ? 'Damit ich denken kann, brauche ich einen Schlüssel für mein Gehirn. Das dauert nur eine Minute.'
      : 'Womit ' + n + ' denkt – und der passende Schlüssel dafür.';
    byId('su-close').hidden = pane;
    byId('su-later').hidden = pane;
    byId('su-loading').hidden = !(su.loading && !d);
    if (d && !su.sel) su.sel = suDefaultSel();
    const box = byId('su-provs');
    const ae = document.activeElement;
    const focusId = ae && box.contains(ae) ? ae.dataset.id : '';
    box.replaceChildren();
    if (d) for (const p of d.providers) box.append(suCard(p, d));
    if (focusId) {
      const card = [...box.children].find((c) => c.dataset.id === focusId);
      if (card) card.focus({ preventScroll: true });
    }
    const p = suSel();
    const where = byId('su-where');
    where.hidden = !p || !p.url;
    if (p && p.url) {
      where.href = p.url;
      where.title = 'Öffnet die Seite von ' + suShort(p) + ' im Browser';
    }
    suInput.readOnly = su.checking;
    renderModel();
    renderSteps(p);
    renderSuHint();
    renderSuGo();
    renderSuResult();
  }

  function suCard(p, d) {
    const on = p.id === su.sel;
    const b = h('button', 'su-prov sp-' + p.id + (on ? ' selected' : ''));
    b.type = 'button';
    b.setAttribute('role', 'radio');
    b.setAttribute('aria-checked', on ? 'true' : 'false');
    b.tabIndex = on ? 0 : -1;
    b.disabled = su.checking;
    b.dataset.id = p.id;
    const ic = h('span', 'sp-ic');
    ic.append(icon(pick(SU_ICON, p.id) || 'sparkles'));
    const main = h('span', 'sp-main');
    const top = h('span', 'sp-top');
    top.append(h('span', 'sp-name', p.name));
    if (p.id === 'deepseek') top.append(h('span', 'sp-badge rec', 'Empfohlen'));
    if (p.id === d.provider) top.append(h('span', 'sp-badge now', 'aktiv'));
    main.append(top);
    if (p.info) main.append(h('span', 'sp-info', p.info));
    const mName = smShownName(p);
    if (mName) {
      const m = h('span', 'sp-model');
      m.append(icon('cpu'), h('span', null, mName));
      main.append(m);
    }
    const k = h('span', 'sp-key' + (p.hasKey ? ' ok' : ''));
    k.append(icon(p.hasKey ? 'checkCircle' : 'key'),
      h('span', null, p.hasKey ? 'Schlüssel gespeichert' : 'noch kein Schlüssel'));
    if (p.hasKey && p.hint) k.append(h('span', 'sp-hint', '(' + p.hint + ')'));
    main.append(k);
    const chk = h('span', 'sp-check');
    chk.append(icon('check'));
    b.append(ic, main, chk);
    b.addEventListener('click', () => suPick(p.id, false));
    return b;
  }

  function suPick(id, keyboard) {
    if (su.checking || id === su.sel) return;
    su.sel = id;
    su.note = '';
    su.result = null;
    renderSetup();
    if (keyboard) {
      const card = [...byId('su-provs').children].find((c) => c.dataset.id === id);
      if (card) card.focus();
    }
  }
  byId('su-provs').addEventListener('keydown', (e) => arrowRadio(e, byId('su-provs'), (b) => suPick(b.dataset.id, true)));

  // ---------- Modell & Denk-Tiefe (je Gehirn; speichert sofort ueber /api/modell) ----------
  // Gezeigt wird der Bereich fuer das oben ausgewaehlte Gehirn. Ist es nicht das aktive, ist er
  // leicht abgeschwaecht: die Auswahl gilt, sobald dieses Gehirn benutzt wird.
  const sm = {
    want: Object.create(null),   // Gehirn -> {model, denken}: gewaehlt, aber noch nicht bestaetigt
    busy: Object.create(null),   // Gehirn -> true, solange eine Anfrage laeuft
    timer: Object.create(null),  // Gehirn -> Verzoegerung (Pfeiltasten: erst speichern, wenn man stehen bleibt)
    toastEl: null,               // letzte Meldung "Eingestellt: …" (eine neue ersetzt sie)
  };
  function smToast(text, kind, ms) {
    if (sm.toastEl) sm.toastEl.remove();
    toast(text, kind, ms);
    sm.toastEl = byId('toasts').lastElementChild;
  }
  const smGroup = (pid) => (su.data && su.data.modelle ? pick(su.data.modelle, pid) || null : null);
  /** Was gerade gewaehlt ist (die noch nicht bestaetigte Auswahl hat Vorrang). */
  function smCur(pid) {
    const g = smGroup(pid);
    const w = pick(sm.want, pid);
    return { model: w ? w.model : g ? g.model : '', denken: w ? w.denken : g ? g.denken : '' };
  }
  const smFind = (list, id) => list.find((x) => x.id === id) || null;
  /** Anzeige-Name fuer die Gehirn-Karte, z.B. "Claude Sonnet 5.5 - schnell". */
  function smShownName(p) {
    const g = smGroup(p.id);
    if (!g || !pick(sm.want, p.id)) return p.modelName;
    const c = smCur(p.id);
    const m = smFind(g.models, c.model);
    const t = smFind(g.depths, c.denken);
    return (m ? m.name : c.model) + (t ? ' - ' + t.name : '');
  }

  function renderModel() {
    const sec = byId('su-model');
    const body = byId('su-body');
    // Reihenfolge: normal gleich nach der Gehirn-Wahl; bei der Begruessung zuerst der Schluessel
    const before = su.welcome ? null : body.querySelector('.su-key');
    if (before ? sec.nextElementSibling !== before : body.lastElementChild !== sec) body.insertBefore(sec, before);
    const p = suSel();
    const g = p ? smGroup(p.id) : null;
    sec.hidden = !g;
    byId('su-input-label').textContent = (g && !su.welcome ? '3' : '2') + '. Schlüssel einfügen';
    byId('su-model-label').textContent = (su.welcome ? '3' : '2') + '. Modell & Denk-Tiefe';
    if (!g) return;
    const ae = document.activeElement;
    const focusKey = ae && sec.contains(ae) ? ae.dataset.sm || '' : '';
    const name = suShort(p);
    const active = p.id === su.data.provider;
    sec.classList.toggle('inactive', !active);
    sec.dataset.provider = p.id;
    byId('sm-for').textContent = active ? 'für ' + name + ' · aktiv' : 'für ' + name;
    byId('sm-inactive').hidden = active;
    byId('sm-inactive-text').textContent = name + ' ist gerade nicht aktiv – die Auswahl gilt, sobald du dieses Gehirn nutzt.';
    byId('sm-saving').hidden = !pick(sm.busy, p.id);
    const cur = smCur(p.id);

    // Modell-Kacheln
    const tiles = byId('sm-models');
    tiles.setAttribute('aria-label', 'Modell für ' + name);
    tiles.replaceChildren();
    const hasModel = g.models.some((m) => m.id === cur.model);
    g.models.forEach((m, i) => {
      const on = m.id === cur.model;
      const b = h('button', 'sm-tile' + (on ? ' selected' : ''));
      b.type = 'button';
      b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      b.tabIndex = on || (!hasModel && i === 0) ? 0 : -1;
      b.dataset.id = m.id;
      b.dataset.sm = 'model:' + m.id;
      b.append(h('span', 'sm-name', m.name));
      if (m.info) b.append(h('span', 'sm-info', m.info));
      if (m.tempo || m.preis) { // "Tempo: … · Preis" – umbrechen lieber am Trenner als mitten im Preis
        const meta = h('span', 'sm-meta');
        if (m.tempo) meta.append(h('span', null, 'Tempo: ' + m.tempo + (m.preis ? ' ·' : '')), m.preis ? ' ' : '');
        if (m.preis) meta.append(h('span', null, m.preis));
        b.append(meta);
      }
      const chk = h('span', 'sp-check');
      chk.append(icon('check'));
      b.append(chk);
      b.addEventListener('click', () => smPick(p.id, 'model', m.id, false));
      tiles.append(b);
    });
    tiles.hidden = !g.models.length;
    byId('sm-models-label').hidden = !g.models.length;

    // Denk-Tiefe als Segment-Leiste
    const seg = byId('sm-depth');
    seg.setAttribute('aria-label', 'Denk-Tiefe für ' + name);
    seg.replaceChildren();
    const hasDepth = g.depths.some((t) => t.id === cur.denken);
    g.depths.forEach((t, i) => {
      const on = t.id === cur.denken;
      const b = h('button', 'segctl-btn sm-seg', t.name);
      b.type = 'button';
      b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      b.tabIndex = on || (!hasDepth && i === 0) ? 0 : -1;
      if (t.info) b.title = t.info;
      b.dataset.id = t.id;
      b.dataset.sm = 'depth:' + t.id;
      b.addEventListener('click', () => smPick(p.id, 'denken', t.id, false));
      seg.append(b);
    });
    seg.hidden = !g.depths.length;
    byId('sm-depth-label').hidden = !g.depths.length;
    const info = byId('sm-depth-info');
    const t = smFind(g.depths, cur.denken);
    info.replaceChildren();
    if (t) info.append(h('b', null, t.name), t.info ? ': ' + t.info : '');
    info.hidden = !t;

    if (focusKey) {
      const el = [...sec.querySelectorAll('[data-sm]')].find((x) => x.dataset.sm === focusKey);
      if (el) el.focus({ preventScroll: true });
    }
  }

  function smPick(pid, kind, id, keyboard) {
    if (!smGroup(pid)) return;
    const cur = smCur(pid);
    if (cur[kind] === id) return;
    sm.want[pid] = Object.assign({}, cur, { [kind]: id });
    renderModel();
    renderSuCardsOnly();
    clearTimeout(pick(sm.timer, pid));
    sm.timer[pid] = setTimeout(() => { delete sm.timer[pid]; smSave(pid); }, keyboard ? 450 : 0);
  }

  /** Nur die Gehirn-Karten neu (zeigen das gewaehlte Modell), Fokus bleibt. */
  function renderSuCardsOnly() {
    const box = byId('su-provs');
    if (!su.data || !box.childElementCount) return;
    for (const c of box.children) {
      const p = su.data.providers.find((x) => x.id === c.dataset.id);
      const line = p && c.querySelector('.sp-model > span:last-child');
      if (line) line.textContent = smShownName(p);
    }
  }

  /** Auswahl an die KI schicken – immer nur eine Anfrage je Gehirn, die neueste Auswahl gewinnt. */
  async function smSave(pid) {
    if (pick(sm.busy, pid)) return; // laeuft schon – danach wird nachgezogen
    const w = pick(sm.want, pid);
    if (!w) return;
    const g = smGroup(pid);
    if (g && g.model === w.model && g.denken === w.denken) { // wieder beim alten angekommen
      delete sm.want[pid];
      renderModel();
      renderSuCardsOnly();
      return;
    }
    sm.busy[pid] = true;
    renderModel();
    // Nur schicken, was wirklich geaendert wurde: eine reine Denk-Tiefen-Wahl laesst das Modell
    // unangetastet (auch ein eigenes aus settings.toml und eines, das ein anderes Fenster gerade gewaehlt hat).
    const body = { provider: pid };
    if (w.model && (!g || w.model !== g.model)) body.model = w.model;
    if (w.denken && (!g || w.denken !== g.denken)) body.denken = w.denken;
    const r = await post('/api/modell', body);
    delete sm.busy[pid];
    const latest = pick(sm.want, pid);
    const newer = latest && (latest.model !== w.model || latest.denken !== w.denken);
    const brain = su.data && su.data.providers.find((p) => p.id === pid);
    if (r.ok) {
      su.gen++; // eine noch laufende (aeltere) Abfrage von /api/setup zaehlt nicht mehr
      const d = normSetup(r.setup);
      if (d) {
        su.data = d;
        su.loading = false;
        if (!d.providers.some((p) => p.id === su.sel)) su.sel = suDefaultSel();
      } else if (g) {
        g.model = w.model;
        g.denken = w.denken;
        loadSetup();
      }
      if (newer) {
        if (!pick(sm.timer, pid)) smSave(pid);
      } else {
        delete sm.want[pid];
        let msg = str(r.message).trim() || 'Gespeichert.';
        if (su.data && pid !== su.data.provider && brain) msg += ' Gilt, sobald du ' + suShort(brain) + ' nutzt.';
        smToast('Eingestellt: ' + msg, 'ok', /Achtung/.test(msg) ? 6500 : 4000);
      }
    } else {
      // nichts geaendert: zurueck zur gespeicherten Auswahl
      delete sm.want[pid];
      clearTimeout(pick(sm.timer, pid));
      delete sm.timer[pid];
      let err = str(r.error).trim() || 'Das hat nicht geklappt.';
      if (!/[.!?]$/.test(err)) err += '.';
      smToast(err + ' Die Einstellung bleibt, wie sie war.', 'error', 6000);
    }
    if (su.data) renderSetup();
    if (su.jump && !su.loading) suJump();
  }

  for (const [gid, kind] of [['sm-models', 'model'], ['sm-depth', 'denken']]) {
    const group = byId(gid);
    group.addEventListener('keydown', (e) => {
      const pid = byId('su-model').dataset.provider;
      if (e.key === 'Home' || e.key === 'End') { // erste/letzte Wahl
        const items = [...group.querySelectorAll('[role="radio"]')];
        if (!items.length || !items.includes(document.activeElement)) return;
        e.preventDefault();
        const b = e.key === 'Home' ? items[0] : items[items.length - 1];
        b.focus();
        smPick(pid, kind, b.dataset.id, true);
        return;
      }
      arrowRadio(e, group, (b) => smPick(pid, kind, b.dataset.id, true));
    });
  }

  /** Zum Bereich "Modell & Denk-Tiefe" springen (Klick auf das Modell in Kopfzeile/Seitenleiste). */
  function suJump() {
    if (!su.jump || !suVisible()) return;
    su.jump = '';
    const sec = byId('su-model');
    if (sec.hidden) { suFocus(); return; }
    const scroller = su.where === 'pane' ? byId('pn-body') : byId('su-body');
    const box = scroller.getBoundingClientRect();
    const r = sec.getBoundingClientRect();
    if (r.top < box.top || r.bottom > box.bottom) scroller.scrollTop += r.top - box.top - 8;
    const tile = sec.querySelector('.sm-tile[tabindex="0"]') || sec.querySelector('[role="radio"][tabindex="0"]');
    if (tile) tile.focus({ preventScroll: true });
    sec.classList.remove('flash');
    void sec.offsetWidth; // Animation neu starten
    sec.classList.add('flash');
    setTimeout(() => sec.classList.remove('flash'), 1400);
  }

  function renderSteps(p) {
    const ol = byId('su-steps');
    ol.replaceChildren();
    if (!p) return;
    const li = (...parts) => {
      const l = h('li');
      l.append(...parts);
      ol.append(l);
    };
    const b = (t) => h('b', null, t);
    let page = 'Seite von ' + suShort(p);
    if (p.url) {
      page = h('a', null, page);
      page.href = p.url;
      page.target = '_blank';
      page.rel = 'noopener';
    }
    li('Öffne die ', page, ' und melde dich an.');
    li('Klicke auf ', b('„Create new API key“'), '.');
    li('Kopiere den Schlüssel und füge ihn hier oben ein.');
    if (p.id === 'deepseek') li('Lade unter ', b('„Top up“'), ' etwas Guthaben auf – ohne Guthaben kann ich nicht antworten.');
    else if (p.id === 'claude') li('Guthaben (Credits) lädst du unter ', b('„Billing“'), ' auf.');
  }

  /** Was der Knopf gerade tut: neuen Schluessel pruefen oder nur das Gehirn wechseln. */
  function suAction() {
    const p = suSel();
    if (!p || !su.data) return null;
    const key = suInput.value.trim();
    if (key) return { label: 'Prüfen & speichern', body: { provider: p.id, api_key: key } };
    if (p.hasKey && p.id !== su.data.provider) return { label: 'Zu ' + suShort(p) + ' wechseln', body: { provider: p.id } };
    return null;
  }

  function renderSuHint() {
    const el = byId('su-hint');
    const p = suSel();
    const v = suInput.value.trim();
    let text = 'Wird nur auf deinem PC gespeichert – nie im Chat.';
    let cls = '';
    if (su.note) { text = su.note; cls = 'note'; }
    else if (v && !/^sk-/.test(v)) { text = 'Ein Schlüssel beginnt normalerweise mit „sk-“.'; cls = 'warn'; }
    else if (!v && p && p.hasKey) text = 'Schon gespeichert. Zum Ersetzen einfach einen neuen Schlüssel einfügen.';
    el.className = 'su-hint' + (cls ? ' ' + cls : '');
    el.textContent = text;
  }

  function renderSuGo() {
    const act = suAction();
    // Modell & Denk-Tiefe sind schon gespeichert: ohne Schluessel im Feld / Wechsel gibt es nichts
    // mehr zu bestaetigen -> nur "Schliessen" (ein "Abbrechen" wuerde nichts rueckgaengig machen).
    const idle = !act && !su.checking && !su.welcome;
    const later = byId('su-later');
    later.textContent = su.welcome ? 'Später' : idle ? 'Schließen' : 'Abbrechen';
    const hadFocus = document.activeElement === suGo;
    suGo.hidden = idle;
    if (hadFocus && idle) (later.hidden ? suInput : later).focus({ preventScroll: true }); // Knopf verschwindet
    suGo.disabled = su.checking || !act;
    suGo.setAttribute('aria-busy', su.checking ? 'true' : 'false');
    if (su.checking) suGo.replaceChildren(h('span', 'spinner'), h('span', null, 'Prüfe …'));
    else suGo.replaceChildren(h('span', null, act ? act.label : 'Prüfen & speichern'));
  }

  function renderSuResult() {
    const box = byId('su-result');
    box.replaceChildren();
    const r = su.result;
    box.hidden = !r;
    if (!r) return;
    box.className = 'su-result ' + (r.ok ? 'ok' : 'error');
    box.setAttribute('role', r.ok ? 'status' : 'alert');
    const ic = h('span', 'sr-ic');
    ic.append(icon(r.ok ? 'checkCircle' : 'alertCircle'));
    const body = h('div', 'sr-body');
    body.append(h('div', 'sr-title', r.ok ? (su.welcome ? 'Geschafft – ich kann denken!' : 'Gespeichert') : 'Das hat nicht geklappt'),
      h('div', 'sr-text', r.text));
    const btns = h('div', 'sr-btns');
    if (r.ok && su.welcome && su.where === 'modal') {
      const go = h('button', 'btn primary', 'Los geht’s!');
      go.type = 'button';
      go.id = 'su-start';
      go.addEventListener('click', closeSetup);
      btns.append(go);
    }
    if (!r.ok && r.kind === 'balance') {
      const a = h('a', 'btn small primary');
      a.append(icon('external'), h('span', null, 'Guthaben aufladen'));
      a.href = pick(SU_TOPUP, r.provider) || SU_TOPUP.deepseek;
      a.target = '_blank';
      a.rel = 'noopener';
      btns.append(a);
    }
    if (!r.ok && (r.kind === 'network' || r.kind === 'server') && r.withKey) {
      const f = h('button', 'btn small secondary', 'Trotzdem speichern');
      f.type = 'button';
      f.title = 'Ohne Prüfung speichern – falls gerade nur die Verbindung hakt';
      f.addEventListener('click', () => suSubmit(true));
      btns.append(f);
    }
    if (btns.childElementCount) body.append(btns);
    box.append(ic, body);
  }

  // ---------- Pruefen & speichern ----------
  async function suSubmit(force) {
    const act = suAction();
    if (!act || su.checking) return;
    const body = Object.assign({}, act.body);
    if (force) body.force = true;
    const prov = body.provider;
    su.checking = true;
    su.result = null;
    clearTimeout(su.closeTimer);
    renderSetup();
    moodSync();
    const gen = ++su.reqGen;
    const r = await post('/api/setup', body);
    if (gen !== su.reqGen) return;
    su.checking = false;
    const visible = suVisible();
    if (r.ok) {
      clearKey();
      const d = normSetup(r.setup);
      if (d) su.data = d;
      su.sel = suDefaultSel();
      su.result = { ok: true, text: str(r.message).trim() || 'Gespeichert.' };
      sphere.settle();
      if (!visible) toast(su.result.text, 'ok', 4500);
      else if (su.where === 'modal') su.closeTimer = setTimeout(closeSetup, su.welcome ? 2800 : 1600);
    } else {
      su.result = {
        ok: false, kind: str(r.kind), provider: prov, withKey: !!body.api_key,
        text: str(r.error).trim() || 'Der Schlüssel konnte nicht gespeichert werden.',
      };
      sphere.flicker();
      if (!visible) toast(su.result.text, 'error', 5000);
    }
    renderSetup();
    moodSync();
    if (!visible) return;
    if (r.ok && byId('su-start')) byId('su-start').focus();
    else if (!r.ok) {
      const btn = byId('su-result').querySelector('.btn');
      (btn || suInput).focus();
    }
  }

  function showKey(on) {
    suInput.type = on ? 'text' : 'password';
    const b = byId('su-eye');
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.setAttribute('aria-label', on ? 'Schlüssel verbergen' : 'Schlüssel anzeigen');
    b.title = on ? 'Schlüssel verbergen' : 'Schlüssel anzeigen';
    b.replaceChildren(icon(on ? 'eyeOff' : 'eye'));
  }

  /** Eingefuegter Schluessel passt zum anderen Gehirn? (sk-ant-… = Claude) – dann umschalten. */
  function suDetect() {
    const v = suInput.value.trim();
    if (v.length < 20 || !su.data) return;
    const want = /^sk-ant-/.test(v) ? 'claude' : /^sk-/.test(v) ? 'deepseek' : '';
    const p = want && su.data.providers.find((x) => x.id === want);
    if (!p || want === su.sel) return;
    su.sel = want;
    su.note = 'Das ist ein Schlüssel für ' + suShort(p) + ' – ich habe „' + p.name + '“ ausgewählt.';
    renderSetup();
  }

  suInput.addEventListener('input', () => {
    su.note = '';
    if (su.result) { su.result = null; renderSuResult(); }
    suDetect();
    renderSuHint();
    renderSuGo();
  });
  suInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); suSubmit(false); }
  });
  byId('su-eye').addEventListener('click', () => showKey(suInput.type === 'password'));
  suGo.addEventListener('click', () => suSubmit(false));
  byId('su-close').addEventListener('click', closeSetup);
  byId('su-later').addEventListener('click', closeSetup);
  /** Maus-Klick zu kurz nach dem Oeffnen oder Teil eines Doppelklicks (z.B. auf den Modell-Chip)? */
  const suTooSoon = (e) => !!(e && e.detail) && (e.detail > 1 || performance.now() - su.openedAt < 400);
  smodal.addEventListener('mousedown', (e) => {
    if (e.target !== smodal) return;
    e.preventDefault(); // Fokus bleibt im Fenster
    if (!su.checking && !suTooSoon(e)) closeSetup();
  });
  function setupKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeSetup(); return; }
    if (e.key === 'F2') { e.preventDefault(); return; }
    if (e.key === 'Tab') trapTab(e, sdialog);
  }
  // Gehirn-Karte und Modell in der Kopfzeile: beim Modell-Bereich oeffnen (ohne Schluessel: beim Schluessel)
  byId('sb-brain').addEventListener('click', () => openSetup(false, state.api_key_missing === true ? '' : 'modell'));
  byId('tb-model').addEventListener('click', () => openSetup(false, 'modell'));
  byId('key-bar-btn').addEventListener('click', () => openSetup(true));

  // ---------- Terminal-Version ----------
  byId('sb-terminal').addEventListener('click', async () => {
    closeSidebar();
    if (ended) return;
    const ok = await confirmDialog({
      icon: 'terminal', title: 'Terminal-Version öffnen?', risk: 'Wechsel ins Terminal',
      body: h('p', null, 'Die App schließt sich und ' + kiName() + ' öffnet sich im Terminal – dasselbe Gedächtnis.'),
      ok: 'Öffnen', cancel: 'Abbrechen',
    });
    if (ok && !ended) send('/terminal');
  });

  // ---------- Grosse Sphaere im leeren Zustand: antippen = Jarvis-Modus ----------
  const heroEl = byId('hero');
  heroEl.addEventListener('click', () => startJarvis());
  heroEl.addEventListener('pointerenter', () => sphere.kick(0.5));
  heroEl.addEventListener('focus', () => sphere.kick(0.4));
  /** Als Buchstabe (Aussehen "avatar: buchstabe") ist die Kachel wie frueher nur ein Bild. */
  function syncHero() {
    const on = sphere.mode === 'sphaere';
    heroEl.tabIndex = on ? 0 : -1;
    if (on) heroEl.removeAttribute('aria-hidden'); else heroEl.setAttribute('aria-hidden', 'true');
    byId('hero-cap').hidden = !on;
  }

  // =====================================================================
  // Globale Tasten
  // =====================================================================
  document.addEventListener('keydown', (e) => {
    if (!cmodal.hidden) { confirmKey(e); return; }
    if (askCur && !modal.hidden) { modalKey(e); return; }
    if (!amodal.hidden) { afkKey(e); return; }
    if (jv.open) { jarvisKey(e); return; }
    if (!smodal.hidden) { setupKey(e); return; }
    if (!pmodal.hidden) { profileKey(e); return; }
    if (ended) return;
    if (tour.open && !tour.paused && e.key === 'Escape' && tourCard.contains(document.activeElement)) {
      e.preventDefault();
      endTour(false);
      return;
    }
    if (e.key === 'F2') {
      e.preventDefault();
      if (!e.repeat) voicePress();
      return;
    }
    if (e.key === 'Escape') {
      if (voice.phase !== 'idle' && voice.phase !== 'stopping' && voice.phase !== 'remote-rec') {
        e.preventDefault();
        voiceCancel();
        return;
      }
      if (!cmdPop.hidden) { closeCmdPop(); return; }
      if (app.classList.contains('sb-open')) { closeSidebar(); menuBtn.focus(); return; }
      if (busy) { e.preventDefault(); stop(); }
    }
  });
  document.addEventListener('keyup', (e) => {
    if (e.key === 'F2') { e.preventDefault(); voiceRelease(); }
  });

  // =====================================================================
  // Verbindung (Server-Sent Events) & Verlauf
  // =====================================================================
  let es = null;
  let retry = 0;
  let retryTimer = 0;
  let loadingHistory = false;
  let buffered = [];
  let histGen = 0;           // nur die neueste Verlaufs-Ladung zaehlt
  let flushing = false;      // gepufferte Ereignisse werden gerade nachgespielt
  let resyncOnEnd = false;   // nach dem Ende der laufenden Antwort den Verlauf neu laden
  let resyncWait = false;    // ... sobald der Server ruhig ist (keine Antwort laeuft, nichts wartet)
  let resyncCount = 0;
  let helloCount = 0;
  const FLOW = new Set(['user', 'start', 'thinking', 'chunk', 'tool', 'agent', 'info', 'done', 'stopped', 'error',
    'notice', 'reset', 'retract', 'afk_report']);

  function setConnected(ok) {
    connected = ok;
    if (ok) everConnected = true;
    const banner = byId('conn-banner');
    banner.classList.remove('ended');
    if (!TOKEN) {
      banner.hidden = false;
      banner.classList.add('fatal');
      byId('conn-text').textContent = 'Kein Zugang – bitte die App über das KI-Symbol neu starten.';
    } else {
      banner.hidden = ok || (!everConnected && retry < 2);
      byId('conn-text').textContent = everConnected
        ? 'Verbindung getrennt … ich verbinde mich neu.'
        : 'Keine Verbindung zur KI … ich versuche es weiter.';
    }
    updateStatus();
  }

  /** Ereignis "bye": nicht neu verbinden, Fenster kann zu. */
  function onBye() {
    ended = true;
    connected = false;
    setSpeaking(false);
    clearTimeout(retryTimer);
    if (es) { es.close(); es = null; }
    loadingHistory = false;
    buffered = [];
    if (reply) endReply('done');
    // offene Fragen sind hinfaellig
    askQueue = [];
    if (askCur) { askCur = null; askFocusBack = null; modal.hidden = true; }
    if (!pmodal.hidden) closeProfile(true);
    if (!smodal.hidden) closeSetup();
    byId('key-bar').hidden = true;
    if (confirmState) closeConfirm(false);
    if (!amodal.hidden) { afk.back = null; amodal.hidden = true; }
    if (jv.open) closeJarvisView();
    ttsStop();
    endClosing();
    if (tour.open) endTour(false, false);
    updateInert();
    if (voice.phase !== 'idle') voiceReset();
    const banner = byId('conn-banner');
    banner.hidden = false;
    banner.classList.remove('fatal');
    banner.classList.add('ended');
    byId('conn-text').textContent = kiName() + ' wurde beendet – du kannst das Fenster schließen.';
    banner.querySelector('.spinner').hidden = true;
    input.disabled = true;
    micBtn.disabled = true;
    app.classList.add('ended');
    for (const el of document.querySelectorAll('.sb-actions, .sb-section, .sb-alerts, .suggestions, .composer-wrap, #tb-jarvis, #tour-offer, #sb-upd')) {
      el.inert = true;
    }
    upd.local = false;
    upd.manual = false;
    clearTimeout(upd.timer);
    clearTimeout(upd.late);
    renderUpdate(); // Knopf aus
    closeCmdPop();
    setBusy(false);
    renderQueue(); // Warteliste weg
    renderAfk();   // AFK-Band weg
    updateEmpty();
  }

  function connect() {
    clearTimeout(retryTimer);
    if (ended) return;
    if (es) es.close();
    es = new EventSource('/api/events?t=' + encodeURIComponent(TOKEN));
    es.onmessage = (m) => {
      let ev;
      try { ev = JSON.parse(m.data); } catch (_) { return; }
      if (ev && typeof ev.type === 'string') handleEvent(ev);
    };
    es.onerror = () => {
      if (ended) return;
      retry++;
      setConnected(false);
      if (speakingOn) setSpeaking(false); // das "aus" kaeme evtl. nie an
      if (es && es.readyState === EventSource.CLOSED) {
        es.close();
        es = null;
        retryTimer = setTimeout(connect, Math.min(10000, 800 * 2 ** Math.min(retry, 4)));
      }
    };
  }

  /** Chat leeren (neues Gespraech oder Neuaufbau aus dem Verlauf). */
  function clearChat() {
    if (reply) { reply.dispose(); reply = null; }
    msgs.replaceChildren();
    markLatest();
    voiceSetupCard = null;
    pendingSent.length = 0;
    jumpBtn.hidden = true;
    moodSync(); // keine laufende Antwort mehr -> Sphaere nicht weiter "nachdenken" lassen
  }

  function addFromHistory(m) {
    if (!m || typeof m !== 'object') return;
    const text = String(m.text == null ? '' : m.text);
    if (m.role === 'user') { addUser(text); rememberOwn(text.trim()); }
    else if (m.role === 'assistant') {
      const r = new Reply();
      r.text(text);
      r.finish('done');
    } else if (m.role === 'notice') {
      if (m.level === 'afk') addAfkNotice(text); // AFK-Schritt (Trennzeile) oder Bericht (Karte)
      else addCard(m.level, text);
    } else if (m.role === 'error') addError(text);
  }

  async function loadHistory(isResync) {
    const gen = ++histGen;
    if (!isResync) resyncCount = 0;
    resyncWait = false;
    loadingHistory = true;
    buffered = [];
    const data = await getJson('/api/history');
    if (gen !== histGen || ended) return; // eine neuere Ladung laeuft schon
    const later = buffered;
    buffered = [];
    loadingHistory = false;
    const list = data && Array.isArray(data.messages) ? data.messages : null;
    if (!list) {
      // Verlauf nicht bekommen: sichtbaren Chat behalten, neue Ereignisse trotzdem zeigen
      toast('Der Verlauf konnte nicht geladen werden.', 'error');
      historyReady = true;
      replay(later, []);
      updateEmpty();
      return;
    }
    // Neu aufbauen (auch nach einer Unterbrechung). Eine laufende Antwort bleibt stehen –
    // sie ist im Verlauf noch nicht enthalten.
    const wasBusy = busy;
    const keep = wasBusy ? reply : null;
    if (keep) reply = null;
    clearChat();
    ownMsgs.length = 0;
    recallIdx = -1;
    histBuilding = true;
    try {
      for (const m of list) addFromHistory(m);
    } finally {
      histBuilding = false;
    }
    if (keep) { msgs.append(keep.row); reply = keep; }
    else if (wasBusy && !afkRunning()) ensureReply().placeholder = true; // Antwort laeuft, ihr Anfang fehlt
    historyReady = true;
    // Der Anfang der laufenden Antwort fehlt evtl. -> nach ihrem Ende den Verlauf neu laden
    resyncOnEnd = wasBusy;
    // Was schon im Verlauf steht, nicht noch einmal anzeigen
    const tail = list.slice(-12)
      .filter((m) => m && (m.role === 'user' || m.role === 'notice' || m.role === 'error'))
      .map((m) => ({ role: m.role, text: String(m.text == null ? '' : m.text).trim() }));
    replay(later, tail);
    updateEmpty();
    toBottom(true);
    moodSync();
  }

  /** Gepufferte Ereignisse nachspielen; Doppeltes (schon im Verlauf) auslassen. */
  function replay(events, tail) {
    flushing = true;
    try {
      for (const ev of events) {
        if (ended) break;
        if (ev.type === 'reset') tail.length = 0;
        if (ev.type === 'user' || ev.type === 'notice' || ev.type === 'error') {
          const t = String(ev.text == null ? '' : ev.text).trim();
          const k = tail.findIndex((x) => x.role === ev.type &&
            (x.text === t || (ev.type === 'error' && x.text && t.endsWith(x.text))));
          if (k >= 0) {
            tail.splice(0, k + 1);
            if (ev.type === 'error') { endReply('error'); setBusy(false); maybeResync(); }
            continue;
          }
        }
        handleEvent(ev);
      }
    } finally {
      flushing = false;
    }
  }

  /** Nach dem Ende einer Antwort, deren Anfang evtl. fehlte, den Verlauf neu laden. */
  function maybeResync() {
    if (!(resyncOnEnd || flushing)) return;
    resyncOnEnd = false;
    if (resyncCount >= 2) return;
    // Nicht sofort: mit der Warteschlange beginnt die naechste Runde genau jetzt – ihre Ereignisse
    // stuenden sonst schon im Verlauf UND kaemen noch einmal live. Erst laden, wenn der Server ruhig ist.
    resyncWait = true;
    resyncIfQuiet();
  }
  /** Aus "done"/"state": Verlauf nachladen, sobald keine Antwort mehr laeuft und nichts mehr wartet. */
  function resyncIfQuiet() {
    if (!resyncWait || loadingHistory || ended) return;
    if (state.busy === true || queueAll().length) return;
    resyncWait = false;
    resyncCount++;
    setTimeout(() => loadHistory(true), 0);
  }

  function handleEvent(ev) {
    if (loadingHistory && FLOW.has(ev.type)) { buffered.push(ev); return; }
    switch (ev.type) {
      case 'hello':
        retry = 0;
        setConnected(true);
        // (neu) verbunden: verpasste "speaking aus" / "ask_done" nicht nachtragen muessen
        setSpeaking(false);
        if (ev.state && ev.state.busy === false) dropAsks();
        // getrennt gewesen: evtl. "off" verpasst – laeuft Jarvis nicht mehr, nichts mehr ignorieren
        if (jv.left && ev.state && ev.state.jarvis !== true) { jv.left = false; endClosing(); }
        updHello();
        applyState(ev.state);
        loadHistory();
        if (helloCount++ > 0) loadAppearance(true); // nach dem Neuverbinden: evtl. verpasste Aenderungen
        break;
      case 'state':
        applyState(ev.state);
        resyncIfQuiet();
        break;
      case 'user':
        onUserEcho(ev.text);
        break;
      case 'start':
        if (reply) endReply('done');
        ensureReply();
        rs.phase = 'thinking';
        setBusy(true);
        break;
      case 'thinking':
        if (ev.on) {
          ensureReply().thinking(true);
          if (rs.phase !== 'working') rs.phase = 'thinking';
        } else if (reply) reply.thinking(false);
        moodSync();
        break;
      case 'chunk':
        ensureReply().text(String(ev.text == null ? '' : ev.text));
        rs.phase = 'writing';
        sphere.pulse();
        moodSync();
        break;
      case 'tool':
        ensureReply().tool(String(ev.name || ''), ev.agent ? String(ev.agent) : null);
        if (rs.phase !== 'working') sphere.kick(0.4);
        rs.phase = 'working';
        moodSync();
        break;
      case 'agent':
        ensureReply().agent(ev.phase, ev.role, ev.task ? String(ev.task) : '');
        rs.phase = 'working';
        moodSync();
        break;
      case 'info': {
        const t = String(ev.text || '');
        if (/^Live-Mitschrift/i.test(t)) jvSetupInfo(t, 'info');
        if (reply) reply.info(t);
        else addInfoLine(t); // ausserhalb einer Antwort keine leere Blase mit Tipp-Punkten
        break;
      }
      case 'done':
        endReply('done');
        setBusy(false);
        sphere.settle();
        maybeResync();
        break;
      case 'stopped':
        endReply('stopped');
        setBusy(false);
        sphere.flinch(false);
        maybeResync();
        break;
      case 'error':
        endReply('error');
        addError(String(ev.text || ''));
        setBusy(false);
        sphere.flicker();
        maybeResync();
        break;
      case 'notice':
        if (/Live-Mitschrift/i.test(String(ev.text || '')) && jv.live === false) jvSetupInfo(String(ev.text), ev.level);
        if (ev.level === 'afk') addAfkNotice(String(ev.text || ''));
        else addCard(ev.level, String(ev.text || ''));
        break;
      case 'afk_report':
        onAfkReport(ev);
        break;
      case 'retract':
        onRetract();
        break;
      case 'queue_returned':
        onQueueReturned(ev.text);
        break;
      case 'reset':
        clearChat();
        resyncOnEnd = false;
        resyncWait = false;
        updateEmpty();
        toBottom(true);
        break;
      case 'ask':
        showAsk(ev);
        break;
      case 'ask_done':
        closeAsk(ev.id);
        break;
      case 'voice':
        onVoiceEvent(ev);
        break;
      case 'bye':
        onBye();
        break;
      case 'jarvis':
        onJarvisEvent(ev);
        break;
      case 'heard':
        onHeard(ev);
        break;
      case 'level':
        if (jv.open && !jv.left) orb.level(Number(ev.value));
        break;
      case 'mic':
        // Pegel beim Mikrofon-Knopf / F2: die Sphaere waechst und leuchtet mit der Stimme
        if (voice.phase !== 'idle' && !jv.open) sphere.level(Number(ev.level));
        break;
      case 'speaking':
        // Vorlesen am PC: die Sphaere spricht mit
        setSpeaking(ev.on === true);
        break;
      case 'say':
        onSay(ev);
        break;
      case 'say_end':
        onSayEnd(ev);
        break;
      case 'hush':
        onHush(ev);
        break;
      case 'open':
        if (ended) break;
        if (ev.what === 'jarvis') { if (!jv.open && !jv.closing) { jv.left = false; openJarvisView(false, 'listening'); } }
        else if (ev.what === 'tutorial') startTour();
        break;
      case 'appearance':
        loadAppearance(true);
        break;
      default:
        break;
    }
  }

  // Start
  // Novas Sphaeren an ihren Plaetzen (Seitenleiste, Kopfzeile, Begruessung, Profil, Tour, Einrichtung)
  for (const el of document.querySelectorAll('[data-orb]')) sphere.slot(el, { live: el.dataset.orb !== 'still' });
  syncHero();
  autosize();
  setBusy(false);
  setConnected(false);
  renderSwitches();
  loadAppearance(false);
  connect();
  input.focus();
})();
