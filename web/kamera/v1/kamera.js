/*
 * Nova-Kamera – Handy-Seite. Das Handy ist der WebRTC-Anbieter: Videospur + DataChannel
 * "steuerung". Signalisierung verschlüsselt über ntfy.sh (siehe signal.js), Video direkt im WLAN.
 *
 * Datenschutz: keine externen Skripte, keine Statistik. Der Kopplungs-Schlüssel steht nur im
 * URL-Fragment (wird sofort aus der Adresszeile entfernt) und im sessionStorage dieses Tabs.
 */
(function () {
  "use strict";

  const S = window.NovaSignal;
  const $ = (id) => document.getElementById(id);
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));

  // Test-Hilfe NUR auf dem eigenen Rechner (localhost): lokaler Ersatz-Vermittler unter
  // /__relay (gleicher Ursprung). Auf GitHub Pages ist das unmöglich (Hostname passt nie).
  const LOKAL = ["localhost", "127.0.0.1", "[::1]"].indexOf(location.hostname) >= 0;
  const RELAY_BASIS = LOKAL && new URLSearchParams(location.search).get("relay") === "lokal"
    ? location.origin + "/__relay" : "https://ntfy.sh";
  const SPEICHER = "nova-kamera-kopplung";
  const KULANZ_S = 120;           // Handy-Uhr darf etwas falsch gehen
  const WIEDER_S = 15 * 60;       // so lange darf ein Tab nach Ablauf neu verbinden

  const TEXTE = {
    wlan: "Keine Verbindung zu Nova. Handy und PC müssen im selben WLAN sein (kein Gäste-WLAN, kein mobiles Netz).",
    verloren: "Verbindung zu Nova verloren. Tippe auf „Neu verbinden“.",
    besetzt: "Nova ist schon mit einem anderen Handy verbunden.",
    keineAntwort: "Nova antwortet nicht. Läuft Nova am PC und zeigt noch den QR-Code? Sonst bitte neu koppeln.",
    abgelaufen: "Der QR-Code ist abgelaufen. Bitte in Nova einen neuen anzeigen lassen.",
    ungueltig: "Dieser Link ist ungültig. Bitte den QR-Code in Nova neu scannen.",
    altBrowser: "Dieser Browser kann das leider nicht. Bitte Safari oder Chrome auf den neuesten Stand bringen.",
    unsicher: "Die Kamera geht nur über eine sichere Verbindung (https).",
    nichtLan: "Verbindung abgelehnt: Die Gegenstelle ist nicht in deinem WLAN. Bitte den QR-Code in Nova neu scannen.",
  };

  class NutzerFehler extends Error {}

  const ui = {
    badge: $("badge"), status: $("status"),
    ohne: $("ohne-kopplung"), scanner: $("scanner"), gekoppelt: $("gekoppelt"),
    btnScannen: $("btn-scannen"), btnScanAbbrechen: $("btn-scan-abbrechen"), scanVideo: $("scan-video"),
    codeEingabe: $("code-eingabe"), btnCode: $("btn-code"),
    vorschau: $("vorschau"), video: $("video"),
    btnStart: $("btn-start"), btnWechseln: $("btn-wechseln"), btnStopp: $("btn-stopp"),
  };

  const z = {
    kopplung: null, kanal: null, relay: new S.NtfyRelay(RELAY_BASIS), geraet: null,
    pc: null, dc: null, sender: null, geprueft: false, strom: null, seite: "environment", lauf: 0, scanLauf: 0,
    verbunden: false, aktiv: false, wachBleiben: false, wakeLock: null, pingTimer: null, abbruch: null,
  };

  // -- Anzeige -----------------------------------------------------------------------------
  function status(text, art) {
    ui.status.textContent = text || "";
    ui.status.className = "status" + (art ? " " + art : "");
  }
  function zeige(bereich) {
    ui.ohne.hidden = bereich !== "ohne";
    ui.scanner.hidden = bereich !== "scanner";
    ui.gekoppelt.hidden = bereich !== "gekoppelt";
  }
  function liveAnzeige(an) {
    ui.badge.hidden = !an;
    ui.btnStart.hidden = an;
    ui.btnWechseln.hidden = !an;
    ui.btnStopp.hidden = !(an || z.aktiv);
  }
  function kameraFehlerText(e) {
    const name = e && e.name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      return "Kamera-Zugriff wurde verweigert. Erlaube die Kamera für diese Seite in den Browser-Einstellungen und lade die Seite neu.";
    }
    if (name === "NotFoundError" || name === "OverconstrainedError") return "Keine passende Kamera gefunden.";
    if (name === "NotReadableError" || name === "AbortError") return "Die Kamera wird gerade von einer anderen App benutzt. Schließe die andere App und versuche es noch einmal.";
    if (e instanceof NutzerFehler || (e && (e.name === "SignalFehler" || e.name === "RelayFehler"))) return e.message;
    return "Etwas ist schiefgegangen: " + ((e && e.message) || "unbekannter Fehler") + ".";
  }

  // -- Kopplung ----------------------------------------------------------------------------
  function jetztSek() { return Date.now() / 1000; }
  function zufallsId() { return S.b64u(crypto.getRandomValues(new Uint8Array(9))); }

  function gespeicherteGeraeteId(payload) {
    // Dieselbe Kopplung erneut gescannt/geöffnet: gleiche Geräte-ID, sonst hielte Nova uns für ein zweites Handy.
    try {
      const d = JSON.parse(sessionStorage.getItem(SPEICHER) || "null");
      if (d && d.p === payload && typeof d.g === "string" && d.g) return d.g;
    } catch (e) { /* nichts gespeichert */ }
    return null;
  }
  function uebernehme(kopplung, geraet) {
    z.kopplung = kopplung;
    z.kanal = new S.Kanal(kopplung, "h");
    // Folgenummern steigen auch über ein Neuladen hinweg (Nova lehnt Wiederholungen ab).
    z.kanal.seq = Math.floor(Date.now() / 100);
    z.geraet = geraet || gespeicherteGeraeteId(kopplung.payload) || zufallsId();
    try { sessionStorage.setItem(SPEICHER, JSON.stringify({ p: kopplung.payload, g: z.geraet })); } catch (e) { /* privat */ }
  }
  function kopplungPruefen(k, kulanz) {
    if (jetztSek() - (kulanz || KULANZ_S) > k.ablauf) throw new S.SignalFehler(TEXTE.abgelaufen);
    return k;
  }
  /** Gescannter Text -> Kopplung (nur Nova-Kamera-Links), sonst null. */
  function kopplungAusText(text) {
    try {
      const url = new URL(text);
      if (url.protocol !== "https:" && !LOKAL) return null;
      if (!/\/kamera\/v1\/(index\.html)?$/.test(url.pathname)) return null;
      return S.kopplungAusLink(text);
    } catch (e) {
      return null;
    }
  }
  function kopplungLaden() {
    const hash = location.hash || "";
    if (hash.indexOf("p=") >= 0) {
      // Schlüssel sofort aus Adresszeile/Verlauf entfernen.
      try { history.replaceState(null, "", location.pathname + location.search); } catch (e) { /* egal */ }
      const k = S.kopplungAusLink(hash);
      kopplungPruefen(k);
      uebernehme(k);
      return true;
    }
    try {
      const roh = sessionStorage.getItem(SPEICHER);
      if (roh) {
        const d = JSON.parse(roh);
        const k = S.leseKopplung(d.p);
        if (jetztSek() - WIEDER_S <= k.ablauf) { uebernehme(k, d.g); return true; }
        sessionStorage.removeItem(SPEICHER);
      }
    } catch (e) { /* nichts gespeichert */ }
    return false;
  }

  // -- Kamera ------------------------------------------------------------------------------
  async function kameraHolen(seite) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new NutzerFehler(TEXTE.unsicher);
    const wunsch = {
      audio: false,
      video: { facingMode: { ideal: seite }, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 15, max: 15 } },
    };
    try {
      return await navigator.mediaDevices.getUserMedia(wunsch);
    } catch (e) {
      if (e && e.name === "OverconstrainedError") {
        return navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: seite } } });
      }
      throw e;
    }
  }
  function kameraAus() {
    if (z.strom) z.strom.getTracks().forEach((t) => t.stop());
    z.strom = null;
    ui.video.srcObject = null;
    ui.vorschau.hidden = true;
  }
  function vorschauZeigen() {
    ui.video.srcObject = z.strom;
    ui.vorschau.hidden = false;
    ui.vorschau.classList.toggle("gespiegelt", z.seite === "user");
    const p = ui.video.play();
    if (p && p.catch) p.catch(() => {});
  }
  function spurVorbereiten(spur) {
    try { spur.contentHint = "detail"; } catch (e) { /* alter Browser */ }
    spur.addEventListener("ended", () => {
      if (z.aktiv && document.visibilityState === "visible") kameraErneuern();
    });
  }
  async function kameraErneuern() {
    // z.B. nach dem Sperren des Bildschirms (iOS beendet dann die Kamera)
    if (!z.aktiv) return;
    try {
      if (z.strom) z.strom.getTracks().forEach((t) => t.stop());
      z.strom = await kameraHolen(z.seite);
      const spur = z.strom.getVideoTracks()[0];
      spurVorbereiten(spur);
      await spurSenden(spur);
      vorschauZeigen();
    } catch (e) {
      status(kameraFehlerText(e), "schlecht");
    }
  }
  /** Bild erst senden, wenn geprüft ist, dass die Verbindung im LAN bleibt. */
  async function spurSenden(spur) {
    if (z.sender && z.geprueft) await z.sender.replaceTrack(spur);
  }

  // -- Wachhalten --------------------------------------------------------------------------
  async function wachHalten(an) {
    z.wachBleiben = an;
    if (!an) {
      if (z.wakeLock) { try { await z.wakeLock.release(); } catch (e) { /* egal */ } }
      z.wakeLock = null;
      return;
    }
    if (!("wakeLock" in navigator) || z.wakeLock || document.visibilityState !== "visible") return;
    try {
      z.wakeLock = await navigator.wakeLock.request("screen");
      z.wakeLock.addEventListener("release", () => { z.wakeLock = null; });
    } catch (e) { /* z.B. Stromsparmodus – Hinweis steht auf der Seite */ }
  }

  // -- WebRTC ------------------------------------------------------------------------------
  function codecWahl(transceiver) {
    // Nur VP8 und H.264 (das kann Nova/aiortc) – hält das Angebot außerdem klein (< 4 KB).
    try {
      if (!transceiver.setCodecPreferences || !RTCRtpSender.getCapabilities) return;
      const alle = RTCRtpSender.getCapabilities("video").codecs;
      const vp8 = alle.filter((c) => /video\/vp8/i.test(c.mimeType));
      const h264 = alle.filter((c) => /video\/h264/i.test(c.mimeType) && /packetization-mode=1/.test(c.sdpFmtpLine || "")
        && /profile-level-id=42/.test(c.sdpFmtpLine || ""));
      const rtx = alle.filter((c) => /video\/rtx/i.test(c.mimeType));
      const liste = vp8.concat(h264, rtx);
      if (vp8.length || h264.length) transceiver.setCodecPreferences(liste);
    } catch (e) { /* Browser entscheidet selbst */ }
  }
  function schlankesSdp(sdp) {
    // TCP-Kandidaten kann Nova nicht nutzen – weglassen spart Platz.
    return sdp.split("\r\n").filter((zeile) => !(zeile.indexOf("a=candidate:") === 0 && / tcp /i.test(zeile))).join("\r\n");
  }
  function sammeln(pc, ms) {
    if (pc.iceGatheringState === "complete") return Promise.resolve();
    return new Promise((fertig) => {
      const t = setTimeout(fertig, ms);
      pc.addEventListener("icegatheringstatechange", () => {
        if (pc.iceGatheringState === "complete") { clearTimeout(t); fertig(); }
      });
    });
  }
  function schliessePc() {
    if (z.pingTimer) clearInterval(z.pingTimer);
    z.pingTimer = null;
    if (z.abbruch) { try { z.abbruch.abort(); } catch (e) { /* egal */ } }
    z.abbruch = null;
    const pc = z.pc;
    z.pc = null; z.dc = null; z.sender = null; z.geprueft = false; z.verbunden = false;
    if (pc) { try { pc.close(); } catch (e) { /* egal */ } }
  }
  function sendeDc(daten) {
    try { if (z.dc && z.dc.readyState === "open") { z.dc.send(JSON.stringify(daten)); return true; } } catch (e) { /* egal */ }
    return false;
  }
  function sendeStatus() {
    sendeDc({ t: "status", kamera: z.seite === "user" ? "vorne" : "hinten", sichtbar: document.visibilityState === "visible" });
  }

  async function verbinden() {
    schliessePc();
    const lauf = ++z.lauf;
    status("Verbinde mit Nova …");
    const pc = new RTCPeerConnection({ iceServers: [] });
    z.pc = pc;
    // Videospur ohne Bild anlegen: das Kamerabild kommt erst nach der LAN-Prüfung dazu (spurSenden).
    let tr;
    try {
      tr = pc.addTransceiver("video", { direction: "sendonly", streams: [z.strom], sendEncodings: [{ maxBitrate: 1500000, maxFramerate: 15 }] });
    } catch (e) {
      tr = pc.addTransceiver("video", { direction: "sendonly", streams: [z.strom] });
    }
    z.sender = tr.sender;
    codecWahl(tr);
    const dc = pc.createDataChannel("steuerung", { ordered: true });
    z.dc = dc;
    steuerkanal(dc, pc);
    pc.addEventListener("connectionstatechange", () => verbindungsZustand(pc));
    await pc.setLocalDescription(await pc.createOffer());
    await sammeln(pc, 4000);
    if (lauf !== z.lauf) return;
    const sdp = schlankesSdp(pc.localDescription.sdp);
    if (sdp.indexOf("a=candidate:") < 0) throw new NutzerFehler("Das Handy hat keine Netzwerkverbindung. Ist das WLAN an?");
    const text = await z.kanal.verpacke("angebot", { sdp: sdp, g: z.geraet });
    const seit = await z.relay.senden(z.kanal.thema, text);
    await aufAntwortWarten(pc, lauf, seit);
  }

  async function aufAntwortWarten(pc, lauf, seit) {
    const ende = Date.now() + 30000;
    const gesehen = new Set();
    z.abbruch = new AbortController();
    let fehlversuche = 0;
    while (Date.now() < ende && lauf === z.lauf) {
      let liste;
      try {
        liste = await z.relay.empfangen(z.kanal.thema, seit, Math.min(15000, Math.max(1000, ende - Date.now())), z.abbruch && z.abbruch.signal);
        fehlversuche = 0;
      } catch (e) {
        if (++fehlversuche > 3) throw e;
        await pause(1500);
        continue;
      }
      for (const n of liste) {
        if (n.id) { if (gesehen.has(n.id)) continue; gesehen.add(n.id); seit = n.id; }
        let m;
        try { m = await z.kanal.oeffne(n.text); } catch (e) { continue; }
        if (!m || m.daten.g !== z.geraet || lauf !== z.lauf) continue;
        if (m.typ === "antwort" && typeof m.daten.sdp === "string") {
          // Nur LAN: Kandidaten außerhalb des Heimnetzes nie verwenden (auch nicht, wenn die Antwort sie enthält).
          const gefiltert = S.filtereSdp(m.daten.sdp);
          if (!gefiltert.behalten) throw new NutzerFehler(TEXTE.nichtLan);
          await pc.setRemoteDescription({ type: "answer", sdp: gefiltert.sdp });
          setTimeout(() => {
            if (lauf === z.lauf && pc.connectionState !== "connected") {
              schliessePc();
              status(TEXTE.wlan, "schlecht");
              ui.btnStart.textContent = "Neu verbinden";
              ui.btnStart.hidden = false;
            }
          }, 25000);
          return;
        }
        if (m.typ === "besetzt") throw new NutzerFehler(TEXTE.besetzt);
        if (m.typ === "fehler") {
          const g = m.daten.grund;
          if (g === "kein-lan") throw new NutzerFehler(TEXTE.wlan);
          if (g === "pc-kein-lan") throw new NutzerFehler("Der PC ist nicht mit dem Heimnetz verbunden (WLAN/LAN prüfen).");
          if (g === "noch-verbunden") throw new NutzerFehler("Nova hängt noch an der alten Verbindung. Bitte in ein paar Sekunden noch einmal versuchen.");
          if (g === "angebot") throw new NutzerFehler("Nova versteht das Videoformat dieses Browsers nicht. Bitte einen anderen Browser versuchen.");
          throw new NutzerFehler("Nova meldet einen Fehler. Bitte neu koppeln.");
        }
      }
    }
    if (lauf === z.lauf) throw new NutzerFehler(TEXTE.keineAntwort);
  }

  function verbindungsZustand(pc) {
    if (pc !== z.pc) return;
    const stand = pc.connectionState;
    if (stand === "connected") {
      if (!z.geprueft) { lanPruefen(pc); return; }
      z.verbunden = true;
      status("Mit Nova verbunden ✓", "gut");
      liveAnzeige(true);
      wachHalten(true);
      try {
        const sender = z.sender;
        const p = sender.getParameters();
        if (p.encodings && p.encodings.length) {
          p.encodings[0].maxBitrate = 1500000;
          p.encodings[0].maxFramerate = 15;
          sender.setParameters(p).catch(() => {});
        }
      } catch (e) { /* egal */ }
    } else if (stand === "disconnected") {
      status("Verbindung wackelt … (WLAN prüfen)");
    } else if (stand === "failed" || stand === "closed") {
      const war = z.verbunden;
      schliessePc();
      liveAnzeige(false);
      ui.btnStopp.hidden = false;
      ui.btnStart.textContent = "Neu verbinden";
      status(war ? TEXTE.verloren : TEXTE.wlan, "schlecht");
    }
  }

  /** Adressen des gewählten Kandidatenpaars (Gegenseite) aus getStats(); null = (noch) unbekannt. */
  async function gewaehlteAdressen(pc) {
    const stats = await pc.getStats();
    const paare = [];
    stats.forEach((r) => {
      if (r.type === "transport" && r.selectedCandidatePairId && stats.get(r.selectedCandidatePairId)) paare.push(stats.get(r.selectedCandidatePairId));
    });
    if (!paare.length) {
      stats.forEach((r) => {
        if (r.type === "candidate-pair" && (r.selected === true || (r.nominated && r.state === "succeeded"))) paare.push(r);
      });
    }
    if (!paare.length) return null;
    const adressen = [];
    for (const paar of paare) {
      const ferne = stats.get(paar.remoteCandidateId);
      const adresse = ferne && (ferne.address || ferne.ip);
      if (!adresse) return null; // z.B. versteckte peer-reflexive Adresse
      adressen.push(adresse);
    }
    return adressen;
  }
  /** Erst wenn das gewählte Paar ins LAN zeigt, geht das Bild raus. Sonst: trennen (sicher ist sicher). */
  async function lanPruefen(pc) {
    let adressen = null;
    for (let versuch = 0; versuch < 6 && pc === z.pc; versuch++) {
      try { adressen = await gewaehlteAdressen(pc); } catch (e) { adressen = null; }
      if (adressen) break;
      await pause(500);
    }
    if (pc !== z.pc) return;
    if (!adressen || !adressen.every((a) => S.istLanAdresse(a))) {
      schliessePc();
      liveAnzeige(false);
      ui.btnStopp.hidden = false;
      ui.btnStart.textContent = "Neu verbinden";
      status(TEXTE.nichtLan, "schlecht");
      return;
    }
    z.geprueft = true;
    try { await spurSenden(z.strom.getVideoTracks()[0]); } catch (e) { /* unten sichtbar */ }
    if (pc === z.pc && pc.connectionState === "connected") verbindungsZustand(pc);
  }

  function steuerkanal(dc, pc) {
    dc.addEventListener("open", () => {
      sendeStatus();
      if (z.pingTimer) clearInterval(z.pingTimer);
      z.pingTimer = setInterval(() => sendeDc({ t: "ping" }), 10000);
    });
    dc.addEventListener("message", (ev) => {
      if (pc !== z.pc || typeof ev.data !== "string" || ev.data.length > 4096) return;
      let d;
      try { d = JSON.parse(ev.data); } catch (e) { return; }
      if (d && d.t === "stopp") beenden("Nova hat die Kamera beendet. Nova sieht nichts mehr.", false);
    });
  }

  // -- Abläufe -----------------------------------------------------------------------------
  async function starten() {
    if (!z.kopplung) return;
    ui.btnStart.disabled = true;
    try {
      z.aktiv = true;
      if (!z.strom || z.strom.getVideoTracks()[0].readyState === "ended") {
        status("Kamera wird gestartet …");
        z.strom = await kameraHolen(z.seite);
      }
      spurVorbereiten(z.strom.getVideoTracks()[0]);
      vorschauZeigen();
      ui.btnStopp.hidden = false;
      await verbinden();
    } catch (e) {
      schliessePc();
      status(kameraFehlerText(e), "schlecht");
      ui.btnStart.textContent = "Noch einmal versuchen";
      liveAnzeige(false);
    } finally {
      ui.btnStart.disabled = false;
    }
  }

  async function beenden(text, handyMeldet) {
    z.lauf++;
    z.aktiv = false;
    if (handyMeldet) {
      if (sendeDc({ t: "stopp" })) {
        await pause(200);
      } else if (z.kanal) {
        try { await z.relay.senden(z.kanal.thema, await z.kanal.verpacke("tschuess", { g: z.geraet })); } catch (e) { /* egal */ }
      }
    }
    schliessePc();
    kameraAus();
    wachHalten(false);
    liveAnzeige(false);
    ui.btnStopp.hidden = true;
    ui.btnStart.textContent = "Kamera starten";
    status(text);
  }

  async function wechseln() {
    if (!z.pc) return;
    ui.btnWechseln.disabled = true;
    const neu = z.seite === "environment" ? "user" : "environment";
    try {
      // iOS kann nur eine Kamera gleichzeitig – die alte zuerst freigeben.
      if (z.strom) z.strom.getTracks().forEach((t) => t.stop());
      let strom;
      try {
        strom = await kameraHolen(neu);
        z.seite = neu;
      } catch (e) {
        strom = await kameraHolen(z.seite);
        status("Die andere Kamera lässt sich nicht öffnen.", "schlecht");
      }
      z.strom = strom;
      const spur = strom.getVideoTracks()[0];
      spurVorbereiten(spur);
      await spurSenden(spur);
      vorschauZeigen();
      sendeStatus();
    } catch (e) {
      status(kameraFehlerText(e), "schlecht");
    } finally {
      ui.btnWechseln.disabled = false;
    }
  }

  // -- QR-Code scannen (installierte App ohne Link) ----------------------------------------
  function skriptLaden(src) {
    return new Promise((fertig, fehler) => {
      if (window.jsQR) { fertig(); return; }
      const s = document.createElement("script");
      s.src = src;
      s.onload = () => fertig();
      s.onerror = () => fehler(new NutzerFehler("Der QR-Leser lässt sich nicht laden."));
      document.head.appendChild(s);
    });
  }
  async function qrErkenner() {
    if ("BarcodeDetector" in window) {
      try {
        const formate = await window.BarcodeDetector.getSupportedFormats();
        if (formate.indexOf("qr_code") >= 0) {
          const bd = new window.BarcodeDetector({ formats: ["qr_code"] });
          return async (video) => { const r = await bd.detect(video); return r.length ? r[0].rawValue : null; };
        }
      } catch (e) { /* jsQR nehmen */ }
    }
    await skriptLaden("vendor/jsQR.js");
    const leinwand = document.createElement("canvas");
    const ctx = leinwand.getContext("2d", { willReadFrequently: true });
    return async (video) => {
      const b = video.videoWidth, h = video.videoHeight;
      if (!b || !h) return null;
      const f = Math.min(1, 800 / Math.max(b, h));
      leinwand.width = Math.round(b * f); leinwand.height = Math.round(h * f);
      ctx.drawImage(video, 0, 0, leinwand.width, leinwand.height);
      const d = ctx.getImageData(0, 0, leinwand.width, leinwand.height);
      const r = window.jsQR(d.data, d.width, d.height, { inversionAttempts: "attemptBoth" });
      return r ? r.data : null;
    };
  }
  async function scannen() {
    zeige("scanner");
    status("");
    const lauf = ++z.scanLauf;
    try {
      z.seite = "environment";
      z.strom = await kameraHolen(z.seite);
      ui.scanVideo.srcObject = z.strom;
      const p = ui.scanVideo.play();
      if (p && p.catch) p.catch(() => {});
      const erkennen = await qrErkenner();
      let falsch = false;
      while (lauf === z.scanLauf) {
        await pause(250);
        if (lauf !== z.scanLauf) return;
        if (ui.scanVideo.readyState < 2) continue;
        let text = null;
        try { text = await erkennen(ui.scanVideo); } catch (e) { text = null; }
        if (!text) continue;
        const k = kopplungAusText(text);
        if (!k) {
          if (!falsch) status("Das ist kein QR-Code von Nova.", "schlecht");
          falsch = true;
          continue;
        }
        kopplungPruefen(k);
        z.scanLauf++;
        ui.scanVideo.srcObject = null;
        uebernehme(k);
        zeige("gekoppelt");
        await starten(); // Kamera läuft schon – gleich verbinden
        return;
      }
    } catch (e) {
      if (lauf !== z.scanLauf) return;
      z.scanLauf++;
      ui.scanVideo.srcObject = null;
      kameraAus();
      zeige("ohne");
      status(kameraFehlerText(e), "schlecht");
    }
  }
  function scanAbbrechen() {
    z.scanLauf++;
    ui.scanVideo.srcObject = null;
    kameraAus();
    zeige("ohne");
    status("");
  }

  async function codeVerbinden() {
    let code;
    try { code = S.codeNormalisieren(ui.codeEingabe.value); } catch (e) { status(e.message, "schlecht"); return; }
    ui.btnCode.disabled = true;
    status("Suche den Code …");
    try {
      const ck = await S.codeKopplung(code);
      const kanal = new S.Kanal(ck, "h");
      for (let versuch = 0; versuch < 4; versuch++) {
        const liste = await z.relay.abfragen(ck.thema, "all");
        for (const n of liste) {
          let m;
          try { m = await kanal.oeffne(n.text); } catch (e) { continue; }
          if (m && m.typ === "kopplung" && typeof m.daten.p === "string") {
            const k = kopplungPruefen(S.leseKopplung(m.daten.p));
            uebernehme(k);
            ui.codeEingabe.value = "";
            zeige("gekoppelt");
            status("Gekoppelt. Tippe auf „Kamera starten“.", "gut");
            return;
          }
        }
        await pause(1500);
      }
      status("Diesen Code kennt Nova nicht (oder er ist abgelaufen). Bitte prüfen.", "schlecht");
    } catch (e) {
      status(kameraFehlerText(e), "schlecht");
    } finally {
      ui.btnCode.disabled = false;
    }
  }

  // -- Start -------------------------------------------------------------------------------
  function init() {
    if (window.top !== window.self) { // nie in fremden Seiten eingebettet laufen
      document.body.textContent = "Die Nova-Kamera funktioniert nur direkt im Browser, nicht eingebettet.";
      return;
    }
    if (!window.isSecureContext) { zeige("ohne"); status(TEXTE.unsicher, "schlecht"); return; }
    if (!S || !window.RTCPeerConnection || !window.crypto || !crypto.subtle || typeof DecompressionStream !== "function") {
      zeige("ohne"); status(TEXTE.altBrowser, "schlecht"); return;
    }
    ui.btnStart.addEventListener("click", starten);
    ui.btnStopp.addEventListener("click", () => beenden("Gestoppt. Nova sieht nichts mehr.", true));
    ui.btnWechseln.addEventListener("click", wechseln);
    ui.btnScannen.addEventListener("click", scannen);
    ui.btnScanAbbrechen.addEventListener("click", scanAbbrechen);
    ui.btnCode.addEventListener("click", codeVerbinden);
    ui.codeEingabe.addEventListener("keydown", (e) => { if (e.key === "Enter") codeVerbinden(); });
    document.addEventListener("visibilitychange", () => {
      sendeStatus();
      if (document.visibilityState === "visible") {
        if (z.wachBleiben) wachHalten(true);
        const spur = z.strom && z.strom.getVideoTracks()[0];
        if (z.aktiv && z.pc && spur && spur.readyState === "ended") kameraErneuern();
      }
    });
    window.addEventListener("pagehide", () => { sendeDc({ t: "stopp" }); });

    let gekoppelt = false;
    try {
      gekoppelt = kopplungLaden();
    } catch (e) {
      zeige("ohne");
      status(e && e.message === TEXTE.abgelaufen ? TEXTE.abgelaufen : TEXTE.ungueltig, "schlecht");
    }
    if (gekoppelt) {
      zeige("gekoppelt");
      status("Bereit. Tippe auf „Kamera starten“.");
    } else if (!ui.status.textContent) {
      zeige("ohne");
    }
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => {});

    if (LOKAL) { // nur für automatische Tests auf diesem Rechner
      window.__novaKamera = { verbunden: () => z.verbunden, status: () => ui.status.textContent, relay: RELAY_BASIS };
    }
  }

  init();
})();
