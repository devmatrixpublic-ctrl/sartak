plugins {
    kotlin("jvm") version "2.0.21"
    kotlin("plugin.serialization") version "2.0.21"
}

group = "com.satark"
version = "0.1.0"

repositories { mavenCentral() }

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    testImplementation(kotlin("test"))
}

kotlin { jvmToolchain(21) }

// Shared contract copies on the classpath (single source of truth stays in contracts/ and data/).
tasks.processResources { from("../contracts") { include("reason_codes.json") } }
tasks.processTestResources {
    from("../data/satarksim") { include("detector_test_vectors_*.csv"); into("vectors") }
}

tasks.test {
    useJUnitPlatform()
    testLogging { events("passed", "skipped", "failed"); showStandardStreams = false }
}
