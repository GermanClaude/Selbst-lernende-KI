"""Oberflaeche (assistant/app/static): Aufbau, Vertrag mit dem Server und die reinen Hilfen.

Die Hilfen in helfer.js (Bild-Typen, Zielgroesse, eigene Bild-Adressen, Feedback-Daten,
Nachfrage-Karte, Bildgenerator-Einstellungen) laufen ohne Seite und werden hier mit Node
geprueft (ohne Node: uebersprungen). Den echten Ablauf im Fenster prueft der E2E-Test.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "assistant" / "app" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
HELFER_JS = (STATIC / "helfer.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js fehlt")

# Elemente, die app.js selbst anlegt (nicht im HTML)
_DYNAMIC_IDS = {"su-start"}


def _ids():
    return set(re.findall(r'\bid="([^"]+)"', HTML))


def _icons():
    block = APP_JS[APP_JS.index("const ICONS = {"):APP_JS.index("};", APP_JS.index("const ICONS = {"))]
    return set(re.findall(r"^\s{4}(\w+):", block, flags=re.M))


def _tag(element_id):
    m = re.search(r'<[a-z]+[^>]*\bid="' + re.escape(element_id) + r'"[^>]*>', HTML)
    assert m, element_id
    return m.group(0)


# ---------------------------------------------------------------------------
# Aufbau
# ---------------------------------------------------------------------------
def test_jedes_element_aus_app_js_steht_im_html():
    missing = set(re.findall(r"byId\('([^']+)'\)", APP_JS)) - _ids() - _DYNAMIC_IDS
    assert not missing, sorted(missing)


def test_ids_sind_eindeutig():
    ids = re.findall(r'\bid="([^"]+)"', HTML)
    doppelt = {i for i in ids if ids.count(i) > 1}
    assert not doppelt, doppelt


def test_alle_symbole_gibt_es():
    icons = _icons()
    for name in ("paperclip", "image", "star", "bug", "maximize", "chevronLeft"):
        assert name in icons
    used = set(re.findall(r'data-icon="(\w+)"', HTML)) | set(re.findall(r"icon\('(\w+)'", APP_JS))
    used |= set(re.findall(r"\['\w+', '[^']+', '(\w+)'\]", HELFER_JS))  # Feedback-Arten
    assert not used - icons, sorted(used - icons)


def test_helfer_wird_vor_app_geladen():
    scripts = re.findall(r'<script src="([^"]+)"></script>', HTML)
    assert scripts == ["/static/helfer.js", "/static/app.js", "/static/sehen.js",
                       "/static/spiel.js"]  # sehen.js: Live-Sehen, spiel.js: Spielmodus


def test_dialoge_sind_zugaenglich():
    for dlg, title in (("fdialog", "fb-title"), ("lightbox", "lb-title")):
        tag = _tag(dlg)
        assert 'role="dialog"' in tag and 'aria-modal="true"' in tag and 'tabindex="-1"' in tag
        assert f'aria-labelledby="{title}"' in tag and title in _ids()
    for group in ("fb-stars", "fb-kinds", "fp-stars", "sbi-pick"):
        assert 'role="radiogroup"' in _tag(group)
    assert 'aria-label="Angehängte Bilder"' in _tag("att-tray")
    assert 'role="alert"' in _tag("att-err") and 'role="alert"' in _tag("fb-err")
    assert "aria-label=" in _tag("attach-btn") and "aria-label=" in _tag("fp-close")
    assert 'aria-haspopup="dialog"' in _tag("sb-feedback")
    # Datei-Auswahl nur ueber die Knoepfe (nicht per Tab erreichbar, nur Bilder)
    for f in ("attach-file", "fb-file"):
        tag = _tag(f)
        assert 'type="file"' in tag and "multiple" in tag and "hidden" in tag
        assert 'accept="image/png,image/jpeg,image/gif,image/webp"' in tag


def test_neue_ebenen_sind_in_tasten_inert_und_ende_eingebunden():
    inert = APP_JS[APP_JS.index("function updateInert()"):APP_JS.index("function nextAsk()")]
    for part in ("fmodal.inert", "lbEl.inert", "const fbOpen", "const lbOpen"):
        assert part in inert
    keys = APP_JS[APP_JS.index("document.addEventListener('keydown', (e) => {\n    if (!cmodal.hidden)"):]
    assert keys.index("lbKey(e)") < keys.index("fbKey(e)") < keys.index("afkKey(e)")
    bye = APP_JS[APP_JS.index("function onBye()"):APP_JS.index("function connect()")]
    assert "fmodal.hidden = true" in bye and "lbEl.hidden = true" in bye and "fpEl.hidden = true" in bye


def test_ebenen_reihenfolge_in_css():
    z = {sel: int(v) for sel, v in re.findall(r"^\.(\w+) \{ z-index: (\d+); \}", CSS, flags=re.M)}
    assert z["smodal"] < z["fmodal"] < z["cmodal"]
    assert 95 < z["fmodal"] < 100  # ueber Jarvis/AFK, unter Rueckfragen
    lb = int(re.search(r"\.lightbox \{[^}]*z-index: (\d+)", CSS).group(1))
    assert z["fmodal"] < lb < 100


def test_dunkles_design_kennt_die_sternfarbe():
    assert CSS.count("--star:") >= 3  # hell, dunkel (System) und dunkel (gewaehlt)
    assert re.search(r':root:where\(\[data-theme="dark"\]\) \{ --star:', CSS)


# ---------------------------------------------------------------------------
# Vertrag mit dem Server (Teil E)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pfad", [
    "/api/send", "/api/feedback", "/api/feedback/gezeigt", "/api/feedback/spaeter", "/api/bilder/einstellen",
    "/api/setup",
])
def test_endpunkte_aus_dem_vertrag(pfad):
    assert f"'{pfad}'" in APP_JS


def test_ereignisse_aus_dem_vertrag():
    flow = re.search(r"const FLOW = new Set\(\[([^\]]+)\]\)", APP_JS).group(1)
    assert "'image'" in flow and "'image_progress'" in flow
    events = APP_JS[APP_JS.index("function handleEvent(ev)"):]
    for case in ("case 'image':", "case 'image_progress':", "case 'queue_returned':", "case 'user':"):
        assert case in events
    assert "ev.what === 'feedback'" in events
    assert "onUserEcho(ev)" in events and "onQueueReturned(ev)" in events
    for key in ("client_id", "ev.images", "ev.items", "state.feedback_due", "m.role === 'image'"):
        assert key in APP_JS, key
    assert "bild_erstellen: ['image', 'Erstelle ein Bild …']" in APP_JS


def test_feedback_befehle_oeffnen_den_dialog_im_fenster():
    send = APP_JS[APP_JS.index("async function send(text, fromInput, interrupt)"):]
    send = send[:send.index("\n  }\n")]
    assert "low === '/feedback'" in send and "low === '/bewertung'" in send and "openFeedback(" in send


def test_eigene_blase_bekommt_nach_dem_echo_die_server_bilder():
    # Gefunden im E2E-Test: die eigene Blase behielt die data:-Vorschauen (Speicher, kein "Speichern").
    echo = APP_JS[APP_JS.index("function onUserEcho(ev)"):]
    echo = echo[:echo.index("\n  }\n")]
    assert "serverImagesFor(own.row, imgs)" in echo
    tausch = APP_JS[APP_JS.index("function serverImagesFor(row, imgs)"):]
    tausch = tausch[:tausch.index("\n  }\n")]
    # erst tauschen, wenn alle Server-Bilder geladen sind - sonst bleibt die Vorschau
    assert "'load'" in tausch and "'error'" in tausch and "old.replaceWith(box)" in tausch


def test_leiste_baut_vorhandene_miniaturen_nicht_neu():
    # Gefunden im E2E-Test: jede Aenderung baute alle Miniaturen neu (alle ploppten erneut auf).
    tray = APP_JS[APP_JS.index("function makeTray(o)"):]
    render = tray[tray.index("function render()"):]
    render = render[:render.index("\n    }\n")]
    assert "o.list.replaceChildren()" not in render
    assert "nodes.get(s.id)" in render and "nodes.set(s.id" in render


# ---------------------------------------------------------------------------
# Datenschutz & Sicherheit
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["app.js", "helfer.js", "sehen.js", "index.html", "app.css"])
def test_keine_email_adresse_und_keine_fremden_abrufe(name):
    text = (STATIC / name).read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", text)
    assert "script.google.com" not in text
    assert not re.search(r"fetch\(\s*['\"`]https?:", text)
    assert "createObjectURL" not in text and "'blob:" not in text  # CSP: kein blob:


def test_nur_harmlose_werte_im_browser_speicher():
    keys = set(re.findall(r"(?:local|session)Storage\.setItem\('([^']+)'", APP_JS))
    assert keys <= {"ki-theme", "ki-stimme", "ki-tour-spaeter"}, keys


def test_bild_adressen_nur_ueber_die_pruefung():
    # Bilder vom Server kommen nur ueber HL.bildUrl (eigene Adresse + Token) in die Seite
    assert "HL.bildUrl(" in APP_JS
    assert not re.search(r"\.src\s*=\s*ev\.url", APP_JS)
    assert r"/^\/api\/bild\/[he]\/[A-Za-z0-9_-]{1,100}\.(?:png|jpe?g|webp|gif)$/" in HELFER_JS


def test_token_feld_ist_ein_passwortfeld_und_wird_geleert():
    tag = _tag("sbi-token")
    assert 'type="password"' in tag and 'autocomplete="off"' in tag
    clear = APP_JS[APP_JS.index("function sbiClear(keepResult)"):]
    assert "sbiToken.value = ''" in clear[:400]
    assert "if (!onlyBrain) sbiClear();" in APP_JS


def test_sichtbare_texte_mit_umlauten():
    for text in (
        "Feedback &amp; Bewertung", "Jetzt senden", "Abbrechen",
        "Was gefällt dir? Was können wir besser machen? Fehler bitte genau beschreiben.",
        "Deine E-Mail für Rückfragen", "Text, Bewertung, App-Version und Bilder werden per E-Mail an den Entwickler "
        "geschickt. Deine Sterne zählen anonym zum Durchschnitt. Bitte keine Passwörter oder privaten Daten.",
        "Meine Bewertung öffentlich zeigen", "Name für die Rezension", "Rezensionen ansehen",
        "Wie gefällt dir Nova?", "Später",
        "Bilder (optional)", "einen Ausschnitt kopieren und hier mit", "Bilder hier ablegen",
    ):
        assert text in HTML, text
    for text in ("Lob/Bewertung", "Fehler", "Idee", "Sonstiges", "AI Horde – kostenlos, ohne Anmeldung, manchmal kurze Wartezeit"):
        assert text in HELFER_JS, text
    for text in ("Create a Workers AI API Token", "Use REST API", "dash.cloudflare.com", "Groß ansehen", "Speichern"):
        assert text in APP_JS, text


# ---------------------------------------------------------------------------
# JavaScript: Syntax und die reinen Hilfen (Node)
# ---------------------------------------------------------------------------
@needs_node
@pytest.mark.parametrize("name", ["app.js", "helfer.js", "sehen.js"])
def test_javascript_syntax(name):
    r = subprocess.run([NODE, "--check", str(STATIC / name)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


_JS_TESTS = r"""
const assert = require('assert');
const H = require(process.argv[2]);
const eq = assert.deepStrictEqual;

// --- erlaubte Typen ---
eq(H.typ('image/png'), 'image/png');
eq(H.typ('IMAGE/JPEG'), 'image/jpeg');
eq(H.typ('image/jpg'), 'image/jpeg');
eq(H.typ('image/webp; x=1'), 'image/webp');
eq(H.typ('', 'Foto.JPG'), 'image/jpeg');
eq(H.typ('application/octet-stream', 'a.webp'), 'image/webp');
eq(H.typ('image/svg+xml', 'a.png'), '');     // nie SVG, auch nicht mit falscher Endung
eq(H.typ('image/heic', 'a.heic'), '');
eq(H.typ('text/plain', 'a.png'), '');
eq(H.typ('', 'a.bmp'), '');
eq(H.typ('', ''), '');
eq(H.typ(null, 'x.proto'), '');

// --- Zielgroesse ---
eq(H.zielMass(4000, 3000, 1568), { w: 1568, h: 1176, skala: 0.392 });
eq(H.zielMass(3000, 4000, 1568).h, 1568);
eq(H.zielMass(3000, 4000, 1568).w, 1176);
eq(H.zielMass(1000, 800, 1568), { w: 1000, h: 800, skala: 1 });
eq(H.zielMass(1568, 10, 1568).skala, 1);
eq(H.zielMass(50000, 1, 1568), { w: 1568, h: 1, skala: 1568 / 50000 });
eq(H.zielMass(0, 0, 0), { w: 1, h: 1, skala: 1 });
eq(H.zielMass(2560, 1440, H.MAX_KANTE_FEEDBACK), { w: 1920, h: 1080, skala: 0.75 });
for (let i = 0; i < 300; i++) {
  const w = 1 + Math.floor(Math.random() * 9000), h = 1 + Math.floor(Math.random() * 9000);
  const t = H.zielMass(w, h, 1568);
  assert.ok(Math.max(t.w, t.h) <= 1568 && t.w >= 1 && t.h >= 1 && t.w <= w && t.h <= h, JSON.stringify([w, h, t]));
  if (Math.max(w, h) > 1568) assert.strictEqual(Math.max(t.w, t.h), 1568);
}

// --- unveraendert behalten? ---
assert.ok(H.behalten({ typ: 'image/png', w: 800, h: 600, bytes: 200000, maxKante: 1568 }));
assert.ok(H.behalten({ typ: 'image/webp', w: 1568, h: 1568, bytes: 1000, maxKante: 1568 }));
assert.ok(!H.behalten({ typ: 'image/gif', w: 10, h: 10, bytes: 100, maxKante: 1568 }));     // GIF -> erstes Bild
assert.ok(!H.behalten({ typ: 'image/png', w: 1569, h: 10, bytes: 100, maxKante: 1568 }));
assert.ok(!H.behalten({ typ: 'image/jpeg', w: 100, h: 100, bytes: 5 * 1024 * 1024, maxKante: 1568 }));
assert.ok(!H.behalten({ typ: 'image/jpeg', w: 100, h: 100, bytes: 0, maxKante: 1568 }));
assert.ok(!H.behalten({ typ: 'image/bmp', w: 100, h: 100, bytes: 10, maxKante: 1568 }));
assert.ok(!H.behalten(null));

// --- PNG oder JPEG ---
eq(H.kodierung(true, 9e6, 10), 'image/png');      // durchsichtig: immer PNG
eq(H.kodierung(false, 100, 200), 'image/png');    // PNG kleiner (z.B. Bildschirmfoto)
eq(H.kodierung(false, 100, 100), 'image/png');
eq(H.kodierung(false, 900, 200), 'image/jpeg');   // Foto
eq(H.kodierung(false, 900, 0), 'image/png');      // kein JPEG moeglich
const opaque = new Uint8ClampedArray(16).fill(255);
assert.ok(!H.hatTransparenz(opaque, 1));
const holes = new Uint8ClampedArray(16).fill(255); holes[7] = 0;   // 2. Pixel durchsichtig
assert.ok(H.hatTransparenz(holes, 1));
assert.ok(!H.hatTransparenz(holes, 2));  // nur jedes 2. Pixel angesehen
assert.ok(!H.hatTransparenz(null, 1));
eq(H.pruefSchritt(100, 100), 1);
eq(H.pruefSchritt(4000, 4000), 64);

// --- data:-Adressen ---
eq(H.dataUrlTyp('data:image/png;base64,AAAA'), 'image/png');
eq(H.dataUrlTyp('data:text/html,<b>'), '');
eq(H.dataUrlBytes('data:image/png;base64,AAAA'), 3);
eq(H.dataUrlBytes('data:image/png;base64,AA=='), 1);
eq(H.dataUrlBytes('kaputt'), 0);
eq(H.mitTyp('data:application/octet-stream;base64,QUJD', 'image/png'), 'data:image/png;base64,QUJD');
eq(H.mitTyp('data:image/png;base64,QUJD', 'image/svg+xml'), '');
eq(H.mitTyp('javascript:alert(1)', 'image/png'), '');
assert.ok(H.istBildDaten('data:image/jpeg;base64,/9j/4AAQ+w=='));
assert.ok(!H.istBildDaten('data:image/svg+xml;base64,PHN2Zz4='));
assert.ok(!H.istBildDaten('data:image/png;base64,AA AA'));
assert.ok(!H.istBildDaten(null));

// --- Namen ---
eq(H.dateiName('C:\\Users\\x\\Foto.PNG', 'image/jpeg'), 'Foto.jpg');
eq(H.dateiName('/home/x/scan.webp', 'image/png'), 'scan.png');
eq(H.dateiName('image.png', 'image/png'), 'bild.png');       // eingefuegt aus der Zwischenablage
eq(H.dateiName('', 'image/gif'), 'bild.gif');
eq(H.dateiName('a\u0000b<c>"|.png', 'image/png'), 'abc.png');
eq(H.dateiName('x'.repeat(300) + '.png', 'image/png').length, 84);
eq(H.dateiName('urlaub', 'image/unbekannt'), 'urlaub.png');
eq(H.anzeigeName('', '/api/bild/h/abc.png'), 'abc.png');
eq(H.anzeigeName('  ein\nbild  '), 'ein bild');
eq(H.anzeigeName(null), 'Bild');
eq(H.anzeigeName('y'.repeat(200)).length, 120);

// --- eigene Bild-Adressen ---
eq(H.bildUrl('/api/bild/h/0123456789abcdef.png', 'a b&c'), '/api/bild/h/0123456789abcdef.png?t=a%20b%26c');
eq(H.bildUrl('/api/bild/e/20261108-120000_haus-am-see.webp?t=alt#x', 'T'), '/api/bild/e/20261108-120000_haus-am-see.webp?t=T');
eq(H.bildUrl('/api/bild/e/x.jpeg', 'T'), '/api/bild/e/x.jpeg?t=T');
for (const bad of ['/api/bild/x/a.png', '/api/bild/h/../a.png', '/api/bild/h/a.svg', '/api/bild/h/a/b.png',
  'https://evil.example/api/bild/h/a.png', '//evil/api/bild/h/a.png', 'javascript:alert(1)', '/api/bild/h/.png',
  '/api/bild/h/' + 'a'.repeat(101) + '.png', null, {}]) eq(H.bildUrl(bad, 'T'), '', String(bad));
eq(H.normBilder([{ url: '/api/bild/h/a.png', name: 'a' }, { url: 'https://x/y.png' }, null, 'x', { url: '/api/bild/h/b.gif' }]),
  [{ url: '/api/bild/h/a.png', name: 'a' }, { url: '/api/bild/h/b.gif', name: 'b.gif' }]);
eq(H.normBilder('kaputt'), []);
eq(H.normBilder(Array.from({ length: 30 }, (_, i) => ({ url: '/api/bild/h/i' + i + '.png' })), 10).length, 10);
eq(H.anzahlBilder([1, 2]), 2);
eq(H.anzahlBilder(3), 3);
eq(H.anzahlBilder('2'), 2);
eq(H.anzahlBilder(-1), 0);
eq(H.anzahlBilder(null), 0);
eq(H.anzahlBilder({}), 0);
eq(H.bildText(1), '1 Bild');
eq(H.bildText(2), '2 Bilder');
eq(H.groesseText(300), '1 KB');
eq(H.groesseText(350 * 1024), '350 KB');
eq(H.groesseText(1.5 * 1024 * 1024), '1,5 MB');
eq(H.gesamtLaenge([{ data: 'abc' }, null, { data: 'de' }]), 5);

// --- Kennung je Nachricht, Echo-Vergleich ---
const ids = new Set(Array.from({ length: 500 }, () => H.neueId()));
eq(ids.size, 500);
for (const id of ids) assert.ok(/^c[0-9a-z]+-[0-9a-f]{16}$/.test(id), id);
assert.ok(/-0{16}$/.test(H.neueId(() => 0)));
eq(H.echoSchluessel(' hallo ', [{ url: '/api/bild/h/a.png?t=X' }]), 'hallo\u0001/api/bild/h/a.png');
eq(H.echoSchluessel('hallo', []), 'hallo');
eq(H.echoSchluessel(null, null), '');
assert.ok(H.textGewinnt(' A1 '));
assert.ok(!H.textGewinnt('  \n'));

// --- Feedback ---
eq(H.sterne(4), 4);
eq(H.sterne('5'), 5);
eq(H.sterne(0), null);
eq(H.sterne(6), null);
eq(H.sterne(2.5), null);
eq(H.sterne(null), null);
eq(H.feedbackArt('BUG'), 'bug');
eq(H.feedbackArt('lob'), 'feedback');
eq(H.FEEDBACK_ARTEN.map((a) => a[0]), ['bewertung', 'bug', 'idee', 'feedback']);
assert.ok(H.feedbackLeer(null, '  ', 0));
assert.ok(!H.feedbackLeer(3, '', 0));
assert.ok(!H.feedbackLeer(null, 'x', 0));
assert.ok(!H.feedbackLeer(null, '', 1));
const img = { name: 'C:\\x\\shot.PNG', data: 'data:image/png;base64,AAAA' };
const fd = H.feedbackDaten({ kind: 'bug', stars: '4', text: '  Absturz  ', contact: ' ich@\n example.org ' + 'x'.repeat(300),
  images: [img, { name: 'b', data: 'data:image/svg+xml;base64,AAAA' }, img, img, img, img, img], trigger: 'popup' });
eq(fd.kind, 'bug'); eq(fd.stars, 4); eq(fd.text, 'Absturz'); eq(fd.trigger, 'popup');
eq(fd.contact.length, 200); assert.ok(!/\n/.test(fd.contact));
eq(fd.images.length, 5);
eq(fd.images[0], { name: 'shot.png', data: 'data:image/png;base64,AAAA' });
eq(Object.keys(fd).sort(), ['contact', 'images', 'kind', 'stars', 'text', 'trigger']);
eq(H.feedbackDaten({ trigger: 'irgendwas', text: 'y'.repeat(30000) }).text.length, 20000);
eq(H.feedbackDaten({}).trigger, 'menue');
eq(H.feedbackDaten(null).stars, null);
eq(H.feedbackErgebnis({ ok: true, status: 'gesendet', message: 'Danke! Dein Feedback wurde gesendet.' }).art, 'gesendet');
eq(H.feedbackErgebnis({ ok: true, status: 'gespeichert', message: 'Keine Verbindung.' }), { art: 'gespeichert', text: 'Keine Verbindung.' });
eq(H.feedbackErgebnis({ ok: false, status: 'abgelehnt', error: 'Die Bilder sind zusammen zu groß.' }),
  { art: 'fehler', text: 'Die Bilder sind zusammen zu groß.' });
eq(H.feedbackErgebnis({ ok: false, message: 'm' }).text, 'm');
eq(H.feedbackErgebnis(null).art, 'fehler');
assert.ok(H.feedbackErgebnis({ ok: true }).text.startsWith('Danke!'));

// --- Nachfrage-Karte ---
const frei = { faellig: true, gezeigt: false, beendet: false, busy: false, afk: false, jarvis: false, dialog: false,
  tippt: false, schluessel: true, tour: true, bereit: true };
assert.ok(H.nachfrageFrei(frei));
for (const [k, v] of [['faellig', false], ['gezeigt', true], ['beendet', true], ['busy', true], ['afk', true], ['jarvis', true],
  ['dialog', true], ['tippt', true], ['schluessel', false], ['tour', false], ['bereit', false]]) {
  assert.ok(!H.nachfrageFrei(Object.assign({}, frei, { [k]: v })), k);
}
assert.ok(!H.nachfrageFrei(Object.assign({}, frei, { faellig: 'true' })));
assert.ok(!H.nachfrageFrei(null));

// --- Bildgenerator-Einstellungen ---
eq(H.normBilderSetup({ anbieter: 'Cloudflare', cloudflare: true, aktiv: 'Cloudflare' }), { anbieter: 'cloudflare', cloudflare: true, aktiv: 'Cloudflare' });
eq(H.normBilderSetup({ anbieter: 'quatsch', cloudflare: 'ja', aktiv: 'X' }), { anbieter: 'auto', cloudflare: false, aktiv: 'AI Horde' });
eq(H.normBilderSetup(null), null);
eq(H.normBilderSetup([]), null);
eq(H.ANBIETER.map((a) => a[0]), ['auto', 'horde', 'cloudflare']);
eq(H.aktivText('AI Horde'), 'AI Horde – kostenlos, ohne Anmeldung, manchmal kurze Wartezeit');
assert.ok(H.aktivText('Cloudflare').startsWith('Cloudflare'));
eq(H.aktivText('constructor'), H.aktivText('AI Horde'));
assert.ok(H.kontoIdOk(' 0123456789ABCDEF0123456789abcdef '));
assert.ok(!H.kontoIdOk('0123456789abcdef'));
assert.ok(!H.kontoIdOk('g123456789abcdef0123456789abcdef'));
assert.ok(H.tokenOk('a'.repeat(40)));
assert.ok(!H.tokenOk('mit leerzeichen'.repeat(4)));
assert.ok(!H.tokenOk('kurz'));
eq(H.cloudflareDaten(' k ', ' t '), { cloudflare_account_id: 'k', cloudflare_token: 't' });
eq(H.cloudflareDaten('', 't'), { cloudflare_token: 't' });
eq(H.cloudflareDaten(null, undefined), {});

// --- Grenzen passen zum Server ---
eq(H.MAX_KANTE, 1568); eq(H.MAX_KANTE_FEEDBACK, 1920); eq(H.MAX_CHAT, 10); eq(H.MAX_FEEDBACK, 5);
assert.ok(H.CHAT_GESAMT < 40 * 1000 * 1000);
eq(H.ERLAUBT, ['image/png', 'image/jpeg', 'image/gif', 'image/webp']);
console.log('OK');
"""


@needs_node
def test_helfer_in_node(tmp_path):
    script = tmp_path / "helfer_test.js"
    script.write_text(_JS_TESTS, encoding="utf-8")
    r = subprocess.run([NODE, str(script), str(STATIC / "helfer.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip().endswith("OK"), r.stdout + r.stderr


@needs_node
def test_helfer_laeuft_ohne_seite_und_ohne_crypto(tmp_path):
    # aeltere Umgebung ohne crypto.getRandomValues: Kennungen trotzdem eindeutig
    script = tmp_path / "ohne.js"
    script.write_text(
        "Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });\n"
        "const H = require(process.argv[2]);\n"
        "const s = new Set(Array.from({length: 200}, () => H.neueId()));\n"
        "if (s.size !== 200 || typeof window !== 'undefined') process.exit(1);\n"
        "console.log(JSON.stringify(Object.keys(H).length));\n",
        encoding="utf-8")
    r = subprocess.run([NODE, str(script), str(STATIC / "helfer.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) > 30
