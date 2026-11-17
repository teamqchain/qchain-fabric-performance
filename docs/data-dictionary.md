# Data dictionary

Every file a session writes. Raw files live in `results/raw/<session>/` (not committed); `scripts/qfp.py publish` copies what is kept into `results/<session>/` after the privacy scan, with `SHA256SUMS` written last. Times in `*_ns` columns are nanoseconds since the run's t0 (monotonic clock of the client); `-1` means the step was not reached.

## Session folder

| File | Content |
|---|---|
| `plan.json` | kind, seed, harness commit, image IDs, thresholds, every network (`net`: organisations, peers, identity; `tag` for a split half or an E3 network; `e3_rep`; `seed`; `extras`; `go_env` for a memory test) with its runs (id, function, T, repetition, seed, C for the trial) |
| `state.json` | networks done, their durations, canaries, the session's canary reference, failures |
| `driver.log` | one line per network step, per run and per E2/E3 level |
| `session-host.txt`, `preflight-*.txt` | macOS version, model, Colima and Docker versions, preflight problems |
| `host/host-all.csv` | host monitor: `utc_ns,other_pct,throttle,on_ac,alert,detail` every 5 s (KPI format) |
| `host/paused.log`, `host/wifi.log` | services paused, Wi-Fi switched off |
| `trial-report.json` | trial only: `c_cases` (per case and candidate: attempts, failed attempts, write throughput, the candidates within 5 %), `c_choice`, `e3_saturation_tps`, `write_tps_2x2_best`, `containers_down`, `vm_memory_mb`, `vm_baseline_mb` (the VM's own use at idle), per network (memory peaks, ledger bytes per write per peer and the orderer's ledger bytes, timings, errors), `memory_warning`, `colima_disk_now_gb`, `projection` (hours, per-network hours and disk, `split_proposed`) |

## Per network: `nets/<netid>/`

`netid` = `o<O>p<P>-<identity>`, for example `o2p2-mldsa44`; `-part1` / `-part2` for the halves of a split E1 network; `-e3r<k>` for E3's network of repetition k.

| File | Content |
|---|---|
| `network.json` | the network, step timings (M12), `ledger_bytes` per data volume (M9), the ledger read-back's result, Colima disk use, `errors` (a failed E2, E3 or read-back) |
| `runs/<run>.json` | the driver's record of one attempt: id, attempt, function, T, repetition, C, seed, start/end (Unix ns), `wall_s`, the client's short result, error, flags, macOS swap before/after, per container `cpu_s`, `rx`, `tx`, `mem_peak`, the network's `mem_total_peak`, every container's `states` (running, oom, exit, restarts, error) |
| `diag-<run>-a<k>.txt` | only when a container was down after a run: its state and last log lines |
| `gen/` | the generated network files (no keys: those stay in the Docker volume) |
| `tools-*.log`, `setup.log` | output of the bring-up scripts and of the setup |
| `out/pool.txt` | the read pool's credential IDs |
| `out/runs/<run>/tx.csv.gz` | `idx, arg, txid, send_ns, endorsed_ns, submitted_ns, gw_commit_ns, all_commit_ns, peers_seen, block, code, ok, err_stage, err_code, result_bytes` |
| `out/runs/<run>/arrivals.csv.gz` | writes only: `peer, block, recv_ns` |
| `out/runs/<run>/summary.json` | the client's summary: M1–M6 (fields `execution_time_*`, `throughput_*`, `latency_*`, `stage_*`), failures, client CPU, client certificate size |
| `out/extras/e2/rep<k>/conn.csv.gz` | E2: `mode (fresh/open), i, connect_ns, call_ns, total_ns`; `summary.json`: both distributions |
| `out/extras/e3/f<pct>-rep<k>/tx.csv.gz` | E3: `idx, txid, send_ns, endorsed_ns, submitted_ns, gw_commit_ns, block, code, ok, err_stage, err_code`; `summary.json`: offered and achieved rate, sent, dropped, ok, gateway latency |
| `out/extras/e2_small/`, `out/extras/e3_small/` | the trial's short checks, same formats |
| `out/ledger/blocks.csv.gz` | `block, bytes, data_bytes, metadata_bytes, orderer_sig_bytes, ntx, orderer_sum` |
| `out/ledger/txbytes.csv.gz` | `block, index, txid, type, code, envelope, orderer_bytes, cert_bytes, n_certs, sig_bytes, n_sigs, input_bytes, response_bytes, rest_bytes, endorsements` |

## Analysis: `analysis/tables/`

| File | Content |
|---|---|
| `runs.csv` | every attempt with its recomputed metrics, flags, headline mark, CPU and egress per component, peak memory per component (column `mem_peak_mb` plus a bar and the component name, e.g. the gateway peer) and total (`mem_total_peak_mb`) |
| `cells.csv`, `cells.md` | per cell (identity, organisations, peers, function, T): medians with bootstrap intervals (`_lo`, `_hi`), CPU per transaction by component, orderer egress per transaction, peak memory per component and total |
| `ratios.csv`, `ratios.md` | ML-DSA-44 / ECDSA per cell, with intervals and `_differs` |
| `bytes.csv` | per topology and arm (a split network's halves averaged): mean bytes per write by part, transactions per block, ledger growth per peer |
| `e2.csv`, `e3.csv`, `setup.csv` | E2 distributions, E3 levels (offered and achieved rate, dropped, latency), bring-up timings |
