package de.nova.handy;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/** Nach dem Einschalten des Handys: "Hey Nova" wieder starten (wenn eingeschaltet). Verbietet Android das
 * (ab Android 14 darf das Mikrofon nach dem Neustart erst nach einem Antippen), kommt eine Mitteilung. */
public class NovaStart extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        if (!NovaHoeren.prefs(c).getBoolean("hoeren", false)) return;
        versuchen(c);
    }

    static void versuchen(Context c) {
        try {
            NovaHoeren.starten(c);
        } catch (Exception e) {
            erinnern(c);
        }
    }

    static void erinnern(Context c) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(NovaHoeren.KANAL) == null) {
            nm.createNotificationChannel(new NotificationChannel(NovaHoeren.KANAL, "Nova hört zu",
                    NotificationManager.IMPORTANCE_LOW));
        }
        int flag = Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0;
        Intent oeffnen = new Intent(c, MainActivity.class).putExtra("hoeren_starten", true);
        PendingIntent pi = PendingIntent.getActivity(c, 2, oeffnen, flag);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, NovaHoeren.KANAL)
                : new Notification.Builder(c);
        nm.notify(8, b.setSmallIcon(R.drawable.ic_nova).setContentTitle("Nova")
                .setContentText("Tippen, damit Nova wieder auf dein Wachwort hört.")
                .setContentIntent(pi).setAutoCancel(true).build());
    }
}
