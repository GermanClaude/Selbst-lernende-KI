/*
 * Nova-Kamera – Signalisierung (gleiches Protokoll wie assistant/kamera/signal.py).
 *
 * Kopplung (#p=…): base64url( Version(1) | Thema(16) | Schlüssel(32) | Ablauf(uint32 BE) | Flags(1) )
 * Nachricht:       base64url( 0x01 | Nonce(12) | AES-256-GCM(Klartext, AAD "nova-kamera/1|<Thema>") )
 * Klartext:        Packart(1: 0 = roh, 1 = deflate-raw) | JSON {t, s, z, f, d}
 *
 * Läuft im Browser und (für Tests) in Node ≥ 22. Kein Netzwerkzugriff außer über NtfyRelay.
 */
(function (global) {
  "use strict";

  const PROTOKOLL = 1;
  const MAX_TEXT = 4000;
  const MAX_KLARTEXT = 64 * 1024;
  const MAX_UHR_ABWEICHUNG_MS = 300 * 1000;
  const CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  const CODE_LAENGE = 8;
  const CODE_SALZ = "nova-kamera/code/1";
  const CODE_RUNDEN = 200000;
  const subtle = global.crypto && global.crypto.subtle;
  const enc = new TextEncoder();
  const dec = new TextDecoder("utf-8", { fatal: true });

  class SignalFehler extends Error {
    constructor(text) { super(text); this.name = "SignalFehler"; }
  }
  class RelayFehler extends Error {
    constructor(text) { super(text); this.name = "RelayFehler"; }
  }

  // -- base64url ---------------------------------------------------------------------------
  function b64u(bytes) {
    let s = "";
    const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function b64uDekodieren(text) {
    if (typeof text !== "string" || !/^[-_A-Za-z0-9]*$/.test(text)) throw new SignalFehler("Ungültige Zeichen in den Daten.");
    let s = text.replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    let roh;
    try { roh = atob(s); } catch (e) { throw new SignalFehler("Ungültige Daten."); }
    const out = new Uint8Array(roh.length);
    for (let i = 0; i < roh.length; i++) out[i] = roh.charCodeAt(i);
    return out;
  }

  // -- Kopplung ----------------------------------------------------------------------------
  function leseKopplung(payload, jetztSek) {
    const roh = b64uDekodieren((payload || "").trim());
    if (roh.length !== 54) throw new SignalFehler("Der Kopplungs-Code ist unvollständig.");
    if (roh[0] !== PROTOKOLL) throw new SignalFehler("Dieser QR-Code stammt von einer anderen Nova-Version.");
    const dv = new DataView(roh.buffer, roh.byteOffset, roh.byteLength);
    const k = {
      version: roh[0],
      themaRoh: roh.slice(1, 17),
      schluessel: roh.slice(17, 49),
      ablauf: dv.getUint32(49, false),
      flags: roh[53],
      payload: payload.trim(),
    };
    k.thema = b64u(k.themaRoh);
    if (jetztSek !== undefined && jetztSek > k.ablauf) {
      throw new SignalFehler("Der QR-Code ist abgelaufen. Bitte in Nova einen neuen anzeigen lassen.");
    }
    return k;
  }
  function kopplungAusLink(link, jetztSek) {
    let fragment = "";
    const i = (link || "").indexOf("#");
    if (i >= 0) fragment = link.slice(i + 1);
    for (const teil of fragment.split("&")) {
      if (teil.startsWith("p=")) return leseKopplung(teil.slice(2), jetztSek);
    }
    throw new SignalFehler("Im Link fehlt die Kopplung.");
  }

  // -- Packen ------------------------------------------------------------------------------
  async function stromLesen(strom, grenze) {
    const leser = strom.getReader();
    const teile = [];
    let laenge = 0;
    for (;;) {
      const { value, done } = await leser.read();
      if (done) break;
      laenge += value.length;
      if (laenge > grenze) { try { await leser.cancel(); } catch (e) { /* egal */ } throw new SignalFehler("Nachricht zu groß."); }
      teile.push(value);
    }
    const out = new Uint8Array(laenge);
    let pos = 0;
    for (const t of teile) { out.set(t, pos); pos += t.length; }
    return out;
  }
  const kannPacken = typeof global.CompressionStream === "function";
  async function packen(daten) {
    if (kannPacken) {
      try {
        const strom = new Blob([daten]).stream().pipeThrough(new CompressionStream("deflate-raw"));
        const gepackt = await stromLesen(strom, MAX_KLARTEXT * 2);
        if (gepackt.length < daten.length) {
          const out = new Uint8Array(gepackt.length + 1);
          out[0] = 1; out.set(gepackt, 1);
          return out;
        }
      } catch (e) { /* ungepackt senden */ }
    }
    const out = new Uint8Array(daten.length + 1);
    out[0] = 0; out.set(daten, 1);
    return out;
  }
  async function entpacken(daten) {
    if (!daten.length) throw new SignalFehler("Leere Nachricht.");
    const rest = daten.subarray(1);
    if (daten[0] === 0) {
      if (rest.length > MAX_KLARTEXT) throw new SignalFehler("Nachricht zu groß.");
      return rest;
    }
    if (daten[0] !== 1) throw new SignalFehler("Unbekannte Packart.");
    if (typeof global.DecompressionStream !== "function") throw new SignalFehler("Dieser Browser kann die Nachricht nicht entpacken.");
    try {
      return await stromLesen(new Blob([rest]).stream().pipeThrough(new DecompressionStream("deflate-raw")), MAX_KLARTEXT);
    } catch (e) {
      if (e instanceof SignalFehler) throw e;
      throw new SignalFehler("Nachricht lässt sich nicht entpacken.");
    }
  }

  // -- Kanal -------------------------------------------------------------------------------
  class Kanal {
    constructor(kopplung, absender, uhr) {
      if (absender !== "n" && absender !== "h") throw new Error("absender muss 'n' oder 'h' sein");
      if (!subtle) throw new SignalFehler("Dieser Browser kann nicht verschlüsseln (nur über HTTPS möglich).");
      this.kopplung = kopplung;
      this.thema = kopplung.thema;
      this.absender = absender;
      this.uhr = uhr || (() => Date.now());
      this.seq = 0;
      this.zuletzt = { n: 0, h: 0 };
      this.aad = enc.encode("nova-kamera/" + PROTOKOLL + "|" + this.thema);
      this._schluessel = subtle.importKey("raw", kopplung.schluessel, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
    }

    async verpacke(typ, daten) {
      this.seq += 1;
      const inhalt = { t: typ, s: this.seq, z: Math.round(this.uhr()), f: this.absender, d: daten || {} };
      const klartext = await packen(enc.encode(JSON.stringify(inhalt)));
      const nonce = global.crypto.getRandomValues(new Uint8Array(12));
      const ct = new Uint8Array(await subtle.encrypt({ name: "AES-GCM", iv: nonce, additionalData: this.aad, tagLength: 128 },
        await this._schluessel, klartext));
      const roh = new Uint8Array(1 + 12 + ct.length);
      roh[0] = PROTOKOLL; roh.set(nonce, 1); roh.set(ct, 13);
      const text = b64u(roh);
      if (text.length > MAX_TEXT) throw new SignalFehler("Nachricht zu groß für das Relais (" + text.length + " Bytes).");
      return text;
    }

    /** Nachricht der Gegenseite, null für eigene. Wirft SignalFehler bei allem Verdächtigen. */
    async oeffne(text) {
      if (typeof text !== "string" || text.length > MAX_TEXT + 96) throw new SignalFehler("Nachricht zu groß.");
      const roh = b64uDekodieren(text.trim());
      if (roh.length < 29 || roh[0] !== PROTOKOLL) throw new SignalFehler("Keine Nova-Nachricht.");
      let klartext;
      try {
        klartext = new Uint8Array(await subtle.decrypt({ name: "AES-GCM", iv: roh.subarray(1, 13), additionalData: this.aad, tagLength: 128 },
          await this._schluessel, roh.subarray(13)));
      } catch (e) {
        throw new SignalFehler("Nachricht ungültig (falscher Schlüssel oder verändert).");
      }
      let inhalt;
      try { inhalt = JSON.parse(dec.decode(await entpacken(klartext))); } catch (e) {
        if (e instanceof SignalFehler) throw e;
        throw new SignalFehler("Nachricht ist kein JSON.");
      }
      if (!inhalt || typeof inhalt !== "object" || Array.isArray(inhalt)) throw new SignalFehler("Nachricht hat das falsche Format.");
      const { t, s, z, f, d } = inhalt;
      if (typeof t !== "string" || !t || t.length > 32 || !Number.isInteger(s) || s < 1 || !Number.isInteger(z)
          || (f !== "n" && f !== "h") || !d || typeof d !== "object" || Array.isArray(d)) {
        throw new SignalFehler("Nachricht hat das falsche Format.");
      }
      if (f === this.absender) return null;
      if (Math.abs(this.uhr() - z) > MAX_UHR_ABWEICHUNG_MS) throw new SignalFehler("Nachricht ist veraltet (oder die Uhr geht falsch).");
      if (s <= this.zuletzt[f]) throw new SignalFehler("Nachricht wurde wiederholt – abgelehnt.");
      this.zuletzt[f] = s;
      return { typ: t, seq: s, zeit: z, absender: f, daten: d };
    }
  }

  // -- Kurzcode ----------------------------------------------------------------------------
  function codeNormalisieren(text) {
    const roh = String(text || "").replace(/[\s\-_.]/g, "").toUpperCase().replace(/O/g, "0").replace(/[IL]/g, "1");
    if (roh.length !== CODE_LAENGE || [...roh].some((z) => CODE_ALPHABET.indexOf(z) < 0)) {
      throw new SignalFehler("Der Code hat 8 Zeichen (Buchstaben und Ziffern).");
    }
    return roh;
  }
  async function codeKopplung(code) {
    const basis = await subtle.importKey("raw", enc.encode(codeNormalisieren(code)), "PBKDF2", false, ["deriveBits"]);
    const bits = new Uint8Array(await subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: enc.encode(CODE_SALZ), iterations: CODE_RUNDEN }, basis, 384));
    const k = { version: PROTOKOLL, themaRoh: bits.slice(0, 16), schluessel: bits.slice(16, 48), ablauf: 0, flags: 1 };
    k.thema = b64u(k.themaRoh);
    return k;
  }

  // -- Relais (ntfy.sh oder lokaler Test-Relay mit gleicher Schnittstelle) -----------------
  class NtfyRelay {
    constructor(basis) {
      this.basis = (basis || "https://ntfy.sh").replace(/\/+$/, "");
      this.name = "ntfy";
    }
    _pruefe(antwort) {
      if (antwort.status === 429) throw new RelayFehler("Der Vermittler (ntfy.sh) bremst gerade. Bitte eine Minute warten.");
      if (!antwort.ok) throw new RelayFehler("Der Vermittler (ntfy.sh) antwortet mit Fehler " + antwort.status + ".");
    }
    async senden(thema, text) {
      let antwort;
      try {
        // Einfache Anfrage (text/plain, keine Extra-Header) – kein CORS-Vorabcheck nötig.
        antwort = await fetch(this.basis + "/" + thema, { method: "POST", body: text, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" });
      } catch (e) {
        throw new RelayFehler("Keine Internetverbindung zum Vermittler (ntfy.sh).");
      }
      this._pruefe(antwort);
      try { return (await antwort.json()).id || null; } catch (e) { return null; }
    }
    static _zeile(zeile) {
      try {
        const d = JSON.parse(zeile);
        if (d && d.event === "message" && typeof d.message === "string") return { id: String(d.id || ""), zeit: d.time || 0, text: d.message };
      } catch (e) { /* Zeile überspringen */ }
      return null;
    }
    /** Sofort alles Vorhandene seit `seit` (ohne zu warten). */
    async abfragen(thema, seit) {
      let antwort;
      try {
        antwort = await fetch(this.basis + "/" + thema + "/json?poll=1&since=" + encodeURIComponent(seit || "all"), { cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" });
      } catch (e) {
        throw new RelayFehler("Keine Internetverbindung zum Vermittler (ntfy.sh).");
      }
      this._pruefe(antwort);
      return (await antwort.text()).split("\n").map(NtfyRelay._zeile).filter(Boolean);
    }
    /** Wartet höchstens `wartenMs` auf neue Nachrichten nach `seit` (Datenstrom). */
    async empfangen(thema, seit, wartenMs, abbruch) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), wartenMs);
      const weiter = () => ctrl.abort();
      if (abbruch) abbruch.addEventListener("abort", weiter, { once: true });
      const ergebnis = [];
      try {
        let antwort;
        try {
          antwort = await fetch(this.basis + "/" + thema + "/json?since=" + encodeURIComponent(seit || "all"), { signal: ctrl.signal, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" });
        } catch (e) {
          if (ctrl.signal.aborted) return ergebnis;
          throw new RelayFehler("Keine Internetverbindung zum Vermittler (ntfy.sh).");
        }
        this._pruefe(antwort);
        const leser = antwort.body.getReader();
        const textDec = new TextDecoder();
        let puffer = "";
        try {
          for (;;) {
            const { value, done } = await leser.read();
            if (done) break;
            puffer += textDec.decode(value, { stream: true });
            let i;
            while ((i = puffer.indexOf("\n")) >= 0) {
              const n = NtfyRelay._zeile(puffer.slice(0, i));
              puffer = puffer.slice(i + 1);
              if (n) ergebnis.push(n);
            }
            if (ergebnis.length) break;
          }
        } catch (e) {
          if (!ctrl.signal.aborted) throw new RelayFehler("Verbindung zum Vermittler (ntfy.sh) abgebrochen.");
        } finally {
          try { ctrl.abort(); } catch (e) { /* egal */ }
        }
        return ergebnis;
      } finally {
        clearTimeout(timer);
        if (abbruch) abbruch.removeEventListener("abort", weiter);
      }
    }
  }

  // -- Nur LAN (wie ist_lan_adresse / filtere_sdp in signal.py) ---------------------------
  function ipv4Bytes(text) {
    const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(text);
    if (!m) return null;
    const b = m.slice(1).map((t) => (t.length > 1 && t[0] === "0" ? NaN : Number(t)));
    return b.every((x) => x >= 0 && x <= 255) ? b : null;
  }
  function ipv6Bytes(text) {
    if (!/^[0-9A-Fa-f:.]+$/.test(text) || text.split("::").length > 2) return null;
    let v4 = null;
    let s = text;
    if (s.indexOf(".") >= 0) { // z.B. ::ffff:192.168.0.2
      const i = s.lastIndexOf(":");
      v4 = ipv4Bytes(s.slice(i + 1));
      if (!v4) return null;
      s = s.slice(0, i + 1);
      if (!s.endsWith("::")) s = s.slice(0, -1);
    }
    const ziel = v4 ? 6 : 8;
    const teile = (x) => (x === "" ? [] : x.split(":"));
    const h = s.split("::");
    let gruppen;
    if (h.length === 2) {
      const l = teile(h[0]), r = teile(h[1]);
      const fehlt = ziel - l.length - r.length;
      if (fehlt < 1) return null;
      gruppen = l.concat(new Array(fehlt).fill("0"), r);
    } else {
      gruppen = teile(s);
      if (gruppen.length !== ziel) return null;
    }
    const out = [];
    for (const g of gruppen) {
      if (!/^[0-9A-Fa-f]{1,4}$/.test(g)) return null;
      const n = parseInt(g, 16);
      out.push(n >> 8, n & 255);
    }
    return v4 ? out.concat(v4) : out;
  }
  /** RFC1918, 169.254/16, fc00::/7, fe80::/10 oder mDNS-Name (*.local). Alles andere: nein. */
  function istLanAdresse(adresse) {
    let a = String(adresse || "").trim().replace(/^\[/, "").replace(/\]$/, "");
    if (a.toLowerCase().endsWith(".local")) return /^[A-Za-z0-9-]{1,63}\.local$/.test(a);
    a = a.split("%")[0];
    const v4 = ipv4Bytes(a);
    if (v4) {
      return v4[0] === 10 || (v4[0] === 172 && v4[1] >= 16 && v4[1] <= 31) || (v4[0] === 192 && v4[1] === 168)
        || (v4[0] === 169 && v4[1] === 254);
    }
    const v6 = ipv6Bytes(a);
    if (!v6) return false;
    const gemappt = v6.slice(0, 10).every((x) => x === 0) && v6[10] === 255 && v6[11] === 255;
    if (gemappt) return istLanAdresse(v6.slice(12).join("."));
    return (v6[0] & 0xfe) === 0xfc || (v6[0] === 0xfe && (v6[1] & 0xc0) === 0x80);
  }
  /** Eine "candidate:"-Zeile: nur Host-Kandidaten mit LAN-Adresse. */
  function kandidatErlaubt(zeile, pruefung) {
    const teile = String(zeile || "").trim().split(/\s+/);
    if (teile.length < 8 || teile[6] !== "typ") return false;
    return teile[7] === "host" && (pruefung || istLanAdresse)(teile[4]);
  }
  /** Entfernt Kandidaten außerhalb des LANs -> {sdp, behalten, verworfen}. */
  function filtereSdp(sdp, pruefung) {
    let behalten = 0, verworfen = 0;
    const zeilen = [];
    for (const zeile of String(sdp || "").replace(/\r\n/g, "\n").split("\n")) {
      if (zeile.indexOf("a=candidate:") === 0) {
        if (kandidatErlaubt(zeile.slice(2), pruefung)) behalten += 1;
        else { verworfen += 1; continue; }
      }
      zeilen.push(zeile);
    }
    return { sdp: zeilen.join("\r\n").replace(/[\r\n]+$/, "") + "\r\n", behalten, verworfen };
  }

  global.NovaSignal = {
    PROTOKOLL, MAX_TEXT, SignalFehler, RelayFehler, b64u, b64uDekodieren, leseKopplung, kopplungAusLink,
    packen, entpacken, Kanal, codeNormalisieren, codeKopplung, NtfyRelay, istLanAdresse, kandidatErlaubt, filtereSdp,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
