#!/bin/bash
# run-linux.sh: the launcher of qchain-fabric-performance on the test machine (Ubuntu; Docker runs on the
# machine's own kernel).
#
#   scripts/run-linux.sh isolate                 reserve the machine's last CPU for everything that is not the study
#                                                and stop automatic package updates (sudo; runtime only: undone by
#                                                `release` or a reboot)
#   scripts/run-linux.sh release                 undo `isolate`
#   scripts/run-linux.sh build                   build the images (needs the internet; sudo, so that the build may
#                                                use every CPU while it runs)
#   scripts/run-linux.sh start <smoke|trial|main> <session> [--seed N] [--force] [--foreground]
#                                                write the session's plan, then run it
#   scripts/run-linux.sh resume <session> [--force] [--foreground]
#                                                continue a session (finished networks are kept)
#   scripts/run-linux.sh status [<session>]
#
# CPU isolation (docs/methodology.md section 8): the study's containers run under the systemd slice qfp.slice,
# allowed CPUs 0 to N-2; system.slice and user.slice (system services, Docker's daemon, the desktop, the remote-
# access agent, other projects' containers, this launcher, the driver and the host monitor) are limited to CPU N-1.
# On the test machine the remote-access agent's login-screen process (AnyDesk, user gdm) keeps one core busy at all
# times; `isolate` also lowers it to the lowest priority, so that it only uses what the reserved CPU leaves.
#
# start and resume restart themselves in a tmux session (setsid and nohup without tmux) under systemd-inhibit, so
# that the remote-desktop session can be closed; --foreground keeps them in this terminal. Trial and main sessions
# refuse to start on a machine that is not ready (smoke sessions only warn), unless --force is given (recorded):
# isolation in place, automatic updates stopped, no package manager running, no other session, 20 GB free on
# Docker's disk, 8 GB of memory available, the study's CPUs quiet.
#
# Functions marked "from qchain-kpi" are adapted from qchain-kpi scripts/run-linux.sh (f1aca562).
set -uo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
self="$repo/scripts/run-linux.sh"
NCPU="$(nproc --all)"
RESERVED_CPUS="$((NCPU - 1))"
STUDY_CPUS="0-$((NCPU - 2))"
SLICE=qfp.slice
UPDATE_UNITS=(apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service)
AGENT_USER=gdm
AGENT_PATTERN="anydesk --backend"
export QFP_CGROUP_PARENT="$SLICE" QFP_CPUSET="$STUDY_CPUS"

die() { echo "run-linux.sh: $*" >&2; exit 1; }
note() { echo "run-linux.sh: $*" >&2; }

cg_cpus() { cat "/sys/fs/cgroup/$1/cpuset.cpus.effective" 2>/dev/null; }

# ------------------------------------------------------------ CPU isolation

agent_nice() { # niceness for every thread of the remote-access agent's login-screen process
  local pid t
  for pid in $(pgrep -u "$AGENT_USER" -f "$AGENT_PATTERN" 2>/dev/null); do
    for t in /proc/"$pid"/task/*; do sudo renice -n "$1" -p "${t##*/}" >/dev/null 2>&1; done
  done
}

show_isolation() {
  local u
  echo "qfp.slice:    CPUs $(cg_cpus "$SLICE" || true)   (the study; expected $STUDY_CPUS)"
  echo "system.slice: CPUs $(cg_cpus system.slice || true)   (expected $RESERVED_CPUS while isolated)"
  echo "user.slice:   CPUs $(cg_cpus user.slice || true)   (expected $RESERVED_CPUS while isolated)"
  for u in "${UPDATE_UNITS[@]}"; do echo "$u: $(systemctl is-active "$u" 2>/dev/null)"; done
  local pid
  pid="$(pgrep -u "$AGENT_USER" -f "$AGENT_PATTERN" 2>/dev/null | head -1)"
  if [ -n "$pid" ]; then echo "remote-access agent (login screen): niceness $(ps -o ni= -p "$pid" | tr -d ' ')"; else echo "remote-access agent (login screen): not running"; fi
}

isolate() {
  sudo -v || die "isolate needs sudo"
  sudo systemctl start "$SLICE" || die "could not start $SLICE"
  sudo systemctl set-property --runtime "$SLICE" "AllowedCPUs=$STUDY_CPUS" || die "could not set $SLICE"
  sudo systemctl set-property --runtime system.slice "AllowedCPUs=$RESERVED_CPUS" || die "could not set system.slice"
  sudo systemctl set-property --runtime user.slice "AllowedCPUs=$RESERVED_CPUS" || die "could not set user.slice"
  sudo systemctl stop "${UPDATE_UNITS[@]}"
  agent_nice 19
  show_isolation
}

release() {
  [ -z "$(docker ps -q --filter label=org.qchain.qfp=1 2>/dev/null)" ] || die "study containers are running; stop the session first (python3 -I scripts/qfp.py down)"
  sudo -v || die "release needs sudo"
  agent_nice 0
  sudo systemctl set-property --runtime system.slice "AllowedCPUs=" && sudo systemctl set-property --runtime user.slice "AllowedCPUs="
  sudo systemctl revert system.slice user.slice "$SLICE" >/dev/null 2>&1
  sudo systemctl stop "$SLICE" 2>/dev/null
  sudo systemctl start "${UPDATE_UNITS[@]}"
  show_isolation
}

# ------------------------------------------------------------ preflight (from qchain-kpi, adapted)

problems=()
notes=()
problem() { problems+=("$1"); }

# (printf, not print: mawk prints large tick counts in scientific notation)
# study_load SECONDS: "busy_pct steal_pct": the study's CPUs' busy share and the machine's steal over that time.
study_load() {
  local a b
  a="$(awk -v want=" $(seq -s ' ' -f 'cpu%g' 0 $((NCPU - 2))) " '$1 == "cpu" {printf "%.0f\n", $9} index(want, " " $1 " ") {b += $2 + $3 + $4 + $7 + $8; t += $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9} END {printf "%.0f %.0f\n", b, t}' /proc/stat | tr '\n' ' ')"
  sleep "$1"
  b="$(awk -v want=" $(seq -s ' ' -f 'cpu%g' 0 $((NCPU - 2))) " '$1 == "cpu" {printf "%.0f\n", $9} index(want, " " $1 " ") {b += $2 + $3 + $4 + $7 + $8; t += $2 + $3 + $4 + $5 + $6 + $7 + $8 + $9} END {printf "%.0f %.0f\n", b, t}' /proc/stat | tr '\n' ' ')"
  # shellcheck disable=SC2086  # splitting the two readings into numbers is intended
  set -- $a $b
  # $1 steal0, $2 busy0, $3 total0, $4 steal1, $5 busy1, $6 total1
  local dt=$(($6 - $3))
  [ "$dt" -gt 0 ] || { echo "0 0"; return 0; }
  echo "$(((100 * ($5 - $2) + dt / 2) / dt)) $(((100 * ($4 - $1) * (NCPU - 1) / NCPU + dt / 2) / dt))"
}

preflight() { # kind
  local kind="$1" u free_kb avail_mb load busy steal root
  problems=()
  notes=()
  docker info >/dev/null 2>&1 || die "Docker is not reachable (is the docker service running, and may this user use it?)"
  [ "$(docker info -f '{{.CgroupVersion}}')" = 2 ] || die "Docker uses cgroup v1 here; the study needs cgroup v2"
  [ "$(cg_cpus "$SLICE")" = "$STUDY_CPUS" ] || problem "CPU isolation is not in place ($SLICE allows '$(cg_cpus "$SLICE")', not $STUDY_CPUS): run scripts/run-linux.sh isolate"
  { [ "$(cg_cpus system.slice)" = "$RESERVED_CPUS" ] && [ "$(cg_cpus user.slice)" = "$RESERVED_CPUS" ]; } \
    || problem "system.slice and user.slice are not limited to CPU $RESERVED_CPUS: run scripts/run-linux.sh isolate"
  for u in "${UPDATE_UNITS[@]}"; do
    if systemctl is-active --quiet "$u"; then problem "$u is active (an update could restart Docker): run scripts/run-linux.sh isolate"; fi
  done
  if pgrep -x 'apt|apt-get|dpkg|unattended-upgr' >/dev/null; then problem "a package manager is running"; fi
  if pgrep -f "scripts/qfp.py run" >/dev/null; then problem "another session is running"; fi
  root="$(docker info -f '{{.DockerRootDir}}')"
  free_kb="$(df -Pk "$root" 2>/dev/null | awk 'NR==2 {print $4}')"
  [ -n "$free_kb" ] || free_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
  [ "${free_kb:-0}" -ge 20971520 ] || problem "less than 20 GB free on Docker's disk"
  avail_mb="$(awk '/^MemAvailable/ {print int($2 / 1024)}' /proc/meminfo)"
  [ "$avail_mb" -ge 8192 ] || problem "less than 8 GB of memory available ($avail_mb MB)"
  load="$(study_load 6)"
  busy="${load% *}"
  steal="${load#* }"
  [ "$busy" -le 5 ] || problem "the study's CPUs were ${busy}% busy over 6 s before the session (not quiet)"
  if [ "$steal" -gt 2 ]; then note "warning: the hypervisor took ${steal}% of the CPU time over 6 s (steal)"; fi
  notes+=("study CPUs busy ${busy}%, steal ${steal}% over 6 s before the session; ${avail_mb} MB available; $((free_kb / 1048576)) GB free")
  if [ "${#problems[@]}" -gt 0 ]; then
    for u in "${problems[@]}"; do note "preflight: $u"; done
    if [ "$kind" = smoke ]; then
      note "smoke session: preflight problems are recorded, not enforced"
    elif [ "$force" = 1 ]; then
      note "--force: continuing despite preflight problems (recorded in the session folder)"
    else
      die "preflight failed; fix the problems above (or use --force, which is recorded)"
    fi
  fi
}

# ------------------------------------------------------------ detaching (from qchain-kpi, adapted)

# relaunch ARGS...: runs this script again with ARGS under systemd-inhibit (sleep and idle blocked): in a tmux
# session (setsid and nohup without tmux) that outlives the terminal, or here with --foreground.
relaunch() {
  local session="$3" inhibit=() sleep_state sdir line wrapper tname="qfp-${3//[.:]/_}"
  if systemd-inhibit --what=sleep:idle --who=qfp --why=check --mode=block true >/dev/null 2>&1; then
    inhibit=(systemd-inhibit --what=sleep:idle --who=qfp "--why=qchain-fabric-performance session" --mode=block)
    sleep_state="sleep and idle blocked by systemd-inhibit"
  else
    note "warning: systemd-inhibit was refused; sleep and idle are not blocked during this session"
    sleep_state="sleep and idle not blocked (systemd-inhibit was refused)"
  fi
  if [ "$foreground" = 1 ]; then
    exec env "QFP_SLEEP=$sleep_state" "${inhibit[@]}" "$self" "$@"
  fi
  sdir="$repo/results/raw/$session"
  wrapper="$sdir/launcher.sh"
  line="$(printf '%q ' env "QFP_SLEEP=$sleep_state" "${inhibit[@]}" "$self" "$@")"
  {
    echo '#!/bin/bash'
    printf '%s 2>&1 | tee -i -a %q\n' "$line" "$sdir/console.log"
    printf 'echo; echo %q\nread -r _\n' "run-linux.sh has finished (log: results/raw/$session/console.log). Press Enter to close this window."
  } > "$wrapper"
  if command -v tmux >/dev/null 2>&1; then
    tmux new-session -d -s "$tname" "bash $(printf '%q' "$wrapper")" || die "could not start the tmux session $tname"
    note "started in the tmux session $tname; watch it with: tmux attach -t $tname (leave it with Ctrl-B, then D)"
  else
    setsid nohup bash "$wrapper" >/dev/null 2>&1 < /dev/null &
    note "started in the background (tmux is not installed); follow it with: tail -f results/raw/$session/console.log"
  fi
  note "closing this terminal or the remote-desktop session does not stop it"
  exit 0
}

# ------------------------------------------------------------ session

mon_pid=""
cleanup() { [ -n "$mon_pid" ] && kill "$mon_pid" 2>/dev/null; mon_pid=""; }
trap cleanup EXIT
trap 'cleanup; exit 129' HUP
trap 'cleanup; exit 143' TERM

session_run() { # kind session
  local kind="$1" session="$2" sdir="$repo/results/raw/$2" stamp
  mkdir -p "$sdir/host"
  preflight "$kind"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  { printf 'problem: %s\n' "${problems[@]}"; printf 'note: %s\n' "${notes[@]}"; } 2>/dev/null | grep -v '^problem: $' > "$sdir/preflight-$stamp.txt"
  {
    echo "utc=$(date -u +%FT%TZ)"; echo "kind=$kind"; echo "force=$force"
    # shellcheck source=/dev/null
    echo "os=$(. /etc/os-release && echo "$PRETTY_NAME")"; echo "kernel=$(uname -r)"
    echo "hypervisor=$(systemd-detect-virt 2>/dev/null)"
    echo "cpu=$(lscpu | sed -n 's/^Model name: *//p' | head -1)"; echo "vcpus=$NCPU"
    echo "study_cpus=$STUDY_CPUS"; echo "reserved_cpus=$RESERVED_CPUS"
    echo "memory_mb=$(awk '/^MemTotal/ {print int($2 / 1024)}' /proc/meminfo)"
    echo "docker=$(docker version --format '{{.Server.Version}}' 2>/dev/null)"
    echo "sleep=${QFP_SLEEP:-not blocked}"
  } >> "$sdir/session-host.txt"
  nice -n 19 "$repo/monitor/monitor-linux.sh" "$sdir/host" 5 "$$" "$STUDY_CPUS" "$RESERVED_CPUS" > "$sdir/host/monitor.log" 2>&1 &
  mon_pid=$!
  note "session $session: log in results/raw/$session/driver.log"
  python3 -I "$repo/scripts/qfp.py" run "$session"
}

# ------------------------------------------------------------ commands

cmd="${1:-}"; shift || true
force=0
foreground=0
seed=20261116
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --force) force=1 ;;
    --foreground) foreground=1 ;;
    --seed) seed="$2"; shift ;;
    *) args+=("$1") ;;
  esac
  shift
done
pass=()
[ "$force" = 1 ] && pass+=(--force)

case "$cmd" in
  isolate) isolate ;;
  release) release ;;
  build)
    widened=0
    if [ "$(cg_cpus system.slice)" = "$RESERVED_CPUS" ]; then
      note "the build runs inside Docker's daemon, which isolation keeps on CPU $RESERVED_CPUS: allowing every CPU while it builds"
      sudo systemctl set-property --runtime system.slice "AllowedCPUs=0-$((NCPU - 1))" && widened=1
    fi
    python3 -I "$repo/scripts/qfp.py" build
    rc=$?
    if [ "$widened" = 1 ]; then sudo systemctl set-property --runtime system.slice "AllowedCPUs=$RESERVED_CPUS"; note "system.slice back on CPU $RESERVED_CPUS"; fi
    exit $rc ;;
  start)
    [ "${#args[@]}" = 2 ] || die "usage: run-linux.sh start <smoke|trial|main> <session> [--seed N] [--force] [--foreground]"
    kind="${args[0]}"; session="${args[1]}"
    [[ "$session" =~ ^[A-Za-z0-9._-]+$ ]] || die "session names use letters, digits, . _ - only"
    preflight "$kind"   # here first, so that a refusal is seen in this terminal; again in the session (recorded)
    python3 -I "$repo/scripts/qfp.py" plan "$kind" "$session" --seed "$seed" || exit 1
    relaunch _session "$kind" "$session" "${pass[@]}" ;;
  resume)
    [ "${#args[@]}" = 1 ] || die "usage: run-linux.sh resume <session> [--force] [--foreground]"
    session="${args[0]}"
    kind="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["kind"])' "$repo/results/raw/$session/plan.json")" \
      || die "no plan for $session"
    preflight "$kind"
    relaunch _session "$kind" "$session" "${pass[@]}" ;;
  _session)
    session_run "${args[0]}" "${args[1]}" ;;
  status)
    if [ "${#args[@]}" -ge 1 ]; then python3 -I "$repo/scripts/qfp.py" status "${args[0]}"; fi
    tmux ls 2>/dev/null | grep '^qfp-' || echo "no tmux session of the study is open"
    show_isolation ;;
  *)
    sed -n '2,28p' "$0"; exit 2 ;;
esac
