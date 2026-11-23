#!/usr/bin/env python3
"""run_all.py: from one session's raw files to the study's tables and figures.

    python3 analysis/run_all.py <session folder> <output folder>

The session folder is results/raw/<session> (written by scripts/qfp.py run): for every network
nets/<netid>/runs/<run>.json (the driver's record: attempt, flags, per-container CPU, network and
memory) and nets/<netid>/out/ (the client's files: runs/<run>/tx.csv.gz, summary.json; extras/;
ledger/txbytes.csv.gz, blocks.csv.gz), plus nets/<netid>/network.json. E1's networks hold the runs
(an E1 network split in two has two folders, `-part1` and `-part2`, whose runs form the same cells);
E2's files are in the (2,2) networks' extras/e2/; E3's networks (`-e3r<k>`) hold only extras/e3/.

Rules (docs/plan.md sections 6 and 7):
- the headline attempt of a run is its first attempt without a quality flag (other CPU on the
  study's CPUs, steal, CPU isolation, system activity, swap, canary); a run whose attempts are all flagged keeps its last
  attempt, marked in runs.csv, and is reported;
- a cell (identity, organisations, peers, function, T) is summarised by the median of its
  repetitions with a 95 % percentile bootstrap interval (10,000 resamples of the repetitions);
- a comparison is ML-DSA-44 / ECDSA of the two cells' medians, with a bootstrap interval made by
  resampling each arm's repetitions independently; it counts as a difference when the interval
  excludes 1.
"""
import csv
import gzip
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figstyle as fs  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

B = 10000
RNG = np.random.default_rng(20261116)
REPEATABLE = {"other_cpu", "steal", "cpuset", "system_activity", "swap", "canary"}
MEM_ROLES = ["gateway peer", "other peers", "orderer", "chaincode", "ca"]


# ------------------------------------------------------------------------------------------ loading

def read_json(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def read_csvgz(p):
    if not os.path.exists(p):
        return []
    with gzip.open(p, "rt", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def run_metrics(rec, txs):
    """M1-M6 of one attempt, from its transactions (times in ns since t0)."""
    fn = rec["fn"]
    ok = [t for t in txs if t["ok"] == "true"]
    send = [int(t["send_ns"]) for t in txs if int(t["send_ns"]) >= 0]
    m = {"n": len(txs), "ok": len(ok), "failed": len(txs) - len(ok)}
    if not ok or not send:
        return m
    first = min(send)
    if fn == "issue":
        done = [t for t in ok if int(t["all_commit_ns"]) >= 0]
        conf = np.array([int(t["all_commit_ns"]) for t in done], dtype=float)
        lat = np.array([int(t["all_commit_ns"]) - int(t["send_ns"]) for t in done], dtype=float) / 1e6
        latgw = np.array([int(t["gw_commit_ns"]) - int(t["send_ns"]) for t in ok], dtype=float) / 1e6
        st = {
            "endorse": [int(t["endorsed_ns"]) - int(t["send_ns"]) for t in ok],
            "order": [int(t["submitted_ns"]) - int(t["endorsed_ns"]) for t in ok],
            "commit": [int(t["gw_commit_ns"]) - int(t["submitted_ns"]) for t in ok],
            "spread": [max(0, int(t["all_commit_ns"]) - int(t["gw_commit_ns"])) for t in done],
        }
        for k, v in st.items():
            m["stage_%s_ms" % k] = float(np.median(v)) / 1e6 if v else float("nan")
        m["blocks_used"] = len({t["block"] for t in ok})
        n_conf = len(done)
    else:
        conf = np.array([int(t["gw_commit_ns"]) for t in ok], dtype=float)
        lat = np.array([int(t["gw_commit_ns"]) - int(t["send_ns"]) for t in ok], dtype=float) / 1e6
        latgw = lat
        n_conf = len(ok)
    if len(conf) == 0:
        return m
    m["exec_s"] = (conf.max() - first) / 1e9
    m["tps"] = n_conf / m["exec_s"] if m["exec_s"] > 0 else float("nan")
    m["lat_mean_ms"], m["lat_p50_ms"] = float(lat.mean()), pct(lat, 50)
    m["lat_p95_ms"], m["lat_p99_ms"], m["lat_max_ms"] = pct(lat, 95), pct(lat, 99), float(lat.max())
    m["latgw_p50_ms"] = pct(latgw, 50)
    m["response_mean_ms"] = float(conf.mean()) / 1e6
    return m


def role_of(container, gateway):
    n = container[4:] if container.startswith("qfp_") else container
    if n == gateway:
        return "gateway peer"
    if n.startswith("peer"):
        return "other peers"
    if n.startswith("orderer"):
        return "orderer"
    if n.startswith("chaincode"):
        return "chaincode"
    if n.startswith("ca."):
        return "ca"
    return "other"


def load(session):
    runs, nets = [], {}
    ndir = os.path.join(session, "nets")
    for netid in sorted(os.listdir(ndir)):
        nj = read_json(os.path.join(ndir, netid, "network.json"))
        if not nj:
            continue
        cj = read_json(os.path.join(ndir, netid, "gen", "client.json"), {})
        nets[netid] = dict(nj, client=cj)
        gw = cj.get("gateway", {}).get("name", "peer0.general.uae.com")
        rdir = os.path.join(ndir, netid, "runs")
        for fn in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:   # E3's networks have no runs
            rec = read_json(os.path.join(rdir, fn))
            base = os.path.join(ndir, netid, "out", "runs", rec["run_dir"])
            txs = read_csvgz(os.path.join(base, "tx.csv.gz"))
            summ = read_json(os.path.join(base, "summary.json"), {})
            r = {"netid": netid, "identity": nj["net"]["identity"], "orgs": nj["net"]["orgs"], "peers": nj["net"]["peers"],
                 "endorsements": cj.get("endorsements"), "run": rec["id"],
                 "attempt": rec["attempt"], "fn": rec["fn"], "t": rec["t"], "rep": rec["rep"], "c": rec["c"],
                 "flags": ";".join(rec.get("flags", [])), "error": (rec.get("error") or "")[:200],
                 "client_cpu_s": summ.get("client_cpu_s", float("nan"))}
            r.update(run_metrics(rec, txs))
            per_role = {}
            for c, v in rec.get("containers", {}).items():
                if "cpu_s" in v:
                    k = role_of(c, gw)
                    per_role.setdefault(k, {"cpu_s": 0.0, "tx": 0, "rx": 0})
                    per_role[k]["cpu_s"] += v["cpu_s"]
                    per_role[k]["tx"] += v["tx"]
                    per_role[k]["rx"] += v["rx"]
            for k, v in per_role.items():
                r["cpu_s|" + k] = v["cpu_s"]
                r["net_tx|" + k] = v["tx"]
            # peak memory: per component the largest container's peak; the network's total peak (sum over the
            # containers within one 5-s sweep of the driver)
            peaks = {}
            for c, v in rec.get("containers", {}).items():
                if "mem_peak" in v:
                    k = role_of(c, gw)
                    peaks[k] = max(peaks.get(k, 0), v["mem_peak"])
            for k, v in peaks.items():
                r["mem_peak_mb|" + k] = v / 2**20
            total = rec.get("mem_total_peak") or sum(v.get("mem_peak", 0) for v in rec.get("containers", {}).values())
            r["mem_total_peak_mb"] = total / 2**20
            runs.append(r)
    # headline attempts
    by = {}
    for r in runs:
        by.setdefault((r["netid"], r["run"]), []).append(r)
    for att in by.values():
        att.sort(key=lambda x: x["attempt"])
        clean = [a for a in att if not (set(a["flags"].split(";")) & REPEATABLE)]
        head = clean[0] if clean else att[-1]
        for a in att:
            a["headline"] = a is head
            a["no_clean_attempt"] = not clean
    return runs, nets


# ------------------------------------------------------------------------------------------ statistics

def boot_median(x):
    x = np.asarray([v for v in x if v == v], dtype=float)
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    if len(x) == 1:
        return float(x[0]), float("nan"), float("nan")
    idx = RNG.integers(0, len(x), size=(B, len(x)))
    meds = np.median(x[idx], axis=1)
    return float(np.median(x)), float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def boot_ratio(a, b):
    a = np.asarray([v for v in a if v == v], dtype=float)
    b = np.asarray([v for v in b if v == v], dtype=float)
    if len(a) == 0 or len(b) == 0:
        return float("nan"), float("nan"), float("nan")
    r = float(np.median(a) / np.median(b))
    if len(a) < 2 or len(b) < 2:
        return r, float("nan"), float("nan")
    ma = np.median(a[RNG.integers(0, len(a), size=(B, len(a)))], axis=1)
    mb = np.median(b[RNG.integers(0, len(b), size=(B, len(b)))], axis=1)
    rs = ma / mb
    return r, float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))


METRICS = ["exec_s", "tps", "lat_mean_ms", "lat_p50_ms", "lat_p95_ms", "lat_p99_ms", "response_mean_ms",
           "stage_endorse_ms", "stage_order_ms", "stage_commit_ms", "stage_spread_ms", "failed"]


def cells(runs):
    head = [r for r in runs if r["headline"]]
    groups = {}
    for r in head:
        groups.setdefault((r["identity"], r["orgs"], r["peers"], r["fn"], r["t"]), []).append(r)
    out = []
    for k, rs in sorted(groups.items()):
        row = {"identity": k[0], "orgs": k[1], "peers": k[2], "fn": k[3], "t": k[4], "reps": len(rs),
               "endorsements": rs[0]["endorsements"], "flagged_reps": sum(r["no_clean_attempt"] for r in rs)}
        for m in METRICS:
            med, lo, hi = boot_median([r.get(m, float("nan")) for r in rs])
            row[m], row[m + "_lo"], row[m + "_hi"] = med, lo, hi
        ok = sum(r.get("ok", 0) for r in rs)
        for role in fs.ROLECOL:
            if role == "client":
                v = [r["client_cpu_s"] / r["ok"] for r in rs if r.get("ok")]
            else:
                v = [r.get("cpu_s|" + role, 0) / r["ok"] for r in rs if r.get("ok")]
            row["cpu_ms_per_tx|" + role] = float(np.median(v)) * 1e3 if v else float("nan")
        v = [r.get("net_tx|orderer", 0) / r["ok"] for r in rs if r.get("ok")]
        row["orderer_egress_bytes_per_tx"] = float(np.median(v)) if v else float("nan")
        row["mem_total_peak_mb"] = float(np.median([r["mem_total_peak_mb"] for r in rs]))
        for role in MEM_ROLES:
            v = [r["mem_peak_mb|" + role] for r in rs if "mem_peak_mb|" + role in r]
            row["mem_peak_mb|" + role] = float(np.median(v)) if v else float("nan")
        row["ok_total"] = ok
        groups[k] = rs
        out.append(row)
    return out, groups


def ratios(groups):
    out = []
    for k, rs in sorted(groups.items()):
        if k[0] != "mldsa44":
            continue
        kb = ("ecdsa",) + k[1:]
        if kb not in groups:
            continue
        row = {"orgs": k[1], "peers": k[2], "fn": k[3], "t": k[4]}
        for m in ("exec_s", "tps", "lat_mean_ms", "lat_p50_ms", "lat_p95_ms", "lat_p99_ms"):
            r, lo, hi = boot_ratio([x.get(m, float("nan")) for x in rs], [x.get(m, float("nan")) for x in groups[kb]])
            row[m + "_ratio"], row[m + "_lo"], row[m + "_hi"] = r, lo, hi
            row[m + "_differs"] = (lo == lo) and (lo > 1 or hi < 1)
        out.append(row)
    return out


def bytes_table(session, nets, runs):
    """Mean bytes per write by part, per E1 network (only the study's own issue transactions); the two halves
    of a split network are averaged into one row."""
    out = []
    for netid, nj in sorted(nets.items()):
        txb = read_csvgz(os.path.join(session, "nets", netid, "out", "ledger", "txbytes.csv.gz"))
        ids = set()
        for r in runs:
            if r["netid"] == netid and r["fn"] == "issue":
                for t in read_csvgz(os.path.join(session, "nets", netid, "out", "runs",
                                                 r["run"] + ("" if r["attempt"] == 1 else "-a%d" % r["attempt"]), "tx.csv.gz")):
                    ids.add(t["txid"])
        rows = [t for t in txb if t["type"] == "ENDORSER_TRANSACTION" and t["txid"] in ids]
        if not rows:
            continue
        row = {"netid": netid, "identity": nj["net"]["identity"], "orgs": nj["net"]["orgs"], "peers": nj["net"]["peers"],
               "endorsements": nj["client"].get("endorsements"), "writes": len(rows)}
        for f in ["envelope", "orderer_bytes"] + fs.PARTS + ["n_certs", "n_sigs"]:
            row[f] = float(np.mean([int(t[f]) for t in rows]))
        blk = read_csvgz(os.path.join(session, "nets", netid, "out", "ledger", "blocks.csv.gz"))
        if blk:
            row["block_metadata_bytes_mean"] = float(np.mean([int(b["metadata_bytes"]) for b in blk]))
            row["tx_per_block_mean"] = float(np.mean([int(b["ntx"]) for b in blk if int(b["ntx"]) > 1] or [1]))
        led = nj.get("ledger_bytes", {})
        peers = [v for k, v in led.items() if k.startswith("peer") and v > 0]
        # plus the untimed setup's 1,400 writes: 100 holders registered and bound, 1,000 pool credentials, 200 warm-up
        n_writes_total = sum(r.get("ok", 0) for r in runs if r["netid"] == netid and r["fn"] == "issue") + 1400
        row["ledger_bytes_per_peer"] = float(np.mean(peers)) if peers else float("nan")
        row["ledger_bytes_per_write_per_peer"] = row["ledger_bytes_per_peer"] / n_writes_total if peers else float("nan")
        row["ledger_gb_per_million_writes_per_peer"] = row["ledger_bytes_per_write_per_peer"] * 1e6 / 1e9 if peers else float("nan")
        out.append(row)
    merged = {}
    for row in out:
        merged.setdefault((row["identity"], row["orgs"], row["peers"]), []).append(row)
    res = []
    for _, rows in sorted(merged.items()):
        m = dict(rows[0])
        if len(rows) > 1:
            m["netid"] = "+".join(r["netid"] for r in rows)
            m["writes"] = sum(r["writes"] for r in rows)
            for f, v in rows[0].items():
                if isinstance(v, float):
                    m[f] = float(np.nanmean([r[f] for r in rows]))
        res.append(m)
    return res


def extras(session, nets):
    e2, e3 = [], []
    for netid, nj in sorted(nets.items()):
        xdir = os.path.join(session, "nets", netid, "out", "extras")
        if not os.path.isdir(xdir):
            continue
        for x in sorted(os.listdir(xdir)):
            for sub in sorted(os.listdir(os.path.join(xdir, x))):
                s = read_json(os.path.join(xdir, x, sub, "summary.json"), {})
                if x.startswith("e2"):
                    for mode, d in s.get("result", {}).items():
                        e2.append(dict({"identity": nj["net"]["identity"], "mode": mode, "rep": sub}, **d))
                elif x == "e3":
                    e3.append({"identity": nj["net"]["identity"], "netid": netid, "case": sub, "offered_tps": s.get("offered_tps"),
                               "achieved_tps": s.get("achieved_tps"), "dropped": s.get("dropped"),
                               "lat_p50_ms": s.get("latency_gateway", {}).get("p50_ms"),
                               "lat_p95_ms": s.get("latency_gateway", {}).get("p95_ms")})
    return e2, e3


# ------------------------------------------------------------------------------------------ figures

def fmt_ms(v):
    if v != v:
        return ""
    if v < 1:
        return "%.2f ms" % v
    if v < 100:
        return "%.1f ms" % v
    if v < 1000:
        return "%.0f ms" % v
    if v < 10000:
        return "%.2f s" % (v / 1000)
    if v < 100000:
        return "%.1f s" % (v / 1000)
    return "{:,.0f} s".format(v / 1000)


def fmt_s(v):
    return "" if v != v else fmt_ms(v * 1000)


def fmt_tps(v):
    return "" if v != v else ("%.1f/s" % v if v < 100 else "{:,.0f}/s".format(v))


def unit_ticks(ax, unit, which="y"):
    """Plain-unit tick labels on a linear axis, in the unit of the values plotted: "ms" (shown in seconds once the
    axis reaches 1 s), "s", "tps", "MB" or "bytes" (shown in KB)."""
    axis = ax.yaxis if which == "y" else ax.xaxis
    hi = (ax.get_ylim() if which == "y" else ax.get_xlim())[1]
    f = {"ms": (lambda v, _: "%g s" % (v / 1000)) if hi >= 1000 else (lambda v, _: "%g ms" % v),
         "s": lambda v, _: "%g s" % v,
         "MB": lambda v, _: "{:,.0f} MB".format(v),
         "bytes": lambda v, _: "%g KB" % (v / 1000),
         "tps": lambda v, _: "{:,.0f}/s".format(v) if v == int(v) else "%g/s" % v}[unit]
    axis.set_major_formatter(FuncFormatter(f))


def cell(cs, ident, o, p, fn, t):
    for c in cs:
        if (c["identity"], c["orgs"], c["peers"], c["fn"], c["t"]) == (ident, o, p, fn, t):
            return c
    return None


FN_LABEL = {"issue": ("write", "writes (issueCredential)"), "get": ("read", "reads (getCredential)")}
# metric: file-name part, title, axis label, value format, unit
FIG_METRICS = {"exec_s": ("execution-time", "Execution time", "execution time", fmt_s, "s"),
           "lat_mean_ms": ("latency", "Mean latency", "mean latency", fmt_ms, "ms"),
           "tps": ("throughput", "Throughput", "throughput", fmt_tps, "tps")}
LOG_TICKS = {"ms": [(0.1, "0.1 ms"), (1, "1 ms"), (10, "10 ms"), (100, "100 ms"), (1000, "1 s"), (10000, "10 s"), (100000, "100 s")],
             "s": [(0.0001, "0.1 ms"), (0.001, "1 ms"), (0.01, "10 ms"), (0.1, "100 ms"), (1, "1 s"), (10, "10 s"), (100, "100 s"),
                   (1000, "1,000 s")],
             "tps": [(0.1, "0.1/s"), (1, "1/s"), (10, "10/s"), (100, "100/s"), (1000, "1,000/s"), (10000, "10,000/s")]}



def tick_text(v, unit):
    if unit == "ms":
        return "%g ms" % v if v < 1000 else "%g s" % (v / 1000)
    if unit == "s":
        return "%g ms" % (v * 1000) if v < 1 else "%g s" % v
    return "{:,.0f}/s".format(v) if v >= 1 else "%g/s" % v


def log_ticks(unit, lo, hi):
    """Plain-unit ticks for a logarithmic value axis: powers of ten, or steps of 1, 2 and 5 when the values span
    less than one and a half powers of ten (so that the axis keeps more than one labelled tick)."""
    if hi / lo >= 30:
        return LOG_TICKS[unit]
    return [(m * 10.0 ** e, tick_text(m * 10.0 ** e, unit)) for e in range(-4, 6) for m in (1, 2, 5)]


def metric_fig(cs, outdir, xs, keyfn, metric, fn, kind, name, title, xlabel, xlog, ylog):
    """One metric of one function against one setting, both arms: kind "lines" (the 95 % interval and the value at
    every point) or "bars" (the value at the end of every bar). keyfn(ident, x, fn) gives the cell. xlog: the base
    of the setting's logarithmic axis in the line charts (10 for the burst size, 2 for peers and organisations);
    ylog: a logarithmic value axis (the burst-size figures, whose values span several orders of magnitude)."""
    _, _, ylabel, fmt, unit = FIG_METRICS[metric]
    fig, ax = fs.new_fig(6.2, 2.8)
    w = 0.38
    texts, allv, series = [], [], {}
    ok = lambda v: v is not None and v == v  # noqa: E731
    for j, ident in enumerate(fs.ARMS):
        pts = [(i, x, keyfn(ident, x, fn)) for i, x in enumerate(xs)]
        pts = [(i, x, c) for i, x, c in pts if c and ok(c.get(metric))]
        if not pts:
            continue
        ys = [c[metric] for _, _, c in pts]
        lo = [c.get(metric + "_lo") for _, _, c in pts]
        hi = [c.get(metric + "_hi") for _, _, c in pts]
        allv += ys + [v for v in lo + hi if ok(v)]
        if kind == "bars":
            pos = [i + (j - 0.5) * w for i, _, _ in pts]
            ax.bar(pos, ys, width=w, color=fs.ARMCOL[ident], label=fs.ARMNAME[ident])
            texts += fs.label_bars(ax, pos, ys, [fmt(v) for v in ys], orient="v")
        else:
            px = [x for _, x, _ in pts]
            el = [y - v if ok(v) else 0 for y, v in zip(ys, lo)]
            eh = [v - y if ok(v) else 0 for y, v in zip(ys, hi)]
            ax.errorbar(px, ys, yerr=[el, eh], color=fs.ARMCOL[ident], marker=fs.ARMMARK[ident], markersize=3.5,
                        capsize=2, label=fs.ARMNAME[ident])
            series[ident] = dict(zip(px, ys))
    if kind == "lines":
        # at each setting the higher value is labelled above its point, the lower one below
        for x in sorted({x for s in series.values() for x in s}):
            here = sorted(((s[x], ident) for ident, s in series.items() if x in s), reverse=True)
            for rank, (y, ident) in enumerate(here):
                ax.annotate(fmt(y), (x, y), xytext=(0, 6 if rank == 0 else -10), textcoords="offset points",
                            ha="center", fontsize=5.5, color=fs.ARMCOL[ident], zorder=5,
                            bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.85))
        fs.log_axis(ax, "x", [(x, "{:,}".format(x)) for x in xs], xlabel, base=xlog)
        m = 2.0 if xlog == 10 else 1.35
        ax.set_xlim(xs[0] / m, xs[-1] * m)
        ax.grid(True, which="major")
    else:
        ax.set_xticks(range(len(xs)))
        ax.set_xticklabels(["{:,}".format(x) for x in xs])
        ax.set_xlabel(xlabel)
    if ylog and allv:
        lo_v, hi_v = min(v for v in allv if v > 0), max(allv)
        fs.log_axis(ax, "y", log_ticks(unit, lo_v, hi_v), ylabel)
        ax.set_ylim(lo_v / 3, hi_v * 3)
    else:
        ax.set_ylabel(ylabel)
        if allv and kind == "lines":  # lines zoom to the data; the bar chart of the same values starts at zero
            lo_v, hi_v = min(allv), max(allv)
            span = max(hi_v - lo_v, 0.1 * hi_v)
            ax.set_ylim(max(0, lo_v - 0.4 * span), hi_v + 0.4 * span)
        elif allv:
            ax.set_ylim(0, max(allv) * 1.05)
    h, lab = ax.get_legend_handles_labels()
    fs.headline(fig, title, h, lab, ncol=2)
    if kind == "bars":
        fs.fit_labels(fig, ax, texts, orient="v")
    if not ylog:
        unit_ticks(ax, unit)
    fs.save(fig, name, outdir)


def bars_vs(cs, outdir, xs, keyfn, metric, xlabel, ylabel, name, title, fmt, fn="issue", t=10000, log_y=False, yunit=None):
    fig, ax = fs.new_fig(6.2, 2.8)
    w = 0.38
    texts = []
    for j, ident in enumerate(fs.ARMS):
        pos, vals = [], []
        for i, x in enumerate(xs):
            c = keyfn(ident, x, fn, t)
            if c and c[metric] == c[metric]:
                pos.append(i + (j - 0.5) * w)
                vals.append(c[metric])
        ax.bar(pos, vals, width=w, color=fs.ARMCOL[ident], label=fs.ARMNAME[ident])
        texts += fs.label_bars(ax, pos, vals, [fmt(v) for v in vals], orient="v")
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels([str(x) for x in xs])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    h, lab = ax.get_legend_handles_labels()
    fs.headline(fig, title, h, lab, ncol=2)
    fs.fit_labels(fig, ax, texts, orient="v")
    if yunit:
        unit_ticks(ax, yunit)
    fs.save(fig, name, outdir)


def heatmap(rat, outdir, rows, cols, keyfn, fn, name, title, xlabel, ylabel):
    """The throughput ratio ML-DSA-44 / ECDSA of one function over two settings (one figure per function)."""
    fig, ax = fs.new_fig(5.6, 3.0)
    m = np.full((len(rows), len(cols)), np.nan)
    for i, rv in enumerate(rows):
        for j, cv in enumerate(cols):
            r = keyfn(rv, cv, fn)
            if r:
                m[i, j] = r["tps_ratio"]
    im = ax.imshow(m, cmap="PRGn", vmin=0.5, vmax=1.5, aspect="auto", origin="lower")  # neither arm's hue
    for i in range(len(rows)):
        for j in range(len(cols)):
            if m[i, j] == m[i, j]:
                ax.text(j, i, "%.2f×" % m[i, j], ha="center", va="center", fontsize=6)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(["{:,}".format(c) for c in cols])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(["{:,}".format(r) for r in rows])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.colorbar(im, ax=ax, label="throughput, ML-DSA-44 / ECDSA", shrink=0.85)
    fs.headline(fig, title)
    fs.save(fig, name, outdir)


def stacked(rows, labels, parts, partcol, partname, outdir, name, title, ylabel, scale=1.0, fmt=lambda v: "%.1f KB" % (v / 1000),
            groups=None, xlabel=None):
    """One stacked bar per row. With groups (one name per row; consecutive rows with the same name form a group,
    for example the two arms of one setting), the bars stand in groups with a gap between them: each bar is named
    by its label and each group once, underneath."""
    fig, ax = fs.new_fig(6.2, 3.0)
    if groups:
        x, pos = [], 0.0
        for i, g in enumerate(groups):
            if i and g != groups[i - 1]:
                pos += 0.6
            x.append(pos)
            pos += 1
        x = np.array(x)
    else:
        x = np.arange(len(rows))
    bottom = np.zeros(len(rows))
    for p in parts:
        v = np.array([r.get(p, 0) * scale for r in rows])
        ax.bar(x, v, bottom=bottom, color=partcol[p], label=partname[p], width=0.6)
        bottom += v
    texts = fs.label_bars(ax, x, bottom, [fmt(v) for v in bottom], orient="v")
    if groups:
        names, centres, i = [], [], 0
        while i < len(groups):
            j = i
            while j < len(groups) and groups[j] == groups[i]:
                j += 1
            names.append(groups[i])
            centres.append(float(np.mean(x[i:j])))
            i = j
        ax.xaxis.remove_overlapping_locs = False  # keep a bar's name where a group's centre falls on it
        ax.set_xticks(centres, names)
        ax.set_xticks(x, labels, minor=True)
        # sizes through tick_params, which reach every tick label (set_xticklabels only reaches those that exist)
        ax.tick_params(axis="x", which="major", labelsize=6.5, length=0, pad=12)
        ax.tick_params(axis="x", which="minor", labelsize=6, length=0)
    else:
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=6)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    h, lab = ax.get_legend_handles_labels()
    fs.headline(fig, title, h, lab, ncol=3)
    fs.fit_labels(fig, ax, texts, orient="v")
    fs.save(fig, name, outdir)


def figures(cs, rat, byt, e2, e3, outdir):
    # F2-F8: every figure holds one metric of one function (write or read), as a line chart and as a bar chart
    kinds, fns = ("lines", "bars"), ("issue", "get")
    # RQ1: one organisation, one peer, against the burst size (F2-F4)
    one = lambda ident, t, fn: cell(cs, ident, 1, 1, fn, t)  # noqa: E731
    for fig_no, metric in (("F2", "exec_s"), ("F3", "lat_mean_ms"), ("F4", "tps")):
        slug, mtitle = FIG_METRICS[metric][:2]
        for fn in fns:
            for kind in kinds:
                metric_fig(cs, outdir, [1, 10, 100, 1000, 10000], one, metric, fn, kind,
                           "%s-%s-1x1-%s-%s" % (fig_no, slug, FN_LABEL[fn][0], kind),
                           "%s of %s, one organisation, one peer" % (mtitle, FN_LABEL[fn][1]),
                           "transactions in the burst", 10, True)
    # RQ2: one organisation, against peers (F5, F6)
    for t in (1000, 10000):
        pk = lambda ident, p, fn, t=t: cell(cs, ident, 1, p, fn, t)  # noqa: E731
        for metric in FIG_METRICS:
            slug, mtitle = FIG_METRICS[metric][:2]
            for fn in fns:
                for kind in kinds:
                    metric_fig(cs, outdir, [1, 2, 4, 8], pk, metric, fn, kind,
                               "F5-%s-peers-T%d-%s-%s" % (slug, t, FN_LABEL[fn][0], kind),
                               "%s of %s, one organisation, %s transactions" % (mtitle, FN_LABEL[fn][1], "{:,}".format(t)),
                               "peers, one organisation", 2, False)
    rk = lambda p, t, fn: next((r for r in rat if (r["orgs"], r["peers"], r["fn"], r["t"]) == (1, p, fn, t)), None)  # noqa: E731
    for fn in fns:
        heatmap(rat, outdir, [1, 2, 4, 8], [1, 10, 100, 1000, 10000], rk, fn, "F6-ratio-peers-x-T-%s" % FN_LABEL[fn][0],
                "ML-DSA-44 / ECDSA throughput, %s, one organisation" % FN_LABEL[fn][1], "transactions in the burst", "peers")
    # RQ3: organisations, at 4 and 8 peers, 10,000 transactions (F7, F8)
    for p in (4, 8):
        orgs = [o for o in (1, 2, 4, 8) if o <= p]
        ok = lambda ident, o, fn, p=p: cell(cs, ident, o, p, fn, 10000)  # noqa: E731
        for metric in FIG_METRICS:
            slug, mtitle = FIG_METRICS[metric][:2]
            for fn in fns:
                for kind in kinds:
                    metric_fig(cs, outdir, orgs, ok, metric, fn, kind,
                               "F7-%s-orgs-P%d-%s-%s" % (slug, p, FN_LABEL[fn][0], kind),
                               "%s of %s, %d peers, 10,000 transactions" % (mtitle, FN_LABEL[fn][1], p),
                               "organisations, %d peers in total" % p, 2, False)
    ok2 = lambda o, p, fn: next((r for r in rat if (r["orgs"], r["peers"], r["fn"], r["t"]) == (o, p, fn, 10000)), None)  # noqa: E731
    for fn in fns:
        heatmap(rat, outdir, [1, 2, 4, 8], [1, 2, 4, 8], ok2, fn, "F8-ratio-orgs-x-peers-%s" % FN_LABEL[fn][0],
                "ML-DSA-44 / ECDSA throughput, %s, 10,000 transactions" % FN_LABEL[fn][1], "peers", "organisations")
    # RQ4: bytes, ledger, CPU, memory, orderer egress, stages (F9-F14)
    sel = sorted([b for b in byt if b["peers"] == 8], key=lambda b: (b["endorsements"], fs.ARMS.index(b["identity"])))
    if sel:
        stacked(sel, [fs.ARMNAME[b["identity"]] for b in sel],
                fs.PARTS, fs.PARTCOL, fs.PARTNAME, outdir, "F9-bytes-per-write", "Bytes of one credential write, by part (8 peers)",
                "kilobytes per transaction", scale=1e-3, fmt=lambda v: "%.1f KB" % v,
                groups=["%d endorsement%s" % (b["endorsements"], "s" if b["endorsements"] > 1 else "") for b in sel])
    sel = [b for b in byt if b.get("ledger_gb_per_million_writes_per_peer") == b.get("ledger_gb_per_million_writes_per_peer")]
    if sel:
        sel.sort(key=lambda b: (b["orgs"], b["peers"], fs.ARMS.index(b["identity"])))
        fig, ax = fs.new_fig(7.0, 2.8)
        topos = sorted({(b["orgs"], b["peers"]) for b in sel})
        w = 0.38
        x = np.array([topos.index((b["orgs"], b["peers"])) + (fs.ARMS.index(b["identity"]) - 0.5) * w for b in sel])
        v = [b["ledger_gb_per_million_writes_per_peer"] for b in sel]
        ax.bar(x, v, width=w, color=[fs.ARMCOL[b["identity"]] for b in sel])
        texts = fs.label_bars(ax, x, v, ["%.0f GB" % y for y in v], orient="v", fontsize=5)
        ax.set_xticks(range(len(topos)))
        ax.set_xticklabels(["%d×%d" % tp for tp in topos], fontsize=6)
        ax.set_xlabel("organisations × peers")
        ax.set_ylabel("GB per million writes, per peer")
        from matplotlib.patches import Patch
        fs.headline(fig, "Ledger growth per peer", [Patch(color=fs.ARMCOL[a]) for a in fs.ARMS], [fs.ARMNAME[a] for a in fs.ARMS], ncol=2)
        fs.fit_labels(fig, ax, texts, orient="v")
        fs.save(fig, "F10-ledger-growth", outdir)
    sel = []
    for o in (1, 2, 4, 8):
        for ident in fs.ARMS:
            c = cell(cs, ident, o, 8, "issue", 10000)
            if c:
                sel.append(c)
    if sel:
        roles = list(fs.ROLECOL)
        stacked(sel, [fs.ARMNAME[c["identity"]] for c in sel],
                ["cpu_ms_per_tx|" + r for r in roles], {"cpu_ms_per_tx|" + r: fs.ROLECOL[r] for r in roles},
                {"cpu_ms_per_tx|" + r: r for r in roles}, outdir, "F11-cpu-per-write",
                "CPU time per credential write, by component (8 peers, 10,000 writes)", "CPU time per transaction (ms)",
                fmt=lambda v: "%.1f ms" % v,
                groups=["%d organisation%s" % (c["orgs"], "s" if c["orgs"] > 1 else "") for c in sel])
    om = lambda ident, o, fn, t: cell(cs, ident, o, 8, fn, t)  # noqa: E731
    bars_vs(cs, outdir, [1, 2, 4, 8], om, "mem_total_peak_mb", "organisations (8 peers in total)", "peak memory of the network",
            "F12-memory-total-orgs-P8", "Peak memory of the whole network against organisations, 8 peers, 10,000 writes",
            lambda v: "{:,.0f} MB".format(v), yunit="MB")
    bars_vs(cs, outdir, [1, 2, 4, 8], om, "mem_peak_mb|gateway peer", "organisations (8 peers in total)", "peak memory of the gateway peer",
            "F12-memory-gateway-orgs-P8", "Peak memory of the gateway peer against organisations, 8 peers, 10,000 writes",
            lambda v: "{:,.0f} MB".format(v), yunit="MB")
    pk2 = lambda ident, p, fn, t: cell(cs, ident, 1, p, fn, t)  # noqa: E731
    bars_vs(cs, outdir, [1, 2, 4, 8], pk2, "orderer_egress_bytes_per_tx", "peers (one organisation)", "orderer egress per transaction",
            "F13-orderer-egress", "Bytes the orderer sends per write, against peers (10,000 writes)", lambda v: "%.0f KB" % (v / 1000),
            yunit="bytes")
    sel = []
    for (o, p) in ((1, 1), (2, 2), (8, 8)):
        for ident in fs.ARMS:
            c = cell(cs, ident, o, p, "issue", 1000)
            if c:
                sel.append(c)
    if sel:
        stacked(sel, [fs.ARMNAME[c["identity"]] for c in sel],
                ["stage_%s_ms" % s for s in fs.STAGES], {"stage_%s_ms" % s: fs.STAGECOL[s] for s in fs.STAGES},
                {"stage_%s_ms" % s: s for s in fs.STAGES}, outdir, "F14-stages",
                "Median time of each stage of a write (1,000 writes)", "milliseconds", fmt=fmt_ms,
                groups=["%d×%d" % (c["orgs"], c["peers"]) for c in sel], xlabel="organisations × peers")
    # E2 and E3 (F15, F16)
    if e2:
        fig, ax = fs.new_fig(5.0, 2.6)
        rows = []
        for ident in fs.ARMS:
            for mode in ("open_connection", "fresh_connection"):
                v = [r["p50_ms"] for r in e2 if r["identity"] == ident and r["mode"] == mode]
                if v:
                    rows.append((ident, mode, float(np.median(v))))
        y = np.arange(len(rows))
        ax.barh(y, [r[2] for r in rows], color=[fs.ARMCOL[r[0]] for r in rows])
        texts = fs.label_bars(ax, y, [r[2] for r in rows], [fmt_ms(r[2]) for r in rows])
        ax.set_yticks(y)
        mode_name = {"open_connection": "open connection", "fresh_connection": "new connection"}
        ax.set_yticklabels(["%s, %s" % (fs.ARMNAME[r[0]], mode_name.get(r[1], r[1].replace("_", " "))) for r in rows], fontsize=6)
        ax.set_xlabel("median time of one read")
        fs.headline(fig, "A read on an open connection and on a new one (TLS handshake)")
        fs.fit_labels(fig, ax, texts)
        unit_ticks(ax, "ms", which="x")
        fs.save(fig, "F15-connection-setup", outdir)
    if e3:
        fig, ax = fs.new_fig(5.2, 2.8)
        for ident in fs.ARMS:
            pts = {}
            for r in e3:
                if r["identity"] == ident and r["lat_p50_ms"] is not None:
                    pts.setdefault(r["offered_tps"], []).append(r["lat_p50_ms"])
            xs = sorted(pts)
            ax.plot(xs, [np.median(pts[x]) for x in xs], marker=fs.ARMMARK[ident], color=fs.ARMCOL[ident], label=fs.ARMNAME[ident])
        ax.set_xlabel("offered load (transactions per second)")
        fs.log_axis(ax, "y", [(10, "10 ms"), (20, "20 ms"), (50, "50 ms"), (100, "100 ms"), (200, "200 ms"), (500, "500 ms"),
                              (1000, "1 s"), (2000, "2 s"), (5000, "5 s"), (10000, "10 s")], "median latency")
        ax.grid(True)
        h, lab = ax.get_legend_handles_labels()
        fs.headline(fig, "Latency against offered load, 2 organisations, 2 peers (E3)", h, lab, ncol=2)
        fs.save(fig, "F16-offered-load", outdir)


def markdown(rows, fields, path, title):
    with open(path, "w") as f:
        f.write("# %s\n\n| %s |\n|%s|\n" % (title, " | ".join(fields), "|".join("---" for _ in fields)))
        for r in rows:
            vals = []
            for k in fields:
                v = r.get(k, "")
                vals.append(("%.3g" % v) if isinstance(v, float) else str(v))
            f.write("| %s |\n" % " | ".join(vals))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    session, out = sys.argv[1], sys.argv[2]
    runs, nets = load(session)
    if not runs:
        sys.exit("no runs in %s" % session)
    tables, figs = os.path.join(out, "tables"), os.path.join(out, "figures")
    write_csv(os.path.join(tables, "runs.csv"), runs, sorted({k for r in runs for k in r}))
    cs, groups = cells(runs)
    write_csv(os.path.join(tables, "cells.csv"), cs, sorted({k for r in cs for k in r}))
    rat = ratios(groups)
    write_csv(os.path.join(tables, "ratios.csv"), rat, sorted({k for r in rat for k in r}) if rat else None)
    byt = bytes_table(session, nets, runs)
    write_csv(os.path.join(tables, "bytes.csv"), byt, sorted({k for r in byt for k in r}) if byt else None)
    e2, e3 = extras(session, nets)
    write_csv(os.path.join(tables, "e2.csv"), e2, sorted({k for r in e2 for k in r}) if e2 else None)
    write_csv(os.path.join(tables, "e3.csv"), e3, sorted({k for r in e3 for k in r}) if e3 else None)
    setup = [dict({"netid": k}, **v.get("timings", {})) for k, v in sorted(nets.items())]
    write_csv(os.path.join(tables, "setup.csv"), setup, sorted({k for r in setup for k in r}))
    markdown(cs, ["identity", "orgs", "peers", "fn", "t", "reps", "exec_s", "tps", "lat_mean_ms", "lat_p95_ms", "mem_total_peak_mb", "failed"],
             os.path.join(tables, "cells.md"), "Cells (median of the repetitions)")
    if rat:
        markdown(rat, ["orgs", "peers", "fn", "t", "tps_ratio", "tps_lo", "tps_hi", "lat_mean_ms_ratio", "lat_p95_ms_ratio"],
                 os.path.join(tables, "ratios.md"), "ML-DSA-44 / ECDSA (95 % bootstrap interval)")
    figures(cs, rat, byt, e2, e3, figs)
    print("runs %d (%d headline), cells %d, comparisons %d, networks %d" % (len(runs), sum(r["headline"] for r in runs), len(cs), len(rat), len(nets)))
    if fs.PROBLEMS:
        print("LAYOUT PROBLEMS:\n  " + "\n  ".join(fs.PROBLEMS))
        sys.exit(3)


if __name__ == "__main__":
    main()
