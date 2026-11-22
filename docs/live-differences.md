# QChain's live network and this study's networks

The rule (decisions log, 17 Nov): **QChain contributes its architecture; every other setting is the study's own, identical in both arms.** This file lists what is taken from QChain unchanged and every place where the study's networks differ from QChain's live network (`qchain-network` at commit `c890bd4`), with the reason.

## 1. Taken from QChain unchanged

| Item | How it is checked |
|---|---|
| The Fabric fork: `qchain-fabric` `e472b4ea`, `qchain-fabric-ca` `e82caf43`, `qchain-fabric-lib-go` `bd30150`, build tag `pqc` | built from `git archive` of the pinned commits; the build checks the vendored provider against `bd30150` |
| ML-DSA-44 identities for every CA, node, admin and user (the ML-DSA-44 arm) | cryptogen and Fabric CA configurations generated from the live files |
| The chaincode `qchaincode` 2.0 (`QChaincode.js`, `index.js`, `package.json`) and its image's entry point, folder, user and dependency tree | byte-for-byte copies (`network/live/SHA256SUMS`); the image build fails if `npm ls --all` differs from the live image |
| The channel's organisations, policies and capabilities (MAJORITY for endorsement and lifecycle; V3_0, V2_0, V2_5); one Raft orderer | `qfp_gen.py --selfcheck`: the generated `configtx.yaml` for the live topology equals the live file except the two block lines below |
| `core.yaml` and `orderer.yaml` (goleveldb, gateway concurrency limit 500, block gossip off with `orgLeader` on, TLS on) | self-check: byte-identical (the ECDSA arm changes only the provider line, `PQC` to `SW`) |
| The orderer's and the peers' environment variables | self-check: equal to the live compose file |
| A Fabric CA per organisation, bootstrapped and enrolled as on the live network | generated from the live CA configuration and `registerEnroll.sh` |

## 2. Where the study's networks differ

| Item | Live network | This study | Why | Effect on the ECDSA against ML-DSA-44 comparison |
|---|---|---|---|---|
| Hardware | x86 virtual machine without AVX2 | a dedicated x86-64 virtual machine (VMware; Intel Xeon Silver 4210R, 8 vCPUs with AVX2 and AVX-512; 26.4 GiB), study on vCPUs 0 to 6 | the project lead's decision; one machine for the whole study | none (the same machine for both arms); absolute numbers differ |
| Binaries | host-built x86 binaries, no recipe | the same commits and build tag, built natively on the test machine (x86-64) from Dockerfiles | the live binaries have no recipe; a recorded build is reproducible | none (the same Go code) |
| Topology | 2 organisations x 1 peer | 10 topologies from 1 x 1 to 8 x 8, including 2 x 2 | the experiment | intended |
| Blocks | 10 transactions / 512 KB preferred / 99 MB / 2 s | 100 transactions / 16 MB preferred / 99 MB / 2 s | the study's setting, from the literature (decisions log) | none: the same in both arms; ML-DSA-44 blocks are not cut by size earlier than ECDSA blocks |
| Container resources | memory limits: orderer 384 MB, peers 512 MB, chaincode 192 MB, CA 256 MB | no memory limit and no CPU quota; peak memory measured; the study's containers confined to the study's CPUs | the study's setting: memory need is a result (RQ4) | intended |
| Chaincode server | one, shared by the peers | one per organisation | one Node.js server would be the bottleneck at 8 organisations | none at the arms' level |
| Chaincode base image | `node:18.20.8` (Debian 12, x86_64) | `node:18.20.8-bookworm-slim` (Debian 12, x86_64), same folder, user, entry point and dependency tree | the slim variant carries the same Node.js build and fewer packages | none |
| Client | the backend: a new connection and Gateway per call | the backend's library versions and signer; one connection kept open per run | thousands of TLS handshakes would swamp the bursts | E2 measures the handshake separately |
| Configuration mount | `core.yaml` / `orderer.yaml` mounted as single files | the generated config folder mounted at the same `FABRIC_CFG_PATH` | Docker volume sub-paths must be folders | none (the nodes read the same file at the same path) |
| Restart policy | `unless-stopped` | none | a silent restart would hide a crash inside a run | none (a crash is recorded) |
| IPFS, MySQL, backend | present | absent | not on the Fabric transaction path | none |
| Ledger at start | holds data | an empty network each time, plus the untimed setup data | every network starts from the same state | none |
| Classical arm | not on the live host | the same fork with ECDSA P-256 identities and provider `SW` | isolates the identity algorithm | intended |
