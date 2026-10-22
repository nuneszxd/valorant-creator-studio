"""HTTP Range streaming for local media files (so the browser can seek inside long recordings)."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from .errors import NotFound

CHUNK = 1024 * 1024
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")

mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/mp4", ".m4v")


def range_file_response(path: Path, request: Request, *, download_name: str | None = None) -> Response:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise NotFound("Arquivo não encontrado no disco (foi movido ou apagado?).") from exc
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    start, end, status = 0, size - 1, 200

    header = request.headers.get("range")
    if header:
        match = _RANGE.match(header.strip())
        if match:
            first, last = match.groups()
            if first == "" and last == "":
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            if first == "":
                start = max(0, size - int(last))
            else:
                start = int(first)
                if last:
                    end = int(last)
            end = min(end, size - 1)
            if start >= size or end < start:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            status = 206

    length = end - start + 1

    def iterate():
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(length)}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if download_name:
        headers["Content-Disposition"] = f'attachment; filename="{download_name}"'
    return StreamingResponse(iterate(), status_code=status, media_type=media_type, headers=headers)
