# QChain Fabric Performance: Plan

**Version 1.1, 17 November 2026.** Status: **plan approved by the project lead (17 Nov); code and images updated; the trial (E0) is next.** The study: ECDSA against ML-DSA-44 identities on QChain's Fabric architecture, as transactions, peers and organisations grow.

This is the current plan. The reason for each choice is in [decisions-log.md](decisions-log.md); how the plan reached this version, and every earlier value, is in [history.md](history.md).

---

## 1. Aim and research questions

**Aim:** on the same Fabric fork, with identical network settings and an identical workload, measure what ML-DSA-44 identities (MSP certificates, endorsement signatures, orderer and node TLS) cost against ECDSA P-256 identities, and how that cost grows with transactions, peers and organisations. The design follows Nasir, Qasse, Abu Talib and Bou Nassif (2018): the same three metrics (execution time, latency, throughput) and the same three views.

| RQ | Question | Expected result (hypothesis, with the reason) |
|---|---|---|
| RQ1 | How do execution time, latency (average and tails) and throughput change for both arms as the **number of transactions** grows from 1 to 10,000, for writes and reads? | T <= 100: no visible difference, the 2 s block timer dominates. T >= 1,000: write throughput lower with ML-DSA-44 (published range -10 to -28 %). Reads lose less: one client signature and one peer signature each. |
| RQ2 | How do they change as the **number of peers** grows from 1 to 8? | The overhead grows: every peer checks every signature of every block and receives larger blocks; on one machine all peers share the CPU. |
| RQ3 | How do they change as the **number of organisations**, and so endorsements, grows from 1 to 8? | Largest growth: each extra endorsement adds about 7.8 KB and one more signature to check with ML-DSA-44, against about 1 KB with ECDSA. |
| RQ4 | What else do ML-DSA-44 identities cost: **peak memory, CPU, transaction and block size, ledger growth, network traffic and TLS connection setup**? | Bytes first (ledger about 2 to 3 times larger), higher peak memory under the same burst (larger endorsements held at the gateway peer), more CPU; TLS only when connections are opened. |

RQ1 is read from topology (1,1); RQ2 from the topologies (1,P); RQ3 from the topologies (O,P); RQ4 from every network, with E2 and E3.

## 2. What comes from QChain and what the study chooses

The comparison varies one thing: the identity type. QChain contributes its architecture; every network setting is the study's own and identical in both arms. QChain's deployed settings (10-transaction, 512 KB blocks; container memory limits) are not used anywhere in the study.

| Taken from QChain (its architecture) | Chosen by the study (identical for both arms) |
|---|---|
| The Fabric fork: `qchain-fabric` `e472b4ea`, `qchain-fabric-ca` `e82caf43`, `qchain-fabric-lib-go` `bd30150`, one build for both arms | Block settings: 100 transactions, 16 MB preferred, 99 MB absolute, 2 s timer (literature) |
| **The one variable:** ECDSA P-256 or ML-DSA-44 identities | Client load: bursts of T with at most C in flight, C frozen by the trial |
| The chaincode `qchaincode` 2.0, byte for byte | Container resources: **no memory or CPU limits**; peak memory is measured |
| The endorsement policy: MAJORITY of the organisations | The topologies: organisations and peers |
| One Raft orderer | The machine and the Colima VM |
| The node configuration files `core.yaml` and `orderer.yaml`, unchanged: goleveldb, gateway concurrency limit 500, block gossip off, TLS on | Workload, repetitions, order, quality rules |
| A Fabric CA per organisation, as live | |

Every difference from QChain's live network is listed in [live-differences.md](live-differences.md).

## 3. Network configuration

- **Channel** `mychannel`, capabilities V3_0 (channel), V2_0 (orderer), V2_5 (application); the live policies, with MAJORITY for endorsement and lifecycle. One Raft orderer.
- **Blocks:** MaxMessageCount 100, PreferredMaxBytes 16 MB, AbsoluteMaxBytes 99 MB, BatchTimeout 2 s.
- **Peers:** goleveldb, one state database per peer; gateway concurrency limit 500; block gossip off with `orgLeader` on (every peer pulls blocks from the orderer); TLS on.
- **Organisations:** General (the issuing organisation; its `peer0` is the gateway, as for the backend), Government, then `org3` to `org8` (`orgN.uae.com`). P is the total number of peers, P/O per organisation. One chaincode server per organisation. A Fabric CA per organisation, as on the live network (its own TLS is ECDSA in both arms); `issuer1@general` is enrolled with `role=issuer:ecert`.
- **Identities:** cryptogen makes every CA, node and admin with `ecdsa` (P-256) or `mldsa44`; the crypto provider is `SW` or `PQC` to match.
- **Containers:** read-only root file system, user 1000, no restart policy, **no memory or CPU limits**. The only ceiling is the Colima VM.
- **Machine:** MacBook Air M1 (4 performance + 4 efficiency cores), 8 GB, macOS 27.2.1. Colima `vz`, aarch64, 4 vCPUs, 5 GiB memory, 60 GiB disk. Cooling pad used for every run.
- **Images,** built natively for arm64 inside Colima from Dockerfiles, base images pinned by digest: Fabric `e472b4ea` with `-tags pqc -mod=vendor` (peer with the chaincode-as-a-service builder, orderer, osnadmin, configtxgen, cryptogen, peer CLI) and Fabric CA `e82caf43` in one image (Go 1.27, Debian 13, liboqs 0.16.0 static); chaincode `qchaincode` 2.0 (Node 18.20.8, the live image's entry point, folder, user and dependency tree); client (Go 1.27, fabric-gateway v1.7.0, grpc v1.68.0, the backend's versions); analysis (Python).
- **Verbatim rule:** the chaincode and all cryptogen and network files are copied byte for byte from `qchain-network`; the generated files differ from them only as listed in [live-differences.md](live-differences.md), and a self-check proves it.

## 4. Experiments

| ID | What | Networks | Runs | Purpose |
|---|---|---|---|---|
| E0 | Trial | 7 | 30, plus a short E2 and E3 check | Freezes C and E3's reference rate, checks memory and disk, freezes the quality thresholds, projects the time of the main session. Not reported. |
| E1 | Main grid | 20 (10 topologies x 2 arms) | 1,000 | RQ1 to RQ4 |
| E2 | Connection setup | inside E1's two (2,2) networks | 2 arms x 5 repetitions x (200 reads on a new connection + 200 on an open one) | The cost of a TLS handshake with each arm's certificates (RQ4) |
| E3 | Offered-load sweep | 10 of its own: (2,2), one per arm and repetition | 2 arms x 7 rates x 5 repetitions = 70 levels of 60 s | Latency against offered load |

**E2:** one `getCredential` read on a fresh connection (new TLS handshake, new Gateway, then the read) against the same read on a connection already open. Reads never reach the orderer, so the block settings play no part.

**E3:** writes sent open-loop at 10, 25, 50, 75, 90, 100 and 110 % of the ECDSA write saturation at (2,2) measured in the trial; the same rates for both arms, so the ML-DSA-44 arm reaches overload earlier. At most 480 writes in flight (below the gateway's limit of 500); a send beyond that is counted as dropped. Each repetition runs in a fresh (2,2) network: one repetition writes about 100,000 transactions, and inside an E1 network the sweep would fill the disk and distort that network's ledger growth (M9).

## 5. Grid

Factors: identity (ECDSA P-256, ML-DSA-44) x function (`issueCredential`, `getCredential`) x T (1, 10, 100, 1,000, 10,000) x topology (10). 200 cells, 5 repetitions each, **1,000 runs**.

Long-running containers per topology = 1 orderer + P peers + O chaincode servers + O Fabric CAs = **1 + P + 2·O**. The client and tool containers start per run or per step.

| (O,P) | Peers per org | Endorsements per write | Containers |
|---|---|---|---|
| (1,1) (1,2) (1,4) (1,8) | 1 / 2 / 4 / 8 | 1 | 4 / 5 / 7 / 11 |
| (2,2) (2,4) (2,8) | 1 / 2 / 4 | 2 | 7 / 9 / 13 |
| (4,4) (4,8) | 1 / 2 | 3 | 13 / 17 |
| (8,8) | 1 | 5 | 25 |

Measured write size at one endorsement: 20.6 KB (ECDSA) and 39.9 KB (ML-DSA-44). Estimated: 2 endorsements 22 and 48 KB; 3: 23 and 55 KB; 5: 25 and 71 KB.

## 6. Workload and procedure

**Per network:** generate the crypto material and start; create the channel and join every peer; start the CAs and enrol `issuer1`; deploy the chaincode; untimed setup (100 holders with real ML-KEM-768 and ML-DSA-44 public keys, 1,000 credentials for the reads); warm-up (200 writes, 200 reads); canary; the network's runs in seeded random order (E1: 50 runs); E2 in the (2,2) networks; E3's seven rates in its own networks; read the ledger back and decode every block; tear down and delete the volumes.

**Order:** the 10 E1 topologies and the 5 E3 repetitions run in seeded random order; the two arms of each run back to back, in random order.

**Per run:** a fresh client process with a persistent connection to `peer0.general` and a block-event stream from every peer. At t0 the client releases T requests with at most C open at once. Writes: each holder in turn, 10 credential fields, a 64-character hash, a fixed real ML-DSA-44 signature and public key, `issuedAt` = send time, identical content in both arms. Reads: random credentials from the pool. Every failed transaction is counted by cause; the driver records every container's state (running, killed for memory, exit code) after each run.

## 7. Metrics (each transaction stored with its timestamps)

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
| M10 | CPU and memory | CPU-seconds per transaction and peak memory for the client, gateway peer, other peers, orderer, chaincode servers and CAs; the network's total peak memory |
| M11 | Network per transaction | orderer egress, gateway-peer traffic |
| M12 | Setup times | crypto generation, channel join, chaincode deploy |

E2 adds: connection + TLS handshake + one read, against the same read on an open connection. E3 adds: achieved rate, dropped sends and latency at each offered rate.

## 8. The trial (E0)

| Network | Runs | Why |
|---|---|---|
| (1,1), both arms | writes and reads at T = 1, 10, 100 | the smallest topology works |
| (2,2), both arms | 10,000 reads at C = 200; 10,000 writes at C = 100, 200, 300; short E2 and E3 checks | the fastest case; E3's saturation reference |
| (8,8), both arms | 10,000 reads at C = 200; 10,000 writes at C = 100, 200, 300 | the heaviest case: memory, throughput |
| (1,8), ML-DSA-44 | 10,000 reads and writes at C = 300 | eight peers, one endorsement, at the highest C |

Writes run with C rising, so that a network that runs out of memory at a high C has already measured the lower ones.

**C** (candidates 100, 200, 300: at least one block, below the gateway's limit of 500): among the candidates that complete all 10,000 writes with no container down, the smallest within 5 % of the best write throughput in **both** the heaviest case (8,8) ML-DSA-44 and the fastest case (2,2) ECDSA. One C for every run of the main session.

**E3's reference:** the best ECDSA write throughput at (2,2).

**Memory:** the peak of every container and of each network's total, against the Colima VM's memory. Above 85 % in any network, the project lead decides before the main run (stop the CAs during measurement, or a larger VM).

**Disk:** each network's ledger is projected from the trial's bytes per write. An E1 network projected above 80 % of the Colima disk is proposed for a split into two networks (repetitions 1 to 3, then 4 and 5); during runs a network stops if the disk passes 85 %.

**Time:** the main session's duration is projected network by network. The project lead decides any reduction; nothing is capped automatically.

The trial report (`qfp.py trial-report`) lists all of this; the project lead approves the values, then `qfp.py freeze` fixes them (C, E3's reference, any split) with the quality thresholds.

## 9. Quality and statistics (KPI rules)

Flags: other macOS CPU above 5 %, thermal pressure above nominal, battery or Low Power Mode, swap growth during the run, canary drift above 3 % (canary at each network's start and every 60 min). A flagged run is repeated up to 3 times and the first clean attempt is kept; thresholds are frozen after E0. Conditions: background services paused, Wi-Fi off during runs, apps closed (VS Code included), automatic macOS updates off, `caffeinate`, adapter connected, cooling pad. Statistics: median of 5 repetitions with a 95 % bootstrap interval (10,000 resamples); each comparison reports ML-DSA-44 / ECDSA with a bootstrap interval and counts as a real difference when it excludes 1. SHA256SUMS and a privacy scan before results are committed.

## 10. Output

E1: 200 cells x about 20 numbers, 100 ECDSA-against-ML-DSA-44 comparisons, about 2.2 million transaction records, one byte breakdown per network. E2: 2,000 connection timings per arm. E3: 2 curves of 7 points, 5 repetitions each.

Figures: F1 transaction flow; F2-F4 execution time, latency, throughput against T at (1,1); F5 the same against P at T = 1,000 and 10,000; F6 ratio heatmap over P x T; F7 against O at P = 4 and P = 8; F8 ratio heatmap over O x P; F9 bytes per write by part against endorsements; F10 ledger growth; F11 CPU per write by component; F12 peak memory (network total and gateway peer) against O; F13 orderer egress against P; F14 stages of a write; F15 connection setup (E2); F16 latency against offered load (E3). ECDSA blue `#0072B2`, ML-DSA-44 vermillion `#D55E00`, values at bar ends, every log axis labelled "(log scale)". Tables: T1 setup, T2 what comes from QChain and what the study chooses, T3 topologies, T4 all cells (appendix), T5 ratios, T6 comparison with Nasir et al. 2018, the SmartCity repository, Hu and Lin, PQFabric.

## 11. Paper outline

1 Introduction; 2 Background; 3 Related work; 4 System under test (QChain's architecture and the study's settings); 5 Methodology; 6 Results (6.1 more transactions RQ1, 6.2 more peers RQ2, 6.3 more organisations RQ3, 6.4 other costs RQ4 with E2, 6.5 offered load E3); 7 Discussion (each RQ against the literature, implications for QChain, limitations); 8 Conclusion and future work (several machines, BFT ordering, ML-DSA-65/87).

## 12. Time

- **Trial:** about 1.5 h.
- **Main session:** projected by the trial, network by network. An earlier test (17 Nov) measured about 19 writes per second at (8,8) with ML-DSA-44, so one 10,000-write run there takes about 10 min; the main session may take 20 h or more.
- **No deadline:** the main session may run in several sittings (it resumes by network). Between sittings the images stay unchanged and automatic macOS updates stay off; during a long pause the updates may be switched on and off again.

## 13. Threats to validity

One machine (peers share the CPU, no real network delay; the reference paper had the same limit); a fanless laptop (random order, back-to-back pairs, thermal flags); arm64, not the live network's x86; one Raft orderer; the settings are the study's, not QChain's deployment (stated as the scope); open connections in the grid (E2 measures the handshake); QChain's node configuration (goleveldb, block gossip off) and Node 18 chaincode; synthetic but realistic credential content; no container limits, so the Colima VM's 5 GiB is the only memory ceiling.

## 14. Steps

1. Repository and revert list (done 16 Nov).
2. Code every component (done 16 Nov; updated for this plan 17 Nov).
3. Installs and image builds (done 16 Nov; images rebuilt 17 Nov).
4. **E0, the trial;** report the values (C, E3's reference, memory, disk, time); the project lead approves; freeze.
5. The main session (E1, E2, E3), in one or more sittings.
6. Analysis, figures, tables; results documents.
7. Test machine reverted (revert list).
8. Paper draft.
