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
  // Zustand & Seitenleiste
  // =====================================================================
  let state = {};
  let busy = false;
  let connected = false;
  let everConnected = false;
  let ended = false; // Ereignis "bye": die KI wurde beendet
  const pendingToggle = {};

  const app = byId('app');
  const msgs = byId('messages');
  const scroller = byId('chat-scroll');
  const emptyEl = byId('empty');
  const input = byId('input');
  const sendBtn = byId('send-btn');
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

  function setFavicon(letter) {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#6366f1"/><stop offset="1" stop-color="#a855f7"/></linearGradient></defs>' +
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
    byId('empty-title').textContent = 'Hallo! Ich bin ' + name + '.';
    // optional: Bedeutung des Namens (z.B. "Neugierige, Offene, Vernetzte Assistenz")
    const meaning = s.meaning ? String(s.meaning).trim() : '';
    fillMeaning(byId('empty-meaning'), name, meaning);
    fillMeaning(byId('sb-meaning'), name, meaning);
    byId('sb-name').title = meaning ? name + ' – ' + meaning : name;
    byId('sb-meaning').title = meaning;
    for (const a of document.querySelectorAll('.ai-avatar')) a.textContent = letter;
    setFavicon(letter);
    input.placeholder = 'Schreib ' + name + ' eine Nachricht …';
    byId('sb-version').textContent = s.version ? 'Version ' + s.version : '';

    // Gehirn
    const prov = String(s.provider || '');
    byId('sb-provider').textContent = pick(PROVIDERS, prov.toLowerCase()) || prov || '–';
    byId('sb-provider').title = byId('sb-provider').textContent;
    byId('sb-model').textContent = s.model || '–';
    byId('sb-model').title = s.model || '';
    byId('tb-model-text').textContent = s.model || '';
    byId('tb-model').hidden = !s.model;

    // Kosten
    byId('sb-eur').textContent = fmtEur(s.eur);
    byId('sb-tokens').textContent = fmtInt(s.tokens) + ' Token';

    // Schalter
    if (!pendingToggle.auto_confirm) setSwitch(byId('sw-erlauben'), !!s.auto_confirm);
    if (!pendingToggle.speak) setSwitch(byId('sw-vorlesen'), !!s.speak);

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
      : 'Sprechen – gedrückt halten oder kurz drücken (F2)';

    // Update in der Kopfzeile
    const upd = s.update && s.update.new ? String(s.update.new) : '';
    byId('tb-update').hidden = !upd;
    byId('tb-update-text').textContent = upd ? 'Update ' + upd : '';

    renderAlerts();
    commands = Array.isArray(s.commands) ? s.commands.filter((c) => c && typeof c.cmd === 'string') : [];
    setBusy(!!s.busy);
    profileNames();
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
        b.addEventListener('click', () => { closeSidebar(); send(cmd); });
        a.append(b);
      }
      box.append(a);
    };
    if (s.update && s.update.new) {
      add('update', 'download', 'Update verfügbar', 'Version ' + s.update.new + ' ist bereit.', 'Jetzt aktualisieren', '/update');
    }
    if (s.api_key_missing) {
      const key = String(s.provider || '').toLowerCase() === 'deepseek' ? 'DEEPSEEK_API_KEY' : 'ANTHROPIC_API_KEY';
      const frag = document.createDocumentFragment();
      frag.append('Trag ihn in die Datei ', h('code', null, '.env'), ' ein (Zeile ', h('code', null, key + '=…'),
        '). Ohne Schlüssel kann ich nicht denken.');
      add('danger', 'key', 'API-Schlüssel fehlt', frag);
    }
    if (s.started_by) {
      add('warn', 'power', 'Automatisch gestartet', 'Ich wurde automatisch gestartet – ' + s.started_by + '.',
        'Autostart prüfen', '/autostart');
    }
    byId('menu-dot').hidden = !box.childElementCount;
  }

  function setBusy(b) {
    busy = !!b;
    sendBtn.classList.toggle('stop', busy);
    sendBtn.replaceChildren(icon(busy ? 'stop' : 'send'));
    if (busy) {
      sendBtn.append(h('span', null, 'Stopp'));
      sendBtn.setAttribute('aria-label', 'Antwort anhalten (Esc)');
      sendBtn.title = 'Antwort anhalten (Esc)';
    } else {
      sendBtn.setAttribute('aria-label', 'Senden (Enter)');
      sendBtn.title = 'Senden (Enter)';
    }
    updateSendBtn();
    updateStatus();
  }

  function updateSendBtn() {
    sendBtn.disabled = ended || (!busy && !input.value.trim());
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
    st.dataset.s = s;
    byId('status-text').textContent = t;
  }

  // Schalter in der Seitenleiste
  const TOGGLES = { erlauben: 'auto_confirm', vorlesen: 'speak' };
  for (const row of document.querySelectorAll('[data-toggle]')) {
    row.addEventListener('click', async () => {
      const name = row.dataset.toggle;
      const key = TOGGLES[name];
      const btn = row.querySelector('.switch');
      if (pendingToggle[key]) return;
      const value = btn.getAttribute('aria-checked') !== 'true';
      setSwitch(btn, value);
      pendingToggle[key] = true;
      const r = await post('/api/toggle', { name, value });
      pendingToggle[key] = false;
      if (r.ok && r.state) applyState(r.state);
      else if (r.ok) state[key] = value;
      else {
        setSwitch(btn, !!state[key]);
        toast(r.error || 'Die Einstellung konnte nicht geändert werden.', 'error');
      }
    });
  }

  // Befehls-Knoepfe
  for (const b of document.querySelectorAll('[data-cmd]')) {
    b.addEventListener('click', () => { closeSidebar(); send(b.dataset.cmd); });
  }
  byId('tb-update').addEventListener('click', () => send('/update'));
  const newChat = () => { closeSidebar(); send('/neu'); };
  byId('sb-new').addEventListener('click', newChat);
  byId('tb-new').addEventListener('click', newChat);
  byId('sb-profile').addEventListener('click', () => openProfile());

  // Seitenleiste als Schublade (schmale Fenster)
  const menuBtn = byId('menu-btn');
  function openSidebar() {
    app.classList.add('sb-open');
    menuBtn.setAttribute('aria-expanded', 'true');
    setTimeout(() => byId('sb-close').focus(), 50);
  }
  function closeSidebar() {
    if (!app.classList.contains('sb-open')) return;
    app.classList.remove('sb-open');
    menuBtn.setAttribute('aria-expanded', 'false');
  }
  menuBtn.addEventListener('click', openSidebar);
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
  let userUpAt = 0;      // wann der Nutzer zuletzt nach oben gescrollt hat (Rad, Tasten)
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
  scroller.addEventListener('wheel', (e) => { if (e.deltaY < 0 && scroller.scrollTop > 0) userUp(); }, { passive: true });
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
    if (force) stick = true;
    if (scrollQueued) return;
    scrollQueued = true;
    requestAnimationFrame(() => {
      scrollQueued = false;
      if (stick) {
        scroller.scrollTop = scroller.scrollHeight;
        lastTop = scroller.scrollTop;
      }
    });
  }
  function keepBottom() {
    if (stick) toBottom();
    else if (msgs.childElementCount) jumpBtn.hidden = false;
  }
  jumpBtn.addEventListener('click', () => { jumpBtn.hidden = true; toBottom(true); });
  if (window.ResizeObserver) new ResizeObserver(() => { if (stick) toBottom(); }).observe(msgs);

  // =====================================================================
  // Chat-Elemente
  // =====================================================================
  let historyReady = false;

  function updateEmpty() {
    // Begruessung, solange noch niemand etwas gesagt hat (Systemkarten allein zaehlen nicht)
    const talked = !!msgs.querySelector('.msg');
    emptyEl.hidden = !historyReady || talked;
    byId('tb-new').hidden = !talked || ended;
  }
  function added() { updateEmpty(); keepBottom(); }

  function aiAvatar() {
    const a = h('div', 'avatar ai-avatar', initial());
    a.setAttribute('aria-hidden', 'true');
    return a;
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
    if (ownMsgs[ownMsgs.length - 1] !== text) ownMsgs.push(text);
    if (ownMsgs.length > 100) ownMsgs.shift();
  }

  async function send(text, fromInput) {
    text = String(text || '').trim();
    if (!text || ended) return;
    if (busy) {
      toast('Ich arbeite noch an der letzten Nachricht – „Stopp“ oder Esc hält sie an.');
      return;
    }
    const row = addUser(text);
    const p = { text, row, t: Date.now() };
    pendingSent.push(p);
    rememberOwn(text);
    recallIdx = -1;
    if (fromInput) {
      input.value = '';
      autosize();
      closeCmdPop();
    }
    toBottom(true);
    const r = await post('/api/send', { text });
    if (!r.ok) {
      const k = pendingSent.indexOf(p);
      if (k >= 0) pendingSent.splice(k, 1);
      row.remove();
      updateEmpty();
      if (fromInput && !input.value) { input.value = text; autosize(); }
      toast(r.error || 'Senden hat nicht geklappt.', 'error');
    }
  }

  function onUserEcho(text) {
    const t = String(text || '').trim();
    // aeltere Eintraege (ohne Echo) aufraeumen
    while (pendingSent.length && Date.now() - pendingSent[0].t > 60000) pendingSent.shift();
    const k = pendingSent.findIndex((p) => p.text === t);
    if (k >= 0) { pendingSent.splice(k, 1); return; }
    addUser(t);
    rememberOwn(t);
  }

  async function stop() {
    const r = await post('/api/stop', {});
    if (!r.ok) toast(r.error || 'Anhalten hat nicht geklappt.', 'error');
  }

  sendBtn.addEventListener('click', () => {
    if (busy) stop();
    else send(input.value, true);
  });

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
    if (!pmodal.hidden || ended) return false;
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
      send(input.value, true);
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
      byId('voice-help').textContent = voice.mode === 'toggle' || voice.phase === 'remote'
        ? 'Nochmal drücken (oder F2) = fertig · Esc bricht ab'
        : 'Loslassen = fertig · Esc bricht ab';
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
    appendToInput(text);
  }

  async function voiceCancel() {
    const startP = voice.startP;
    const wasRemote = voice.phase === 'remote';
    voice.quietUntil = Date.now() + 3000;
    voiceReset();
    toast('Aufnahme abgebrochen');
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
      else if (ev.text) appendToInput(ev.text);
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
    const profOpen = !pmodal.hidden;
    app.inert = askOpen || profOpen;
    pmodal.inert = askOpen;
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
        else if (!pmodal.hidden) panel.focus();
        else focusInput();
      }
      askFocusBack = null;
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
  }

  function closeAsk(id) {
    if (askCur && askCur.id === id) nextAsk();
    else askQueue = askQueue.filter((a) => a.id !== id);
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
  const TABS = ['charakter', 'stil', 'ueber', 'werte', 'gedaechtnis'];
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
    updateInert();
    profError = '';
    savedNote = false;
    hideConfirm();
    showTab(tab && TABS.includes(tab) ? tab : profTab, false);
    loadProfile();
    loadMemory();
    requestAnimationFrame(() => byId('tab-' + profTab).focus());
  }

  function requestClose() {
    if (profSaving) return;
    if (prof && Object.keys(profChanges()).length) { showConfirm(); return; }
    closeProfile();
  }

  function closeProfile() {
    hideConfirm();
    memConfirmReset();
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
    byId('pn-body').scrollTop = 0;
    const tabBtn = byId('tab-' + t);
    if (focus) tabBtn.focus();
    tabBtn.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (t === 'gedaechtnis' && !mem.loaded && !mem.loading) loadMemory();
  }

  function renderPanes() {
    const ready = panelState === 'ready';
    const memTab = profTab === 'gedaechtnis';
    byId('pn-loading').hidden = memTab || panelState !== 'loading';
    byId('pn-error').hidden = memTab || panelState !== 'error';
    for (const t of TABS) byId('pane-' + t).hidden = t !== profTab || (t !== 'gedaechtnis' && !ready);
    if (ready && profTab === 'ueber') for (const el of Object.values(aboutEls)) grow(el);
  }

  for (const t of TABS) byId('tab-' + t).addEventListener('click', () => showTab(t, false));
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
    byId('pf-avatar').textContent = (n.charAt(0) || 'K').toUpperCase();
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
    // Name und Bedeutung immer zusammen schicken (der Server speichert die Bedeutung nur mit Namen)
    if (name !== prof.name || meaning !== prof.meaning) { ch.name = name; ch.meaning = meaning; }
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
    if (/["\\\n]/.test(ch.name)) return 'Bitte einen Namen ohne Anführungszeichen oder Backslash.';
    if (ch.name.length > 40) return 'Der Name ist zu lang (höchstens 40 Zeichen).';
    if (/[\\\n]/.test(ch.meaning || '')) return 'Bitte die Bedeutung ohne Backslash (\\) schreiben.';
    return '';
  }

  function updateDirty() {
    const ch = profChanges();
    const n = Object.keys(ch).length;
    const td = {
      charakter: 'name' in ch || 'character' in ch,
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
    profSaving = true;
    profError = '';
    updateDirty();
    const r = await post('/api/profile', ch);
    profSaving = false;
    if (!r.ok) {
      profError = r.error || 'Speichern hat nicht geklappt.';
      updateDirty();
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
    }
    return true;
  }

  function startNewConversation() {
    if (busy) { toast('Ich arbeite noch – ein neues Gespräch geht, sobald ich fertig bin.'); return; }
    closeProfile();
    send('/neu');
  }

  byId('pn-save').addEventListener('click', () => saveProfile(false));
  byId('pn-save-new').addEventListener('click', () => saveProfile(true));
  byId('pn-close').addEventListener('click', requestClose);
  byId('pn-retry').addEventListener('click', loadProfile);
  pmodal.addEventListener('mousedown', (e) => { if (e.target === pmodal) requestClose(); });
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
  // Globale Tasten
  // =====================================================================
  document.addEventListener('keydown', (e) => {
    if (askCur && !modal.hidden) { modalKey(e); return; }
    if (!pmodal.hidden) { profileKey(e); return; }
    if (ended) return;
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
  let resyncCount = 0;
  const FLOW = new Set(['user', 'start', 'thinking', 'chunk', 'tool', 'agent', 'info', 'done', 'stopped', 'error',
    'notice', 'reset']);

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
    clearTimeout(retryTimer);
    if (es) { es.close(); es = null; }
    loadingHistory = false;
    buffered = [];
    if (reply) endReply('done');
    // offene Fragen sind hinfaellig
    askQueue = [];
    if (askCur) { askCur = null; askFocusBack = null; modal.hidden = true; }
    if (!pmodal.hidden) closeProfile(true);
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
    closeCmdPop();
    setBusy(false);
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
    voiceSetupCard = null;
    pendingSent.length = 0;
    jumpBtn.hidden = true;
  }

  function addFromHistory(m) {
    if (!m || typeof m !== 'object') return;
    const text = String(m.text == null ? '' : m.text);
    if (m.role === 'user') { addUser(text); rememberOwn(text.trim()); }
    else if (m.role === 'assistant') {
      const r = new Reply();
      r.text(text);
      r.finish('done');
    } else if (m.role === 'notice') addCard(m.level, text);
    else if (m.role === 'error') addError(text);
  }

  async function loadHistory(isResync) {
    const gen = ++histGen;
    if (!isResync) resyncCount = 0;
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
    for (const m of list) addFromHistory(m);
    if (keep) { msgs.append(keep.row); reply = keep; }
    else if (wasBusy) ensureReply();
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
    resyncCount++;
    setTimeout(() => loadHistory(true), 0);
  }

  function handleEvent(ev) {
    if (loadingHistory && FLOW.has(ev.type)) { buffered.push(ev); return; }
    switch (ev.type) {
      case 'hello':
        retry = 0;
        setConnected(true);
        applyState(ev.state);
        loadHistory();
        break;
      case 'state':
        applyState(ev.state);
        break;
      case 'user':
        onUserEcho(ev.text);
        break;
      case 'start':
        if (reply) endReply('done');
        ensureReply();
        setBusy(true);
        break;
      case 'thinking':
        if (ev.on) ensureReply().thinking(true);
        else if (reply) reply.thinking(false);
        break;
      case 'chunk':
        ensureReply().text(String(ev.text == null ? '' : ev.text));
        break;
      case 'tool':
        ensureReply().tool(String(ev.name || ''), ev.agent ? String(ev.agent) : null);
        break;
      case 'agent':
        ensureReply().agent(ev.phase, ev.role, ev.task ? String(ev.task) : '');
        break;
      case 'info':
        ensureReply().info(String(ev.text || ''));
        break;
      case 'done':
        endReply('done');
        setBusy(false);
        maybeResync();
        break;
      case 'stopped':
        endReply('stopped');
        setBusy(false);
        maybeResync();
        break;
      case 'error':
        endReply('error');
        addError(String(ev.text || ''));
        setBusy(false);
        maybeResync();
        break;
      case 'notice':
        addCard(ev.level, String(ev.text || ''));
        break;
      case 'reset':
        clearChat();
        resyncOnEnd = false;
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
      default:
        break;
    }
  }

  // Start
  autosize();
  setBusy(false);
  setConnected(false);
  connect();
  input.focus();
})();
