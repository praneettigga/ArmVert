package app.saavdhan.core

import org.json.JSONArray
import org.json.JSONObject
import java.util.regex.Pattern
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

/** One piece of evidence. Weights are log-odds contributions. Mirrors ml/saavdhan/rules.py. */
data class Signal(
    val id: String,
    val category: String,
    val weight: Double,
    val en: String,
    val hi: String,
    val advice: List<String>,
    val detail: String = "",
) {
    fun text(lang: String) = if (lang == "hi") hi else en
}

enum class Level { LOW, MEDIUM, HIGH }

data class Verdict(
    val risk: Double,
    val level: Level,
    val classifierProb: Double?,
    val signals: List<Signal>,
) {
    val positive: List<Signal> get() = signals.filter { it.weight > 0 }
}

class RuleEngine(rulesJson: String) {
    private val brands: List<String>
    private val brandWords: List<Pattern>
    private val official: List<String>
    private val shorteners: Set<String>
    private val riskyTlds: Set<String>
    private val registeredSender: Pattern
    private val mobileSender: Pattern
    private val structural: JSONObject
    private val keywordRules: List<KeywordRule>
    val advice: Map<String, Pair<String, String>>
    private val fusion: JSONObject

    private class KeywordRule(
        val id: String, val category: String, val weight: Double, val en: String, val hi: String,
        val advice: List<String>, val patterns: List<Pattern>, val negations: List<Pattern>,
    )

    init {
        val cfg = JSONObject(rulesJson)
        brands = cfg.getJSONArray("brands").strings()
        brandWords = cfg.getJSONArray("brand_words").strings().map {
            RegexCompat.compile("(^|[^a-z])" + Pattern.quote(it) + "($|[^a-z])")
        }
        official = cfg.getJSONArray("official_domain_suffixes").strings()
        shorteners = cfg.getJSONArray("url_shorteners").strings().toSet()
        riskyTlds = cfg.getJSONArray("risky_tlds").strings().toSet()
        registeredSender = RegexCompat.compile(cfg.getString("registered_sender_pattern"))
        mobileSender = RegexCompat.compile(cfg.getString("mobile_sender_pattern"))
        structural = cfg.getJSONObject("structural_signals")
        val kr = cfg.getJSONArray("keyword_rules")
        keywordRules = (0 until kr.length()).map { i ->
            val r = kr.getJSONObject(i)
            KeywordRule(
                r.getString("id"), r.getString("category"), r.getDouble("weight"), r.getString("en"), r.getString("hi"),
                r.getJSONArray("advice").strings(),
                r.getJSONArray("patterns").strings().map { RegexCompat.compile(it) },
                (r.optJSONArray("negations") ?: JSONArray()).strings().map { RegexCompat.compile("($it)\\s*$") },
            )
        }
        val adv = cfg.getJSONObject("advice")
        advice = adv.keys().asSequence().associateWith { k ->
            val o = adv.getJSONObject(k); o.getString("en") to o.getString("hi")
        }
        fusion = cfg.getJSONObject("fusion")
    }

    fun adviceText(key: String, lang: String): String =
        advice[key]?.let { if (lang == "hi") it.second else it.first } ?: key

    private fun struct(id: String, detail: String = ""): Signal {
        val s = structural.getJSONObject(id)
        return Signal(id, s.getString("category"), s.getDouble("weight"), s.getString("en"), s.getString("hi"),
            s.getJSONArray("advice").strings(), detail)
    }

    private fun isOfficial(host: String) = official.any { endsWithDomain(host, it) }

    fun mentionsBrand(norm: String) = brandWords.any { it.matcher(norm).find() }

    fun signals(text: String, sender: String?): List<Signal> {
        val norm = TextFeatures.nfkcLower(text)
        val urls = TextFeatures.extractUrls(norm)
        val brand = mentionsBrand(norm)
        return urlSignals(urls, brand) + senderSignals(sender, brand) + keywordSignals(norm)
    }

    private fun urlSignals(urls: List<TextFeatures.Url>, brandInText: Boolean): List<Signal> {
        val out = ArrayList<Signal>()
        if (urls.isEmpty()) return out
        val seen = HashSet<String>()
        var allOfficial = true
        for (u in urls) {
            val host = u.host
            val off = isOfficial(host)
            allOfficial = allOfficial && off
            if (off) continue
            val rd = registeredDomain(host)
            val tld = host.substringAfterLast('.')
            fun add(id: String) { if (seen.add(id)) out.add(struct(id, host)) }
            val isShort = host in shorteners || rd in shorteners
            if (isIpv4(host)) add("URL_IP")
            if (isShort) add("URL_SHORTENER")
            if (tld in riskyTlds) add("URL_RISKY_TLD")
            if ("xn--" in host) add("URL_PUNYCODE")
            val labels = rd.replace('-', '.').split('.') + host.replace('-', '.').split('.')
            val compact = host.replace("-", "").replace(".", "")
            if (brands.any { b -> b in labels || (b.length >= 4 && b in compact) }) add("URL_BRAND_LOOKALIKE")
            if (u.scheme == "http") add("URL_HTTP")
            if (u.path.substringBefore('?').endsWith(".apk")) add("URL_APK")
            if (brandInText && !host.endsWith("bank.in") && "URL_NOT_BANK_IN" !in seen && !isShort) add("URL_NOT_BANK_IN")
        }
        if (allOfficial) out.add(struct("URL_OFFICIAL", urls.joinToString(", ") { it.host }))
        return out
    }

    private fun senderSignals(sender: String?, brandInText: Boolean): List<Signal> {
        if (sender.isNullOrBlank()) return emptyList()
        val s = sender.trim()
        val compact = if (s.startsWith("+") || s.first().isDigit()) s.replace(" ", "").replace("-", "") else s
        if (mobileSender.matcher(compact).find() && brandInText) return listOf(struct("SENDER_MOBILE_IMPERSONATION", s))
        if (registeredSender.matcher(s.lowercase()).find()) return listOf(struct("SENDER_REGISTERED", s))
        return emptyList()
    }

    private fun keywordSignals(norm: String): List<Signal> {
        val out = ArrayList<Signal>()
        for (r in keywordRules) {
            ruleLoop@ for (p in r.patterns) {
                val m = p.matcher(norm)
                while (m.find()) {
                    val window = norm.substring(max(0, m.start() - 20), m.start())
                    if (r.negations.any { it.matcher(window).find() }) continue
                    out.add(Signal(r.id, r.category, r.weight, r.en, r.hi, r.advice, m.group().take(60)))
                    break@ruleLoop
                }
            }
        }
        return out
    }

    fun fuse(signals: List<Signal>, classifierLogit: Double?): Verdict {
        val base: Double
        val prob: Double?
        if (classifierLogit == null) {
            base = fusion.getDouble("no_classifier_prior"); prob = null
        } else {
            val clip = fusion.getDouble("classifier_clip")
            base = fusion.getDouble("classifier_scale") * max(-clip, min(clip, classifierLogit))
            prob = 1.0 / (1.0 + exp(-classifierLogit))
        }
        val z = base + fusion.getDouble("bias") + signals.sumOf { it.weight }
        val risk = 1.0 / (1.0 + exp(-z))
        val level = when {
            risk >= fusion.getDouble("high_threshold") -> Level.HIGH
            risk >= fusion.getDouble("medium_threshold") -> Level.MEDIUM
            else -> Level.LOW
        }
        return Verdict(risk, level, prob, signals.sortedByDescending { it.weight })
    }

    fun analyse(text: String, sender: String? = null, classifierLogit: Double? = null): Verdict =
        fuse(signals(text, sender), classifierLogit)

    companion object {
        private val SECOND_LEVEL = setOf("co", "gov", "nic", "bank", "fin", "org", "net", "ac", "edu", "res", "gen", "firm", "ind")
        private val IPV4 = Regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}$")

        fun registeredDomain(host: String): String {
            val p = host.split('.')
            return if (p.size >= 3 && p[p.size - 2] in SECOND_LEVEL) p.takeLast(3).joinToString(".")
            else p.takeLast(2).joinToString(".")
        }

        fun isIpv4(host: String) = IPV4.matches(host) && host.split('.').all { it.toInt() <= 255 }

        fun endsWithDomain(host: String, suffix: String) = host == suffix || host.endsWith(".$suffix")

        private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
    }
}
