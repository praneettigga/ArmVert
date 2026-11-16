package app.saavdhan.core

import java.util.regex.Pattern

/**
 * Compiles patterns written for Python `re.ASCII | re.IGNORECASE` so they behave the same on
 * the JVM and on Android, whose java.util.regex is ICU-based with Unicode `\w`, `\b`, `\s`, `\d`.
 * The shorthand classes are rewritten to explicit ASCII sets before compiling.
 */
object RegexCompat {
    private const val WORD = "a-z0-9_"
    private const val SPACE = " \\t\\n\\r\\f\\u000B"
    private const val BOUNDARY = "(?:(?<![$WORD])(?=[$WORD])|(?<=[$WORD])(?![$WORD]))"

    fun toAscii(p: String): String {
        val sb = StringBuilder()
        var inClass = false
        var i = 0
        while (i < p.length) {
            val c = p[i]
            if (c == '\\' && i + 1 < p.length) {
                val n = p[i + 1]
                val rep = if (inClass) when (n) {
                    'w' -> WORD; 'd' -> "0-9"; 's' -> SPACE; else -> null
                } else when (n) {
                    'w' -> "[$WORD]"; 'W' -> "[^$WORD]"; 'd' -> "[0-9]"; 'D' -> "[^0-9]"
                    's' -> "[$SPACE]"; 'S' -> "[^$SPACE]"; 'b' -> BOUNDARY; else -> null
                }
                if (rep != null) sb.append(rep) else sb.append(c).append(n)
                i += 2
                continue
            }
            if (c == '[' && !inClass) inClass = true
            else if (c == ']' && inClass) inClass = false
            sb.append(c)
            i++
        }
        return sb.toString()
    }

    fun compile(p: String): Pattern = Pattern.compile(toAscii(p), Pattern.CASE_INSENSITIVE)
}
