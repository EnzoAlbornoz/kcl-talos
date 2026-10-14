#!/usr/bin/env bash
# Validate a generated package in build/talos:
#   1. it is already in `kcl fmt` canonical form,
#   2. every module compiles,
#   3. tests/kcl unit tests pass,
#   4. every tests/kcl/invalid/*.k snippet fails with the message in its `# expect:` line.
# Set KCL to override the kcl binary.
set -euo pipefail

KCL=${KCL:-kcl}
root=$(cd "$(dirname "$0")/.." && pwd)
pkg=$root/build/talos
[ -f "$pkg/kcl.mod" ] || { echo "no package in $pkg; run talos-kcl generate first" >&2; exit 1; }

echo "== kcl fmt is a no-op"
fmt=$root/build/fmt-check
rm -rf "$fmt" && cp -r "$pkg" "$fmt"
(cd "$fmt" && "$KCL" fmt ./... >/dev/null)
diff -r "$pkg" "$fmt"
rm -rf "$fmt"

echo "== every module compiles"
(cd "$pkg" && "$KCL" run -E talos=. talos.k >/dev/null)

echo "== unit tests"
cd "$root/tests/kcl"
"$KCL" test ./...

echo "== invalid snippets are rejected"
status=0
for f in invalid/*.k; do
  expect=$(sed -n 's/^# expect: //p' "$f")
  if out=$("$KCL" run "$f" 2>&1); then
    echo "FAIL $f: compiled and ran, expected an error containing: $expect"
    status=1
  elif ! grep -qF -- "$expect" <<<"$out"; then
    echo "FAIL $f: error did not contain: $expect"
    echo "$out"
    status=1
  else
    echo "ok   $f"
  fi
done
exit $status
