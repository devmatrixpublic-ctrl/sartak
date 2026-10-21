plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("com.google.devtools.ksp")
}

android {
    namespace = "com.satark.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.satark.app"
        minSdk = 26 // covers the older test phone; TelephonyCallback needs 31, older path uses PhoneStateListener
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        // Overridable: ./gradlew -PsatarkBaseUrl=https://...
        buildConfigField("String", "BASE_URL", "\"${providers.gradleProperty("satarkBaseUrl").getOrElse("http://10.0.2.2:8000/")}\"")
        buildConfigField("String", "RAZORPAY_KEY_ID", "\"${providers.gradleProperty("satarkRazorpayKey").getOrElse("rzp_test_REPLACE_ME")}\"") // test-mode key id (public)
        buildConfigField("String", "CERT_PINS", "\"${providers.gradleProperty("satarkPins").getOrElse("")}\"") // M4: contracts/pins.txt
    }

    signingConfigs {
        create("release") { // keystore comes from CI secrets (M4); absent locally -> unsigned release
            val ks = System.getenv("SATARK_KEYSTORE")
            if (ks != null) {
                storeFile = file(ks)
                storePassword = System.getenv("SATARK_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("SATARK_KEY_ALIAS")
                keyPassword = System.getenv("SATARK_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (System.getenv("SATARK_KEYSTORE") != null) signingConfig = signingConfigs.getByName("release")
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

    testImplementation(kotlin("test"))
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}
