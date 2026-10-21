"""Startup validation: unsafe auth configuration must refuse to boot."""
import pytest

from app.auth.config import expected_signing_digests, validate_auth_settings
from app.core.settings import DEV_JWT_SECRET, Settings

GOOD_SECRET = "p" * 48


def prod(tmp_path, **kw):
    roots = tmp_path / "roots.pem"
    roots.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    base = dict(env="production", jwt_secret=GOOD_SECRET, auth_expected_package="com.satark.app",
                auth_expected_signing_sha256="ab" * 32, auth_attestation_roots=str(roots))
    base.update(kw)
    return Settings(**base)


def test_dev_defaults_boot():
    validate_auth_settings(Settings(env="dev"))


def test_valid_production_boots(tmp_path):
    validate_auth_settings(prod(tmp_path))


@pytest.mark.parametrize("kw,msg", [
    ({"jwt_secret": DEV_JWT_SECRET}, "SATARK_JWT_SECRET"),
    ({"jwt_secret": "short"}, "SATARK_JWT_SECRET"),
    ({"auth_enable_dev_token": True}, "only allowed when SATARK_ENV=dev"),
    ({"auth_require_hardware": False}, "hardware"),
    ({"auth_expected_package": ""}, "EXPECTED_PACKAGE"),
    ({"auth_expected_signing_sha256": ""}, "EXPECTED_PACKAGE"),
    ({"auth_attestation_roots": "/does/not/exist.pem"}, "ATTESTATION_ROOTS"),
    ({"auth_attestation_roots": ""}, "ATTESTATION_ROOTS"),
])
def test_unsafe_production_settings_refuse_to_boot(tmp_path, kw, msg):
    with pytest.raises(RuntimeError, match=msg):
        validate_auth_settings(prod(tmp_path, **kw))


def test_dev_token_flag_refused_outside_dev():
    with pytest.raises(RuntimeError, match="only allowed"):
        validate_auth_settings(Settings(env="staging", auth_enable_dev_token=True, jwt_secret=GOOD_SECRET))


def test_documented_env_var_names_actually_configure_the_settings(monkeypatch, tmp_path):
    """Every SATARK_AUTH_* name in contracts/auth.md and render.yaml must map to a real field.
    (A field named ..._roots_path silently ignored SATARK_AUTH_ATTESTATION_ROOTS and could never boot.)"""
    roots = tmp_path / "roots.pem"
    roots.write_text("x")
    for name, value in {
        "SATARK_ENV": "production",
        "SATARK_JWT_SECRET": GOOD_SECRET,
        "SATARK_AUTH_ATTESTATION_ROOTS": str(roots),
        "SATARK_AUTH_EXPECTED_PACKAGE": "com.satark.app",
        "SATARK_AUTH_EXPECTED_SIGNING_SHA256": "AB" * 32 + "," + "cd" * 32,
        "SATARK_AUTH_REQUIRE_HARDWARE": "true",
        "SATARK_AUTH_ENABLE_DEV_TOKEN": "false",
    }.items():
        monkeypatch.setenv(name, value)
    s = Settings()
    assert s.auth_attestation_roots == str(roots)
    assert s.auth_expected_package == "com.satark.app"
    assert expected_signing_digests(s) == frozenset({"ab" * 32, "cd" * 32})
    validate_auth_settings(s)          # a fully env-configured production config boots


def test_every_documented_auth_env_var_exists_in_the_docs_and_render_blueprint():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    docs = (root / "contracts" / "auth.md").read_text(encoding="utf-8")
    render = (root / "render.yaml").read_text(encoding="utf-8")
    m4_fields = ("auth_attestation_roots", "auth_expected_package", "auth_expected_signing_sha256",
                 "auth_require_hardware", "auth_enable_dev_token")
    for field in m4_fields:
        assert field in Settings.model_fields
        assert field.upper() in docs.upper().replace("`", ""), f"{field} not documented in contracts/auth.md"
    for var in ("SATARK_AUTH_ATTESTATION_ROOTS", "SATARK_AUTH_EXPECTED_PACKAGE", "SATARK_AUTH_EXPECTED_SIGNING_SHA256"):
        assert var in render
        assert var.removeprefix("SATARK_").lower() in Settings.model_fields


def test_migrations_use_their_own_connection_when_one_is_set():
    s = Settings(database_url="postgresql://satark_app@h/db")
    assert s.effective_migration_url == "postgresql://satark_app@h/db"          # falls back
    s = Settings(database_url="postgresql://satark_app@h/db", migration_database_url="postgresql://owner@h/db")
    assert s.effective_migration_url == "postgresql://owner@h/db"
    assert s.database_url == "postgresql://satark_app@h/db"                      # runtime stays least-privilege


def test_alembic_env_reads_the_migration_url(monkeypatch, tmp_path):
    import subprocess, sys
    db = tmp_path / "mig.db"
    env = dict(**__import__("os").environ, SATARK_DATABASE_URL="sqlite:///./should_not_be_used.db",
               SATARK_MIGRATION_DATABASE_URL=f"sqlite:///{db.as_posix()}")
    server_dir = __import__("pathlib").Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=server_dir, env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-500:]
    assert db.exists() and not (server_dir / "should_not_be_used.db").exists()
