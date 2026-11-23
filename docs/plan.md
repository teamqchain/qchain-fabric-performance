# QChain Fabric Performance: Consolidated Plan

**Version 1.2, 22 November 2026.** Status: **complete: the trial (E0) passed on 22 Nov, the main session (E1, E2, E3) ran on 23 Nov, and the findings are in [results.md](results.md); the paper draft is next.** The study: ECDSA against ML-DSA-44 identities on QChain's Fabric architecture, as transactions, peers and organisations grow. Code and results live in the private repository `teamqchain/qchain-fabric-performance`; the test machine is a dedicated university virtual machine (§3).

**This copy lives in the repository as `docs/plan.md`; it is the current plan. Where it disagrees with `docs/methodology.md` or `docs/data-dictionary.md`, those describe what the code does and win.** The reason for each choice is in `docs/decisions-log.md`; how the plan reached this version, and every earlier value, is in `docs/history.md`.

---

## 1. Aim and research questions

**Aim:** on the same Fabric fork, with identical network settings and an identical workload, measure what ML-DSA-44 identities (MSP certificates, endorsement signatures, orderer and node TLS) cost against ECDSA P-256 identities, and how that cost grows with transactions, peers and organisations. The design follows Nasir, Qasse, Abu Talib and Bou Nassif (2018): the same three metrics (execution time, latency, throughput) and the same three views.

| RQ | Question | Expected result (hypothesis, with the reason) |
|---|---|---|
| RQ1 | How do execution time, latency (average and tails) and throughput change for both arms as the **number of transactions** grows from 1 to 10,000, for writes and reads? | T = 1 and 10: no difference, the burst waits for the 2 s block timer. From T = 100, where a block of 100 fills at once, write throughput is lower with ML-DSA-44 (published: 10 to 28 % lower in two studies, 40 to 68 % in a thesis). Reads lose less: one client signature and one peer signature each. |
| RQ2 | How do they change as the **number of peers** grows from 1 to 8? | The overhead grows: every peer checks every signature of every block and receives larger blocks; on one machine all peers share the CPU. |
| RQ3 | How do they change as the **number of organisations**, and so endorsements, grows from 1 to 8? | Largest growth: each extra endorsement adds about 8.1 KB (a certificate and a signature) and one more signature to check with ML-DSA-44, against about 0.9 KB with ECDSA. |
| RQ4 | What else do ML-DSA-44 identities cost: **peak memory, CPU, transaction and block size, ledger growth, network traffic and TLS connection setup**? | Bytes first (a write is 2 to 3 times larger, so the ledger is too), higher peak memory under the same burst (larger endorsements held at the gateway peer), more CPU; TLS only when connections are opened. |

RQ1 is read from topology (1,1); RQ2 from the topologies (1,P); RQ3 from the topologies (O,P); RQ4 from every network, with E2 and E3.

## 2. What comes from QChain and what the study chooses

The comparison varies one thing: the identity type. QChain contributes its architecture; every network setting is the study's own and identical in both arms. QChain's deployed settings (10-transaction, 512 KB blocks; container memory limits) are not used anywhere in the study.

| Taken from QChain (its architecture) | Chosen by the study (identical for both arms) |
|---|---|
| The Fabric fork: `qchain-fabric` `e472b4ea`, `qchain-fabric-ca` `e82caf43`, `qchain-fabric-lib-go` `bd30150`, one build for both arms | Block settings: 100 transactions, 16 MB preferred, 99 MB absolute, 2 s timer (literature) |
| **The one variable:** ECDSA P-256 or ML-DSA-44 identities | Client load: bursts of T with at most C in flight, C frozen by the trial |
| The chaincode `qchaincode` 2.0, byte for byte | Container resources: **no memory limit and no CPU quota**; the study's CPUs reserved for it; peak memory is measured |
| The endorsement policy: MAJORITY of the organisations | The topologies: organisations and peers |
| One Raft orderer | The test machine and its CPU isolation |
| The node configuration files `core.yaml` and `orderer.yaml`, unchanged: goleveldb, gateway concurrency limit 500, block gossip off, TLS on | Workload, repetitions, order, quality rules |
| A Fabric CA per organisation, as live | |

Every difference from QChain's live network is listed in [live-differences.md](live-differences.md).

## 3. Network configuration and test machine

- **Channel** `mychannel`, capabilities V3_0 (channel), V2_0 (orderer), V2_5 (application); the live policies, with MAJORITY for endorsement and lifecycle. One Raft orderer.
- **Blocks:** MaxMessageCount 100, PreferredMaxBytes 16 MB, AbsoluteMaxBytes 99 MB, BatchTimeout 2 s.
- **Peers:** goleveldb, one state database per peer; gateway concurrency limit 500; block gossip off with `orgLeader` on (every peer pulls blocks from the orderer); TLS on.
- **Organisations:** General (the issuing organisation; its `peer0` is the gateway, as for the backend), Government, then `org3` to `org8` (`orgN.uae.com`). P is the total number of peers, P/O per organisation. One chaincode server per organisation. A Fabric CA per organisation, as on the live network (its own TLS is ECDSA in both arms); `issuer1@general` is enrolled with `role=issuer:ecert`.
- **Identities:** cryptogen makes every CA, node and admin with `ecdsa` (P-256) or `mldsa44`; the crypto provider is `SW` or `PQC` to match.
- **Containers:** read-only root file system, user 1000, no restart policy, **no memory limit and no CPU quota**. They run on the study's CPUs only (below); the machine's memory is the only memory ceiling.
- **Images,** built natively on the test machine (x86-64) from Dockerfiles, base images pinned by digest: Fabric `e472b4ea` with `-tags pqc -mod=vendor` (peer with the chaincode-as-a-service builder, orderer, osnadmin, configtxgen, cryptogen, peer CLI) and Fabric CA `e82caf43` in one image (Go 1.27, Debian 13, liboqs 0.16.0 static); chaincode `qchaincode` 2.0 (Node 18.20.8, the live image's entry point, folder, user and dependency tree); client (Go 1.27, fabric-gateway v1.7.0, grpc v1.68.0, the backend's versions); analysis (Python).
- **Verbatim rule:** the chaincode and all cryptogen and network files are copied byte for byte from `qchain-network`; the generated files differ from them only as listed in [live-differences.md](live-differences.md), and a self-check proves it.

**The test machine:** a dedicated university virtual machine, separate from QChain's live host.

| Item | Value |
|---|---|
| Hypervisor | VMware (full virtualisation; VMware Virtual Platform) |
| CPU | Intel Xeon Silver 4210R at 2.40 GHz (Cascade Lake), 8 vCPUs; AVX2 and AVX-512, AES-NI, no SHA extensions |
| Memory | 26.4 GiB, 2 GiB swap |
| Disk | 251 GB virtual disk, about 81 GB free for the study; synced 4 KB writes 0.23 ms, sequential writes 1.9 GB/s |
| Operating system | Ubuntu 22.04.5 LTS, Linux 6.8.0 |
| Runtime | Docker 29.8 (cgroup v2), buildx 0.37; Python 3.10 for the driver |
| Single-core reference (Go 1.27, standard library) | ML-DSA-44 sign 565 µs, verify 169 µs; ECDSA P-256 sign 46 µs, verify 97 µs |

- **CPU isolation:** the study's containers run under their own systemd slice (`qfp.slice`) on vCPUs 0 to 6; every other process of the machine (system services, Docker's daemon, the desktop, the remote-access agent, another project's containers, the launcher, the driver and the host monitor) is limited to vCPU 7. The remote-access agent's login-screen process keeps one core busy at all times; it runs on vCPU 7 at the lowest priority.
- **Qualification (22 Nov):** with every vCPU under full load the machine held a constant speed for 40 minutes (spread under 1 %; no steal reported); after the isolation, seven workers on the study's vCPUs each ran at the speed of a single worker alone (0.92 million SHA3-256 hashes per second), steady over 10 minutes, so the background load is confined to vCPU 7; the heaviest network, (8,8) with ML-DSA-44, completed 10,000 writes at C = 100 and 300 (44 to 47 writes/s, whole network at most 4.8 GB of memory) with no container lost.
- **Access:** remote desktop only; the machine has no access to the team's GitHub, so the code arrives as git bundles (which keep the pinned commits) by file transfer, and nothing is pushed from it.

## 4. Experiments

| ID | What | Networks | Runs | Purpose |
|---|---|---|---|---|
| E0 | Trial | 7 | 30, plus a short E2 and E3 check | Freezes C and E3's reference rate, checks memory and disk, freezes the quality thresholds, projects the time of the main session. Not reported. |
| E1 | Main grid | 20 (10 topologies x 2 arms) | 1,000 | RQ1 to RQ4 |
| E2 | Connection setup | inside E1's two (2,2) networks | 2 arms x 5 repetitions x (200 reads on a new connection + 200 on an open one) | The cost of a TLS handshake with each arm's certificates (RQ4) |
| E3 | Offered-load sweep | 10 of its own: (2,2), one per arm and repetition | 2 arms x 7 rates x 5 repetitions = 70 levels of 60 s | Latency against offered load |

**E2:** one `getCredential` read on a fresh connection (new TLS handshake, new Gateway, then the read) against the same read on a connection already open. Reads never reach the orderer, so the block settings play no part.

**E3:** writes sent open-loop at 10, 25, 50, 75, 90, 100 and 110 % of the ECDSA write saturation at (2,2) measured in the trial; the same rates for both arms, so the ML-DSA-44 arm reaches overload earlier. At most 480 writes in flight (below the gateway's limit of 500); a send beyond that is counted as dropped. Each repetition runs in a fresh (2,2) network of its own: one repetition sends about 95,500 writes (7 rates for 60 s each), and its own network keeps that load out of every E1 ledger (ledger growth is a measured result, M9).

## 5. Grid

Factors: identity (ECDSA P-256, ML-DSA-44) x function (`issueCredential`, `getCredential`) x T (1, 10, 100, 1,000, 10,000) x topology (10). 200 cells, 5 repetitions each, **1,000 runs**.

Long-running containers per topology = 1 orderer + P peers + O chaincode servers + O Fabric CAs = **1 + P + 2·O**. The client and tool containers start per run or per step.

| (O,P) | Peers per org | Endorsements per write | Containers |
|---|---|---|---|
| (1,1) (1,2) (1,4) (1,8) | 1 / 2 / 4 / 8 | 1 | 4 / 5 / 7 / 11 |
| (2,2) (2,4) (2,8) | 1 / 2 / 4 | 2 | 7 / 9 / 13 |
| (4,4) (4,8) | 1 / 2 | 3 | 13 / 17 |
| (8,8) | 1 | 5 | 25 |

Size of a credential write (`issueCredential`), measured in the main session (`bytes.csv`, 8 peers): at one endorsement 20.6 KB (ECDSA) and 39.9 KB (ML-DSA-44), of which certificates 2.4 and 17.0 KB; each further endorsement adds a certificate and a signature, about 0.9 KB (ECDSA) and 8.1 KB (ML-DSA-44): 2 endorsements 21.5 and 48.0 KB; 3: 22.4 and 56.1 KB; 5: 24.1 and 72.3 KB.

## 6. Workload and procedure

**Per network:** generate the crypto material and start; create the channel and join every peer; start the CAs and enrol `issuer1`; deploy the chaincode; untimed setup (100 holders with real ML-KEM-768 and ML-DSA-44 public keys, 1,000 credentials for the reads); warm-up (200 writes, 200 reads); canary; the network's runs in seeded random order (E1: 50 runs); E2 in the (2,2) networks; E3's seven rates in its own networks; read the ledger back and decode every block; tear down and delete the volumes.

**Order:** the 10 E1 topologies and the 5 E3 repetitions run in seeded random order; the two arms of each run back to back, in random order.

**Per run:** a fresh client process with a persistent connection to `peer0.general` and a block-event stream from every peer. At t0 the client releases T requests with at most C open at once. Writes: each holder in turn, 10 credential fields, a 64-character hash, a fixed real ML-DSA-44 signature and public key, `issuedAt` = send time, identical content in both arms. Reads: random credentials from the pool. Every failed transaction is counted by cause; the driver records every container's state (running, killed for memory, exit code) after each run.

**Sessions** run unattended: the launcher detaches them into a `tmux` session with sleep blocked, so the remote-desktop session is closed while they run.

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

**Memory:** the peak of every container and of each network's total, against the machine's memory (26.4 GiB, of which about 3.5 GB is in use by the machine's own processes). Above 85 % in any network, the project lead decides before the main run.

**Disk:** each network's ledger is projected from the trial's bytes per write. An E1 network projected above 80 % of Docker's disk is proposed for a split into two networks (repetitions 1 to 3, then 4 and 5); during runs a network stops if the disk passes 90 %.

**Time:** the main session's duration is projected network by network. The project lead decides any reduction; nothing is capped automatically.

The trial report (`qfp.py trial-report`) lists all of this; the project lead approves the values, then `qfp.py freeze` fixes them (C, E3's reference, any split) with the quality thresholds.

## 9. Quality and statistics (KPI rules)

Flags of a run: CPU time on the study's CPUs not used by the study above 5 % (mean over the run); steal above 2 %; the CPU isolation not in place at any sample; system activity (a package manager or automatic-update unit running); swap growth above 64 MB; canary drift above 3 % (canary at each network's start and every 60 min). A flagged run is repeated up to 3 times and the first clean attempt is kept; thresholds are frozen after E0. Conditions: CPU isolation in place, automatic package updates stopped, no other session, the session detached with sleep blocked, the remote-desktop session closed. Statistics: median of 5 repetitions with a 95 % bootstrap interval (10,000 resamples); each comparison reports ML-DSA-44 / ECDSA with a bootstrap interval and counts as a real difference when it excludes 1. SHA256SUMS and a privacy scan before results are committed.

## 10. Output

E1: 200 cells x about 20 numbers, 100 ECDSA-against-ML-DSA-44 comparisons, about 2.2 million transaction records, one byte breakdown per network. E2: 2,000 connection timings per arm. E3: 2 curves of 7 points, 5 repetitions each.

Figures: F1 transaction flow; F2-F4 execution time, latency, throughput against T at (1,1); F5 the same against P at T = 1,000 and 10,000; F6 ratio heatmap over P x T; F7 the same three against O at P = 4 and P = 8; F8 ratio heatmap over O x P; in F2-F8 every figure holds one function (writes or reads), and F2-F5 and F7 are drawn both as a line chart and as a bar chart; F9 bytes per write by part against endorsements; F10 ledger growth; F11 CPU per write by component; F12 peak memory (network total and gateway peer) against O at 8 peers; F13 orderer egress against P; F14 stages of a write; F15 connection setup (E2); F16 latency against offered load (E3). ECDSA blue `#0072B2`, ML-DSA-44 vermillion `#D55E00`, values at bar ends, every log axis labelled "(log scale)". Tables: T1 setup (with the test machine's specification), T2 what comes from QChain and what the study chooses, T3 topologies, T4 all cells (appendix), T5 ratios, T6 comparison with Nasir et al. 2018, the SmartCity repository, Hu and Lin, PQFabric.

## 11. Paper outline

1 Introduction; 2 Background; 3 Related work; 4 System under test (QChain's architecture, the study's settings, the test machine); 5 Methodology; 6 Results (6.1 more transactions RQ1, 6.2 more peers RQ2, 6.3 more organisations RQ3, 6.4 other costs RQ4 with E2, 6.5 offered load E3); 7 Discussion (each RQ against the literature, implications for QChain, limitations); 8 Conclusion and future work (several machines, BFT ordering, ML-DSA-65/87).

## 12. Time

- **Trial:** about an hour.
- **Main session:** projected by the trial, network by network. The networks with the most peers and endorsements take the longest, (8,8) with ML-DSA-44 above all: a 10,000-write run there takes about 4 minutes on the test machine, and each of the 5 repetitions sends 10,000 writes. The trial's projection is the reference.
- **No deadline:** the main session may run in several sittings (it resumes by network). Between sittings the images stay unchanged and automatic package updates stay stopped.

## 13. Threats to validity

One machine (peers share the CPU, no real network delay; the reference paper had the same limit); a virtual machine on a shared VMware host (other virtual machines' load is not visible from inside except as steal, which this hypervisor may not report; the canary, the steady-speed qualification, random order and back-to-back pairs guard against it); an x86 CPU different from the live host's (the live host's virtual CPU has no AVX2); one Raft orderer; the settings are the study's, not QChain's deployment (stated as the scope); open connections in the grid (E2 measures the handshake); QChain's node configuration (goleveldb, block gossip off) and Node 18 chaincode; synthetic but realistic credential content; no container limits, so the machine's 26.4 GiB is the only memory ceiling.

## 14. Steps

1. Repository and revert list (done 16 Nov).
2. Code every component (done 16 Nov; updated 17 and 22 Nov).
3. Test machine set up and qualified; images built natively on it; smoke session and the (8,8) check passed (22 Nov).
4. E0, the trial; report the values (C, E3's reference, memory, disk, time); the project lead approves; freeze (done 22 and 23 Nov: C = 300, E3's reference 346.2 writes/s, no split).
5. The main session (E1, E2, E3), in one or more sittings (done 23 Nov).
6. Analysis on the test machine (`qfp.py analyse`), then `qfp.py publish` (privacy scan, `SHA256SUMS`). **Transfer of the results:** the machine has no access to the team's GitHub, so the published folder `results/<session>/` is packed on the test machine into one archive with its sha256 (`tar -czf ../<session>-results.tar.gz -C results <session>`, kept in `~/qfp/`, outside the repository), moved to the development laptop by the remote desktop's file transfer into `~/Desktop/qfp-vm-transfer/`, checked there against its sha256 and unpacked into the repository's `results/`; `SHA256SUMS` inside the folder is checked again. Figures, tables and results documents are made on the laptop from the published folder, which is committed with the project lead's approval (done 23 Nov: [results.md](results.md)).
7. Machines reverted (revert list) (done 23 Nov; the list then left the repository).
8. **Paper draft** (next).
