plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("com.google.devtools.ksp")
}

// Trusted-contact push (Firebase Cloud Messaging). The Google services plugin is applied only when the Firebase
// config app/google-services.json is present (git-ignored; M3 owns the Firebase project). Without it the app still
// builds and runs, and the trusted-contact screen says push is not set up.
if (file("google-services.json").exists()) apply(plugin = "com.google.gms.google-services")

fun env(vararg names: String): String? = names.firstNotNullOfOrNull { System.getenv(it)?.takeIf(String::isNotBlank) }

android {
    namespace = "com.satark.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.satark.app"
        minSdk = 26 // covers the older test phone; TelephonyCallback needs 31, older path uses PhoneStateListener
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // Overridable: ./gradlew -PsatarkBaseUrl=https://...
        buildConfigField("String", "BASE_URL", "\"${providers.gradleProperty("satarkBaseUrl").getOrElse("http://10.0.2.2:8000/")}\"")
        buildConfigField("String", "RAZORPAY_KEY_ID", "\"${providers.gradleProperty("satarkRazorpayKey").getOrElse("rzp_test_REPLACE_ME")}\"") // test-mode key id (public)
        // Labelled demo build only: ./gradlew assembleDebug -PsatarkLongSessionTestMin=2 shortens the 2 h long-session
        // rule so it can be shown live. Ignored in release builds (see AppGraph).
        buildConfigField("int", "LONG_SESSION_TEST_MIN", providers.gradleProperty("satarkLongSessionTestMin").getOrElse("0"))
        buildConfigField("String", "CERT_PINS", "\"${providers.gradleProperty("satarkPins").getOrElse("")}\"") // M4: contracts/pins.txt
    }

    signingConfigs {
        create("release") { // keystore comes from CI secrets (M4); absent locally -> unsigned release
            // Accepts the SATARK_* names and the names M4's release.yml exports (KEYSTORE_PATH, KEYSTORE_PASSWORD, ...).
            val ks = env("SATARK_KEYSTORE", "KEYSTORE_PATH")
            if (ks != null) {
                storeFile = file(ks)
                storePassword = env("SATARK_KEYSTORE_PASSWORD", "KEYSTORE_PASSWORD")
                keyAlias = env("SATARK_KEY_ALIAS", "KEY_ALIAS")
                keyPassword = env("SATARK_KEY_PASSWORD", "KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (env("SATARK_KEYSTORE", "KEYSTORE_PATH") != null) signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    kotlinOptions { jvmTarget = "21" }
    buildFeatures { compose = true; buildConfig = true }
    testOptions { unitTests.isReturnDefaultValues = true }
    sourceSets["main"].assets.srcDir("../contracts") // watchlist.json is read at runtime (WatchlistSource)
    // M2's 36 test vectors, shared by the JVM test and the on-device test.
    sourceSets["test"].kotlin.srcDir("src/sharedTest/kotlin")
    sourceSets["androidTest"].kotlin.srcDir("src/sharedTest/kotlin")
    sourceSets["androidTest"].assets.srcDir(layout.buildDirectory.dir("generated/vectorAssets"))
}

dependencies {
    implementation("com.satark:detector")

    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("com.jakewharton.retrofit:retrofit2-kotlinx-serialization-converter:1.0.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("androidx.camera:camera-camera2:1.4.1")
    implementation("androidx.camera:camera-lifecycle:1.4.1")
    implementation("androidx.camera:camera-view:1.4.1")
    implementation("com.google.mlkit:barcode-scanning:17.3.0")
    implementation("com.razorpay:checkout:1.6.40")
    // 33.x on purpose: newer BoMs pull a Kotlin stdlib newer than this project's Kotlin 2.0.21 compiler can read.
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging")

    testImplementation(kotlin("test"))
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    testImplementation("org.yaml:snakeyaml:2.3") // ApiContractTest reads contracts/api.yaml
    testImplementation("org.json:json:20240303") // real org.json for JVM tests (android.jar has stubs)
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}

// Only the three small vector files go into the test APK (not the 124k-row SatarkSim data).
val copyVectorAssets by tasks.registering(Sync::class) {
    from("../data/satarksim") { include("detector_test_vectors_*.csv") }
    into(layout.buildDirectory.dir("generated/vectorAssets/vectors"))
}
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("AndroidTestAssets") }.configureEach { dependsOn(copyVectorAssets) }
