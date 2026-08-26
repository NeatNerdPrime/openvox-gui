#!/usr/bin/env bash
# Regression for GitHub #44: TLS installs must probe https://localhost:PORT/health.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL="$REPO_ROOT/install.sh"

fail() { echo "  FAIL  $*" >&2; exit 1; }
pass() { echo "  OK  $*"; }

[[ -f "$INSTALL" ]] || fail "missing $INSTALL"

if grep -nE 'curl -sf http://localhost:\$\{APP_PORT\}/health' "$INSTALL"; then
  fail "install.sh still probes plaintext http://localhost for /health"
fi
pass "no plaintext localhost /health curls in install.sh"

grep -q 'HEALTH_URL="${APP_SCHEME}://localhost:${APP_PORT}/health"' "$INSTALL" \
  || fail "HEALTH_URL is not derived from APP_SCHEME"
grep -q 'curl -skf "${HEALTH_URL}"' "$INSTALL" \
  || fail "probes do not use curl -skf \"\${HEALTH_URL}\""
pass "HEALTH_URL uses APP_SCHEME and curl -skf"

workdir="$(mktemp -d)"
http_pid=""
https_pid=""
cleanup() {
  { kill $http_pid $https_pid; wait; } >/dev/null 2>&1 || true
  rm -rf "$workdir"
}
trap cleanup EXIT

export PROBE_DIR="$workdir"

# Plain HTTP listener (one request).
python3 - <<'PY' &
import http.server, os
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def log_message(self, *a):
        return
httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
open(os.path.join(os.environ["PROBE_DIR"], "http.port"), "w").write(
    str(httpd.server_address[1])
)
httpd.serve_forever()
PY
http_pid=$!

openssl req -x509 -newkey rsa:2048 -keyout "$workdir/key.pem" -out "$workdir/cert.pem" \
  -days 1 -nodes -subj "/CN=localhost" >/dev/null 2>&1

# Self-signed HTTPS listener (one request).
python3 - <<'PY' &
import http.server, os, ssl
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def log_message(self, *a):
        return
httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(
    os.path.join(os.environ["PROBE_DIR"], "cert.pem"),
    os.path.join(os.environ["PROBE_DIR"], "key.pem"),
)
httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
open(os.path.join(os.environ["PROBE_DIR"], "https.port"), "w").write(
    str(httpd.server_address[1])
)
httpd.serve_forever()
PY
https_pid=$!

for _ in $(seq 1 50); do
  [[ -f "$workdir/http.port" && -f "$workdir/https.port" ]] && break
  sleep 0.05
done
[[ -f "$workdir/http.port" ]] || fail "HTTP test listener did not start"
[[ -f "$workdir/https.port" ]] || fail "HTTPS test listener did not start"

http_port="$(cat "$workdir/http.port")"
https_port="$(cat "$workdir/https.port")"

if curl -sf "http://127.0.0.1:${https_port}/health" >/dev/null 2>&1; then
  fail "plaintext curl unexpectedly succeeded against TLS listener"
fi
pass "old http:// probe fails against TLS (issue #44)"

if ! curl -skf "https://127.0.0.1:${https_port}/health" >/dev/null; then
  fail "curl -skf https:// did not succeed against TLS listener"
fi
pass "new https:// -skf probe succeeds against TLS"

if ! curl -skf "http://127.0.0.1:${http_port}/health" >/dev/null; then
  fail "curl -skf http:// failed against plaintext listener"
fi
pass "http:// -skf probe still succeeds without TLS"

echo "tests/shell/test_installer_health_probe: OK"
