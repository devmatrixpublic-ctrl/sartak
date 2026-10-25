package com.satark.app.guard

import android.os.Build
import android.os.Environment
import java.io.File

/** "All files access": Android 11 and newer keep other apps' files out of reach without it. Older versions are not supported by the guard. */
fun hasAllFilesAccess(): Boolean = Build.VERSION.SDK_INT >= 30 && runCatching { Environment.isExternalStorageManager() }.getOrDefault(false)

/**
 * Where downloaded and received files land. The watcher is not recursive, so each folder is listed. A folder that does not exist on this
 * phone (no WhatsApp, say) is left out.
 */
fun watchedDownloadDirs(): List<File> {
    val root = Environment.getExternalStorageDirectory()
    return listOf(
        Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
        Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS),
        File(root, "Download/Telegram"),
        File(root, "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents"),
        File(root, "Android/media/com.whatsapp.w4b/WhatsApp Business/Media/WhatsApp Business Documents"),
        File(root, "Android/media/org.telegram.messenger/Telegram/Telegram Documents"),
        File(root, "WhatsApp/Media/WhatsApp Documents"),
    ).filter { it.isDirectory }
}
