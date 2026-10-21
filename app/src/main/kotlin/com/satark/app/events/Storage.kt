package com.satark.app.events

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

/** Every mapped event, stored as schema.json JSON, so a crashed session can be inspected. No raw numbers or VPAs. */
@Entity(tableName = "event_queue")
data class EventRow(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val tMs: Long,
    val json: String,
    val dispatched: Boolean = false,
)

@Entity(tableName = "decision_log")
data class DecisionRow(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val tMs: Long,
    val level: String,
    val score: Double,
    val reasons: String, // comma-separated reason codes
    val mechanism: String?,
)

@Entity(tableName = "known_payee")
data class KnownPayee(@PrimaryKey val hash: String)

/** Completed payments only: the baseline never learns from held attempts. */
@Entity(tableName = "completed_payment")
data class CompletedPayment(@PrimaryKey(autoGenerate = true) val id: Long = 0, val amountInr: Double)

/** Calls that failed offline and are retried later (/alert, /signature). */
@Entity(tableName = "queued_call")
data class QueuedCall(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val kind: String, // "alert" | "signature"
    val body: String,
    val attempts: Int = 0,
)

@Dao
interface SatarkDao {
    @Insert suspend fun insertEvent(e: EventRow): Long
    @Query("UPDATE event_queue SET dispatched = 1 WHERE id = :id") suspend fun markDispatched(id: Long)
    @Query("DELETE FROM event_queue WHERE tMs < :before") suspend fun pruneEvents(before: Long)
    @Query("DELETE FROM decision_log WHERE tMs < :before") suspend fun pruneDecisions(before: Long)
    @Query("SELECT * FROM event_queue WHERE tMs >= :since ORDER BY tMs, id") suspend fun eventsSince(since: Long): List<EventRow>

    @Insert suspend fun insertDecision(d: DecisionRow)

    @Insert(onConflict = OnConflictStrategy.IGNORE) suspend fun addPayee(p: KnownPayee)
    @Query("SELECT COUNT(*) FROM known_payee WHERE hash = :hash") suspend fun payeeCount(hash: String): Int

    @Insert suspend fun addCompleted(p: CompletedPayment)
    @Query("SELECT amountInr FROM completed_payment ORDER BY id DESC LIMIT :n") suspend fun lastAmounts(n: Int): List<Double>

    @Insert suspend fun enqueue(q: QueuedCall)
    @Query("SELECT * FROM queued_call ORDER BY id") suspend fun queued(): List<QueuedCall>
    @Query("DELETE FROM queued_call WHERE id = :id") suspend fun dequeue(id: Long)
    @Query("UPDATE queued_call SET attempts = attempts + 1 WHERE id = :id") suspend fun bump(id: Long)
}

@Database(
    entities = [EventRow::class, DecisionRow::class, KnownPayee::class, CompletedPayment::class, QueuedCall::class],
    version = 1,
    exportSchema = false,
)
abstract class SatarkDb : RoomDatabase() {
    abstract fun dao(): SatarkDao

    companion object {
        fun create(ctx: Context) = Room.databaseBuilder(ctx, SatarkDb::class.java, "satark.db").build()
    }
}
