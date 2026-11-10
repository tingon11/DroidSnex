plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.droidsnex.agent"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.droidsnex.agent"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Per comodità la release è firmata con la chiave di debug:
            // l'APK è pensato per il sideload via adb sul proprio telefono.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

// Nessuna dipendenza a runtime: solo framework Android + stdlib Kotlin.
// JUnit solo per i test JVM dello stack di rete (./gradlew test).
dependencies {
    testImplementation("junit:junit:4.13.2")
}
