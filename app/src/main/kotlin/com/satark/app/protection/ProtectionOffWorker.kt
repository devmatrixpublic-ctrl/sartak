package com.satark.app.protection

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.satark.app.SatarkApp
import java.util.concurrent.TimeUnit

/** Ends the wait for turning protection off even if Satark is not open when it is over. */
class ProtectionOffWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val graph = (applicationContext as? SatarkApp)?.graph ?: return Result.retry()
        return runCatching { graph.protectionOff.completeIfDue() }.fold({ Result.success() }, { Result.retry() })
    }

    companion object {
        private const val WORK_NAME = "satark_protection_off"

        /** Runs [ProtectionOff.completeIfDue] after [delayMs] (a little over, so the wait has really ended). */
        fun schedule(ctx: Context, delayMs: Long) = runCatching {
            WorkManager.getInstance(ctx).enqueueUniqueWork(
                WORK_NAME, ExistingWorkPolicy.REPLACE,
                OneTimeWorkRequestBuilder<ProtectionOffWorker>().setInitialDelay(delayMs + 2_000, TimeUnit.MILLISECONDS).build(),
            )
        }
    }
}
