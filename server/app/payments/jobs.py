"""Background job boundary for the handed_off -> no_result timeout sweep.

Runs on its own thread with its own DB session; never shares a session with
a request. Safe to no-op on Render's free tier while the service sleeps —
`sweep_if_stale` covers the gap by re-evaluating on read (see
app/payments/service.py).
"""

import logging
import threading

from sqlalchemy.orm import sessionmaker

from app.payments.service import sweep_stale_handed_off

logger = logging.getLogger("satark.payments.jobs")


class TimeoutSweeper:
    def __init__(self, session_factory: sessionmaker, *, interval_seconds: int = 60, ttl_seconds: int):
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._ttl_seconds = ttl_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _run_once(self) -> None:
        db = self._session_factory()
        try:
            swept = sweep_stale_handed_off(db, ttl_seconds=self._ttl_seconds)
            if swept:
                logger.info("timeout_sweep", extra={"swept_count": swept})
        except Exception:
            logger.exception("timeout_sweep_failed")
        finally:
            db.close()

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            self._run_once()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="satark-timeout-sweeper", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
