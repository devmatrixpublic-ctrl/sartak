"""Structural checks on the GitHub workflows. They cannot prove the jobs pass on GitHub's runners (nothing
here can), but they pin the properties that matter: least privilege, no fork-secret exposure, release gating,
and that every script a step calls actually exists."""
import re
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
                                           "dependency-scan", "docker", "stubs", "android"}


def test_gitleaks_scans_full_history():
    job = load("ci.yml")["jobs"]["secrets-scan"]
    assert job["steps"][0]["with"]["fetch-depth"] == 0
    assert "gitleaks" in run_lines(load("ci.yml"))


def test_pr_stub_check_looks_at_what_the_pr_adds():
    wf = load("ci.yml")
    assert wf["jobs"]["stubs"]["steps"][0]["with"]["fetch-depth"] == 0
    assert "--new-since" in run_lines(wf)


def test_evaluation_is_soft_only_through_the_explicit_variable():
    job = load("ci.yml")["jobs"]["evaluation"]
    assert "EVAL_GATE_ENFORCED" in str(job["continue-on-error"])
    assert "run_eval.py" in run_lines({"jobs": {"e": job}})


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
