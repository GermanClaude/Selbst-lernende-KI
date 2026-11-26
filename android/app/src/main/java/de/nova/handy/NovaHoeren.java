package de.nova.handy;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Locale;

/**
 * "Hey Nova" auf dem Handy: hoert im Hintergrund (Vordergrund-Dienst mit Mitteilung "Nova hoert zu") auf das
 * Wachwort - die App muss nicht offen sein. Gehoert: (wenn eingestellt) die Nova-App oeffnen und den Befehl
 * aufnehmen, an Nova schicken (POST /api/frage, dieselbe Adresse wie die App) und die Antwort vorlesen.
 * Ausschalten: in der Mitteilung "Aus", in der App (Zurueck-Taste -> Hilfeseite) oder per Nova.
 * Die Spracherkennung ist die von Android; je nach Handy laeuft sie offline. Nichts wird gespeichert.
 */
public class NovaHoeren extends Service {
    static final String KANAL = "nova_hoeren";
    static final String AUS = "de.nova.handy.HOEREN_AUS";
    private static final int ID = 7;
    private final Handler haupt = new Handler(Looper.getMainLooper());
    private SpeechRecognizer erkenner;
    private TextToSpeech stimme;
    private boolean laeuft = false;
    private boolean befehlModus = false;
    private boolean beschaeftigt = false;

    static void starten(Context c) {
        Intent i = new Intent(c, NovaHoeren.class);
        if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
        else c.startService(i);
    }

    static void stoppen(Context c) {
        c.stopService(new Intent(c, NovaHoeren.class));
    }

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("nova", MODE_PRIVATE);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && AUS.equals(intent.getAction())) {
            prefs(this).edit().putBoolean("hoeren", false).apply();
            stopSelf();
            return START_NOT_STICKY;
        }
        Notification n = mitteilung("Sag „" + wachwort() + "“ – Nova hört zu.");
        if (Build.VERSION.SDK_INT >= 30) {
            startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        } else {
            startForeground(ID, n);
        }
        if (!laeuft) {
            laeuft = true;
            stimme = new TextToSpeech(this, s -> {
                if (s == TextToSpeech.SUCCESS) stimme.setLanguage(Locale.GERMANY);
            });
            haupt.post(this::zuhoeren);
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        laeuft = false;
        haupt.removeCallbacksAndMessages(null);
        if (erkenner != null) erkenner.destroy();
        if (stimme != null) stimme.shutdown();
        super.onDestroy();
    }

    private String wachwort() {
        return prefs(this).getString("wachwort", "Hey Nova");
    }

    private Notification mitteilung(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(KANAL) == null) {
            nm.createNotificationChannel(new NotificationChannel(KANAL, "Nova hört zu",
                    NotificationManager.IMPORTANCE_LOW));
        }
        int flag = Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0;
        PendingIntent oeffnen = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), flag);
        PendingIntent aus = PendingIntent.getService(this, 1, new Intent(this, NovaHoeren.class).setAction(AUS), flag);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, KANAL)
                : new Notification.Builder(this);
        return b.setSmallIcon(R.drawable.ic_nova).setContentTitle("Nova").setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(oeffnen).setOngoing(true)
                .addAction(new Notification.Action.Builder(null, "Aus", aus).build()).build();
    }

    private void zeigen(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.notify(ID, mitteilung(text));
    }

    // ------------------------------------------------------------------ Zuhoeren (Hauptfaden)
    private void zuhoeren() {
        if (!laeuft || beschaeftigt) return;
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            zeigen("Auf diesem Handy gibt es keine Spracherkennung (Google-App installieren).");
            return;
        }
        if (erkenner == null) {
            erkenner = SpeechRecognizer.createSpeechRecognizer(this);
            erkenner.setRecognitionListener(new Hoerer());
        }
        Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "de-DE");
        i.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true);
        i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3);
        i.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getPackageName());
        try {
            erkenner.startListening(i);
        } catch (Exception e) {
            haupt.postDelayed(this::zuhoeren, 3000);
        }
    }

    static String normal(String s) {
        return s == null ? "" : s.toLowerCase(Locale.GERMANY).replaceAll("[^\\p{L}\\p{N} ]", " ")
                .replaceAll("\\s+", " ").trim();
    }

    private class Hoerer implements RecognitionListener {
        @Override public void onReadyForSpeech(Bundle b) { }
        @Override public void onBeginningOfSpeech() { }
        @Override public void onRmsChanged(float v) { }
        @Override public void onBufferReceived(byte[] b) { }
        @Override public void onEndOfSpeech() { }
        @Override public void onPartialResults(Bundle b) { }
        @Override public void onEvent(int t, Bundle b) { }

        @Override
        public void onError(int fehler) {
            if (befehlModus && (fehler == SpeechRecognizer.ERROR_NO_MATCH
                    || fehler == SpeechRecognizer.ERROR_SPEECH_TIMEOUT)) {
                befehlModus = false;
                zeigen("Sag „" + wachwort() + "“ – Nova hört zu.");
            }
            long warte = fehler == SpeechRecognizer.ERROR_RECOGNIZER_BUSY ? 1500
                    : fehler == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ? 60000 : 250;
            if (fehler == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) {
                zeigen("Nova darf das Mikrofon nicht benutzen - in der App erlauben.");
            }
            haupt.postDelayed(NovaHoeren.this::zuhoeren, warte);
        }

        @Override
        public void onResults(Bundle b) {
            ArrayList<String> treffer = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
            String erstes = treffer != null && !treffer.isEmpty() ? treffer.get(0) : "";
            if (befehlModus) {
                befehlModus = false;
                if (!erstes.trim().isEmpty()) fragen(erstes.trim());
                else haupt.postDelayed(NovaHoeren.this::zuhoeren, 250);
                return;
            }
            String wort = normal(wachwort());
            for (String t : treffer == null ? new ArrayList<String>() : treffer) {
                String n = normal(t);
                int pos = n.indexOf(wort);
                if (pos < 0) continue;
                gehoert(n.substring(pos + wort.length()).trim());
                return;
            }
            haupt.postDelayed(NovaHoeren.this::zuhoeren, 150);
        }
    }

    private void gehoert(String rest) {
        SharedPreferences p = prefs(this);
        if (p.getBoolean("hoeren_app_oeffnen", true)) {
            try {
                startActivity(new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            } catch (Exception ignored) { }
        }
        if (!p.getBoolean("hoeren_sprechen", true)) {          // nur die App oeffnen, nicht gleich zuhoeren
            haupt.postDelayed(this::zuhoeren, 1500);
            return;
        }
        if (rest.length() > 2) {                                // "Hey Nova, mach das Licht an" in einem Satz
            fragen(rest);
            return;
        }
        befehlModus = true;
        zeigen("Ich höre …");
        sagen("Ja?");
        haupt.postDelayed(this::zuhoeren, 700);
    }

    private void sagen(String text) {
        if (stimme != null) stimme.speak(text, TextToSpeech.QUEUE_FLUSH, null, "nova");
    }

    // ------------------------------------------------------------------ An Nova schicken (eigener Faden)
    private void fragen(String text) {
        beschaeftigt = true;
        zeigen("„" + text + "“ – Nova denkt …");
        new Thread(() -> {
            String antwort;
            try {
                antwort = schicken(text);
            } catch (Exception e) {
                antwort = "Ich erreiche Nova gerade nicht. Ist die Adresse in der App richtig?";
            }
            final String a = antwort;
            haupt.post(() -> {
                zeigen(a);
                sagen(a);
                beschaeftigt = false;
                haupt.postDelayed(this::zuhoeren, Math.min(20000, 1500 + a.length() * 70L));
            });
        }, "nova-frage").start();
    }

    private String schicken(String text) throws Exception {
        String[] ziel = NovaSteuerung.basisUndSchluessel(prefs(this).getString("url", ""));
        if (ziel == null) return "Nova ist noch nicht verbunden - in der App die Adresse eintragen.";
        JSONObject body = new JSONObject();
        body.put("text", text);
        byte[] daten = body.toString().getBytes(StandardCharsets.UTF_8);
        HttpURLConnection c = (HttpURLConnection) new URL(ziel[0] + "/api/frage").openConnection();
        c.setConnectTimeout(20000);
        c.setReadTimeout(200000);
        c.setDoOutput(true);
        c.setRequestMethod("POST");
        c.setRequestProperty("X-KI-Token", ziel[1]);
        c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        c.setFixedLengthStreamingMode(daten.length);
        try {
            try (OutputStream o = c.getOutputStream()) {
                o.write(daten);
            }
            if (c.getResponseCode() != 200) return "Nova hat abgelehnt (" + c.getResponseCode() + ").";
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            try (InputStream in = c.getInputStream()) {
                byte[] puffer = new byte[8192];
                int n;
                while ((n = in.read(puffer)) > 0) b.write(puffer, 0, n);
            }
            JSONObject r = new JSONObject(new String(b.toByteArray(), StandardCharsets.UTF_8));
            return r.optString("antwort", r.optString("error", "Erledigt."));
        } finally {
            c.disconnect();
        }
    }
}
