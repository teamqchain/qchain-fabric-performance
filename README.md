<p align="center">
  <img src=".github/assets/qchain_logo.jpeg" width="220" alt="QChain logo" />
</p>

<h1 align="center">qchain-fabric-performance</h1>

<p align="center">
  <b>What does it cost to make every Hyperledger Fabric identity post-quantum?</b><br/>
  A performance study of QChain's Fabric network with ECDSA identities against ML-DSA-44 identities, as workload, peers and organisations grow, in the design of Nasir et al. (2018): 5 experiments, 1,000 main runs, one machine
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Fabric-3.1.5%20line%20(fork%20e472b4ea)-2F3134" alt="Fabric" />
  <img src="https://img.shields.io/badge/Identities-ECDSA%20P--256%20vs%20ML--DSA--44-0A66C2" alt="Identities" />
  <img src="https://img.shields.io/badge/Go-1.27-00ADD8" alt="Go" />
  <img src="https://img.shields.io/badge/liboqs-0.16.0-6E40C9" alt="liboqs" />
  <img src="https://img.shields.io/badge/Machine-MacBook%20Air%20M1%20%C2%B7%20Colima-2F3134" alt="Machine" />
  <img src="https://img.shields.io/badge/Status-code%20written%2C%20not%20run%20yet-F2A900" alt="Status" />
  <img src="https://img.shields.io/badge/License-Proprietary-red" alt="License" />
</p>

---

## 📊 Status

| | |
|---|---|
| **Plan** | approved by the project lead on 16 November 2026 ([docs/plan.md](docs/plan.md)) |
| **Literature review** | done: 45 papers, kept outside this repository |
| **Code** | written and unit-tested on 16 November 2026 (client tests, generator self-check, plan checks); images not built yet |
| **Measurements** | not started |
| **Test machine** | one MacBook Air M1; every change to it is recorded in [docs/revert-list.md](docs/revert-list.md) before it is made |
| **Next** | installs (revert list first), the arm64 image builds, the trial (E0), then the unattended main run |

> ⚠️ **Private until publication.** This repository becomes public when the paper is published. Credentials never enter
> any file, and every run folder will pass an automatic privacy scan before it is committed.

---

## Overview

QChain issues academic credentials on a Hyperledger Fabric network whose every identity (organisation CA, peer, orderer, admin, client and node TLS) is signed with **ML-DSA-44**, in a fork of Fabric built by the team (Fabric 3.1.5 line, build tag `pqc`). The same fork builds a classical network with ECDSA P-256 identities. Post-quantum certificates and signatures are 4 to 80 times larger than their ECDSA counterparts, and every transaction carries several of them, so the question is what that costs in practice.

This repository answers it by repeating the design of Nasir, Qasse, Abu Talib and Bou Nassif (2018, *Security and Communication Networks*): the same three metrics (execution time, latency, throughput), the same stress-test style (all requests at once), and the same three views (more transactions, more peers, more organisations), with the same Fabric fork for both arms.

| | Question |
|---|---|
| **RQ1** | How do execution time, latency (average and tails) and throughput change from 1 to 10,000 transactions, for writes and reads? |
| **RQ2** | How does the overhead change as peers grow from 1 to 8? |
| **RQ3** | How does it change as organisations, and so endorsements, grow from 1 to 8? |
| **RQ4** | Where does the cost come from: bytes, CPU or TLS connection setup? |

---

## Architecture

```
 identity {ECDSA, ML-DSA-44}  x  function {issueCredential, getCredential}
          x  T {1, 10, 100, 1,000, 10,000}  x  topology (O organisations, P peers)
                                                 (1,1) (1,2) (1,4) (1,8)
                                                 (2,2) (2,4) (2,8)
                                                 (4,4) (4,8)  (8,8)

 Colima VM (arm64, 4 vCPU, 5 GiB)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  Go client ──gRPC/TLS──> peer0.general ──> endorsing peers (MAJORITY of orgs)  │
 │     │                          │                                              │
 │     └── block events <─────────┴── orderer (Raft, 1 node) ── blocks ──> peers  │
 │  one chaincode server and one Fabric CA per organisation                      │
 └──────────────────────────────────────────────────────────────────────────────┘
        │                                         │
        ▼                                         ▼
  host monitor + canary                  results/ (every transaction, checksummed)
        │
        ▼
  analysis/  ──▶  tables T1–T6 · figures F1–F16
```

| Experiment | What it is |
|---|---|
| **E0** | smoke test and trial: fixes the burst cap, checks memory and disk, freezes the quality thresholds, projects the total time |
| **E1** | the main grid: 2 identities x 2 functions x 5 workloads x 10 topologies x 5 repetitions = 1,000 runs |
| **E2** | connection-setup test: the cost of ML-DSA TLS when every call opens a new connection, as QChain's backend does |
| **E3** | the live block settings (10 transactions, 512 KB) at the live topology, to tie the results to QChain as deployed |
| **E4** | optional offered-load sweep, only if the trial projects the main run under 15 hours |

Differences from QChain's live network, and why, are in [docs/live-differences.md](docs/live-differences.md).

---

## What is measured

| Metric | What it is |
|---|---|
| Execution time, throughput | last confirmation minus first send; successful transactions per second |
| Latency | per transaction, until commit on all peers and at the gateway peer; mean, median, p95, p99, max |
| Stage times | endorse, order, commit, spread to all peers |
| Bytes | per transaction (certificates, signatures, payload) and per block; ledger growth |
| CPU and network | per transaction, per container |
| Failures, blocks | counts by cause; transactions per block and why each block was cut |

The full list (M1 to M12) is in [docs/plan.md](docs/plan.md) §6.

---

## Machines

| | Mac (the only machine) |
|---|---|
| Processor | Apple M1, 4 performance + 4 efficiency cores |
| Memory | 8 GB |
| Runtime | Docker in Colima (Apple Virtualization), arm64, 4 vCPUs, 5 GiB, 60 GiB disk |
| OS | macOS 27.2 |
| Cooling | cooling pad, used for every run |

> The VM and the Windows laptop of the KPI study are not used here. In the paper the live network's host is described only as *a tested environment*.

---

## Technology stack

| Layer | Technology |
|---|---|
| Fabric | the team's post-quantum fork (`qchain-fabric` `e472b4ea`, `qchain-fabric-ca` `e82caf43`, `qchain-fabric-lib-go` `bd30150`), built natively for arm64 with `-tags pqc` |
| Post-quantum | ML-DSA-44 through Go 1.27 `crypto/mldsa`; ML-KEM-768 through liboqs 0.16.0 |
| Chaincode | `qchaincode` 2.0, Node.js 18, as a service, copied verbatim from `qchain-network` |
| Client | Go 1.27, fabric-gateway v1.7.0, grpc v1.68.0 (the backend's versions) |
| Images | Docker in Colima; base images pinned by digest |
| Launchers | Bash |
| Analysis | Python 3 with numpy, scipy and matplotlib |

---

## Repository structure

```
qchain-fabric-performance/
├── README.md                this file
├── LICENSE
├── docker/                  Dockerfiles: fabric (peer, orderer, CA, tools; arm64, -tags pqc), chaincode, client, analysis
│   └── chaincode-lock/      the live chaincode image's lock file (recorded in step 3)
├── network/
│   ├── live/                qchain-network's files, byte for byte (SHA256SUMS)
│   └── gen/qfp_gen.py       one network from the live files: O organisations, P peers, ECDSA or ML-DSA-44, blocks
├── client/                  qfp-client (Go): setup, bursts, per-peer block events, E2, E4, block decoder, canary, tests
├── scripts/
│   ├── run-mac.sh           the Mac launcher: Colima, build, start/resume a session with the KPI's conditions
│   └── qfp.py               the driver: images, networks, runs, Docker statistics, quality, trial report, analysis, publish
├── monitor/monitor-mac.sh   the host monitor (the KPI's)
├── analysis/                run_all.py (tables, figures F2–F16), figstyle.py, selftest.py
├── config/                  thresholds.json, frozen after the trial (written by `qfp.py freeze`)
├── results/                 published sessions (raw/ is local and ignored)
└── docs/                    plan, methodology, data dictionary, provenance, decisions, revert list, differences from live
```

---

## Recent updates

- **16 November 2026: code written.** Network generator (self-checked against the live files), client, driver, launcher, Dockerfiles, analysis, documentation.
- **16 November 2026: planning done.** Literature review (45 papers), plan approved, repository created.

---

## Roadmap

- [x] Literature review
- [x] Research plan approved
- [x] Repository and revert list
- [x] Harness and network generator
- [ ] Installs and arm64 images
- [ ] Trial (E0)
- [ ] Main run (E1, E2, E3, optional E4)
- [ ] Analysis, figures and tables
- [ ] Test machine reverted
- [ ] Paper draft
- [ ] Public release with the paper

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/README.md](docs/README.md) | **start here**: reading order and conventions |
| [docs/plan.md](docs/plan.md) | the research plan: questions, experiments, setup, metrics, statistics, time budget |
| [docs/methodology.md](docs/methodology.md) | what the code does when it measures |
| [docs/data-dictionary.md](docs/data-dictionary.md) | every file and column a session writes |
| [docs/provenance.md](docs/provenance.md) | every copied file and pinned version |
| [docs/decisions-log.md](docs/decisions-log.md) | dated decisions and their reasons |
| [docs/live-differences.md](docs/live-differences.md) | where this network differs from QChain's live network, and by how much |
| [docs/revert-list.md](docs/revert-list.md) | the Mac's baseline and every change made to it |

---

## Conventions and rules

- **Privacy.** Run folders hold only allow-listed facts. Before a folder enters `results/`, every file is scanned for the machine's host name, user name, home path, IP and MAC addresses and serial numbers.
- **Verbatim copies.** The chaincode and the network files are copied byte for byte from `qchain-network`, except the differences listed in [docs/live-differences.md](docs/live-differences.md). A check script compares them.
- **Revert list.** Every change to the test machine is written in [docs/revert-list.md](docs/revert-list.md) before it is made, and reverted at the end.
- **Frozen thresholds.** The quality thresholds are not changed after the trial (E0).
- **Script names.** A script tied to one experiment starts with it (`eN-`); one tied to the Mac ends with `-mac`: `eN-<purpose>-<machine>`.
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

This is an academic research project. The measurements will describe one machine under controlled conditions and the team's Fabric fork of 30 October 2026; they are not a certification of any algorithm or product. The live network's host is a tested environment only. Both networks of the study are built for it and differ from QChain's live network in the ways listed in [docs/live-differences.md](docs/live-differences.md).
