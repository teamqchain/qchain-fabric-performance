#!/bin/bash
# run-mac.sh: the Mac launcher of qchain-fabric-performance.
#
#   scripts/run-mac.sh colima-up                       start the Colima VM (profile qfp: vz, 4 CPUs, 5 GiB, 60 GiB)
#   scripts/run-mac.sh build                           build the images (needs Wi-Fi)
#   scripts/run-mac.sh start <kind> <session> [--seed N] [--force]
#                                                      kind: smoke | trial | main; writes the plan, then runs it
#   scripts/run-mac.sh resume <session> [--force]      continue a session (finished networks are kept)
#   scripts/run-mac.sh status <session>
#
# For trial and main sessions the machine must be quiet (KPI rules, carried over): mains power,
# no thermal pressure, Low Power Mode off, automatic updates off, Teams, Chrome, Edge, VS Code (found by its path) and
# OneDrive closed, host CPU idle. During a session the macOS background analysis services are
# paused, Wi-Fi is switched off, the Mac is kept awake and a host monitor records other CPU,
# thermal pressure and power every 5 s; all of it is undone when the script ends, on every exit
# path. Keep the Terminal window open (closing it ends the session; `resume` continues it).
#
# The functions marked "from qchain-kpi" are copied from qchain-kpi scripts/run-mac.sh (f1aca562).
set -uo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE=qfp
die() { echo "run-mac.sh: $*" >&2; exit 1; }
note() { echo "run-mac.sh: $*" >&2; }

# ------------------------------------------------------------ preflight (from qchain-kpi, adapted)
problems=()
problem() { problems+=("$1"); }

preflight_host() {
  local n busy app out key free_kb
  out="$(pmset -g batt)"
  [[ "$out" == *"AC Power"* ]] || problem "on battery power"
  n="$(pmset -g batt | grep -Eo '[0-9]+%' | head -n 1 | tr -d '%')"
  if [ -n "$n" ] && [ "$n" -lt 98 ]; then
    note "warning: battery at $n% (use 'Charge to Full Now' in the battery menu)"
  fi
  [ "$(notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}')" = "0" ] || problem "thermal pressure is above nominal"
  [ "$(pmset -g | awk '/lowpowermode/{print $2}')" != "1" ] || problem "Low Power Mode is on"
  for key in AutomaticallyInstallMacOSUpdates AutomaticDownload; do
    out="$(defaults read /Library/Preferences/com.apple.SoftwareUpdate "$key" 2>/dev/null || true)"
    [ "$out" != "1" ] || problem "automatic macOS updates are on ($key); turn them off in System Settings > General > Software Update > Automatic updates"
  done
  for app in "MSTeams" "Microsoft Teams" "Google Chrome" "Microsoft Edge" "OneDrive"; do
    if pgrep -a -x -q "$app"; then problem "$app is running (close it during trial and main runs)"; fi
  done
  # VS Code is found by its application path (a name check missed it)
  if pgrep -f "Visual Studio Code.app" >/dev/null 2>&1; then problem "VS Code is running (close it during trial and main runs)"; fi
  free_kb="$(df -Pk "$HOME" | awk 'NR==2{print $4}')"
  [ "$free_kb" -ge 20971520 ] || problem "less than 20 GB free on the Mac"
  busy="$(top -l 3 -s 2 -n 0 | awk '/^CPU usage/{u=$3; s=$5} END{gsub("%","",u); gsub("%","",s); printf "%.0f", u+s}')"
  [ "$busy" -le 15 ] || problem "host CPU busy at ${busy}% over 6 s (machine not quiet)"
}

preflight_colima() {
  local out
  command -v colima >/dev/null || problem "colima is not installed"
  command -v docker >/dev/null || problem "docker is not installed"
  out="$(colima list 2>/dev/null | awk -v p="$PROFILE" '$1==p{print $2, $4, $5}')"
  [[ "$out" == "Running 4 5GiB" ]] || problem "Colima profile $PROFILE is not running with 4 CPUs and 5 GiB (found: ${out:-none}); run: scripts/run-mac.sh colima-up"
  [ "$(docker info --format '{{.Architecture}}' 2>/dev/null)" = "aarch64" ] || problem "Docker does not answer, or is not arm64"
}

verdict() { # kind
  local p
  if [ "${#problems[@]}" -gt 0 ]; then
    for p in "${problems[@]}"; do note "preflight: $p"; done
    if [ "$1" = smoke ]; then
      note "smoke session: preflight problems are recorded, not enforced"
    elif [ "$force" = 1 ]; then
      note "--force: continuing despite preflight problems (recorded in the session folder)"
    else
      die "preflight failed; fix the problems above (or use --force, which is recorded)"
    fi
  fi
}

# ------------------------------------------------------------ session conditions (from qchain-kpi)
BG_PATTERN='/(mediaanalysisd|photoanalysisd|spotlightknowledged|spotlightknowledged[.]importer|spotlightknowledged[.]updater|suggestd|duetexpertd|knowledge-agent|knowledgeconstructiond|siriknowledged|AddressBookSourceSync|appstoreagent)( |$)'
pause_bg() { # logfile
  local pid name
  for pid in $(pgrep -f "$BG_PATTERN" 2>/dev/null); do
    if [ "$(ps -o stat= -p "$pid" 2>/dev/null | cut -c1)" != "T" ]; then
      name="$(ps -o comm= -p "$pid" 2>/dev/null)"
      name="${name##*/}"
      if kill -STOP "$pid" 2>/dev/null; then
        printf '%s paused %s %s\n' "$(date -u +%H:%M:%S)" "$pid" "$name" >> "$1"
      fi
    fi
  done
}
resume_bg() { pkill -CONT -f "$BG_PATTERN" 2>/dev/null || true; }

wifi_dev=""
wifi_cut=0
bg_paused=0
mon_pid=""
caf_pid=""
wifi_off() { # logfile
  local dev out
  dev="$(networksetup -listallhardwareports | awk '/Hardware Port: Wi-Fi/{getline; print $2; exit}')"
  [ -n "$dev" ] || { note "no Wi-Fi device found; nothing to switch off"; return 0; }
  out="$(networksetup -getairportpower "$dev" 2>&1 || true)"
  if [[ "$out" == *": On" ]]; then
    wifi_dev="$dev"
    if networksetup -setairportpower "$dev" off >/dev/null 2>&1; then
      wifi_cut=1
      printf '%s Wi-Fi (%s) switched off\n' "$(date -u +%H:%M:%S)" "$dev" >> "$1"
      note "Wi-Fi switched off for this session (it is switched back on when the script ends)"
    else
      note "warning: could not switch Wi-Fi off; the session continues with Wi-Fi on"
    fi
  else
    note "Wi-Fi was already off; it stays off"
  fi
}
wifi_restore() {
  if [ "$wifi_cut" = 1 ]; then
    wifi_cut=0
    if networksetup -setairportpower "$wifi_dev" on >/dev/null 2>&1; then
      note "Wi-Fi switched back on"
    else
      note "WARNING: could not switch Wi-Fi back on; run: networksetup -setairportpower $wifi_dev on"
    fi
  fi
}
cleanup() {
  [ -n "$mon_pid" ] && kill "$mon_pid" 2>/dev/null; mon_pid=""
  [ -n "$caf_pid" ] && kill "$caf_pid" 2>/dev/null; caf_pid=""
  if [ "$bg_paused" = 1 ]; then resume_bg; bg_paused=0; fi
  wifi_restore
}
trap cleanup EXIT
trap 'cleanup; exit 129' HUP
trap 'cleanup; exit 143' TERM

# ------------------------------------------------------------ commands
cmd="${1:-}"; shift || true
force=0
seed=20261116
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --force) force=1 ;;
    --seed) seed="$2"; shift ;;
    *) args+=("$1") ;;
  esac
  shift
done

session_run() { # kind session
  local kind="$1" session="$2" sdir="$repo/results/raw/$2"
  mkdir -p "$sdir/host"
  problems=()
  preflight_colima
  [ "$kind" = smoke ] || preflight_host
  verdict "$kind"
  printf '%s\n' "${problems[@]:-}" > "$sdir/preflight-$(date -u +%Y%m%dT%H%M%SZ).txt"
  {
    echo "utc=$(date -u +%FT%TZ)"; echo "kind=$kind"; echo "force=$force"
    echo "macos=$(sw_vers -productVersion) ($(sw_vers -buildVersion))"; echo "model=$(sysctl -n hw.model)"
    echo "colima=$(colima version 2>/dev/null | head -1)"; echo "docker=$(docker version --format '{{.Server.Version}}' 2>/dev/null)"
    echo "cooling_pad=used for every run (decision 16 Nov)"
  } >> "$sdir/session-host.txt"
  if [ "$kind" != smoke ]; then
    pause_bg "$sdir/host/paused.log"; bg_paused=1
    wifi_off "$sdir/host/wifi.log"
  fi
  caffeinate -i -s -w "$$" >/dev/null 2>&1 &
  caf_pid=$!
  "$repo/monitor/monitor-mac.sh" "$sdir/host" 5 720 "$$" > "$sdir/host/monitor.log" 2>&1 &
  mon_pid=$!
  note "session $session: log in results/raw/$session/driver.log (keep this window open)"
  python3 -I "$repo/scripts/qfp.py" run "$session"
  return $?
}

case "$cmd" in
  colima-up)
    command -v colima >/dev/null || die "colima is not installed (step 3 of the plan; see docs/revert-list.md R1)"
    colima start --profile "$PROFILE" --vm-type vz --arch aarch64 -c 4 -m 5 -d 60 \
      || die "colima start failed"
    colima list ;;
  build)
    [ "$(networksetup -getairportpower "$(networksetup -listallhardwareports | awk '/Hardware Port: Wi-Fi/{getline; print $2; exit}')" 2>/dev/null | awk '{print $NF}')" = "On" ] \
      || note "warning: Wi-Fi seems off; the build downloads base images and liboqs"
    python3 -I "$repo/scripts/qfp.py" build ;;
  start)
    [ "${#args[@]}" = 2 ] || die "usage: run-mac.sh start <smoke|trial|main> <session> [--seed N] [--force]"
    kind="${args[0]}"; session="${args[1]}"
    [[ "$session" =~ ^[A-Za-z0-9._-]+$ ]] || die "session names use letters, digits, . _ - only"
    python3 -I "$repo/scripts/qfp.py" plan "$kind" "$session" --seed "$seed" || exit 1
    session_run "$kind" "$session" ;;
  resume)
    [ "${#args[@]}" = 1 ] || die "usage: run-mac.sh resume <session> [--force]"
    session="${args[0]}"
    kind="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["kind"])' "$repo/results/raw/$session/plan.json")" \
      || die "no plan for $session"
    session_run "$kind" "$session" ;;
  status)
    python3 -I "$repo/scripts/qfp.py" status "${args[0]:?session}" ;;
  *)
    sed -n '2,20p' "$0" ; exit 2 ;;
esac
