package app.saavdhan.core

import java.text.Normalizer
import java.util.Locale

/**
 * Text normalisation, URL extraction and feature hashing.
 * Must stay identical to ml/saavdhan/text.py (checked by ParityChecker against shared/test_vectors.json).
 */
object TextFeatures {
    const val NUM_BUCKETS = 65536
    const val MAX_FEATURES = 512
    private val CHAR_NGRAMS = intArrayOf(3, 4)

    private val URL_RE = RegexCompat.compile(
        "(?:https?://|www\\.)[^\\s<>\"']+" +
            "|\\b(?:[a-z0-9-]+\\.)+(?:com|in|net|org|info|xyz|top|icu|click|live|shop|online|site|buzz|vip|cyou|rest|sbs|cfd|" +
            "monster|gq|tk|ml|cf|ga|ly|cc|co|me|io|app|link|club|fun|pw|work|support|help|loan|win|bond|gl|gd|to|at|ru|ws|it|sbi)" +
            "\\b(?:/[^\\s<>\"']*)?",
    )
    private val TRAIL = ".,;:!?)]}'\"".toCharArray()

    data class Url(val raw: String, val scheme: String, val host: String, val path: String)

    fun nfkcLower(text: String): String =
        Normalizer.normalize(text, Normalizer.Form.NFKC).lowercase(Locale.ROOT)

    fun extractUrls(norm: String): List<Url> {
        val out = ArrayList<Url>()
        val m = URL_RE.matcher(norm)
        while (m.find()) {
            val start = m.start()
            if (start > 0 && norm[start - 1] == '@') continue
            val raw = m.group().trimEnd(*TRAIL)
            var rest = raw
            var scheme = ""
            if (rest.startsWith("http://")) { scheme = "http"; rest = rest.substring(7) }
            else if (rest.startsWith("https://")) { scheme = "https"; rest = rest.substring(8) }
            var cut = rest.length
            for (ch in "/?#") {
                val i = rest.indexOf(ch)
                if (i != -1 && i < cut) cut = i
            }
            var host = rest.substring(0, cut)
            val at = host.lastIndexOf('@')
            if (at != -1) host = host.substring(at + 1)
            val colon = host.indexOf(':')
            if (colon != -1) host = host.substring(0, colon)
            if (host.startsWith("www.")) host = host.substring(4)
            host = host.trim('.')
            if (host.isNotEmpty()) out.add(Url(raw, scheme, host, rest.substring(cut)))
        }
        return out
    }

    private fun isTokenChar(c: Char): Boolean =
        c in 'a'..'z' || c in '0'..'9' || c.code in 0x0900..0x097F || c == '₹'

    private fun digitPlaceholder(n: Int): String = when {
        n <= 2 -> "0"
        n <= 5 -> "00"
        n <= 9 -> "000"
        else -> "0000"
    }

    fun modelTokens(text: String): List<String> {
        var norm = nfkcLower(text)
        val urls = extractUrls(norm)
        val sb = StringBuilder()
        var pos = 0
        for (u in urls) {
            val i = norm.indexOf(u.raw, pos)
            if (i == -1) continue
            sb.append(norm, pos, i)
            val tld = if ('.' in u.host) u.host.substringAfterLast('.') else "none"
            sb.append(" xurl xtld").append(tld).append(' ')
            pos = i + u.raw.length
        }
        sb.append(norm, pos, norm.length)
        norm = sb.toString()

        val tokens = ArrayList<String>()
        val buf = StringBuilder()
        var i = 0
        val n = norm.length
        while (i < n) {
            val c = norm[i]
            if (c in '0'..'9') {
                var j = i
                while (j < n && norm[j] in '0'..'9') j++
                buf.append(digitPlaceholder(j - i))
                i = j
                continue
            }
            if (isTokenChar(c)) buf.append(c)
            else if (buf.isNotEmpty()) { tokens.add(buf.toString()); buf.setLength(0) }
            i++
        }
        if (buf.isNotEmpty()) tokens.add(buf.toString())
        return tokens
    }

    fun featureStrings(text: String): List<String> {
        val toks = modelTokens(text)
        val feats = ArrayList<String>()
        for (t in toks) feats.add("w:$t")
        for (k in 0 until toks.size - 1) feats.add("b:${toks[k]} ${toks[k + 1]}")
        for (t in toks) {
            val padded = "<$t>"
            for (n in CHAR_NGRAMS) {
                for (k in 0..padded.length - n) feats.add("c:" + padded.substring(k, k + n))
            }
        }
        return if (feats.size > MAX_FEATURES) feats.subList(0, MAX_FEATURES) else feats
    }

    fun fnv1a32(s: String): Long {
        var h = 0x811C9DC5L
        for (b in s.toByteArray(Charsets.UTF_8)) {
            h = h xor (b.toLong() and 0xFF)
            h = (h * 0x01000193L) and 0xFFFFFFFFL
        }
        return h
    }

    /** Fixed-length id vector (padded with 0) fed to the ExecuTorch classifier. */
    fun featureIds(text: String): LongArray {
        val out = LongArray(MAX_FEATURES)
        featureStrings(text).forEachIndexed { i, f -> out[i] = fnv1a32(f) % (NUM_BUCKETS - 1) + 1 }
        return out
    }
}
