#!/usr/bin/env bash
set -euo pipefail

BASE=/data1/agent-research-runtime/sem-paper-minecraft-20260910
TEMPLATE=/data1/agent-research-runtime/sem-paper-minecraft-template-20260910
ARCHIVE=/data1/agent-research-runtime/sem-paper-minecraft-assignment-archives
PIDFILE=$BASE/sem-paper-server.pid
assignment="$1"
if [[ -z "$assignment" ]]; then
    echo "assignment id is required" >&2
    exit 2
fi
safe_id=$(printf '%s' "$assignment" | tr -c 'A-Za-z0-9_.-' '_')

mkdir -p "$ARCHIVE"
server_pid=""
for pid in $(pgrep -f 'java .*server.jar' || true); do
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    if [[ "$cwd" == "$BASE" && "$cmd" == *server.jar* ]]; then
        server_pid=$pid
        break
    fi
done
if [[ -z "$server_pid" && -f "$PIDFILE" ]]; then
    candidate=$(cat "$PIDFILE")
    cwd=$(readlink -f "/proc/$candidate/cwd" 2>/dev/null || true)
    cmd=$(tr '\0' ' ' < "/proc/$candidate/cmdline" 2>/dev/null || true)
    if [[ "$cwd" == "$BASE" && "$cmd" == *server.jar* ]]; then
        server_pid=$candidate
    fi
fi
if [[ -n "$server_pid" ]]; then
    kill -TERM "$server_pid" || true
    for _ in $(seq 1 45); do
        kill -0 "$server_pid" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "$server_pid" 2>/dev/null; then
        kill -KILL "$server_pid" || true
    fi
fi
rm -f "$PIDFILE"
if [[ -d "$BASE/world" ]]; then
    mv "$BASE/world" "$ARCHIVE/$safe_id-$(date +%s)"
fi
cp -a "$TEMPLATE/world" "$BASE/world"

cd "$BASE"
nohup java -Xms512M -Xmx2G -jar server.jar nogui > "$BASE/server.log" 2>&1 </dev/null &
echo $! > "$PIDFILE"

for _ in $(seq 1 90); do
    if (exec 3<>/dev/tcp/127.0.0.1/25565) 2>/dev/null; then
        exec 3>&-
        printf 'minecraft_ready assignment=%s pid=%s
' "$safe_id" "$(cat "$PIDFILE")"
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
