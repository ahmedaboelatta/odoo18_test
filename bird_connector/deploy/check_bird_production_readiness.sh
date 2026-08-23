#!/usr/bin/env bash
set -Eeuo pipefail

MAIN_CONF=""
MAIN_SERVICE=""
BIRD_SERVICE="odoo-bird-webhook.service"
BIRD_CONF="/etc/odoo-bird-webhook.conf"
DOMAIN=""
NGINX_SITE=""
STRICT=0

PASS=0
WARN=0
FAIL=0

usage() {
  cat <<'USAGE'
Bird Connector - Production Readiness Check

Usage:
  sudo bash check_bird_production_readiness.sh [options]

Options:
  --main-conf PATH       Main Odoo config (auto-detected when omitted)
  --main-service NAME    Main Odoo native systemd service (auto-detected when possible)
  --bird-service NAME    Bird webhook service (default: odoo-bird-webhook.service)
  --bird-conf PATH       Bird webhook config (default: /etc/odoo-bird-webhook.conf)
  --domain DOMAIN        Public domain, used for Nginx routing validation
  --nginx-site PATH      Exact Nginx site to inspect
  --strict               Treat warnings as a non-zero result
  -h, --help             Show this help
USAGE
}

p() { printf '\033[1;32mPASS\033[0m  %-24s %s\n' "$1" "$2"; PASS=$((PASS+1)); }
w() { printf '\033[1;33mWARN\033[0m  %-24s %s\n' "$1" "$2"; WARN=$((WARN+1)); }
f() { printf '\033[1;31mFAIL\033[0m  %-24s %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --main-conf) MAIN_CONF="${2:-}"; shift 2 ;;
    --main-service) MAIN_SERVICE="${2:-}"; shift 2 ;;
    --bird-service) BIRD_SERVICE="${2:-}"; shift 2 ;;
    --bird-conf) BIRD_CONF="${2:-}"; shift 2 ;;
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --nginx-site) NGINX_SITE="${2:-}"; shift 2 ;;
    --strict) STRICT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$MAIN_CONF" ]]; then
  for c in /etc/odoo-server.conf /etc/odoo.conf /etc/odoo/odoo.conf; do
    [[ -r "$c" ]] && { MAIN_CONF="$c"; break; }
  done
fi

if [[ -z "$MAIN_CONF" || ! -r "$MAIN_CONF" ]]; then
  f "Main config" "Cannot find readable main Odoo config. Use --main-conf."
  MAIN_PORT="8069"
else
  p "Main config" "$MAIN_CONF"
  MAIN_PORT="$(sed -nE 's/^[[:space:]]*(http_port|xmlrpc_port)[[:space:]]*=[[:space:]]*([0-9]+).*$/\2/p' "$MAIN_CONF" | head -n1)"
  [[ -n "$MAIN_PORT" ]] || MAIN_PORT="8069"
fi

# Main Odoo process / listener
mapfile -t MAIN_PIDS < <(ps -eo pid=,args= | awk -v bc="$BIRD_CONF" '/[o]doo-bin/ && index($0,bc)==0 {print $1}')
if (( ${#MAIN_PIDS[@]} == 1 )); then
  MAIN_PID="${MAIN_PIDS[0]}"
  p "Main process" "Exactly one main Odoo process (PID $MAIN_PID)"
elif (( ${#MAIN_PIDS[@]} == 0 )); then
  MAIN_PID=""
  f "Main process" "No main Odoo process found"
else
  MAIN_PID="${MAIN_PIDS[0]}"
  f "Main process" "Multiple main Odoo processes found: ${MAIN_PIDS[*]}"
fi

if ss -lntp 2>/dev/null | grep -Eq ":${MAIN_PORT}[[:space:]].*python"; then
  p "Main port" "$MAIN_PORT is listening"
else
  f "Main port" "$MAIN_PORT is not listening"
fi

# Detect service from cgroup if possible.
if [[ -z "$MAIN_SERVICE" && -n "${MAIN_PID:-}" && -r "/proc/$MAIN_PID/cgroup" ]]; then
  MAIN_SERVICE="$(sed -nE 's#.*system\.slice/([^/]+\.service).*#\1#p' "/proc/$MAIN_PID/cgroup" | head -n1)"
fi

if [[ -n "$MAIN_SERVICE" ]]; then
  if systemctl is-active --quiet "$MAIN_SERVICE" 2>/dev/null; then
    p "Main service active" "$MAIN_SERVICE"
  else
    f "Main service active" "$MAIN_SERVICE is not active"
  fi
  if systemctl is-enabled --quiet "$MAIN_SERVICE" 2>/dev/null; then
    p "Main service boot" "$MAIN_SERVICE is enabled"
  else
    w "Main service boot" "$MAIN_SERVICE is not enabled"
  fi
  load_state="$(systemctl show "$MAIN_SERVICE" -p LoadState --value 2>/dev/null || true)"
  fragment="$(systemctl show "$MAIN_SERVICE" -p FragmentPath --value 2>/dev/null || true)"
  if [[ "$load_state" == "loaded" && "$fragment" == /etc/systemd/system/* ]]; then
    p "Main service type" "Native systemd unit: $fragment"
  else
    w "Main service type" "Service is not a native /etc/systemd/system unit (${fragment:-unknown})"
  fi
else
  f "Main service" "Could not associate main Odoo PID with a systemd service. Do not run production Odoo from nohup/foreground."
fi

# Detect enabled legacy Odoo services that can collide with the main port.
while read -r unit state _; do
  [[ -z "$unit" ]] && continue
  [[ "$unit" == "$MAIN_SERVICE" || "$unit" == "$BIRD_SERVICE" ]] && continue
  if [[ "$unit" == *odoo* && "$state" == "enabled" ]]; then
    w "Legacy/extra service" "$unit is enabled; verify it cannot start another Odoo on port $MAIN_PORT"
  fi
done < <(systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '$1 ~ /odoo/ {print $1,$2,$3}')

# Bird service
if systemctl is-active --quiet "$BIRD_SERVICE" 2>/dev/null; then
  p "Bird service active" "$BIRD_SERVICE"
else
  f "Bird service active" "$BIRD_SERVICE is not active"
fi
if systemctl is-enabled --quiet "$BIRD_SERVICE" 2>/dev/null; then
  p "Bird service boot" "$BIRD_SERVICE is enabled"
else
  f "Bird service boot" "$BIRD_SERVICE is not enabled"
fi

if [[ -r "$BIRD_CONF" ]]; then
  p "Bird config" "$BIRD_CONF"
  BIRD_PORT="$(sed -nE 's/^[[:space:]]*(http_port|xmlrpc_port)[[:space:]]*=[[:space:]]*([0-9]+).*$/\2/p' "$BIRD_CONF" | head -n1)"
  [[ -n "$BIRD_PORT" ]] || BIRD_PORT="8070"

  conf_bool() {
    local key="$1" expected="$2" actual
    actual="$(sed -nE "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*([^#;[:space:]]+).*$/\\1/p" "$BIRD_CONF" | tail -n1 | tr '[:upper:]' '[:lower:]')"
    if [[ "$actual" == "${expected,,}" ]]; then
      p "$key" "$actual"
    else
      f "$key" "expected $expected, found ${actual:-missing}"
    fi
  }
  conf_bool "list_db" "false"
  conf_bool "proxy_mode" "true"
  zero_cron="$(sed -nE 's/^[[:space:]]*max_cron_threads[[:space:]]*=[[:space:]]*([0-9]+).*$/\1/p' "$BIRD_CONF" | tail -n1)"
  if [[ "$zero_cron" == "0" ]]; then
    p "Cron isolation" "max_cron_threads = 0"
  else
    f "Cron isolation" "max_cron_threads must be 0 (found ${zero_cron:-missing})"
  fi
  dbfilter="$(sed -nE 's/^[[:space:]]*dbfilter[[:space:]]*=[[:space:]]*(.+)$/\1/p' "$BIRD_CONF" | tail -n1)"
  if [[ -n "$dbfilter" ]]; then
    p "Database routing" "dbfilter = $dbfilter"
  else
    w "Database routing" "No dbfilter in dedicated Bird config"
  fi
else
  BIRD_PORT="8070"
  f "Bird config" "$BIRD_CONF is not readable"
fi

if [[ "$BIRD_PORT" == "$MAIN_PORT" ]]; then
  f "Port isolation" "Main and Bird both use port $MAIN_PORT"
else
  p "Port isolation" "Main=$MAIN_PORT, Bird=$BIRD_PORT"
fi

if ss -lntp 2>/dev/null | grep -Eq ":${BIRD_PORT}[[:space:]].*python"; then
  p "Bird port" "$BIRD_PORT is listening"
else
  f "Bird port" "$BIRD_PORT is not listening"
fi

# Local health checks. Odoo commonly returns 303 on /web/login when DB selection/session redirects.
http_check() {
  local name="$1" port="$2" code
  code="$(curl -sS -o /dev/null -m 10 -w '%{http_code}' "http://127.0.0.1:${port}/web/login" 2>/dev/null || true)"
  case "$code" in
    200|301|302|303) p "$name" "HTTP $code" ;;
    *) f "$name" "HTTP ${code:-no response}" ;;
  esac
}
http_check "Main HTTP" "$MAIN_PORT"
http_check "Bird HTTP" "$BIRD_PORT"

# Nginx validation
if command -v nginx >/dev/null 2>&1; then
  if nginx -t >/dev/null 2>&1; then p "Nginx syntax" "nginx -t successful"; else f "Nginx syntax" "nginx -t failed"; fi

  if [[ -z "$NGINX_SITE" && -n "$DOMAIN" ]]; then
    NGINX_SITE="$(grep -RslE "server_name[[:space:]].*${DOMAIN//./\\.}" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n1 || true)"
  fi
  if [[ -z "$NGINX_SITE" ]]; then
    NGINX_SITE="$(grep -RslE 'location( \^~)?[[:space:]]+/bird/webhook/' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n1 || true)"
  fi

  if [[ -n "$NGINX_SITE" && -r "$NGINX_SITE" ]]; then
    p "Nginx site" "$NGINX_SITE"
    if grep -A20 -E 'location( \^~)?[[:space:]]+/bird/webhook/' "$NGINX_SITE" | grep -qE "proxy_pass[[:space:]]+http://127\.0\.0\.1:${BIRD_PORT}"; then
      p "Webhook proxy route" "/bird/webhook/ -> 127.0.0.1:$BIRD_PORT"
    else
      f "Webhook proxy route" "Could not prove /bird/webhook/ routes to 127.0.0.1:$BIRD_PORT"
    fi
  else
    w "Nginx site" "Could not auto-detect the site. Use --domain or --nginx-site for route validation."
  fi
else
  w "Nginx" "nginx command not found; external proxy may be in use"
fi

printf '\n===============================================\n'
printf 'Bird Connector Production Readiness Summary\n'
printf '===============================================\n'
printf 'PASS: %d   WARN: %d   FAIL: %d\n' "$PASS" "$WARN" "$FAIL"

if (( FAIL > 0 )); then
  printf '\033[1;31mNOT READY FOR PRODUCTION\033[0m\n'
  exit 1
fi
if (( WARN > 0 )); then
  printf '\033[1;33mREADY WITH RECOMMENDATIONS\033[0m\n'
  (( STRICT == 1 )) && exit 2 || exit 0
fi
printf '\033[1;32mREADY FOR PRODUCTION\033[0m\n'
