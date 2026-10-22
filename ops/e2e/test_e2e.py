"""Opt-in wrapper: RUN_E2E=1 pytest ops/e2e. Needs JDK 21 + Gradle (builds the detector's decisions) and the server's dev dependencies."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("run_e2e.py")


@pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 (starts the real server and runs Gradle, about 1 minute)")
def test_real_detector_decisions_drive_the_real_server():
    p = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-3000:] + p.stderr[-500:]
