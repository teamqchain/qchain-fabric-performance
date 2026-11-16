# Data dictionary

Every file a session writes. Raw files live in `results/raw/<session>/` (not committed); `scripts/qfp.py publish` copies what is kept into `results/<session>/` after the privacy scan, with `SHA256SUMS` written last. Times in `*_ns` columns are nanoseconds since the run's t0 (monotonic clock of the client); `-1` means the step was not reached.

## Session folder

| File | Content |
|---|---|
| `plan.json` | kind, seed, harness commit, image IDs, frozen thresholds, every network with its runs (id, function, T, repetition, seed, C override) |
| `state.json` | networks done, their durations, canaries, the session's canary reference, failures |
| `driver.log` | one line per network step and per run |
| `session-host.txt`, `preflight-*.txt` | macOS version, model, Colima and Docker versions, preflight problems |
| `host/host-all.csv` | host monitor: `utc_ns,other_pct,throttle,on_ac,alert,detail` every 5 s (KPI format) |
| `host/paused.log`, `host/wifi.log` | services paused, Wi-Fi switched off |
| `trial-report.json` | trial only: C per arm, saturation, memory peaks, ledger bytes, time projection, E4 decision |

## Per network: `nets/<netid>/`

`netid` = `o<O>p<P>-<identity>-<blocks>`, for example `o2p2-mldsa44-study`.

| File | Content |
|---|---|
| `network.json` | the network, step timings (M12), `ledger_bytes` per data volume (M9), blocks read, Colima disk use |
| `runs/<run>.json` | the driver's record of one attempt: id, attempt, function, T, repetition, C, seed, start/end (Unix ns), the client's short result, error, flags, macOS swap before/after, per container `cpu_s`, `rx`, `tx`, `mem_peak` |
| `gen/` | the generated network files (no keys: those stay in the Docker volume) |
| `tools-*.log`, `setup.log` | output of the bring-up scripts and of the setup |
| `out/pool.txt` | the read pool's credential IDs |
| `out/runs/<run>/tx.csv.gz` | `idx, arg, txid, send_ns, endorsed_ns, submitted_ns, gw_commit_ns, all_commit_ns, peers_seen, block, code, ok, err_stage, err_code, result_bytes` |
| `out/runs/<run>/arrivals.csv.gz` | writes only: `peer, block, recv_ns` |
| `out/runs/<run>/summary.json` | the client's summary: M1–M6 (fields `execution_time_*`, `throughput_*`, `latency_*`, `stage_*`), failures, client CPU, client certificate size |
| `out/extras/e2*/rep<k>/conn.csv.gz` | E2: `mode (fresh/open), i, connect_ns, call_ns, total_ns` |
| `out/extras/e4*/f<pct>-rep<k>/tx.csv.gz` | E4: as `tx.csv.gz` without the all-peer columns; `summary.json`: offered and achieved rate, dropped, latency |
| `out/ledger/blocks.csv.gz` | `block, bytes, data_bytes, metadata_bytes, orderer_sig_bytes, ntx, orderer_sum` |
| `out/ledger/txbytes.csv.gz` | `block, index, txid, type, code, envelope, orderer_bytes, cert_bytes, n_certs, sig_bytes, n_sigs, input_bytes, response_bytes, rest_bytes, endorsements` |

## Analysis: `analysis/tables/`

| File | Content |
|---|---|
| `runs.csv` | every attempt with its recomputed metrics, flags, headline mark, CPU and egress per component |
| `cells.csv`, `cells.md` | per cell: medians with bootstrap intervals (`_lo`, `_hi`), CPU per transaction by component, orderer egress per transaction, memory peak |
| `ratios.csv`, `ratios.md` | ML-DSA-44 / ECDSA per cell, with intervals and `_differs` |
| `bytes.csv` | per network: mean bytes per write by part, transactions per block, ledger growth per peer |
| `e2.csv`, `e4.csv`, `setup.csv` | E2 distributions, E4 points, bring-up timings |
