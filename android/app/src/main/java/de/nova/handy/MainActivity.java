package de.nova.handy;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/**
 * Nova auf dem Handy: zeigt die Oberflaeche von Nova (laeuft in Termux, Befehl "nova").
 * Termux oeffnet diese App mit der Adresse inkl. Schluessel; die App merkt sie sich.
 * Laeuft Nova nicht, erscheint eine Hilfeseite (Termux oeffnen, nochmal versuchen, Adresse eingeben).
 * Nova kann auch in der Cloud laufen (https://...?t=...) - dann ist es egal, ob PC oder Termux laufen.
 * Zurueck-Taste auf der Startseite von Nova: Hilfeseite (Adresse wechseln); dort nochmal: App schliessen.
 * Handy-Steuerung (Nova bedient das Handy, auch wenn diese App zu ist): NovaSteuerung.java.
 */
public class MainActivity extends Activity {
    private static final int DATEI_WAHL = 7;
    private WebView web;
    private SharedPreferences prefs;
    private ValueCallback<Uri[]> dateiRueckruf;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("nova", MODE_PRIVATE);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        web.addJavascriptInterface(new Bruecke(), "NovaApp");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri ziel = req.getUrl();
                String gespeichert = prefs.getString("url", "");
                Uri nova = gespeichert.isEmpty() ? null : Uri.parse(gespeichert);
                boolean eigen = "file".equals(ziel.getScheme())
                        || (nova != null && ziel.getHost() != null && ziel.getHost().equals(nova.getHost())
                            && ziel.getPort() == nova.getPort());
                if (eigen) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, ziel)); // fremde Links im Browser
                } catch (ActivityNotFoundException ignored) { }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) zeigeHilfe();
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> rueckruf, FileChooserParams p) {
                if (dateiRueckruf != null) dateiRueckruf.onReceiveValue(null);
                dateiRueckruf = rueckruf;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("image/*");
                i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                try {
                    startActivityForResult(Intent.createChooser(i, "Bild wählen"), DATEI_WAHL);
                } catch (ActivityNotFoundException e) {
                    dateiRueckruf = null;
                    return false;
                }
                return true;
            }
        });
        setContentView(web);
        oeffne(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        oeffne(intent);
    }

    private void oeffne(Intent intent) {
        Uri d = intent != null ? intent.getData() : null;
        if (d != null && ("http".equals(d.getScheme()) || "https".equals(d.getScheme()))) {
            prefs.edit().putString("url", d.toString()).apply();
        }
        String url = prefs.getString("url", "");
        if (url.isEmpty()) zeigeHilfe();
        else web.loadUrl(url);
    }

    private void zeigeHilfe() {
        web.loadUrl("file:///android_asset/hilfe.html");
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode != DATEI_WAHL || dateiRueckruf == null) {
            super.onActivityResult(requestCode, resultCode, data);
            return;
        }
        Uri[] ergebnis = null;
        if (resultCode == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                int n = data.getClipData().getItemCount();
                ergebnis = new Uri[n];
                for (int k = 0; k < n; k++) ergebnis[k] = data.getClipData().getItemAt(k).getUri();
            } else if (data.getData() != null) {
                ergebnis = new Uri[]{data.getData()};
            }
        }
        dateiRueckruf.onReceiveValue(ergebnis);
        dateiRueckruf = null;
    }

    @Override
    public void onBackPressed() {
        String jetzt = web.getUrl();
        boolean hilfe = jetzt == null || jetzt.startsWith("file:");
        if (!hilfe && web.canGoBack()) web.goBack();
        else if (!hilfe) zeigeHilfe();
        else super.onBackPressed();
    }

    /** Fuer die Hilfeseite: Termux oeffnen, nochmal versuchen, eine Adresse uebernehmen. */
    private class Bruecke {
        @JavascriptInterface
        public void termuxOeffnen() {
            runOnUiThread(() -> {
                Intent i = getPackageManager().getLaunchIntentForPackage("com.termux");
                if (i != null) startActivity(i);
                else startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://f-droid.org/packages/com.termux/")));
            });
        }

        @JavascriptInterface
        public void nochmal() {
            runOnUiThread(() -> oeffne(null));
        }

        /** Fuer die Hilfeseite: wohin die App gerade verbindet (ohne Schluessel). */
        @JavascriptInterface
        public String adresse() {
            String u = prefs.getString("url", "");
            if (u.isEmpty()) return "";
            Uri x = Uri.parse(u);
            return x.getScheme() + "://" + x.getHost() + (x.getPort() > 0 ? ":" + x.getPort() : "");
        }

        /** Handy-Steuerung (NovaSteuerung): "aus", "pausiert" oder "an". */
        @JavascriptInterface
        public String steuerungStatus() {
            if (!NovaSteuerung.eingeschaltet(MainActivity.this)) return "aus";
            return prefs.getBoolean("steuern_pause", false) ? "pausiert" : "an";
        }

        @JavascriptInterface
        public void steuerungPausieren(boolean pause) {
            prefs.edit().putBoolean("steuern_pause", pause).apply();
        }

        @JavascriptInterface
        public void bedienungshilfeOeffnen() {
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
                } catch (ActivityNotFoundException ignored) { }
            });
        }

        @JavascriptInterface
        public void appInfoOeffnen() {
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            Uri.parse("package:" + getPackageName())));
                } catch (ActivityNotFoundException ignored) { }
            });
        }

        @JavascriptInterface
        public void verbinden(String adresse) {
            if (adresse == null) return;
            String a = adresse.trim();
            if (!(a.startsWith("http://") || a.startsWith("https://"))) return;
            prefs.edit().putString("url", a).apply();
            runOnUiThread(() -> web.loadUrl(a));
        }
    }
}
