"""Run in your own Terminal. The key is never echoed or sent to chat."""

import getpass
import os
from pathlib import Path
import sys
import warnings


def main() -> int:
    if not sys.stdin.isatty():
        print("Run this helper in your own interactive Terminal; no key was read.")
        return 2
    target = Path(__file__).resolve().parents[1] / ".env.local"
    if target.exists():
        print("A local credential file already exists; it was not overwritten.")
        return 2
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("OpenAI API key (hidden; paste here, then press Enter): ").strip()
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        print("Secure input unavailable or cancelled; nothing saved.")
        return 2
    if not key or any(c.isspace() for c in key) or any(c in key for c in "\"'`$"):
        print("No valid key supplied; nothing saved.")
        return 2
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("OPENAI_API_KEY=" + key + "\n")
    print("Saved to .env.local with owner-only permissions. No API call was made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
