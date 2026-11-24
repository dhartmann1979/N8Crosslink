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
  find "$APP_DIR" -path "$DATA_DIR" -prune -o -path "$APP_DIR/venv/bin" -prune -o -type f -exec chmod 644 {} +
  [[ -d "$APP_DIR/venv/bin" ]] && chmod -R go-w "$APP_DIR/venv/bin" && find "$APP_DIR/venv/bin" -type f -exec chmod 755 {} + 2>/dev/null || true
  for f in install.sh update.sh uninstall.sh; do [[ -f "$APP_DIR/$f" ]] && chmod 755 "$APP_DIR/$f"; done
  mkdir -p "$DATA_DIR"
  local m; m=$(find "$DATA_DIR" \( ! -user "$SVC_USER" ! -name update.log \) -print 2>/dev/null | wc -l)
  chown -R "$SVC_USER:$SVC_USER" "$DATA_DIR"
  chmod 750 "$DATA_DIR"
  find "$DATA_DIR" -type f -name '*.db*' -exec chmod 640 {} +
  [[ -f "$DATA_DIR/update.log" ]] && chmod 644 "$DATA_DIR/update.log"
  for f in n8crosslink.service n8crosslink-update.path n8crosslink-update.service md380-emu.service; do
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

# ---------------------------------------------------------------- Software-Vocoder md380-emu
# Quelle: DVSwitch-Paketquelle (http://dvswitch.org/bookworm – Debian 12/13, Ubuntu 22.04/24.04,
# amd64/arm64). Auf x86 läuft md380-emu (ARM-Code) über qemu-user-static.
# Danach echter Test (Encode/Decode über UDP 2470); passt der Paket-Dienst nicht, werden
# Startvarianten durchprobiert.
md380_bin() {
  local p
  for p in "$(type -P md380-emu 2>/dev/null)" /opt/md380-emu/md380-emu /usr/local/bin/md380-emu /usr/bin/md380-emu; do
    [[ -n "$p" && -f "$p" ]] && { echo "$p"; return 0; }
  done
  return 1
}
md380_probe() {
  local i
  for i in 1 2 3 4 5 6; do
    sleep 2
    (cd "$APP_DIR" && runuser -u "$SVC_USER" -- env N8X_DB="$DB" "$APP_DIR/venv/bin/python" -m n8crosslink.cli \
       vocoder-test --mode md380 --host 127.0.0.1 --port 2470) 2>/dev/null | grep -q '^OK' && return 0
  done
  return 1
}
install_md380() {
  local BIN REPO
  . /etc/os-release 2>/dev/null || true
  BIN=$(md380_bin || true)
  if [[ -z "$BIN" ]]; then
    case "${ID:-}:${VERSION_CODENAME:-}" in
      *:bullseye) REPO=bullseye ;;
      *:buster)   REPO=buster ;;
      *)          REPO=bookworm ;;   # Debian 12/13, Raspberry Pi OS, Ubuntu 22.04/24.04
    esac
    info "Richte DVSwitch-Paketquelle ein (dvswitch.org/$REPO) …"
    if curl -fsSL "http://dvswitch.org/$REPO" -o /tmp/dvswitch-repo; then
      DEBIAN_FRONTEND=noninteractive bash /tmp/dvswitch-repo </dev/null >/tmp/dvswitch-repo.log 2>&1 || warn "DVSwitch-Skript meldet Fehler (siehe /tmp/dvswitch-repo.log)"
      apt-get update -qq || true
      apt-get install -y -qq md380-emu >/dev/null 2>&1 || warn "apt install md380-emu fehlgeschlagen"
    else
      warn "dvswitch.org nicht erreichbar"
    fi
    BIN=$(md380_bin || true)
  fi
  if [[ -z "$BIN" ]]; then
    warn "md380-emu konnte nicht installiert werden – siehe docs/VOCODER.md (manuell installieren oder USB-Stick nutzen)"
    return 1
  fi
  chmod +x "$BIN"
  ok "md380-emu: $BIN"
  case "$(dpkg --print-architecture 2>/dev/null || uname -m)" in
    arm*|aarch64) : ;;
    *) if ! command -v qemu-arm-static >/dev/null; then
         info "x86: installiere qemu-user-static für den ARM-Emulator …"
         apt-get install -y -qq qemu-user-static binfmt-support >/dev/null 2>&1 || warn "qemu-user-static nicht installierbar"
       fi ;;
  esac
  [[ -d /run/systemd/system ]] || { warn "kein systemd – md380-emu von Hand starten: $BIN -S 2470"; return 0; }
  systemctl daemon-reload
  if systemctl list-unit-files 2>/dev/null | grep -q '^md380-emu.service'; then
    systemctl enable md380-emu >/dev/null 2>&1 || true
    systemctl restart md380-emu >/dev/null 2>&1 || true
    if md380_probe; then ok "md380-emu antwortet auf UDP 2470 (Dienst aus dem Paket)"; return 0; fi
    warn "Paket-Dienst antwortet nicht auf 2470 – probiere eigene Startvarianten"
  fi
  local args
  for args in "-S 2470" "2470" "-p 2470"; do
    cat > /etc/systemd/system/md380-emu.service <<UNIT
[Unit]
Description=md380-emu AMBE+2 Software-Vocoder (DVSwitch) für N8 Crosslink
After=network.target

[Service]
Type=simple
WorkingDirectory=$(dirname "$BIN")
ExecStart=$BIN $args
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable md380-emu >/dev/null 2>&1 || true
    systemctl restart md380-emu >/dev/null 2>&1 || true
    if md380_probe; then ok "md380-emu antwortet auf UDP 2470 (ExecStart: $BIN $args)"; return 0; fi
  done
  warn "md380-emu läuft, antwortet aber nicht auf UDP 2470 – journalctl -u md380-emu prüfen"
  return 1
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
  systemctl list-unit-files 2>/dev/null | grep -q '^md380-emu.service' && add_unit md380-emu.service "md380-emu (Vocoder)" start stop restart enable disable
  for u in $(systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Ei '^(svxlink|mmdvm_bridge|analog_bridge|ambeserver|.*zello.*)\.service$' | grep -v n8crosslink); do
    add_unit "$u" "${u%.service} (alt)" start stop restart enable disable
  done
  [[ "$allow_reboot" == "true" ]] && echo "$SVC_USER ALL=(root) NOPASSWD: $SC reboot" >> "$TMP"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/install.sh --fix-perms" >> "$TMP"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/install.sh --install-md380" >> "$TMP"
  if visudo -cf "$TMP" >/dev/null 2>&1; then
    install -o root -g root -m 0440 "$TMP" "$F"
    printf '{"sudo": true, "systemctl": "%s", "reboot": %s, "fix_perms": true, "install_md380": true, "units": [%s]}\n' "$SC" "$allow_reboot" "$json" > "$DATA_DIR/system.json"
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
  echo "Berechtigungen prüfen (N8 Crosslink) …"; fix_perms; exit 0
fi
if [[ "${1:-}" == "--install-md380" ]]; then
  [[ $EUID -eq 0 ]] || fail "Bitte als root starten"
  echo "Software-Vocoder md380-emu installieren/prüfen …"
  install_md380 && { setcfg vocoder vocoder_mode md380; setcfg vocoder md380_port 2470; ok "Vocoder auf md380-emu gestellt"; } || exit 1
  # sudo-Freigaben um md380-emu ergänzen (neuer Dienst)
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
apt-get install -y -qq python3 python3-venv python3-pip libgsm1 libopus0 sqlite3 curl git ca-certificates iproute2 sudo >/dev/null
ok "python3, libgsm (FRN), libopus (Zello), sqlite3"
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
       ask V "Pfad zur Private-Key-Datei (PEM)" ""; [[ -f "$V" ]] && setcfg zello private_key "$(cat "$V")" || warn "Datei nicht gefunden – im Adminportal nachtragen." ;;
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
  "md380-emu (Software, ohne Hardware)" \
  "USB-Stick (ThumbDV / DVstick 30 / DV3000)" \
  "AMBEserver im Netz" \
  "später im Adminportal festlegen"
case "$VOC" in
  1) setcfg vocoder vocoder_mode md380; setcfg vocoder md380_port 2470
     install_md380 || warn "Vocoder kann später unter Admin → 🎛️ Vocoder → „md380-emu installieren“ nachgeholt werden" ;;
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
  # Software-Vocoder bei Update/Wiederherstellung mitprüfen: md380 eingestellt, aber nicht installiert -> nachholen
  if cli show vocoder | grep -q '"vocoder_mode": "md380"' && { [[ "$MODE" == "restored" ]] || ! md380_bin >/dev/null; }; then
    install_md380 || true
  fi
  step 5 "–"; step 6 "–"; step 7 "–"; step 8 "–"
fi

# ---------------------------------------------------------------- 9 Dienst
step 9 "Berechtigungen, Dienst und alte Bridges"
if [[ ! -d /run/systemd/system ]]; then
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
REBOOT=true
if [[ -f "$DATA_DIR/system.json" ]]; then grep -q '"reboot": false' "$DATA_DIR/system.json" && REBOOT=false
elif ! ask_yn "Server-Neustart (Reboot) über das Webinterface erlauben?" j; then REBOOT=false; fi
systemctl daemon-reload
setup_sudo "$REBOOT"
fix_perms
systemctl enable n8crosslink >/dev/null 2>&1
systemctl enable --now n8crosslink-update.path >/dev/null 2>&1 && ok "„Update jetzt“ aus dem Adminportal eingerichtet"
systemctl restart n8crosslink
sleep 3
systemctl is-active --quiet n8crosslink && ok "Dienst n8crosslink läuft" || { warn "Dienst läuft nicht – Log:"; journalctl -u n8crosslink -n 25 --no-pager; }

PORT=$(cli show general | grep -oP '"web_port": \K[0-9]+' || echo 8080)
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
