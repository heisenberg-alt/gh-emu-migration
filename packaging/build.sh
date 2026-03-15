#!/usr/bin/env bash
# Build the EMU Migration desktop app for the current platform.
#
# Usage:
#   ./packaging/build.sh            # build for current OS
#   ./packaging/build.sh --clean    # clean previous build first
#
# Prerequisites:
#   pip install "pyinstaller>=6.0"
#   (or: uv pip install "pyinstaller>=6.0")
#
# Output:
#   macOS  → dist/EMU Migration.app
#   Windows → dist/EMU Migration/EMU Migration.exe

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Clean previous builds if requested
if [[ "${1:-}" == "--clean" ]]; then
    echo "Cleaning previous builds…"
    rm -rf build/ dist/ *.spec 2>/dev/null || true
fi

# Verify pyinstaller is available
if ! command -v pyinstaller &>/dev/null; then
    echo "Error: pyinstaller not found. Install with:"
    echo "  pip install 'pyinstaller>=6.0'"
    exit 1
fi

echo "Building EMU Migration desktop app…"
echo "Platform: $(uname -s) $(uname -m)"
echo ""

pyinstaller packaging/emu_migration.spec \
    --distpath dist/ \
    --workpath build/ \
    --noconfirm

echo ""
echo "Build complete!"

case "$(uname -s)" in
    Darwin)
        APP="dist/EMU Migration.app"
        if [[ -d "$APP" ]]; then
            echo "  macOS app: $APP"
            echo "  Size: $(du -sh "$APP" | cut -f1)"
            echo ""
            echo "To run:  open '$APP'"
            echo "To distribute: zip the .app or create a DMG."
        fi
        ;;
    MINGW*|MSYS*|CYGWIN*)
        EXE="dist/EMU Migration/EMU Migration.exe"
        if [[ -f "$EXE" ]]; then
            echo "  Windows exe: $EXE"
            echo "  Size: $(du -sh "dist/EMU Migration" | cut -f1)"
            echo ""
            echo "To run:  \"$EXE\""
            echo "To distribute: zip the folder or use an NSIS/Inno Setup installer."
        fi
        ;;
    *)
        echo "  Output: dist/EMU Migration/"
        ;;
esac
