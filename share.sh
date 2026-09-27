#!/usr/bin/env bash
#
# share.sh — put APEX on a public URL from this machine.
#
#   ./share.sh
#
# Starts the API, builds and serves the frontend, opens a Cloudflare
# tunnel, and prints a link you can send someone. Ctrl+C stops everything.
#
# This is for "click around while I watch", not for leaving running. The
# link dies when this machine sleeps and the URL changes every run. For a
# stable link see DEPLOYMENT.md.

set -euo pipefail

cd "$(dirname "$0")"
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"
LOGS="$ROOT/.share-logs"
mkdir -p "$LOGS"

API_PORT=8000
WEB_PORT=3000

# cloudflared resolves "localhost" to IPv6 ::1, but Next binds IPv4 only —
# so the origin must be given explicitly as 127.0.0.1 or every request from
# the internet returns a Cloudflare 502.
API_ORIGIN="http://127.0.0.1:$API_PORT"
WEB_ORIGIN="http://127.0.0.1:$WEB_PORT"

step()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail()  { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }

cleanup() {
  printf '\n\nStopping…\n'
  # Kill our own children; never a blanket pkill, which would also take out
  # anything else the user happens to be running.
  for pid in ${TUNNEL_PID:-} ${WEB_PID:-} ${API_PID:-}; do
    kill "$pid" 2>/dev/null || true
  done
  printf 'Stopped. The link is now dead.\n'
}
trap cleanup EXIT INT TERM

[ -x "$PY" ] || fail "No virtualenv at .venv — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
command -v cloudflared >/dev/null || fail "cloudflared not installed — run: brew install cloudflared"

step "Freeing ports $API_PORT and $WEB_PORT"
for port in $API_PORT $WEB_PORT; do
  lsof -ti:"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
done
sleep 1
ok "ports clear"

step "Starting the API"
# No APEX_SECRET_KEY here on purpose: in development the app generates one
# and persists it to .apex_dev_secret, so accounts stay signed in across
# restarts of this script.
"$PY" -m uvicorn api.main:app --host 0.0.0.0 --port "$API_PORT" \
  --log-level warning > "$LOGS/api.log" 2>&1 &
API_PID=$!

for _ in $(seq 1 30); do
  curl -sf -m 2 "$API_ORIGIN/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf -m 5 "$API_ORIGIN/health" >/dev/null || fail "API did not start — see $LOGS/api.log"
ok "API on $API_PORT"

step "Building the frontend (production build, not dev)"
( cd frontend && APEX_API_ORIGIN="$API_ORIGIN" npm run build ) > "$LOGS/build.log" 2>&1 \
  || fail "Build failed — see $LOGS/build.log"
ok "built"

step "Serving the frontend"
( cd frontend && APEX_API_ORIGIN="$API_ORIGIN" \
    npx next start --hostname 0.0.0.0 --port "$WEB_PORT" ) > "$LOGS/web.log" 2>&1 &
WEB_PID=$!

for _ in $(seq 1 40); do
  curl -sf -m 2 "$WEB_ORIGIN" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf -m 5 "$WEB_ORIGIN" >/dev/null || fail "Frontend did not start — see $LOGS/web.log"
ok "web on $WEB_PORT"

step "Opening the tunnel"
cloudflared tunnel --url "$WEB_ORIGIN" --no-autoupdate > "$LOGS/tunnel.log" 2>&1 &
TUNNEL_PID=$!

URL=""
for _ in $(seq 1 40); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGS/tunnel.log" 2>/dev/null | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || fail "No tunnel URL — see $LOGS/tunnel.log"

# Prove it end to end from outside before handing over a link. Checking
# only the local port is what previously produced a URL that 502'd for
# everyone else.
#
# Cloudflare needs a few seconds to publish the hostname after printing it,
# so this retries rather than judging on the first attempt.
step "Verifying from the public internet"
code=000
for _ in $(seq 1 20); do
  code=$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null) || code=000
  [ "$code" = "200" ] && break
  sleep 3
done
[ "$code" = "200" ] || fail "Tunnel returned $code after 60s — see $LOGS/tunnel.log"
ok "page loads ($code)"

curl -sf -m 25 "$URL/api/health" >/dev/null || fail "API unreachable through the tunnel"
ok "API reachable through the tunnel"

cat <<EOF

────────────────────────────────────────────────────────────
  $URL
────────────────────────────────────────────────────────────

  Your tester creates their own account on the sign-in screen.

  This link lives only while this window is open and this
  machine is awake. It changes every run.

  Ctrl+C to stop.

EOF

wait
