# Live network versus this study's network

Everything not listed here is copied byte for byte from `qchain-network` (commit `c890bd4`): the chaincode (`QChaincode.js`, `index.js`, `package.json`), `crypto-config.yaml`, `configtx.yaml`, `core.yaml`, `orderer.yaml`, the Fabric CA configurations and the enrolment scripts. A check script compares the study's files with the live ones and lists every difference.

| Item | Live VM | This study | Why | Size of the difference |
|---|---|---|---|---|
| Hardware | x86 VM without AVX2 | MacBook Air M1, arm64, Colima | Project lead's decision | Large for absolute numbers; none for the ECDSA against ML-DSA comparison (same machine for both) |
| Binaries | Host-built x86 binaries, no recipe | Same commits (`e472b4ea`, `e82caf43`, `bd30150`) and build tag `pqc`, built natively for arm64 | x86 cannot run natively; emulation would distort timings | Small: the same Go code runs; glibc and OpenSSL versions differ and are not used on the transaction path |
| Topology | 2 organisations x 1 peer | 10 topologies from 1 x 1 to 8 x 8, including 2 x 2 | This is the experiment | Intended |
| Blocks | 10 transactions / 512 KB / 2 s | 100 transactions / 16 MB / 2 s (E3 keeps the live values) | Avoids a block-size bottleneck and a size-cut distortion at 8 organisations | Medium; measured by E3 |
| Chaincode server | One shared | One per organisation | One Node.js server would be the bottleneck at 8 organisations | Small at 2 x 2 |
| Client | Backend: new connection and Gateway per call | Same library versions, connections kept open | Thousands of TLS handshakes would swamp the bursts | Medium for single calls; measured by E2 |
| Restart policy | `unless-stopped` | none | A silent restart would hide a crash inside a run | None (a crash is recorded as a failure) |
| IPFS, MySQL, backend | Present | Absent | Not on the Fabric transaction path | None |
| Ledger at start | Holds data | Empty network each time, plus untimed setup data | Every topology starts from the same state | Small |
| Classical arm | Not on the VM (the earlier network ran Fabric 2.5.15) | Same fork, ECDSA identities, provider `SW` | Isolates the identity algorithm | Intended |
