#!/usr/bin/env bash
# =============================================================================
#  N8 Crosslink – Deinstallation / von vorn beginnen
#
#  sudo /opt/n8crosslink/uninstall.sh            geführt (empfohlen)
#  Optionen:  --keep-data   Programm entfernen, Daten (Einstellungen, Benutzer, Last Heard) behalten
#             --purge       alles entfernen inkl. Daten und Dienstbenutzer
#             --yes         keine Rückfragen (mit --keep-data oder --purge)
#             --no-backup   kein Backup vorher anbieten
# =============================================================================
set -uo pipefail
APP_DIR=/opt/n8crosslink; DATA_DIR=$APP_DIR/data; DB=$DATA_DIR/crosslink.db; SVC_USER=n8crosslink
STATE=/var/lib/n8crosslink
if [[ -t 1 ]]; then B=$'\e[1m'; D=$'\e[2m'; R=$'\e[0m'; G=$'\e[38;5;77m'; Y=$'\e[38;5;221m'; E=$'\e[38;5;203m'; C=$'\e[38;5;81m'
else B=""; D=""; R=""; G=""; Y=""; E=""; C=""; fi
ok()   { echo "  ${G}✔${R} $*"; }
warn() { echo "  ${Y}⚠${R} $*"; }
info() { echo "  ${C}›${R} $*"; }
YES=0; MODE=""; BACKUP=1
for a in "$@"; do case "$a" in --yes) YES=1 ;; --keep-data) MODE=keep ;; --purge) MODE=purge ;; --no-backup) BACKUP=0 ;; esac; done
ask_yn() { local q="$1" def="${2:-n}" a hint="j/N"; [[ "$def" == "j" ]] && hint="J/n"
  if [[ $YES -eq 1 ]]; then [[ "$def" == "j" ]]; return; fi
  read -r -p "  ${B}?${R} $q ${D}[$hint]${R}: " a </dev/tty || true; a="${a:-$def}"; [[ "$a" =~ ^[jJyY] ]]; }

[[ $EUID -eq 0 ]] || { echo "Bitte als root starten: sudo $0"; exit 1; }
echo; echo "${B}N8 Crosslink – Deinstallation${R}"; echo
[[ -d "$APP_DIR" ]] || warn "$APP_DIR existiert nicht (bereits entfernt?) – räume Reste auf."

# ---------------------------------------------------------------- 1 Modus
if [[ -z "$MODE" ]]; then
  echo "     ${B}1)${R} Programm entfernen, ${B}Daten behalten${R} (für eine saubere Neuinstallation)"
  echo "     ${B}2)${R} ${E}Alles entfernen${R} inkl. Einstellungen, Benutzer, Last Heard (komplett von vorn)"
  echo "     ${B}3)${R} Abbrechen"
  read -r -p "  ${B}?${R} Auswahl ${D}[1]${R}: " m </dev/tty || true
  case "${m:-1}" in 1) MODE=keep ;; 2) MODE=purge ;; *) echo "Abgebrochen."; exit 0 ;; esac
fi

# ---------------------------------------------------------------- 2 Backup
if [[ $BACKUP -eq 1 && -f "$DB" && -x "$APP_DIR/venv/bin/python" ]]; then
  if ask_yn "Vorher ein verschlüsseltes Backup erstellen (empfohlen)?" j; then
    echo "  ${Y}WICHTIG:${R} Das Backup wird mit dem ${B}Superadmin-Passwort${R} verschlüsselt."
    echo "           Ohne dieses Passwort ist keine Wiederherstellung möglich – im Passwortsafe aufbewahren!"
    mkdir -p /root/n8crosslink-backups; chmod 700 /root/n8crosslink-backups
    for t in 1 2 3; do
      read -r -s -p "  ${B}?${R} Superadmin-Passwort: " pw </dev/tty || true; echo
      if out=$(cd "$APP_DIR" && printf '%s\n' "$pw" | N8X_DB="$DB" "$APP_DIR/venv/bin/python" -m n8crosslink.cli backup --out /root/n8crosslink-backups 2>&1); then
        ok "$out"; break
      else warn "$out"; fi
    done
    unset pw
  fi
fi
if [[ "$MODE" == "purge" && $YES -eq 0 ]]; then
  ask_yn "${E}Wirklich ALLES löschen?${R} Das kann nicht rückgängig gemacht werden" n || { echo "Abgebrochen."; exit 0; }
fi

# ---------------------------------------------------------------- 3 Dienste & Dateien
info "Dienste stoppen …"
systemctl disable --now n8crosslink n8crosslink-update.path n8crosslink-update.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/n8crosslink.service /etc/systemd/system/n8crosslink-update.path /etc/systemd/system/n8crosslink-update.service
rm -f /etc/sudoers.d/n8crosslink
ok "Dienste, Update-Auslöser und sudo-Freigaben entfernt"
if [[ -f /etc/nginx/sites-available/n8crosslink ]]; then
  DOMAIN=$(awk '/server_name/{print $2; exit}' /etc/nginx/sites-available/n8crosslink | tr -d ';')
  rm -f /etc/nginx/sites-enabled/n8crosslink /etc/nginx/sites-available/n8crosslink
  nginx -t >/dev/null 2>&1 && systemctl reload nginx
  ok "nginx-Konfiguration entfernt"
  if [[ -n "$DOMAIN" ]] && command -v certbot >/dev/null && ask_yn "Let's-Encrypt-Zertifikat für $DOMAIN löschen?" n; then
    certbot delete --cert-name "$DOMAIN" --non-interactive >/dev/null 2>&1 && ok "Zertifikat gelöscht"
  fi
fi
if [[ "$MODE" == "keep" ]]; then
  find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name data -exec rm -rf {} + 2>/dev/null
  ok "Programm entfernt – Daten liegen weiter in $DATA_DIR (Neuinstallation übernimmt sie)"
else
  rm -rf "$APP_DIR"
  userdel "$SVC_USER" 2>/dev/null || true
  ok "Programm, Daten und Dienstbenutzer entfernt"
  if [[ -d /usr/local/src/N8Crosslink ]] && ask_yn "Quellcode in /usr/local/src/N8Crosslink löschen?" j; then rm -rf /usr/local/src/N8Crosslink; fi
fi

# ---------------------------------------------------------------- 4 md380-emu
if systemctl list-unit-files 2>/dev/null | grep -q '^md380-emu.service' || command -v md380-emu >/dev/null || [[ -f /opt/md380-emu/md380-emu ]]; then
  if ask_yn "Software-Vocoder md380-emu entfernen? (nein, falls DVSwitch/Analog_Bridge ihn noch nutzt)" n; then
    systemctl disable --now md380-emu >/dev/null 2>&1 || true
    grep -q "N8 Crosslink" /etc/systemd/system/md380-emu.service 2>/dev/null && rm -f /etc/systemd/system/md380-emu.service
    apt-get purge -y -qq md380-emu >/dev/null 2>&1 || true
    ok "md380-emu entfernt"
    if ls /etc/apt/sources.list.d/*dvswitch* >/dev/null 2>&1 && ask_yn "DVSwitch-Paketquelle ebenfalls entfernen?" n; then
      rm -f /etc/apt/sources.list.d/*dvswitch*; apt-get update -qq >/dev/null 2>&1; ok "DVSwitch-Paketquelle entfernt"
    fi
  fi
fi
systemctl daemon-reload 2>/dev/null || true

# ---------------------------------------------------------------- 5 alte Dienste
if [[ -s "$STATE/disabled-services" ]]; then
  echo "  Diese Dienste hatte der Installer abgeschaltet:"; sed 's/^/       • /' "$STATE/disabled-services"
  if ask_yn "Wieder einschalten (SvxLink / alte Bridges)?" n; then
    while read -r s; do systemctl enable --now "$s" >/dev/null 2>&1 && ok "$s wieder aktiv"; done < "$STATE/disabled-services"
  fi
fi
[[ "$MODE" == "purge" ]] && rm -rf "$STATE"

echo
echo "${G}${B}  ✔ N8 Crosslink wurde entfernt.${R}"
[[ -d /root/n8crosslink-backups ]] && echo "    Backups:  /root/n8crosslink-backups (verschlüsselt mit dem Superadmin-Passwort)"
echo "    Neu installieren: git clone https://github.com/dhartmann1979/N8Crosslink.git && cd N8Crosslink && sudo ./install.sh"
echo
