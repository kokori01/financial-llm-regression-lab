"""Explicit local credential loading; no shell evaluation or secret logging."""

import os
from pathlib import Path
import stat


def load_key_file(path: Path) -> None:
    """Load only OPENAI_API_KEY from an owner-only regular file when requested."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Credential file must be owned by you and have permissions 600")
        with os.fdopen(fd, encoding="utf-8") as stream:
            fd = -1
            text = stream.read(4097)
    finally:
        if fd >= 0:
            os.close(fd)
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(text) > 4096 or len(lines) != 1 or not lines[0].startswith("OPENAI_API_KEY="):
        raise ValueError("Credential file must contain only one OPENAI_API_KEY assignment")
    key = lines[0].split("=", 1)[1].strip()
    if not key or any(c.isspace() for c in key) or any(c in key for c in "\"'`$"):
        raise ValueError("Credential file requires an unquoted, nonempty API key")
    if os.environ.get("OPENAI_API_KEY") and os.environ["OPENAI_API_KEY"] != key:
        raise ValueError("Environment and credential file disagree; select only one credential source")
    os.environ["OPENAI_API_KEY"] = key
