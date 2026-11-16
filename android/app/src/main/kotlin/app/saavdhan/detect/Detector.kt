package app.saavdhan.detect

import android.content.Context
import android.util.Log
import app.saavdhan.core.Explainer
import app.saavdhan.core.RuleEngine
import app.saavdhan.core.TextFeatures
import app.saavdhan.core.Verdict
import org.pytorch.executorch.EValue
import org.pytorch.executorch.Module
import org.pytorch.executorch.Tensor
import java.io.File

/**
 * Fast path: shared rules + the ExecuTorch classifier (XNNPACK on the Arm CPU). Runs in well under
 * 10 ms, so it is used for every incoming notification. Llama is only used for the explanation.
 */
class Detector(context: Context) {
    val engine = RuleEngine(context.assets.open("rules.json").bufferedReader().use { it.readText() })
    val explainer = Explainer(engine)
    private val module: Module?
    val classifierLoadMs: Long
    val classifierError: String?

    data class Result(
        val verdict: Verdict,
        val classifierLogit: Double?,
        val featureMs: Double,
        val classifierMs: Double,
        val rulesMs: Double,
    ) {
        val totalMs get() = featureMs + classifierMs + rulesMs
    }

    init {
        val t0 = System.nanoTime()
        var err: String? = null
        module = try {
            val f = copyAsset(context, CLASSIFIER_ASSET)
            Module.load(f.absolutePath)
        } catch (t: Throwable) {
            Log.e(TAG, "classifier unavailable, running rules-only", t)
            err = t.message ?: t.javaClass.simpleName
            null
        }
        classifierError = err
        classifierLoadMs = (System.nanoTime() - t0) / 1_000_000
    }

    val hasClassifier get() = module != null

    fun analyse(text: String, sender: String?): Result {
        val t0 = System.nanoTime()
        val ids = TextFeatures.featureIds(text)
        val t1 = System.nanoTime()
        val logit = module?.let { m ->
            synchronized(this) {
                m.forward(EValue.from(Tensor.fromBlob(ids, longArrayOf(1, TextFeatures.MAX_FEATURES.toLong()))))[0]
                    .toTensor().dataAsFloatArray[0].toDouble()
            }
        }
        val t2 = System.nanoTime()
        val verdict = engine.analyse(text, sender, logit)
        val t3 = System.nanoTime()
        return Result(verdict, logit, (t1 - t0) / 1e6, (t2 - t1) / 1e6, (t3 - t2) / 1e6)
    }

    companion object {
        private const val TAG = "Saavdhan"
        const val CLASSIFIER_ASSET = "scam_classifier.pte"

        /** ExecuTorch needs a file path, so assets are copied to internal storage once per app version. */
        fun copyAsset(context: Context, name: String): File {
            val dest = File(context.filesDir, name)
            val size = context.assets.openFd(name).use { it.length }
            if (!dest.exists() || dest.length() != size) {
                context.assets.open(name).use { input -> dest.outputStream().use { input.copyTo(it) } }
            }
            return dest
        }
    }
}
