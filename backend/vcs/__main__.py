"""Command line: `python -m vcs serve` / `python -m vcs doctor`."""

from __future__ import annotations

import argparse
import dataclasses
import os
import socket
import sys
import threading
import webbrowser

from .config import AppConfig, ConfigError, check_host, load_dotenv
from .security import setup_logging


def _port_free(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host in ("localhost", "::1") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((bind_host, port))
        except OSError:
            return False
    return True


def _serve(args: argparse.Namespace) -> int:
    load_dotenv()
    try:
        config = AppConfig.from_env()
        overrides: dict[str, object] = {}
        if args.host:
            check_host(args.host)
            overrides["host"] = args.host
        if args.port:
            overrides["port"] = args.port
        if overrides:
            config = dataclasses.replace(config, **overrides)
    except ConfigError as exc:
        print(f"Configuração inválida: {exc}", file=sys.stderr)
        return 2

    if not _port_free(config.host, config.port):
        print(
            f"A porta {config.port} já está em uso. Feche a outra instância do aplicativo "
            f"ou use --port com outro número.",
            file=sys.stderr,
        )
        return 2

    setup_logging(config.logs_dir, config.secrets())
    import uvicorn

    from .main import create_app

    app = create_app(config)
    # timeout_graceful_shutdown: an open <video> keeps a streaming response alive; do not wait for it forever.
    server = uvicorn.Server(
        uvicorn.Config(app, host=config.host, port=config.port, log_level="info", timeout_graceful_shutdown=5)
    )
    app.state.server = server
    url = f"http://{'127.0.0.1' if config.host == 'localhost' else config.host}:{config.port}"
    print(f"\nValorant Creator Studio em {url}  (Ctrl+C para encerrar)\n")
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    pid_file = config.data_dir / "vcs.pid"
    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    try:
        server.run()
    finally:
        try:
            pid_file.unlink()
        except OSError:
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vcs", description="Valorant Creator Studio")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="inicia o servidor local")
    serve.add_argument("--host", help="endereço local (padrão 127.0.0.1)")
    serve.add_argument("--port", type=int, help="porta (padrão 8000)")
    serve.add_argument("--open", action="store_true", help="abre o navegador ao iniciar")

    doctor = sub.add_parser("doctor", help="verifica o ambiente (FFmpeg, Python, dependências)")
    doctor.add_argument("--deep", action="store_true", help="faz testes reais de codificação")
    doctor.add_argument("--json", action="store_true", help="saída em JSON")

    args = parser.parse_args(argv)
    if args.cmd == "serve":
        return _serve(args)
    from . import doctor as doctor_module

    return doctor_module.main(deep=args.deep, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
