/**
 * Nova Feedback - kleines Google-Apps-Skript, das Feedback aus der App per E-Mail an dich schickt
 * und die Sterne-Bewertungen sammelt (Durchschnitt + oeffentliche Rezensionen).
 *
 * Einrichtung: siehe docs/FEEDBACK_EINRICHTEN.md
 * Wichtig: Im oeffentlichen Repo steht KEINE E-Mail-Adresse. Ohne EMPFAENGER schickt das Skript
 * die Mail an das Google-Konto, dem es gehoert ("Ausfuehren als: Ich"). Soll sie an eine andere
 * Adresse gehen, trag sie NUR in deiner Kopie bei Google unten bei EMPFAENGER ein.
 *
 * Bewertungen: Jede Rueckmeldung mit Sternen landet in der Google-Tabelle "Nova Bewertungen"
 * (legt das Skript selbst in deinem Google Drive an). Pro Installation zaehlt nur die letzte
 * Bewertung. Text und Name werden nur gezeigt, wenn die Person "oeffentlich" angekreuzt hat.
 * Eine Rezension ausblenden: in der Tabelle in der Spalte "Sichtbar" FALSE eintragen - oder bequemer:
 *   * in der Mail zu jeder oeffentlichen Rezension steht ein Loeschen-Link (nur du hast die Mail), oder
 *   * im Codegenerator, Reiter "Rezensionen" (braucht den Admin-Schluessel aus der Test-Mail).
 * Geloescht heisst ausgeblendet (Sichtbar = FALSE) - mit "Wiederherstellen" kommt sie zurueck.
 * Oeffentlich posten darf jede Installation nur EINMAL PRO WOCHE (auch wenn die App veraendert wurde):
 * eine weitere oeffentliche Rezension innerhalb von 7 Tagen wird nur privat gespeichert.
 * Abruf (fuer App und Repo): <Web-App-URL>?aktion=bewertungen
 *
 * Nach einer Aenderung an diesem Skript: Bereitstellen -> Bereitstellungen verwalten -> Bearbeiten ->
 * Version "Neue Version" -> Bereitstellen (die Adresse bleibt gleich).
 */

var EMPFAENGER = '';   // leer = an dich selbst (das Konto, dem das Skript gehoert)

var MAX_BILDER = 5;
var MAX_BILDER_BYTES = 15 * 1024 * 1024;   // MailApp erlaubt 25 MB je Mail
var MAX_PRO_STUNDE = 30;                    // Schutz vor Spam ueber die oeffentliche Adresse
var MAX_OEFFENTLICH = 30;                   // so viele oeffentliche Rezensionen liefert der Abruf
var ARTEN = {bewertung: 'Bewertung', feedback: 'Feedback', bug: 'Fehler', idee: 'Idee'};
var TABELLE_NAME = 'Nova Bewertungen';
var SPALTEN = ['Datum', 'Sterne', 'Oeffentlich', 'Name', 'Text', 'Version', 'Kennung', 'Sichtbar', 'ID'];
var REZENSION_TAGE = 7;                     // eine oeffentliche Rezension pro Installation und Woche
var SIG_FENSTER_MS = 10 * 60 * 1000;        // signierte Verwaltungs-Anfragen gelten 10 Minuten

/** Geheimer Admin-Schluessel (legt das Skript selbst an, steht nur in den Skript-Eigenschaften). */
function adminSchluessel() {
  var props = PropertiesService.getScriptProperties();
  var k = props.getProperty('admin');
  if (!k) {
    k = Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, '');
    props.setProperty('admin', k);
  }
  return k;
}

function hmacHex(text) {
  return Utilities.computeHmacSha256Signature(String(text), adminSchluessel()).map(function (b) {
    return ('0' + ((b + 256) % 256).toString(16)).slice(-2);
  }).join('');
}

/** Vergleich ohne Zeitverraet (gleich lange Hex-Texte). */
function gleich(a, b) {
  a = String(a || ''); b = String(b || '');
  if (a.length !== b.length || !a.length) return false;
  var x = 0;
  for (var i = 0; i < a.length; i++) x |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return x === 0;
}

function empfaenger() {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(EMPFAENGER) ? EMPFAENGER : Session.getEffectiveUser().getEmail();
}

/** Einmal im Editor ausfuehren (oben "Ausfuehren"): erteilt die Berechtigungen, legt die
 *  Bewertungs-Tabelle an und schickt dir eine Test-Mail. Kommt sie an, funktioniert alles. */
function testMail() {
  var tabelle = blatt();
  MailApp.sendEmail({
    to: empfaenger(),
    subject: '[Nova-Feedback] Test',
    body: 'Wenn du das liest, funktioniert das Feedback-Skript. Jetzt noch als Web-App bereitstellen ' +
          '(Schritt 5 der Anleitung).\n\nDie Bewertungen sammle ich hier: ' + tabelle.getParent().getUrl() +
          '\n\nAdmin-Schluessel fuer den Codegenerator (Reiter "Rezensionen" - NICHT weitergeben):\n' +
          adminSchluessel(),
    name: 'Nova Feedback'
  });
}

function doGet(e) {
  var aktion = e && e.parameter ? String(e.parameter.aktion || '') : '';
  if (aktion === 'bewertungen') {
    return antwort(bewertungen());
  }
  if (aktion === 'loeschen' || aktion === 'wiederherstellen') {   // Link aus deiner Mail
    var id = String(e.parameter.id || '').replace(/[^a-f0-9]/g, '').slice(0, 32);
    if (!id || !gleich(e.parameter.t, hmacHex('link|' + id))) {
      return HtmlService.createHtmlOutput('<p>Link ungueltig.</p>');
    }
    var an = aktion === 'wiederherstellen';
    var ok = sichtbarSetzen(id, an);
    var zurueck = ScriptApp.getService().getUrl() + '?aktion=' + (an ? 'loeschen' : 'wiederherstellen') +
                  '&id=' + id + '&t=' + hmacHex('link|' + id);
    return HtmlService.createHtmlOutput(
      '<p style="font-family:sans-serif">' + (ok ? (an ? 'Rezension ist wieder sichtbar.' : 'Rezension geloescht ' +
      '(ausgeblendet).') : 'Rezension nicht gefunden.') + '</p>' + (ok ? '<p style="font-family:sans-serif">' +
      '<a href="' + zurueck + '" target="_top">' + (an ? 'Doch loeschen' : 'Rueckgaengig') + '</a></p>' : ''));
  }
  return antwort({ok: true, dienst: 'nova-feedback'});
}

/** Verwaltung aus dem Codegenerator: {aktion, id?, zeit, sig = HMAC(admin, aktion|id|zeit)}. */
function verwaltung(d) {
  var zeit = Number(d.zeit) || 0;
  var id = String(d.id || '').replace(/[^a-f0-9]/g, '').slice(0, 32);
  if (Math.abs(Date.now() - zeit) > SIG_FENSTER_MS ||
      !gleich(d.sig, hmacHex(String(d.aktion) + '|' + id + '|' + zeit))) {
    return {ok: false, fehler: 'nicht_erlaubt'};
  }
  if (d.aktion === 'liste') {
    var werte = blatt().getDataRange().getValues().slice(1);
    var liste = [];
    werte.forEach(function (z) {
      if (!(z[2] === true || String(z[2]).toUpperCase() === 'TRUE') || !z[4]) return;
      liste.push({id: String(z[8] || ''), datum: Utilities.formatDate(new Date(z[0]), 'Europe/Berlin', 'yyyy-MM-dd'),
                  sterne: Number(z[1]), name: String(z[3] || '') || 'Anonym', text: String(z[4] || ''),
                  sichtbar: !(z[7] === false || String(z[7]).toUpperCase() === 'FALSE')});
    });
    liste.reverse();
    return {ok: true, rezensionen: liste.slice(0, 200)};
  }
  if (!id) return {ok: false, fehler: 'ungueltig'};
  return {ok: sichtbarSetzen(id, d.aktion === 'wiederherstellen')};
}

function sichtbarSetzen(id, sichtbar) {
  var sheet = blatt();
  var werte = sheet.getDataRange().getValues();
  for (var i = 1; i < werte.length; i++) {
    if (String(werte[i][8] || '') === id) {
      sheet.getRange(i + 1, 8).setValue(sichtbar);
      CacheService.getScriptCache().remove('bewertungen');
      return true;
    }
  }
  return false;
}

/** Hat diese Installation in den letzten 7 Tagen schon oeffentlich rezensiert? */
function kuerzlichOeffentlich(kennung) {
  if (!kennung) return false;
  var grenze = Date.now() - REZENSION_TAGE * 86400000;
  var werte = blatt().getDataRange().getValues().slice(1);
  for (var i = werte.length - 1; i >= 0; i--) {
    var z = werte[i];
    if (String(z[6] || '') === kennung && (z[2] === true || String(z[2]).toUpperCase() === 'TRUE') &&
        new Date(z[0]).getTime() >= grenze) return true;
  }
  return false;
}

function kennungAus(d) {
  return String(d.install || '').replace(/[^A-Za-z0-9_-]/g, '').slice(0, 40);
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    var d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (d.app !== 'Nova' || d.website) {
      return antwort({ok: false, fehler: 'ungueltig'});
    }
    if (!lock.tryLock(10000)) {
      return antwort({ok: false, fehler: 'limit'});
    }
    if (d.aktion === 'liste' || d.aktion === 'loeschen' || d.aktion === 'wiederherstellen') {
      return antwort(verwaltung(d));
    }
    var cache = CacheService.getScriptCache();
    var zaehler = Number(cache.get('anzahl') || 0);
    if (zaehler >= MAX_PRO_STUNDE || MailApp.getRemainingDailyQuota() < 1) {
      return antwort({ok: false, fehler: 'limit'});
    }

    var gesamt = 0;
    var anhaenge = [];
    (d.images || []).slice(0, MAX_BILDER).forEach(function (bild) {
      var bytes = Utilities.base64Decode(String(bild.data || ''));
      gesamt += bytes.length;
      var typ = bildTyp(bytes);  // Typ nur an den Bytes erkennen, Name selbst vergeben
      if (typ) {
        anhaenge.push(Utilities.newBlob(bytes, typ.mime, 'bild' + (anhaenge.length + 1) + '.' + typ.endung));
      }
    });
    if (gesamt > MAX_BILDER_BYTES) {
      return antwort({ok: false, fehler: 'zu_gross'});
    }

    var art = ARTEN[d.kind] || 'Feedback';
    var sterne = Number(d.stars) >= 1 && Number(d.stars) <= 5 ? Math.round(Number(d.stars)) : 0;
    var kontakt = String(d.contact || '').trim().slice(0, 200);
    var text = String(d.text || '').slice(0, 20000);
    var oeffentlich = d.public === true && sterne > 0;
    var wochenlimit = false;
    if (oeffentlich && kuerzlichOeffentlich(kennungAus(d))) {   // nur einmal pro Woche oeffentlich
      oeffentlich = false;
      wochenlimit = true;
    }
    var id = Utilities.getUuid().replace(/-/g, '').slice(0, 16);
    var name = String(d.name || '').replace(/\s+/g, ' ').trim().slice(0, 40);
    var zeilen = [
      'Art: ' + art,
      'Sterne: ' + (sterne ? new Array(sterne + 1).join('★') + ' (' + sterne + '/5)' : '-'),
      'Oeffentlich zeigen: ' + (oeffentlich ? 'ja' + (name ? ' (als "' + name + '")' : ' (ohne Namen)') :
        (wochenlimit ? 'nein (Wochenlimit - diese Woche schon eine oeffentliche Rezension)' : 'nein')),
      'Version: ' + String(d.version || '?').slice(0, 30),
      'System: ' + String(d.os || '?').slice(0, 120),
      'Gehirn: ' + String(d.brain || '?').slice(0, 80),
      'Anlass: ' + (d.trigger === 'popup' ? 'Nachfrage nach Nutzung' : 'selbst geöffnet'),
      'Kontakt: ' + (kontakt || '-'),
      'Bilder: ' + anhaenge.length,
      '',
      text || '(kein Text)'
    ];
    if (oeffentlich) {
      zeilen.push('', 'Diese Rezension loeschen (ausblenden): ' + ScriptApp.getService().getUrl() +
                  '?aktion=loeschen&id=' + id + '&t=' + hmacHex('link|' + id));
    }
    var mail = {
      to: empfaenger(),
      subject: '[Nova-Feedback] ' + art + (sterne ? ' ' + sterne + '★' : '') + ' – v' + String(d.version || '?').slice(0, 30),
      body: zeilen.join('\n'),
      name: 'Nova Feedback',
      attachments: anhaenge
    };
    if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(kontakt)) {
      mail.replyTo = kontakt;
    }
    MailApp.sendEmail(mail);
    if (sterne) {
      try {
        bewertungSpeichern(sterne, oeffentlich, name, text, d, id);
      } catch (ignored) {}  // die Mail ist raus - eine volle Tabelle soll das Feedback nicht verhindern
    }
    cache.put('anzahl', String(zaehler + 1), 3600);
    return antwort({ok: true});
  } catch (err) {
    return antwort({ok: false, fehler: 'server'});
  } finally {
    try { lock.releaseLock(); } catch (ignored) {}
  }
}

/** Die Bewertungs-Tabelle (beim ersten Mal anlegen; ihre ID merkt sich das Skript). */
function blatt() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('tabelle');
  var datei = null;
  if (id) {
    try { datei = SpreadsheetApp.openById(id); } catch (ignored) { datei = null; }
  }
  if (!datei) {
    datei = SpreadsheetApp.create(TABELLE_NAME);
    props.setProperty('tabelle', datei.getId());
    var neu = datei.getSheets()[0];
    neu.setName('Bewertungen');
    neu.appendRow(SPALTEN);
    neu.setFrozenRows(1);
  }
  return datei.getSheets()[0];
}

function bewertungSpeichern(sterne, oeffentlich, name, text, d, id) {
  var kennung = kennungAus(d);
  blatt().appendRow([new Date(), sterne, oeffentlich, oeffentlich ? name : '',
                     oeffentlich ? saeubern(text) : '', String(d.version || '').slice(0, 30), kennung, true, id]);
  CacheService.getScriptCache().remove('bewertungen');
}

/** Oeffentlicher Text: ohne E-Mail-Adressen, Links und Telefonnummern, hoechstens 600 Zeichen. */
function saeubern(text) {
  return String(text || '')
    .replace(/[^\s@]+@[^\s@]+\.[^\s@]+/g, '[entfernt]')
    .replace(/(https?:\/\/|www\.)\S+/gi, '[Link entfernt]')
    .replace(/\+?\d[\d\s\/().-]{7,}\d/g, '[entfernt]')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 600);
}

/** Durchschnitt, Verteilung und die neuesten oeffentlichen Rezensionen (5 Minuten zwischengespeichert). */
function bewertungen() {
  var cache = CacheService.getScriptCache();
  var fertig = cache.get('bewertungen');
  if (fertig) {
    return JSON.parse(fertig);
  }
  var werte = blatt().getDataRange().getValues().slice(1);
  var letzte = {};   // Kennung -> neueste Zeile (pro Installation zaehlt nur die letzte Bewertung)
  var ohne = [];
  werte.forEach(function (z) {
    var sterne = Number(z[1]);
    if (!(sterne >= 1 && sterne <= 5)) return;
    var eintrag = {datum: z[0], sterne: Math.round(sterne), oeffentlich: z[2] === true || String(z[2]).toUpperCase() === 'TRUE',
                   name: String(z[3] || ''), text: String(z[4] || ''), version: String(z[5] || ''),
                   versteckt: z[7] === false || String(z[7]).toUpperCase() === 'FALSE', id: String(z[8] || '')};
    var kennung = String(z[6] || '');
    if (!kennung) { if (!eintrag.versteckt) ohne.push(eintrag); return; }
    // die neueste zaehlt - auch wenn du sie geloescht hast (dann taucht keine aeltere wieder auf)
    if (!letzte[kennung] || new Date(eintrag.datum) >= new Date(letzte[kennung].datum)) letzte[kennung] = eintrag;
  });
  var alle = ohne.concat(Object.keys(letzte).map(function (k) { return letzte[k]; })
    .filter(function (b) { return !b.versteckt; }));
  var verteilung = {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0};
  var summe = 0;
  alle.forEach(function (b) { verteilung[String(b.sterne)] += 1; summe += b.sterne; });
  alle.sort(function (a, b) { return new Date(b.datum) - new Date(a.datum); });
  var oeffentlich = alle.filter(function (b) { return b.oeffentlich && b.text; }).slice(0, MAX_OEFFENTLICH)
    .map(function (b) {
      return {sterne: b.sterne, name: b.name || 'Anonym', text: b.text, version: b.version,
              datum: Utilities.formatDate(new Date(b.datum), 'Europe/Berlin', 'yyyy-MM-dd')};
    });
  var ergebnis = {ok: true, anzahl: alle.length, schnitt: alle.length ? Math.round(summe / alle.length * 10) / 10 : 0,
                  verteilung: verteilung, oeffentlich: oeffentlich,
                  stand: Utilities.formatDate(new Date(), 'Europe/Berlin', "yyyy-MM-dd'T'HH:mm")};
  cache.put('bewertungen', JSON.stringify(ergebnis), 300);
  return ergebnis;
}

/** Nur echte Bilder als Anhang (PNG, JPEG, GIF, WebP) - alles andere wird weggelassen. */
function bildTyp(b) {
  function ist(i, wert) { return b.length > i && ((b[i] + 256) % 256) === wert; }
  if (ist(0, 0x89) && ist(1, 0x50) && ist(2, 0x4E) && ist(3, 0x47)) return {mime: 'image/png', endung: 'png'};
  if (ist(0, 0xFF) && ist(1, 0xD8) && ist(2, 0xFF)) return {mime: 'image/jpeg', endung: 'jpg'};
  if (ist(0, 0x47) && ist(1, 0x49) && ist(2, 0x46) && ist(3, 0x38)) return {mime: 'image/gif', endung: 'gif'};
  if (ist(0, 0x52) && ist(1, 0x49) && ist(2, 0x46) && ist(3, 0x46) &&
      ist(8, 0x57) && ist(9, 0x45) && ist(10, 0x42) && ist(11, 0x50)) return {mime: 'image/webp', endung: 'webp'};
  return null;
}

function antwort(objekt) {
  return ContentService.createTextOutput(JSON.stringify(objekt)).setMimeType(ContentService.MimeType.JSON);
}
