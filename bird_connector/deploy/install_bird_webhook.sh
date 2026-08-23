#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="odoo-bird-webhook.service"
BIRD_CONF="/etc/odoo-bird-webhook.conf"
BIRD_LOG="/var/log/odoo/odoo-bird-webhook.log"
DEFAULT_PORT="8070"
MAIN_CONF=""
DB_NAME=""
DOMAIN=""
PORT="$DEFAULT_PORT"
ODOO_BIN=""
ODOO_USER=""
ODOO_GROUP=""
NGINX_SITE=""
SKIP_NGINX=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Bird Connector - Dedicated Webhook Installer

Usage:
  sudo bash install_bird_webhook.sh --db DATABASE [options]

Required on multi-database servers:
  --db NAME              Odoo database that owns the Bird webhook.

Optional:
  --domain DOMAIN        Public Odoo domain. Used to auto-detect the Nginx site.
  --main-conf PATH       Main Odoo config. Auto-detected when omitted.
  --odoo-bin PATH        Path to odoo-bin. Auto-detected when omitted.
  --user USER            Odoo service user. Auto-detected when omitted.
  --group GROUP          Odoo service group. Defaults to USER.
  --port PORT            Dedicated webhook HTTP port. Default: 8070.
  --nginx-site PATH      Exact Nginx site file to update.
  --skip-nginx           Configure Odoo/systemd only.
  --dry-run              Show planned actions without changing the server.
  -h, --help             Show this help.
EOF
}

log() { printf '\033[1;34m[Bird]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '+ '; printf '%q ' "$@"; printf '\n'
  else
    "$@"
  fi
}

backup_file() {
  local file="$1"
  [[ -e "$file" ]] || return 0
  local backup="${file}.bird-backup-$(date +%Y%m%d-%H%M%S)"
  run cp -a "$file" "$backup"
  log "Backup: $backup"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB_NAME="${2:-}"; shift 2 ;;
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --main-conf) MAIN_CONF="${2:-}"; shift 2 ;;
    --odoo-bin) ODOO_BIN="${2:-}"; shift 2 ;;
    --user) ODOO_USER="${2:-}"; shift 2 ;;
    --group) ODOO_GROUP="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    --nginx-site) NGINX_SITE="${2:-}"; shift 2 ;;
    --skip-nginx) SKIP_NGINX=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "Run this installer as root (sudo)."
[[ "$PORT" =~ ^[0-9]+$ ]] || die "Invalid port: $PORT"
(( PORT >= 1024 && PORT <= 65535 )) || die "Port must be between 1024 and 65535."

if [[ -z "$MAIN_CONF" ]]; then
  for c in /etc/odoo-server.conf /etc/odoo.conf /etc/odoo/odoo.conf; do
    if [[ -r "$c" ]]; then MAIN_CONF="$c"; break; fi
  done
fi
[[ -n "$MAIN_CONF" && -r "$MAIN_CONF" ]] || die "Cannot find a readable main Odoo config. Use --main-conf."

if [[ -z "$ODOO_USER" ]]; then
  ODOO_USER="$(ps -eo user=,args= | awk '/[o]doo-bin/ && $0 !~ /odoo-bird-webhook\.conf/ {print $1; exit}')"
  [[ -n "$ODOO_USER" ]] || ODOO_USER="odoo"
fi
[[ -n "$ODOO_GROUP" ]] || ODOO_GROUP="$ODOO_USER"
id "$ODOO_USER" >/dev/null 2>&1 || die "Odoo user does not exist: $ODOO_USER"

if [[ -z "$ODOO_BIN" ]]; then
  ODOO_BIN="$(ps -eo args= | sed -nE 's#.*((/[^ ]+)*/odoo-bin)( |$).*#\1#p' | head -n1 || true)"
fi
for c in "$ODOO_BIN" /odoo/odoo-server/odoo-bin /opt/odoo18/odoo-bin /opt/odoo/odoo-bin; do
  [[ -n "$c" && -x "$c" ]] && { ODOO_BIN="$c"; break; }
done
[[ -n "$ODOO_BIN" && -x "$ODOO_BIN" ]] || die "Cannot find executable odoo-bin. Use --odoo-bin."

if [[ -z "$DB_NAME" ]]; then
  DB_NAME="$(sed -nE 's/^[[:space:]]*dbfilter[[:space:]]*=[[:space:]]*\^?([A-Za-z0-9_.-]+)\$?[[:space:]]*$/\1/p' "$MAIN_CONF" | head -n1 || true)"
fi
[[ -n "$DB_NAME" ]] || die "Database cannot be safely inferred. Re-run with --db DATABASE."
[[ "$DB_NAME" =~ ^[A-Za-z0-9_.-]+$ ]] || die "Unsafe database name: $DB_NAME"

if ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${PORT}$"; then
  if ! systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    die "Port $PORT is already in use by another process. Stop it or choose --port."
  fi
fi

log "Main config : $MAIN_CONF"
log "Odoo binary : $ODOO_BIN"
log "Odoo user   : $ODOO_USER:$ODOO_GROUP"
log "Database    : $DB_NAME"
log "Webhook port: $PORT"

backup_file "$BIRD_CONF"
if [[ "$DRY_RUN" -eq 0 ]]; then
  cp "$MAIN_CONF" "$BIRD_CONF"
  python3 - "$BIRD_CONF" "$PORT" "$DB_NAME" "$BIRD_LOG" <<'PY'
from pathlib import Path
import re, sys
path, port, db, logfile = sys.argv[1:]
p = Path(path)
text = p.read_text(encoding="utf-8")
if not re.search(r"(?m)^\s*\[options\]\s*$", text):
    text = "[options]\n" + text

def set_opt(name, value):
    global text
    rx = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=.*$")
    line = f"{name} = {value}"
    if rx.search(text):
        text = rx.sub(line, text, count=1)
    else:
        m = re.search(r"(?m)^\s*\[options\]\s*$", text)
        at = m.end()
        text = text[:at] + "\n" + line + text[at:]

set_opt("http_port", port)
set_opt("dbfilter", f"^{db}$")
set_opt("list_db", "False")
set_opt("proxy_mode", "True")
set_opt("max_cron_threads", "0")
set_opt("logfile", logfile)
p.write_text(text.rstrip() + "\n", encoding="utf-8")
PY
  chown root:"$ODOO_GROUP" "$BIRD_CONF"
  chmod 640 "$BIRD_CONF"
fi
ok "Dedicated Odoo config prepared: $BIRD_CONF"

SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
backup_file "$SERVICE_PATH"
if [[ "$DRY_RUN" -eq 0 ]]; then
  cat >"$SERVICE_PATH" <<EOF
[Unit]
Description=Odoo Bird Webhook Instance
After=network.target
Wants=network.target

[Service]
Type=simple
User=$ODOO_USER
Group=$ODOO_GROUP
ExecStart=$ODOO_BIN -c $BIRD_CONF
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF
fi

run systemctl daemon-reload
run systemctl enable "$SERVICE_NAME"
ok "systemd service installed and enabled."

if [[ "$SKIP_NGINX" -eq 0 ]]; then
  command -v nginx >/dev/null 2>&1 || die "Nginx not found. Use --skip-nginx if another proxy is used."

  if [[ -z "$NGINX_SITE" && -n "$DOMAIN" ]]; then
    NGINX_SITE="$(grep -RslE "server_name[[:space:]].*${DOMAIN//./\\.}" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n1 || true)"
  fi

  if [[ -z "$NGINX_SITE" ]]; then
    warn "Nginx site could not be safely auto-detected; Nginx was left unchanged."
    warn "Re-run with --domain DOMAIN or --nginx-site PATH."
  else
    [[ -f "$NGINX_SITE" ]] || die "Nginx site not found: $NGINX_SITE"
    log "Nginx site  : $NGINX_SITE"
    backup_file "$NGINX_SITE"

    if ! grep -q "BIRD WEBHOOK MANAGED BLOCK" "$NGINX_SITE"; then
      if [[ "$DRY_RUN" -eq 0 ]]; then
        python3 - "$NGINX_SITE" "$PORT" "$DOMAIN" <<'PY'
from pathlib import Path
import re, sys
path, port, domain = sys.argv[1:]
p = Path(path)
text = p.read_text(encoding="utf-8")
block = f"""
    # BEGIN BIRD WEBHOOK MANAGED BLOCK
    location ^~ /bird/webhook/ {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_redirect off;
    }}
    # END BIRD WEBHOOK MANAGED BLOCK

"""
starts = [m.start() for m in re.finditer(r"(?m)^\s*server\s*\{", text)]
chosen = None
for start in starts:
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        continue
    chunk = text[start:end+1]
    if domain and not re.search(rf"\bserver_name\b[^;]*\b{re.escape(domain)}\b", chunk):
        continue
    if "listen 443" in chunk or "ssl" in chunk:
        chosen = (start, end, chunk)
        break
    if chosen is None:
        chosen = (start, end, chunk)
if chosen is None:
    raise SystemExit("Could not safely identify an Nginx server block.")
start, end, chunk = chosen
loc = re.search(r"(?m)^\s*location\s+/\s*\{", chunk)
insert = start + loc.start() if loc else end
text = text[:insert] + block + text[insert:]
p.write_text(text, encoding="utf-8")
PY
      fi
    else
      log "Nginx Bird managed block already exists; leaving it unchanged."
    fi
    run nginx -t
    run systemctl reload nginx
    ok "Nginx routing configured."
  fi
fi

run install -d -o "$ODOO_USER" -g "$ODOO_GROUP" /var/log/odoo
if [[ "$DRY_RUN" -eq 0 ]]; then
  touch "$BIRD_LOG"
  chown "$ODOO_USER":"$ODOO_GROUP" "$BIRD_LOG"
fi

run systemctl restart "$SERVICE_NAME"

if [[ "$DRY_RUN" -eq 0 ]]; then
  for _ in {1..20}; do
    if systemctl is-active --quiet "$SERVICE_NAME" && ss -lnt | awk '{print $4}' | grep -Eq "[:.]${PORT}$"; then
      break
    fi
    sleep 1
  done
  systemctl is-active --quiet "$SERVICE_NAME" || {
    systemctl status "$SERVICE_NAME" --no-pager -l || true
    tail -n 80 "$BIRD_LOG" || true
    die "Bird webhook service failed to start."
  }
  ss -lnt | awk '{print $4}' | grep -Eq "[:.]${PORT}$" || die "Port $PORT is not listening."
fi

ok "Bird webhook instance is active on port $PORT."
ok "Cron execution is disabled on this instance (max_cron_threads = 0)."
log "Final validation: send a real WhatsApp message and confirm /bird/webhook/... returns HTTP 200."
