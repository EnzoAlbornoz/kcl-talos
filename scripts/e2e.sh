#!/usr/bin/env bash
# End-to-end check of a generated package: render patches with KCL, apply them to a fresh
# config with the real `talosctl machineconfig patch`, then assert on the result in KCL.
#
# Usage: scripts/e2e.sh [suite...]   suites live in tests/e2e/<suite>/ (default: all)
# A suite with a `min-version` file is skipped for older packages.
# Expects the package in build/talos; set KCL / TALOSCTL to override the binaries.
set -euo pipefail

KCL=${KCL:-kcl}
TALOSCTL=${TALOSCTL:-talosctl}

cd "$(dirname "$0")/../tests/e2e"
version=$(sed -n 's/^version = "\(.*\)"/\1/p' ../../build/talos/kcl.mod)
[ $# -gt 0 ] || set -- $(ls -d */ | tr -d /)

run_suite() {
  local suite=$1
  # Relative paths keep this working with native Windows binaries under Git Bash, and the
  # output stays inside the suite directory, where KCL's file.read is allowed to read.
  local work=$suite/.out
  rm -rf "$work" && mkdir -p "$work"

  "$TALOSCTL" gen config e2e https://10.5.0.2:6443 --output-types controlplane \
    --with-docs=false --with-examples=false -o "$work/base.yaml" >/dev/null
  local current=$work/base.yaml

  # Stages are applied in this order when present; each one patches the previous result.
  for stage in add patch delete; do
    [ -f "$suite/$stage.k" ] || continue
    "$KCL" run "$suite/$stage.k" >"$work/$stage.yaml"
    echo "--- $suite/$stage.k"
    cat "$work/$stage.yaml"
    "$TALOSCTL" machineconfig patch "$current" --patch "@$work/$stage.yaml" -o "$work/after-$stage.yaml"
    current=$work/after-$stage.yaml
  done

  # file.read resolves paths relative to the KCL file.
  "$KCL" run "$suite/verify.k" -D patched="${current#"$suite/"}"
}

for suite in "$@"; do
  if [ -f "$suite/min-version" ]; then
    min=$(tr -d 'v \r\n' <"$suite/min-version")
    if [ "$(printf '%s\n%s\n' "$min" "${version%%-*}" | sort -V | head -1)" != "$min" ]; then
      echo "=== skipping e2e suite '$suite': needs Talos >= $min, package is $version"
      continue
    fi
  fi
  echo "=== e2e suite '$suite' (Talos $version)"
  run_suite "$suite"
  echo "=== e2e suite '$suite' passed"
done
