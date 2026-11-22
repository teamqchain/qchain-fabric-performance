#!/usr/bin/env python3
"""selftest.py: runs run_all.py on a small synthetic session and checks its numbers.

    python3 analysis/selftest.py        (inside the qfp/analysis image; needs numpy and matplotlib)

The synthetic session has the driver's and the client's file layout, two topologies, both identity
arms, both functions and two burst sizes, with known latencies and memory, so that the cells, the
ratios, the headline rule, the memory columns and the byte table can be checked exactly. One network
is split in two folders (repetitions 1-2 and 3), as the driver does for a split E1 network, and two
E3 networks (one per arm) hold only offered-load results.
"""
import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def wjson(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(o, f)


def wcsvgz(p, header, rows):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


TX_HEADER = ["idx", "arg", "txid", "send_ns", "endorsed_ns", "submitted_ns", "gw_commit_ns", "all_commit_ns", "peers_seen",
             "block", "code", "ok", "err_stage", "err_code", "result_bytes"]


def make(root):
    ms = 1_000_000
    for (o, p) in ((1, 1), (2, 2)):
        for ident, lat in (("ecdsa", 100), ("mldsa44", 150)):
            base = "o%dp%d-%s" % (o, p, ident)
            # (2,2) ML-DSA-44 is split as the driver splits an E1 network: repetitions 1-2, then 3
            parts = [(base + "-part1", (1, 2)), (base + "-part2", (3,))] if (o, p, ident) == (2, 2, "mldsa44") else [(base, (1, 2, 3))]
            for netid, reps in parts:
                nd = os.path.join(root, "nets", netid)
                wjson(os.path.join(nd, "network.json"), {"net": {"orgs": o, "peers": p, "identity": ident},
                                                        "timings": {"network_up_s": 60}, "ledger_bytes": {"peer0.general.uae.com": 10**8}})
                wjson(os.path.join(nd, "gen", "client.json"), {"endorsements": o // 2 + 1, "gateway": {"name": "peer0.general.uae.com"}})
                txb = []
                for fn in ("issue", "get"):
                    for t in (10, 100):
                        for rep in reps:
                            rid = "%s-%s-%d-%d" % (base, fn, t, rep)
                            flags = ["other_cpu"] if rep == 2 else []
                            for att in ((1, 2) if rep == 2 else (1,)):
                                run_dir = rid + ("" if att == 1 else "-a%d" % att)
                                wjson(os.path.join(nd, "runs", run_dir + ".json"), {
                                    "id": rid, "attempt": att, "run_dir": run_dir, "fn": fn, "t": t, "rep": rep, "c": 200,
                                    "flags": flags if att == 1 else [], "error": None, "mem_total_peak": 3 * 2**20,
                                    "containers": {"qfp_peer0.general.uae.com": {"cpu_s": 1.0, "tx": 1000, "rx": 1000, "mem_peak": 2**20}}})
                                rows = []
                                for i in range(t):
                                    # each transaction takes `lat` ms; sends 1 ms apart; the flagged attempt is 10x slower
                                    l = lat * (10 if (rep == 2 and att == 1) else 1)
                                    s, e = i * ms, i * ms + l * ms
                                    txid = "%s-%d" % (run_dir, i)
                                    rows.append([i, "H-0001", txid, s, s + ms, s + 2 * ms, e, e, p, 3, 0, "true", "", "", 100])
                                    if fn == "issue":
                                        cert = 900 if ident == "ecdsa" else 5400
                                        sig = 72 if ident == "ecdsa" else 2420
                                        n = 2 + o // 2 + 1
                                        txb.append([3, i, txid, "ENDORSER_TRANSACTION", 0, 0, 0, n * cert, n, (n - 1) * sig, n - 1,
                                                    9000, 8800, 300, n - 2])
                                wcsvgz(os.path.join(nd, "out", "runs", run_dir, "tx.csv.gz"), TX_HEADER, rows)
                                wjson(os.path.join(nd, "out", "runs", run_dir, "summary.json"), {"client_cpu_s": 0.5})
                for r in txb:
                    r[5] = r[7] + r[9] + r[11] + r[12] + r[13]
                wcsvgz(os.path.join(nd, "out", "ledger", "txbytes.csv.gz"),
                       ["block", "index", "txid", "type", "code", "envelope", "orderer_bytes", "cert_bytes", "n_certs", "sig_bytes",
                        "n_sigs", "input_bytes", "response_bytes", "rest_bytes", "endorsements"], txb)
                wcsvgz(os.path.join(nd, "out", "ledger", "blocks.csv.gz"), ["block", "bytes", "data_bytes", "metadata_bytes",
                       "orderer_sig_bytes", "ntx", "orderer_sum"], [[3, 1000, 900, 100, 72, 10, 900]])
    # E3: one network per arm (no runs), two offered-load levels each
    for ident, p50 in (("ecdsa", 40), ("mldsa44", 90)):
        nd = os.path.join(root, "nets", "o2p2-%s-e3r1" % ident)
        wjson(os.path.join(nd, "network.json"), {"net": {"orgs": 2, "peers": 2, "identity": ident}, "timings": {"network_up_s": 60},
                                                "ledger_bytes": {}})
        wjson(os.path.join(nd, "gen", "client.json"), {"endorsements": 2, "gateway": {"name": "peer0.general.uae.com"}})
        for pct, rate in ((50, 100.0), (100, 200.0)):
            wjson(os.path.join(nd, "out", "extras", "e3", "f%03d-rep1" % pct, "summary.json"),
                  {"offered_tps": rate, "achieved_tps": rate, "dropped": 0, "ok": int(rate * 60),
                   "latency_gateway": {"p50_ms": p50 * pct / 50, "p95_ms": 3 * p50}})


def main():
    root = tempfile.mkdtemp()
    out = tempfile.mkdtemp()
    try:
        make(root)
        proc = subprocess.run([sys.executable, os.path.join(HERE, "run_all.py"), root, out], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(proc.stdout.decode())
        with open(os.path.join(out, "tables", "cells.csv")) as f:
            cells = list(csv.DictReader(f))
        with open(os.path.join(out, "tables", "ratios.csv")) as f:
            rat = list(csv.DictReader(f))
        with open(os.path.join(out, "tables", "bytes.csv")) as f:
            byt = list(csv.DictReader(f))
        with open(os.path.join(out, "tables", "e3.csv")) as f:
            e3 = list(csv.DictReader(f))
        bad = []
        if len(cells) != 16 or any(int(c["reps"]) != 3 for c in cells):   # the split network's runs form whole cells
            bad.append("cells: %d (want 16), reps %s" % (len(cells), sorted({c["reps"] for c in cells})))
        for c in cells:
            if abs(float(c["mem_total_peak_mb"]) - 3) > 1e-9 or abs(float(c["mem_peak_mb|gateway peer"]) - 1) > 1e-9:
                bad.append("cell %s/%s/%s: memory %s / %s" % (c["identity"], c["fn"], c["t"], c["mem_total_peak_mb"],
                                                              c["mem_peak_mb|gateway peer"]))
        if len(byt) != 4:                                                   # one row per topology and arm
            bad.append("bytes: %d rows, want 4" % len(byt))
        if len(e3) != 4 or sorted(float(r["offered_tps"]) for r in e3) != [100.0, 100.0, 200.0, 200.0]:
            bad.append("e3: %s" % [(r["identity"], r["offered_tps"]) for r in e3])
        for c in cells:
            want = 100 if c["identity"] == "ecdsa" else 150
            if abs(float(c["lat_mean_ms"]) - want) > 1e-6:      # the flagged 10x attempt must not be the headline
                bad.append("cell %s/%s/%s: latency %s, want %d" % (c["identity"], c["fn"], c["t"], c["lat_mean_ms"], want))
            t = int(c["t"])
            exec_s = ((t - 1) + want) / 1000
            if abs(float(c["exec_s"]) - exec_s) > 1e-9 or abs(float(c["tps"]) - t / exec_s) > 1e-6:
                bad.append("cell %s/%s/%s: execution %s s, want %.3f" % (c["identity"], c["fn"], t, c["exec_s"], exec_s))
        for r in rat:
            if abs(float(r["lat_mean_ms_ratio"]) - 1.5) > 1e-9:
                bad.append("ratio %s: %s, want 1.5" % (r, r["lat_mean_ms_ratio"]))
        for b in byt:
            n = 2 + int(b["orgs"]) // 2 + 1
            cert = 900 if b["identity"] == "ecdsa" else 5400
            if abs(float(b["cert_bytes"]) - n * cert) > 1e-9:
                bad.append("bytes %s: certificates %s" % (b["netid"], b["cert_bytes"]))
        figs = sorted(os.listdir(os.path.join(out, "figures")))
        print("figures: %s" % ", ".join(f for f in figs if f.endswith(".png")))
        if not any(f.startswith("F16-offered-load") for f in figs):
            bad.append("no F16 figure")
        if proc.returncode != 0:
            bad.append("run_all.py exited %d" % proc.returncode)
        print("selftest: %s" % ("ok" if not bad else "FAILED\n  " + "\n  ".join(bad)))
        sys.exit(1 if bad else 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    main()
