"""Handy-Seite (web/kamera/v1): statische Pruefungen + Protokoll-Gegenprobe mit Node.

Die Gegenprobe laedt signal.js in Node (falls installiert) und prueft, dass Browser- und
Python-Seite dieselben Nachrichten verstehen (AES-GCM, deflate-raw, Kurzcode).
"""
import hashlib
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
SEITE = WEB / "kamera" / "v1"
NODE = shutil.which("node")


class _Sammler(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.skript_inhalt = []
        self._im_skript = False

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        self._im_skript = tag == "script"

    def handle_endtag(self, tag):
        if tag == "script":
            self._im_skript = False

    def handle_data(self, data):
        if self._im_skript and data.strip():
            self.skript_inhalt.append(data)


def _parse(pfad):
    sammler = _Sammler()
    sammler.feed(pfad.read_text(encoding="utf-8"))
    return sammler


def _csp(sammler):
    for tag, attrs in sammler.tags:
        if tag == "meta" and (attrs.get("http-equiv") or "").lower() == "content-security-policy":
            return {teil.split()[0]: teil.split()[1:] for teil in attrs["content"].split(";") if teil.strip()}
    return None


@pytest.mark.parametrize("seite", [SEITE / "index.html", WEB / "index.html"])
def test_csp_streng_und_keine_inline_skripte(seite):
    sammler = _parse(seite)
    csp = _csp(sammler)
    assert csp is not None, "CSP-Meta-Tag fehlt"
    assert csp["default-src"] == ["'none'"]
    alles = " ".join(" ".join(v) for v in csp.values())
    assert "unsafe-inline" not in alles and "unsafe-eval" not in alles and "*" not in alles.split()
    assert csp["base-uri"] == ["'none'"] and csp["form-action"] == ["'none'"]
    # CSP muss vor allem anderen (Skripte/Stile) im Kopf stehen
    erste = [t for t, a in sammler.tags if t in ("meta", "script", "link", "style")]
    assert erste[0] == "meta" and sammler.tags[[t for t, _ in sammler.tags].index("meta")][1].get("charset")
    assert not sammler.skript_inhalt, "Inline-Skript gefunden"
    for tag, attrs in sammler.tags:
        assert tag != "style", "Inline-<style> ist durch die CSP verboten"
        assert "style" not in attrs, f"style-Attribut an <{tag}>"
        assert not any(name.startswith("on") for name in attrs), f"Event-Attribut an <{tag}>"
        if tag == "script":
            assert attrs.get("src") and not re.match(r"^(https?:)?//", attrs["src"])


def test_kamera_csp_erlaubt_nur_ntfy():
    csp = _csp(_parse(SEITE / "index.html"))
    assert csp["script-src"] == ["'self'"]
    assert set(csp["connect-src"]) == {"'self'", "https://ntfy.sh"}
    assert csp["worker-src"] == ["'self'"]


def test_lokale_verweise_existieren():
    for seite in (SEITE / "index.html", WEB / "index.html"):
        for tag, attrs in _parse(seite).tags:
            for name in ("src", "href"):
                ziel = attrs.get(name)
                if not ziel or re.match(r"^(https?:|mailto:|#)", ziel):
                    continue
                pfad = (seite.parent / ziel.split("#")[0].split("?")[0])
                assert pfad.exists(), f"{seite.name}: {ziel} fehlt"


def test_texte_mit_umlauten_und_pflichtelemente():
    html = (SEITE / "index.html").read_text(encoding="utf-8")
    for text in ("Nova-Kamera", "Kamera starten", "Stopp", "Nova sieht zu", "QR-Code scannen",
                 "Handy ans Ladekabel, Bildschirm an lassen", "selben WLAN"):
        assert text in html
    js = (SEITE / "kamera.js").read_text(encoding="utf-8")
    for text in ("Verbinde mit Nova \u2026", "Mit Nova verbunden \u2713", "Handy und PC m\u00fcssen im selben WLAN sein"):
        assert text in js
    assert 'lang="de"' in html


def test_manifest_gueltig():
    manifest = json.loads((SEITE / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "Nova-Kamera" and manifest["display"] == "standalone"
    assert manifest["start_url"] == "./" and manifest["scope"] == "./"
    PIL = pytest.importorskip("PIL.Image")
    groessen = set()
    for icon in manifest["icons"]:
        pfad = SEITE / icon["src"]
        assert pfad.exists(), icon["src"]
        if icon["type"] == "image/png":
            with PIL.open(pfad) as bild:
                assert f"{bild.size[0]}x{bild.size[1]}" == icon["sizes"]
            groessen.add(icon["sizes"])
    assert {"192x192", "512x512"} <= groessen
    assert any(i.get("purpose") == "maskable" for i in manifest["icons"])


def test_service_worker_huelle_existiert():
    sw = (SEITE / "sw.js").read_text(encoding="utf-8")
    liste = re.search(r"const HUELLE = \[(.*?)\];", sw, re.S).group(1)
    eintraege = re.findall(r'"([^"]+)"', liste)
    assert "kamera.js" in eintraege and "signal.js" in eintraege
    for eintrag in eintraege:
        if eintrag != "./":
            assert (SEITE / eintrag).exists(), eintrag
    assert "ntfy" not in liste


def test_keine_fremden_server_in_skripten():
    for datei in ("kamera.js", "signal.js", "sw.js"):
        text = (SEITE / datei).read_text(encoding="utf-8")
        urls = set(re.findall(r"https?://[^\s\"'`)]+", text))
        assert urls <= {"https://ntfy.sh"}, (datei, urls)
        assert "eval(" not in text and "new Function" not in text and "innerHTML" not in text


def test_testhaken_nur_auf_localhost():
    js = (SEITE / "kamera.js").read_text(encoding="utf-8")
    assert re.search(r'const LOKAL = \["localhost", "127\.0\.0\.1", "\[::1\]"\]\.indexOf\(location\.hostname\) >= 0;', js)
    assert re.search(r'const RELAY_BASIS = LOKAL && new URLSearchParams\(location\.search\)\.get\("relay"\) === "lokal"'
                     r'\s*\? location\.origin \+ "/__relay" : "https://ntfy\.sh";', js)
    assert js.count('"/__relay"') == 1


def test_vendor_jsqr_herkunft():
    herkunft = (SEITE / "vendor" / "HERKUNFT.txt").read_text(encoding="utf-8")
    soll = re.search(r"SHA-256 \(jsQR\.js\):\s+([0-9a-f]{64})", herkunft).group(1)
    assert hashlib.sha256((SEITE / "vendor" / "jsQR.js").read_bytes()).hexdigest() == soll
    assert "Apache License" in (SEITE / "vendor" / "jsQR-LICENSE.txt").read_text(encoding="utf-8")


def test_pages_workflow():
    text = (WEB.parent / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    for teil in ("actions/configure-pages@v", "actions/upload-pages-artifact@v", "actions/deploy-pages@v",
                 "pages: write", "id-token: write", "workflow_dispatch", "web/**", "concurrency:",
                 "ccr-cfa1ff8c-wgsyxb"):
        assert teil in text


@pytest.mark.skipif(not NODE, reason="node fehlt")
@pytest.mark.parametrize("datei", ["kamera.js", "signal.js", "sw.js", "vendor/jsQR.js"])
def test_node_check(datei):
    ergebnis = subprocess.run([NODE, "--check", str(SEITE / datei)], capture_output=True, text=True, timeout=60)
    assert ergebnis.returncode == 0, ergebnis.stderr


_GEGENPROBE = r"""
require(process.argv[2]);
const S = globalThis.NovaSignal;
(async () => {
  const ein = JSON.parse(require("fs").readFileSync(0, "utf8"));
  const k = S.kopplungAusLink(ein.link, Date.now() / 1000);
  const handy = new S.Kanal(k, "h");
  const raus = {};
  const m = await handy.oeffne(ein.von_nova);
  raus.typ = m.typ; raus.sdp = m.daten.sdp; raus.umlaut = m.daten.umlaut;
  raus.echo = await handy.oeffne(await handy.verpacke("x", {}));  // eigene -> null
  try { await handy.oeffne(ein.von_nova); raus.wiederholung = "angenommen"; } catch (e) { raus.wiederholung = e.message; }
  try { await new S.Kanal(S.leseKopplung(ein.fremd), "h").oeffne(ein.von_nova); raus.fremd = "angenommen"; }
  catch (e) { raus.fremd = e.message; }
  raus.angebot = await handy.verpacke("angebot", { sdp: ein.sdp, g: "geraet1" });
  raus.klein = await handy.verpacke("tschuess", { g: "geraet1" });
  const ck = await S.codeKopplung(ein.code.toLowerCase());
  raus.code_thema = ck.thema;
  const cm = await new S.Kanal(ck, "h").oeffne(ein.code_text);
  raus.code_payload = cm.daten.p;
  raus.thema = k.thema;
  process.stdout.write(JSON.stringify(raus));
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
"""


@pytest.mark.skipif(not NODE, reason="node fehlt")
def test_gegenprobe_browser_und_python(tmp_path):
    pytest.importorskip("cryptography")
    from assistant.kamera import signal as sig
    from tests.test_kamera_signal import SDP_ANGEBOT

    kopplung = sig.Kopplung.neu()
    nova = sig.Kanal(kopplung, "n")
    code = sig.neuer_code()
    _, code_text = sig.code_nachricht(kopplung, code)
    ein = {
        "link": kopplung.link(),
        "von_nova": nova.verpacke("antwort", {"sdp": SDP_ANGEBOT, "umlaut": "Gr\u00fc\u00dfe \u00e4\u00f6\u00fc \u00df \u2713"}),
        "fremd": sig.Kopplung.neu().payload(),
        "sdp": SDP_ANGEBOT,
        "code": code,
        "code_text": code_text,
    }
    skript = tmp_path / "gegenprobe.js"
    skript.write_text(_GEGENPROBE, encoding="utf-8")
    ergebnis = subprocess.run([NODE, str(skript), str(SEITE / "signal.js")], input=json.dumps(ein),
                              capture_output=True, text=True, timeout=120, encoding="utf-8")
    assert ergebnis.returncode == 0, ergebnis.stderr
    raus = json.loads(ergebnis.stdout)
    assert raus["thema"] == kopplung.thema
    assert raus["typ"] == "antwort" and raus["sdp"] == SDP_ANGEBOT and raus["umlaut"] == "Gr\u00fc\u00dfe \u00e4\u00f6\u00fc \u00df \u2713"
    assert raus["echo"] is None
    assert "wiederholt" in raus["wiederholung"]
    assert "ung\u00fcltig" in raus["fremd"]
    angebot = nova.oeffne(raus["angebot"])
    assert angebot.typ == "angebot" and angebot.daten == {"sdp": SDP_ANGEBOT, "g": "geraet1"}
    assert len(raus["angebot"]) < 4096
    assert sig.entschluesseln(kopplung.schluessel, kopplung.thema, raus["angebot"])[0] == 1  # deflate-raw
    assert nova.oeffne(raus["klein"]).typ == "tschuess"
    assert raus["code_thema"] == sig.code_kopplung(code, 0).thema
    assert raus["code_payload"] == kopplung.payload()


_LAN_PROBE = r"""
require(process.argv[2]);
const S = globalThis.NovaSignal;
const ein = JSON.parse(require("fs").readFileSync(0, "utf8"));
const raus = {
  lan: ein.faelle.map((a) => S.istLanAdresse(a)),
  sdp: S.filtereSdp(ein.sdp),
  oeffentlich: S.filtereSdp(ein.oeffentlich),
  srflx: S.kandidatErlaubt("candidate:9 1 udp 1 192.168.0.9 3478 typ srflx raddr 192.168.0.2 rport 1"),
  relay: S.kandidatErlaubt("candidate:9 1 udp 1 10.0.0.9 3478 typ relay raddr 0.0.0.0 rport 0"),
  kurz: S.kandidatErlaubt("candidate:9 1 udp 1 10.0.0.9"),
};
process.stdout.write(JSON.stringify(raus));
"""


@pytest.mark.skipif(not NODE, reason="node fehlt")
def test_lan_filter_im_browser_wie_in_python(tmp_path):
    """Die Handy-Seite prueft Novas Antwort mit demselben LAN-Filter wie Nova das Angebot."""
    from assistant.kamera import signal as sig
    from tests.test_kamera_signal import LAN_FAELLE, SDP_ANGEBOT

    oeffentlich = "\r\n".join(z for z in SDP_ANGEBOT.split("\r\n")
                               if not z.startswith("a=candidate:") or "2003:e3:" in z)
    ein = {"faelle": [a for a, _ in LAN_FAELLE], "sdp": SDP_ANGEBOT, "oeffentlich": oeffentlich}
    skript = tmp_path / "lanprobe.js"
    skript.write_text(_LAN_PROBE, encoding="utf-8")
    ergebnis = subprocess.run([NODE, str(skript), str(SEITE / "signal.js")], input=json.dumps(ein),
                              capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert ergebnis.returncode == 0, ergebnis.stderr
    raus = json.loads(ergebnis.stdout)
    for (adresse, soll), js in zip(LAN_FAELLE, raus["lan"]):
        assert js is soll, f"signal.js: {adresse!r} -> {js}, erwartet {soll}"
        assert sig.ist_lan_adresse(adresse) is soll
    py_sdp, py_behalten, py_verworfen = sig.filtere_sdp(SDP_ANGEBOT)
    assert raus["sdp"] == {"sdp": py_sdp, "behalten": py_behalten, "verworfen": py_verworfen}
    assert raus["oeffentlich"]["behalten"] == 0 and raus["oeffentlich"]["verworfen"] == 2
    assert "a=candidate:" not in raus["oeffentlich"]["sdp"]
    assert raus["srflx"] is False and raus["relay"] is False and raus["kurz"] is False


def test_handy_prueft_antwort_und_gewaehltes_paar():
    """Statische Absicherung der LAN-Pruefungen in kamera.js (Verhalten: Spike mit Chromium)."""
    js = (SEITE / "kamera.js").read_text(encoding="utf-8")
    # Antwort wird gefiltert, ohne LAN-Kandidaten abgelehnt
    assert re.search(r"const gefiltert = S\.filtereSdp\(m\.daten\.sdp\);\s*"
                     r"if \(!gefiltert\.behalten\) throw new NutzerFehler\(TEXTE\.nichtLan\);\s*"
                     r"await pc\.setRemoteDescription\(\{ type: \"answer\", sdp: gefiltert\.sdp \}\);", js)
    assert js.count("setRemoteDescription(") == 1
    # Bild erst nach der Pruefung des gewaehlten Paars (getStats)
    assert 'pc.addTransceiver("video"' in js and "addTransceiver(spur" not in js
    assert "if (z.sender && z.geprueft) await z.sender.replaceTrack(spur);" in js
    assert js.count("replaceTrack(") == 1
    assert "pc.getStats()" in js and "selectedCandidatePairId" in js and "S.istLanAdresse(a)" in js
    assert "if (!z.geprueft) { lanPruefen(pc); return; }" in js
    # gleiche Kopplung -> gleiche Geraete-ID (sonst "besetzt" nach erneutem Scannen)
    assert "gespeicherteGeraeteId(kopplung.payload)" in js
    # neuer QR-Link im offenen Tab (nur Fragment geaendert) wird neu geladen statt ignoriert
    assert re.search(r'addEventListener\("hashchange".*?location\.reload\(\)', js, re.S)
