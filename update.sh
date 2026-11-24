#!/usr/bin/env bash
# N8 Crosslink – Update: holt die neueste Version und behält alle Einstellungen.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Bitte als root starten: sudo $0"; exit 1; }
SRC="$(cat /opt/n8crosslink/.source 2>/dev/null || true)"
if [[ -z "$SRC" || ! -d "$SRC/.git" ]]; then
  SRC=/usr/local/src/N8Crosslink
  [[ -d "$SRC/.git" ]] || git clone https://github.com/dhartmann1979/N8Crosslink.git "$SRC"
fi
echo "› Hole Updates in $SRC …"
git -C "$SRC" pull --ff-only
N8X_UPDATE=1 bash "$SRC/install.sh"
