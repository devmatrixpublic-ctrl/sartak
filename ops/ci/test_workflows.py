"""Structural checks on the GitHub workflows. They cannot prove the jobs pass on GitHub's runners (nothing
here can), but they pin the properties that matter: least privilege, no fork-secret exposure, release gating,
and that every script a step calls actually exists."""
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"


def load(name):
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def steps(wf):
    for job in wf["jobs"].values():
        yield from job.get("steps", [])


def run_lines(wf):
    return "\n".join(s.get("run", "") for s in steps(wf))


@pytest.fixture(params=["ci.yml", "release.yml"])
def wf(request):
    return load(request.param)


def test_workflows_parse_and_have_jobs(wf):
    assert wf["jobs"]


def test_least_privilege_and_no_dangerous_trigger(wf):
    assert wf["permissions"] == {"contents": "read"}
    triggers = wf.get("on", wf.get(True))
    assert "pull_request_target" not in triggers


def test_every_action_is_version_pinned(wf):
    uses = [s["uses"] for s in steps(wf) if "uses" in s]
    assert uses
    assert all(re.search(r"@[\w.\-]+$", u) for u in uses), uses


def test_pull_request_workflow_never_touches_secrets():
    text = (WF / "ci.yml").read_text(encoding="utf-8")
    assert "secrets." not in text


def test_expected_pr_jobs_exist():
    assert set(load("ci.yml")["jobs"]) == {"server", "contracts", "detector", "evaluation", "secrets-scan",
                                           "dependency-scan", "docker", "stubs", "android", "tls-tool", "integration"}


def test_gitleaks_scans_full_history():
    job = load("ci.yml")["jobs"]["secrets-scan"]
    assert job["steps"][0]["with"]["fetch-depth"] == 0
    assert "gitleaks" in run_lines(load("ci.yml"))


def test_pr_stub_check_looks_at_what_the_pr_adds():
    wf = load("ci.yml")
    assert wf["jobs"]["stubs"]["steps"][0]["with"]["fetch-depth"] == 0
    assert "--new-since" in run_lines(wf)


def test_evaluation_is_soft_only_through_the_explicit_variable_and_only_on_the_gate_step():
    job = load("ci.yml")["jobs"]["evaluation"]
    assert "continue-on-error" not in job                      # job-level would show a red check run
    gate = [s for s in job["steps"] if "run_eval.py" in s.get("run", "")]
    assert len(gate) == 1 and "EVAL_GATE_ENFORCED" in str(gate[0]["continue-on-error"])
    assert any("::warning" in s.get("run", "") for s in job["steps"])      # and the miss stays visible


def test_release_is_gated_before_anything_ships():
    rel = load("release.yml")
    assert rel["jobs"]["server-image"]["needs"] == "gate"
    assert rel["jobs"]["android-release"]["needs"] == "gate"
    gate = run_lines({"jobs": {"g": rel["jobs"]["gate"]}})
    assert "check_stubs.py ." in gate and "run_eval.py" in gate and "validate_strings.py" in gate


def test_release_never_softens_a_gate():
    text = (WF / "release.yml").read_text(encoding="utf-8")
    assert "continue-on-error" not in text and "|| true" not in text


def test_release_secrets_are_only_passed_through_env():
    text = (WF / "release.yml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if "secrets." in line:
            assert "${{ secrets." in line and ("env:" in text), line
    assert not re.search(r"(echo|run:).*\$\{\{ *secrets\.", text)             # never interpolated into a script body


def test_every_script_a_step_calls_exists(wf):
    text = run_lines(wf)
    for rel in set(re.findall(r"(?:python|pytest)\s+(ops/[\w./-]+\.py|detector/tools/[\w./-]+\.py)", text)):
        assert (ROOT / rel).is_file(), rel
    assert (ROOT / "server" / "Dockerfile").is_file() and (ROOT / "ops" / "requirements-eval.txt").is_file()


def test_tls_tool_job_uses_python_313_or_newer():
    job = load("ci.yml")["jobs"]["tls-tool"]
    step = [s for s in job["steps"] if s.get("uses", "").startswith("actions/setup-python")][0]
    assert tuple(int(x) for x in str(step["with"]["python-version"]).split(".")) >= (3, 13)


def test_dependency_scan_upgrades_pip_before_auditing():
    job = load("ci.yml")["jobs"]["dependency-scan"]
    text = run_lines({"jobs": {"d": job}})
    assert text.index("install --upgrade pip") < text.index("pip-audit --skip-editable")


def test_every_java_setup_matches_the_toolchain_the_projects_require():
    """The app (`JavaVersion.VERSION_21`, `jvmTarget = "21"`) and the detector (`jvmToolchain(21)`) need JDK 21. A runner with
    an older JDK fails the first Android job with a toolchain error, so every setup-java step must provide the required one."""
    pattern = re.compile(r"VERSION_(\d+)|jvmTarget\s*=\s*\"(\d+)\"|jvmToolchain\((\d+)\)")
    required = [int(g) for f in ("app/build.gradle.kts", "detector/build.gradle.kts")
                for m in pattern.findall((ROOT / f).read_text(encoding="utf-8")) for g in m if g]
    assert required, "could not read the required JDK from the Gradle files"
    need = max(required)
    for name in ("ci.yml", "release.yml"):
        for s in steps(load(name)):
            if str(s.get("uses", "")).startswith("actions/setup-java"):
                got = int(s["with"]["java-version"])
                assert got >= need, f"{name}: setup-java provides JDK {got} but the projects need {need}"


def test_the_gradle_wrapper_is_executable_in_git():
    """`./gradlew` is run by the Android jobs; mode 100644 makes them fail with exit code 126 ("not executable"), which is exactly
    how the first Android CI run failed. Windows checkouts silently drop the bit, so pin it."""
    p = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", "gradlew"], capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        pytest.skip("not a git checkout or no gradlew in the repo")
    assert p.stdout.split()[0] == "100755", f"gradlew has git mode {p.stdout.split()[0]}; run: git update-index --chmod=+x gradlew"


def test_integration_job_uses_real_postgres_and_redis_and_cannot_pass_by_skipping():
    job = load("ci.yml")["jobs"]["integration"]
    assert job["services"]["postgres"]["image"].startswith("postgres:") and job["services"]["redis"]["image"].startswith("redis:")
    assert "test" in job["env"]["SATARK_TEST_POSTGRES_URL"].rsplit("/", 1)[1]        # the tests refuse to wipe other databases
    assert job["env"]["SATARK_TEST_REDIS_URL"].startswith("redis://")
    for service in job["services"].values():
        assert "--health-cmd" in service["options"]                                  # wait until the service is ready
    text = run_lines({"jobs": {"i": job}})
    assert "tests/test_it_postgres.py" in text and "tests/test_it_redis.py" in text and "tests/test_it_stores.py" in text
    assert "SATARK_TEST_" in text and "exit 1" in text                              # skip detection
