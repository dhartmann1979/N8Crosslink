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
OLD_REV=$(git -C "$SRC" rev-parse HEAD 2>/dev/null || true)
OLD_VER=$(grep -oP '__version__ = "\K[^"]+' /opt/n8crosslink/n8crosslink/__init__.py 2>/dev/null || echo "?")
echo "› Hole Updates in $SRC …"
git -C "$SRC" fetch --quiet origin
git -C "$SRC" reset --hard --quiet "origin/$(git -C "$SRC" rev-parse --abbrev-ref HEAD)"
NEW_VER=$(grep -oP '__version__ = "\K[^"]+' "$SRC/n8crosslink/__init__.py")
echo "› Version: $OLD_VER → $NEW_VER"
set +e
N8X_UPDATE=1 bash "$SRC/install.sh" </dev/null
RC=$?
set -e
if [[ $RC -eq 3 && -n "$OLD_REV" && "$OLD_REV" != "$(git -C "$SRC" rev-parse HEAD)" ]]; then
  # Neue Version startet nicht -> vorige Version wiederherstellen, damit das Dashboard erreichbar bleibt
  echo "⚠ Version $NEW_VER startet nicht – stelle $OLD_VER wieder her (${OLD_REV:0:7}) …"
  git -C "$SRC" reset --hard --quiet "$OLD_REV"
  set +e; N8X_UPDATE=1 bash "$SRC/install.sh" </dev/null; RC2=$?; set -e
  mkdir -p "$DATA"; date '+%s' > "$DATA/update.rollback"; echo "$NEW_VER" >> "$DATA/update.rollback"
  # gleiches Ergebnis-Format wie der N8 update guard der anderen N8schicht-Projekte (Admin → Updates → Letztes Update)
  printf '{"ok": false, "from": "%s", "to": "%s", "time": %s, "message": "zurückgesetzt auf %s"}\n' "$OLD_VER" "$NEW_VER" "$(date +%s)" "$OLD_VER" > "$DATA/update.result"
  chmod 644 "$LOG" 2>/dev/null || true
  echo "=== Update auf $NEW_VER fehlgeschlagen – $OLD_VER wiederhergestellt (Rückgabe $RC2) $(date '+%d.%m.%Y %H:%M:%S') ==="
  echo "    Bitte die Ausgabe oben bzw. sudo /opt/n8crosslink/install.sh --diagnose an den Entwickler schicken."
  exit 1
elif [[ $RC -ne 0 ]]; then
  chmod 644 "$LOG" 2>/dev/null || true
  echo "=== Update mit Fehler beendet (Rückgabe $RC) $(date '+%d.%m.%Y %H:%M:%S') ==="
  exit "$RC"
fi
rm -f "$DATA/update.rollback"
if [[ "$OLD_VER" != "$NEW_VER" || "$OLD_REV" != "$(git -C "$SRC" rev-parse HEAD)" ]]; then
  mkdir -p "$DATA"
  printf '{"ok": true, "from": "%s", "to": "%s", "time": %s, "message": ""}\n' "$OLD_VER" "$NEW_VER" "$(date +%s)" > "$DATA/update.result"
  chmod 644 "$DATA/update.result" 2>/dev/null || true
fi
chmod 644 "$LOG" 2>/dev/null || true
echo "=== Update fertig $(date '+%d.%m.%Y %H:%M:%S') ==="
