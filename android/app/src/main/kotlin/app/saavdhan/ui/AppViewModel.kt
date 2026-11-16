package app.saavdhan.ui

import android.app.ActivityManager
import android.app.Application
import android.content.Context
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import app.saavdhan.SaavdhanApp
import app.saavdhan.core.Level
import app.saavdhan.detect.Detector
import app.saavdhan.detect.LlamaExplainer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val sa = app as SaavdhanApp
    private val prefs = app.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    var text by mutableStateOf("")
    var sender by mutableStateOf("")
    var lang by mutableStateOf(prefs.getString("lang", "en") ?: "en"); private set

    var ready by mutableStateOf(false); private set
    var result by mutableStateOf<Detector.Result?>(null); private set
    var template by mutableStateOf(""); private set
    var llmText by mutableStateOf(""); private set
    var llmRunning by mutableStateOf(false); private set
    var llmStats by mutableStateOf<LlamaExplainer.Stats?>(null); private set
    var llmNote by mutableStateOf<String?>(null); private set
    var benchText by mutableStateOf(""); private set
    var benchRunning by mutableStateOf(false); private set
    private var llmJob: Job? = null

    init {
        viewModelScope.launch(Dispatchers.Default) { sa.detector; withContext(Dispatchers.Main) { ready = true } }
    }

    val detector get() = sa.detector
    val llama get() = sa.llama

    fun updateLang(l: String) {
        lang = l
        prefs.edit().putString("lang", l).apply()
        result?.let { template = detector.explainer.template(it.verdict, l) }
    }

    fun load(t: String, s: String?) { text = t; sender = s.orEmpty(); check() }

    fun check() {
        val t = text.trim()
        if (t.isEmpty()) return
        llmJob?.cancel(); llama.stop()
        llmText = ""; llmStats = null; llmNote = null
        viewModelScope.launch {
            val r = withContext(Dispatchers.Default) { detector.analyse(t, sender.ifBlank { null }) }
            result = r
            template = detector.explainer.template(r.verdict, lang)
            if (r.verdict.level != Level.LOW && llama.isAvailable) explain()
        }
    }

    fun explain() {
        val r = result ?: return
        if (!llama.isAvailable) { llmNote = "Llama model not installed. See Setup tab."; return }
        val prompt = detector.explainer.buildPrompt(r.verdict, text.trim(), lang)
        llmText = ""; llmStats = null; llmRunning = true
        llmNote = if (llama.isLoaded) null else "Loading Llama on-device..."
        llmJob = viewModelScope.launch(Dispatchers.IO) {
            val (raw, stats) = llama.generate(prompt) { tok ->
                viewModelScope.launch(Dispatchers.Main) { llmNote = null; llmText += tok }
            }
            val g = detector.explainer.guard(raw, r.verdict, lang)
            withContext(Dispatchers.Main) {
                llmText = g.text
                llmStats = stats
                llmRunning = false
                llmNote = when {
                    raw.isEmpty() -> llama.lastError ?: "Llama produced no output"
                    g.usedFallback -> "Llama output was replaced by the detector's explanation (${g.issues.joinToString()})"
                    g.issues.isNotEmpty() -> "Cleaned: ${g.issues.joinToString()}"
                    else -> null
                }
            }
        }
    }

    fun deviceInfo(): JSONObject {
        val am = getApplication<Application>().getSystemService(ActivityManager::class.java)
        val mi = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        return JSONObject()
            .put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
            .put("soc", if (Build.VERSION.SDK_INT >= 31) "${Build.SOC_MANUFACTURER} ${Build.SOC_MODEL}" else Build.HARDWARE)
            .put("abi", Build.SUPPORTED_ABIS.firstOrNull())
            .put("cores", Runtime.getRuntime().availableProcessors())
            .put("ram_gb", String.format(Locale.US, "%.1f", mi.totalMem / 1e9))
            .put("android", Build.VERSION.RELEASE)
    }

    fun runBenchmark(includeLlama: Boolean) {
        if (benchRunning) return
        benchRunning = true
        benchText = "Running..."
        viewModelScope.launch(Dispatchers.Default) {
            val report = JSONObject().put("device", deviceInfo())
            // 1) detector latency over the sample set
            val feat = ArrayList<Double>(); val clf = ArrayList<Double>(); val rules = ArrayList<Double>(); val total = ArrayList<Double>()
            repeat(3) { Samples.all.forEach { detector.analyse(it.text, it.sender) } }        // warm-up
            repeat(20) {
                Samples.all.forEach {
                    val r = detector.analyse(it.text, it.sender)
                    feat += r.featureMs; clf += r.classifierMs; rules += r.rulesMs; total += r.totalMs
                }
            }
            report.put("detector", JSONObject()
                .put("runs", total.size)
                .put("classifier_backend", if (detector.hasClassifier) "ExecuTorch XNNPACK" else "none (rules only)")
                .put("classifier_load_ms", detector.classifierLoadMs)
                .put("features_ms", stat(feat)).put("classifier_ms", stat(clf))
                .put("rules_ms", stat(rules)).put("total_ms", stat(total)))
            report.put("demo_verdicts", JSONArray(Samples.all.map {
                val r = detector.analyse(it.text, it.sender)
                JSONObject().put("expected", it.expected).put("level", r.verdict.level.name).put("risk", round3(r.verdict.risk))
            }))
            withContext(Dispatchers.Main) { benchText = report.toString(2) }

            // 2) Llama
            if (includeLlama && llama.isAvailable) {
                val rssBefore = LlamaExplainer.currentRssMb()
                llama.ensureLoaded()
                val runs = JSONArray()
                Samples.all.filter { it.expected != "LOW" }.take(3).forEach { s ->
                    val v = detector.analyse(s.text, s.sender).verdict
                    val (raw, st) = llama.generate(detector.explainer.buildPrompt(v, s.text, "en")) {}
                    if (st != null) runs.put(JSONObject()
                        .put("prompt_tokens", st.promptTokens).put("generated_tokens", st.generatedTokens)
                        .put("ttft_ms", st.ttftMs).put("prefill_tok_s", round3(st.prefillTokPerSec))
                        .put("decode_tok_s", round3(st.decodeTokPerSec)).put("total_ms", st.totalMs)
                        .put("guard_fallback", detector.explainer.guard(raw, v, "en").usedFallback))
                }
                report.put("llama", JSONObject()
                    .put("model_file", llama.modelFile()?.name).put("model_mb", (llama.modelFile()?.length() ?: 0) / 1_000_000)
                    .put("load_ms", llama.loadMs).put("rss_before_mb", rssBefore)
                    .put("peak_rss_mb", LlamaExplainer.peakRssMb()).put("runs", runs).put("error", llama.lastError ?: JSONObject.NULL))
            } else if (includeLlama) {
                report.put("llama", "model not installed")
            }
            withContext(Dispatchers.Main) { benchText = report.toString(2); benchRunning = false }
        }
    }

    private fun round3(d: Double) = Math.round(d * 1000) / 1000.0

    private fun stat(xs: List<Double>): JSONObject {
        val s = xs.sorted()
        fun pct(p: Double) = round3(s[((s.size - 1) * p).toInt()])
        return JSONObject().put("mean", round3(s.average())).put("p50", pct(0.5)).put("p95", pct(0.95)).put("max", round3(s.last()))
    }
}
