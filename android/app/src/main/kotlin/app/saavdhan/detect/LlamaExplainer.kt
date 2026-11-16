package app.saavdhan.detect

import android.content.Context
import android.util.Log
import org.json.JSONObject
import org.pytorch.executorch.extension.llm.LlmCallback
import org.pytorch.executorch.extension.llm.LlmModule
import java.io.File

/**
 * Llama 3.2 (1B/3B) running through ExecuTorch on the Arm CPU (XNNPACK backend, INT4 weights).
 *
 * Model files are pushed by the user (they are too big to bundle in the APK):
 *   adb push Llama-3.2-1B-Instruct-SpinQuant_INT4_EO8.pte tokenizer.model \
 *       /sdcard/Android/data/app.saavdhan/files/models/
 */
class LlamaExplainer(private val context: Context) {
    private var module: LlmModule? = null
    @Volatile var loadMs: Long = -1; private set
    @Volatile var lastError: String? = null; private set

    val modelDir: File get() = File(context.getExternalFilesDir(null), "models").apply { mkdirs() }

    fun modelFile(): File? = modelDir.listFiles { f -> f.extension == "pte" }?.maxByOrNull { it.length() }

    fun tokenizerFile(): File? = modelDir.listFiles { f ->
        f.name.startsWith("tokenizer") && f.extension in setOf("model", "json", "bin")
    }?.firstOrNull()

    val isAvailable get() = modelFile() != null && tokenizerFile() != null
    val isLoaded get() = module != null

    @Synchronized
    fun ensureLoaded(): Boolean {
        if (module != null) return true
        val m = modelFile() ?: return false.also { lastError = "No .pte model in ${modelDir.absolutePath}" }
        val t = tokenizerFile() ?: return false.also { lastError = "No tokenizer in ${modelDir.absolutePath}" }
        return try {
            val t0 = System.currentTimeMillis()
            module = LlmModule(m.absolutePath, t.absolutePath, TEMPERATURE).also { it.load() }
            loadMs = System.currentTimeMillis() - t0
            lastError = null
            true
        } catch (e: Throwable) {
            Log.e(TAG, "Llama load failed", e)
            lastError = e.message ?: e.javaClass.simpleName
            false
        }
    }

    data class Stats(
        val promptTokens: Int,
        val generatedTokens: Int,
        val ttftMs: Long,
        val prefillTokPerSec: Double,
        val decodeTokPerSec: Double,
        val totalMs: Long,
        val peakRssMb: Long,
    )

    /** Blocking. Call from a background thread. Streams tokens through [onToken]. */
    @Synchronized
    fun generate(prompt: String, onToken: (String) -> Unit): Pair<String, Stats?> {
        if (!ensureLoaded()) return "" to null
        val llm = module!!
        val sb = StringBuilder()
        var statsJson: String? = null
        val start = System.currentTimeMillis()
        llm.generate(prompt, SEQ_LEN, object : LlmCallback {
            override fun onResult(result: String) {
                if (result.contains("<|eot_id|>") || result.contains("<|end_of_text|>")) {
                    llm.stop(); return
                }
                sb.append(result)
                onToken(result)
            }
            override fun onStats(stats: String) { statsJson = stats }
            override fun onError(errorCode: Int, message: String) {
                lastError = "generate error $errorCode: $message"
                Log.e(TAG, lastError!!)
            }
        }, false)
        val total = System.currentTimeMillis() - start
        return sb.toString() to parseStats(statsJson, total)
    }

    fun stop() { module?.stop() }

    @Synchronized
    fun unload() { module?.close(); module = null }

    private fun parseStats(json: String?, totalMs: Long): Stats? = try {
        val o = JSONObject(json ?: return null)
        val start = o.optLong("inference_start_ms")
        val promptEnd = o.optLong("prompt_eval_end_ms")
        val first = o.optLong("first_token_ms")
        val end = o.optLong("inference_end_ms")
        val pt = o.optInt("prompt_tokens")
        val gt = o.optInt("generated_tokens")
        Stats(
            promptTokens = pt,
            generatedTokens = gt,
            ttftMs = first - start,
            prefillTokPerSec = if (promptEnd > start) pt * 1000.0 / (promptEnd - start) else 0.0,
            decodeTokPerSec = if (end > first && gt > 1) (gt - 1) * 1000.0 / (end - first) else 0.0,
            totalMs = totalMs,
            peakRssMb = peakRssMb(),
        )
    } catch (e: Exception) {
        Log.w(TAG, "could not parse stats: $json", e); null
    }

    companion object {
        private const val TAG = "SaavdhanLlama"
        private const val TEMPERATURE = 0.2f
        private const val SEQ_LEN = 768          // prompt (~350 tokens) + explanation

        /** Peak resident memory of this process (VmHWM), the number reported in the technical report. */
        fun peakRssMb(): Long = try {
            File("/proc/self/status").readLines().firstOrNull { it.startsWith("VmHWM:") }
                ?.filter(Char::isDigit)?.toLong()?.div(1024) ?: -1
        } catch (_: Exception) { -1 }

        fun currentRssMb(): Long = try {
            File("/proc/self/status").readLines().firstOrNull { it.startsWith("VmRSS:") }
                ?.filter(Char::isDigit)?.toLong()?.div(1024) ?: -1
        } catch (_: Exception) { -1 }
    }
}
