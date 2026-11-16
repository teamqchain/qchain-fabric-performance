# QChain Fabric Performance: Consolidated Plan

**Version 1.0, 16 November 2026.** Status: **plan approved (16 Nov); coding next.** The study: ECDSA against ML-DSA-44 identities on QChain's Fabric network, as workload, peers and organisations grow.

This copy lives in the repository as `docs/plan.md`; it is the planning snapshot. Changes to the design are recorded in `docs/decisions-log.md` first; where the two differ, the decisions log wins.

---

## 1. Aim and research questions

**Aim:** measure what replacing every Fabric identity (MSP certificates, endorsement signatures, orderer and node TLS) with ML-DSA-44 costs, and how that cost grows with workload, peers and organisations. The design follows Nasir, Qasse, Abu Talib and Bou Nassif (2018).

| RQ | Question | Expected result (hypothesis, with the reason) |
|---|---|---|
| RQ1 | How do execution time, latency (average and tails) and throughput change from 1 to 10,000 transactions, for writes and reads? | T <= 100: no visible difference, the 2 s block timer dominates. T >= 1,000: write throughput 10 to 30 % lower (published range -10 to -28 %). Reads lose less: one client signature and one peer signature each. |
| RQ2 | How does the overhead change as peers grow from 1 to 8? | It grows: every peer checks every signature of every block and downloads bigger blocks; on one machine all peers share the CPU. |
| RQ3 | How does it change as organisations, and so endorsements, grow from 1 to 8? | Largest growth: each extra endorsement adds about 7.8 KB and one more signature to check with ML-DSA, against about 1 KB with ECDSA. |
| RQ4 | Where does the cost come from: bytes, CPU or TLS connection setup? | Mainly bytes (ledger about 2 to 3 times larger), then CPU; TLS only when connections are opened. |

Paper sections: RQ1 is read from topology (1,1) (more transactions); RQ2 from topologies (1,P) (more peers); RQ3 from topologies (O,P) (more organisations). Together they answer RQ4.

## 2. Experiments

| ID | What | Topology | Runs | Block settings | Purpose |
|---|---|---|---|---|---|
| E0 | Smoke test and trial | (1,1), (2,2), (1,8), (8,8) | about 15 | E1's | Fix the burst cap C, check memory and disk, freeze the quality thresholds, project the total time. Not reported. |
| E1 | Main grid | 10 topologies | 1,000 | 100 tx / 16 MB / 2 s | RQ1 to RQ4 |
| E2 | Connection-setup test | (2,2), inside E1's networks | 2 arms x 5 repetitions x 200 connections | E1's (reads never reach the orderer) | Cost of the backend's new connection per call with ML-DSA TLS (RQ4) |
| E3 | Live-settings check | (2,2), two extra networks | 100 (2 identities x 2 functions x 5 T x 5 repetitions) | **live: 10 tx / 512 KB / 2 s** | Link to QChain as deployed; effect of the block change |
| E4 | Offered-load sweep, only if E1 + E2 + E3 project under 15 h | (2,2), writes, inside E1's networks | 70 | E1's | Latency against offered load at 10, 25, 50, 75, 90, 100, 110 % of the trial's ECDSA saturation, 60 s each |

## 3. Setup

- **Machine:** MacBook Air M1 (4 performance + 4 efficiency cores), 8 GB, macOS 27.2. Colima `vz`, aarch64, 4 vCPUs, 5 GiB memory, **60 GiB disk** (the Mac has 75 GiB free). Cooling pad used for every run.
- **Images,** built natively for arm64 inside Colima from Dockerfiles, base images pinned by digest: builder (Go 1.27, Debian 13, OpenSSL 3.5, liboqs 0.16.0 static); Fabric `e472b4ea` with `-tags pqc -mod=vendor` (peer with the chaincode-as-a-service builder, orderer, osnadmin, configtxgen, cryptogen, peer CLI); Fabric CA `e82caf43` with `-tags pkcs11,pqc`; chaincode `qchaincode` 2.0 (Node 18.20.8, Debian 12, dependency versions pinned to the live image by one read-only VM command); client (Go 1.27, fabric-gateway v1.7.0, grpc v1.68.0, the backend's versions); analysis (Python). If `-mod=vendor` fails, the build container (never the repository) gets fabric-lib-go `bd30150` at Obeid's path.
- **Network per topology** generated from the live `qchain-network` files: channel `mychannel` (V3_0 / V2_0 / V2_5), one Raft orderer, live policies with MAJORITY for endorsement and lifecycle, goleveldb, TLS on, gateway limit 500, block gossip off, live memory limits (peer 512 MB, orderer 384 MB, chaincode 192 MB, CA 256 MB), containers read-only, user 1000.
- **Organisations and identities:** General (issuing organisation; its `peer0` is the gateway, as for the backend), Government, then `org3` to `org8` (`orgN.uae.com`). Every CA, node and admin comes from cryptogen with `mldsa44` or `ecdsa`; the provider is `PQC` or `SW` to match. Per-organisation Fabric CA as on the live VM (its own TLS is ECDSA in both arms); `issuer1@general` is enrolled with `role=issuer:ecert`. One chaincode server per organisation.
- **Verbatim rule:** the chaincode and all cryptogen/network files are copied byte for byte from `qchain-network`, except the differences in `live-differences.md`.

## 4. Grid

Factors: identity (ECDSA P-256, ML-DSA-44) x function (`issueCredential`, `getCredential`) x T (1, 10, 100, 1,000, 10,000) x topology (10). 200 cells, 5 repetitions each, **1,000 runs**.

Long-running containers per topology = 1 orderer + P peers (P/O per organisation) + O chaincode servers + O Fabric CAs = **1 + P + 2·O**. The client and tool containers start per run or per step.

| (O,P) | Peers per org | Endorsements per transaction | Containers |
|---|---|---|---|
| (1,1) (1,2) (1,4) (1,8) | 1 / 2 / 4 / 8 | 1 | 4 / 5 / 7 / 11 |
| (2,2) (2,4) (2,8) | 1 / 2 / 4 | 2 | 7 / 9 / 13 |
| (4,4) (4,8) | 1 / 2 | 3 | 13 / 17 |
| (8,8) | 1 | 5 | 25 |

Estimated transaction size (to be measured): 1 endorsement about 21 KB (ECDSA) and 40 KB (ML-DSA-44); 2: 22 and 48 KB; 3: 23 and 55 KB; 5: 25 and 71 KB.

## 5. Workload and procedure

Per network: generate crypto material and start; create the channel and join every peer; start the CAs and enrol `issuer1`; deploy the chaincode; untimed setup (100 holders with real ML-KEM-768 and ML-DSA-44 public keys, 1,000 credentials for the reads); warm-up (200 writes, 200 reads); canary; the 50 runs in seeded random order; E2 (and E4) in the (2,2) networks; read the ledger back and decode every block; tear down and delete the volumes. The 22 networks (20 for E1, 2 for E3) run in seeded random order; the ECDSA and ML-DSA networks of a topology run back to back, in random order.

Per run: a fresh client process with a persistent connection to `peer0.general` and a block-event stream from every peer. At t0 the client releases T requests with at most C open at once (C is the smallest of 200, 300, 400, 480 reaching within 5 % of the best throughput in E0, then frozen). Writes: each holder in turn, 10 credential fields, a 64-character hash, a fixed real ML-DSA-44 signature and public key, `issuedAt` = send time, identical content in both arms. Reads: random credentials from the pool. After each run wait until every peer has the same block height, then 5 s. Every failed transaction is counted by cause; a crash of the harness stops the run.

## 6. Metrics (each transaction stored with its timestamps)

| # | Metric | Definition |
|---|---|---|
| M1 | Execution time | last confirmation minus first send |
| M2 | Throughput | successful transactions / M1 |
| M3 | Latency per transaction | commit on all peers minus send; also at the gateway peer; mean, median, p95, p99, max |
| M4 | Burst response time | commit minus t0 |
| M5 | Stage times (writes) | endorse, order, commit at the gateway, spread to all peers |
| M6 | Failures | count and rate by cause |
| M7 | Blocks | count, transactions per block, cut reason |
| M8 | Bytes per transaction | certificates, signatures, payload, rest; bytes per block |
| M9 | Ledger growth | per peer and network; state database size |
| M10 | CPU per transaction | CPU-seconds and peak memory for client, gateway peer, other peers, orderer, chaincode servers, CAs |
| M11 | Network per transaction | orderer egress, gateway-peer traffic |
| M12 | Setup times | crypto generation, channel join, chaincode deploy |

E2 adds: connection + TLS handshake + one read, against the same read on an open connection.

## 7. Quality and statistics (KPI rules)

Flags: other macOS CPU above 5 %, thermal pressure above nominal, battery or Low Power Mode, swap growth during the run, canary drift above 3 % (canary at start, every 60 min, end). A flagged run is repeated up to 3 times and the first clean attempt is kept; thresholds are frozen after E0. Conditions: background services paused, Wi-Fi off during runs, apps closed (VS Code included), `caffeinate`, adapter connected, cooling pad. Statistics: median of 5 repetitions with a 95 % bootstrap interval (10,000 resamples); each comparison reports ML-DSA / ECDSA with a bootstrap interval and counts as a real difference when it excludes 1. SHA256SUMS and a privacy scan before results are committed.

## 8. Output

E1: 200 cells x about 20 numbers, 100 ECDSA-against-ML-DSA comparisons, about 2.2 million transaction records, one byte breakdown per network. E2: 2,000 connection timings. E3: 20 cells, 10 comparisons, live against our blocks at (2,2). E4: 2 curves of 7 points.

Figures: F1 transaction flow; F2-F4 execution time, latency, throughput against T at (1,1); F5 the same against P at T = 1,000 and 10,000; F6 ratio heatmaps over P x T; F7 against O at P = 8 and P = 4; F8 ratio heatmap over O x P; F9 bytes per transaction by part against endorsements; F10 ledger growth; F11 CPU per transaction; F12 orderer egress against P; F13 stage breakdown; F14 connection-setup times; F15 E3; F16 E4. ECDSA blue `#0072B2`, ML-DSA-44 vermillion `#D55E00`, values at bar ends, every log axis labelled "(log scale)". Tables: T1 setup, T2 differences from live, T3 topologies, T4 all cells (appendix), T5 ratios, T6 comparison with Nasir et al. 2018, the SmartCity repository, Hu and Lin, PQFabric.

## 9. Paper outline

1 Introduction; 2 Background; 3 Related work; 4 System under test; 5 Methodology; 6 Results (6.1 one peer RQ1, 6.2 peers RQ2, 6.3 organisations RQ3, 6.4 sources of the cost RQ4 with E2, 6.5 as deployed E3 and E4); 7 Discussion (each RQ against the literature, implications for QChain, limitations); 8 Conclusion and future work (several machines, BFT ordering, ML-DSA-65/87).

## 10. Time budget

Coding about 2 days; installs and image builds 2 to 3 h; E0 about 3 h; **E1 + E2 + E3 about 16 h** (range 12 to 26 h); E4 1.5 h only if the trial projects under 15 h; analysis about 1 day. Estimate: 22 networks x (about 8 min setup + about 8 min overhead + about 4 min ledger read-back + 13 to 32 min measuring) plus about 15 % repeats. Guards: if E0 projects more than 36 h, T is capped at 5,000; if (8,8) exceeds 85 % of the Colima VM's memory, stop the CAs during measurement, then drop P = 8; disk guard: a network is aborted above 85 % of the Colima disk (see the decisions log for the 60 GiB disk and the (8,8) split).

## 11. Threats to validity

One machine (peers share the CPU, no real network delay; the reference paper had the same limit); a fanless laptop (random order, back-to-back pairs, thermal flags); arm64, not the VM's x86; one orderer and Raft only; block settings differ from live (E3 measures it); open connections (E2 measures it); Node 18 chaincode and goleveldb; synthetic but realistic credential content.

## 12. Steps

1 repository and revert list; 2 code every component; 3 one read-only VM command (chaincode dependency versions), installs and image builds; 4 E0 and report the frozen values (C, memory and disk decisions, projection, whether E4 runs); 5 unattended main run; 6 analysis, figures, tables.
