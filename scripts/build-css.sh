#!/usr/bin/env sh
# Rebuilds app/static/css/app.css from app/static/src/app.css.
# Uses the standalone Tailwind CLI + daisyUI plugin files (no Node.js needed).
# The compiled CSS is committed, so you only need this after changing templates/styles.
set -eu

TAILWIND_VERSION="${TAILWIND_VERSION:-4.3.3}"
DAISYUI_VERSION="${DAISYUI_VERSION:-5.7.47}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/.tools"
mkdir -p "$TOOLS"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)  TW_ASSET="tailwindcss-linux-x64" ;;
  Linux-aarch64) TW_ASSET="tailwindcss-linux-arm64" ;;
  Darwin-arm64)  TW_ASSET="tailwindcss-macos-arm64" ;;
  Darwin-x86_64) TW_ASSET="tailwindcss-macos-x64" ;;
  *) echo "Unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

if [ ! -x "$TOOLS/tailwindcss" ]; then
  echo "Downloading Tailwind CSS v$TAILWIND_VERSION ($TW_ASSET)…"
  curl -fSL -C - --retry 5 -o "$TOOLS/tailwindcss" \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/v$TAILWIND_VERSION/$TW_ASSET"
  chmod +x "$TOOLS/tailwindcss"
fi
for f in daisyui.mjs daisyui-theme.mjs; do
  if [ ! -f "$TOOLS/$f" ]; then
    echo "Downloading $f (daisyUI v$DAISYUI_VERSION)…"
    curl -fsSL -o "$TOOLS/$f" "https://github.com/saadeghi/daisyui/releases/download/v$DAISYUI_VERSION/$f"
  fi
done

cd "$ROOT/app/static"
"$TOOLS/tailwindcss" -i src/app.css -o css/app.css --minify "$@"
