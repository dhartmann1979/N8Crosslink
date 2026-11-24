#!/usr/bin/env bash
# Baut den N8schicht-Vocoder (libn8vocoder.so) aus den mitgelieferten Quellen.
#   third_party/n8schicht-vocoder/build.sh <ziel/libn8vocoder.so>
# Umgebungsvariablen: CXX (Standard g++), CXXFLAGS (zusätzlich)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HERE/libn8vocoder.so}"
VER="$(cat "$HERE/VERSION")"
REF="$(cut -c1-12 "$HERE/UPSTREAM_COMMIT")"
CXX="${CXX:-g++}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
"$CXX" -O2 -fPIC -shared -std=c++17 -w ${CXXFLAGS:-} \
       -DN8X_AMBE2_VERSION="\"N8schicht-Vocoder $VER (DroidStar $REF)\"" \
       -I"$HERE/src" "$HERE"/src/*.cc -o "$TMP/libn8vocoder.so"
install -m 644 "$TMP/libn8vocoder.so" "$OUT"
echo "$OUT"
