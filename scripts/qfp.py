#!/usr/bin/env python3
"""qfp.py: the driver of qchain-fabric-performance (runs on the Mac, Python 3.9 standard library).

It talks to Docker in the Colima VM, builds the images, brings every network up and down,
runs every run in a fresh client container, reads each container's CPU, network and memory
from the Docker API, applies the quality rules (flags and repeats), and keeps a resumable
state. The Mac-side conditions (preflight, paused services, Wi-Fi, caffeinate, host monitor)
are the launcher's job: scripts/run-mac.sh, which calls this script.

    qfp.py build [--lock live|none]           the four images (needs the internet)
    qfp.py selfcheck                          generator and verbatim checks, Docker reachable
    qfp.py plan <kind> <session> [--seed N]   write a session plan: smoke | trial | main
    qfp.py run <session>                      execute or resume a session
    qfp.py status <session>                   progress and projected end
    qfp.py trial-report <session>             C, E3 saturation, memory, disk and time projections
    qfp.py freeze --c N --saturation X [--split NET ...]
                                              freeze the thresholds after the trial
    qfp.py analyse <session>                  tables and figures (in the analysis image)
    qfp.py analysis-selftest                  the analysis on a synthetic session
    qfp.py publish <session>                  copy into results/<session>, privacy scan, SHA256SUMS
    qfp.py down                               remove every study container and network volume

Every container, volume and network of the study carries the label org.qchain.qfp=1 and a
name starting with qfp; nothing else in Docker is ever touched.
"""

import argparse
import datetime
import http.client
import io
import json
import math
import os
import random
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tarfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "network", "gen"))
import qfp_gen  # noqa: E402

RAW = os.path.join(REPO, "results", "raw")
CONFIG = os.path.join(REPO, "config", "thresholds.json")
IMAGES = os.path.join(RAW, "images.json")
TEAM = os.path.dirname(REPO)
CLONES = {  # name: (folder, pinned commit)
    "fabric": ("qchain-fabric", "e472b4ea7693811ffa99768cd415d8bd4f6117f4"),
    "fabric-ca": ("qchain-fabric-ca", "e82caf43f01642728ef189710a6739f5f77dfd54"),
    "fabric-lib-go": ("qchain-fabric-lib-go", "bd30150"),
}
DOCKER_NET = "qfp-net"
RESULTS_VOL = "qfp-results"
LABEL = "org.qchain.qfp=1"

TOPOLOGIES = [(1, 1), (1, 2), (1, 4), (1, 8), (2, 2), (2, 4), (2, 8), (4, 4), (4, 8), (8, 8)]
ARMS = ["ecdsa", "mldsa44"]
T_LEVELS = [1, 10, 100, 1000, 10000]
REPS = 5
# C, the cap on transactions in flight: candidates tested by the trial (at least one block of 100, below the
# gateway's concurrency limit of 500), and the two cases that decide it (docs/plan.md section 8)
C_CANDIDATES = [100, 200, 300]
C_CASES = [("heaviest", "o8p8-mldsa44"), ("fastest", "o2p2-ecdsa")]
E3_FRACTIONS = [0.10, 0.25, 0.50, 0.75, 0.90, 1.00, 1.10]   # offered load, as fractions of the ECDSA saturation
E3_SMALL_RATE = 25            # the trial's short check of the load client (transactions per second, 20 s)
DISK_SPLIT_PCT = 80           # a projected network above this share of the Colima disk is proposed for a split

DEFAULT_THRESHOLDS = {
    "frozen": False,
    "c": None,                    # transactions in flight, chosen by the trial
    "e3_saturation_tps": None,    # the trial's ECDSA write saturation at (2,2), the reference of E3's rates
    "split": [],                  # E1 networks run as two networks (repetitions 1-3, then 4-5), set at freeze
    "other_cpu_pct_mean": 5.0,    # host CPU used by other processes, mean over the run
    "canary_drift_pct": 3.0,      # canary below the session reference
    "swap_growth_mb": 64.0,       # macOS swap growth during a run
    "max_attempts": 3,
    "settle_s": 5,
    "canary_every_s": 3600,
    "holders": 100, "pool": 1000, "warm": 200,
    "e2_n": 200, "e3_duration_s": 60,
}


# ---------------------------------------------------------------- utilities

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(session, msg):
    line = "%s %s" % (now_utc(), msg)
    print(line, flush=True)
    if session:
        with open(os.path.join(session_dir(session), "driver.log"), "a") as f:
            f.write(line + "\n")


def sh(cmd, inp=None, check=True, timeout=None, capture=True):
    r = subprocess.run(cmd, input=inp, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None, timeout=timeout)
    if check and r.returncode != 0:
        err = (r.stderr or b"").decode(errors="replace")[-2000:]
        raise RuntimeError("command failed (%d): %s\n%s" % (r.returncode, " ".join(cmd[:6]), err))
    return r


def docker(*args, **kw):
    return sh(["docker"] + list(args), **kw)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def session_dir(session):
    return os.path.join(RAW, session)


def thresholds():
    t = dict(DEFAULT_THRESHOLDS)
    t.update(read_json(CONFIG, {}))
    return t


def images():
    im = read_json(IMAGES)
    if not im:
        raise SystemExit("no images: run `scripts/qfp.py build` first")
    return im


def harness_commit():
    r = sh(["git", "-C", REPO, "rev-parse", "--short=12", "HEAD"])
    dirty = sh(["git", "-C", REPO, "status", "--porcelain", "--", "client", "docker", "network", "scripts"]).stdout.strip()
    return r.stdout.decode().strip() + ("-dirty" if dirty else "")


# ---------------------------------------------------------------- Docker Engine API (stats)

class DockerAPI:
    """Minimal client of the Docker Engine API over the CLI's unix socket."""

    def __init__(self):
        host = docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}").stdout.decode().strip()
        if not host.startswith("unix://"):
            raise SystemExit("the Docker context is not a unix socket: %s" % host)
        self.path = host[len("unix://"):]

    def get(self, url):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(30)
        s.connect(self.path)
        conn = http.client.HTTPConnection("localhost")
        conn.sock = s
        conn.request("GET", url)
        r = conn.getresponse()
        body = r.read()
        conn.close()
        if r.status != 200:
            raise RuntimeError("Docker API %s: %d %s" % (url, r.status, body[:200]))
        return json.loads(body)

    def stats(self, name):
        """Cumulative CPU (ns), current memory (bytes), network bytes of one container."""
        d = self.get("/containers/%s/stats?stream=false&one-shot=true" % name)
        nets = d.get("networks") or {}
        ms = d.get("memory_stats", {})
        # as `docker stats` reports it: usage without the reclaimable file cache (cgroup v2 inactive_file)
        mem = ms.get("usage", 0) - (ms.get("stats") or {}).get("inactive_file", 0)
        return {
            "cpu_ns": d.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0),
            "mem": mem,
            "mem_raw": ms.get("usage", 0),
            "rx": sum(v.get("rx_bytes", 0) for v in nets.values()),
            "tx": sum(v.get("tx_bytes", 0) for v in nets.values()),
        }

    def snapshot(self, names):
        out = {}
        for n in names:
            try:
                out[n] = self.stats(n)
            except Exception as e:  # a stopped container is reported, not fatal here
                out[n] = {"error": str(e)[:200]}
        return out


class MemSampler(threading.Thread):
    """Samples the containers' memory every 5 s during a run and keeps each container's peak and the
    peak of the network's total (the sum over the containers within one sweep)."""

    def __init__(self, api, names):
        super().__init__(daemon=True)
        self.api, self.names, self.peak = api, names, {n: 0 for n in names}
        self.total_peak = 0
        self.stop_ev = threading.Event()

    def run(self):
        while not self.stop_ev.is_set():
            total = 0
            for n in self.names:
                try:
                    m = self.api.stats(n)["mem"]
                    total += m
                    if m > self.peak[n]:
                        self.peak[n] = m
                except Exception:
                    pass
            if total > self.total_peak:
                self.total_peak = total
            self.stop_ev.wait(5)

    def stop(self):
        self.stop_ev.set()
        self.join(10)
        return self.peak


# ---------------------------------------------------------------- images

def git_archive(name, dest):
    folder, commit = CLONES[name]
    path = os.path.join(TEAM, folder)
    full = sh(["git", "-C", path, "rev-parse", commit + "^{commit}"]).stdout.decode().strip()
    data = sh(["git", "-C", path, "archive", "--format=tar", full]).stdout
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        tf.extractall(dest)
    return full


def build(args):
    ctx = os.path.join(RAW, "build-context")
    shutil.rmtree(ctx, ignore_errors=True)
    commit = harness_commit()
    commits = {n: git_archive(n, os.path.join(ctx, "fabric", "src", n)) for n in CLONES}
    tag = commit[:12]
    out = {"harness": commit, "commits": commits, "built_utc": now_utc(), "tags": {}}

    def bx(dockerfile, context, image, build_args):
        cmd = ["buildx", "build", "--load", "--progress=plain", "-f", os.path.join(REPO, "docker", dockerfile), "-t", image]
        for k, v in build_args.items():
            cmd += ["--build-arg", "%s=%s" % (k, v)]
        print("building %s ..." % image, flush=True)
        docker(*(cmd + [context]), capture=False)
        out["tags"][image.split(":")[0].split("/")[1]] = image
        out.setdefault("ids", {})[image] = docker("image", "inspect", "--format", "{{.Id}}", image).stdout.decode().strip()

    bx("Dockerfile.fabric", os.path.join(ctx, "fabric"), "qfp/fabric:%s" % commits["fabric"][:8],
       {"FABRIC_COMMIT": commits["fabric"], "FABRIC_CA_COMMIT": commits["fabric-ca"], "FABRIC_LIB_COMMIT": commits["fabric-lib-go"]})
    # chaincode: the verbatim chaincode and, if recorded, the live image's lock file
    cc = os.path.join(ctx, "chaincode")
    shutil.copytree(os.path.join(REPO, "network", "live", "chaincode"), os.path.join(cc, "chaincode"))
    shutil.copytree(os.path.join(REPO, "docker", "chaincode-lock"), os.path.join(cc, "lock"))
    lock = args.lock
    if lock == "auto":
        lock = "live" if os.path.exists(os.path.join(cc, "lock", "live-npm-ls.txt")) else "none"
    bx("Dockerfile.chaincode", cc, "qfp/chaincode:%s-%s" % (lock, tag), {"LOCK": lock})
    out["chaincode_lock"] = lock
    bx("Dockerfile.client", os.path.join(REPO, "client"), "qfp/client:%s" % tag, {"HARNESS_COMMIT": commit})
    bx("Dockerfile.analysis", os.path.join(REPO, "docker"), "qfp/analysis:%s" % tag, {})
    shutil.rmtree(ctx, ignore_errors=True)
    write_json(IMAGES, out)
    print(json.dumps(out, indent=1))


# ---------------------------------------------------------------- one network

def vol(netid, suffix=""):
    return "qfp-%s%s" % (netid, ("-" + suffix) if suffix else "")


def cname(name):
    return "qfp_" + name


def ensure_base():
    r = docker("network", "inspect", DOCKER_NET, check=False)
    if r.returncode != 0:
        docker("network", "create", "--label", LABEL, DOCKER_NET)
    r = docker("volume", "inspect", RESULTS_VOL, check=False)
    if r.returncode != 0:
        docker("volume", "create", "--label", LABEL, RESULTS_VOL)
        docker("run", "--rm", "--user", "0", "--label", LABEL, "-v", RESULTS_VOL + ":/out", "--entrypoint", "chown",
               images()["tags"]["fabric"], "1000:1000", "/out")


def tar_folder(folder):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for root, dirs, files in os.walk(folder):
            dirs.sort()
            for fn in sorted(files):
                p = os.path.join(root, fn)
                ti = tf.gettarinfo(p, arcname=os.path.relpath(p, folder))
                ti.uid = ti.gid = 1000
                ti.uname = ti.gname = ""
                with open(p, "rb") as f:
                    tf.addfile(ti, f)
    return buf.getvalue()


def load_volume(netid, folder):
    fab = images()["tags"]["fabric"]
    docker("volume", "create", "--label", LABEL, "--label", "org.qchain.qfp.net=" + netid, vol(netid))
    docker("run", "--rm", "-i", "--user", "0", "--label", LABEL, "-v", vol(netid) + ":/qfp", "--entrypoint", "sh", fab,
           "-c", "mkdir -p /qfp/net && tar -x -C /qfp/net && chown -R 1000:1000 /qfp", inp=tar_folder(folder))


def vol_cat(netid, path):
    r = docker("run", "--rm", "--label", LABEL, "-v", vol(netid) + ":/qfp:ro", "--entrypoint", "cat",
               images()["tags"]["fabric"], "/qfp/" + path)
    return r.stdout.decode().strip()


def tools(session, netid, script, timeout=900):
    t = time.time()
    r = docker("run", "--rm", "--network", DOCKER_NET, "--user", "1000:1000", "--label", LABEL,
               "-v", vol(netid) + ":/qfp", "-w", "/qfp/net", "--entrypoint", "bash", images()["tags"]["fabric"],
               "/qfp/net/scripts/" + script, check=False, timeout=timeout)
    out = (r.stdout + r.stderr).decode(errors="replace")
    with open(os.path.join(session_dir(session), "nets", netid, "tools-" + script + ".log"), "w") as f:
        f.write(out)
    if r.returncode != 0:
        raise RuntimeError("%s failed:\n%s" % (script, out[-3000:]))
    return time.time() - t


def start_container(netid, c, env_extra=None):
    im = images()["tags"]
    args = ["run", "-d", "--name", cname(c["name"]), "--hostname", c["name"], "--network", DOCKER_NET,
            "--network-alias", c["name"], "--user", "1000:1000", "--read-only", "--tmpfs", "/tmp:mode=1777",
            "--restart", "no", "--stop-timeout", "10",
            "--label", LABEL, "--label", "org.qchain.qfp.net=" + netid, "--label", "org.qchain.qfp.role=" + c["role"]]
    env = dict(c.get("env", {}))
    env.update(env_extra or {})
    for k in sorted(env):
        args += ["-e", "%s=%s" % (k, env[k])]
    for m in c.get("mounts", []):
        spec = "type=volume,src=%s,dst=%s" % (vol(netid), m["dst"])
        sub = m["sub"]
        spec += ",volume-subpath=%s" % sub
        if m["ro"]:
            spec += ",readonly"
        args += ["--mount", spec]
    if c.get("data"):
        args += ["--mount", "type=volume,src=%s,dst=%s" % (vol(netid, c["name"]), c["data"])]
    image = im["chaincode"] if c["image"] == "chaincode" else im["fabric"]
    args.append(image)
    args += c.get("cmd", [])
    docker(*args)


def wait_ready(name, pattern, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = docker("logs", cname(name), check=False)
        text = (r.stdout + r.stderr).decode(errors="replace")
        if pattern in text:
            return
        st = docker("inspect", "-f", "{{.State.Running}}", cname(name), check=False).stdout.decode().strip()
        if st != "true":
            raise RuntimeError("%s stopped:\n%s" % (name, text[-3000:]))
        time.sleep(1)
    raise RuntimeError("%s not ready after %d s" % (name, timeout))


def net_containers(topo):
    return [cname(c["name"]) for c in topo["containers"]]


def item_netid(it):
    """The network's id in the session: the generator's id, plus the item's tag when one topology and arm
    has several networks (an E1 network split in two, E3's networks)."""
    n = it["net"]
    base = qfp_gen.net_id(n["orgs"], n["peers"], n["identity"])
    return base + ("-" + it["tag"] if it.get("tag") else "")


def bring_up(session, item):
    """Generates, loads and starts one network; returns (netid, topology, setup timings)."""
    n = item["net"]
    netid = item_netid(item)
    ndir = os.path.join(session_dir(session), "nets", netid)
    gen = os.path.join(ndir, "gen")
    shutil.rmtree(gen, ignore_errors=True)
    os.makedirs(ndir, exist_ok=True)
    qfp_gen.write(qfp_gen.generate(n["orgs"], n["peers"], n["identity"]), gen)
    topo = read_json(os.path.join(gen, "topology.json"))
    teardown(netid)
    timings = {}
    t0 = time.time()
    load_volume(netid, gen)
    timings["crypto_s"] = tools(session, netid, "01-crypto.sh")
    t = time.time()
    for c in topo["containers"]:
        if c["stage"] == "ca":
            start_container(netid, c)
    for c in topo["containers"]:
        if c["stage"] == "ca":
            wait_ready(c["name"], c["ready"])
    timings["ca_start_s"] = time.time() - t
    timings["enroll_s"] = tools(session, netid, "03-enroll.sh")
    t = time.time()
    for c in topo["containers"]:
        if c["stage"] == "node":
            start_container(netid, c)
    for c in topo["containers"]:
        if c["stage"] == "node":
            wait_ready(c["name"], c["ready"])
    timings["node_start_s"] = time.time() - t
    timings["channel_s"] = tools(session, netid, "02-channel.sh")
    timings["install_s"] = tools(session, netid, "04-install.sh")
    t = time.time()
    for c in topo["containers"]:
        if c["stage"] == "chaincode":
            pkg = vol_cat(netid, c["env_file"]["CHAINCODE_ID"])
            start_container(netid, c, {"CHAINCODE_ID": pkg})
    time.sleep(2)
    timings["chaincode_start_s"] = time.time() - t
    timings["commit_s"] = tools(session, netid, "05-commit.sh")
    timings["network_up_s"] = time.time() - t0
    return netid, topo, timings


def teardown(netid):
    r = docker("ps", "-aq", "--filter", "label=org.qchain.qfp.net=" + netid)
    ids = r.stdout.decode().split()
    if ids:
        docker("rm", "-f", *ids)
    r = docker("volume", "ls", "-q", "--filter", "name=^" + vol(netid))
    vols = [v for v in r.stdout.decode().split() if v == vol(netid) or v.startswith(vol(netid) + "-")]
    if vols:
        docker("volume", "rm", "-f", *vols)


def down(args):
    r = docker("ps", "-aq", "--filter", "label=" + LABEL)
    ids = r.stdout.decode().split()
    if ids:
        docker("rm", "-f", *ids)
    # data volumes are created by `docker run --mount` without labels: select by the qfp- prefix
    r = docker("volume", "ls", "-q")
    vols = [v for v in r.stdout.decode().split() if v.startswith("qfp-") and (args.all or v != RESULTS_VOL)]
    if vols:
        docker("volume", "rm", "-f", *vols)
    print("removed %d containers, %d volumes" % (len(ids), len(vols)))


def client(session, netid, args, timeout=3600, mount_out=True):
    cmd = ["run", "--rm", "--network", DOCKER_NET, "--user", "1000:1000", "--read-only", "--tmpfs", "/tmp:mode=1777",
           "--label", LABEL, "--label", "org.qchain.qfp.net=" + netid,
           "--mount", "type=volume,src=%s,dst=/qfp,readonly" % vol(netid)]
    if mount_out:
        cmd += ["--mount", "type=volume,src=%s,dst=/out" % RESULTS_VOL]
    cmd += [images()["tags"]["client"]] + args
    r = docker(*cmd, check=False, timeout=timeout)
    out = r.stdout.decode(errors="replace").strip()
    err = r.stderr.decode(errors="replace").strip()
    if r.returncode != 0:
        raise RuntimeError("client %s failed: %s" % (args[0], (err or out)[-2000:]))
    last = out.splitlines()[-1] if out else "{}"
    try:
        return json.loads(last), out
    except ValueError:
        return {}, out


def copy_out(session, netid):
    """Copies the network's folder of the results volume into results/raw/<session>/nets/<netid>/out."""
    dest = os.path.join(session_dir(session), "nets", netid, "out")
    r = docker("run", "--rm", "--label", LABEL, "-v", RESULTS_VOL + ":/out:ro", "--entrypoint", "tar",
               images()["tags"]["fabric"], "-c", "-C", "/out/%s" % session, netid)
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        tmp = dest + ".tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tf.extractall(tmp)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(os.path.join(tmp, netid), dest)
    shutil.rmtree(tmp, ignore_errors=True)


def ledger_sizes(netid, topo):
    out = {}
    fab = images()["tags"]["fabric"]
    for c in topo["containers"]:
        if c.get("data"):
            r = docker("run", "--rm", "--label", LABEL, "-v", vol(netid, c["name"]) + ":/d:ro", "--entrypoint", "du",
                       fab, "-sb", "/d", check=False)
            try:
                out[c["name"]] = int(r.stdout.decode().split()[0])
            except (IndexError, ValueError):
                out[c["name"]] = -1
    return out


def colima_disk():
    """(used bytes, size bytes) of the Colima VM's Docker disk, or (None, None)."""
    r = sh(["colima", "ssh", "--profile", "qfp", "--", "df", "-P", "-k", "/var/lib/docker"], check=False, timeout=60)
    try:
        f = r.stdout.decode().splitlines()[1].split()
        return int(f[2]) * 1024, int(f[1]) * 1024
    except (IndexError, ValueError):
        return None, None


def colima_disk_pct():
    r = sh(["colima", "ssh", "--profile", "qfp", "--", "df", "-P", "/var/lib/docker"], check=False, timeout=60)
    try:
        return float(r.stdout.decode().splitlines()[1].split()[4].rstrip("%"))
    except (IndexError, ValueError):
        return -1.0


# ---------------------------------------------------------------- host quality

def host_rows(session, t_from_ns, t_to_ns):
    path = os.path.join(session_dir(session), "host", "host-all.csv")
    rows = []
    try:
        with open(path) as f:
            next(f)
            for line in f:
                p = line.strip().split(",")
                if len(p) < 5:
                    continue
                ts = int(p[0])
                if t_from_ns <= ts <= t_to_ns + 6 * 10**9:
                    rows.append({"other": float(p[1]), "throttle": int(p[2]), "on_ac": int(p[3]), "alert": int(p[4])})
    except FileNotFoundError:
        return None
    return rows


def swap_used_mb():
    r = sh(["sysctl", "-n", "vm.swapusage"], check=False)
    m = re.search(r"used = ([\d.]+)M", r.stdout.decode())
    return float(m.group(1)) if m else -1.0


def run_flags(session, th, t_from_ns, t_to_ns, swap0, swap1):
    flags = []
    rows = host_rows(session, t_from_ns, t_to_ns)
    if rows is None:
        flags.append("no_monitor")
    elif rows:
        if statistics.mean(r["other"] for r in rows) > th["other_cpu_pct_mean"]:
            flags.append("other_cpu")
        if any(r["throttle"] == 1 for r in rows):
            flags.append("thermal")
        if any(r["on_ac"] == 0 for r in rows):
            flags.append("battery")
        if any(r["alert"] == 1 for r in rows):
            flags.append("low_power")
    if swap0 >= 0 and swap1 >= 0 and swap1 - swap0 > th["swap_growth_mb"]:
        flags.append("swap")
    return flags


# ---------------------------------------------------------------- plans

def item(orgs, peers, identity, runs, extras=(), tag=None, e3_rep=None):
    it = {"net": {"orgs": orgs, "peers": peers, "identity": identity}, "runs": runs, "extras": list(extras)}
    if tag:
        it["tag"] = tag
    if e3_rep:
        it["e3_rep"] = e3_rep
    return it


def grid_runs(rng, reps=REPS, fns=("issue", "get"), tlevels=T_LEVELS):
    runs = [{"fn": f, "t": t, "rep": r} for f in fns for t in tlevels for r in range(1, reps + 1)]
    rng.shuffle(runs)
    return runs


def make_plan(kind, seed, th):
    rng = random.Random(seed)
    items = []
    if kind == "smoke":
        for ident in ("mldsa44", "ecdsa"):
            items.append(item(1, 1, ident, [{"fn": f, "t": t, "rep": 1} for f in ("issue", "get") for t in (1, 10, 100)],
                              ["e2_small"]))
    elif kind == "trial":
        # E0 (docs/plan.md section 8). The smallest topology, both arms, small bursts.
        small = [{"fn": f, "t": t, "rep": 1} for f in ("issue", "get") for t in (1, 10, 100)]
        for ident in ("mldsa44", "ecdsa"):
            items.append(item(1, 1, ident, [dict(r) for r in small]))
        # The C candidates on the fastest case, (2,2) (whose ECDSA arm is also E3's saturation reference),
        # and on the heaviest, (8,8), both arms each. Reads first, then writes with C rising, so that a
        # network that runs out of memory at a high C has already measured the lower ones.
        sweep = [{"fn": "get", "t": 10000, "rep": 1, "c": C_CANDIDATES[1]}] + \
                [{"fn": "issue", "t": 10000, "rep": 1, "c": c} for c in C_CANDIDATES]
        for ident in ("mldsa44", "ecdsa"):
            items.append(item(2, 2, ident, [dict(r) for r in sweep], ["e2_small", "e3_small"]))
        for ident in ("mldsa44", "ecdsa"):
            items.append(item(8, 8, ident, [dict(r) for r in sweep]))
        # eight peers with one endorsement, at the highest candidate (memory, orderer egress)
        top = C_CANDIDATES[-1]
        items.append(item(1, 8, "mldsa44", [{"fn": "get", "t": 10000, "rep": 1, "c": top},
                                            {"fn": "issue", "t": 10000, "rep": 1, "c": top}]))
    elif kind == "main":
        if not th.get("frozen"):
            raise SystemExit("thresholds are not frozen: run the trial, then `qfp.py freeze`")
        split = set(th.get("split") or [])
        # E1: one network per topology and arm (E2 inside the (2,2) networks); E3: one fresh (2,2) network
        # per arm and repetition. The units run in a seeded random order; the two arms of a unit back to
        # back, in random order.
        units = [("e1", o, p, None) for (o, p) in TOPOLOGIES] + [("e3", 2, 2, k) for k in range(1, REPS + 1)]
        rng.shuffle(units)
        for (exp, o, p, k) in units:
            arms = list(ARMS)
            rng.shuffle(arms)
            for ident in arms:
                if exp == "e3":
                    items.append(item(o, p, ident, [], ["e3"], tag="e3r%d" % k, e3_rep=k))
                    continue
                runs = grid_runs(rng)
                extras = ["e2"] if (o, p) == (2, 2) else []
                if qfp_gen.net_id(o, p, ident) in split:
                    items.append(item(o, p, ident, [r for r in runs if r["rep"] <= 3], extras, tag="part1"))
                    items.append(item(o, p, ident, [r for r in runs if r["rep"] > 3], [], tag="part2"))
                else:
                    items.append(item(o, p, ident, runs, extras))
    else:
        raise SystemExit("plan kind must be smoke, trial or main")
    for i, it in enumerate(items):
        it["seed"] = rng.randrange(1, 2**62)
        for j, r in enumerate(it["runs"]):
            r["id"] = "n%02d-r%03d" % (i + 1, j + 1)
            r["seed"] = rng.randrange(1, 2**62)
    return {"kind": kind, "seed": seed, "created_utc": now_utc(), "harness": harness_commit(),
            "images": read_json(IMAGES, {}), "thresholds": th, "items": items}


def plan_cmd(args):
    sdir = session_dir(args.session)
    if os.path.exists(os.path.join(sdir, "plan.json")):
        raise SystemExit("session %s already has a plan" % args.session)
    p = make_plan(args.kind, args.seed, thresholds())
    write_json(os.path.join(sdir, "plan.json"), p)
    n_runs = sum(len(i["runs"]) for i in p["items"])
    print("session %s: %d networks, %d runs (%s)" % (args.session, len(p["items"]), n_runs, args.kind))


# ---------------------------------------------------------------- running

def canary(session, netid, state):
    res, _ = client(session, netid, ["canary"], mount_out=False)
    rate = res.get("median_rate_per_s", 0)
    state.setdefault("canaries", []).append({"utc": now_utc(), "rate": rate, "net": netid})
    ref = state.get("canary_ref")
    if ref is None and len(state["canaries"]) >= 3:
        state["canary_ref"] = statistics.median(c["rate"] for c in state["canaries"][:3])
    return rate


def canary_drift(state, th):
    ref = state.get("canary_ref")
    if not ref:
        return False
    rate = state["canaries"][-1]["rate"]
    return (ref - rate) / ref * 100 > th["canary_drift_pct"]


def container_states(names):
    """Running, OOM-killed, exit code and restart count of every container (docker inspect)."""
    out = {}
    for n in names:
        r = docker("inspect", "-f", "{{.State.Running}}|{{.State.OOMKilled}}|{{.State.ExitCode}}|{{.RestartCount}}|{{.State.Error}}", n, check=False)
        p = r.stdout.decode().strip().split("|")
        if len(p) < 5:
            out[n] = {"running": False, "missing": True}
        else:
            out[n] = {"running": p[0] == "true", "oom": p[1] == "true", "exit": int(p[2] or 0), "restarts": int(p[3] or 0), "error": p[4]}
    return out


def save_diag(session, netid, tag, bad):
    """The last log lines of every container that is not running or was OOM-killed."""
    path = os.path.join(session_dir(session), "nets", netid, "diag-%s.txt" % tag)
    with open(path, "w") as f:
        for n, s in bad.items():
            f.write("== %s %s\n" % (n, json.dumps(s)))
            r = docker("logs", "--tail", "40", n, check=False)
            f.write((r.stdout + r.stderr).decode(errors="replace")[-6000:] + "\n")


def do_run(session, netid, topo, api, run, attempt, th, state):
    wall0 = time.time()
    rid = run["id"] + ("" if attempt == 1 else "-a%d" % attempt)
    out = "/out/%s/%s/runs/%s" % (session, netid, rid)
    # the trial sets C per run; the main session uses the frozen C; the smoke test (T <= 100) any candidate
    c = run.get("c") or th.get("c") or C_CANDIDATES[0]
    names = net_containers(topo)
    sampler = MemSampler(api, names)
    swap0 = swap_used_mb()
    s0 = api.snapshot(names)
    t_from = time.time_ns()
    sampler.start()
    args = ["run", "-fn", run["fn"], "-t", str(run["t"]), "-c", str(c), "-seed", str(run["seed"]), "-id", rid, "-out", out,
            "-holders", str(th["holders"]), "-poolfile", "/out/%s/%s/pool.txt" % (session, netid)]
    err = None
    try:
        res, _ = client(session, netid, args)
    except Exception as e:  # the run's failure is a result; the harness records it and goes on
        res, err = {}, str(e)[-1500:]
    peak = sampler.stop()
    t_to = time.time_ns()
    s1 = api.snapshot(names)
    swap1 = swap_used_mb()
    host = {}
    for n in names:
        a, b = s0.get(n, {}), s1.get(n, {})
        if "cpu_ns" in a and "cpu_ns" in b:
            host[n] = {"cpu_s": (b["cpu_ns"] - a["cpu_ns"]) / 1e9, "rx": b["rx"] - a["rx"], "tx": b["tx"] - a["tx"],
                       "mem_peak": peak.get(n, 0)}
        else:
            host[n] = {"error": a.get("error") or b.get("error")}
    states = container_states(names)
    bad = {n: s for n, s in states.items() if not s.get("running") or s.get("oom") or s.get("restarts")}
    if bad:
        save_diag(session, netid, run["id"] + "-a%d" % attempt, bad)
    flags = run_flags(session, th, t_from, t_to, swap0, swap1)
    rec = {"id": run["id"], "attempt": attempt, "run_dir": rid, "fn": run["fn"], "t": run["t"], "rep": run["rep"], "c": c,
           "seed": run["seed"], "start_ns": t_from, "end_ns": t_to, "result": res, "error": err, "flags": flags,
           "swap_mb": [swap0, swap1], "containers": host, "mem_total_peak": sampler.total_peak, "states": states,
           "wall_s": round(time.time() - wall0, 3)}
    write_json(os.path.join(session_dir(session), "nets", netid, "runs", rid + ".json"), rec)
    return rec


def run_network(session, idx, it, api, th, state):
    netid, topo, timings = bring_up(session, it)
    ndir = os.path.join(session_dir(session), "nets", netid)
    log(session, "network %s up in %.0f s" % (netid, timings["network_up_s"]))
    t = time.time()
    res, out = client(session, netid, ["setup", "-holders", str(th["holders"]), "-pool", str(th["pool"]),
                                       "-warm", str(th["warm"]), "-c", "100", "-seed", str(it["runs"][0]["seed"] if it["runs"] else it.get("seed", 1)),
                                       "-poolfile", "/out/%s/%s/pool.txt" % (session, netid)], timeout=3600)
    timings["setup_s"] = time.time() - t
    with open(os.path.join(ndir, "setup.log"), "w") as f:
        f.write(out + "\n")
    rate = canary(session, netid, state)
    last_canary = time.time()
    log(session, "setup done in %.0f s; canary %.0f/s" % (timings["setup_s"], rate))
    queue = [(r, 1) for r in it["runs"]]
    window = []
    records = []
    while queue:
        run, attempt = queue.pop(0)
        rec = do_run(session, netid, topo, api, run, attempt, th, state)
        records.append(rec)
        window.append(rec)
        r = rec["result"]
        log(session, "%s %s %s T=%d rep %d att %d: ok=%s tps=%s p50=%s ms flags=%s%s" % (
            netid, rec["id"], run["fn"], run["t"], run["rep"], attempt, r.get("ok"), r.get("tps"),
            r.get("lat_p50_ms"), ",".join(rec["flags"]) or "-", " ERROR" if rec["error"] else ""))
        repeatable = [f for f in rec["flags"] if f not in ("no_monitor",)]
        if repeatable and attempt < th["max_attempts"]:
            queue.append((run, attempt + 1))
        if time.time() - last_canary > th["canary_every_s"]:
            canary(session, netid, state)
            last_canary = time.time()
            if canary_drift(state, th):
                log(session, "canary %.0f/s drifted from the reference %.0f/s: the window's runs are repeated" % (
                    state["canaries"][-1]["rate"], state["canary_ref"]))
                for w in window:
                    w["flags"].append("canary")
                    write_json(os.path.join(ndir, "runs", w["run_dir"] + ".json"), w)
                    if w["attempt"] < th["max_attempts"]:
                        orig = [x for x in it["runs"] if x["id"] == w["id"]][0]
                        queue.append((orig, w["attempt"] + 1))
            window = []
        time.sleep(th["settle_s"])
        pct = colima_disk_pct()
        if pct > 85:
            raise RuntimeError("Colima disk at %.0f %%: network %s stopped (disk guard)" % (pct, netid))
    errors = {}
    for x in it["extras"]:
        try:
            run_extra(session, netid, it, x, th)
        except Exception as e:  # recorded in network.json; the network's runs, ledger and timings are kept
            errors[x] = str(e)[-1500:]
            log(session, "%s %s FAILED: %s" % (netid, x, str(e)[:300]))
    t = time.time()
    try:
        res, _ = client(session, netid, ["blocks", "-out", "/out/%s/%s/ledger" % (session, netid)], timeout=7200)
    except Exception as e:
        res = {"error": str(e)[-1500:]}
        errors["blocks"] = res["error"]
        log(session, "%s ledger read-back FAILED: %s" % (netid, str(e)[:300]))
    timings["blocks_dump_s"] = time.time() - t
    sizes = ledger_sizes(netid, topo)
    copy_out(session, netid)
    write_json(os.path.join(ndir, "network.json"), {"index": idx, "net": it["net"], "netid": netid, "timings": timings,
                                                    "ledger_bytes": sizes, "blocks": res, "end_utc": now_utc(),
                                                    "colima_disk_pct": colima_disk_pct(), "runs": len(records),
                                                    "errors": errors})
    teardown(netid)
    docker("run", "--rm", "--label", LABEL, "-v", RESULTS_VOL + ":/out", "--entrypoint", "rm", images()["tags"]["fabric"],
           "-rf", "/out/%s/%s" % (session, netid))
    log(session, "network %s done (%d runs%s)" % (netid, len(records), ", errors in " + ", ".join(errors) if errors else ""))


def run_extra(session, netid, it, x, th):
    """E2, E3 and their short trial checks, after a network's runs."""
    xdir = "/out/%s/%s/extras/%s" % (session, netid, x)
    pool = "/out/%s/%s/pool.txt" % (session, netid)
    if x in ("e2", "e2_small"):
        n = th["e2_n"] if x == "e2" else 20
        for rep in range(1, (REPS if x == "e2" else 1) + 1):
            res, _ = client(session, netid, ["conn", "-n", str(n), "-poolfile", pool, "-seed", str(rep),
                                             "-out", "%s/rep%d" % (xdir, rep)])
            log(session, "%s E2 rep %d: %s" % (netid, rep, json.dumps(res)[:200]))
    elif x == "e3":
        # one repetition of the offered-load sweep: the seven rates in a seeded random order
        rng_x = random.Random(it["seed"])
        jobs = list(E3_FRACTIONS)
        rng_x.shuffle(jobs)
        for f in jobs:
            rate = round(th["e3_saturation_tps"] * f, 2)
            res, _ = client(session, netid, ["load", "-rate", str(rate), "-dur", "%ds" % th["e3_duration_s"],
                                             "-seed", str(rng_x.randrange(1, 2**31)), "-holders", str(th["holders"]),
                                             "-out", "%s/f%03d-rep%d" % (xdir, round(f * 100), it["e3_rep"])])
            log(session, "%s E3 %.0f%% rep %d: %s" % (netid, f * 100, it["e3_rep"], json.dumps(res)[:200]))
            time.sleep(th["settle_s"])
    elif x == "e3_small":
        # the trial's check of the load client: one short level at a low fixed rate
        res, _ = client(session, netid, ["load", "-rate", str(E3_SMALL_RATE), "-dur", "20s", "-seed", "1",
                                         "-holders", str(th["holders"]), "-out", "%s/small" % xdir])
        log(session, "%s E3 check: %s" % (netid, json.dumps(res)[:200]))
        time.sleep(th["settle_s"])
    else:
        raise RuntimeError("unknown extra %s" % x)


def run_cmd(args):
    session = args.session
    sdir = session_dir(session)
    plan = read_json(os.path.join(sdir, "plan.json"))
    if not plan:
        raise SystemExit("no plan for session %s" % session)
    if plan["images"].get("ids") != images().get("ids"):
        raise SystemExit("the images changed since the plan was written; make a new session")
    th = plan["thresholds"]
    state = read_json(os.path.join(sdir, "state.json"), {"done": [], "started_utc": now_utc()})
    api = DockerAPI()
    ensure_base()
    for idx, it in enumerate(plan["items"]):
        key = "n%02d" % (idx + 1)
        if key in state["done"]:
            continue
        log(session, "network %d/%d: %s" % (idx + 1, len(plan["items"]), json.dumps(it["net"])))
        t = time.time()
        try:
            run_network(session, idx, it, api, th, state)
        except Exception as e:
            log(session, "network %s FAILED: %s" % (key, e))
            state.setdefault("failures", []).append({"item": key, "utc": now_utc(), "error": str(e)[-3000:]})
            write_json(os.path.join(sdir, "state.json"), state)
            if args.stop_on_error:
                raise
            teardown(item_netid(it))
            continue
        state["done"].append(key)
        state.setdefault("durations", {})[key] = time.time() - t
        write_json(os.path.join(sdir, "state.json"), state)
    state["finished_utc"] = now_utc()
    write_json(os.path.join(sdir, "state.json"), state)
    log(session, "session %s finished" % session)


def status_cmd(args):
    sdir = session_dir(args.session)
    plan = read_json(os.path.join(sdir, "plan.json"))
    state = read_json(os.path.join(sdir, "state.json"), {"done": []})
    n = len(plan["items"])
    d = len(state["done"])
    print("session %s (%s): %d of %d networks done" % (args.session, plan["kind"], d, n))
    durs = list(state.get("durations", {}).values())
    if durs:
        left = statistics.mean(durs) * (n - d)
        print("mean %.0f min per network; about %.1f h left" % (statistics.mean(durs) / 60, left / 3600))
    for f in state.get("failures", []):
        print("FAILED %s at %s: %s" % (f["item"], f["utc"], f["error"].splitlines()[0][:200]))
    nets = os.path.join(sdir, "nets")
    for netid in sorted(os.listdir(nets)) if os.path.isdir(nets) else []:
        errs = (read_json(os.path.join(nets, netid, "network.json"), {}) or {}).get("errors") or {}
        if errs:
            print("ERRORS in %s (network kept): %s" % (netid, ", ".join(sorted(errs))))


# ---------------------------------------------------------------- trial report and freeze

def load_runs(session):
    out = []
    nets = os.path.join(session_dir(session), "nets")
    for netid in sorted(os.listdir(nets)) if os.path.isdir(nets) else []:
        rdir = os.path.join(nets, netid, "runs")
        for fn in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
            rec = read_json(os.path.join(rdir, fn))
            summ = read_json(os.path.join(nets, netid, "out", "runs", rec["run_dir"], "summary.json"), {})
            rec["netid"], rec["summary"] = netid, summ
            out.append(rec)
    return out


def survived(r):
    """A run survived when every transaction succeeded and no container of the network was down after it."""
    down = any(not v.get("running", True) or v.get("oom") or v.get("restarts") for v in r.get("states", {}).values())
    return r["summary"].get("ok", 0) == r["t"] and not down


def load_index(o, p):
    """The size of a topology for the projections: log2(organisations) + log2(peers)."""
    return math.log2(o) + math.log2(p)


def interp(points, x, geometric=True):
    """A value at x from measured points (x, value): interpolated between the two nearest points (geometrically
    or linearly), the nearest point's value outside them, None without points. Points at the same x are averaged."""
    by = {}
    for a, b in points:
        if b is not None and b > 0:
            by.setdefault(a, []).append(b)
    if not by:
        return None
    pts = sorted((a, statistics.mean(v)) for a, v in by.items())
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, v0), (x1, v1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            f = (x - x0) / (x1 - x0)
            return v0 * (v1 / v0) ** f if geometric else v0 + (v1 - v0) * f
    return pts[-1][1]


def trial_report(args):
    """The trial's findings and what they mean for the main session (docs/plan.md section 8): the C choice,
    E3's saturation reference, memory, and the disk and time projections. Nothing is decided here: the
    project lead approves the values, then `qfp.py freeze`."""
    runs = load_runs(args.session)
    if not runs:
        raise SystemExit("no runs in %s" % args.session)
    th = thresholds()
    sdir = session_dir(args.session)
    setup_writes = 2 * th["holders"] + th["pool"] + th["warm"]
    rep = {"session": args.session, "c_candidates": C_CANDIDATES}

    def tput(r):
        return r["summary"].get("throughput_all_peers_tps")

    # 1. C: per case, the candidates that completed all 10,000 writes with no container down in at least one
    # attempt, and among them those within 5 % of the case's best throughput; C is the smallest candidate
    # within 5 % in both cases
    rep["c_cases"], sets, best_of = {}, [], {}
    for case, netid in C_CASES:
        per_c = {}
        for r in runs:
            if r["netid"] == netid and r["fn"] == "issue" and r["t"] == 10000 and r["c"] in C_CANDIDATES:
                d = per_c.setdefault(r["c"], {"attempts": 0, "failed_attempts": 0, "tps": []})
                d["attempts"] += 1
                if survived(r):
                    d["tps"].append(tput(r))
                else:
                    d["failed_attempts"] += 1
        tps = {c: statistics.median(d["tps"]) for c, d in per_c.items() if d["tps"]}
        best = max(tps.values()) if tps else None
        best_of[netid] = best
        within = sorted(c for c, v in tps.items() if v >= 0.95 * best) if best else []
        rep["c_cases"][case] = {
            "network": netid, "within_5pct_of_best": within,
            "candidates": {str(c): {"attempts": d["attempts"], "failed_attempts": d["failed_attempts"],
                                    "write_tps": round(tps[c], 1) if c in tps else None}
                           for c, d in sorted(per_c.items())}}
        sets.append(set(within))
    common = set.intersection(*sets) if len(sets) == len(C_CASES) else set()
    rep["c_choice"] = min(common) if common else None
    c_used = rep["c_choice"]

    # 2. E3's reference: the best ECDSA write throughput at (2,2), and the ML-DSA-44 one for comparison
    rep["e3_saturation_tps"] = round(best_of["o2p2-ecdsa"], 1) if best_of.get("o2p2-ecdsa") else None
    mldsa_22 = [tput(r) for r in runs if r["netid"] == "o2p2-mldsa44" and r["fn"] == "issue" and r["t"] == 10000 and survived(r)]
    cap = {"ecdsa": best_of.get("o2p2-ecdsa"), "mldsa44": max(mldsa_22) if mldsa_22 else None}
    rep["write_tps_2x2_best"] = {a: round(v, 1) if v else None for a, v in cap.items()}
    rep["containers_down"] = sorted({"%s %s %s" % (r["netid"], r["id"], n) for r in runs
                                     for n, v in r.get("states", {}).items()
                                     if not v.get("running", True) or v.get("oom") or v.get("restarts")})

    # 3. per network: memory peaks, ledger bytes per write, timings
    vm_mem = docker("info", "--format", "{{.MemTotal}}", check=False).stdout.decode().strip()
    vm_mem = int(vm_mem) if vm_mem.isdigit() else 0
    rep["vm_memory_mb"] = round(vm_mem / 2**20)
    nets = os.path.join(sdir, "nets")
    rep["networks"] = {}
    for netid in sorted(os.listdir(nets)):
        nj = read_json(os.path.join(nets, netid, "network.json"), {})
        mine = [r for r in runs if r["netid"] == netid]
        peaks = {}
        for r in mine:
            for c, v in r["containers"].items():
                peaks[c] = max(peaks.get(c, 0), v.get("mem_peak", 0) or 0)
        total = max([r.get("mem_total_peak", 0) or 0 for r in mine] or [0])
        writes = sum(r["summary"].get("ok", 0) for r in mine if r["fn"] == "issue") + setup_writes
        xdir = os.path.join(nets, netid, "out", "extras")
        for root, _, files in os.walk(xdir):
            if "summary.json" in files and os.path.basename(os.path.dirname(root)).startswith("e3"):
                writes += read_json(os.path.join(root, "summary.json"), {}).get("ok", 0)
        led = nj.get("ledger_bytes", {})
        peer_b = [v for k, v in led.items() if k.startswith("peer") and v > 0]
        tm = nj.get("timings") or {}
        m = re.match(r"o(\d+)p(\d+)-(ecdsa|mldsa44)$", netid)
        rep["networks"][netid] = {
            "net": {"orgs": int(m.group(1)), "peers": int(m.group(2)), "identity": m.group(3)} if m else None,
            "done": bool(nj), "errors": nj.get("errors") or {}, "writes": writes,
            "mem_gateway_peer_peak_mb": round(peaks.get("qfp_peer0.general.uae.com", 0) / 2**20),
            "mem_largest_container": max(peaks, key=peaks.get) if peaks else None,
            "mem_total_peak_mb": round(total / 2**20),
            "mem_total_peak_pct_of_vm": round(total / vm_mem * 100, 1) if vm_mem else None,
            "ledger_bytes_per_write_per_peer": round(statistics.mean(peer_b) / writes) if peer_b else None,
            "network_up_s": tm.get("network_up_s"), "setup_s": tm.get("setup_s"), "blocks_dump_s": tm.get("blocks_dump_s"),
        }
    worst = max((v["mem_total_peak_pct_of_vm"] or 0) for v in rep["networks"].values())
    rep["memory_warning"] = worst > 85
    rep["memory_note"] = ("a network used %.0f %% of the Colima VM's memory (above 85 %%): decide before the main run "
                          "(stop the Fabric CAs during measurement, or a larger Colima VM)" % worst) if worst > 85 else \
        "largest network total %.0f %% of the Colima VM's memory" % worst

    # 4. projections for the main session, from the trial's networks (geometric interpolation over the
    # topology size log2(O) + log2(P); bytes per write linear in the endorsements)
    meas = {a: {"w": [], "r": [], "up": [], "dump": [], "bpw": []} for a in ARMS}
    for netid, v in rep["networks"].items():
        n = v["net"]
        if not n:
            continue
        a, x = n["identity"], load_index(n["orgs"], n["peers"])
        if v["network_up_s"] is not None and v["setup_s"] is not None:
            meas[a]["up"].append((x, v["network_up_s"] + v["setup_s"]))
        if v["blocks_dump_s"] and v["writes"]:
            meas[a]["dump"].append((x, v["blocks_dump_s"] / v["writes"]))
        if v["ledger_bytes_per_write_per_peer"]:
            meas[a]["bpw"].append((n["orgs"] // 2 + 1, v["ledger_bytes_per_write_per_peer"]))
        for fn, key in (("issue", "w"), ("get", "r")):
            sel = [r for r in runs if r["netid"] == netid and r["fn"] == fn and r["t"] == 10000 and survived(r)]
            at_c = [tput(r) for r in sel if c_used and r["c"] == c_used]
            vals = at_c or [tput(r) for r in sel]
            if vals:
                meas[a][key].append((x, statistics.median(vals)))
    over = [r["wall_s"] - (r["summary"].get("execution_time_all_peers_s") or 0) for r in runs
            if r.get("wall_s") and r["summary"].get("ok")]
    per_run = (statistics.median(over) if over else 20) + th["settle_s"] + 1
    e2_s = 0.0
    for root, _, files in os.walk(nets):
        if "summary.json" in files and os.path.basename(os.path.dirname(root)) == "e2_small":
            res = read_json(os.path.join(root, "summary.json"), {}).get("result", {})
            ms = sum((res.get(m) or {}).get("p50_ms", 0) for m in ("fresh_connection", "open_connection"))
            e2_s = max(e2_s, REPS * th["e2_n"] * ms / 1000)
    used, size = colima_disk()
    rep["colima_disk_now_gb"] = {"used": round(used / 1e9, 1) if used else None, "size": round(size / 1e9, 1) if size else None}
    w_e1 = sum(T_LEVELS) * REPS
    plan_rows, total_s = [], 0.0

    def disk_pct(b):
        return round((used + b) / size * 100, 1) if used and size else None

    for (o, p) in TOPOLOGIES:
        x = load_index(o, p)
        for a in ARMS:
            m = meas[a]
            w, r_, up, dump = interp(m["w"], x), interp(m["r"], x), interp(m["up"], x), interp(m["dump"], x)
            bpw = interp(m["bpw"], o // 2 + 1, geometric=False)
            if not (w and r_):
                plan_rows.append({"network": qfp_gen.net_id(o, p, a), "hours": None, "note": "no rate measured for this arm"})
                continue
            t = (up or 120) + w_e1 / w + w_e1 / r_ + 2 * len(T_LEVELS) * REPS * per_run + REPS * 3 * 2 \
                + (dump or 0) * (w_e1 + setup_writes) + (e2_s if (o, p) == (2, 2) else 0)
            disk = bpw * (w_e1 + setup_writes) * (p + 1) + 0.2e9 if bpw else None
            disk1 = bpw * (0.6 * w_e1 + setup_writes) * (p + 1) + 0.2e9 if bpw else None
            pct = disk_pct(disk) if disk else None
            plan_rows.append({"network": qfp_gen.net_id(o, p, a), "hours": round(t / 3600, 2),
                              "write_tps": round(w, 1), "read_tps": round(r_, 1),
                              "disk_gb": round(disk / 1e9, 1) if disk else None, "disk_pct": pct,
                              "split_proposed": bool(pct and pct > DISK_SPLIT_PCT),
                              "disk_pct_if_split": disk_pct(disk1) if disk1 else None})
            total_s += t
    sat = rep["e3_saturation_tps"]
    for a in ARMS:
        x = load_index(2, 2)
        m = meas[a]
        up, dump, bpw = interp(m["up"], x), interp(m["dump"], x), interp(m["bpw"], 2, geometric=False)
        writes = sum(min(f * sat, cap[a] or f * sat) * th["e3_duration_s"] for f in E3_FRACTIONS) if sat else 0
        t = (up or 120) + len(E3_FRACTIONS) * (th["e3_duration_s"] + th["settle_s"] + 10) + (dump or 0) * (writes + setup_writes)
        disk = bpw * (writes + setup_writes) * 3 + 0.2e9 if bpw else None
        plan_rows.append({"network": qfp_gen.net_id(2, 2, a) + "-e3r<k> (x%d)" % REPS, "hours": round(REPS * t / 3600, 2),
                          "writes_per_network": round(writes), "disk_gb": round(disk / 1e9, 1) if disk else None,
                          "disk_pct": disk_pct(disk) if disk else None})
        total_s += REPS * t
    rep["projection"] = {
        "hours_expected": round(total_s * 1.15 / 3600, 1),
        "assumptions": "per network: bring-up and setup, 55,555 writes and 55,555 reads at the interpolated rates, "
                       "%.0f s per run outside the burst, the ledger read-back; E3: 7 levels of %d s per network; "
                       "plus 15 %% for repeated runs" % (per_run, th["e3_duration_s"]),
        "networks": plan_rows,
        "split_proposed": [r["network"] for r in plan_rows if r.get("split_proposed")],
        "note": "the project lead decides any reduction of the grid; nothing is capped automatically",
    }
    write_json(os.path.join(sdir, "trial-report.json"), rep)
    print(json.dumps(rep, indent=1))


def freeze(args):
    th = thresholds()
    if th.get("frozen") and not args.force:
        raise SystemExit("thresholds already frozen")
    valid = {qfp_gen.net_id(o, p, a) for (o, p) in TOPOLOGIES for a in ARMS}
    bad = [n for n in args.split if n not in valid]
    if bad:
        raise SystemExit("--split takes E1 network ids such as o8p8-mldsa44; unknown: %s" % ", ".join(bad))
    th.update({"frozen": True, "c": args.c, "e3_saturation_tps": args.saturation, "split": sorted(set(args.split)),
               "frozen_utc": now_utc()})
    write_json(CONFIG, th)
    print(json.dumps(th, indent=1))


def analysis_image():
    return images()["tags"]["analysis"]


def analyse(args):
    """Runs analysis/run_all.py in the analysis image on one session; the session's files go in and the
    tables and figures come out as tar streams (the Colima VM has no host mounts)."""
    sdir = session_dir(args.session)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        tf.add(os.path.join(REPO, "analysis"), arcname="analysis",
               filter=lambda ti: None if "__pycache__" in ti.name else ti)
        nets = os.path.join(sdir, "nets")
        for netid in sorted(os.listdir(nets)):
            for sub in ("network.json", "runs", "out", os.path.join("gen", "client.json")):
                p = os.path.join(nets, netid, sub)
                if os.path.exists(p):
                    tf.add(p, arcname=os.path.join("session", "nets", netid, sub))
    script = ("mkdir -p /tmp/w && tar -x -C /tmp/w && cd /tmp/w && "
              "python3 analysis/run_all.py session out >&2; s=$?; tar -c -C /tmp/w out; exit $s")
    r = docker("run", "--rm", "-i", "--label", LABEL, "--entrypoint", "sh", analysis_image(), "-c", script,
               inp=buf.getvalue(), check=False)
    sys.stderr.write(r.stderr.decode(errors="replace"))
    dest = os.path.join(sdir, "analysis")
    shutil.rmtree(dest, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        tf.extractall(sdir + ".analysis.tmp")
    os.replace(os.path.join(sdir + ".analysis.tmp", "out"), dest)
    shutil.rmtree(sdir + ".analysis.tmp", ignore_errors=True)
    print("analysis written to results/raw/%s/analysis (exit %d)" % (args.session, r.returncode))
    sys.exit(r.returncode)


def analysis_selftest(args):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        tf.add(os.path.join(REPO, "analysis"), arcname="analysis", filter=lambda ti: None if "__pycache__" in ti.name else ti)
    r = docker("run", "--rm", "-i", "--label", LABEL, "--entrypoint", "sh", analysis_image(), "-c",
               "mkdir -p /tmp/w && tar -x -C /tmp/w && cd /tmp/w && python3 analysis/selftest.py",
               inp=buf.getvalue(), check=False, capture=False)
    sys.exit(r.returncode)


def privacy_patterns():
    """The Mac's identifying strings (host and user names, home path, addresses, serial): held in memory only."""
    pats = set()
    for cmd in (["hostname"], ["hostname", "-s"], ["scutil", "--get", "ComputerName"], ["scutil", "--get", "LocalHostName"],
                ["id", "-un"], ["id", "-F"]):
        r = sh(cmd, check=False)
        pats.add(r.stdout.decode().strip())
    pats.add(os.path.expanduser("~"))
    ifc = sh(["ifconfig", "-a"], check=False).stdout.decode()
    pats.update(m for m in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", ifc) if not m.startswith("127."))
    pats.update(re.findall(r"ether ([0-9a-f:]{17})", ifc))
    io_ = sh(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], check=False).stdout.decode()
    pats.update(re.findall(r'"IOPlatform(?:SerialNumber|UUID)" = "([^"]+)"', io_))
    return sorted(p for p in pats if len(p) >= 4)


def publish(args):
    """Copies a session's results into results/<session>/ (committed): the analysis, the per-network records
    and the client's files, without the generated configuration; scans every file for the Mac's identifying
    text and writes SHA256SUMS last."""
    import gzip
    import hashlib
    sdir = session_dir(args.session)
    dest = os.path.join(REPO, "results", args.session)
    if os.path.exists(dest):
        raise SystemExit("%s exists" % dest)
    tmp = dest + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    for name in ("plan.json", "state.json", "driver.log", "trial-report.json", "session-host.txt"):
        if os.path.exists(os.path.join(sdir, name)):
            os.makedirs(tmp, exist_ok=True)
            shutil.copy2(os.path.join(sdir, name), tmp)
    for sub in ("analysis", "host"):
        if os.path.isdir(os.path.join(sdir, sub)):
            shutil.copytree(os.path.join(sdir, sub), os.path.join(tmp, sub))
    nets = os.path.join(sdir, "nets")
    for netid in sorted(os.listdir(nets)):
        for sub in ("network.json", "runs", "out", "setup.log", os.path.join("gen", "client.json"), os.path.join("gen", "topology.json")):
            src = os.path.join(nets, netid, sub)
            dst = os.path.join(tmp, "nets", netid, sub)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            elif os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
    pats = [p.lower() for p in privacy_patterns()]
    bad = []
    for root, _, files in os.walk(tmp):
        for fn in files:
            p = os.path.join(root, fn)
            data = gzip.open(p).read() if fn.endswith(".gz") else open(p, "rb").read()
            low = data.decode(errors="replace").lower()
            if any(x in low for x in pats):
                bad.append(os.path.relpath(p, tmp))
    if bad:
        raise SystemExit("privacy scan: identifying text in %d file(s), nothing published:\n  %s" % (len(bad), "\n  ".join(bad[:20])))
    lines = []
    for root, _, files in os.walk(tmp):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            lines.append("%s  ./%s" % (hashlib.sha256(open(p, "rb").read()).hexdigest(), os.path.relpath(p, tmp)))
    with open(os.path.join(tmp, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sorted(lines, key=lambda l: l.split("  ", 1)[1])) + "\n")
    os.replace(tmp, dest)
    print("published %d files to results/%s (privacy scan passed)" % (len(lines), args.session))


def selfcheck(args):
    bad = qfp_gen.selfcheck()
    r = subprocess.run(["shasum", "-a", "256", "-c", "SHA256SUMS"], cwd=os.path.join(REPO, "network", "live"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("network/live checksums: %s" % ("ok" if r.returncode == 0 else "FAILED"))
    bad += r.returncode != 0
    for name, (folder, commit) in CLONES.items():
        p = os.path.join(TEAM, folder)
        ok = sh(["git", "-C", p, "cat-file", "-e", commit + "^{commit}"], check=False).returncode == 0
        print("clone %s has %s: %s" % (folder, commit[:8], "yes" if ok else "NO"))
        bad += not ok
    # the verbatim copies against the live repository at its current commit
    live = os.path.join(TEAM, "qchain-network")
    for root, _, files in os.walk(os.path.join(REPO, "network", "live")):
        for fn in files:
            if fn in ("SHA256SUMS", "README.md"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), os.path.join(REPO, "network", "live"))
            src = os.path.join(live, rel)
            same = os.path.exists(src) and open(src, "rb").read() == open(os.path.join(root, fn), "rb").read()
            if not same:
                print("DIFFERS from qchain-network: %s" % rel)
                bad += 1
    if shutil.which("docker"):
        r = docker("info", "--format", "{{.Architecture}} {{.NCPU}} {{.MemTotal}} {{.ServerVersion}}", check=False)
        print("docker: %s" % (r.stdout.decode().strip() or "not reachable"))
    else:
        print("docker: not installed")
    print("selfcheck: %s" % ("ok" if not bad else "%d problem(s)" % bad))
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--lock", default="auto", choices=["auto", "live", "none"])
    sub.add_parser("selfcheck")
    p = sub.add_parser("plan")
    p.add_argument("kind", choices=["smoke", "trial", "main"])
    p.add_argument("session")
    p.add_argument("--seed", type=int, default=20261116)
    r = sub.add_parser("run")
    r.add_argument("session")
    r.add_argument("--stop-on-error", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("session")
    t = sub.add_parser("trial-report")
    t.add_argument("session")
    f = sub.add_parser("freeze")
    f.add_argument("--c", type=int, required=True, choices=C_CANDIDATES)
    f.add_argument("--saturation", type=float, required=True, help="E3's reference: the trial's ECDSA write saturation at (2,2)")
    f.add_argument("--split", nargs="*", default=[], help="E1 networks to run as two networks, e.g. o8p8-mldsa44")
    f.add_argument("--force", action="store_true")
    an = sub.add_parser("analyse")
    an.add_argument("session")
    sub.add_parser("analysis-selftest")
    pb = sub.add_parser("publish")
    pb.add_argument("session")
    d = sub.add_parser("down")
    d.add_argument("--all", action="store_true", help="also the results volume")
    a = ap.parse_args()
    {"build": build, "selfcheck": selfcheck, "plan": plan_cmd, "run": run_cmd, "status": status_cmd,
     "trial-report": trial_report, "freeze": freeze, "down": down, "analyse": analyse,
     "analysis-selftest": analysis_selftest, "publish": publish}[a.cmd](a)


if __name__ == "__main__":
    main()
