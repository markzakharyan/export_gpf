#!/usr/bin/env bash
set -euo pipefail

# Simple installer for the Export GPF KLayout macro and Yale Freebeam.
# Override the variables below to customize paths or mirror URLs:
#   KLAYOUT_MACRO_DIR  - destination for export_gpf.py (default: ~/.klayout/macros)
#   FREEBEAM_PREFIX    - install prefix for Freebeam (default: ~/.local/freebeam)
#   FREEBEAM_URL       - tarball containing a gpfout binary (default: Yale GitHub release)
#   PIP                - pip executable (default: python3 -m pip)
#   PATH_BIN_DIR       - directory to symlink gpfout into (default: ~/.local/bin)

KLAYOUT_MACRO_DIR=${KLAYOUT_MACRO_DIR:-"$HOME/.klayout/macros"}
FREEBEAM_PREFIX=${FREEBEAM_PREFIX:-"$HOME/.local/freebeam"}
FREEBEAM_URL=${FREEBEAM_URL:-"https://github.com/yale-microlab/freebeam/releases/latest/download/freebeam-linux-x86_64.tar.gz"}
PIP=${PIP:-"python3 -m pip"}
PATH_BIN_DIR=${PATH_BIN_DIR:-"$HOME/.local/bin"}

mkdir -p "$KLAYOUT_MACRO_DIR" "$FREEBEAM_PREFIX" "$PATH_BIN_DIR"

# Install Python dependencies for the macro
$PIP install --upgrade pip
$PIP install --upgrade gdstk

# Install Freebeam if gpfout is not already present
if command -v gpfout >/dev/null 2>&1 || [ -n "${FREEBEAM_BIN:-}" ]; then
  echo "Freebeam gpfout already present (PATH or FREEBEAM_BIN). Skipping download."
else
  tmpdir=$(mktemp -d)
  cleanup() { rm -rf "$tmpdir"; }
  trap cleanup EXIT
  echo "Downloading Freebeam from $FREEBEAM_URL"
  curl -L "$FREEBEAM_URL" -o "$tmpdir/freebeam.tar.gz"
  tar -xzf "$tmpdir/freebeam.tar.gz" -C "$FREEBEAM_PREFIX"
  if [ ! -x "$FREEBEAM_PREFIX/gpfout" ]; then
    echo "Expected gpfout inside $FREEBEAM_PREFIX. Please adjust FREEBEAM_URL or install manually." >&2
    exit 1
  fi
  ln -sf "$FREEBEAM_PREFIX/gpfout" "$PATH_BIN_DIR/gpfout"
  echo "Installed gpfout to $FREEBEAM_PREFIX and symlinked into $PATH_BIN_DIR"
fi

# Copy macro
cp export_gpf.py "$KLAYOUT_MACRO_DIR/"

cat <<EON
Installation complete.
- Macro copied to: $KLAYOUT_MACRO_DIR/export_gpf.py
- Ensure KLayout loads macros from that directory and enable autorun.
- Verify Freebeam is discoverable via PATH or set FREEBEAM_BIN to the installed gpfout.
EON
