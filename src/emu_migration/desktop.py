"""Desktop application launcher using pywebview.

Creates a native window with the embedded WebKit (macOS) or
Edge WebView2 (Windows) renderer, exposing the DesktopAPI
Python class to the frontend JS.

Launch with:
    uv run emu-migrate-desktop
    # or
    python -m emu_migration.desktop
"""

from __future__ import annotations

import sys
from pathlib import Path

import webview  # pywebview

from .desktop_api import DesktopAPI

_UI_DIR = Path(__file__).resolve().parent / "ui"


def main() -> None:
    """Entry point for the desktop application."""
    api = DesktopAPI()

    window = webview.create_window(  # noqa: F841
        title="GitHub EMU Migration Tool",
        url=str(_UI_DIR / "index.html"),
        js_api=api,
        width=1280,
        height=860,
        min_size=(900, 600),
        text_select=True,
    )

    # Start the native event loop.
    # debug=True enables right-click → Inspect Element during development.
    debug = "--debug" in sys.argv
    webview.start(debug=debug)


if __name__ == "__main__":
    main()
