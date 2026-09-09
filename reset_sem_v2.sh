#!/usr/bin/env bash
set -euo pipefail

BASE=/data/hdd3/agent-research-runtime/minecraft-data/vanilla-1.21.1
WORLD=sem-minecraft-primary-v2
TEMPLATE=/data/hdd3/agent-research-runtime/minecraft-data/sem-minecraft-primary-v2-template
ARCHIVE=/data/hdd3/agent-research-runtime/minecraft-assignment-archives
PIDFILE=/data/hdd3/agent-research-runtime/minecraft-primary-v2.pid
assignment=${1:?assignment id is required}
safe_id=$(printf '%s' "$assignment" | tr -c 'A-Za-z0-9_.-' '_')

mkdir -p "$ARCHIVE"
if [[ -f "$PIDFILE" ]]; then
  pid=$(cat "$PIDFILE")
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" || true
    for _ in $(seq 1 45); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" || true
    fi
  fi
  rm -f "$PIDFILE"
fi
if [[ -d "$BASE/$WORLD" ]]; then
  mv "$BASE/$WORLD" "$ARCHIVE/${safe_id}-$(date +%s)"
fi
cp -a "$TEMPLATE" "$BASE/$WORLD"

cd "$BASE"
nohup bash -c "cd '$BASE' && exec java -Xms512M -Xmx2G -jar server.jar nogui" \
  > "$BASE/server.log" 2>&1 </dev/null &
echo $! > "$PIDFILE"

for _ in $(seq 1 90); do
  if ss -ltn | awk '$4 ~ /:25565$/ {found=1} END {exit found ? 0 : 1}'; then
    printf 'minecraft_ready assignment=%s pid=%s\n' "$safe_id" "$(cat "$PIDFILE")"
    exit 0
  fi
  pid=$(cat "$PIDFILE")
  if ! kill -0 "$pid" 2>/dev/null; then
    tail -40 "$BASE/server.log" >&2
    exit 1
  fi
  sleep 1
done
tail -40 "$BASE/server.log" >&2
exit 1
