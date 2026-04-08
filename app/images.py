import base64
import mimetypes
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from .config import settings


def save_image_to_temp(url: str, workdir: Optional[Path] = None) -> str:
    """Fetch an image URL or data URI to a temporary file and return its path."""
    try:
        if url.startswith("data:"):
            header, b64data = url.split(",", 1)
            mime = header.split(";")[0][5:] if header.startswith("data:") else "image"
            suffix = mimetypes.guess_extension(mime) or ".png"
            data = base64.b64decode(b64data)
        else:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme == "file":
                with open(urllib.request.url2pathname(parsed.path), "rb") as fh:
                    data = fh.read()
                suffix = os.path.splitext(parsed.path)[1] or ".png"
            else:
                with urllib.request.urlopen(url) as resp:
                    data = resp.read()
                suffix = os.path.splitext(parsed.path)[1] or ".png"
        target_dir = str(workdir) if workdir is not None else settings.codex_workdir
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=target_dir) as f:
            f.write(data)
            return f.name
    except Exception as e:
        raise ValueError(f"failed to load image: {e}")
