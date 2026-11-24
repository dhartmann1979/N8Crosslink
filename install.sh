#!/usr/bin/env bash
# =============================================================================
#  N8 Crosslink – geführter Installer
#  FRN · DMR · Zello Bridge im Die-N8schicht-Design (nur Python, ohne SvxLink)
#  Debian 12/13, Ubuntu 22.04+, Raspberry Pi OS, DietPi (amd64 / arm64 / armhf)
# =============================================================================
set -euo pipefail

APP_DIR="/opt/n8crosslink"
DATA_DIR="$APP_DIR/data"
DB="$DATA_DIR/crosslink.db"
SVC_USER="n8crosslink"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS=9

# ---------------------------------------------------------------- Ausgabe
if [[ -t 1 ]]; then
  B=$'\e[1m'; D=$'\e[2m'; R=$'\e[0m'; C=$'\e[38;5;81m'; G=$'\e[38;5;77m'; Y=$'\e[38;5;221m'; E=$'\e[38;5;203m'; M=$'\e[38;5;141m'
else B=""; D=""; R=""; C=""; G=""; Y=""; E=""; M=""; fi
step()  { echo; echo "${C}${B}━━ [$1/$STEPS] $2 ${R}"; }
info()  { echo "  ${C}›${R} $*"; }
ok()    { echo "  ${G}✔${R} $*"; }
warn()  { echo "  ${Y}⚠${R} $*"; }
fail()  { echo "  ${E}✖ $*${R}"; exit 1; }

ask() {        # ask VAR "Frage" "Vorgabe"
  local __v="$1" q="$2" def="${3:-}" a
  read -r -p "  ${B}?${R} $q ${D}[${def}]${R}: " a </dev/tty || true
  printf -v "$__v" '%s' "${a:-$def}"
}
ask_secret() { # ask_secret VAR "Frage" (leer erlaubt, wenn $3=optional)
  local __v="$1" q="$2" opt="${3:-}" a
  while true; do
    read -r -s -p "  ${B}?${R} $q: " a </dev/tty || true; echo
    [[ -n "$a" || "$opt" == "optional" ]] && break
    warn "Bitte einen Wert eingeben."
  done
  printf -v "$__v" '%s' "$a"
}
ask_yn() {     # ask_yn "Frage" j|n  -> Rückgabe 0 = ja
  local q="$1" def="${2:-j}" a hint="J/n"
  [[ "$def" == "n" ]] && hint="j/N"
  read -r -p "  ${B}?${R} $q ${D}[$hint]${R}: " a </dev/tty || true
  a="${a:-$def}"; [[ "$a" =~ ^[jJyY] ]]
}
ask_choice() { # ask_choice VAR "Frage" "Vorgabe" opt1 opt2 ...
  local __v="$1" q="$2" def="$3"; shift 3
  local i=1 o; for o in "$@"; do echo "     ${M}$i)${R} $o"; i=$((i+1)); done
  local a; read -r -p "  ${B}?${R} $q ${D}[$def]${R}: " a </dev/tty || true
  printf -v "$__v" '%s' "${a:-$def}"
}
# ---------------------------------------------------------------- Berechtigungen
# Programm, Skripte und venv gehören root (schreibgeschützt für den Dienst), nur data/ gehört dem Dienst.
# Wichtig: update.sh läuft über n8crosslink-update.service als root und darf deshalb NICHT
# vom Dienstbenutzer veränderbar sein.
fix_perms() {
  local n=0 f dev="" mode=""
  [[ -d "$APP_DIR" ]] || return 0
  if [[ -f "$DB" ]]; then   # vor der Rechtekorrektur lesen (sqlite legt ggf. WAL-Dateien an)
    dev=$(sqlite3 "$DB" "SELECT value FROM settings WHERE section='vocoder' AND key='usb_device'" 2>/dev/null | tr -d '"')
    mode=$(sqlite3 "$DB" "SELECT value FROM settings WHERE section='vocoder' AND key='vocoder_mode'" 2>/dev/null | tr -d '"')
  fi
  n=$(find "$APP_DIR" -path "$DATA_DIR" -prune -o ! -type l \( ! -user root -o ! -group root -o -perm /022 \) -print 2>/dev/null | wc -l)
  rm -rf "$APP_DIR/.cache"
  find "$APP_DIR" -path "$DATA_DIR" -prune -o -exec chown -h root:root {} +
  find "$APP_DIR" -path "$DATA_DIR" -prune -o -type d -exec chmod 755 {} +
  find "$APP_DIR" -path "$DATA_DIR" -prune -o -path "$APP_DIR/venv/bin" -prune -o -type f \
       ! -name '*.key' ! -name '*.pem' ! -name '*.p12' -exec chmod 644 {} +
  [[ -d "$APP_DIR/venv/bin" ]] && chmod -R go-w "$APP_DIR/venv/bin" && find "$APP_DIR/venv/bin" -type f -exec chmod 755 {} + 2>/dev/null || true
  for f in install.sh update.sh uninstall.sh; do [[ -f "$APP_DIR/$f" ]] && chmod 755 "$APP_DIR/$f"; done
  # private Schlüssel/Zertifikate (z. B. zello.key) nur für root lesbar
  local k; while IFS= read -r k; do chmod 600 "$k"; n=$((n + 1)); warn "Schlüsseldatei $k war lesbar – auf 600 gesetzt (wird nicht mehr gebraucht, liegt in der Datenbank)"; done \
    < <(find "$APP_DIR" -path "$DATA_DIR" -prune -o -path "$APP_DIR/venv" -prune -o -type f \( -name '*.key' -o -name '*.pem' -o -name '*.p12' \) -perm /044 -print 2>/dev/null)
  mkdir -p "$DATA_DIR"
  local m; m=$(find "$DATA_DIR" \( ! -user "$SVC_USER" ! -name update.log \) -print 2>/dev/null | wc -l)
  chown -R "$SVC_USER:$SVC_USER" "$DATA_DIR"
  chmod 750 "$DATA_DIR"
  find "$DATA_DIR" -type f -name '*.db*' -exec chmod 640 {} +
  [[ -f "$DATA_DIR/update.log" ]] && chmod 644 "$DATA_DIR/update.log"
  for f in n8crosslink.service n8crosslink-update.path n8crosslink-update.service; do
    [[ -f "/etc/systemd/system/$f" ]] && chown root:root "/etc/systemd/system/$f" && chmod 644 "/etc/systemd/system/$f"
  done
  if id "$SVC_USER" &>/dev/null && ! id -nG "$SVC_USER" | grep -qw dialout; then
    usermod -a -G dialout "$SVC_USER" && warn "Dienstbenutzer war nicht in der Gruppe dialout – korrigiert"
  fi
  if [[ -f "$DB" ]]; then
    if [[ "$mode" == "usb" && -n "$dev" ]]; then
      if [[ -e "$dev" ]]; then
        local grp; grp=$(stat -c %G "$(readlink -f "$dev")")
        id -nG "$SVC_USER" | grep -qw "$grp" || { usermod -a -G "$grp" "$SVC_USER"; warn "Zugriff auf $dev (Gruppe $grp) ergänzt"; }
        ok "USB-Stick $dev erreichbar (Gruppe $grp)"
      else
        warn "USB-Stick $dev ist gerade nicht angeschlossen"
      fi
    fi
  fi
  [[ -f "$APP_DIR/.source" ]] && { local src; src=$(cat "$APP_DIR/.source"); [[ -d "$src" ]] && chown -R root:root "$src" 2>/dev/null; } || true
  if (( n + m > 0 )); then ok "Berechtigungen geprüft – $((n + m)) Einträge korrigiert"; else ok "Berechtigungen geprüft – alles in Ordnung"; fi
}

# ---------------------------------------------------------------- Zello-Schlüssel: Datei -> SQLite
# Sucht Zello-Schlüssel (zello*.key, zello*.pem) im Programm-, Daten- und Quellordner, verschiebt sie
# zuerst an einen sicheren Ort (/root/.n8crosslink-import, nur root), übernimmt sie in die Datenbank,
# prüft per Fingerabdruck gegen und löscht die Datei danach sicher (shred). Die Bridge liest den
# Schlüssel ausschließlich aus der Datenbank (und er ist Teil des verschlüsselten Backups).
import_zello_keys() {
  local SAFE=/root/.n8crosslink-import f src dirs=("$APP_DIR" "$DATA_DIR")
  [[ -x "$APP_DIR/venv/bin/python" && -f "$DB" ]] || return 0
  src=$(cat "$APP_DIR/.source" 2>/dev/null || true); [[ -n "$src" && -d "$src" ]] && dirs+=("$src")
  local found=()
  for d in "${dirs[@]}"; do
    while IFS= read -r f; do found+=("$f"); done < <(find "$d" -maxdepth 2 -path "$APP_DIR/venv" -prune -o -type f \
      \( -iname 'zello*.key' -o -iname 'zello*.pem' \) -print 2>/dev/null)
  done
  (( ${#found[@]} )) || return 0
  install -d -m 700 -o root -g root "$SAFE"
  for f in "${found[@]}"; do
    grep -q "PRIVATE KEY" "$f" 2>/dev/null || continue
    local tmp="$SAFE/$(basename "$f").$$"
    mv "$f" "$tmp"; chmod 600 "$tmp"
    info "Schlüsseldatei $f gefunden – sicher verschoben, übernehme in die Datenbank …"
    # der Dienstbenutzer darf $SAFE nicht lesen -> Inhalt über eine kurzlebige Kopie im Datenordner
    local hand="$DATA_DIR/.import.key"; install -m 600 -o "$SVC_USER" -g "$SVC_USER" "$tmp" "$hand"
    if out=$(cli import-zello-key "$hand" 2>&1); then
      shred -u "$hand" 2>/dev/null || rm -f "$hand"
      shred -u "$tmp" 2>/dev/null || rm -f "$tmp"
      ok "Zello-Schlüssel in SQLite übernommen (${out#OK }) – Datei sicher gelöscht"
    else
      shred -u "$hand" 2>/dev/null || rm -f "$hand"
      warn "Import fehlgeschlagen ($out) – Datei bleibt geschützt in $tmp"
    fi
  done
  rmdir "$SAFE" 2>/dev/null || true
}

# ---------------------------------------------------------------- Software-Vocoder DroidStar
# Quelle: DroidStar (Doug McLain, https://github.com/nostar/DroidStar), Verzeichnis mbe/ –
# AMBE+2 half-rate (DMR) Encoder und Decoder, C-API ambe2.h, GPL-3.0-or-later.
# Nicht im Repository enthalten: wird bei der Installation aus einem festen, geprüften Stand der
# DroidStar-Quellen gebaut (nur die Codec-Dateien, ohne Qt) und läuft per ctypes direkt in der Bridge.
DS_REPO="https://github.com/nostar/DroidStar.git"
DS_REF="${N8X_DROIDSTAR_REF:-fc8e340a61d65f9719d1c4a0c28fdf5cc5d2b444}"
DS_SRC="/usr/local/src/n8crosslink-droidstar"
VOC_DIR="$APP_DIR/lib"
VOC_LIB="$VOC_DIR/libambe2.so"

voc_probe() { cli vocoder-test --mode droidstar 2>&1 | tail -1; }
build_vocoder() {   # build_vocoder [force]
  local force="${1:-}" tmp out
  if [[ -z "$force" && -f "$VOC_LIB" && "$(cat "$VOC_DIR/libambe2.ref" 2>/dev/null)" == "$DS_REF" ]]; then
    out=$(voc_probe); [[ "$out" == OK* ]] && { ok "DroidStar-Vocoder aktuell (${DS_REF:0:12}) – $out"; return 0; }
  fi
  info "Baue DroidStar-Vocoder (Stand ${DS_REF:0:12}) …"
  command -v g++ >/dev/null && command -v git >/dev/null || apt-get install -y -qq g++ git >/dev/null \
    || { warn "Compiler (g++) nicht installierbar"; return 1; }
  if [[ ! -d "$DS_SRC/.git" ]]; then
    rm -rf "$DS_SRC"; install -d -m 755 "$DS_SRC"; git -C "$DS_SRC" init -q; git -C "$DS_SRC" remote add origin "$DS_REPO"
  fi
  git -C "$DS_SRC" fetch -q --depth 1 origin "$DS_REF" && git -C "$DS_SRC" checkout -q --force FETCH_HEAD \
    || { warn "DroidStar-Quellen nicht ladbar (GitHub erreichbar?)"; return 1; }
  chown -R root:root "$DS_SRC"
  tmp=$(mktemp -d); echo "/* N8 Crosslink: Build ohne Qt */" > "$tmp/QtGlobal"
  if ! g++ -O2 -fPIC -shared -std=c++17 -w -I"$tmp" -I"$DS_SRC/mbe" "$DS_SRC"/mbe/*.cc -o "$tmp/libambe2.so" 2>"$tmp/build.log"; then
    warn "Bauen fehlgeschlagen:"; tail -5 "$tmp/build.log"; rm -rf "$tmp"; return 1
  fi
  install -d -m 755 -o root -g root "$VOC_DIR"
  install -m 644 -o root -g root "$tmp/libambe2.so" "$VOC_LIB"
  echo "$DS_REF" > "$VOC_DIR/libambe2.ref"; chmod 644 "$VOC_DIR/libambe2.ref"
  rm -rf "$tmp"
  out=$(voc_probe)
  if [[ "$out" == OK* ]]; then ok "DroidStar-Vocoder gebaut und getestet – $out"; return 0; fi
  warn "DroidStar-Vocoder gebaut, Test fehlgeschlagen: $out"; return 1
}

# md380-emu wird nicht mehr gebraucht (ersetzt durch den DroidStar-Vocoder) und wird restlos entfernt:
# Dienst, Paket, /opt/md380-emu, sudo-Freigabe. Die DVSwitch-Paketquelle bleibt nur, wenn noch andere
# DVSwitch-Pakete (Analog_Bridge, MMDVM_Bridge …) installiert sind.
remove_md380() {
  local did=0 f others
  if systemctl list-unit-files 2>/dev/null | grep -q '^md380-emu.service'; then
    systemctl disable --now md380-emu >/dev/null 2>&1 || true; did=1
  fi
  if [[ -f /etc/systemd/system/md380-emu.service ]]; then rm -f /etc/systemd/system/md380-emu.service; did=1; fi
  if dpkg -s md380-emu >/dev/null 2>&1; then
    apt-get purge -y -qq md380-emu >/dev/null 2>&1 && did=1 || warn "apt purge md380-emu fehlgeschlagen"
  fi
  for f in /opt/md380-emu /usr/local/bin/md380-emu; do [[ -e "$f" ]] && { rm -rf "$f"; did=1; }; done
  systemctl daemon-reload 2>/dev/null || true
  others=$(dpkg-query -W -f='${Package}\n' 2>/dev/null | grep -Ei '^(analog-bridge|mmdvm-bridge|dvswitch|ambeserver|hblink|dmrgateway|ysfgateway|p25gateway|nxdngateway)' || true)
  for f in /etc/apt/sources.list.d/*dvswitch* /etc/apt/sources.list.d/*DVSwitch*; do
    [[ -e "$f" ]] || continue
    if [[ -z "$others" ]]; then rm -f "$f"; did=1; info "DVSwitch-Paketquelle entfernt ($f)"
    else info "DVSwitch-Paketquelle bleibt – noch genutzt von: $(echo $others)"; fi
  done
  (( did )) && ok "md380-emu deinstalliert (Dienst, Paket, Programmdateien)"
  if dpkg -s qemu-user-static >/dev/null 2>&1; then
    info "qemu-user-static bleibt installiert (wurde ggf. nur für md380-emu gebraucht – entfernen: apt purge qemu-user-static binfmt-support)"
  fi
  return 0
}

# ---------------------------------------------------------------- sudo fürs Webinterface
# Nur exakt aufgezählte Befehle, geprüft mit visudo. Die Bridge selbst bleibt ohne root-Rechte.
setup_sudo() {
  local SC; SC=$(type -P systemctl || echo /usr/bin/systemctl)
  local allow_reboot="${1:-true}" units=() u acts line json="" sep=""
  local F=/etc/sudoers.d/n8crosslink TMP; TMP=$(mktemp)
  command -v sudo >/dev/null || apt-get install -y -qq sudo >/dev/null
  add_unit() {  # add_unit unit "label" "aktionen…"
    local unit="$1" label="$2"; shift 2
    for a in "$@"; do
      case "$a" in start|restart) echo "$SVC_USER ALL=(root) NOPASSWD: $SC --no-block $a $unit" >> "$TMP" ;;
                   *)             echo "$SVC_USER ALL=(root) NOPASSWD: $SC $a $unit" >> "$TMP" ;; esac
    done
    local al; al=$(printf '"%s",' "$@"); al="[${al%,}]"
    json+="${sep}{\"unit\": \"$unit\", \"label\": \"$label\", \"actions\": $al}"; sep=", "
  }
  echo "# N8 Crosslink – vom Installer erzeugt, nicht von Hand ändern (wird bei jedem Update neu geschrieben)" > "$TMP"
  echo "Defaults:$SVC_USER !requiretty" >> "$TMP"
  add_unit n8crosslink.service "N8 Crosslink" restart
  add_unit n8crosslink-update.service "Update-Dienst" start
  for u in $(systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Ei '^(svxlink|mmdvm_bridge|analog_bridge|ambeserver|.*zello.*)\.service$' | grep -v n8crosslink); do
    add_unit "$u" "${u%.service} (alt)" start stop restart enable disable
  done
  [[ "$allow_reboot" == "true" ]] && echo "$SVC_USER ALL=(root) NOPASSWD: $SC reboot" >> "$TMP"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/install.sh --fix-perms" >> "$TMP"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/install.sh --build-vocoder" >> "$TMP"
  if visudo -cf "$TMP" >/dev/null 2>&1; then
    install -o root -g root -m 0440 "$TMP" "$F"
    printf '{"sudo": true, "systemctl": "%s", "reboot": %s, "fix_perms": true, "build_vocoder": true, "units": [%s]}\n' "$SC" "$allow_reboot" "$json" > "$DATA_DIR/system.json"
    chown "$SVC_USER:$SVC_USER" "$DATA_DIR/system.json"; chmod 640 "$DATA_DIR/system.json"
    ok "sudo fürs Webinterface eingerichtet ($(grep -c NOPASSWD "$F") freigegebene Befehle, mit visudo geprüft)"
  else
    warn "sudoers-Datei ungültig – nicht übernommen"; visudo -cf "$TMP" || true
  fi
  rm -f "$TMP"
}

cli() { (cd "$APP_DIR" && runuser -u "$SVC_USER" -- env N8X_DB="$DB" "$APP_DIR/venv/bin/python" -m n8crosslink.cli "$@"); }
setcfg() { cli set "$1" "$2" "$3" >/dev/null; }

if [[ "${1:-}" == "--fix-perms" ]]; then
  [[ $EUID -eq 0 ]] || fail "Bitte als root starten"
  echo "Berechtigungen prüfen (N8 Crosslink) …"; import_zello_keys; fix_perms; exit 0
fi
if [[ "${1:-}" == "--diagnose" ]]; then
  [[ $EUID -eq 0 ]] || fail "Bitte als root starten"
  {
  . /etc/os-release 2>/dev/null
  echo "== System:  $PRETTY_NAME ($(dpkg --print-architecture)), $(python3 --version 2>&1)"
  echo "== Version: $(grep -oP '__version__ = "\K[^"]+' "$APP_DIR/n8crosslink/__init__.py" 2>/dev/null)"
  PORT=$(cli show general 2>/dev/null | grep -oP '"web_port": \K[0-9]+'); echo "== Web-Port: ${PORT:-?}"
  for u in n8crosslink n8crosslink-update.path; do
    echo "== Dienst $u: $(systemctl is-active $u 2>&1) / $(systemctl is-enabled $u 2>&1)"
  done
  echo "== Weboberfläche antwortet: $(curl -fsS -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT:-0}/api/info" 2>&1 || echo 'nein')"
  echo "== systemctl status n8crosslink:"; systemctl status n8crosslink --no-pager -l 2>/dev/null | head -12
  echo "== Dienst-Rechte: $(systemctl show n8crosslink -p User -p AmbientCapabilities --value 2>/dev/null | tr '\n' ' ')"
  echo "== Lauscht auf Port ${PORT:-?}:"; ss -ltnp "( sport = :${PORT:-0} )" 2>/dev/null | tail -n +2 || true
  if [[ -n "$PORT" ]] && ! ss -ltn "( sport = :$PORT )" | grep -q LISTEN; then
    echo "== Bind-Test als Dienstbenutzer mit Dienst-Rechten:"
    systemd-run --quiet --wait --pipe -p User="$SVC_USER" -p AmbientCapabilities=CAP_NET_BIND_SERVICE \
      "$APP_DIR/venv/bin/python" -c "import socket;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('0.0.0.0',$PORT));print('Port $PORT: OK')" 2>&1 || true
  fi
  echo "== DroidStar-Vocoder: $([[ -f "$VOC_LIB" ]] && echo "$VOC_LIB (Stand $(cut -c1-12 "$VOC_DIR/libambe2.ref" 2>/dev/null))" || echo 'nicht gebaut'); md380-emu: $(dpkg -s md380-emu >/dev/null 2>&1 || [[ -d /opt/md380-emu ]] && echo 'noch vorhanden – wird beim Update entfernt' || echo 'entfernt')"
  echo "== Vocoder-Test: $( (cd "$APP_DIR" && runuser -u "$SVC_USER" -- env N8X_DB="$DB" "$APP_DIR/venv/bin/python" -m n8crosslink.cli vocoder-test) 2>&1 | tail -1)"
  echo "== Zello-Schlüssel: $(cli zello-key-info 2>&1 | tail -1); Schlüsseldateien: $(find "$APP_DIR" -maxdepth 2 -iname 'zello*.key' 2>/dev/null | wc -l)"
  echo "== sudo-Freigaben: $(grep -c NOPASSWD /etc/sudoers.d/n8crosslink 2>/dev/null || echo 0)"
  echo "== Log n8crosslink (letzte 40):"; journalctl -u n8crosslink -n 40 --no-pager -o cat 2>/dev/null
  } 2>&1 | tee /tmp/n8crosslink-diagnose.txt
  echo; echo "(gespeichert in /tmp/n8crosslink-diagnose.txt – enthält keine Passwörter)"; exit 0
fi
if [[ "${1:-}" == "--build-vocoder" || "${1:-}" == "--install-md380" ]]; then
  [[ $EUID -eq 0 ]] || fail "Bitte als root starten"
  echo "DroidStar-Vocoder bauen/prüfen …"
  build_vocoder force || exit 1
  setcfg vocoder vocoder_mode droidstar; ok "Vocoder auf DroidStar gestellt"
  remove_md380
  REBOOT=true; grep -q '"reboot": false' "$DATA_DIR/system.json" 2>/dev/null && REBOOT=false
  setup_sudo "$REBOOT"; exit 0
fi

clear || true
cat <<BANNER
${C}${B}
     _   _  ___      ____                    _ _       _
    | \\ | |( _ )    / ___|_ __ ___  ___ ___| (_)_ __ | | __
    |  \\| |/ _ \\   | |   | '__/ _ \\/ __/ __| | | '_ \\| |/ /
    | |\\  | (_) |  | |___| | | (_) \\__ \\__ \\ | | | | |   <
    |_| \\_|\\___/    \\____|_|  \\___/|___/___/_|_|_| |_|_|\\_\\
${R}
    ${B}FRN · DMR · Zello Crosslink${R}  ${D}– Die N8schicht${R}
    ${D}Ersetzt SvxLink (FRN↔DMR) und die alte Zello-Bridge – reines Python.${R}
BANNER

[[ $EUID -eq 0 ]] || fail "Bitte als root starten:  sudo ./install.sh"
[[ -f "$SRC_DIR/n8crosslink/__init__.py" ]] || fail "Installer bitte aus dem geklonten Repository starten."
APP_VERSION=$(grep -oP '__version__ = "\K[^"]+' "$SRC_DIR/n8crosslink/__init__.py")
. /etc/os-release 2>/dev/null || true
ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
info "System: ${PRETTY_NAME:-unbekannt} (${ARCH}) · N8 Crosslink ${APP_VERSION}"

MODE="neu"
if [[ -f "$DB" && "${N8X_UPDATE:-0}" == "1" ]]; then
  MODE="update"
elif [[ -f "$DB" ]]; then
  echo
  warn "Es gibt bereits eine Installation in $APP_DIR."
  ask_choice M "Was soll passieren?" 1 "Aktualisieren – alle Einstellungen behalten" "Neu einrichten – Einstellungen erneut abfragen (Last Heard bleibt)"
  [[ "$M" == "2" ]] && MODE="neu" || MODE="update"
fi

# ---------------------------------------------------------------- 1 Pakete
step 1 "Systempakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip libgsm1 libopus0 sqlite3 curl git ca-certificates iproute2 sudo espeak-ng >/dev/null
ok "python3, libgsm (FRN), libopus (Zello), sqlite3, espeak-ng (Sprachansage)"
# Update-Modus: vor dem Kopieren auch alte, falsch gesetzte Rechte erkennen
[[ "$MODE" == "update" ]] && fix_perms

# ---------------------------------------------------------------- 2 Benutzer + Dateien
step 2 "Dienstbenutzer und Programmdateien"
if ! id "$SVC_USER" &>/dev/null; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SVC_USER"
  ok "Benutzer $SVC_USER angelegt"
fi
usermod -a -G dialout "$SVC_USER" 2>/dev/null || true   # Zugriff auf USB-AMBE-Stick
mkdir -p "$APP_DIR" "$DATA_DIR"
cp -r "$SRC_DIR/n8crosslink" "$SRC_DIR/requirements.txt" "$APP_DIR/"
cp "$SRC_DIR/install.sh" "$SRC_DIR/update.sh" "$SRC_DIR/uninstall.sh" "$APP_DIR/" 2>/dev/null || true
[[ -d "$SRC_DIR/.git" ]] && echo "$SRC_DIR" > "$APP_DIR/.source"
rm -rf "$APP_DIR/n8crosslink/__pycache__"
ok "Dateien nach $APP_DIR kopiert"
fix_perms

# ---------------------------------------------------------------- 3 Python-Umgebung
step 3 "Python-Umgebung (venv)"
[[ -d "$APP_DIR/venv" ]] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/python" -m compileall -q "$APP_DIR/n8crosslink" >/dev/null || true
fix_perms
runuser -u "$SVC_USER" -- "$APP_DIR/venv/bin/python" -c "import sys; sys.path.insert(0, '$APP_DIR'); from n8crosslink.audio import gsm, opus; gsm.GsmEncoder(); opus.OpusEncoder()" \
  || fail "libgsm/libopus konnten nicht geladen werden"
ok "Abhängigkeiten installiert, GSM- und Opus-Codec geprüft"

if [[ "$MODE" == "neu" ]]; then
  echo
  ask BK_FILE "Verschlüsseltes Backup (.n8xbak) einspielen? Pfad angeben, leer = nein" ""
  if [[ -n "$BK_FILE" ]]; then
    if [[ -f "$BK_FILE" ]]; then
      cp "$BK_FILE" "$DATA_DIR/restore.n8xbak"; chown "$SVC_USER" "$DATA_DIR/restore.n8xbak"
      for try in 1 2 3; do
        ask_secret BK_PW "Superadmin-Passwort, mit dem das Backup erstellt wurde"
        if printf '%s\n' "$BK_PW" | cli restore "$DATA_DIR/restore.n8xbak"; then MODE="restored"; break; fi
      done
      rm -f "$DATA_DIR/restore.n8xbak"; unset BK_PW
      [[ "$MODE" == "restored" ]] && ok "Backup eingespielt – alle Einstellungen, Benutzer und Daten übernommen" || warn "Backup nicht eingespielt – weiter mit Neueinrichtung"
    else
      warn "Datei nicht gefunden – weiter mit Neueinrichtung"
    fi
  fi
fi

if [[ "$MODE" == "neu" ]]; then
# ---------------------------------------------------------------- 4 Allgemein + Superadmin
step 4 "Dashboard und Superadmin"
FREE=8080; while ss -ltn "( sport = :$FREE )" 2>/dev/null | grep -q LISTEN; do FREE=$((FREE+1)); done
[[ $FREE -ne 8080 ]] && warn "Port 8080 ist belegt (z. B. HBlink4-Dashboard) – Vorschlag: $FREE"
ask WEB_PORT "Web-Port für das Dashboard" "$FREE"
if (( WEB_PORT < 1024 )); then
  if ss -ltn "( sport = :$WEB_PORT )" 2>/dev/null | grep -q LISTEN; then
    warn "Port $WEB_PORT ist bereits belegt (z. B. nginx/Apache) – nehme $FREE"; WEB_PORT=$FREE
  else
    info "Port $WEB_PORT < 1024: der Dienst erhält dafür nur das Recht CAP_NET_BIND_SERVICE (kein root)"
  fi
fi
ask TITLE "Titel im Dashboard" "N8 Crosslink"
ask SERVER_NAME "Domain / Servername" "$(hostname -f 2>/dev/null || hostname)"
setcfg general web_port "$WEB_PORT"; setcfg general title "$TITLE"; setcfg general server_name "$SERVER_NAME"
echo
info "${B}Adminportal${R}: Standard-Login ist ${B}n8schicht / n8schicht${R} (Superadmin)."
if ask_yn "Jetzt ein eigenes Passwort für n8schicht setzen? (sonst später im Adminportal)" n; then
  while true; do
    ask_secret P1 "Neues Passwort (min. 8 Zeichen)"; ask_secret P2 "Passwort wiederholen"
    [[ "$P1" == "$P2" && ${#P1} -ge 8 ]] && break; warn "Passwörter ungleich oder zu kurz."
  done
  printf '%s\n' "$P1" | cli admin n8schicht >/dev/null && ok "Passwort für n8schicht gesetzt"
  unset P1 P2
else
  cli users >/dev/null; ok "Standard-Login n8schicht / n8schicht aktiv – das Dashboard erinnert ans Ändern"
fi

# ---------------------------------------------------------------- 5 FRN
step 5 "FRN – FreeRadioNetwork"
if ask_yn "FRN anbinden?" j; then
  setcfg frn enabled true
  ask V "FRN-Server" "frn.auf-der-nachtschicht.de"; setcfg frn server "$V"
  ask V "Port" "10024"; setcfg frn port "$V"
  ask V "Backup-Server (leer = keiner)" ""; setcfg frn backup_server "$V"
  ask V "E-Mail des FRN-Kontos" ""; setcfg frn email "$V"
  ask_secret V "FRN-Passwort (dynamisches Passwort)"; setcfg frn password "$V"
  ask V "Rufzeichen der Bridge" "N8XLINK"; setcfg frn callsign "$V"
  ask V "Name / Bezeichnung" "Crosslink"; setcfg frn op_name "$V"
  ask V "Raum (Net)" "Test"; setcfg frn net "$V"
  ask V "Ort – Ortsteil / Locator" "Minden - JO42"; setcfg frn city "$V"
  ask V "Land" "Germany"; setcfg frn country "$V"
  ok "FRN konfiguriert (Client-Typ 0 = Crosslink)"
else setcfg frn enabled false; info "FRN bleibt aus."; fi

# ---------------------------------------------------------------- 6 DMR
step 6 "DMR – HBlink4 / FreeDMR (HomeBrew)"
if ask_yn "DMR anbinden?" j; then
  setcfg dmr enabled true
  ask V "DMR-Server" "dmr.die-n8schicht.de"; setcfg dmr host "$V"
  ask V "Port" "62031"; setcfg dmr port "$V"
  ask_secret V "Passwort (Passphrase am Server)"; setcfg dmr password "$V"
  ask V "Peer-/Repeater-ID (am Server erlaubt)" "262000101"; setcfg dmr peer_id "$V"
  ask V "Rufzeichen" "N8XLINK"; setcfg dmr callsign "$V"
  ask V "Quell-ID für Sendungen ins DMR (eigene DMR-ID)" "2620001"; setcfg dmr src_id "$V"
  ask V "Zeitschlitz (1/2)" "2"; setcfg dmr slot "$V"
  ask V "Empfangs-Talkgroup" "262"; setcfg dmr tg_rx "$V"
  ask V "Sende-Talkgroup" "$V"; setcfg dmr tg_tx "$V"
  ask V "Color Code" "1"; setcfg dmr color_code "$V"
  ask V "RPTO-Optionen (z. B. TS2=262, leer = Serverkonfig)" ""; setcfg dmr options "$V"
  ok "DMR konfiguriert – Talker Alias (Stationsname) ist aktiv"
else setcfg dmr enabled false; info "DMR bleibt aus."; fi

# ---------------------------------------------------------------- 7 Zello
step 7 "Zello – Channel API"
if ask_yn "Zello anbinden?" j; then
  setcfg zello enabled true
  ask_choice Z "Zello-Variante" 1 "Zello (Friends & Family) – mit Entwickler-Token" "Zello (Friends & Family) – Issuer + Private Key" "Zello Work"
  case "$Z" in
    3) ask V "Zello-Work-Netzwerk (Name)" ""; setcfg zello server "wss://zellowork.io/ws/$V"; setcfg zello auth_mode none ;;
    2) setcfg zello server "wss://zello.io/ws"; setcfg zello auth_mode key
       ask V "Issuer" ""; setcfg zello issuer "$V"
       ask V "Pfad zur Private-Key-Datei (PEM)" ""
       if [[ -f "$V" ]]; then
         install -d -m 700 /root/.n8crosslink-import; mv "$V" /root/.n8crosslink-import/zello.key
         install -m 600 -o "$SVC_USER" -g "$SVC_USER" /root/.n8crosslink-import/zello.key "$DATA_DIR/.import.key"
         if out=$(cli import-zello-key "$DATA_DIR/.import.key" 2>&1); then
           ok "Private Key in SQLite übernommen (${out#OK })"
           shred -u /root/.n8crosslink-import/zello.key; ok "Schlüsseldatei sicher gelöscht – gelesen wird nur noch aus der Datenbank"
         else warn "$out – Datei liegt geschützt in /root/.n8crosslink-import/"; fi
         shred -u "$DATA_DIR/.import.key" 2>/dev/null || true
       else warn "Datei nicht gefunden – im Adminportal nachtragen."; fi ;;
    *) setcfg zello server "wss://zello.io/ws"; setcfg zello auth_mode token
       ask_secret V "Entwickler-Token (developers.zello.com)" optional; [[ -n "$V" ]] && setcfg zello auth_token "$V" ;;
  esac
  ask V "Kanal" ""; setcfg zello channel "$V"
  ask V "Zello-Benutzername der Bridge" ""; setcfg zello username "$V"
  ask_secret V "Zello-Passwort"; setcfg zello password "$V"
  ok "Zello konfiguriert – Sprechername wird als Textnachricht mitgeschickt"
else setcfg zello enabled false; info "Zello bleibt aus."; fi

# ---------------------------------------------------------------- 8 Vocoder
step 8 "Vocoder für DMR (AMBE+2)"
ask_choice VOC "Welcher Vocoder?" 1 \
  "DroidStar (Software, ohne Hardware – empfohlen)" \
  "USB-Stick (ThumbDV / DVstick 30 / DV3000)" \
  "AMBEserver im Netz" \
  "später im Adminportal festlegen"
case "$VOC" in
  1) setcfg vocoder vocoder_mode droidstar
     build_vocoder || warn "Vocoder kann später unter Admin → 🎛️ Vocoder → „DroidStar-Vocoder bauen“ nachgeholt werden" ;;
  2) setcfg vocoder vocoder_mode usb
     DEV=$(ls /dev/serial/by-id/* 2>/dev/null | head -1 || true); [[ -z "$DEV" ]] && DEV=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1 || true)
     ask V "Gerät" "${DEV:-/dev/ttyUSB0}"; setcfg vocoder usb_device "$V"
     ask V "Baudrate (ThumbDV/DVstick 30: 460800, DV3000-Hat: 230400)" "460800"; setcfg vocoder usb_baud "$V"
     ok "USB-Stick eingetragen (Benutzer $SVC_USER ist in der Gruppe dialout)" ;;
  3) setcfg vocoder vocoder_mode ambeserver
     ask V "AMBEserver-Adresse" "127.0.0.1"; setcfg vocoder ambeserver_host "$V"
     ask V "AMBEserver-Port" "2460"; setcfg vocoder ambeserver_port "$V" ;;
  *) info "Vocoder wird später im Adminportal gewählt (Admin → 🎛️ Vocoder)." ;;
esac
else
  step 4 "Einstellungen bleiben erhalten"; ok "$([[ "$MODE" == restored ]] && echo "aus dem Backup übernommen" || echo "Update-Modus")"
  # 1.4.0: md380-emu -> DroidStar. Alte Einstellung umstellen, Vocoder bauen (nur wenn nötig), md380-emu entfernen
  if sqlite3 "$DB" "SELECT value FROM settings WHERE section='vocoder' AND key='vocoder_mode'" 2>/dev/null | grep -q md380; then
    setcfg vocoder vocoder_mode droidstar; ok "Vocoder von md380-emu auf DroidStar umgestellt"
  fi
  if cli show vocoder | grep -q '"vocoder_mode": "droidstar"'; then build_vocoder || true; fi
  remove_md380
  step 5 "–"; step 6 "–"; step 7 "–"; step 8 "–"
fi

# ---------------------------------------------------------------- 9 Dienst
step 9 "Berechtigungen, Dienst und alte Bridges"
if [[ ! -d /run/systemd/system ]]; then
  import_zello_keys
  fix_perms
  warn "Kein systemd gefunden (Container?). Start von Hand:"
  echo "       runuser -u $SVC_USER -- env N8X_DB=$DB $APP_DIR/venv/bin/python -m n8crosslink"
  exit 0
fi
OLD=$(systemctl list-units --type=service --all --no-legend 2>/dev/null | awk '{print $1}' | grep -Ei 'svxlink|mmdvm_bridge|analog_bridge|zello' | grep -v n8crosslink || true)
if [[ -n "$OLD" ]]; then
  warn "Gefundene alte Dienste (SvxLink-FRN / DMR-Bridge / Zello-Bridge):"
  echo "$OLD" | sed 's/^/       • /'
  if ask_yn "Diese Dienste stoppen und deaktivieren? (später mit systemctl enable --now wieder einschaltbar)" n; then
    mkdir -p /var/lib/n8crosslink
    for s in $OLD; do
      systemctl disable --now "$s" >/dev/null 2>&1 && ok "$s gestoppt und deaktiviert" && echo "$s" >> /var/lib/n8crosslink/disabled-services
    done
    sort -u -o /var/lib/n8crosslink/disabled-services /var/lib/n8crosslink/disabled-services
  else info "Alte Dienste bleiben aktiv – Achtung: nicht beide Bridges gleichzeitig im selben Raum/derselben TG betreiben."; fi
fi
cp "$SRC_DIR/systemd/n8crosslink.service" "$SRC_DIR/systemd/n8crosslink-update.path" \
   "$SRC_DIR/systemd/n8crosslink-update.service" /etc/systemd/system/
import_zello_keys
REBOOT=true
if [[ -f "$DATA_DIR/system.json" ]]; then grep -q '"reboot": false' "$DATA_DIR/system.json" && REBOOT=false
elif ! ask_yn "Server-Neustart (Reboot) über das Webinterface erlauben?" j; then REBOOT=false; fi
systemctl daemon-reload
setup_sudo "$REBOOT"
fix_perms
systemctl enable n8crosslink >/dev/null 2>&1
systemctl enable --now n8crosslink-update.path >/dev/null 2>&1 && ok "„Update jetzt“ aus dem Adminportal eingerichtet"
systemctl restart n8crosslink
PORT=$(cli show general | grep -oP '"web_port": \K[0-9]+' || echo 8080)
# Echte Prüfung: antwortet die Weboberfläche (nicht nur „Port offen“)?
web_ok() { curl -fsS -m 3 -o /dev/null "http://127.0.0.1:$PORT/api/info" 2>/dev/null \
           || { ss -ltn "( sport = :$PORT )" 2>/dev/null | grep -q LISTEN && ! ss -ltn "( sport = :$PORT )" | grep -qE '(0\.0\.0\.0|\*|127\.0\.0\.1|\[::\]):'"$PORT"; }; }
WEB_OK=0
for i in $(seq 1 45); do web_ok && { WEB_OK=1; break; }; sleep 1; done
if (( WEB_OK )); then
  ok "Dienst n8crosslink läuft – Weboberfläche antwortet auf Port $PORT"
else
  warn "Weboberfläche antwortet nicht auf Port $PORT – Dienststatus und Log:"
  systemctl status n8crosslink --no-pager -l 2>/dev/null | head -15 || true
  journalctl -u n8crosslink -n 40 --no-pager -o cat
  info "Ausführliche Prüfung: sudo $APP_DIR/install.sh --diagnose"
  # Beim Update meldet der Installer das an update.sh – das stellt dann die vorige Version wieder her
  [[ "${N8X_UPDATE:-0}" == "1" ]] && exit 3
fi
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [[ "$MODE" == "neu" ]]; then
  echo
  if ask_yn "Optional: nginx als HTTPS-Reverse-Proxy mit Let's Encrypt für ${SERVER_NAME:-die Domain} einrichten?" n; then
    apt-get install -y -qq nginx certbot python3-certbot-nginx >/dev/null
    sed -e "s/__SERVER_NAME__/${SERVER_NAME}/g" -e "s/__PORT__/${PORT}/g" "$SRC_DIR/systemd/nginx-n8crosslink.conf" > /etc/nginx/sites-available/n8crosslink
    ln -sf /etc/nginx/sites-available/n8crosslink /etc/nginx/sites-enabled/n8crosslink
    nginx -t >/dev/null 2>&1 && systemctl reload nginx
    ask LE_MAIL "E-Mail für Let's Encrypt" ""
    certbot --nginx -d "$SERVER_NAME" --non-interactive --agree-tos -m "$LE_MAIL" --redirect >/dev/null 2>&1 \
      && ok "HTTPS aktiv: https://${SERVER_NAME}" || warn "Zertifikat fehlgeschlagen – DNS/Port 80 prüfen, dann: certbot --nginx -d ${SERVER_NAME}"
  fi
fi

echo
echo "${G}${B}  ✔ N8 Crosslink ${APP_VERSION} ist installiert.${R}"
echo
echo "    Dashboard:   ${B}http://${IP:-<ip>}:${PORT}${R}"
echo "    Admin:       oben rechts 🔐 Login – Standard: n8schicht / n8schicht"
echo "    Watchdog:    Netze, Vocoder und Dienst werden automatisch überwacht"
echo "    Updates:     stündlich geprüft, Installation per Knopf im Adminportal"
echo "    Logs:        journalctl -u n8crosslink -f"
echo "    Update:      sudo $APP_DIR/update.sh"
echo "    Doku:        https://github.com/dhartmann1979/N8Crosslink"
echo
