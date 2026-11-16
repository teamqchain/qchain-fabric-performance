# Provenance

Where every copied file and every pinned version comes from.

## Copied files

| In this repository | Source | How |
|---|---|---|
| `network/live/**` (19 files) | `qchain-network` at `c890bd4` (10 Nov 2026) | byte for byte; `network/live/SHA256SUMS`; `scripts/qfp.py selfcheck` compares them with the clone |
| `client/identity.go`, function `newSign` | `qchain-backend` `ledger/fabric.go` at `b5a7ace` | verbatim, between marked lines |
| `client/identity.go`, `dial`, `connectGateway` | the same file, `getContract` | the same calls, options and timeouts; one open connection per run instead of one per call |
| `client/extras.go`, canary | `qchain-kpi` `fabric/client/canary.go` at `f1aca562` (itself the KPI harness's `internal/canary`) | verbatim, between marked lines |
| `client/go.sum` | `qchain-kpi` `fabric/client/go.sum` at `f1aca562` | the same module versions (fabric-gateway v1.7.0, grpc v1.68.0: the backend's) |
| `monitor/monitor-mac.sh` | `qchain-kpi` `scripts/monitor-mac.sh` at `f1aca562` | verbatim except the list of excluded commands |
| `scripts/run-mac.sh`: preflight, paused services, Wi-Fi | `qchain-kpi` `scripts/run-mac.sh` at `f1aca562` | adapted (`siriknowledged` added to the paused services; Colima profile check) |
| `analysis/figstyle.py` | `qchain-kpi` `analysis/figures_common.py` at `f1aca562` | rcParams, number formats, log axes, bar labels, layout check copied; colours changed |
| `network/gen/*` scripts `01`–`05` | the live `generate-crypto-pqc.sh`, `create-channel-pqc.sh`, `registerEnroll.sh`, `deployCC-pqc.sh` | the same commands per organisation and peer; differences in [live-differences.md](live-differences.md) |

## Pinned versions

| Item | Version | Pin |
|---|---|---|
| Fabric fork | `qchain-fabric` `e472b4ea7693811ffa99768cd415d8bd4f6117f4` | `git archive` of the clone at that commit |
| Fabric CA fork | `qchain-fabric-ca` `e82caf43f01642728ef189710a6739f5f77dfd54` | same |
| fabric-lib-go fork | `qchain-fabric-lib-go` `bd30150` | same; the build checks that both forks' vendored `bccsp-pqc` equals it |
| liboqs | 0.16.0 | tarball SHA-256 `162d5b51…01eae` |
| Go | 1.27.4 | `golang:1.27.4-trixie@sha256:f18c3d73…` |
| Runtime base | Debian 13 | `debian:trixie-slim@sha256:a72b4433…` |
| Node.js (chaincode) | 18.20.8 | `node:18.20.8-bookworm-slim@sha256:f9ab18e3…` |
| Chaincode dependencies | the live image's tree (fabric-shim 2.5.8, fabric-contract-api 2.5.8, @grpc/grpc-js 1.14.5, json-stringify-deterministic 1.0.16, ...) | `docker/chaincode-lock/live-npm-ls.txt` (read from the VM on 16 Nov), `pins.txt`; the build fails on any difference |
| Python (analysis) | 3.13; numpy 2.3.4, scipy 1.16.3, matplotlib 3.10.7 | `python:3.13-slim-trixie@sha256:e48f59cd…` |

Every image writes its build information (versions, `ldd`, binary checksums, package lists) to `/opt/qfp/build-info/`, and `results/raw/images.json` records the image IDs; a session refuses to run on images other than its plan's.
