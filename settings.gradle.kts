pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "satark"
include(":app")
// M2's detector stays a standalone build (its own settings) and is substituted for com.satark:detector.
includeBuild("detector")
