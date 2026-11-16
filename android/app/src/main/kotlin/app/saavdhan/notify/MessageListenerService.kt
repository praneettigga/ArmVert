package app.saavdhan.notify

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import app.saavdhan.SaavdhanApp
import app.saavdhan.core.Level
import app.saavdhan.ui.MainActivity
import java.util.concurrent.Executors

/**
 * Watches notifications from SMS and chat apps, runs the fast detector (rules + classifier, no LLM)
 * on the message text and posts a warning for suspicious messages. Nothing leaves the device:
 * the app has no INTERNET permission.
 */
class MessageListenerService : NotificationListenerService() {
    private val worker = Executors.newSingleThreadExecutor()
    private val recent = ArrayDeque<Int>()

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName !in WATCHED || sbn.isOngoing) return
        val n = sbn.notification
        if (n.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        val extras = n.extras
        val sender = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()
        val text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: extras.getCharSequence(Notification.EXTRA_TEXT))
            ?.toString()?.trim().orEmpty()
        if (text.length < 12) return
        val key = (sbn.packageName + sender + text).hashCode()
        synchronized(recent) {
            if (key in recent) return
            recent.addLast(key)
            if (recent.size > 50) recent.removeFirst()
        }
        worker.execute { check(sbn.packageName, sender, text) }
    }

    private fun check(pkg: String, sender: String?, text: String) {
        try {
            val app = application as SaavdhanApp
            val r = app.detector.analyse(text, sender)
            Log.i(TAG, "pkg=$pkg level=${r.verdict.level} risk=${"%.2f".format(r.verdict.risk)} in ${"%.2f".format(r.totalMs)} ms")
            if (r.verdict.level == Level.LOW) return
            val lang = getSharedPreferences("prefs", MODE_PRIVATE).getString("lang", "en") ?: "en"
            val title = when (r.verdict.level) {
                Level.HIGH -> if (lang == "hi") "⚠️ संभावित ठगी: ${sender ?: ""}" else "⚠️ Likely scam from ${sender ?: "unknown"}"
                else -> if (lang == "hi") "संदिग्ध संदेश: ${sender ?: ""}" else "Suspicious message from ${sender ?: "unknown"}"
            }
            val open = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra(MainActivity.EXTRA_TEXT, text)
                putExtra(MainActivity.EXTRA_SENDER, sender)
            }
            val pi = PendingIntent.getActivity(this, text.hashCode(), open,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val body = app.detector.explainer.template(r.verdict, lang)
            val notif = Notification.Builder(this, SaavdhanApp.ALERT_CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_warning)
                .setContentTitle(title)
                .setContentText(body.lineSequence().drop(1).firstOrNull()?.removePrefix("- ") ?: body)
                .setStyle(Notification.BigTextStyle().bigText(body))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build()
            getSystemService(NotificationManager::class.java).notify(text.hashCode(), notif)
        } catch (t: Throwable) {
            Log.e(TAG, "check failed", t)
        }
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "SaavdhanListener"
        val WATCHED = setOf(
            "com.google.android.apps.messaging",   // Google Messages
            "com.samsung.android.messaging",       // Samsung Messages
            "com.android.mms", "com.android.messaging",
            "com.oneplus.mms", "com.miui.securitycenter", "com.coloros.mms",
            "com.whatsapp", "com.whatsapp.w4b",
            "org.telegram.messenger", "com.truecaller",
        )
    }
}
