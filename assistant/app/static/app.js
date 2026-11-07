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
  };

  function icon(name, cls) {
    const span = document.createElement('span');
    span.className = 'ic' + (cls ? ' ' + cls : '');
    span.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICONS[name] || ICONS.info) + '</svg>';
    return span;
  }

  // Platzhalter data-icon im HTML mit Symbolen fuellen
  for (const el of document.querySelectorAll('[data-icon]')) {
    el.prepend(icon(el.dataset.icon));
    el.removeAttribute('data-icon');
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
    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, text, url) => keep(link(url, emph(text))));
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

  const RE_FENCE = /^(\s*)(`{3,}|~{3,})\s*([\w+#.\-]*)\s*$/;
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
    const meaning = s.meaning ? String(s.meaning) : '';
    byId('empty-meaning').textContent = meaning;
    byId('empty-meaning').hidden = !meaning;
    byId('sb-name').title = meaning ? name + ' – ' + meaning : name;
    for (const a of document.querySelectorAll('.ai-avatar')) a.textContent = letter;
    setFavicon(letter);
    input.placeholder = 'Schreib ' + name + ' eine Nachricht …';
    byId('sb-version').textContent = s.version ? 'Version ' + s.version : '';

    // Gehirn
    const prov = String(s.provider || '');
    byId('sb-provider').textContent = PROVIDERS[prov.toLowerCase()] || prov || '–';
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
    sendBtn.disabled = !busy && !input.value.trim();
  }

  function updateStatus() {
    const st = byId('status');
    let s = 'ready';
    let t = 'Bereit';
    if (!connected) { s = everConnected ? 'off' : 'connecting'; t = everConnected ? 'Getrennt' : 'Verbinde …'; }
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
  const jumpBtn = byId('jump');
  const distBottom = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  scroller.addEventListener('scroll', () => {
    // Nur echtes Hochscrollen loest das Mitlaufen – waechst der Inhalt, bleibt es an
    const top = scroller.scrollTop;
    if (distBottom() < 70) stick = true;
    else if (top < lastTop - 2) stick = false;
    lastTop = top;
    if (stick) jumpBtn.hidden = true;
  }, { passive: true });
  scroller.addEventListener('wheel', (e) => { if (e.deltaY < 0 && distBottom() > 4) stick = false; }, { passive: true });
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
    emptyEl.hidden = !historyReady || msgs.childElementCount > 0;
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

  function addCard(level, mdText, opts) {
    const lv = ['info', 'warn', 'ok'].includes(level) ? level : 'info';
    const card = h('div', 'card ' + lv);
    card.setAttribute('role', 'note');
    card.append(icon(lv === 'warn' ? 'alert' : lv === 'ok' ? 'checkCircle' : 'info', 'card-ic'));
    const body = h('div', 'card-body md');
    body.innerHTML = renderMarkdown(mdText); // renderMarkdown escaped alles
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
    if (TOOL_INFO[n]) return TOOL_INFO[n];
    const label = n.replace(/_/g, ' ').replace(/ae/g, 'ä').replace(/oe/g, 'ö').replace(/ue/g, 'ü');
    return ['wrench', label.charAt(0).toUpperCase() + label.slice(1)];
  }
  const ROLE_NAMES = { recherche: 'Recherche', helfer: 'Helfer', pruefer: 'Prüfer', 'prüfer': 'Prüfer' };
  const roleLabel = (r) => ROLE_NAMES[String(r).toLowerCase()] ||
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
      finish() {
        if (this.done) return;
        this.done = true;
        el.classList.remove('running');
        el.classList.add('done');
        st.replaceChildren(icon('check'));
        cnt.textContent = !this.steps ? 'fertig' : (this.steps === 1 ? '1 Schritt' : this.steps + ' Schritte') + ' · fertig';
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

    /** kind: 'done' | 'stopped' | 'error' */
    finish(kind) {
      this.flush();
      this.thinking(false);
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
    if (!text) return;
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

  function appendToInput(text) {
    const t = String(text || '').trim();
    if (!t) return;
    const v = input.value;
    input.value = v + (v && !/\s$/.test(v) ? ' ' : '') + t;
    autosize();
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
    updateCmdPop();
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

  function voiceFailed(r) {
    if (r.setup) {
      addCard('warn', 'Die Spracheingabe ist noch nicht eingerichtet.' + (r.error ? '\n\n' + r.error : ''), {
        button: { label: 'Spracheingabe einrichten', onClick: () => send('/sprache einrichten') },
      });
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
    if (!text) { toast('Ich habe nichts verstanden – versuch es noch einmal.'); input.focus(); return; }
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

  function nextAsk() {
    askCur = askQueue.shift() || null;
    askSending = false;
    if (!askCur) {
      modal.hidden = true;
      if (askFocusBack && document.contains(askFocusBack)) askFocusBack.focus();
      else input.focus();
      askFocusBack = null;
      return;
    }
    if (!askFocusBack) askFocusBack = document.activeElement;
    if (!Array.isArray(askCur.options) || !askCur.options.length) {
      askCur.options = [{ value: 'ok', label: 'OK' }];
    }
    const risk = RISKS[askCur.risk] || null;
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
  // Globale Tasten
  // =====================================================================
  document.addEventListener('keydown', (e) => {
    if (askCur && !modal.hidden) { modalKey(e); return; }
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
  const FLOW = new Set(['user', 'start', 'thinking', 'chunk', 'tool', 'agent', 'info', 'done', 'stopped', 'error', 'notice']);

  function setConnected(ok) {
    connected = ok;
    if (ok) everConnected = true;
    const banner = byId('conn-banner');
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

  function connect() {
    clearTimeout(retryTimer);
    if (es) es.close();
    es = new EventSource('/api/events?t=' + encodeURIComponent(TOKEN));
    es.onmessage = (m) => {
      let ev;
      try { ev = JSON.parse(m.data); } catch (_) { return; }
      if (ev && typeof ev.type === 'string') handleEvent(ev);
    };
    es.onerror = () => {
      retry++;
      setConnected(false);
      if (es && es.readyState === EventSource.CLOSED) {
        es.close();
        es = null;
        retryTimer = setTimeout(connect, Math.min(10000, 800 * 2 ** Math.min(retry, 4)));
      }
    };
  }

  async function loadHistory() {
    loadingHistory = true;
    buffered = [];
    const data = await getJson('/api/history');
    // Neu aufbauen (auch nach einer Unterbrechung)
    if (reply) { reply.thinking(false); reply = null; }
    msgs.replaceChildren();
    pendingSent.length = 0;
    const list = data && Array.isArray(data.messages) ? data.messages : [];
    for (const m of list) {
      if (!m || typeof m !== 'object') continue;
      const text = String(m.text == null ? '' : m.text);
      if (m.role === 'user') { addUser(text); rememberOwn(text.trim()); }
      else if (m.role === 'assistant') {
        const r = new Reply();
        r.text(text);
        r.finish('done');
      } else if (m.role === 'notice') addCard(m.level, text);
      else if (m.role === 'error') addError(text);
    }
    if (!data) toast('Der Verlauf konnte nicht geladen werden.', 'error');
    historyReady = true;
    loadingHistory = false;
    const later = buffered;
    buffered = [];
    for (const ev of later) handleEvent(ev);
    updateEmpty();
    toBottom(true);
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
        break;
      case 'stopped':
        endReply('stopped');
        setBusy(false);
        break;
      case 'error':
        endReply('error');
        addError(String(ev.text || ''));
        setBusy(false);
        break;
      case 'notice':
        addCard(ev.level, String(ev.text || ''));
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
