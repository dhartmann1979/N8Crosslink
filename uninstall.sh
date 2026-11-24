#!/usr/bin/env bash
# N8 Crosslink – Deinstallation (fragt, ob die Datenbank behalten werden soll).
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Bitte als root starten: sudo $0"; exit 1; }
read -r -p "N8 Crosslink wirklich entfernen? [j/N]: " a </dev/tty; [[ "$a" =~ ^[jJyY] ]] || exit 0
systemctl disable --now n8crosslink n8crosslink-update.path 2>/dev/null || true
rm -f /etc/systemd/system/n8crosslink.service /etc/systemd/system/n8crosslink-update.path /etc/systemd/system/n8crosslink-update.service
rm -f /etc/sudoers.d/n8crosslink
rm -f /etc/nginx/sites-enabled/n8crosslink /etc/nginx/sites-available/n8crosslink 2>/dev/null || true
systemctl daemon-reload
read -r -p "Datenbank (Einstellungen, Last Heard) behalten? [J/n]: " k </dev/tty
if [[ "${k:-j}" =~ ^[jJyY] ]]; then
  BK="/root/n8crosslink-backup-$(date +%Y%m%d-%H%M).db"
  cp /opt/n8crosslink/data/crosslink.db "$BK" 2>/dev/null && echo "✔ Datenbank gesichert: $BK"
fi
rm -rf /opt/n8crosslink
userdel n8crosslink 2>/dev/null || true
echo "✔ N8 Crosslink entfernt. md380-emu und alte Dienste (SvxLink etc.) wurden nicht angefasst."
