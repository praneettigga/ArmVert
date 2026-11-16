package app.saavdhan.core

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class CoreParityTest {
    @Test
    fun kotlinMatchesPythonReference() {
        val root = generateSequence(File("").absoluteFile) { it.parentFile }
            .first { File(it, "shared/rules.json").exists() }
        val failures = ParityChecker.run(root)
        assertTrue(failures.joinToString("\n"), failures.isEmpty())
    }
}
