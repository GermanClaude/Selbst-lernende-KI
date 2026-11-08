/**
 * Nova Feedback - kleines Google-Apps-Skript, das Feedback aus der App per E-Mail an dich schickt.
 *
 * Einrichtung: siehe docs/FEEDBACK_EINRICHTEN.md
 * Wichtig: Hier steht KEINE E-Mail-Adresse. Das Skript schickt die Mail an das Google-Konto,
 * dem es gehoert ("Ausfuehren als: Ich"). So bleibt deine Adresse ueberall verborgen.
 */

var MAX_BILDER = 5;
var MAX_BILDER_BYTES = 15 * 1024 * 1024;   // MailApp erlaubt 25 MB je Mail
var MAX_PRO_STUNDE = 30;                    // Schutz vor Spam ueber die oeffentliche Adresse
var ARTEN = {bewertung: 'Bewertung', feedback: 'Feedback', bug: 'Fehler', idee: 'Idee'};

/** Einmal im Editor ausfuehren (oben "Ausfuehren"): erteilt die Berechtigungen und schickt dir
 *  eine Test-Mail. Kommt sie an, funktioniert alles - dann als Web-App bereitstellen. */
function testMail() {
  MailApp.sendEmail({
    to: Session.getEffectiveUser().getEmail(),
    subject: '[Nova-Feedback] Test',
    body: 'Wenn du das liest, funktioniert das Feedback-Skript. Jetzt noch als Web-App bereitstellen (Schritt 5 der Anleitung).',
    name: 'Nova Feedback'
  });
}

function doGet() {
  return antwort({ok: true, dienst: 'nova-feedback'});
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
    var zeilen = [
      'Art: ' + art,
      'Sterne: ' + (sterne ? new Array(sterne + 1).join('★') + ' (' + sterne + '/5)' : '-'),
      'Version: ' + String(d.version || '?').slice(0, 30),
      'System: ' + String(d.os || '?').slice(0, 120),
      'Gehirn: ' + String(d.brain || '?').slice(0, 80),
      'Anlass: ' + (d.trigger === 'popup' ? 'Nachfrage nach Nutzung' : 'selbst geöffnet'),
      'Kontakt: ' + (kontakt || '-'),
      'Bilder: ' + anhaenge.length,
      '',
      text || '(kein Text)'
    ];
    var mail = {
      to: Session.getEffectiveUser().getEmail(),
      subject: '[Nova-Feedback] ' + art + (sterne ? ' ' + sterne + '★' : '') + ' – v' + String(d.version || '?').slice(0, 30),
      body: zeilen.join('\n'),
      name: 'Nova Feedback',
      attachments: anhaenge
    };
    if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(kontakt)) {
      mail.replyTo = kontakt;
    }
    MailApp.sendEmail(mail);
    cache.put('anzahl', String(zaehler + 1), 3600);
    return antwort({ok: true});
  } catch (err) {
    return antwort({ok: false, fehler: 'server'});
  } finally {
    try { lock.releaseLock(); } catch (ignored) {}
  }
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
