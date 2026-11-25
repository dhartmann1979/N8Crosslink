#!/usr/bin/env bash
# N8 Crosslink – Domains & HTTPS (Let's Encrypt) für das Webinterface.
#
# Läuft als root über sudo (/etc/sudoers.d/n8crosslink erlaubt nur dieses Skript). Jede Eingabe wird hier geprüft:
#   n8x-certs.sh status PORT HTTP HTTPS                 Zustand als JSON (nginx, certbot, Domains, Zertifikate, Belegung der Ports)
#   n8x-certs.sh deps                                   nginx und certbot installieren, Erneuerungs-Timer an
#   n8x-certs.sh add DOMAIN EMAIL PORT HTTP HTTPS [staging]
#                                                      nginx: DOMAIN auf HTTP/HTTPS → 127.0.0.1:PORT, Zertifikat holen (webroot)
#   n8x-certs.sh ports PORT HTTP HTTPS                  alle Domains auf neue Ports umschreiben (Web-Port, HTTP-, HTTPS-Port)
#   n8x-certs.sh renew DOMAIN                           Zertifikat jetzt erneuern (auch wenn es noch nicht fällig ist)
#   n8x-certs.sh remove DOMAIN                          Weiterleitung und Zertifikat entfernen
#
# PORT = Web-Port von N8 Crosslink (nginx leitet dorthin), HTTP = Port für http:// und die Let's-Encrypt-Prüfung (Standard 80),
# HTTPS = Port für https:// (Standard 443). Let's Encrypt prüft immer über Port 80 aus dem Internet – ein anderer HTTP-Port
# geht nur mit Portweiterleitung im Router (außen 80 → innen HTTP).
#
# Dateien: /etc/nginx/sites-available/n8crosslink-<domain> (+ Link in sites-enabled), Prüf-Dateien in /var/www/n8crosslink-acme,
# Zertifikate von certbot unter /etc/letsencrypt/live/<domain>/. Die Seite des alten Installers (sites-available/n8crosslink) wird
# erkannt und beim nächsten Schreiben in das neue Format übernommen. Erneuert wird automatisch über den certbot-Timer; danach lädt
# nginx die Zertifikate neu (deploy-hook).
set -euo pipefail
export LC_ALL=C
AV=/etc/nginx/sites-available
EN=/etc/nginx/sites-enabled
LE=/etc/letsencrypt/live
WEBROOT=/var/www/n8crosslink-acme
DOM_RE='^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$'
MAIL_RE='^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$'
HOOK="systemctl reload nginx || nginx -s reload"

die() { python3 -c 'import json,sys; print(json.dumps({"ok": False, "message": sys.argv[1]}, ensure_ascii=False))' "$1"; exit 1; }
[[ $EUID -eq 0 ]] || die "nur als root (über sudo)"
# Aus dem Webinterface kommt der Aufruf aus der Sandbox des Dienstes (ProtectSystem=full: /etc und /usr schreibgeschützt –
# das erbt auch sudo). Dann als eigener kurzlebiger systemd-Dienst außerhalb der Sandbox neu starten; Ausgabe und
# Rückgabewert kommen über --pipe/--wait zurück.
if [[ -z "${N8X_UNSANDBOXED:-}" && ! -w /etc ]]; then
    command -v systemd-run >/dev/null 2>&1 || die "/etc ist schreibgeschützt (Dienst-Sandbox) und systemd-run fehlt"
    exec systemd-run --quiet --wait --pipe --collect --service-type=exec -p "Description=N8 Crosslink – Domains & HTTPS ($1)" \
        --setenv=N8X_UNSANDBOXED=1 -- "$(readlink -f "${BASH_SOURCE[0]}")" "$@"
fi
dom_ok() { [[ ${#1} -le 253 && "$1" =~ $DOM_RE ]] || die "Ungültige Domain: $1"; }
port_ok() { [[ "$1" =~ ^[0-9]{1,5}$ && "$1" -ge 1 && "$1" -le 65535 ]] || die "Ungültiger Port: $1"; }
have() { command -v "$1" >/dev/null 2>&1; }
reload_nginx() { nginx -t >/dev/null 2>&1 || return 0; systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null || true; }
# Löschen nur über feste Pfade: Name der Seite prüfen, dann /etc/nginx/… ausschreiben
site_name_ok() { [[ "$1" == n8crosslink || "$1" =~ ^n8crosslink-[a-z0-9.-]+$ ]]; }
drop_site() {   # drop_site NAME – Seite, Link und Sicherung entfernen
    site_name_ok "$1" || die "unerwarteter Dateiname: $1"
    rm -f "/etc/nginx/sites-enabled/$1" "/etc/nginx/sites-available/$1" "/etc/nginx/sites-available/$1.bak"
}

site_of() {   # Name der Seite, in der die Domain steht (eigene oder die des alten Installers), sonst leer
    local d="$1" n re="${1//./\\.}"
    for n in "n8crosslink-$d" n8crosslink; do
        [[ -f "$AV/$n" ]] && grep -Eq "server_name[^;]*[[:space:]]$re([[:space:];]|$)" "$AV/$n" && { echo "$n"; return 0; }
    done
    return 0
}

status() {
    local port="$1" http="$2" https="$3"
    python3 - "$port" "$http" "$https" <<'PY'
import glob, json, os, re, shutil, subprocess, sys, time
port, http_port, https_port = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
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
            days = int((int(ts) - time.time()) // 86400)
    return {"expires": end.group(1).strip() if end else "", "days": days, "issuer": (iss.group(1).strip() if iss else ""),
            "staging": "STAGING" in out.upper()}
sites, seen = [], set()
for f in sorted(glob.glob("/etc/nginx/sites-available/n8crosslink*")):
    if f.endswith((".bak", ".tmp")):
        continue
    txt = open(f, encoding="utf-8", errors="replace").read()
    names = sorted({n for m in re.findall(r"server_name\s+([^;]+);", txt) for n in m.split() if n not in ("_", "localhost")})
    up = re.search(r"proxy_pass\s+http://127\.0\.0\.1:(\d+)", txt)
    lp = sorted({int(x) for x in re.findall(r"listen\s+(?:\[::\]:)?(\d+)", txt)})
    enabled = os.path.exists(f.replace("sites-available", "sites-enabled"))
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        c = cert(n)
        upstream = int(up.group(1)) if up else None
        sites.append({"domain": n, "file": f, "legacy": f.endswith("/n8crosslink"), "enabled": enabled, "upstream": upstream,
                      "listen": lp, "https": "ssl_certificate" in txt and c is not None, "cert": c,
                      "ports_ok": upstream == port and http_port in lp and (c is None or https_port in lp)})
listen = sh("ss", "-ltnpH")
def who(p):
    for l in listen.splitlines():
        if re.search(rf":{p}\s", l):
            m = re.search(r'users:\(\("([^"]+)"', l)
            return m.group(1) if m else "belegt"
    return ""
timer = sh("systemctl", "is-enabled", "certbot.timer").strip() == "enabled" or os.path.exists("/etc/cron.d/certbot")
print(json.dumps({"ok": True, "nginx": bool(shutil.which("nginx")), "certbot": bool(shutil.which("certbot")),
                  "renew_timer": timer, "port80": who(http_port), "port443": who(https_port), "web_port": port,
                  "http_port": http_port, "https_port": https_port,
                  "portal": os.path.exists("/etc/nginx/sites-available/hobbyradioportal") or os.path.isdir("/opt/hobbyradioportal"),
                  "sites": sites}, ensure_ascii=False))
PY
}

deps() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null 2>&1 || true
    apt-get install -y -qq nginx certbot >/dev/null 2>&1 || die "Pakete nicht installierbar (apt-get install nginx certbot)"
    systemctl enable --now nginx >/dev/null 2>&1 || true
    systemctl enable --now certbot.timer >/dev/null 2>&1 || true
    rm -f /etc/nginx/sites-enabled/default   # Standardseite von nginx belegt sonst Port 80 für alle Namen
    reload_nginx
    echo '{"ok": true, "message": "nginx und certbot sind installiert, automatische Erneuerung ist an."}'
}

write_site() {   # write_site DOMAIN PORT HTTP HTTPS DATEI – mit HTTPS-Block, sobald ein Zertifikat da ist
    local d="$1" port="$2" http="$3" https="$4" f="$5" redir
    if [[ "$https" == 443 ]]; then redir='https://$host$request_uri'; else redir="https://\$host:$https\$request_uri"; fi
    install -d -m 755 "$WEBROOT"
    {
        echo "# N8 Crosslink – $d (angelegt im Webinterface unter Domains & HTTPS, nicht von Hand ändern)"
        echo "# n8x: port=$port http=$http https=$https"
        echo "server {"
        echo "    listen $http;"
        echo "    listen [::]:$http;"
        echo "    server_name $d;"
        echo "    location ^~ /.well-known/acme-challenge/ { root $WEBROOT; default_type text/plain; }"
        if [[ -f "$LE/$d/fullchain.pem" ]]; then
            echo "    location / { return 301 $redir; }"
            echo "}"
            echo "server {"
            echo "    listen $https ssl;"
            echo "    listen [::]:$https ssl;"
            echo "    http2 on;"
            echo "    server_name $d;"
            echo "    ssl_certificate     $LE/$d/fullchain.pem;"
            echo "    ssl_certificate_key $LE/$d/privkey.pem;"
            echo "    ssl_protocols TLSv1.2 TLSv1.3;"
            echo '    add_header Strict-Transport-Security "max-age=31536000" always;'
        fi
        echo "    client_max_body_size 16m;"
        echo "    location / {"
        echo "        proxy_pass http://127.0.0.1:$port;"
        echo "        proxy_http_version 1.1;"
        echo '        proxy_set_header Upgrade $http_upgrade;'
        echo '        proxy_set_header Connection "upgrade";'
        echo '        proxy_set_header Host $host;'
        echo '        proxy_set_header X-Real-IP $remote_addr;'
        echo '        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;'
        echo '        proxy_set_header X-Forwarded-Proto $scheme;'
        echo "        proxy_read_timeout 3600s;"
        echo "    }"
        echo "}"
    } > "$f"
    chmod 644 "$f"
}

apply_site() {   # apply_site DOMAIN PORT HTTP HTTPS – schreiben, prüfen, bei Fehler alten Stand zurück
    local d="$1" old new log
    old="$(site_of "$d")"; new="n8crosslink-$d"
    site_name_ok "$new" || die "Ungültige Domain: $d"
    [[ -n "$old" ]] && cp -p "$AV/$old" "$AV/$old.bak"
    write_site "$d" "$2" "$3" "$4" "$AV/$new.tmp"
    mv -f "$AV/$new.tmp" "$AV/$new"
    # Seite des alten Installers: nicht mehr einbinden (sie bleibt als Sicherung liegen, bis alles geklappt hat)
    [[ "$old" == n8crosslink ]] && rm -f /etc/nginx/sites-enabled/n8crosslink
    ln -sf "$AV/$new" "$EN/$new"
    if ! nginx -t >/dev/null 2>&1; then
        log="$(nginx -t 2>&1 | tail -3)"
        if [[ -n "$old" ]]; then
            [[ "$old" == "$new" ]] || drop_site "$new"
            mv -f "$AV/$old.bak" "$AV/$old"; ln -sf "$AV/$old" "$EN/$old"
        else
            drop_site "$new"
        fi
        reload_nginx
        die "nginx-Konfiguration für $d ungültig – nichts geändert: $log"
    fi
    if [[ -n "$old" ]]; then
        rm -f "/etc/nginx/sites-available/$old.bak"
        [[ "$old" == n8crosslink ]] && mv -f "$AV/n8crosslink" "$AV/n8crosslink.bak"
    fi
    reload_nginx
}

add() {
    local d="$1" mail="$2" port="$3" http="$4" https="$5" staging="${6:-}" log rc
    dom_ok "$d"; [[ "$mail" =~ $MAIL_RE ]] || die "Ungültige E-Mail-Adresse"; port_ok "$port"; port_ok "$http"; port_ok "$https"
    [[ "$port" != "$http" && "$port" != "$https" ]] || die "N8 Crosslink lauscht selbst auf Port $port – erst den Web-Port oder die nginx-Ports ändern (Seite Ports)"
    [[ "$http" != "$https" ]] || die "HTTP- und HTTPS-Port müssen verschieden sein"
    have nginx && have certbot || die "nginx/certbot fehlen – zuerst „Benötigte Pakete installieren“"
    apply_site "$d" "$port" "$http" "$https"
    log="$(certbot certonly --webroot -w "$WEBROOT" -d "$d" --cert-name "$d" -m "$mail" --agree-tos -n --keep-until-expiring \
           --deploy-hook "$HOOK" ${staging:+--staging} 2>&1)" && rc=0 || rc=$?
    [[ $rc == 0 ]] && apply_site "$d" "$port" "$http" "$https"     # jetzt mit HTTPS-Block
    python3 -c 'import json,sys; ok = sys.argv[1] == "0"; log = sys.argv[3].strip().splitlines(); hp = sys.argv[4]
url = "https://" + sys.argv[2] + ("" if hp == "443" else ":" + hp)
msg = ("HTTPS aktiv: " + url) if ok else ("Zertifikat nicht bekommen – die Domain ist über http:// erreichbar. " + (" ".join(l for l in log if "Detail" in l or "Error" in l or "error" in l)[-400:] or (log[-1] if log else "")))
print(json.dumps({"ok": ok, "message": msg, "log": "\n".join(log[-25:])}, ensure_ascii=False))' "$rc" "$d" "$log" "$https"
}

ports() {   # alle verwalteten Domains auf neue Ports umschreiben
    local port="$1" http="$2" https="$3" f d done=""
    port_ok "$port"; port_ok "$http"; port_ok "$https"
    [[ "$port" != "$http" && "$port" != "$https" && "$http" != "$https" ]] || die "Web-Port, HTTP- und HTTPS-Port müssen verschieden sein"
    have nginx || die "nginx ist nicht installiert"
    for f in "$AV"/n8crosslink "$AV"/n8crosslink-*; do
        [[ -f "$f" && "$f" != *.bak && "$f" != *.tmp ]] || continue
        for d in $(awk '/server_name/{for(i=2;i<=NF;i++){gsub(";","",$i); print $i}}' "$f" | sort -u); do
            [[ " $done " == *" $d "* ]] && continue
            [[ ${#d} -le 253 && "$d" =~ $DOM_RE ]] || continue
            apply_site "$d" "$port" "$http" "$https"; done="$done $d"
        done
    done
    python3 -c 'import json,sys; d = sys.argv[1].split(); print(json.dumps({"ok": True, "domains": d, "message": (str(len(d)) + " Domain(s) auf HTTP " + sys.argv[2] + " / HTTPS " + sys.argv[3] + " → 127.0.0.1:" + sys.argv[4] + " umgestellt") if d else "Keine Domains – nichts umzustellen"}, ensure_ascii=False))' "$done" "$http" "$https" "$port"
}

renew() {
    local d="$1" log rc
    dom_ok "$d"; have certbot || die "certbot fehlt"
    [[ -d "$LE/$d" ]] || die "Für $d gibt es noch kein Zertifikat"
    log="$(certbot renew --cert-name "$d" --force-renewal -n --deploy-hook "$HOOK" 2>&1)" && rc=0 || rc=$?
    reload_nginx
    python3 -c 'import json,sys; ok = sys.argv[1] == "0"; log = sys.argv[3].strip().splitlines()
print(json.dumps({"ok": ok, "message": ("Zertifikat für " + sys.argv[2] + " erneuert") if ok else ("Erneuern fehlgeschlagen: " + (log[-1] if log else "")), "log": "\n".join(log[-25:])}, ensure_ascii=False))' "$rc" "$d" "$log"
}

remove() {
    local d="$1" n
    dom_ok "$d"
    n="$(site_of "$d")"
    [[ -n "$n" ]] || die "$d wird hier nicht verwaltet"
    drop_site "$n"
    if have certbot && [[ -d "$LE/$d" ]]; then certbot delete --cert-name "$d" -n >/dev/null 2>&1 || true; fi
    reload_nginx
    python3 -c 'import json,sys; print(json.dumps({"ok": True, "message": sys.argv[1] + " entfernt (Weiterleitung und Zertifikat)"}, ensure_ascii=False))' "$d"
}

case "${1:-}" in
    status) port_ok "${2:-0}"; port_ok "${3:-80}"; port_ok "${4:-443}"; status "$2" "${3:-80}" "${4:-443}" ;;
    deps) deps ;;
    add) [[ $# -ge 6 ]] || die "add DOMAIN EMAIL PORT HTTP HTTPS [staging]"; [[ -z "${7:-}" || "${7:-}" == staging ]] || die "unbekannte Option ${7}"
         add "$2" "$3" "$4" "$5" "$6" "${7:-}" ;;
    ports) [[ $# -eq 4 ]] || die "ports PORT HTTP HTTPS"; ports "$2" "$3" "$4" ;;
    renew) [[ $# -eq 2 ]] || die "renew DOMAIN"; renew "$2" ;;
    remove) [[ $# -eq 2 ]] || die "remove DOMAIN"; remove "$2" ;;
    *) die "Aufruf: status PORT HTTP HTTPS | deps | add DOMAIN EMAIL PORT HTTP HTTPS [staging] | ports PORT HTTP HTTPS | renew DOMAIN | remove DOMAIN" ;;
esac
