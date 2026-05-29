#!/usr/bin/env bash
# Append (or refresh) the Tonado image flash instructions + checksums on a
# release, without clobbering the changelog body the release process wrote.
#
# Idempotent: a marker comment delimits our block, so a re-run (e.g. a
# workflow_dispatch rebuild) replaces it in place instead of stacking copies.
#
# Usage: release-notes.sh <tag>
# Reference: docs/fuer-entwickler/pi-image-ci.md section 4.

set -euo pipefail

TAG="${1:?usage: release-notes.sh <tag>}"
MARKER="<!-- tonado-image-notes -->"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Checksum files uploaded by the build matrix.
gh release download "$TAG" --pattern 'SHA256SUMS-*.txt' --dir "$WORK" || true

# Preserve the existing body up to (but not including) any previous block.
EXISTING="$(gh release view "$TAG" --json body -q .body 2>/dev/null || true)"
BASE="${EXISTING%%"$MARKER"*}"

{
  printf '%s\n' "$BASE"
  printf '%s\n\n' "$MARKER"
  echo "## Image flashen"
  echo
  echo "1. [Raspberry Pi Imager](https://www.raspberrypi.com/software/) öffnen"
  echo "2. \"Eigenes Image wählen\" antippen und die passende \`.img.xz\` unten auswählen"
  echo "3. SD-Karte flashen, Pi einstecken, Handy mit dem WLAN \"Tonado-Setup\" verbinden — der Rest läuft im Browser"
  echo
  echo "## Varianten"
  echo
  echo "| Hardware | Datei |"
  echo "|---|---|"
  echo "| Pi 3B+ / 4 / 5 / Zero 2 W (64-bit) | \`tonado-${TAG}-pi-3plus-4-5.img.xz\` |"
  echo "| Pi Zero W (32-bit) | \`tonado-${TAG}-pi-zero-w.img.xz\` |"
  echo
  echo "## Prüfsummen (SHA256)"
  echo
  echo '```'
  if ls "$WORK"/SHA256SUMS-*.txt >/dev/null 2>&1; then
    cat "$WORK"/SHA256SUMS-*.txt
  else
    echo "(keine Prüfsummen-Dateien am Release gefunden)"
  fi
  echo '```'
  echo
  echo "Prüfen mit \`sha256sum -c SHA256SUMS-*.txt\`."
  echo
  echo "<details><summary>Signatur prüfen (cosign keyless, optional)</summary>"
  echo
  echo '```bash'
  echo "cosign verify-blob \\"
  echo "  --certificate <datei>.img.xz.pem \\"
  echo "  --signature  <datei>.img.xz.sig \\"
  echo "  --certificate-identity-regexp 'https://github.com/t13gazh/tonado/.*' \\"
  echo "  --certificate-oidc-issuer https://token.actions.githubusercontent.com \\"
  echo "  <datei>.img.xz"
  echo '```'
  echo
  echo "</details>"
} > "$WORK/notes.md"

gh release edit "$TAG" --notes-file "$WORK/notes.md"
echo "Release notes updated for $TAG."
