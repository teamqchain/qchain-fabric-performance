<p align="center">
  <img src=".github/assets/qchain_logo.jpeg" width="220" alt="QChain logo" />
</p>

<h1 align="center">qchain-fabric-performance</h1>

<p align="center">
  <b>What does it cost to make every Hyperledger Fabric identity post-quantum?</b><br/>
  A performance study of QChain's Fabric network with ECDSA identities against ML-DSA-44 identities, as workload, peers and organisations grow, in the design of Nasir et al. (2018): 4 experiments, 1,000 main runs, one machine
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Fabric-3.1.5%20line%20(fork%20e472b4ea)-2F3134" alt="Fabric" />
  <img src="https://img.shields.io/badge/Identities-ECDSA%20P--256%20vs%20ML--DSA--44-0A66C2" alt="Identities" />
  <img src="https://img.shields.io/badge/Go-1.27-00ADD8" alt="Go" />
  <img src="https://img.shields.io/badge/liboqs-0.16.0-6E40C9" alt="liboqs" />
  <img src="https://img.shields.io/badge/Machine-Ubuntu%2022.04%20VM%20%C2%B7%20Xeon%20Silver%204210R-2F3134" alt="Machine" />
  <img src="https://img.shields.io/badge/Status-main%20run-F2A900" alt="Status" />
  <img src="https://img.shields.io/badge/License-Proprietary-red" alt="License" />
</p>

---

## 📊 Status

| | |
|---|---|
| **Plan** | version 1.2, 22 November 2026, approved by the project lead ([docs/plan.md](docs/plan.md); earlier versions in [docs/history.md](docs/history.md)) |
| **Literature review** | done: 45 papers, kept outside this repository |
| **Code** | written 16 to 22 November 2026; client unit tests run in the image build, generator self-check and analysis self-test pass |
| **Test machine** | a dedicated university virtual machine (Ubuntu 22.04, Intel Xeon Silver 4210R, 8 vCPUs, 26.4 GiB), set up and qualified on 22 November 2026; every change to it is recorded in [docs/revert-list.md](docs/revert-list.md) before it is made |
| **Images** | built natively on the test machine (x86-64); the chaincode image's dependency tree equals the live image's |
| **Measurements** | the trial (E0) passed on 22 November (7 networks, 30 runs, no failure) and its values were frozen on 23 November: C = 300, E3's reference rate 346.2 writes/s, no split; the main session (E1, E2, E3) started on 23 November |
| **Next** | the main session to its end (30 networks, about 8.3 hours), then the analysis, the transfer of the published results to the development laptop, and the figures and tables |

> ⚠️ **Private until publication.** This repository becomes public when the paper is published. Credentials never enter
> any file, and every run folder will pass an automatic privacy scan before it is committed.

---

## Overview

QChain issues academic credentials on a Hyperledger Fabric network whose every identity (organisation CA, peer, orderer, admin, client and node TLS) is signed with **ML-DSA-44**, in a fork of Fabric built by the team (Fabric 3.1.5 line, build tag `pqc`). The same fork builds a classical network with ECDSA P-256 identities. A post-quantum certificate is about 7 times the size of an ECDSA one (5.7 against 0.8 KB) and a signature about 34 times (2,420 against 70 bytes), and every transaction carries several of them, so the question is what that costs in practice.

This repository answers it by repeating the design of Nasir, Qasse, Abu Talib and Bou Nassif (2018, *Security and Communication Networks*): the same three metrics (execution time, latency, throughput), the same stress-test style (all requests at once), and the same three views (more transactions, more peers, more organisations), with the same Fabric fork for both arms. QChain contributes its architecture (the fork, the identity type, the chaincode, the endorsement policy, the orderer, the node configuration); every network setting is the study's own and identical in both arms.

| | Question |
|---|---|
| **RQ1** | How do execution time, latency (average and tails) and throughput change for both arms as the number of transactions grows from 1 to 10,000, for writes and reads? |
| **RQ2** | How do they change as the number of peers grows from 1 to 8? |
| **RQ3** | How do they change as the number of organisations, and so endorsements, grows from 1 to 8? |
| **RQ4** | What else do ML-DSA-44 identities cost: peak memory, CPU, transaction and block size, ledger growth, network traffic, TLS connection setup? |

---

## Architecture

```
 identity {ECDSA, ML-DSA-44}  x  function {issueCredential, getCredential}
          x  T {1, 10, 100, 1,000, 10,000}  x  topology (O organisations, P peers)
                                                 (1,1) (1,2) (1,4) (1,8)
                                                 (2,2) (2,4) (2,8)
                                                 (4,4) (4,8)  (8,8)

 test machine: Ubuntu 22.04 VM, x86-64, 8 vCPUs, 26.4 GiB
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │  qfp.slice, vCPUs 0 to 6: the study's containers, both arms                    │
 │  Go client ──gRPC/TLS──> peer0.general ──> endorsing peers (MAJORITY of orgs)  │
 │     │                          │                                               │
 │     └── block events <─────────┴── orderer (Raft, 1 node) ── blocks ──> peers  │
 │  one chaincode server and one Fabric CA per organisation                       │
 │  study settings, same in both arms: blocks of 100, no container limits         │
 └────────────────────────────────────────────────────────────────────────────────┘
        │                                         │
        ▼                                         ▼
  host monitor + canary                  results/ (every transaction, checksummed)
        │
        ▼
  analysis/  ──▶  tables T1–T6 · figures F1–F16

 vCPU 7: the rest of the machine (system services, Docker's daemon, desktop, launcher, driver, host monitor)
```

| Experiment | What it is |
|---|---|
| **E0** | the trial: fixes the burst cap C and E3's reference rate, checks memory and disk, freezes the quality thresholds, projects the main session's time |
| **E1** | the main grid: 2 identities x 2 functions x 5 workloads x 10 topologies x 5 repetitions = 1,000 runs |
| **E2** | connection setup, inside E1's (2,2) networks: a read on a new connection (TLS handshake) against one on an open connection |
| **E3** | offered-load sweep in its own (2,2) networks: writes at 10 to 110 % of the ECDSA saturation, latency against load |

What comes from QChain unchanged, and every difference from its live network, is in [docs/live-differences.md](docs/live-differences.md).

---

## What is measured

| Metric | What it is |
|---|---|
| Execution time, throughput | last confirmation minus first send; successful transactions per second |
| Latency | per transaction, until commit on all peers and at the gateway peer; mean, median, p95, p99, max |
| Stage times | endorse, order, commit, spread to all peers |
| Bytes | per transaction (certificates, signatures, payload) and per block; ledger growth |
| CPU and network | per transaction, per container |
| Memory | peak per container and for the whole network (no container has a memory limit) |
| Failures, blocks | counts by cause; transactions per block and why each block was cut |

The full list (M1 to M12) is in [docs/plan.md](docs/plan.md) §7.

---

## Test machine

| | The only machine of the study |
|---|---|
| Platform | a VMware virtual machine (VMware Virtual Platform), dedicated to the study and separate from QChain's live host |
| Processor | Intel Xeon Silver 4210R at 2.40 GHz (Cascade Lake), 8 vCPUs; AVX2, AVX-512 and AES-NI, no SHA extensions |
| Memory | 26.4 GiB, 2 GiB swap |
| Disk | 251 GB, about 81 GB free for the study; synced 4 KB writes 0.23 ms, sequential writes 1.9 GB/s |
| OS | Ubuntu 22.04.5 LTS, Linux 6.8.0 (automatic package updates stopped during the study) |
| Runtime | Docker 29.8 (cgroup v2), buildx 0.37, Python 3.10 |
| CPU isolation | the study's containers on vCPUs 0 to 6 (systemd slice `qfp.slice`); every other process on vCPU 7 |
| One core, Go 1.27 | ML-DSA-44 sign 565 µs, verify 169 µs; ECDSA P-256 sign 46 µs, verify 97 µs |

> QChain's live host is not used. In the paper it is described only as *a tested environment*.

---

## Technology stack

| Layer | Technology |
|---|---|
| Fabric | the team's post-quantum fork (`qchain-fabric` `e472b4ea`, `qchain-fabric-ca` `e82caf43`, `qchain-fabric-lib-go` `bd30150`), built natively for x86-64 with `-tags pqc` |
| Post-quantum | ML-DSA-44 through Go 1.27 `crypto/mldsa`; ML-KEM-768 through liboqs 0.16.0 |
| Chaincode | `qchaincode` 2.0, Node.js 18, as a service, copied verbatim from `qchain-network` |
| Client | Go 1.27, fabric-gateway v1.7.0, grpc v1.68.0 (the backend's versions) |
| Images | Docker (cgroup v2) on the test machine; base images pinned by digest |
| Launcher | Bash, with systemd slices, `tmux` and `systemd-inhibit` |
| Analysis | Python 3 with numpy, scipy and matplotlib |

---

## Repository structure

```
qchain-fabric-performance/
├── README.md                this file
├── LICENSE
├── docker/                  Dockerfiles: fabric (peer, orderer, CA, tools; x86-64, -tags pqc), chaincode, client, analysis
│   └── chaincode-lock/      the live chaincode image's lock file (recorded in step 3)
├── network/
│   ├── live/                qchain-network's files, byte for byte (SHA256SUMS)
│   └── gen/qfp_gen.py       one network from the live files: O organisations, P peers, ECDSA or ML-DSA-44
├── client/                  qfp-client (Go): setup, bursts, per-peer block events, E2, E3, block decoder, canary, tests
├── scripts/
│   ├── run-linux.sh         the launcher: CPU isolation, build, start/resume a session (preflight, tmux, sleep blocked)
│   └── qfp.py               the driver: images, networks, runs, Docker statistics, quality, trial report, analysis, publish
├── monitor/monitor-linux.sh the host monitor: other CPU on the study's CPUs, steal, isolation, package updates
├── analysis/                run_all.py (tables, figures F2–F16), figstyle.py, selftest.py
├── config/                  thresholds.json, frozen after the trial (written by `qfp.py freeze`)
├── results/                 published sessions (raw/ is local and ignored)
└── docs/                    plan, decisions, history, methodology, data dictionary, provenance, revert list, differences from live
```

---

## Running the study

Everything runs on the test machine, from this folder, in a terminal of the remote-desktop session. The code arrives as git bundles of this repository and of the source repositories (checked against `SHA256SUMS`), so the machine needs no access to GitHub, and nothing is pushed from it. A trial or main session refuses to start unless the machine is ready: CPU isolation in place, automatic package updates stopped, no package manager running, no other session, 20 GB free on Docker's disk, 8 GB of memory available, the study's CPUs quiet. It then runs detached in `tmux` with sleep blocked, so the remote-desktop session can be closed, and it ends with `session <name> finished` in its console log.

```bash
# 1. Before each sitting: CPU isolation and automatic updates stopped (sudo; undone by `release` or a reboot)
scripts/run-linux.sh isolate
scripts/run-linux.sh status

# 2. Once: the images (the build needs the internet and may use every CPU while it runs)
scripts/run-linux.sh build

# 3. The trial (E0), about an hour; then read its report and freeze the values
scripts/run-linux.sh start trial trial-1
python3 -I scripts/qfp.py trial-report trial-1        # C, E3's reference rate, memory, disk, time
python3 -I scripts/qfp.py freeze --c <C> --saturation <rate> [--split o8p8-mldsa44 ...]

# 4. The main session (E1, E2, E3), in one or more sittings
scripts/run-linux.sh start main main-1
scripts/run-linux.sh status main-1
scripts/run-linux.sh resume main-1                    # after an interruption: finished networks are kept

# 5. After the runs
python3 -I scripts/qfp.py analyse main-1              # tables and figures, inside the analysis image
python3 -I scripts/qfp.py publish main-1              # privacy scan, SHA256SUMS, results/main-1/
tar -czf ../main-1-results.tar.gz -C results main-1   # one archive of the published folder, outside the repository
(cd .. && sha256sum main-1-results.tar.gz > main-1-results.tar.gz.sha256)
scripts/run-linux.sh release                          # CPU settings and automatic updates back as they were
```

`tmux attach -t qfp-<session>` shows a running session (leave it with Ctrl-B, then D). Checks that need no session: `python3 -I scripts/qfp.py selfcheck` (generator against the live files, verbatim copies, the three Fabric clones, Docker) and `python3 -I scripts/qfp.py analysis-selftest` (the analysis on a synthetic session). `python3 -I scripts/qfp.py down` removes every study container and network volume left by an interrupted session. Raw results stay in the git-ignored `results/raw/<session>/`.

---

## Recent updates

- **23 November 2026: trial passed, values frozen, main session started.** The trial ran 7 networks and 30 runs in 42 minutes without a failure; the project lead froze C = 300, E3's reference rate 346.2 writes/s and no split of the (8,8) ML-DSA-44 network (its projected ledger, 80.8 % of Docker's disk, stays under the disk guard of 85 %). The main session started the same night.
- **22 November 2026: the test machine.** A dedicated university virtual machine (Ubuntu 22.04, Intel Xeon Silver 4210R, 8 vCPUs, 26.4 GiB) set up and qualified: a constant speed under sustained load, the study's containers isolated on seven of its vCPUs, the images built natively; a smoke session and the largest network, (8,8) with ML-DSA-44, passed. Plan 1.2.
- **17 November 2026: plan 1.1 approved.** QChain contributes its architecture; every network setting is the study's own and identical in both arms (blocks of 100 transactions, no container memory limits). Experiments E0 to E3.
- **16 November 2026: code written.** Network generator (self-checked against the live files), client, driver, launcher, Dockerfiles, analysis, documentation; the chaincode image's dependency tree matches the live image's.
- **16 November 2026: planning done.** Literature review (45 papers), plan approved, repository created.

The whole story, with the reasons for each turn and every earlier version of the plan, is in [docs/history.md](docs/history.md).

---

## Roadmap

- [x] Literature review
- [x] Research plan approved
- [x] Repository and revert list
- [x] Harness and network generator
- [x] Test machine set up and qualified
- [x] Images built natively (x86-64)
- [x] Trial (E0) and frozen values
- [ ] Main run (E1, E2, E3)
- [ ] Analysis, figures and tables
- [ ] Revert list closed
- [ ] Paper draft
- [ ] Public release with the paper

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/README.md](docs/README.md) | **start here**: reading order and conventions |
| [docs/plan.md](docs/plan.md) | the current research plan: questions, what comes from QChain, experiments, setup, metrics, the trial, statistics, time |
| [docs/methodology.md](docs/methodology.md) | what the code does when it measures |
| [docs/data-dictionary.md](docs/data-dictionary.md) | every file and column a session writes |
| [docs/provenance.md](docs/provenance.md) | every copied file and pinned version |
| [docs/decisions-log.md](docs/decisions-log.md) | the decisions in force and their reasons |
| [docs/history.md](docs/history.md) | how the plan changed: earlier versions, superseded values, failed sessions |
| [docs/live-differences.md](docs/live-differences.md) | what comes from QChain unchanged, and where the study's networks differ from its live network |
| [docs/revert-list.md](docs/revert-list.md) | the baseline of each machine used, every change made to it, the final checks |

---

## Conventions and rules

- **Privacy.** Run folders hold only allow-listed facts. Before a folder enters `results/`, every file is scanned for the machine's host name, user name, home path, IP and MAC addresses and machine id.
- **Verbatim copies.** The chaincode and the network files are copied byte for byte from `qchain-network`, except the differences listed in [docs/live-differences.md](docs/live-differences.md). A check script compares them.
- **Revert list.** Every change to a machine is written in [docs/revert-list.md](docs/revert-list.md) before it is made, and reverted at the end.
- **Shared machine.** Another project's containers run on the test machine. The study touches only its own Docker objects (names starting with `qfp`, label `org.qchain.qfp=1`): never `docker system prune`, never `docker compose down`.
- **Frozen thresholds.** The quality thresholds are not changed after the trial (E0).
- **Script names.** A script tied to the operating system ends with `-linux` (`run-linux.sh`, `monitor-linux.sh`); the driver `qfp.py` uses only Python's standard library and Docker.
- **Commits.** No co-author lines.

---

## Related repositories

| Repository | What it holds |
|------------|---------------|
| [qchain-network](https://github.com/teamqchain/qchain-network) | the live Hyperledger Fabric network and the chaincode this study copies |
| [qchain-fabric](https://github.com/teamqchain/qchain-fabric) | the post-quantum Fabric fork |
| [qchain-fabric-ca](https://github.com/teamqchain/qchain-fabric-ca) | the post-quantum Fabric CA fork |
| [qchain-fabric-lib-go](https://github.com/teamqchain/qchain-fabric-lib-go) | the post-quantum crypto provider (BCCSP) |
| [qchain-kpi](https://github.com/teamqchain/qchain-kpi) | the algorithm benchmarks whose method this study follows |
| [qchain-backend](https://github.com/teamqchain/qchain-backend) | the Go API whose Fabric client library versions the load generator uses |
| [qchain-docs](https://github.com/teamqchain/qchain-docs) | reports and the setup guide |
| [qchain-fabric-performance](https://github.com/teamqchain/qchain-fabric-performance) | this repository |

Some of these repositories are private.

---

## Team

A University of Sharjah capstone project, supervised by **Dr. Manar Abu Talib** and **Dr. Sohail Abbas**.

| Member | Role |
|--------|------|
| Mohammed Bin Ali Maqqavi ([@M0hd-Maqqavi](https://github.com/M0hd-Maqqavi)) | Project Manager |
| Mohammed Abdul Haris ([@mohammed-ah-14](https://github.com/mohammed-ah-14)) | Technical Lead |
| Mohammed Nihal ([@nihvp](https://github.com/nihvp)) | Quality Assurance Lead |
| Mohammed Obeid ([@MohammedObeid88](https://github.com/MohammedObeid88)) | Blockchain Specialist |

---

## License

**Proprietary — all rights reserved.** © 2026 QChain. This source code and its data are proprietary and confidential;
unauthorized copying, modification, distribution, or use is prohibited without prior written permission.
See [LICENSE](LICENSE).

---

## Disclaimer

This is an academic research project. The measurements will describe one machine under controlled conditions and the team's Fabric fork of 30 October 2026; they are not a certification of any algorithm or product. The live network's host is a tested environment only. Both networks of the study are built for the test machine and differ from QChain's live network in the ways listed in [docs/live-differences.md](docs/live-differences.md).
