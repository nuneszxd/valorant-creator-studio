"""Environment check: `python -m vcs doctor [--deep] [--json]`.

Prints what is installed and what is missing, so problems can be fixed (or reported) quickly.
Never prints secret values - only whether each credential is set.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import sys
from typing import Any

from .config import AppConfig, load_dotenv
from .media.ffmpeg import FFmpegTools

OK, WARN, FAIL, INFO = "OK", "AVISO", "FALHA", "INFO"


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def run_checks(config: AppConfig, *, deep: bool = False) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    version = sys.version_info
    checks.append(
        _check(
            "Python",
            OK if version >= (3, 11) else FAIL,
            f"{platform.python_version()} ({platform.system()} {platform.release()})"
            + ("" if version >= (3, 11) else " - é preciso Python 3.11 ou superior"),
        )
    )

    tools = FFmpegTools.discover(config.ffmpeg_path, config.ffprobe_path)
    if tools.ffmpeg:
        checks.append(_check("FFmpeg", OK, f"{tools.ffmpeg} - {tools.version() or 'versão desconhecida'}"))
    else:
        checks.append(_check("FFmpeg", FAIL, "não encontrado no PATH (instale ou defina VCS_FFMPEG_PATH)"))
    checks.append(
        _check("ffprobe", OK if tools.ffprobe else FAIL, tools.ffprobe or "não encontrado (acompanha o FFmpeg)")
    )

    if tools.ffmpeg:
        encoders = tools.encoders()
        filters = tools.filters()
        checks.append(
            _check("Encoder libx264 (CPU)", OK if "libx264" in encoders else FAIL,
                   "disponível" if "libx264" in encoders else "ausente nesta build do FFmpeg")
        )
        for name, label in (("h264_amf", "AMD"), ("h264_nvenc", "NVIDIA"), ("h264_qsv", "Intel")):
            checks.append(
                _check(f"Encoder {name} ({label})", INFO,
                       "listado pelo FFmpeg (use --deep para testar de verdade)" if name in encoders
                       else "não listado")
            )
        checks.append(
            _check("Filtro 'ass' (legendas)", OK if "ass" in filters else WARN,
                   "disponível" if "ass" in filters else "ausente: use uma build 'full' do FFmpeg para legendas")
        )
        checks.append(
            _check("Filtros boxblur/loudnorm", OK if {"boxblur", "loudnorm"} <= filters else WARN,
                   "disponíveis" if {"boxblur", "loudnorm"} <= filters else "ausentes nesta build")
        )
        if deep:
            ok, detail = tools.test_encoder("libx264")
            checks.append(_check("Teste real libx264", OK if ok else FAIL, "codificou 15 quadros" if ok else detail))
            if "h264_amf" in encoders:
                ok, detail = tools.test_encoder("h264_amf")
                checks.append(
                    _check("Teste real h264_amf", OK if ok else WARN,
                           "codificou 15 quadros" if ok else f"falhou: {detail}")
                )

    fw = importlib.util.find_spec("faster_whisper") is not None
    checks.append(
        _check(
            "faster-whisper (transcrição)",
            OK if fw else WARN,
            "instalado (roda na CPU com GPU AMD)" if fw else 'não instalado: pip install -e "backend[transcribe]"',
        )
    )
    tk = importlib.util.find_spec("tkinter") is not None
    checks.append(_check("tkinter (seletor de arquivos)", OK if tk else WARN,
                         "disponível" if tk else "ausente: será preciso digitar o caminho dos arquivos"))

    node = shutil.which("node")
    checks.append(_check("Node.js (só para compilar a interface)", OK if node else WARN, node or "não encontrado"))
    dist_ok = (config.frontend_dist / "index.html").is_file()
    checks.append(
        _check("Interface compilada", OK if dist_ok else WARN,
               str(config.frontend_dist) if dist_ok else "não compilada (rode scripts\\setup.bat)")
    )

    try:
        config.ensure_dirs()
        probe = config.data_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(_check("Pasta de dados gravável", OK, str(config.data_dir)))
    except OSError as exc:
        checks.append(_check("Pasta de dados gravável", FAIL, f"{config.data_dir}: {exc}"))

    integrations = config.integrations()
    checks.append(_check("Credenciais Twitch", INFO, "configuradas" if integrations["twitch"] else "não configuradas (opcional)"))
    checks.append(_check("Chave YouTube", INFO, "configurada" if integrations["youtube"] else "não configurada (opcional)"))
    return checks


def format_report(checks: list[dict[str, Any]]) -> str:
    width = max(len(c["name"]) for c in checks)
    lines = [f"{c['status']:<6} {c['name']:<{width}}  {c['detail']}" for c in checks]
    failures = sum(1 for c in checks if c["status"] == FAIL)
    warnings = sum(1 for c in checks if c["status"] == WARN)
    lines.append("")
    lines.append(f"Resumo: {failures} falha(s), {warnings} aviso(s).")
    return "\n".join(lines)


def main(*, deep: bool = False, as_json: bool = False) -> int:
    load_dotenv()
    config = AppConfig.from_env()
    checks = run_checks(config, deep=deep)
    print(json.dumps(checks, ensure_ascii=False, indent=2) if as_json else format_report(checks))
    return 1 if any(c["status"] == FAIL for c in checks) else 0
