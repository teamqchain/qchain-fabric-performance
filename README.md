<p align="center">
  <img src=".github/assets/qchain_logo.jpeg" width="220" alt="QChain logo" />
</p>

<h1 align="center">qchain-fabric-performance</h1>

<p align="center">
  <b>What does it cost to make every Hyperledger Fabric identity post-quantum?</b><br/>
  A performance study of QChain's Fabric network with ECDSA identities against ML-DSA-44 identities, as workload, peers and organisations grow, in the design of Nasir et al. (2018)
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Fabric-3.1.5%20line%20(fork%20e472b4ea)-2F3134" alt="Fabric" />
  <img src="https://img.shields.io/badge/Identities-ECDSA%20P--256%20vs%20ML--DSA--44-0A66C2" alt="Identities" />
  <img src="https://img.shields.io/badge/Go-1.27-00ADD8" alt="Go" />
  <img src="https://img.shields.io/badge/Machine-MacBook%20Air%20M1%20%C2%B7%20Colima-2F3134" alt="Machine" />
  <img src="https://img.shields.io/badge/Status-planning%20approved%2C%20coding%20next-F2A900" alt="Status" />
  <img src="https://img.shields.io/badge/License-Proprietary-red" alt="License" />
</p>

---

## 📊 Status

| | |
|---|---|
| **Plan** | approved by the project lead on 16 November 2026 ([`docs/plan.md`](docs/plan.md)) |
| **Literature review** | done: 45 papers (kept outside this repository) |
| **Code** | not started (step 2) |
| **Measurements** | not started |
| **Test machine** | one MacBook Air M1; every change to it is recorded in [`docs/revert-list.md`](docs/revert-list.md) before it is made |

> ⚠️ **Private until publication.** Credentials never enter any file; every run folder passes a privacy scan before it is committed.

---

## Overview

QChain issues academic credentials on a Hyperledger Fabric network whose every identity (organisation, peer, orderer, admin, client, node TLS) is signed with **ML-DSA-44**, in a fork of Fabric built by the team. The same fork builds a classical network with ECDSA identities. This study measures the difference between the two.

| | Question |
|---|---|
| **RQ1** | How do execution time, latency and throughput change from 1 to 10,000 transactions, for writes and reads? |
| **RQ2** | How does the overhead change as peers grow from 1 to 8? |
| **RQ3** | How does it change as organisations, and so endorsements, grow from 1 to 8? |
| **RQ4** | Where does the cost come from: bytes, CPU or TLS connection setup? |

---

## Design in one picture

```
 identity {ECDSA, ML-DSA-44}  x  function {issueCredential, getCredential}
          x  T {1, 10, 100, 1,000, 10,000}  x  topology (O orgs, P peers)
                                                 (1,1) (1,2) (1,4) (1,8)
                                                 (2,2) (2,4) (2,8)
                                                 (4,4) (4,8)  (8,8)

   Go client ──gRPC/TLS──> peer0.general ──> endorsing peers (MAJORITY of orgs)
        │                       │
        └── block events <──────┴── orderer (Raft, 1 node) ── blocks ──> every peer
   one chaincode server and one Fabric CA per organisation, all in Colima (arm64)
```

Experiments: **E0** trial, **E1** main grid (1,000 runs), **E2** connection-setup test, **E3** the live block settings, **E4** optional offered-load sweep. Details in [`docs/plan.md`](docs/plan.md); differences from QChain's live network in [`docs/live-differences.md`](docs/live-differences.md).

---

## Repository structure

| Path | Content |
|---|---|
| `docs/` | plan, decisions log, revert list, live differences |
| `docker/` | Dockerfiles for the arm64 images (planned) |
| `network/` | network templates copied from `qchain-network` and the topology generator (planned) |
| `client/` | Go load generator and block decoder (planned) |
| `scripts/` | preflight, build, trial, run, teardown, revert (planned) |
| `monitor/` | host monitor and canary (planned) |
| `analysis/` | statistics, figures and tables (planned) |
| `results/` | summaries and checksums (planned) |

---

## Related repositories

[`qchain-network`](https://github.com/teamqchain/qchain-network) (the live network files), [`qchain-fabric`](https://github.com/teamqchain/qchain-fabric), [`qchain-fabric-ca`](https://github.com/teamqchain/qchain-fabric-ca), [`qchain-fabric-lib-go`](https://github.com/teamqchain/qchain-fabric-lib-go) (the post-quantum forks), [`qchain-kpi`](https://github.com/teamqchain/qchain-kpi) (the algorithm study whose method this one follows), [`qchain-backend`](https://github.com/teamqchain/qchain-backend).

---

## License

Proprietary, see [`LICENSE`](LICENSE).
