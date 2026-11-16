# Methodology (as implemented)

This file describes what the code does when it measures. It is written from the code; the research plan is [plan.md](plan.md) and the reasons for each choice are in [decisions-log.md](decisions-log.md). Any difference between this file and the code is a bug in this file.

## 1. The two arms

Both arms run the **same binaries**: Fabric `e472b4ea` and Fabric CA `e82caf43` built with the build tag `pqc` (fabric-lib-go `bd30150` vendored), natively for arm64 (`docker/Dockerfile.fabric`). Only two things differ:

| | ECDSA arm | ML-DSA-44 arm |
|---|---|---|
| Every identity (organisation CAs, TLS CAs, orderer, peers, admins, users) | cryptogen `PublicKeyAlgorithm: ecdsa` (P-256) | `mldsa44` (as live) |
| Application users from the Fabric CA (`issuer1`, `verifier1`) | `csr.keyrequest.algo: ecdsa`, provider `SW` | `mldsa44`, provider `PQC` (as live) |
| Crypto provider of peers, orderer and CLI (`BCCSP.Default`) | `SW` | `PQC` (as live) |
| Client signer | fabric-gateway's ECDSA signer | the backend's ML-DSA signer (`newSign`, verbatim) |

Everything else is identical: the channel (V3_0 / V2_0 / V2_5, MAJORITY endorsement and lifecycle), the chaincode, the payloads, the client, the topology and the machine. The Fabric CA servers' own TLS is ECDSA in both arms, as on the live network. TLS key exchange is whatever Go 1.27 negotiates in both arms; only the certificates' signature algorithm differs.

## 2. Networks

`network/gen/qfp_gen.py` writes one network from the verbatim copies in `network/live/` (`qchain-network` at `c890bd4`):

- **Organisations:** O = 1 (General), 2 (Government, General: the live pair), 4 or 8 (plus `org3` ... `org8`, `orgN.uae.com`). P peers in total, P/O per organisation, `peer0` ... `peer7`. Ports follow the live port map for Government and General.
- **Endorsements per write** (MAJORITY of O organisations): 1, 2, 3, 5.
- **Blocks:** E1, E2, E4: 100 transactions / 16 MB preferred / 99 MB absolute / 2 s. E3: the live 10 / 512 KB / 99 MB / 2 s.
- **Containers** (1 + P + 2·O): one Raft orderer, P peers, one chaincode server and one Fabric CA per organisation, each with the live environment, memory limit, user and read-only root file system.
- **Self-check** (`qfp_gen.py --selfcheck`, also run by `scripts/qfp.py selfcheck`): for the live case (2 × 2, ML-DSA-44, live blocks) the generated `crypto-config.yaml`, `configtx.yaml` and CA configurations equal the live files (comments aside), `core.yaml` and `orderer.yaml` are byte-identical, and the orderer's and both peers' environments equal the live compose file's.

Bring-up order (`scripts/qfp.py bring_up`): files into a Docker volume → cryptogen and CA bootstrap (`01-crypto.sh`) → CAs → enrolment (`03-enroll.sh`) → orderer and peers → channel (`02-channel.sh`) → chaincode packages and install (`04-install.sh`) → chaincode servers → approve and commit (`05-commit.sh`). Every step is timed (M12).

## 3. Workload

**Untimed setup per network** (`qfp-client setup`): 100 holders registered with real ML-KEM-768 and ML-DSA-44 public keys, 1,000 credentials issued for the read pool, then 200 writes and 200 reads as warm-up.

**Writes** are `issueCredential` with the backend's argument shapes: holder `H-0001` ... `H-0100` in turn, 10 SHA3-256 field hashes, a CIDv0, the SHA3-256 credential hash and a real ML-DSA-44 signature and public key (64 signed variants per process, made before t0). `issuedAt` is the send time (UAE offset). The content is identical in both arms. Every write creates a new key (`CRED-<txID>`), so writes never conflict.

**Reads** are `getCredential` of a credential drawn (seeded) from the read pool. A read is checked: the returned record's ID must be the requested one.

## 4. One run

One run is one fresh `qfp-client run` process in its own container on the network's Docker network:

1. Untimed: the connection to `peer0.general` (the gateway, as for the backend), the workload, the ledger height, a block-event stream from every peer starting at that height, one warm-up call.
2. **t0**: T requests are released at once; at most **C** are in flight (C from the trial, frozen). Writes: proposal → endorse → submit → commit status, each step timed; reads: proposal → evaluate.
3. Writes: the client waits until every peer has delivered the highest block of the run (at most 120 s), then joins each transaction with the time its block reached each peer.

Files: `tx.csv.gz` (every transaction), `arrivals.csv.gz` (every block on every peer), `summary.json`.

## 5. Metrics

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
| M10 | CPU and memory | per container, from the Docker Engine API: cumulative CPU before and after the run, memory sampled every 5 s (peak; usage minus the reclaimable file cache, as `docker stats` shows it); the client's own CPU from `getrusage` |
| M11 | Network | per container: bytes sent and received during the run (Docker API) |
| M12 | Setup times | every bring-up step |

## 6. Order, quality and repeats

- **Order:** the 11 topology/block pairs in a seeded random order; the two arms of a pair back to back in random order; the 50 runs of a network shuffled.
- **Host monitor** (`monitor/monitor-mac.sh`, the KPI's): every 5 s, other CPU, thermal pressure, power source, Low Power Mode.
- **Flags of a run:** mean other CPU above 5 %; thermal pressure above nominal; battery; Low Power Mode; macOS swap growth above 64 MB; canary drift (below). A flagged run is repeated at the end of its network, up to 3 attempts; the headline attempt is the first clean one.
- **Canary:** the KPI's SHA3-256 canary at each network's start and every 60 min; the session reference is the median of its first three. A canary more than 3 % below the reference flags the runs since the previous canary.
- **Guards:** a network stops if the Colima disk passes 85 %; the trial decides the memory and disk fallbacks (plan §10).

## 7. Statistics

`analysis/run_all.py`: per cell, the median of the repetitions' headline values with a 95 % percentile bootstrap interval (10,000 resamples); per comparison, ML-DSA-44 / ECDSA of the medians with a bootstrap interval from resampling each arm independently; a comparison is a difference when its interval excludes 1. `analysis/selftest.py` checks these numbers on a synthetic session.
