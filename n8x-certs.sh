#!/usr/bin/env bash
# N8 Crosslink – Domains & HTTPS (Let's Encrypt) für das Webinterface.
#
# Läuft als root über sudo (/etc/sudoers.d/n8crosslink erlaubt nur dieses Skript). Jede Eingabe wird hier geprüft:
#   n8x-certs.sh status PORT                     Zustand als JSON (nginx, certbot, Domains, Zertifikate, Port 80/443)
#   n8x-certs.sh deps                            nginx, certbot und python3-certbot-nginx installieren, Erneuerungs-Timer an
#   n8x-certs.sh add DOMAIN EMAIL PORT [staging] nginx-Weiterleitung für DOMAIN → 127.0.0.1:PORT anlegen, Zertifikat holen
#   n8x-certs.sh renew DOMAIN                    Zertifikat jetzt erneuern (auch wenn es noch nicht fällig ist)
#   n8x-certs.sh remove DOMAIN                   Weiterleitung und Zertifikat entfernen
#
# Dateien: /etc/nginx/sites-available/n8crosslink-<domain> (+ Link in sites-enabled), Zertifikate von certbot unter
# /etc/letsencrypt/live/<domain>/. Die Seite des alten Installers (/etc/nginx/sites-available/n8crosslink) wird erkannt.
# Erneuert wird automatisch über den certbot-Timer (certbot.timer bzw. /etc/cron.d/certbot).
set -euo pipefail
export LC_ALL=C
AV=/etc/nginx/sites-available
EN=/etc/nginx/sites-enabled
LE=/etc/letsencrypt/live
DOM_RE='^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$'
MAIL_RE='^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$'

die() { python3 -c 'import json,sys; print(json.dumps({"ok": False, "message": sys.argv[1]}, ensure_ascii=False))' "$1"; exit 1; }
[[ $EUID -eq 0 ]] || die "nur als root (über sudo)"
dom_ok() { [[ ${#1} -le 253 && "$1" =~ $DOM_RE ]] || die "Ungültige Domain: $1"; }
port_ok() { [[ "$1" =~ ^[0-9]{1,5}$ && "$1" -ge 1 && "$1" -le 65535 ]] || die "Ungültiger Port: $1"; }
have() { command -v "$1" >/dev/null 2>&1; }
reload_nginx() { nginx -t >/dev/null 2>&1 || return 0; systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null || true; }

site_of() {   # Datei, in der die Domain steht (eigene oder die des alten Installers)
    local d="$1" f re="${1//./\\.}"
    for f in "$AV/n8crosslink-$d" "$AV/n8crosslink"; do
        [[ -f "$f" ]] && grep -Eq "server_name[^;]*[[:space:]]$re([[:space:];]|$)" "$f" && { echo "$f"; return 0; }
    done
    return 0
}

status() {
    local port="$1"
    python3 - "$port" <<'PY'
import glob, json, os, re, shutil, subprocess, sys
port = int(sys.argv[1])
def sh(*a):
    try:
        return subprocess.run(list(a), capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""
def cert(d):
    f = f"/etc/letsencrypt/live/{d}/fullchain.pem"
    if not os.path.isfile(f):
        return None
    out = sh("openssl", "x509", "-noout", "-enddate", "-issuer", "-in", f)
    end = re.search(r"notAfter=(.+)", out)
    iss = re.search(r"issuer=.*?O ?= ?([^,\n]+)", out)
    days = None
    if end:
        ts = sh("date", "-d", end.group(1).strip(), "+%s").strip()
        if ts.isdigit():
            import time
            days = int((int(ts) - time.time()) // 86400)
    return {"expires": end.group(1).strip() if end else "", "days": days, "issuer": (iss.group(1).strip() if iss else ""),
            "staging": "STAGING" in out.upper() or "(STAGING)" in out}
sites = []
for f in sorted(glob.glob("/etc/nginx/sites-available/n8crosslink*")):
    txt = open(f, encoding="utf-8", errors="replace").read()
    names = sorted({n for m in re.findall(r"server_name\s+([^;]+);", txt) for n in m.split() if n not in ("_", "localhost")})
    up = re.search(r"proxy_pass\s+http://127\.0\.0\.1:(\d+)", txt)
    enabled = os.path.exists(f.replace("sites-available", "sites-enabled"))
    for n in names:
        c = cert(n)
        sites.append({"domain": n, "file": f, "legacy": f.endswith("/n8crosslink"), "enabled": enabled,
                      "upstream": int(up.group(1)) if up else None, "https": "ssl_certificate" in txt and c is not None, "cert": c})
listen = sh("ss", "-ltnpH")
def who(p):
    for l in listen.splitlines():
        if re.search(rf":{p}\s", l):
            m = re.search(r'users:\(\("([^"]+)"', l)
            return m.group(1) if m else "belegt"
    return ""
timer = sh("systemctl", "is-enabled", "certbot.timer").strip() == "enabled" or os.path.exists("/etc/cron.d/certbot")
print(json.dumps({"ok": True, "nginx": bool(shutil.which("nginx")), "certbot": bool(shutil.which("certbot")),
                  "certbot_nginx": bool(glob.glob("/usr/lib/python3/dist-packages/certbot_nginx*")) or bool(shutil.which("certbot") and "nginx" in sh("certbot", "plugins", "--text")),
                  "renew_timer": timer, "port80": who(80), "port443": who(443), "web_port": port,
                  "portal": os.path.exists("/etc/nginx/sites-available/hobbyradioportal") or os.path.isdir("/opt/hobbyradioportal"),
                  "sites": sites}, ensure_ascii=False))
PY
}

deps() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null 2>&1 || true
    apt-get install -y -qq nginx certbot python3-certbot-nginx >/dev/null 2>&1 || die "Pakete nicht installierbar (apt-get install nginx certbot python3-certbot-nginx)"
    systemctl enable --now nginx >/dev/null 2>&1 || true
    systemctl enable --now certbot.timer >/dev/null 2>&1 || true
    rm -f "$EN/default"   # Standardseite von nginx belegt sonst Port 80 für alle Namen
    reload_nginx
    echo '{"ok": true, "message": "nginx und certbot sind installiert, automatische Erneuerung ist an."}'
}

write_site() {   # write_site DOMAIN PORT DATEI
    cat > "$3" <<EOF
# N8 Crosslink – $1 (angelegt im Webinterface unter Domains & HTTPS, nicht von Hand ändern)
server {
    listen 80;
    listen [::]:80;
    server_name $1;
    client_max_body_size 16m;

    location / {
        proxy_pass http://127.0.0.1:$2;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 3600s;
    }
}
EOF
    chmod 644 "$3"
}

add() {
    local d="$1" mail="$2" port="$3" staging="${4:-}" f log rc
    dom_ok "$d"; [[ "$mail" =~ $MAIL_RE ]] || die "Ungültige E-Mail-Adresse"; port_ok "$port"
    [[ "$port" != 80 && "$port" != 443 ]] || die "N8 Crosslink lauscht selbst auf Port $port – erst unter Allgemein den Web-Port ändern (z. B. 8070)"
    have nginx && have certbot || die "nginx/certbot fehlen – zuerst „Benötigte Pakete installieren“"
    f="$(site_of "$d")"; [[ -n "$f" ]] || f="$AV/n8crosslink-$d"
    [[ -f "$f" ]] && cp -p "$f" "$f.bak"
    write_site "$d" "$port" "$f"
    ln -sf "$f" "$EN/$(basename "$f")"
    if ! nginx -t >/dev/null 2>&1; then
        log="$(nginx -t 2>&1 | tail -3)"
        if [[ -f "$f.bak" ]]; then mv -f "$f.bak" "$f"; else rm -f "$f" "$EN/$(basename "$f")"; fi
        die "nginx-Konfiguration ungültig – nichts geändert: $log"
    fi
    rm -f "$f.bak"
    reload_nginx
    log="$(certbot --nginx -d "$d" --cert-name "$d" -m "$mail" --agree-tos -n --redirect --keep-until-expiring \
           ${staging:+--staging} 2>&1)" && rc=0 || rc=$?
    reload_nginx
    python3 -c 'import json,sys; ok = sys.argv[1] == "0"; log = sys.argv[3].strip().splitlines()
msg = ("HTTPS aktiv: https://" + sys.argv[2]) if ok else ("Zertifikat nicht bekommen – die Domain ist über http:// erreichbar. " + (" ".join(l for l in log if "Detail" in l or "Error" in l or "error" in l)[-400:] or (log[-1] if log else "")))
print(json.dumps({"ok": ok, "message": msg, "log": "\n".join(log[-25:])}, ensure_ascii=False))' "$rc" "$d" "$log"
}

renew() {
    local d="$1" log rc
    dom_ok "$d"; have certbot || die "certbot fehlt"
    [[ -d "$LE/$d" ]] || die "Für $d gibt es noch kein Zertifikat"
    log="$(certbot renew --cert-name "$d" --force-renewal -n 2>&1)" && rc=0 || rc=$?
    reload_nginx
    python3 -c 'import json,sys; ok = sys.argv[1] == "0"; log = sys.argv[3].strip().splitlines()
print(json.dumps({"ok": ok, "message": ("Zertifikat für " + sys.argv[2] + " erneuert") if ok else ("Erneuern fehlgeschlagen: " + (log[-1] if log else "")), "log": "\n".join(log[-25:])}, ensure_ascii=False))' "$rc" "$d" "$log"
}

remove() {
    local d="$1" f
    dom_ok "$d"
    f="$(site_of "$d")"
    [[ -n "$f" ]] || die "$d wird hier nicht verwaltet"
    rm -f "$EN/$(basename "$f")" "$f" "$f.bak"
    have certbot && [[ -d "$LE/$d" ]] && certbot delete --cert-name "$d" -n >/dev/null 2>&1 || true
    reload_nginx
    python3 -c 'import json,sys; print(json.dumps({"ok": True, "message": sys.argv[1] + " entfernt (Weiterleitung und Zertifikat)"}, ensure_ascii=False))' "$d"
}

case "${1:-}" in
    status) port_ok "${2:-0}"; status "$2" ;;
    deps) deps ;;
    add) [[ $# -ge 4 ]] || die "add DOMAIN EMAIL PORT [staging]"; [[ -z "${5:-}" || "${5:-}" == staging ]] || die "unbekannte Option ${5}"
         add "$2" "$3" "$4" "${5:-}" ;;
    renew) [[ $# -eq 2 ]] || die "renew DOMAIN"; renew "$2" ;;
    remove) [[ $# -eq 2 ]] || die "remove DOMAIN"; remove "$2" ;;
    *) die "Aufruf: status PORT | deps | add DOMAIN EMAIL PORT [staging] | renew DOMAIN | remove DOMAIN" ;;
esac
