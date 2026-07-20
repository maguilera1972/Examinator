#!/usr/bin/env python3
"""Generate all Examinator user-manual PDFs on disk."""

from app.services.user_manual_service import generate_all_manuals


def main() -> None:
    written = generate_all_manuals()
    for code, path in written.items():
        print(f"{code}: {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
