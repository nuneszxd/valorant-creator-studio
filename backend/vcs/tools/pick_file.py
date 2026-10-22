"""Tiny helper process that opens a native file/folder dialog and prints the chosen path.

Runs in its own process so the GUI toolkit never touches the web server's threads.
Exit codes: 0 ok (empty output = cancelled), 3 tkinter unavailable.
"""

from __future__ import annotations

import argparse
import sys

from ..security import VIDEO_EXTENSIONS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["video", "folder"], default="video")
    args = parser.parse_args(argv)
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        return 3
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    root = tkinter.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    if args.kind == "folder":
        chosen = filedialog.askdirectory(parent=root, title="Escolha a pasta")
    else:
        patterns = " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))
        chosen = filedialog.askopenfilename(
            parent=root,
            title="Escolha o vídeo",
            filetypes=[("Vídeos", patterns), ("Todos os arquivos", "*.*")],
        )
    root.destroy()
    print(chosen or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
