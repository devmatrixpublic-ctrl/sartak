package com.satark.app.events

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.satark.app.SatarkApp
import java.util.concurrent.TimeUnit

/**
 * Daily backstop that deletes event_queue rows older than 7 days, even if the app has not been opened (the dispatcher
 * prunes more tightly, 24 h, while it runs). event_queue records which apps were open and when, so it is never kept as
 * a usage history.
 */
class EventPurgeWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as? SatarkApp)?.graph ?: return Result.retry()
        return runCatching { graph.purgeOldEvents(System.currentTimeMillis()) }.fold({ Result.success() }, { Result.retry() })
    }

    companion object {
        const val RETENTION_MS = 7L * 24 * 3600_000L
        const val WORK_NAME = "satark_event_purge"

        /** Rows with tMs before this are deleted. */
        fun cutoff(nowMs: Long): Long = nowMs - RETENTION_MS

        fun schedule(ctx: Context) = runCatching {
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, PeriodicWorkRequestBuilder<EventPurgeWorker>(1, TimeUnit.DAYS).build(),
            )
        }
    }
}
