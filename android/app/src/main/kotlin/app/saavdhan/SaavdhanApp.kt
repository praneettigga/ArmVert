package app.saavdhan

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import app.saavdhan.detect.Detector
import app.saavdhan.detect.LlamaExplainer

class SaavdhanApp : Application() {
    val detector: Detector by lazy { Detector(this) }
    val llama: LlamaExplainer by lazy { LlamaExplainer(this) }

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(ALERT_CHANNEL, "Scam alerts", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Warnings about suspicious SMS and chat messages"
            },
        )
    }

    companion object {
        const val ALERT_CHANNEL = "scam_alerts"
    }
}
