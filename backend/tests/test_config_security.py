from __future__ import annotations

import pytest

from vcs.config import AppConfig, ConfigError, parse_env_file
from vcs.errors import Forbidden, InvalidInput, NotFound
from vcs.security import (
    ensure_within,
    host_without_port,
    redact,
    safe_filename,
    validate_directory,
    validate_media_file,
)


def test_parse_env_file_ignores_comments_and_strips_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# comment\nA=1\nB="two words"\n\nC=\nNOEQUALS\n', encoding="utf-8")
    assert parse_env_file(env) == {"A": "1", "B": "two words", "C": ""}


def test_from_env_defaults_are_local(monkeypatch):
    for name in ("VCS_HOST", "VCS_PORT", "VCS_DATA_DIR", "VCS_ALLOW_NON_LOCAL"):
        monkeypatch.delenv(name, raising=False)
    config = AppConfig.from_env()
    assert config.host == "127.0.0.1"
    assert config.port == 8000


def test_from_env_rejects_non_local_host(monkeypatch):
    monkeypatch.setenv("VCS_HOST", "0.0.0.0")
    monkeypatch.delenv("VCS_ALLOW_NON_LOCAL", raising=False)
    with pytest.raises(ConfigError):
        AppConfig.from_env()


def test_from_env_rejects_bad_port(monkeypatch):
    monkeypatch.setenv("VCS_PORT", "abc")
    with pytest.raises(ConfigError):
        AppConfig.from_env()


def test_secrets_are_not_in_repr_and_integrations_are_booleans(tmp_path):
    config = AppConfig(
        data_dir=tmp_path, twitch_client_id="id-123456", twitch_client_secret="secret-abcdef",
        youtube_api_key="AIza-key-123456",
    )
    text = repr(config)
    assert "secret-abcdef" not in text and "AIza-key-123456" not in text
    assert config.integrations() == {"twitch": True, "youtube": True}


def test_host_without_port():
    assert host_without_port("127.0.0.1:8000") == "127.0.0.1"
    assert host_without_port("localhost") == "localhost"
    assert host_without_port("[::1]:8000") == "::1"
    assert host_without_port("Evil.Example:80") == "evil.example"


def test_validate_media_file_ok_and_errors(tmp_path):
    video = tmp_path / "partida.MP4"
    video.write_bytes(b"x")
    assert validate_media_file(str(video)) == video.resolve()
    assert validate_media_file(f'"{video}"') == video.resolve()

    with pytest.raises(InvalidInput):
        validate_media_file("")
    with pytest.raises(InvalidInput):
        validate_media_file("relativo/partida.mp4")
    with pytest.raises(InvalidInput):
        validate_media_file("\\\\servidor\\share\\x.mp4")
    with pytest.raises(NotFound):
        validate_media_file(str(tmp_path / "nao_existe.mp4"))
    other = tmp_path / "notas.txt"
    other.write_text("x")
    with pytest.raises(InvalidInput):
        validate_media_file(str(other))
    with pytest.raises(InvalidInput):
        validate_media_file(str(tmp_path))


def test_validate_directory(tmp_path):
    target = tmp_path / "saida" / "cortes"
    assert validate_directory(str(target), create=True) == target.resolve()
    with pytest.raises(InvalidInput):
        validate_directory("relativo")
    with pytest.raises(NotFound):
        validate_directory(str(tmp_path / "nada"))


def test_ensure_within(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "a" / "b.txt"
    assert ensure_within(inside, root) == inside.resolve()
    with pytest.raises(Forbidden):
        ensure_within(tmp_path / "outside.txt", root)
    with pytest.raises(Forbidden):
        ensure_within(root / ".." / "outside.txt", root)


def test_safe_filename():
    assert safe_filename("Clutch 1v3 — Ascent!.mp4") == "Clutch_1v3_Ascent_.mp4"
    assert safe_filename("../../etc/passwd") == "etc_passwd"
    assert safe_filename("???") == "arquivo"
    assert safe_filename("CON").startswith("_")
    assert len(safe_filename("a" * 500)) == 80


def test_network_paths_are_refused_before_touching_the_filesystem():
    from pathlib import PureWindowsPath

    from vcs.security import _reject_network_path

    for value in ("\\\\srv\\share\\a.mp4", "//srv/share/a.mp4", "/\\srv\\share\\a.mp4"):
        with pytest.raises(InvalidInput):
            _reject_network_path(value, PureWindowsPath(value))
    _reject_network_path("D:\\videos\\a.mp4", PureWindowsPath("D:\\videos\\a.mp4"))  # a normal drive is fine


def test_redact_handles_json_quoted_tokens_and_error_text():
    from vcs.errors import AppError
    from vcs.security import error_text

    out = redact('{"access_token": "abcdef123456", "other": 1} and api_key="AIzaSyXXXX1234"')
    assert "abcdef123456" not in out and "AIzaSyXXXX1234" not in out
    text = error_text(AppError("falha com client_secret=top-secret-value"), ["top-secret-value"])
    assert "top-secret-value" not in text
    assert error_text(RuntimeError("boom")).startswith("RuntimeError")


def test_redact_masks_keys_tokens_and_known_secrets():
    text = "client_secret=abc12345 and Authorization: Bearer abcdefghijklmnop key"
    out = redact(text)
    assert "abc12345" not in out and "abcdefghijklmnop" not in out
    assert redact("my-secret-value is here", ["my-secret-value"]) == "*** is here"
    assert redact("nothing to hide") == "nothing to hide"
