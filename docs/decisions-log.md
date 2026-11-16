# Decisions log

The decisions about the study (scope, machine, design, run rules), with their reasons. Each row is a decision of the project lead unless it says otherwise. Newest last.

| Date | Decision | Why |
|---|---|---|
| 15 Nov | The study measures the performance of QChain's Fabric network whose identities are all ML-DSA-44 (item A.5 of the Week 12 deck). New repository, separate journal paper from the KPI paper. | The KPI paper covers the old network only. |
| 15 Nov | Same approach and rules as `qchain-kpi`; methodology and aim differ. | Proven way of working. |
| 16 Nov | The design repeats Nasir, Qasse, Abu Talib and Bou Nassif (2018), "Performance Analysis of Hyperledger Fabric Platforms". | Reference paper from Prof. Qassim Nasir; Dr. Manar Abu Talib is a co-author. |
| 16 Nov | Compare the same Fabric fork with ECDSA identities against ML-DSA-44 identities. No version comparison, no other PQC algorithms. | Isolates the identity algorithm; the KPI study covered algorithms. |
| 16 Nov | Machine: this Mac only. No VM, no Obeid's laptop. Nothing is asked of Obeid. | The live network keeps running; time is short. |
| 16 Nov | Main run at most 2 to 3 days. | Deadline. |
| 16 Nov | Functions: `issueCredential` (write) and `getCredential` (read). | QChain's two key operations; same pair as the reference paper's invoke and query. |
| 16 Nov | Workload T in {1, 10, 100, 1,000, 10,000}; topologies (O,P) in (1,1) (1,2) (1,4) (1,8) (2,2) (2,4) (2,8) (4,4) (4,8) (8,8); O in {1, 2, 4, 8}. | Mac capacity (8 GB, 8 cores); MAJORITY policy gives 1, 2, 3, 5 endorsements. |
| 16 Nov | Block settings: 100 transactions / 16 MB preferred / 99 MB absolute / 2 s in E1, E2, E4; the live 10 / 512 KB / 2 s in E3. | Thakkar et al. (2018) and Ouadrassi et al. (2026): larger blocks avoid a block-size bottleneck at saturation; at 8 organisations a 512 KB limit would cut post-quantum blocks by size and inflate the measured overhead. E3 keeps the link to the live network. |
| 16 Nov | Per-organisation Fabric CA exactly as on the live VM; `issuer1@general` enrolled from GeneralCA with `role=issuer:ecert`; nodes and admins from cryptogen. | The client certificate is stored twice in every transaction, so its exact shape changes transaction size. |
| 16 Nov | One chaincode server per organisation. | One Node.js server would be an artificial bottleneck at 8 organisations. |
| 16 Nov | Persistent client connections in the grid; connection cost measured separately (E2). | Thousands of TLS handshakes would swamp the bursts. |
| 16 Nov | E4 (offered-load sweep) only if the trial projects E1 + E2 + E3 under 15 h. | Time. |
| 16 Nov | Mac conditions as in the KPI study (services paused, Wi-Fi off during runs, apps closed, `caffeinate`, adapter connected); the cooling pad exists and is used for every run. | Noise control. |
| 16 Nov | Docker and Colima with Dockerfiles; images built natively for arm64, never emulated; installs only right before testing, each written to the revert list first. | KPI rule. |
| 16 Nov | The chaincode and the cryptogen/network files are copied verbatim from `qchain-network`, except the differences listed in `docs/live-differences.md`. | Faithfulness to QChain. |
| 16 Nov | Repository name `qchain-fabric-performance` (private). Literature review folder `Performance Analysis of Hyperledger Fabric/Literature Review`. | |
| 16 Nov | Code everything first, then run unattended. | Short time; the KPI loop of coding and running was slow. |
| 16 Nov | Observation of the assistant, noted at step 1: the Mac has 75 GiB free, not the 90 GB seen on 15 Nov, so the Colima disk is 60 GiB (not 80). The largest network, (8,8) with ML-DSA, is estimated at about 40 GB, so the trial measures real ledger growth; if the projection passes 80 % of the VM disk, (8,8) is run as two networks back to back (repetitions 1 to 3, then 4 to 5). | Disk. |
| 16 Nov | Proposal, step 2: figure colours ECDSA dark grey `#555555` and ML-DSA-44 reddish purple `#CC79A7`, replacing the plan's blue and vermillion. | The project lead's figure rules reserve `#0072B2` (Mac), `#009E73` (laptop) and `#D55E00` (VM) for the machines in every QChain chart. |
| 16 Nov | Proposal, step 2: no docker-compose; the driver starts every container with `docker run` and the image builds use `docker buildx` (revert list R1 changed accordingly). | One fewer install; the per-topology containers are generated, not hand-written. |
| 16 Nov | Proposal, step 2: the configuration folder is mounted at `FABRIC_CFG_PATH` instead of `core.yaml` / `orderer.yaml` alone. | Docker volume sub-paths must be folders (no host mounts in Colima); the nodes read the same file at the same path. |
| 16 Nov | Proposal, step 2: one image (`qfp/fabric`) carries peer, orderer, Fabric CA and the tools, on Debian 13 with a shell and openssl. | The live images are host-built and have no recipe; one image keeps the binaries identical across roles. |
| 16 Nov | Proposal, step 2: a Go 1.27.4 toolchain in the session scratchpad (revert list R10) for compile checks and unit tests of the client while coding. | Nothing installed on the Mac; the images build the client again with their own Go. |
| 16 Nov | Proposal, step 2: the client records commit on every peer through per-peer filtered block events, and its own CPU through `getrusage`. | The working group's network-wide latency; the client container is short-lived, so its CPU cannot be read from Docker after it exits. |
