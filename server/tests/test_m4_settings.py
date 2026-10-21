"""Startup validation: unsafe auth configuration must refuse to boot."""
import pytest

from app.auth.config import validate_auth_settings
from app.core.settings import DEV_JWT_SECRET, Settings

GOOD_SECRET = "p" * 48


def prod(tmp_path, **kw):
    roots = tmp_path / "roots.pem"
    roots.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n")
    base = dict(env="production", jwt_secret=GOOD_SECRET, auth_expected_package="com.satark.app",
                auth_expected_signing_sha256="ab" * 32, auth_attestation_roots_path=str(roots))
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
    ({"auth_attestation_roots_path": "/does/not/exist.pem"}, "ATTESTATION_ROOTS"),
    ({"auth_attestation_roots_path": ""}, "ATTESTATION_ROOTS"),
])
def test_unsafe_production_settings_refuse_to_boot(tmp_path, kw, msg):
    with pytest.raises(RuntimeError, match=msg):
        validate_auth_settings(prod(tmp_path, **kw))


def test_dev_token_flag_refused_outside_dev():
    with pytest.raises(RuntimeError, match="only allowed"):
        validate_auth_settings(Settings(env="staging", auth_enable_dev_token=True, jwt_secret=GOOD_SECRET))
