#!/bin/bash
# Build Voca.app (py2app) and package it into an unsigned .dmg for release.
#
#   bash scripts/build_app.sh
#
# Produces dist/Voca.app and dist/Voca-1.1.0.dmg. Requires the venv with deps
# plus py2app (pip install -r requirements-dev.txt). Models are NOT bundled —
# the app downloads them on first launch.
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION="1.1.0"
DMG="dist/Voca-${VERSION}.dmg"

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Generating assets/icon.icns from assets/icon.png"
ICONSET="$(mktemp -d)/Voca.iconset"
mkdir -p "$ICONSET"
for sz in 16 32 128 256 512; do
  sips -z $sz $sz assets/icon.png --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
  d=$((sz * 2))
  sips -z $d $d assets/icon.png --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
sips -z 1024 1024 assets/icon.png --out "$ICONSET/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$ICONSET" -o assets/icon.icns

echo "==> Building Voca.app with py2app"
rm -rf build dist
python setup.py py2app

echo "==> Packaging $DMG"
STAGE="dist/dmg-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "dist/Voca.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Voca" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo "==> Done"
echo "    App: dist/Voca.app  ($(du -sh dist/Voca.app | cut -f1))"
echo "    DMG: $DMG  ($(du -sh "$DMG" | cut -f1))"
