# Methodology (as implemented)

This file describes what the code does when it measures. It is written from the code; the research plan is [plan.md](plan.md) and the reasons for each choice are in [decisions-log.md](decisions-log.md). Any difference between this file and the code is a bug in this file.

## 1. The two arms

Both arms run the **same binaries**: Fabric `e472b4ea` and Fabric CA `e82caf43` built with the build tag `pqc` (fabric-lib-go `bd30150` vendored), natively on the test machine, x86-64 (`docker/Dockerfile.fabric`). Only the identities differ:

| | ECDSA arm | ML-DSA-44 arm |
|---|---|---|
| Every identity (organisation CAs, TLS CAs, orderer, peers, admins, users) | cryptogen `PublicKeyAlgorithm: ecdsa` (P-256) | `mldsa44` (as live) |
| Application users from the Fabric CA (`issuer1`, `verifier1`) | `csr.keyrequest.algo: ecdsa`, provider `SW` | `mldsa44`, provider `PQC` (as live) |
| Crypto provider of peers, orderer and CLI (`BCCSP.Default`) | `SW` | `PQC` (as live) |
| Client signer | fabric-gateway's ECDSA signer | the backend's ML-DSA signer (`newSign`, verbatim) |

Everything else is identical: the channel (V3_0 / V2_0 / V2_5, MAJORITY endorsement and lifecycle), the block settings, the node configuration, the chaincode, the payloads, the client, the topology, the containers and the machine. The Fabric CA servers' own TLS is ECDSA in both arms, as on the live network. TLS key exchange is whatever Go 1.27 negotiates in both arms; only the certificates' signature algorithm differs.

## 2. Networks

`network/gen/qfp_gen.py` writes one network from the verbatim copies in `network/live/` (`qchain-network` at `c890bd4`):

- **Organisations:** O = 1 (General), 2 (Government, General: the live pair), 4 or 8 (plus `org3` ... `org8`, `orgN.uae.com`). P peers in total, P/O per organisation, `peer0` ... `peer7`. Ports follow the live port map for Government and General.
- **Endorsements per write** (MAJORITY of O organisations): 1, 2, 3, 5.
- **Blocks:** 100 transactions / 16 MB preferred / 99 MB absolute / 2 s (the study's setting, in every network).
- **Containers** (1 + P + 2·O): one Raft orderer, P peers, one chaincode server and one Fabric CA per organisation, each with the live environment, user and read-only root file system, **without a memory limit or CPU quota** and without a restart policy. Under the launcher's CPU isolation (section 8) every container of the study, the network's, the tools' and the client's, starts with `--cgroup-parent qfp.slice`, so it runs on the study's CPUs only.
- **Network id:** `o<O>p<P>-<identity>`, for example `o2p2-mldsa44`; the driver adds `-part1` / `-part2` to the two halves of a split E1 network and `-e3r<k>` to E3's networks.
- **Self-check** (`qfp_gen.py --selfcheck`, also run by `scripts/qfp.py selfcheck`): for the live topology (2 × 2, ML-DSA-44) the generated `crypto-config.yaml` and CA configurations equal the live files (comments aside), the generated `configtx.yaml` equals the live file except `MaxMessageCount` and `PreferredMaxBytes`, `core.yaml` and `orderer.yaml` are byte-identical, and the orderer's and both peers' environments equal the live compose file's. All 20 networks (10 topologies × 2 arms) generate, with no container memory limit.

Bring-up order (`scripts/qfp.py bring_up`): files into a Docker volume → cryptogen and CA bootstrap (`01-crypto.sh`) → CAs → enrolment (`03-enroll.sh`) → orderer and peers → channel (`02-channel.sh`) → chaincode packages and install (`04-install.sh`) → chaincode servers → approve and commit (`05-commit.sh`). Every step is timed (M12).

## 3. Workload

**Untimed setup per network** (`qfp-client setup`): 100 holders registered with real ML-KEM-768 and ML-DSA-44 public keys (it waits up to 60 s while gossip discovery completes), 1,000 credentials issued for the read pool, then 200 writes and 200 reads as warm-up: 1,400 writes in all.

**Writes** are `issueCredential` with the backend's argument shapes: holder `H-0001` ... `H-0100` in turn, 10 SHA3-256 field hashes, a CIDv0, the SHA3-256 credential hash and a real ML-DSA-44 signature and public key (64 signed variants per process, made before t0). `issuedAt` is the send time (UAE offset). The content is identical in both arms. Every write creates a new key (`CRED-<txID>`), so writes never conflict.

**Reads** are `getCredential` of a credential drawn (seeded) from the read pool. A read is checked: the returned record's ID must be the requested one.

## 4. One run (E0, E1)

One run is one fresh `qfp-client run` process in its own container on the network's Docker network:

1. Untimed: the connection to `peer0.general` (the gateway, as for the backend), the workload, the ledger height, a block-event stream from every peer starting at that height, one warm-up call.
2. **t0**: T requests are released at once; at most **C** are in flight (the trial sets C per run; the main session uses the frozen C). Writes: proposal → endorse → submit → commit status, each step timed; reads: proposal → evaluate.
3. Writes: the client waits until every peer has delivered the highest block of the run (at most 120 s), then joins each transaction with the time its block reached each peer.

Files: `tx.csv.gz` (every transaction), `arrivals.csv.gz` (every block on every peer), `summary.json`. Around the client, the driver reads every container's CPU and network counters before and after, samples memory every 5 s, and records every container's state (running, killed for memory, exit code, restarts) and, for a container that is down, its last log lines.

## 5. E2 and E3

**E2** (`qfp-client conn`, in E1's two (2,2) networks after their runs, 5 repetitions): 200 times, a new gRPC connection, a new Gateway and one `getCredential` (the TLS handshake with the peer's certificate chain happens on this first call), each timed; then 200 reads on one open connection. File: `conn.csv.gz` (mode, connect, call, total).

**E3** (`qfp-client load`, in its own (2,2) networks, one per arm and repetition): after the network's setup, seven levels in a seeded random order, each 60 s of writes sent open-loop (one send every 1/rate s, whether or not earlier ones have finished) at 10, 25, 50, 75, 90, 100 and 110 % of the frozen ECDSA saturation at (2,2). At most 480 writes are in flight (below the gateway's limit of 500); a send beyond that is counted as dropped, not queued. Commit is taken at the gateway. Files per level: `tx.csv.gz`, `summary.json` (offered and achieved rate, sent, dropped, successful, latency).

A failure of E2, E3 or the ledger read-back is written to the network's `network.json` (`errors`) and shown by `qfp.py status`; the network's other measurements are kept.

## 6. Metrics

| # | Metric | Definition in the code |
|---|---|---|
| M1 | Execution time | last confirmation minus first send; confirmation = block delivered by every peer (writes) or response received (reads) |
| M2 | Throughput | confirmed successful transactions / M1 |
| M3 | Latency | per transaction: confirmation minus send; also at the gateway peer. Mean, median, p95, p99, max |
| M4 | Burst response | confirmation minus t0 (includes waiting for a free slot, the paper's "all at once") |
| M5 | Stages (writes) | endorse = endorsed − send; order = submitted − endorsed; commit = gateway commit − submitted; spread = all peers − gateway |
| M6 | Failures | by stage (`proposal`, `endorse`, `submit`, `commit_status`, `validation`, `read_check`, `result_check`) and gRPC or validation code |
| M7 | Blocks | per block: bytes, data and metadata bytes, orderer signature bytes, transactions, the orderer's byte count |
| M8 | Bytes per transaction | `txbytes.csv.gz`: envelope, certificates (every serialized identity's `id_bytes`: creator twice, one per endorser), signatures (envelope + endorsements), call arguments, read-write set and result, the rest |
| M9 | Ledger growth | `du -sb` of every peer's and the orderer's data volume after the network's runs |
| M10 | CPU and memory | per container, from the Docker Engine API: cumulative CPU before and after the run; memory sampled every 5 s (usage minus the reclaimable file cache, as `docker stats` shows it): each container's peak and the peak of the network's total (the sum over the containers within one sampling sweep); the client's own CPU from `getrusage` |
| M11 | Network | per container: bytes sent and received during the run (Docker API) |
| M12 | Setup times | every bring-up step |

## 7. The trial and the frozen values

`qfp.py trial-report <session>` reads the trial's records and writes `trial-report.json`:

- **C:** for each case, (8,8) ML-DSA-44 ("heaviest") and (2,2) ECDSA ("fastest"), a candidate (100, 200, 300) survives when at least one attempt completed all 10,000 writes with no container down; among the survivors, those within 5 % of the case's best write throughput qualify; C is the smallest candidate that qualifies in both cases.
- **E3's reference:** the best surviving ECDSA write throughput at (2,2).
- **Memory:** per network, the gateway peer's peak, the largest container and the total peak, as a share of the machine's memory with the machine's own use added (`MemTotal - MemAvailable` of `/proc/meminfo`, read when the report is made and no network is running: the kernel, Docker, the desktop and other programs, about 3 GB on the test machine); a warning above 85 %. A shortage would end in the kernel killing a container, which the driver records.
- **Projections** for every network of the main session: write and read throughput, bring-up and setup time, ledger read-back time per write and ledger bytes per write per peer, each from the trial's networks (throughput and times interpolated geometrically over log2(O) + log2(P); bytes linearly over the endorsements); hours and disk per network, with 15 % added for repeated runs. The disk of a network is the bytes per write per peer × (peers + 1, the orderer counting as one more peer) × the network's writes + 0.2 GB for the orderer's Raft log, added to what Docker's disk already holds. An E1 network above 80 % of that disk is listed as a proposed split, with the projection for the larger of its two halves (repetitions 1 to 3: 60 % of the grid's writes, plus the setup).

`qfp.py freeze --c N --saturation X [--split NET ...]` writes `config/thresholds.json` (with the quality thresholds) after the project lead's approval; a main session cannot be planned before it.

## 8. Machine conditions, order, quality and repeats

- **CPU isolation** (`scripts/run-linux.sh isolate`, runtime only): the systemd slice `qfp.slice` is allowed vCPUs 0 to N-2 (0 to 6 on the test machine) and `system.slice` and `user.slice` vCPU N-1 (7), so every process that is not the study (system services, Docker's daemon, the desktop, the remote-access agent, other projects' containers, the launcher, the driver, the host monitor) runs on the reserved CPU. The remote-access agent's login-screen process is set to the lowest priority there. Automatic package updates (`apt-daily.timer`, `apt-daily-upgrade.timer`, `unattended-upgrades`) are stopped. `release` undoes all of it. The image build temporarily allows Docker's daemon every CPU, because the build runs inside it.
- **Session start** (`scripts/run-linux.sh start` or `resume`): a preflight checks Docker (cgroup v2), the isolation, the stopped updates, that no package manager and no other session runs, 20 GB free on Docker's disk, 8 GB of memory available and the study's CPUs quiet over 6 s (at most 5 % busy); trial and main sessions refuse to start on a problem unless `--force` is given (recorded), smoke sessions record it. The session then restarts itself in a `tmux` session under `systemd-inhibit` (sleep and idle blocked), so the remote-desktop session can be closed; the driver also refuses to run if `qfp.slice` does not allow exactly the study's CPUs.
- **Order:** the 10 E1 topologies and the 5 E3 repetitions in a seeded random order; the two arms of each back to back in random order; the 50 runs of an E1 network shuffled; a split network's two halves back to back.
- **Host monitor** (`monitor/monitor-linux.sh`, adapted from the KPI's), every 5 s on the reserved CPU: the CPU time on the study's CPUs that the study did not use (their busy time minus the CPU time of `qfp.slice`), the machine's steal, whether the isolation is still in place, and whether a package manager or an update unit runs.
- **Flags of a run:** mean other CPU on the study's CPUs above 5 %; mean steal above 2 %; the isolation not in place at any sample (`cpuset`); system activity at any sample; swap growth above 64 MB; canary drift (below). A flagged run is repeated at the end of its network, up to 3 attempts; the headline attempt is the first clean one.
- **Canary:** the KPI's SHA3-256 canary at each network's start and every 60 min; the session reference is the median of its first three. A canary more than 3 % below the reference flags the runs since the previous canary.
- **Guard:** a network stops if Docker's disk passes 85 %.

## 9. Statistics

`analysis/run_all.py`: per cell (identity, organisations, peers, function, T), the median of the repetitions' headline values with a 95 % percentile bootstrap interval (10,000 resamples), memory included (per component and total); per comparison, ML-DSA-44 / ECDSA of the medians with a bootstrap interval from resampling each arm independently; a comparison is a difference when its interval excludes 1. The runs of a split network's two halves form the same cells. `analysis/selftest.py` checks these numbers on a synthetic session.
