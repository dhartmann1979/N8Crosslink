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
  for f in install.sh update.sh uninstall.sh n8x-certs.sh; do [[ -f "$APP_DIR/$f" ]] && chmod 755 "$APP_DIR/$f"; done
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

# ---------------------------------------------------------------- N8schicht-Vocoder
# Software-AMBE+2 für DMR: Fork des Codecs aus DroidStar (Doug McLain, GPL-3.0-or-later).
# Die Quellen liegen im Repository (third_party/n8schicht-vocoder) und werden hier mit g++
# gebaut – kein Download nötig. Die Bibliothek läuft in einem eigenen Prozess der Bridge.
VOC_SRC="$APP_DIR/third_party/n8schicht-vocoder"
VOC_DIR="$APP_DIR/lib"
VOC_LIB="$VOC_DIR/libn8vocoder.so"

voc_probe() { cli vocoder-test --mode n8vocoder 2>&1 | tail -1; }
voc_hash() { (cd "$VOC_SRC" && cat VERSION UPSTREAM_COMMIT build.sh src/*) | sha256sum | cut -c1-16; }
build_vocoder() {   # build_vocoder [force]
  local force="${1:-}" out h
  [[ -f "$VOC_SRC/build.sh" ]] || { warn "Quellen des N8schicht-Vocoders fehlen ($VOC_SRC)"; return 1; }
  h=$(voc_hash)
  if [[ -z "$force" && -f "$VOC_LIB" && "$(cat "$VOC_DIR/libn8vocoder.ref" 2>/dev/null)" == "$h" ]]; then
    out=$(voc_probe); [[ "$out" == OK* ]] && { ok "N8schicht-Vocoder aktuell – $out"; return 0; }
  fi
  info "Baue N8schicht-Vocoder $(cat "$VOC_SRC/VERSION") …"
  command -v g++ >/dev/null || apt-get install -y -qq g++ >/dev/null || { warn "Compiler (g++) nicht installierbar"; return 1; }
  install -d -m 755 -o root -g root "$VOC_DIR"
  if ! out=$(bash "$VOC_SRC/build.sh" "$VOC_LIB.new" 2>&1); then
    warn "Bauen fehlgeschlagen:"; echo "$out" | tail -8; rm -f "$VOC_LIB.new"; return 1
  fi
  mv -f "$VOC_LIB.new" "$VOC_LIB"; chown root:root "$VOC_LIB"; chmod 644 "$VOC_LIB"
  echo "$h" > "$VOC_DIR/libn8vocoder.ref"; chmod 644 "$VOC_DIR/libn8vocoder.ref"
  rm -f "$VOC_DIR/libambe2.so" "$VOC_DIR/libambe2.ref"                       # Bau aus 1.4/1.5
  rm -rf /usr/local/src/n8crosslink-droidstar                                 # Quellen-Download aus 1.4/1.5
  out=$(voc_probe)
  if [[ "$out" == OK* ]]; then ok "N8schicht-Vocoder gebaut und getestet – $out"; return 0; fi
  warn "N8schicht-Vocoder gebaut, Test fehlgeschlagen: $out"; return 1
}

# md380-emu wird nicht mehr gebraucht (ersetzt durch den N8schicht-Vocoder) und wird restlos entfernt:
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
SUDOERS=/etc/sudoers.d/n8crosslink
reboot_pref() { grep -q '"reboot": false' "$DATA_DIR/system.json" 2>/dev/null && echo false || echo true; }
sudo_rules() {   # sudo_rules DATEI [reboot] – schreibt die Freigaben nach DATEI, setzt SUDO_JSON (Dienste fürs Webinterface)
  local out="$1" allow_reboot="${2:-true}" u SC sep=""
  SC=$(type -P systemctl || echo /usr/bin/systemctl); SUDO_SC="$SC"; SUDO_JSON=""
  add_unit() {  # add_unit unit "label" "aktionen…"
    local unit="$1" label="$2" a al; shift 2
    for a in "$@"; do
      case "$a" in start|restart) echo "$SVC_USER ALL=(root) NOPASSWD: $SC --no-block $a $unit" >> "$out" ;;
                   *)             echo "$SVC_USER ALL=(root) NOPASSWD: $SC $a $unit" >> "$out" ;; esac
    done
    al=$(printf '"%s",' "$@"); al="[${al%,}]"
    local hidden=false; [[ "$unit" == *-update.service ]] && hidden=true     # wird über „Updates“ gestartet, nicht in der Liste
    SUDO_JSON+="${sep}{\"unit\": \"$unit\", \"label\": \"$label\", \"actions\": $al, \"hidden\": $hidden}"; sep=", "
  }
  echo "# N8 Crosslink – vom Installer erzeugt, nicht von Hand ändern (wird bei jedem Update neu geschrieben)" > "$out"
  echo "Defaults:$SVC_USER !requiretty" >> "$out"
  # eigene Dienste: aktivieren, deaktivieren, starten, stoppen, neu starten (Adminportal → System → Dienste)
  add_unit n8crosslink.service "N8 Crosslink" start stop restart enable disable
  add_unit n8crosslink-update.path "Update-Auslöser („Update jetzt“)" start stop restart enable disable
  add_unit n8crosslink-update.service "Update-Dienst" start
  for u in $(systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Ei '^(svxlink|mmdvm_bridge|analog_bridge|ambeserver|.*zello.*)\.service$' | grep -v n8crosslink | sort -u); do
    add_unit "$u" "${u%.service} (alt)" start stop restart enable disable
  done
  [[ "$allow_reboot" == "true" ]] && echo "$SVC_USER ALL=(root) NOPASSWD: $SC reboot" >> "$out"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/install.sh --fix-perms" >> "$out"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/install.sh --check-perms --json" >> "$out"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/install.sh --build-vocoder" >> "$out"
  # Domains & HTTPS (Let's Encrypt) im Webinterface – das Skript prüft jede Eingabe selbst
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/n8x-certs.sh" >> "$out"
  echo "$SVC_USER ALL=(root) NOPASSWD: $APP_DIR/n8x-certs.sh *" >> "$out"
  return 0
}
system_json() {  # Inhalt von data/system.json (was das Webinterface darf)
  printf '{"sudo": true, "systemctl": "%s", "reboot": %s, "fix_perms": true, "check_perms": true, "build_vocoder": true, "certs": true, "units": [%s]}\n' \
    "$SUDO_SC" "$1" "$SUDO_JSON"
}
sudo_includedir() {   # /etc/sudoers muss /etc/sudoers.d einbinden (fehlt auf manchen Minimal-Images)
  grep -Eq '^[[:space:]]*[@#]includedir[[:space:]]+/etc/sudoers\.d[[:space:]]*$' /etc/sudoers 2>/dev/null && return 0
  local T; T=$(mktemp); cat /etc/sudoers > "$T" 2>/dev/null || true; echo "@includedir /etc/sudoers.d" >> "$T"
  if visudo -cf "$T" >/dev/null 2>&1; then install -o root -g root -m 0440 "$T" /etc/sudoers; warn "/etc/sudoers band /etc/sudoers.d nicht ein – ergänzt"
  else warn "/etc/sudoers ließ sich nicht ergänzen (visudo) – bitte von Hand „@includedir /etc/sudoers.d“ eintragen"; fi
  rm -f "$T"
}
setup_sudo() {
  local allow_reboot="${1:-true}" TMP; TMP=$(mktemp)
  command -v sudo >/dev/null || { info "sudo fehlt – wird installiert"; apt-get install -y -qq sudo >/dev/null 2>&1 || warn "sudo nicht installierbar"; }
  command -v sudo >/dev/null || { rm -f "$TMP"; return 0; }
  [[ -f /etc/sudoers ]] && sudo_includedir
  install -d -o root -g root -m 0750 /etc/sudoers.d
  sudo_rules "$TMP" "$allow_reboot"
  if visudo -cf "$TMP" >/dev/null 2>&1; then
    install -o root -g root -m 0440 "$TMP" "$SUDOERS"
    mkdir -p "$DATA_DIR"; system_json "$allow_reboot" > "$DATA_DIR/system.json"
    id "$SVC_USER" &>/dev/null && chown "$SVC_USER:$SVC_USER" "$DATA_DIR/system.json"; chmod 640 "$DATA_DIR/system.json"
    ok "sudo fürs Webinterface eingerichtet ($(grep -c NOPASSWD "$SUDOERS") freigegebene Befehle, mit visudo geprüft)"
  else
    warn "sudoers-Datei ungültig – nicht übernommen"; visudo -cf "$TMP" || true
  fi
  rm -f "$TMP"
}

# ---------------------------------------------------------------- Berechtigungsprüfung (ändert nichts)
# Jede Prüfung ergibt eine Zeile „ok|warn|bad · Bereich · Text“. bad = Fehler, den --fix-perms korrigiert.
CK=()
ck() { CK+=("$1|$2|$3"); }
ck_mode() {   # ck_mode Bereich Datei besitzer:gruppe modus Beschreibung
  local is; is=$(stat -c '%U:%G %a' "$2" 2>/dev/null) || { ck bad "$1" "$5 fehlt ($2)"; return; }
  if [[ "$is" == "$3 $4" ]]; then ck ok "$1" "$5 ($3, $4)"; else ck bad "$1" "$5: $is statt $3 $4 ($2)"; fi
}
first_of() { head -1 | sed "s|^$APP_DIR/||"; }
check_perms() {
  local -; set +e +o pipefail      # nur prüfen: einzelne fehlgeschlagene Befehle sind Befunde, kein Abbruch
  CK=()
  local f n x mode="" dev=""
  # Dienstbenutzer
  if id "$SVC_USER" &>/dev/null; then
    ck ok user "Dienstbenutzer $SVC_USER vorhanden"
    if id -nG "$SVC_USER" | grep -qw dialout; then ck ok user "$SVC_USER ist in der Gruppe dialout (USB-Vocoder)"
    else ck bad user "$SVC_USER ist nicht in der Gruppe dialout (USB-Vocoder)"; fi
    [[ "$(getent passwd "$SVC_USER" | cut -d: -f7)" == */nologin || "$(getent passwd "$SVC_USER" | cut -d: -f7)" == /bin/false ]] \
      && ck ok user "$SVC_USER hat keine Login-Shell" || ck warn user "$SVC_USER hat eine Login-Shell ($(getent passwd "$SVC_USER" | cut -d: -f7))"
  else ck bad user "Dienstbenutzer $SVC_USER fehlt – bitte den Installer neu starten"; fi
  [[ -d "$APP_DIR" ]] || { ck bad prog "$APP_DIR fehlt – N8 Crosslink ist nicht installiert"; return 0; }
  # Programm: root:root, für den Dienst nicht beschreibbar
  n=$(find "$APP_DIR" -path "$DATA_DIR" -prune -o ! -type l \( ! -user root -o ! -group root -o -perm /022 \) -print 2>/dev/null | wc -l)
  if (( n == 0 )); then ck ok prog "Programmdateien gehören root und sind für den Dienst schreibgeschützt"
  else ck bad prog "$n Programmdateien gehören nicht root:root oder sind für Gruppe/andere beschreibbar (z. B. $(find "$APP_DIR" -path "$DATA_DIR" -prune -o ! -type l \( ! -user root -o ! -group root -o -perm /022 \) -print 2>/dev/null | first_of))"; fi
  n=$(find "$APP_DIR" -path "$DATA_DIR" -prune -o -type d ! -perm 755 -print 2>/dev/null | wc -l)
  (( n == 0 )) && ck ok prog "Ordner 755" || ck bad prog "$n Ordner nicht 755 (z. B. $(find "$APP_DIR" -path "$DATA_DIR" -prune -o -type d ! -perm 755 -print 2>/dev/null | first_of))"
  for f in install.sh update.sh uninstall.sh n8x-certs.sh; do [[ -f "$APP_DIR/$f" ]] && ck_mode prog "$APP_DIR/$f" root:root 755 "$f"; done
  if [[ -x "$APP_DIR/venv/bin/python" ]]; then ck ok prog "Python-Umgebung (venv) ausführbar"; else ck bad prog "venv/bin/python fehlt oder ist nicht ausführbar"; fi
  n=$(find "$APP_DIR/venv/bin" -maxdepth 1 -type f ! -perm 755 2>/dev/null | wc -l)
  (( n == 0 )) || ck bad prog "$n Programme in venv/bin nicht 755"
  [[ -e "$APP_DIR/.cache" ]] && ck bad prog "Zwischenspeicher $APP_DIR/.cache gehört nicht ins Programmverzeichnis"
  n=$(find "$APP_DIR" -path "$DATA_DIR" -prune -o -path "$APP_DIR/venv" -prune -o -type f \( -name '*.key' -o -name '*.pem' -o -name '*.p12' \) -perm /044 -print 2>/dev/null | wc -l)
  (( n == 0 )) && ck ok prog "keine lesbaren Schlüsseldateien" || ck bad prog "$n Schlüsseldateien (*.key/*.pem) für andere lesbar"
  # Daten: gehören dem Dienst
  if [[ -d "$DATA_DIR" ]]; then
    ck_mode data "$DATA_DIR" "$SVC_USER:$SVC_USER" 750 "Datenordner"
    n=$(find "$DATA_DIR" \( ! -user "$SVC_USER" ! -name update.log \) -print 2>/dev/null | wc -l)
    (( n == 0 )) && ck ok data "alle Daten gehören $SVC_USER" || ck bad data "$n Dateien im Datenordner gehören nicht $SVC_USER (z. B. $(find "$DATA_DIR" \( ! -user "$SVC_USER" ! -name update.log \) -print 2>/dev/null | first_of))"
    if [[ -f "$DB" ]]; then
      n=$(find "$DATA_DIR" -type f -name '*.db*' ! -perm 640 2>/dev/null | wc -l)
      (( n == 0 )) && ck ok data "Datenbank nur für $SVC_USER lesbar (640)" || ck bad data "$n Datenbankdateien nicht 640 (Passwörter und Schlüssel liegen darin)"
    else ck warn data "Datenbank $DB fehlt noch (wird beim ersten Start angelegt)"; fi
    [[ -f "$DATA_DIR/update.log" ]] && { [[ "$(stat -c %a "$DATA_DIR/update.log")" == 644 ]] && ck ok data "update.log lesbar (644)" || ck bad data "update.log nicht 644"; }
  else ck bad data "Datenordner $DATA_DIR fehlt"; fi
  # systemd
  for f in n8crosslink.service n8crosslink-update.path n8crosslink-update.service; do
    [[ -f "/etc/systemd/system/$f" ]] && ck_mode systemd "/etc/systemd/system/$f" root:root 644 "$f" || ck bad systemd "$f fehlt in /etc/systemd/system"
  done
  x=$(sed -n 's/^User=//p' /etc/systemd/system/n8crosslink.service 2>/dev/null | head -1)
  [[ -f /etc/systemd/system/n8crosslink.service ]] && { [[ "$x" == "$SVC_USER" ]] && ck ok systemd "Dienst läuft als $SVC_USER (ohne root)" || ck bad systemd "Dienst läuft als ${x:-root} statt $SVC_USER"; }
  systemctl is-enabled n8crosslink-update.path >/dev/null 2>&1 && ck ok systemd "„Update jetzt“ (n8crosslink-update.path) aktiv" || ck bad systemd "n8crosslink-update.path ist nicht aktiv – „Update jetzt“ im Adminportal geht nicht"
  # Quelle (daraus installiert update.sh als root)
  if [[ -f "$APP_DIR/.source" ]]; then
    x=$(cat "$APP_DIR/.source")
    if [[ -d "$x" ]]; then
      n=$(find "$x" ! -type l \( ! -user root -o -perm /022 \) -print 2>/dev/null | wc -l)
      (( n == 0 )) && ck ok source "Quellordner $x gehört root" || ck bad source "$n Dateien im Quellordner $x gehören nicht root oder sind beschreibbar (daraus wird als root installiert)"
    fi
  fi
  # USB-Vocoder (Einstellung über den Dienstbenutzer lesen – root legt so keine Datenbankdateien an)
  if [[ -f "$DB" && -x "$APP_DIR/venv/bin/python" ]] && id "$SVC_USER" &>/dev/null; then
    x=$(cli show vocoder 2>/dev/null || true)
    mode=$(grep -oP '"vocoder_mode": "\K[^"]*' <<<"$x" || true); dev=$(grep -oP '"usb_device": "\K[^"]*' <<<"$x" || true)
    if [[ "$mode" == usb && -n "$dev" ]]; then
      if [[ -e "$dev" ]]; then
        x=$(stat -c %G "$(readlink -f "$dev")")
        id -nG "$SVC_USER" | grep -qw "$x" && ck ok usb "USB-Stick $dev erreichbar (Gruppe $x)" || ck bad usb "kein Zugriff auf $dev (Gruppe $x fehlt bei $SVC_USER)"
      else ck warn usb "USB-Stick $dev ist gerade nicht angeschlossen"; fi
    fi
  fi
  # Domains & HTTPS
  [[ -d /var/www/n8crosslink-acme ]] && ck_mode https /var/www/n8crosslink-acme root:root 755 "Let's-Encrypt-Prüfordner"
  for f in /etc/nginx/sites-available/n8crosslink /etc/nginx/sites-available/n8crosslink-*; do
    [[ -f "$f" && "$f" != *.bak && "$f" != *.tmp ]] && ck_mode https "$f" root:root 644 "nginx-Seite ${f##*/}"
  done
  check_sudo
  return 0
}
check_sudo() {
  local -; set +e +o pipefail
  local T x
  if ! command -v sudo >/dev/null; then ck bad sudo "sudo ist nicht installiert – Dienste, Updates und HTTPS im Webinterface gehen nicht"; return 0; fi
  ck ok sudo "sudo installiert"
  if grep -Eq '^[[:space:]]*[@#]includedir[[:space:]]+/etc/sudoers\.d[[:space:]]*$' /etc/sudoers 2>/dev/null; then ck ok sudo "/etc/sudoers bindet /etc/sudoers.d ein"
  else ck bad sudo "/etc/sudoers bindet /etc/sudoers.d nicht ein – die Freigaben wirken nicht"; fi
  if command -v systemd-run >/dev/null; then ck ok sudo "systemd-run vorhanden (Root-Aufgaben aus dem Webinterface laufen außerhalb der Dienst-Sandbox)"
  else ck bad sudo "systemd-run fehlt – Root-Aufgaben aus dem Webinterface scheitern an der Dienst-Sandbox (/etc schreibgeschützt)"; fi
  [[ -w /etc ]] && ck ok sudo "/etc beschreibbar (Prüfung läuft außerhalb der Sandbox)" || ck bad sudo "/etc ist hier schreibgeschützt – Prüfung läuft noch in der Dienst-Sandbox"
  if [[ ! -f "$SUDOERS" ]]; then ck bad sudo "Freigaben $SUDOERS fehlen"; return 0; fi
  ck_mode sudo "$SUDOERS" root:root 440 "Freigaben $SUDOERS"
  if visudo -cf "$SUDOERS" >/dev/null 2>&1; then ck ok sudo "Freigaben gültig (visudo)"; else ck bad sudo "Freigaben ungültig (visudo meldet Fehler)"; fi
  T=$(mktemp); sudo_rules "$T" "$(reboot_pref)"
  x=$(diff <(grep -v '^#' "$T" | sort) <(grep -v '^#' "$SUDOERS" | sort) | grep -c '^[<>]' || true); rm -f "$T"
  [[ "$x" == 0 ]] && ck ok sudo "Freigaben aktuell ($(grep -c NOPASSWD "$SUDOERS") Befehle)" || ck bad sudo "Freigaben veraltet oder von Hand geändert ($x Zeilen weichen ab)"
  if id "$SVC_USER" &>/dev/null && sudo -l -U "$SVC_USER" 2>/dev/null | grep -qF "$APP_DIR/install.sh --fix-perms"; then ck ok sudo "Freigaben wirksam für $SVC_USER (sudo -l)"
  else ck bad sudo "Freigaben wirken nicht für $SVC_USER (sudo -l zeigt sie nicht)"; fi
  if [[ -f "$DATA_DIR/system.json" ]]; then
    ck_mode sudo "$DATA_DIR/system.json" "$SVC_USER:$SVC_USER" 640 "system.json (was das Webinterface darf)"
    grep -q '"check_perms": true' "$DATA_DIR/system.json" && grep -q '"certs": true' "$DATA_DIR/system.json" \
      && ck ok sudo "system.json vollständig" || ck bad sudo "system.json veraltet – Webinterface kennt nicht alle Freigaben"
  else ck bad sudo "system.json fehlt – das Webinterface weiß nicht, was es darf"; fi
  return 0
}
perm_bad() { local l n=0; for l in "${CK[@]}"; do [[ "$l" == bad\|* ]] && n=$((n + 1)); done; echo "$n"; }
perm_bad_in() { local l; for l in "${CK[@]}"; do [[ "$l" == "bad|$1|"* ]] && return 0; done; return 1; }
perm_report() {   # perm_report [alle|fehler]
  local l st ar tx last="" icon
  declare -A NAME=([user]="Dienstbenutzer" [prog]="Programm $APP_DIR" [data]="Daten $DATA_DIR" [systemd]="systemd" [source]="Quellordner"
                   [usb]="USB-Vocoder" [https]="Domains & HTTPS" [sudo]="sudo")
  for l in "${CK[@]}"; do
    IFS='|' read -r st ar tx <<<"$l"
    [[ "${1:-alle}" == fehler && "$st" == ok ]] && continue
    [[ "$ar" != "$last" ]] && { echo "  ${B}${NAME[$ar]:-$ar}${R}"; last="$ar"; }
    case "$st" in ok) icon="${G}✔${R}" ;; warn) icon="${Y}⚠${R}" ;; *) icon="${E}✖${R}" ;; esac
    echo "    $icon $tx"
  done
}
perm_json() {
  printf '%s\n' "${CK[@]}" | python3 -c 'import json,sys
rows = [dict(zip(("status", "area", "text"), l.rstrip("\n").split("|", 2))) for l in sys.stdin if l.strip()]
print(json.dumps({"ok": not any(r["status"] == "bad" for r in rows), "bad": sum(r["status"] == "bad" for r in rows),
                  "warn": sum(r["status"] == "warn" for r in rows), "checks": rows}, ensure_ascii=False))'
}
repair_perms() {   # prüfen → gezielt korrigieren → erneut prüfen; Rückgabe 0 = alles in Ordnung
  local before after f
  check_perms; before=$(perm_bad)
  if (( before == 0 )); then ok "Berechtigungen und sudo geprüft – $((${#CK[@]})) Prüfungen, alles in Ordnung"; perm_report fehler; return 0; fi
  warn "$before Fehler gefunden:"; perm_report fehler
  info "korrigiere …"
  if id "$SVC_USER" &>/dev/null && perm_bad_in user && ! id -nG "$SVC_USER" | grep -qw dialout; then usermod -a -G dialout "$SVC_USER"; fi
  import_zello_keys; fix_perms
  if perm_bad_in systemd; then
    for f in n8crosslink.service n8crosslink-update.path n8crosslink-update.service; do
      local src="$APP_DIR/systemd/$f"; [[ -f "$src" ]] || src="$SRC_DIR/systemd/$f"
      [[ -f "/etc/systemd/system/$f" || ! -f "$src" ]] || install -o root -g root -m 644 "$src" "/etc/systemd/system/$f"
    done
    systemctl daemon-reload >/dev/null 2>&1 || true; systemctl enable --now n8crosslink-update.path >/dev/null 2>&1 || true
  fi
  perm_bad_in https && { [[ -d /var/www/n8crosslink-acme ]] && chown root:root /var/www/n8crosslink-acme && chmod 755 /var/www/n8crosslink-acme
    for f in /etc/nginx/sites-available/n8crosslink /etc/nginx/sites-available/n8crosslink-*; do [[ -f "$f" ]] && chown root:root "$f" && chmod 644 "$f"; done; }
  perm_bad_in sudo && setup_sudo "$(reboot_pref)"
  check_perms; after=$(perm_bad)
  if (( after == 0 )); then ok "alle $before Fehler korrigiert – erneut geprüft, alles in Ordnung"; return 0; fi
  warn "$after Fehler ließen sich nicht automatisch korrigieren:"; perm_report fehler; return 1
}

cli() { (cd "$APP_DIR" && runuser -u "$SVC_USER" -- env N8X_DB="$DB" "$APP_DIR/venv/bin/python" -m n8crosslink.cli "$@"); }
setcfg() { cli set "$1" "$2" "$3" >/dev/null; }

# Aus dem Webinterface (sudo) läuft das in der Sandbox des Dienstes: ProtectSystem=full macht /etc und /usr schreibgeschützt,
# das erbt auch sudo. Root-Aufgaben deshalb als eigener kurzlebiger systemd-Dienst außerhalb der Sandbox neu starten
# (Ausgabe und Rückgabewert kommen über --pipe/--wait zurück).
case "${1:-}" in
  --check-perms|--fix-perms|--build-vocoder|--install-md380)
    if [[ $EUID -eq 0 && -z "${N8X_UNSANDBOXED:-}" && ! -w /etc ]]; then
      command -v systemd-run >/dev/null 2>&1 || fail "/etc ist schreibgeschützt (Dienst-Sandbox) und systemd-run fehlt – bitte auf der Konsole ausführen"
      exec systemd-run --quiet --wait --pipe --collect --service-type=exec -p "Description=N8 Crosslink – install.sh $1" \
        --setenv=N8X_UNSANDBOXED=1 -- "$(readlink -f "${BASH_SOURCE[0]}")" "$@"
    fi ;;
esac
if [[ "${1:-}" == "--check-perms" ]]; then   # nur prüfen, nichts ändern (Rückgabe 1 = Fehler gefunden)
  [[ $EUID -eq 0 ]] || fail "Bitte als root starten"
  check_perms
  if [[ "${2:-}" == "--json" ]]; then perm_json; else echo "Berechtigungen und sudo prüfen (N8 Crosslink) …"; perm_report alle
    n=$(perm_bad); (( n == 0 )) && ok "alles in Ordnung" || warn "$n Fehler – korrigieren: sudo $APP_DIR/install.sh --fix-perms"; fi
  (( $(perm_bad) == 0 )); exit $?
fi
if [[ "${1:-}" == "--fix-perms" ]]; then   # prüfen, Fehler korrigieren (auch sudo), erneut prüfen
  [[ $EUID -eq 0 ]] || fail "Bitte als root starten"
  echo "Berechtigungen und sudo prüfen & korrigieren (N8 Crosslink) …"; repair_perms; exit $?
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
  echo "== N8schicht-Vocoder: $([[ -f "$VOC_LIB" ]] && echo "$VOC_LIB ($(cat "$VOC_SRC/VERSION" 2>/dev/null), Bau $(cat "$VOC_DIR/libn8vocoder.ref" 2>/dev/null))" || echo 'nicht gebaut'); md380-emu: $(dpkg -s md380-emu >/dev/null 2>&1 || [[ -d /opt/md380-emu ]] && echo 'noch vorhanden – wird beim Update entfernt' || echo 'entfernt')"
  echo "== Vocoder-Test: $( (cd "$APP_DIR" && runuser -u "$SVC_USER" -- env N8X_DB="$DB" "$APP_DIR/venv/bin/python" -m n8crosslink.cli vocoder-test) 2>&1 | tail -1)"
  echo "== Zello-Schlüssel: $(cli zello-key-info 2>&1 | tail -1); Schlüsseldateien: $(find "$APP_DIR" -maxdepth 2 -iname 'zello*.key' 2>/dev/null | wc -l)"
  echo "== sudo-Freigaben: $(grep -c NOPASSWD /etc/sudoers.d/n8crosslink 2>/dev/null || echo 0)"
  echo "== Öffentliches FRN-Fehlerprotokoll (http://log.freeradionetwork.de:60080/error_log.php) – Einträge zu Rufzeichen/Servern:"
  cli show frn 2>/dev/null | (cd "$APP_DIR" && "$APP_DIR/venv/bin/python" -c '
import asyncio, json, sys
from n8crosslink import frn_errorlog as el
s = json.load(sys.stdin)
entries, err = asyncio.run(el.fetch(force=True))
if err: print("   " + err); raise SystemExit
mine = el.summarize(el.relevant(entries, [s.get("callsign", "")], [s.get("server", ""), s.get("backup_server", "")]))
print("   (keine – in den letzten %d Einträgen)" % len(entries) if not mine else "\n".join(
    "   %s  %s %s  %s (%d×)%s" % (g["ts"], g["kind"], g["id"], g["message"], g["count"], ("\n      → " + g["hint"]) if g["hint"] else "") for g in mine))
' 2>&1 || echo "   (nicht abrufbar)")
  echo "== Log n8crosslink (letzte 40):"; journalctl -u n8crosslink -n 40 --no-pager -o cat 2>/dev/null
  } 2>&1 | tee /tmp/n8crosslink-diagnose.txt
  echo; echo "(gespeichert in /tmp/n8crosslink-diagnose.txt – enthält keine Passwörter)"; exit 0
fi
if [[ "${1:-}" == "--build-vocoder" || "${1:-}" == "--install-md380" ]]; then
  [[ $EUID -eq 0 ]] || fail "Bitte als root starten"
  echo "N8schicht-Vocoder bauen/prüfen …"
  build_vocoder force || exit 1
  setcfg vocoder vocoder_mode n8vocoder; ok "Vocoder auf N8schicht-Vocoder gestellt"
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
rm -rf "$APP_DIR/third_party"; mkdir -p "$APP_DIR/third_party"
cp -r "$SRC_DIR/third_party/n8schicht-vocoder" "$APP_DIR/third_party/"
chmod 755 "$APP_DIR/third_party/n8schicht-vocoder/build.sh"
cp "$SRC_DIR/install.sh" "$SRC_DIR/update.sh" "$SRC_DIR/uninstall.sh" "$SRC_DIR/n8x-certs.sh" "$APP_DIR/" 2>/dev/null || true
mkdir -p "$APP_DIR/systemd"; cp "$SRC_DIR"/systemd/*.service "$SRC_DIR"/systemd/*.path "$APP_DIR/systemd/" 2>/dev/null || true   # für die Reparatur
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
  "N8schicht-Vocoder (Software, ohne Hardware – empfohlen)" \
  "USB-Stick (ThumbDV / DVstick 30 / DV3000)" \
  "AMBEserver im Netz" \
  "später im Adminportal festlegen"
case "$VOC" in
  1) setcfg vocoder vocoder_mode n8vocoder
     build_vocoder || warn "Vocoder kann später unter Admin → 🎛️ Vocoder → „Vocoder bauen“ nachgeholt werden" ;;
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
elif [[ "$MODE" != "setup" ]]; then
  step 4 "Einstellungen bleiben erhalten"; ok "$([[ "$MODE" == restored ]] && echo "aus dem Backup übernommen" || echo "Update-Modus")"
  # md380-emu (bis 1.3) und „droidstar“ (1.4/1.5) -> N8schicht-Vocoder; bauen nur wenn nötig; md380-emu entfernen
  if sqlite3 "$DB" "SELECT value FROM settings WHERE section='vocoder' AND key='vocoder_mode'" 2>/dev/null | grep -qE 'md380|droidstar'; then
    setcfg vocoder vocoder_mode n8vocoder; ok "Vocoder auf den N8schicht-Vocoder umgestellt"
  fi
  if cli show vocoder | grep -q '"vocoder_mode": "n8vocoder"'; then build_vocoder || true; fi
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
info "Berechtigungen und sudo prüfen …"; repair_perms || warn "Berechtigungen: siehe oben – Prüfung später: sudo $APP_DIR/install.sh --check-perms"
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
    # dasselbe Skript wie im Webinterface (Admin → 🔒 Domains & HTTPS) – weitere Domains kommen dort dazu
    "$APP_DIR/n8x-certs.sh" deps >/dev/null || warn "nginx/certbot nicht installierbar"
    ask LE_MAIL "E-Mail für Let's Encrypt" ""
    R=$("$APP_DIR/n8x-certs.sh" add "$SERVER_NAME" "$LE_MAIL" "$PORT" 80 443 2>&1 || true)
    if [[ "$R" == *'"ok": true'* ]]; then ok "HTTPS aktiv: https://${SERVER_NAME}"
    else warn "Zertifikat fehlgeschlagen – DNS/Port 80 prüfen, dann im Webinterface unter 🔒 Domains & HTTPS erneut"; fi
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
