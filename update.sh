#!/usr/bin/env bash
# N8 Crosslink – Update: holt die neueste Version und behält alle Einstellungen.
#   sudo /opt/n8crosslink/update.sh          (von Hand)
#   update.sh --auto                         (vom Adminportal über n8crosslink-update.path)
set -euo pipefail
DATA=/opt/n8crosslink/data
LOG="$DATA/update.log"
if [[ "${1:-}" == "--auto" ]]; then
  rm -f "$DATA/update.request"
  exec > >(tee "$LOG") 2>&1
  echo "=== Update gestartet $(date '+%d.%m.%Y %H:%M:%S') ==="
fi
[[ $EUID -eq 0 ]] || { echo "Bitte als root starten: sudo $0"; exit 1; }
SRC="$(cat /opt/n8crosslink/.source 2>/dev/null || true)"
if [[ -z "$SRC" || ! -d "$SRC/.git" ]]; then
  SRC=/usr/local/src/N8Crosslink
  [[ -d "$SRC/.git" ]] || git clone https://github.com/dhartmann1979/N8Crosslink.git "$SRC"
fi
git config --global --add safe.directory "$SRC" 2>/dev/null || true
# Quellverzeichnis darf nur root gehören (daraus wird als root installiert)
chown -R root:root "$SRC"; chmod -R go-w "$SRC"
echo "› Hole Updates in $SRC …"
git -C "$SRC" fetch --quiet origin
git -C "$SRC" reset --hard --quiet "origin/$(git -C "$SRC" rev-parse --abbrev-ref HEAD)"
echo "› Version: $(grep -oP '__version__ = "\K[^"]+' "$SRC/n8crosslink/__init__.py")"
N8X_UPDATE=1 bash "$SRC/install.sh" </dev/null
chmod 644 "$LOG" 2>/dev/null || true
echo "=== Update fertig $(date '+%d.%m.%Y %H:%M:%S') ==="
