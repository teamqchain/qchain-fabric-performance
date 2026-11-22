#!/bin/bash
# monitor-linux.sh: the host monitor of qchain-fabric-performance, adapted from qchain-kpi
# scripts/monitor-linux.sh (f1aca562). Started and stopped by scripts/run-linux.sh; it runs in the
# user's session, so on the machine's reserved CPU, at the lowest priority.
#
#   monitor-linux.sh <work-dir> <period-s> <launcher-pid> <study-cpus> <reserved-cpus>
#
# Every sample becomes one row of <work-dir>/host-all.csv:
#
#   utc_ns,other_pct,steal_pct,cpuset_ok,alert,detail
#
#   other_pct  CPU time on the study's CPUs that the study did not use: their busy time
#              (/proc/stat) minus the CPU time of qfp.slice (its cpu.stat), as a share of those
#              CPUs over the sample
#   steal_pct  CPU time the hypervisor took from the whole machine (steal) over the sample
#   cpuset_ok  1 while qfp.slice allows exactly the study's CPUs and system.slice and user.slice
#              exactly the reserved ones; 0 otherwise
#   alert      1 while automatic package updates run or their units are active (checked once a
#              minute)
#   detail     the study's CPUs' busy %, the study's own share, the machine's busy %, the 1-minute
#              load, the available memory and what the last check found
#
# No user names, host names or paths are recorded. The monitor ends when the launcher does.
set -euo pipefail

dir="$1"
period="$2"
launcher="$3"
study="$4"
reserved="$5"
header="utc_ns,other_pct,steal_pct,cpuset_ok,alert,detail"
mkdir -p "$dir"
[ -s "$dir/host-all.csv" ] || echo "$header" > "$dir/host-all.csv"
hz="$(getconf CLK_TCK)"
us_per_tick=$((1000000 / hz))
slice=/sys/fs/cgroup/qfp.slice

# The study's CPUs as " cpu0 cpu1 ... " (from "0-6" or "0,2,4-5").
want=" "
IFS=, read -r -a parts <<< "$study"
for part in "${parts[@]}"; do
  if [[ "$part" == *-* ]]; then
    for c in $(seq "${part%-*}" "${part#*-}"); do want+="cpu$c "; done
  else
    want+="cpu$part "
  fi
done

# Unix time in ns (from qchain-kpi). EPOCHREALTIME (bash 5) may use the locale's decimal mark.
now_ns() {
  if [ -n "${EPOCHREALTIME:-}" ]; then printf '%s000\n' "${EPOCHREALTIME//[!0-9]/}"; else date +%s%N; fi
}

# read_stat: the machine's busy, total and steal ticks and the study CPUs' busy and total ticks.
read_stat() {
  local name u n s i w q sq st rest
  sbusy=0 stotal=0
  while read -r name u n s i w q sq st rest; do
    case "$name" in
      cpu) mbusy=$((u + n + s + q + sq)); mtotal=$((u + n + s + i + w + q + sq + st)); msteal=$st ;;
      cpu*) case "$want" in *" $name "*)
              sbusy=$((sbusy + u + n + s + q + sq)); stotal=$((stotal + u + n + s + i + w + q + sq + st)) ;;
            esac ;;
      *) break ;;
    esac
  done < /proc/stat
  slice_us="$(awk '/^usage_usec/ {print $2}' "$slice/cpu.stat" 2>/dev/null || true)"
  slice_us="${slice_us:-0}"
}

pct() { # part whole -> percent with one decimal (0.0 when whole is 0; never negative)
  local v=0
  [ "$2" -gt 0 ] && [ "$1" -gt 0 ] && v=$(((1000 * $1 + $2 / 2) / $2))
  printf '%d.%d' $((v / 10)) $((v % 10))
}

cpuset_ok() {
  [ "$(cat "$slice/cpuset.cpus.effective" 2>/dev/null)" = "$study" ] &&
    [ "$(cat /sys/fs/cgroup/system.slice/cpuset.cpus.effective 2>/dev/null)" = "$reserved" ] &&
    [ "$(cat /sys/fs/cgroup/user.slice/cpuset.cpus.effective 2>/dev/null)" = "$reserved" ] && echo 1 || echo 0
}

# check: sets alert (0/1) and found (what ran).
alert=0
found="not_checked"
check() {
  local what=() u
  if pgrep -x 'apt|apt-get|dpkg|unattended-upgr' >/dev/null 2>&1; then what+=("package_manager"); fi
  if command -v systemctl >/dev/null 2>&1; then
    for u in apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service; do
      if systemctl is-active --quiet "$u"; then what+=("${u%%.*}"); fi
    done
  fi
  alert=0
  found="none"
  if [ "${#what[@]}" -gt 0 ]; then alert=1; found="$(IFS=+; printf '%s' "${what[*]}")"; fi
}

trap 'exit 0' TERM INT HUP
read_stat
mb0=$mbusy mt0=$mtotal ms0=$msteal sb0=$sbusy st0=$stotal su0=$slice_us
samples=0
while kill -0 "$launcher" 2>/dev/null; do
  sleep "$period" &
  wait $! || true
  if [ $((samples % 12)) -eq 0 ]; then check; fi
  samples=$((samples + 1))
  read_stat
  dsb=$((sbusy - sb0)) dst=$((stotal - st0)) dsu=$((slice_us - su0))
  other_us=$((dsb * us_per_tick - dsu))
  read -r load1 _ < /proc/loadavg
  avail_mb="$(awk '/^MemAvailable/ {print int($2 / 1024)}' /proc/meminfo)"
  row="$(printf '%s,%s,%s,%s,%d,study_cpus_busy_pct=%s;study_pct=%s;machine_busy_pct=%s;load1=%s;mem_avail_mb=%s;found=%s' \
    "$(now_ns)" "$(pct "$other_us" $((dst * us_per_tick)))" "$(pct $((msteal - ms0)) $((mtotal - mt0)))" "$(cpuset_ok)" "$alert" \
    "$(pct "$dsb" "$dst")" "$(pct "$dsu" $((dst * us_per_tick)))" "$(pct $((mbusy - mb0)) $((mtotal - mt0)))" "$load1" "$avail_mb" "$found")"
  mb0=$mbusy mt0=$mtotal ms0=$msteal sb0=$sbusy st0=$stotal su0=$slice_us
  echo "$row" >> "$dir/host-all.csv"
done
