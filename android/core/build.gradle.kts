// Pure-Kotlin detection core (no Android deps) so it can be unit-tested on any JVM.
plugins {
    id("org.jetbrains.kotlin.jvm")
}

kotlin { jvmToolchain(17) }

dependencies {
    // org.json ships with Android; on the JVM we only need it to compile and test.
    compileOnly("org.json:json:20240303")
    testImplementation("org.json:json:20240303")
    testImplementation("junit:junit:4.13.2")
}
