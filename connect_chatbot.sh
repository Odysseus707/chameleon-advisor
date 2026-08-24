#!/usr/bin/env bash
# connect_chatbot.sh — reliable local access to the hosted Streamlit chatbot.
#
# The app (RAG-docs-chameleon/web_rag.py) runs on the Chameleon node — either as
# the systemd service `rag-app` or as a bare nohup'd streamlit process, which is
# how it is currently deployed — and listens on port 8501. The node's security group
# blocks 8501 from outside, so the ONLY way in is an SSH local-port-forward.
# That tunnel lives only as long as its SSH session: laptop sleep, a Wi-Fi
# change, or an idle timeout drops it and the browser then says "server not
# found" even though the node app is still healthy.
#
# This script (a) cleans up a stale tunnel that is squatting on local :8501
# (the "port in use but nothing loads" symptom), (b) opens a keepalive tunnel,
# and (c) auto-reconnects it through brief network blips. It does NOT survive a
# fully slept/rebooted laptop — after real sleep, just run it again.
#
# Usage:
#   ./connect_chatbot.sh            # = connect (default)
#   ./connect_chatbot.sh connect    # clean up + open the keepalive tunnel
#   ./connect_chatbot.sh status     # is the remote app up? (process, port, advisor)
#   ./connect_chatbot.sh stop       # kill our local tunnel, free the port
#
# Env overrides (floating IP changes across Chameleon leases):
#   NODE=cc@<new-ip>  KEY=/path/to/vivek.pem  PORT=8501
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
NODE="${NODE:-${BENCH_NODE:-cc@129.114.108.156}}"
KEY="${KEY:-${BENCH_KEY:-$HERE/vivek.pem}}"
PORT="${PORT:-8501}"
SSH_BASE=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new)
# The exact -L spec; also used as the fingerprint to recognise OUR tunnel.
FWD="$PORT:localhost:$PORT"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# PIDs of OUR tunnels, identified by command line (ssh/autossh carrying this
# exact -L spec and node host). Identity-based, so we never rely on the flaky
# macOS lsof LISTEN-state field and never kill anything that isn't our tunnel.
our_tunnel_pids() {
  local pid args out=""
  for pid in $(pgrep -f -- "-L $FWD" 2>/dev/null || true); do
    args="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    [[ "$pid" == "$$" ]] && continue                      # never ourselves
    [[ "$args" == *"$FWD"* && "$args" == *"$NODE"* \
       && ( "$args" == *ssh* ) ]] && out+="$pid "
  done
  printf '%s' "$out"
}

# Best-effort: is a process BOUND to local :$PORT (a listener/squatter, not a
# transient client connection)? Advisory only — used to warn, never to decide a
# kill. macOS lsof mislabels listener state (often "(CLOSED)"), so we can't rely
# on -sTCP:LISTEN; instead we keep lsof rows whose local address is *:$PORT with
# no "->" peer (bound socket), and drop rows owned by our own tunnel pids.
port_holder() {
  local skip="$1"           # space-separated pids to ignore (our tunnels)
  # lsof exits non-zero when it finds nothing; `|| true` keeps that out of the
  # pipeline result under `set -o pipefail`.
  { lsof -nP -iTCP:"$PORT" 2>/dev/null || true; } | awk -v port=":$PORT" -v skip="$skip" '
    NR == 1 { next }                         # header
    {
      pid = $2; name = $9
      if (index(name, "->")) next            # outbound/established client conn
      if (index(name, port) == 0) next       # not the local port we care about
      n = split(skip, s, " ")
      for (i = 1; i <= n; i++) if (s[i] == pid) next
      print
    }'
}

# Kill our own tunnel(s) if present, then warn (but never kill) if some other
# process is still squatting on the port.
cmd_stop() {
  local pids; pids="$(our_tunnel_pids)"
  if [[ -n "$pids" ]]; then
    for pid in $pids; do
      log "killing our tunnel (pid $pid): $(ps -o command= -p "$pid" 2>/dev/null)"
      kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in $pids; do kill -9 "$pid" 2>/dev/null || true; done
  else
    log "no tunnel of ours is running for $FWD -> $NODE."
  fi
  local holder; holder="$(port_holder "$pids")"
  if [[ -n "$holder" ]]; then
    log "NOTE: local port $PORT is still held by another process — not touching it:"
    printf '%s\n' "$holder" | sed 's/^/    /'
    log "If this blocks the tunnel, close that app or run with PORT=<other>."
    return 1
  fi
  return 0
}

# The app may run either as the systemd unit or as a bare nohup'd process, so
# look for the process first and fall back to systemd. Checking the unit alone
# reports "inactive" for a perfectly healthy manually-started app.
cmd_status() {
  log "checking remote app on $NODE (5s connect timeout)…"
  "${SSH_BASE[@]}" -o ConnectTimeout=5 "$NODE" "PORT=$PORT bash -s" <<'REMOTE'
pid=$(pgrep -f 'streamlit run web_rag.py' | head -1)
if [ -n "$pid" ]; then
  echo "rag-app: RUNNING (pid $pid, since $(ps -o lstart= -p "$pid" | sed 's/^ *//'))"
  # Owned by us, so /proc is readable without sudo. Never print LLM_API_KEY.
  for var in ADVISOR_ENABLED LLM_MODEL; do
    echo "  $(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null \
              | grep -m1 "^$var=" || echo "$var=(unset)")"
  done
else
  state=$(systemctl is-active rag-app 2>/dev/null || true)
  [ -z "$state" ] && state='no unit installed'
  echo "rag-app: NOT RUNNING (no streamlit process; systemd: $state)"
fi
printf 'port %s: ' "$PORT"
if ss -ltn 2>/dev/null | grep -q ":$PORT "; then echo listening; else echo 'NOT listening'; fi
echo '--- last log lines ---'
tail -n 6 ~/chatbot.log 2>/dev/null || journalctl -u rag-app -n 6 --no-pager 2>/dev/null || true
REMOTE
}

# Block until the local port answers a TCP connect, or time out.
wait_ready() {
  local tries=0
  while (( tries < 20 )); do
    if command -v nc >/dev/null 2>&1; then
      nc -z localhost "$PORT" 2>/dev/null && return 0
    else
      # bash /dev/tcp fallback
      (exec 3<>"/dev/tcp/localhost/$PORT") 2>/dev/null && { exec 3>&- 3<&-; return 0; }
    fi
    sleep 1; (( tries++ ))
  done
  return 1
}

cmd_connect() {
  cmd_stop || exit 1

  local -a tunnel
  if command -v autossh >/dev/null 2>&1; then
    log "using autossh (robust auto-reconnect)."
    tunnel=(autossh -M 0 -i "$KEY" -o StrictHostKeyChecking=accept-new -N -L "$FWD"
            -o ServerAliveInterval=30 -o ServerAliveCountMax=3
            -o ExitOnForwardFailure=yes "$NODE")
  else
    log "autossh not found — using a bash reconnect loop."
    log "(optional: 'brew install autossh' for more robust reconnection.)"
    tunnel=("${SSH_BASE[@]}" -N -L "$FWD"
            -o ServerAliveInterval=30 -o ServerAliveCountMax=3
            -o ExitOnForwardFailure=yes "$NODE")
  fi

  log "opening tunnel $FWD -> $NODE …  (Ctrl+C to stop)"
  # Announce readiness once, in the background, without blocking the tunnel.
  ( if wait_ready; then
      log "ready — open  http://localhost:$PORT   (NOT the node's IP)"
    else
      log "tunnel started but port $PORT did not answer yet; give it a moment,"
      log "or run './connect_chatbot.sh status' to check the remote service."
    fi ) &

  if command -v autossh >/dev/null 2>&1; then
    exec "${tunnel[@]}"   # autossh handles reconnection itself
  fi
  # Plain-ssh path: reconnect loop for network blips. Ctrl+C exits cleanly.
  trap 'log "stopping."; exit 0' INT TERM
  while true; do
    "${tunnel[@]}" || true
    log "tunnel dropped — reconnecting in 2s (Ctrl+C to stop)…"
    sleep 2
  done
}

case "${1:-connect}" in
  connect) cmd_connect ;;
  status)  cmd_status ;;
  stop)    cmd_stop ;;
  *) echo "usage: $0 [connect|status|stop]   (env: NODE=user@ip KEY=/path/key PORT=8501)" >&2
     exit 2 ;;
esac
