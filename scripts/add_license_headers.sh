#!/usr/bin/env bash
# Add license headers to tracked files if missing.
set -euo pipefail

PROJECT="isightViewer"
COPYRIGHT="Copyright (c) 2025 Robert Čmrlec"
LICENSE_LINE="Licensed under the GNU General Public License v3.0"
NOTICE="$PROJECT
$COPYRIGHT
$LICENSE_LINE
See LICENSE file for details."

# comment wrappers by extension
header_for_ext() {
  case "$1" in
    html|xml)   printf "<!--\n %s\n-->\n\n" "$NOTICE" ;;
    sh|bash)    printf "# %s\n\n" "$NOTICE" ;;
    py|yml|yaml|md) printf "# %s\n\n" "$NOTICE" ;;
    js|css|c|cpp|h|java|ts) printf "/*\n %s\n*/\n\n" "$NOTICE" ;;
    *) printf "# %s\n\n" "$NOTICE" ;; # fallback
  esac
}

# iterate tracked files
git ls-files -z | while IFS= read -r -d '' file; do
  ext="${file##*.}"
  # skip binary-ish and LICENSE
  case "$file" in
    LICENSE|*.png|*.jpg|*.jpeg|*.gif|*.pdf) continue ;;
  esac
  # skip files that already contain the copyright or license line
  if grep -q -E "Copyright .*2025|Licensed under the GNU" -- "$file"; then
    continue
  fi
  header="$(header_for_ext "$ext")"
  tmp="$(mktemp)"
  printf "%s" "$header" > "$tmp"
  cat "$file" >> "$tmp"
  mv "$tmp" "$file"
  echo "Prepended header to: $file"
done

echo "Done. Review changes, then git add & commit."
