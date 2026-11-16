package app.saavdhan.core

import org.json.JSONObject
import java.io.File
import kotlin.math.abs

/**
 * Checks the Kotlin core against shared/test_vectors.json produced by ml/tests/make_vectors.py.
 * Runs from JUnit (CoreParityTest) or standalone: `kotlin ParityCheckerKt <repoRoot>`.
 */
object ParityChecker {
    fun run(repoRoot: File): List<String> {
        val rules = File(repoRoot, "shared/rules.json").readText()
        val vectors = JSONObject(File(repoRoot, "shared/test_vectors.json").readText())
        val engine = RuleEngine(rules)
        val failures = mutableListOf<String>()

        val hashes = vectors.getJSONObject("fnv1a32")
        for (k in hashes.keys()) {
            val got = TextFeatures.fnv1a32(k)
            if (got != hashes.getLong(k)) failures += "fnv1a32('$k'): kotlin $got python ${hashes.getLong(k)}"
        }

        val cases = vectors.getJSONArray("cases")
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val text = c.getString("text")
            val tag = "case $i '${text.take(40)}'"
            if (TextFeatures.nfkcLower(text) != c.getString("normalized")) failures += "$tag: normalized differs"
            val urls = TextFeatures.extractUrls(TextFeatures.nfkcLower(text)).map { "${it.scheme}|${it.host}|${it.path}" }
            val pyUrls = c.getJSONArray("urls").let { a -> (0 until a.length()).map { a.getJSONObject(it) }
                .map { "${it.getString("scheme")}|${it.getString("host")}|${it.getString("path")}" } }
            if (urls != pyUrls) failures += "$tag: urls kotlin $urls python $pyUrls"
            val toks = TextFeatures.modelTokens(text)
            val pyToks = c.getJSONArray("tokens").let { a -> (0 until a.length()).map { a.getString(it) } }
            if (toks != pyToks) failures += "$tag: tokens kotlin $toks python $pyToks"
            val ids = TextFeatures.featureIds(text)
            val pyIds = c.getJSONArray("feature_ids").let { a -> LongArray(a.length()) { a.getLong(it) } }
            if (!ids.contentEquals(pyIds)) {
                val first = ids.indices.first { ids[it] != pyIds.getOrElse(it) { -1 } }
                failures += "$tag: feature ids differ at index $first"
            }
            val sender = if (c.isNull("sender")) null else c.getString("sender")
            val logit = if (c.isNull("classifier_logit")) null else c.getDouble("classifier_logit")
            val v = engine.analyse(text, sender, logit)
            val sig = v.signals.map { it.id }
            val pySig = c.getJSONArray("signals").let { a -> (0 until a.length()).map { a.getString(it) } }
            if (sig != pySig) failures += "$tag: signals kotlin $sig python $pySig"
            if (abs(v.risk - c.getDouble("risk")) > 1e-5) failures += "$tag: risk kotlin ${v.risk} python ${c.getDouble("risk")}"
            if (v.level.name.lowercase() != c.getString("level")) failures += "$tag: level kotlin ${v.level} python ${c.getString("level")}"
        }

        // explainer smoke checks
        val ex = Explainer(engine)
        val v = engine.analyse("Update KYC http://sbi-kyc.xyz now", "9876543210")
        val prompt = ex.buildPrompt(v, "Update KYC http://sbi-kyc.xyz now", "en")
        if ("sbi-kyc[.]xyz" !in prompt || "http://sbi-kyc.xyz" in prompt) failures += "prompt: link not defanged"
        val g = ex.guard("Why: It looks like a scam. Do: visit www.sbi-help.xyz or call 9876543210. Call 1930.", v, "en")
        if ("sbi-help" in g.text || "9876543210" in g.text || "1930" !in g.text) failures += "guard: did not clean output: ${g.text}"
        if (!ex.guard("Why: This message is safe and genuine.", v, "en").usedFallback) failures += "guard: no fallback on contradiction"
        return failures
    }
}

fun main(args: Array<String>) {
    val root = File(args.firstOrNull() ?: "../..")
    val failures = ParityChecker.run(root)
    if (failures.isEmpty()) println("PARITY OK: Kotlin core matches Python reference")
    else { failures.forEach { println("FAIL $it") }; kotlin.system.exitProcess(1) }
}
