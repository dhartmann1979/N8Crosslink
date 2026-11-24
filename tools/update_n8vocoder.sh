#!/usr/bin/env bash
# Übernimmt einen neuen Stand des DroidStar-Codecs in den N8schicht-Vocoder (für Entwickler).
#   tools/update_n8vocoder.sh <commit|branch>
# Danach: tests/test_vocoder.py + tools/vocoder_test.py --compare laufen lassen, VERSION erhöhen,
# CHANGELOG und third_party/n8schicht-vocoder/README.md ergänzen.
set -euo pipefail
REF="${1:?Commit oder Branch von github.com/nostar/DroidStar angeben}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="$ROOT/third_party/n8schicht-vocoder"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
git -C "$TMP" init -q
git -C "$TMP" remote add origin https://github.com/nostar/DroidStar.git
git -C "$TMP" fetch -q --depth 1 origin "$REF"
git -C "$TMP" checkout -q FETCH_HEAD
SHA=$(git -C "$TMP" rev-parse HEAD)
rm -f "$DST"/src/*.cc "$DST"/src/*.h
for f in "$TMP"/mbe/*.cc "$TMP"/mbe/*.h; do
  case "$(basename "$f")" in mbevocoder.*|vocoder_tables.h) continue ;; esac   # brauchen Qt/IMBE, nicht nötig
  cp "$f" "$DST/src/"
done
# --- N8-Änderungen wieder einspielen ---
python3 - "$DST/src" <<'PY'
import sys, re, pathlib
d = pathlib.Path(sys.argv[1])
p = d / "decoder_synth.cc"; s = p.read_text()
s = s.replace("#include <QtGlobal>\n", "")
s = re.sub(r"//#ifdef Q_PROCESSOR_ARM_V7\n#if defined\(Q_OS_ANDROID\)[^\n]*\n",
           "// N8 Crosslink: portabler Pfad für alle Compiler ohne __int128 (z. B. 32-Bit-ARM)\n"
           "#if !defined(__SIZEOF_INT128__) || defined(N8X_FORCE_PORTABLE_MULHI)\n", s)
p.write_text(s)
p = d / "ambe2.cc"; s = p.read_text()
if "N8X_AMBE2_VERSION" not in s:
    s = re.sub(r"//const char \*ambe2_version\(void\)[^\n]*\n",
               '#ifndef N8X_AMBE2_VERSION\n#define N8X_AMBE2_VERSION "unknown"\n#endif\n'
               "const char *ambe2_version(void) { return N8X_AMBE2_VERSION; }\n", s)
p.write_text(s)
bad = [str(f) for f in d.iterdir() if "QtGlobal" in f.read_text(errors="ignore") or "Q_OS_" in f.read_text(errors="ignore")]
if bad: sys.exit("Qt-Reste: " + ", ".join(bad))
PY
echo "$SHA" > "$DST/UPSTREAM_COMMIT"
"$DST/build.sh" "$TMP/libn8vocoder.so" >/dev/null && echo "✔ DroidStar ${SHA:0:12} übernommen, Testbau ok – jetzt Tests laufen lassen und VERSION erhöhen"
