#!/usr/bin/env bash
# Install Tonado's git hooks into the local repo clone.
#
# Git hooks live under .git/hooks/, which is not tracked. We ship the
# actual hook scripts under scripts/hooks/ and point git at them by
# either symlinking or copying into place.
#
# Run once per fresh clone:
#   bash scripts/install-hooks.sh

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

src="scripts/hooks/pre-commit"
dst=".git/hooks/pre-commit"

if [[ ! -f "$src" ]]; then
  echo "error: $src not found" >&2
  exit 1
fi

mkdir -p .git/hooks

# Prefer a symlink so updates in scripts/hooks/ propagate automatically.
# On Windows without symlink support, fall back to a copy.
if ln -sf "../../$src" "$dst" 2>/dev/null; then
  echo "installed: symlink $dst -> $src"
else
  cp -f "$src" "$dst"
  echo "installed: copy    $dst (from $src)"
fi

chmod +x "$dst" 2>/dev/null || true

echo
echo "Tonado hooks installed. Feat/fix commits now require a CHANGELOG entry."
echo "Bypass (rare): SKIP_DOC_CHECK=1 git commit ..."
