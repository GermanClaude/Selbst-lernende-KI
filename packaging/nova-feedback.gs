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
    var anhaenge = (d.images || []).slice(0, MAX_BILDER).map(function (bild, i) {
      var bytes = Utilities.base64Decode(String(bild.data || ''));
      gesamt += bytes.length;
      var mime = /^image\/(png|jpeg|gif|webp)$/.test(bild.mime) ? bild.mime : 'image/jpeg';
      var name = String(bild.name || ('bild' + (i + 1) + '.jpg')).replace(/[^\w.\- ]+/g, '_').slice(0, 80);
      return Utilities.newBlob(bytes, mime, name);
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

function antwort(objekt) {
  return ContentService.createTextOutput(JSON.stringify(objekt)).setMimeType(ContentService.MimeType.JSON);
}
