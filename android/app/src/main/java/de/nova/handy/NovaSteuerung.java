package de.nova.handy;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Path;
import android.graphics.Rect;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.media.AudioManager;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Handy-Steuerung fuer Nova: ein Android-Bedienungshilfe-Dienst. Ist er eingeschaltet (Einstellungen >
 * Bedienungshilfen > Nova), laeuft er im Hintergrund - die App muss NICHT offen sein - und holt bei Nova
 * (Cloud oder PC, dieselbe Adresse wie die App) Auftraege ab: Bildschirm lesen, tippen, schreiben, wischen,
 * Tasten, Apps starten ... Nova fragt vorher wie gewohnt nach. Dieser Dienst verweigert selbst:
 * Eingaben in die Nova-App (Schutz vor Selbst-Freigabe), Passwortfelder und den App-Installierer.
 */
public class NovaSteuerung extends AccessibilityService {
    private static final int MAX_ELEMENTE = 150;
    private volatile boolean aktiv = false;
    private final List<Eintrag> letzte = new ArrayList<>();
    private final LinkedList<String> meldungen = new LinkedList<>();

    private static class Eintrag {
        AccessibilityNodeInfo knoten;
        int x;
        int y;
    }

    private static class Verweigert extends Exception {
        Verweigert(String m) {
            super(m);
        }
    }

    /** Ist der Dienst in den Android-Einstellungen eingeschaltet? (fuer die Hilfeseite) */
    static boolean eingeschaltet(Context c) {
        String an = Settings.Secure.getString(c.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        if (an == null) return false;
        String ich = new ComponentName(c, NovaSteuerung.class).flattenToString();
        String kurz = new ComponentName(c, NovaSteuerung.class).flattenToShortString();
        for (String s : an.split(":")) {
            if (s.equalsIgnoreCase(ich) || s.equalsIgnoreCase(kurz)) return true;
        }
        return false;
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        if (aktiv) return;
        aktiv = true;
        if (getSharedPreferences("nova", MODE_PRIVATE).getBoolean("hoeren", false)) {
            NovaStart.versuchen(this);           // nach dem Neustart: "Hey Nova" wieder an (sonst Mitteilung)
        }
        Thread faden = new Thread(this::schleife, "nova-steuerung");
        faden.setDaemon(true);
        faden.start();
    }

    @Override
    public boolean onUnbind(Intent intent) {
        aktiv = false;
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        aktiv = false;
        super.onDestroy();
    }

    @Override
    public void onInterrupt() {
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent e) {
        if (e == null || e.getEventType() != AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED) return;
        CharSequence pkg = e.getPackageName();
        if (pkg == null || getPackageName().contentEquals(pkg)) return;
        StringBuilder t = new StringBuilder();
        for (CharSequence c : e.getText()) {
            if (c == null || c.length() == 0) continue;
            if (t.length() > 0) t.append(" - ");
            t.append(c);
        }
        if (t.length() == 0) return;
        String zeile = String.format(Locale.GERMANY, "%tR %s: %s", new Date(), appName(pkg.toString()),
                kuerzen(t.toString(), 300));
        synchronized (meldungen) {
            meldungen.addFirst(zeile);
            while (meldungen.size() > 30) meldungen.removeLast();
        }
    }

    // ------------------------------------------------------------------ Verbindung zu Nova
    private void schleife() {
        long pause = 2000;
        while (aktiv) {
            SharedPreferences p = getSharedPreferences("nova", MODE_PRIVATE);
            String[] ziel = basisUndSchluessel(p.getString("url", ""));
            if (ziel == null || p.getBoolean("steuern_pause", false)) {
                schlafen(15000);
                continue;
            }
            try {
                JSONObject j = new JSONObject(holen(ziel[0], ziel[1]));
                pause = 2000;
                JSONObject auftrag = j.optJSONObject("auftrag");
                if (auftrag != null) {
                    JSONObject erg = bearbeiten(auftrag);
                    erg.put("id", auftrag.optString("id"));
                    senden(ziel[0], ziel[1], erg);
                }
            } catch (Exception ex) {
                schlafen(pause);
                pause = Math.min(pause * 2, 60000);
            }
        }
    }

    /** Aus der gespeicherten Adresse (https://host/?t=SCHLUESSEL): {Basis, Schluessel} - sonst null. */
    static String[] basisUndSchluessel(String url) {
        if (url == null || url.isEmpty()) return null;
        Uri u = Uri.parse(url);
        String t = u.getQueryParameter("t");
        if (u.getHost() == null || t == null || t.isEmpty()) return null;
        if (!"https".equals(u.getScheme()) && !"http".equals(u.getScheme())) return null;
        String basis = u.getScheme() + "://" + u.getHost() + (u.getPort() > 0 ? ":" + u.getPort() : "");
        return new String[]{basis, t};
    }

    private String holen(String basis, String schluessel) throws IOException {
        String q = "?modell=" + enc(Build.MANUFACTURER + " " + Build.MODEL) + "&android=" + enc(Build.VERSION.RELEASE)
                + "&bedienung=1&app=" + enc(appVersion());
        HttpURLConnection c = (HttpURLConnection) new URL(basis + "/api/geraet/auftrag" + q).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(45000);
        c.setRequestProperty("X-KI-Token", schluessel);
        try {
            if (c.getResponseCode() != 200) throw new IOException("HTTP " + c.getResponseCode());
            return lesen(c.getInputStream());
        } finally {
            c.disconnect();
        }
    }

    private void senden(String basis, String schluessel, JSONObject daten) throws IOException {
        byte[] body = daten.toString().getBytes(StandardCharsets.UTF_8);
        HttpURLConnection c = (HttpURLConnection) new URL(basis + "/api/geraet/ergebnis").openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(20000);
        c.setDoOutput(true);
        c.setRequestMethod("POST");
        c.setRequestProperty("X-KI-Token", schluessel);
        c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        c.setFixedLengthStreamingMode(body.length);
        try {
            try (OutputStream o = c.getOutputStream()) {
                o.write(body);
            }
            c.getResponseCode();
        } finally {
            c.disconnect();
        }
    }

    private static String lesen(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] puffer = new byte[8192];
        int n;
        try {
            while ((n = in.read(puffer)) > 0) {
                b.write(puffer, 0, n);
                if (b.size() > 1 << 20) throw new IOException("zu gross");
            }
        } finally {
            in.close();
        }
        return new String(b.toByteArray(), StandardCharsets.UTF_8);
    }

    private static String enc(String s) {
        try {
            return URLEncoder.encode(s == null ? "" : s, "UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    private String appVersion() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
        }
    }

    private static void schlafen(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ignored) {
        }
    }

    // ------------------------------------------------------------------ Auftraege
    private JSONObject bearbeiten(JSONObject a) throws Exception {
        JSONObject r = new JSONObject();
        try {
            r.put("text", ausfuehren(a.optString("aktion"), a));
            r.put("ok", true);
        } catch (Verweigert v) {
            r.put("ok", false);
            r.put("fehler", v.getMessage());
        } catch (Exception e) {
            r.put("ok", false);
            r.put("fehler", e.getClass().getSimpleName() + (e.getMessage() != null ? ": " + e.getMessage() : ""));
        }
        return r;
    }

    private String ausfuehren(String aktion, JSONObject a) throws Exception {
        switch (aktion) {
            case "info":
                return "Verbunden: " + Build.MANUFACTURER + " " + Build.MODEL + ", Android " + Build.VERSION.RELEASE
                        + ". Vorne: " + vorne();
            case "bildschirm":
                return bildschirm();
            case "tippen":
            case "lange_tippen":
                return tippen(a, "lange_tippen".equals(aktion));
            case "text":
                return schreiben(a);
            case "wischen":
                return wischen(a);
            case "taste":
                return taste(a.optString("taste"));
            case "apps":
                return apps();
            case "app_starten":
                return appStarten(a.optString("name"));
            case "link_oeffnen": {
                String url = a.optString("url");
                if (!url.startsWith("https://") && !url.startsWith("http://")) throw new Verweigert("Nur https-Adressen.");
                starte(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                return "Geoeffnet. Vorne: " + vorne();
            }
            case "waehlen": {
                String n = nummer(a.optString("nummer"));
                starte(new Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + Uri.encode(n))));
                return "Die Nummer steht im Telefon (" + n + ") - zum Anrufen auf den Anruf-Knopf tippen.";
            }
            case "sms_schreiben": {
                String n = nummer(a.optString("nummer"));
                Intent i = new Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + Uri.encode(n)));
                i.putExtra("sms_body", a.optString("text"));
                starte(i);
                return "Die SMS an " + n + " ist vorbereitet (noch NICHT gesendet). Zum Senden den Senden-Knopf tippen.";
            }
            case "benachrichtigungen":
                synchronized (meldungen) {
                    if (meldungen.isEmpty()) return "Keine neuen Benachrichtigungen, seit die Handy-Steuerung laeuft.";
                    return "Letzte Benachrichtigungen (neueste zuerst):\n" + TextUtils.join("\n", meldungen);
                }
            case "akku": {
                BatteryManager bm = (BatteryManager) getSystemService(BATTERY_SERVICE);
                int prozent = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
                return "Akku: " + prozent + " %" + (bm.isCharging() ? " (laedt)" : "");
            }
            case "taschenlampe":
                return taschenlampe(a.optBoolean("an", true));
            case "wachwort": {                       // "Hey Nova" am Handy einstellen (an, text = Wort, sprechen)
                SharedPreferences p = getSharedPreferences("nova", MODE_PRIVATE);
                SharedPreferences.Editor e = p.edit();
                String wort = a.optString("text").trim();
                if (wort.length() >= 4 && wort.length() <= 60) e.putString("wachwort", wort);
                if (a.has("sprechen")) e.putBoolean("hoeren_sprechen", a.optBoolean("sprechen", true));
                if (a.has("an")) e.putBoolean("hoeren", a.optBoolean("an", false));
                e.apply();
                if (p.getBoolean("hoeren", false)) NovaStart.versuchen(this);
                else NovaHoeren.stoppen(this);
                return "Wachwort am Handy: " + (p.getBoolean("hoeren", false) ? "an" : "aus") + " ('"
                        + p.getString("wachwort", "Hey Nova") + "'), Spracheingabe danach: "
                        + (p.getBoolean("hoeren_sprechen", true) ? "an" : "aus") + ".";
            }
            case "warten": {
                double s = Math.max(0.5, Math.min(a.optDouble("sekunden", 2), 10));
                schlafen((long) (s * 1000));
                return "Gewartet. Vorne: " + vorne();
            }
            default:
                throw new Verweigert("Unbekannte Aktion: " + aktion);
        }
    }

    private static String nummer(String roh) throws Verweigert {
        String n = roh == null ? "" : roh.replaceAll("[^0-9+*#]", "");
        if (n.length() < 3) throw new Verweigert("Keine gueltige Telefonnummer.");
        return n;
    }

    private void starte(Intent i) throws Verweigert {
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            startActivity(i);
        } catch (Exception e) {
            throw new Verweigert("Dafuer gibt es auf dem Handy keine App.");
        }
        schlafen(900);
    }

    /** Eingaben nur ausserhalb der Nova-App und des App-Installierers. */
    private AccessibilityNodeInfo geschuetzt() throws Verweigert {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) throw new Verweigert("Den Bildschirm kann ich gerade nicht lesen (gesperrt oder aus?).");
        String pkg = root.getPackageName() == null ? "" : root.getPackageName().toString();
        if (pkg.equals(getPackageName())) {
            throw new Verweigert("In die Nova-App selbst tippe und schreibe ich nicht (Schutz: sonst koennte ich mir "
                    + "selbst Rechte geben). Erst eine andere App oeffnen.");
        }
        if (pkg.contains("packageinstaller")) throw new Verweigert("Apps installieren bestaetigt dein Mensch selbst.");
        return root;
    }

    private String vorne() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null || root.getPackageName() == null) return "(nicht lesbar)";
        return appName(root.getPackageName().toString());
    }

    private String appName(String pkg) {
        try {
            PackageManager pm = getPackageManager();
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (Exception e) {
            return pkg;
        }
    }

    private static String kuerzen(String s, int n) {
        String t = s.replace('\n', ' ').trim();
        return t.length() > n ? t.substring(0, n) + "..." : t;
    }

    private static String beschriftung(AccessibilityNodeInfo k) {
        CharSequence t = k.getText();
        if (t == null || t.length() == 0) t = k.getContentDescription();
        if ((t == null || t.length() == 0) && Build.VERSION.SDK_INT >= 26) t = k.getHintText();
        return t == null ? "" : t.toString().trim();
    }

    private static String typ(AccessibilityNodeInfo k) {
        CharSequence c = k.getClassName();
        if (c == null) return "Element";
        String s = c.toString();
        return s.substring(s.lastIndexOf('.') + 1);
    }

    private String bildschirm() throws Verweigert {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) throw new Verweigert("Den Bildschirm kann ich gerade nicht lesen (gesperrt oder aus?).");
        String pkg = root.getPackageName() == null ? "?" : root.getPackageName().toString();
        StringBuilder sb = new StringBuilder("App: " + appName(pkg) + " (" + pkg + ")\n");
        List<Eintrag> neu = new ArrayList<>();
        ArrayDeque<AccessibilityNodeInfo> stapel = new ArrayDeque<>();
        stapel.push(root);
        int gesamt = 0;
        while (!stapel.isEmpty()) {
            AccessibilityNodeInfo k = stapel.pop();
            for (int i = k.getChildCount() - 1; i >= 0; i--) {
                AccessibilityNodeInfo c = k.getChild(i);
                if (c != null) stapel.push(c);
            }
            if (!k.isVisibleToUser()) continue;
            String text = beschriftung(k);
            if (text.isEmpty() && !k.isClickable() && !k.isEditable() && !k.isScrollable() && !k.isCheckable()) continue;
            Rect r = new Rect();
            k.getBoundsInScreen(r);
            if (r.width() <= 0 || r.height() <= 0) continue;
            gesamt++;
            if (neu.size() >= MAX_ELEMENTE) continue;
            Eintrag e = new Eintrag();
            e.knoten = k;
            e.x = r.centerX();
            e.y = r.centerY();
            neu.add(e);
            sb.append('[').append(neu.size()).append("] ").append(typ(k));
            if (k.isPassword()) sb.append(" (Passwortfeld)");
            else if (!text.isEmpty()) sb.append(" '").append(kuerzen(text, 120)).append('\'');
            String id = k.getViewIdResourceName();
            if (id != null) {
                int s = id.indexOf(":id/");
                sb.append(" id=").append(s >= 0 ? id.substring(s + 4) : id);
            }
            if (k.isCheckable()) sb.append(k.isChecked() ? " [an]" : " [aus]");
            if (k.isEditable()) sb.append(" [Feld]");
            else if (k.isClickable()) sb.append(" [tippbar]");
            if (k.isScrollable()) sb.append(" [scrollbar]");
            if (!k.isEnabled()) sb.append(" [gesperrt]");
            sb.append(" @").append(e.x).append(',').append(e.y).append('\n');
        }
        synchronized (letzte) {
            letzte.clear();
            letzte.addAll(neu);
        }
        if (gesamt > neu.size()) sb.append("(").append(gesamt - neu.size()).append(" weitere nicht gezeigt - wischen)\n");
        if (neu.isEmpty()) sb.append("(keine lesbaren Elemente - z.B. ein Spiel oder Video; dann per x/y tippen)\n");
        return sb.toString();
    }

    /** Ziel aus nr (letzte Liste) oder element (sichtbarer Text). null = keins angegeben. */
    private Eintrag ziel(JSONObject a, AccessibilityNodeInfo root) throws Verweigert {
        int nr = a.optInt("nr", 0);
        if (nr > 0) {
            synchronized (letzte) {
                if (nr > letzte.size()) throw new Verweigert("Nr. " + nr + " gibt es nicht - erst 'bildschirm' lesen.");
                Eintrag e = letzte.get(nr - 1);
                if (e.knoten != null && !e.knoten.refresh()) e.knoten = null;   // Bildschirm hat sich geaendert: dann per Position
                return e;
            }
        }
        String gesucht = a.optString("element").trim();
        if (gesucht.isEmpty()) return null;
        List<AccessibilityNodeInfo> treffer = root.findAccessibilityNodeInfosByText(gesucht);
        AccessibilityNodeInfo bester = null;
        for (AccessibilityNodeInfo k : treffer) {
            if (!k.isVisibleToUser()) continue;
            if (beschriftung(k).equalsIgnoreCase(gesucht)) {
                bester = k;
                break;
            }
            if (bester == null) bester = k;
        }
        if (bester == null) throw new Verweigert("Kein Element '" + gesucht + "' zu sehen - erst 'bildschirm' lesen.");
        Rect r = new Rect();
        bester.getBoundsInScreen(r);
        Eintrag e = new Eintrag();
        e.knoten = bester;
        e.x = r.centerX();
        e.y = r.centerY();
        return e;
    }

    private static AccessibilityNodeInfo tippbar(AccessibilityNodeInfo k, boolean lang) {
        for (int i = 0; k != null && i < 8; i++) {
            if (lang ? k.isLongClickable() : k.isClickable()) return k;
            k = k.getParent();
        }
        return null;
    }

    private String tippen(JSONObject a, boolean lang) throws Exception {
        AccessibilityNodeInfo root = geschuetzt();
        Eintrag e = ziel(a, root);
        boolean ok = false;
        if (e != null && e.knoten != null) {
            AccessibilityNodeInfo k = tippbar(e.knoten, lang);
            if (k != null) {
                ok = k.performAction(lang ? AccessibilityNodeInfo.ACTION_LONG_CLICK : AccessibilityNodeInfo.ACTION_CLICK);
            }
        }
        if (!ok) {
            int x, y;
            if (e != null) {
                x = e.x;
                y = e.y;
            } else if (a.has("x") && a.has("y")) {
                x = a.optInt("x");
                y = a.optInt("y");
            } else {
                throw new Verweigert("Wohin? nr, element oder x/y angeben.");
            }
            Path weg = new Path();
            weg.moveTo(Math.max(0, x), Math.max(0, y));
            ok = geste(weg, lang ? 900 : 60);
        }
        if (!ok) throw new Verweigert("Das Tippen hat nicht geklappt.");
        schlafen(700);
        return "Getippt. Vorne: " + vorne();
    }

    private String schreiben(JSONObject a) throws Exception {
        AccessibilityNodeInfo root = geschuetzt();
        Eintrag e = ziel(a, root);
        AccessibilityNodeInfo feld = e != null ? e.knoten : root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (feld != null && !feld.isEditable()) {
            feld.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            schlafen(400);
            AccessibilityNodeInfo neu = getRootInActiveWindow();
            feld = neu != null ? neu.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) : null;
        }
        if (feld == null || !feld.isEditable()) {
            throw new Verweigert("Kein Eingabefeld gefunden - erst ins Feld tippen oder nr angeben.");
        }
        if (feld.isPassword()) throw new Verweigert("Passwortfelder fuelle ich nicht aus - das macht dein Mensch selbst.");
        Bundle b = new Bundle();
        b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, a.optString("text"));
        if (!feld.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, b)) throw new Verweigert("Schreiben ging nicht.");
        return "Geschrieben.";
    }

    private String wischen(JSONObject a) throws Exception {
        geschuetzt();
        DisplayMetrics m = getResources().getDisplayMetrics();
        int w = m.widthPixels, h = m.heightPixels;
        float x1, y1, x2, y2;
        switch (a.optString("richtung")) {
            case "hoch":
                x1 = w / 2f; y1 = h * 0.75f; x2 = w / 2f; y2 = h * 0.25f;
                break;
            case "runter":
                x1 = w / 2f; y1 = h * 0.25f; x2 = w / 2f; y2 = h * 0.75f;
                break;
            case "links":
                x1 = w * 0.85f; y1 = h / 2f; x2 = w * 0.15f; y2 = h / 2f;
                break;
            case "rechts":
                x1 = w * 0.15f; y1 = h / 2f; x2 = w * 0.85f; y2 = h / 2f;
                break;
            default:
                if (!(a.has("x") && a.has("y") && a.has("x2") && a.has("y2"))) {
                    throw new Verweigert("richtung (hoch/runter/links/rechts) oder x,y,x2,y2 angeben.");
                }
                x1 = a.optInt("x"); y1 = a.optInt("y"); x2 = a.optInt("x2"); y2 = a.optInt("y2");
        }
        Path weg = new Path();
        weg.moveTo(Math.max(0, x1), Math.max(0, y1));
        weg.lineTo(Math.max(0, x2), Math.max(0, y2));
        if (!geste(weg, 350)) throw new Verweigert("Wischen hat nicht geklappt.");
        schlafen(600);
        return "Gewischt.";
    }

    private boolean geste(Path weg, long dauer) throws InterruptedException {
        GestureDescription g = new GestureDescription.Builder()
                .addStroke(new GestureDescription.StrokeDescription(weg, 0, dauer)).build();
        final CountDownLatch fertig = new CountDownLatch(1);
        final boolean[] ok = {false};
        boolean los = dispatchGesture(g, new GestureResultCallback() {
            @Override
            public void onCompleted(GestureDescription d) {
                ok[0] = true;
                fertig.countDown();
            }

            @Override
            public void onCancelled(GestureDescription d) {
                fertig.countDown();
            }
        }, null);
        if (!los) return false;
        fertig.await(dauer + 3000, TimeUnit.MILLISECONDS);
        return ok[0];
    }

    private String taste(String t) throws Exception {
        AudioManager am = (AudioManager) getSystemService(AUDIO_SERVICE);
        switch (t) {
            case "zurueck":
                return global(GLOBAL_ACTION_BACK);
            case "home":
                return global(GLOBAL_ACTION_HOME);
            case "apps":
                return global(GLOBAL_ACTION_RECENTS);
            case "benachrichtigungen":
                return global(GLOBAL_ACTION_NOTIFICATIONS);
            case "schnelleinstellungen":
                return global(GLOBAL_ACTION_QUICK_SETTINGS);
            case "sperren":
                if (Build.VERSION.SDK_INT < 28) throw new Verweigert("Sperren geht erst ab Android 9.");
                return global(GLOBAL_ACTION_LOCK_SCREEN);
            case "screenshot":
                if (Build.VERSION.SDK_INT < 28) throw new Verweigert("Screenshot geht erst ab Android 9.");
                return global(GLOBAL_ACTION_TAKE_SCREENSHOT);
            case "enter": {
                AccessibilityNodeInfo root = geschuetzt();
                if (Build.VERSION.SDK_INT < 30) throw new Verweigert("Enter geht erst ab Android 11 - tipp auf den Senden-Knopf.");
                AccessibilityNodeInfo f = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
                if (f == null || !f.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.getId())) {
                    throw new Verweigert("Enter ging nicht - tipp auf den Senden-Knopf.");
                }
                return "Enter gedrueckt.";
            }
            case "lauter":
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI);
                return "Lauter.";
            case "leiser":
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI);
                return "Leiser.";
            case "stumm":
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_TOGGLE_MUTE, AudioManager.FLAG_SHOW_UI);
                return "Stumm umgeschaltet.";
            case "pause":
                return medien(am, KeyEvent.KEYCODE_MEDIA_PAUSE);
            case "weiter":
                return medien(am, KeyEvent.KEYCODE_MEDIA_PLAY);
            case "naechstes":
                return medien(am, KeyEvent.KEYCODE_MEDIA_NEXT);
            case "vorheriges":
                return medien(am, KeyEvent.KEYCODE_MEDIA_PREVIOUS);
            default:
                throw new Verweigert("Unbekannte Taste: " + t);
        }
    }

    private String global(int aktion) throws Verweigert {
        if (!performGlobalAction(aktion)) throw new Verweigert("Das ging nicht.");
        schlafen(700);
        return "Erledigt. Vorne: " + vorne();
    }

    private static String medien(AudioManager am, int code) {
        am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, code));
        am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, code));
        return "Erledigt.";
    }

    private Map<String, String> appListe() {
        PackageManager pm = getPackageManager();
        Intent i = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        Map<String, String> apps = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        for (ResolveInfo r : pm.queryIntentActivities(i, 0)) {
            apps.put(r.loadLabel(pm).toString(), r.activityInfo.packageName);
        }
        return apps;
    }

    private String apps() {
        Map<String, String> apps = appListe();
        StringBuilder sb = new StringBuilder(apps.size() + " Apps:\n");
        int n = 0;
        for (Map.Entry<String, String> e : apps.entrySet()) {
            if (++n > 300) break;
            sb.append("- ").append(e.getKey()).append(" (").append(e.getValue()).append(")\n");
        }
        return sb.toString();
    }

    private String appStarten(String name) throws Verweigert {
        String gesucht = name == null ? "" : name.trim();
        if (gesucht.isEmpty()) throw new Verweigert("Welche App? name angeben.");
        Map<String, String> apps = appListe();
        String pkg = apps.get(gesucht);
        if (pkg == null && apps.containsValue(gesucht)) pkg = gesucht;
        if (pkg == null) {
            for (Map.Entry<String, String> e : apps.entrySet()) {
                if (e.getKey().toLowerCase(Locale.GERMANY).contains(gesucht.toLowerCase(Locale.GERMANY))) {
                    pkg = e.getValue();
                    break;
                }
            }
        }
        if (pkg == null) throw new Verweigert("Keine App '" + gesucht + "' gefunden - 'apps' zeigt alle.");
        Intent i = getPackageManager().getLaunchIntentForPackage(pkg);
        if (i == null) throw new Verweigert("Diese App laesst sich nicht direkt oeffnen.");
        starte(i);
        return "Geoeffnet: " + appName(pkg) + ". Vorne: " + vorne();
    }

    private String taschenlampe(boolean an) throws Exception {
        CameraManager cm = (CameraManager) getSystemService(CAMERA_SERVICE);
        for (String id : cm.getCameraIdList()) {
            Boolean blitz = cm.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
            if (Boolean.TRUE.equals(blitz)) {
                cm.setTorchMode(id, an);
                return "Taschenlampe " + (an ? "an." : "aus.");
            }
        }
        throw new Verweigert("Dieses Handy hat keine Taschenlampe.");
    }
}
