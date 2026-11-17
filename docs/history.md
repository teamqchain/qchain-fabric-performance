# History of the study

How the study went, from the first plan to the current one, in the order things happened. It is written for someone who joins later, a reviewer, or an assistant that has to pick the work up. Every date is 2026; times are UAE local time (UTC+4) unless a run id or a log line is quoted (those are UTC). **This is the only document that describes earlier versions of the plan:** the current design is [plan.md](plan.md), and the *why* of every decision in force is in the [decisions log](decisions-log.md).

---

## At a glance

```
 Nov 15            study opened; context and repositories checked
 Nov 16            reference paper, literature review (45 papers), plan v1.0 approved       docs/plan.md v1.0 (replaced)
 Nov 16 (day)      repository, harness code, Colima, arm64 images
 Nov 16 19:39      smoke sessions 1 and 2 passed
 Nov 17 01:29      first trial: stopped after 9 minutes, the live memory limit killed a peer
 Nov 17 01:45-03:13  memory tests on (2,2) and (8,8); interim plan (blocks of 50), never run
 Nov 17 (daytime)  one rule for every setting: plan v1.1 approved, code, images and documents updated   docs/plan.md v1.1
```

---

## 1. Planning (15 to 16 November)

- **15 November.** The project lead opened the study: the performance of QChain's Fabric network whose identities are all ML-DSA-44 (live since 7 November), as a second journal paper, separate from the KPI paper, in a repository of its own. The organisation's repositories were checked clean and level with GitHub.
- **16 November: the design.** The project lead supplied the reference paper, Nasir, Qasse, Abu Talib and Bou Nassif (2018), which compared Fabric v0.6 and v1.0 on one server with three metrics (execution time, latency, throughput) for a single peer, for 1 to 20 peers and for one against two organisations. Decided: the same Fabric fork with ECDSA against ML-DSA-44 identities (no version comparison, no other algorithms), the project lead's Mac only, a time limit of 2 to 3 days for the main run, Docker in Colima, every change to the Mac written into a revert list first, and all code written before any unattended run.
- **16 November: literature.** A literature review of 45 papers (the closest works use hybrid or application-level post-quantum signatures, or one fixed small network) found the gap the study fills: nobody varies peers or organisations (endorsements) with pure ML-DSA identities including node TLS, nobody repeats the reference paper's design, and nothing exists for arm64.
- **16 November: plan v1 and plan v1.0.** A first proposal (identities from cryptogen only, QChain's live channel settings) was replaced the same day by plan v1.0 after the project lead's answers: Fabric CAs exactly as on the live network, and larger blocks if the live ones would be a bottleneck. **Plan v1.0 (approved):** 2 identities × 2 functions × 5 workloads × 10 topologies × 5 repetitions = 1,000 runs (the grid has not changed since); blocks of 100 transactions and 16 MB, except a check "E3" of two extra (2,2) networks with QChain's own 10 transactions and 512 KB; QChain's live container memory limits (peer 512 MB, orderer 384 MB, chaincode 192 MB, Fabric CA 256 MB); the burst cap C chosen by the trial from 200, 300, 400, 480; an optional offered-load sweep "E4" only if the trial projected the main session under 15 hours; a time budget of 16 hours (range 12 to 26), with T capped at 5,000 if the trial projected more than 36; research question 4 asked where the cost comes from (bytes, CPU or TLS setup).

---

## 2. Building the harness and the first sessions (16 November)

- **Repository and revert list.** The Mac had 75 GiB free, not the 90 GB seen on 15 November, so the Colima disk was set to 60 GiB (not 80); a disk clean-up freed 5 GiB (caches only).
- **Code.** A network generator (self-checked against the live files), the Go load generator, the driver, the Mac launcher, the Dockerfiles and the analysis were written and unit-tested. A proposal to recolour the figures was declined: ECDSA blue, ML-DSA-44 vermillion.
- **Installs and images.** Colima, Docker and buildx were installed (revert list R1 to R3), and the four images were built natively for arm64. Found while building: the vendored-code check had to skip tests and mocks; a name clash in the analysis; and the driver's memory figure first included the file cache (a peer showed 506 MB of 512 MB), so it now reports usage minus the reclaimable cache, as `docker stats` does.
- **Chaincode dependencies.** One read-only command on the live host gave the chaincode image's entry point and dependency tree. The first build differed in two packages (`@grpc/grpc-js` 1.14.7 against 1.14.5, `json-stringify-deterministic` 1.0.18 against 1.0.16); they were pinned, and the build now fails on any difference from the live tree.
- **19:39 and 19:59: smoke sessions 1 and 2.** (1,1), both arms, writes and reads at T = 1, 10 and 100: 12 runs per session, no failure. Networks came up in 14 to 15 s and the setup took 24 to 28 s. A credential write (`issueCredential`, 1,411 of them per arm) was 20.0 KB with ECDSA and 39.4 KB with ML-DSA-44 at one endorsement; the certificates were 2.4 and 17.0 KB, and each further endorsement adds a certificate and a signature (0.9 KB with ECDSA, 8.1 KB with ML-DSA-44).
- **20:42: updates.** Automatic macOS updates were switched off (revert list R11); macOS 27.2.1, already downloaded, was installed first.

---

## 3. The first trial (17 November, from 01:29)

- **01:29: trial-1.** Plan v1.0's trial (7 networks, C from 200 to 480) stopped after 9 minutes. The two (1,1) networks finished. In the ML-DSA-44 networks (2,2), (1,8) and (8,8) and in the network with QChain's own block settings, the gateway peer died during the 10,000-write bursts (in the first, at C = 200, all 10,000 requests failed) and later calls failed because Docker's DNS no longer resolved it. The ECDSA (2,2) network failed in its setup ("no combination of peers can be derived", a race while the peers find each other). In the small runs the ML-DSA-44 gateway peer already held 457 MB against 173 MB with ECDSA (QChain's limit is 512 MB).
- **Cause, from direct tests (the same night).** The kernel killed the gateway peer `peer0.general` for exceeding QChain's 512 MB peer limit (exit code 137, killed for memory):

| Network | Memory limit | C | Result (10,000 writes unless stated) |
|---|---|---|---|
| (2,2) ML-DSA-44 | 512 MB | 200 | gateway peer killed |
| (2,2) ML-DSA-44 | 512 MB | 100 | completed, 163 writes/s, median latency 603 ms |
| (2,2) ML-DSA-44 | 512 MB | 50 | completed, 22 writes/s (C below the block size of 100: every block waits for the 2 s timer) |
| (2,2) ECDSA | 512 MB | 200 | completed, 392 writes/s, median 564 ms, peak 339 MB |
| (2,2) ML-DSA-44 | 1 GiB | 200 | completed, 155 writes/s, median 1,335 ms, peak 483 MB |
| (8,8) ML-DSA-44 | 512 MB | 100 | gateway peer killed after 200 writes |
| (8,8) ML-DSA-44 | 512 MB | 75 | 3,000 writes completed, 16.1 writes/s, median 4.76 s, peak 339 MB |
| (8,8) ML-DSA-44 | 512 MB | 50 | 3,000 writes completed, 12.8 writes/s, median 3.97 s, peak 323 MB |
| (8,8) ECDSA | 512 MB | 100 | 3,000 writes completed, 44.9 writes/s, median 2.27 s, peak 265 MB |
| (8,8) ECDSA | 512 MB | 200 | 3,000 writes completed, 42.4 writes/s, median 4.62 s, peak 272 MB |

  Blocks were 100 transactions in all of these. The ML-DSA-44 gateway peer's memory under a burst grows with the number of endorsements (the kill came between C = 100 and 200 at (2,2), between 75 and 100 at (8,8)); ECDSA never came close. At (8,8) the throughput barely changed between C = 75 and 100 (writes are limited by the CPU), so a higher C only adds waiting time.
- **Two harness fixes.** The client's setup now waits up to 60 s for the peers to find each other ("no combination of peers can be derived", seen once in the ECDSA (2,2) network), and the driver records every container's state and last log lines after each run, so that a killed container is visible.

---

## 4. An interim plan (17 November, 02:43 to 03:13)

- **To keep QChain's 512 MB limit,** the project lead chose to lower the study's blocks to 50 transactions (so that a C below 100 still fills a block) and to let the trial test C = 60, 75, 90 and 100. A margin test at (8,8) ML-DSA-44 with blocks of 50 completed 10,000 writes at C = 75 (18.9 writes/s, median 3.93 s, peak 291 MB) and at C = 90 (19.1 writes/s, median 4.61 s, peak 300 MB): the same throughput, so a higher C only lengthens the latency. The trial was rewritten (8 networks, 26 runs) and committed at 03:13. **It was never run:** the plan changed first.

---

## 5. Plan v1.1 (17 November, daytime)

- **The project lead's observation.** Some settings came from QChain's deployment (the 2 s timer, the 99 MB block limit, the 512 MB memory limit) and others from the literature or the trial (the block size, C). A reviewer would ask why; either every setting comes from QChain, or every setting comes from the study and only the architecture, above all the ML-DSA-44 identities, comes from QChain. The project lead chose the second.
- **The rule that followed.** QChain contributes its architecture: the Fabric fork, the identity type (the one variable), the chaincode, the endorsement policy, one Raft orderer, the node configuration files (goleveldb, gateway limit 500, block gossip off, taken unchanged and to be stated in the paper) and a Fabric CA per organisation. Every other setting is the study's own, identical in both arms.
- **Answers to the open questions.** Memory: no container limits, the peak is measured and reported. The check with QChain's own settings ("E3") was dropped: it answers whether QChain's deployment copes, which is not one of the four research questions. The connection-setup test (E2) stays. The offered-load sweep ("E4") became E3 and always runs; the time and memory guards became reports for the project lead; there is no deadline, and the main session may run in sittings.

| | Plan v1.0 | Plan v1.1 |
|---|---|---|
| Source of the settings | QChain's live settings, except where a bottleneck was expected | QChain: the architecture only; the study: every setting |
| Blocks | 100 / 16 MB / 99 MB / 2 s; QChain's 10 / 512 KB in the check E3 | 100 / 16 MB / 99 MB / 2 s in every network |
| Container memory | QChain's live limits (peer 512 MB, orderer 384 MB, chaincode 192 MB, CA 256 MB) | none; peak memory measured |
| Experiments | E0 trial, E1 grid, E2 connection setup, E3 live-settings check, E4 optional sweep | E0 trial, E1 grid, E2 connection setup, E3 offered-load sweep (always) |
| C | the smallest of 200, 300, 400, 480 within 5 % of the best throughput | the smallest of 100, 200, 300 within 5 % of the best in the heaviest and the fastest case, among the values with no container down |
| Time | at most 2 to 3 days; budget 16 h; T capped at 5,000 above 36 h | no deadline; sittings allowed; the trial reports, the project lead decides |
| Memory guard | above 85 % of the VM at (8,8): stop the CAs during measurement, then drop P = 8 | the trial reports each network's peak; the project lead decides |
| Research question 4 | where the cost comes from: bytes, CPU or TLS setup | what else ML-DSA-44 costs: peak memory, CPU, sizes, ledger, traffic, TLS setup |

- **Found while the code was updated.** (1) Inside E1's (2,2) networks the offered-load sweep would have added about 540,000 writes to one ledger (roughly 45 GB, close to the disk guard of the 60 GiB disk) and distorted that network's ledger growth, so E3 runs in its own (2,2) networks, one per arm and repetition. (2) The fallback agreed on 16 November for a network too large for the disk (two networks, repetitions 1 to 3 and 4 to 5) had not been coded; it is now a split chosen at freeze time. (3) The trial report would have stopped on a wrong key name; a load level with no successful write would have produced an invalid summary; a failed extra test or ledger read-back would have discarded the whole network. All three were fixed. (4) The trial report's memory share counted only the containers; the VM's own use (about 0.6 GB, no swap) is now included. The first trial's (8,8) network, with the gateway peer still capped at 512 MB, already held 3.7 GB in its containers (75 % of the VM's 4.9 GB), so with the VM's own use it was above the 85 % line the report warns at.
- **Found while the documents were checked against the data.** Three statements of the plan were wrong and were corrected: a credential write is 20.0 and 39.4 KB at one endorsement (the plan said 20.6 and 39.9 KB), a further endorsement adds 0.9 and 8.1 KB (it said 1 and 7.8 KB), and at T = 100 a block of 100 fills at once, so the 2 s timer does not hide a difference; only T = 1 and 10 wait for the timer. Single runs at (1,1), T = 100 are noisy and do not yet show how large the difference is: 578 against 334 writes/s for ECDSA and ML-DSA-44 in the first trial (C = 480), 243 against 220 in a smoke run on 17 November (C = 100); the study measures it with five repetitions.
- **Tests before the trial.** The generator's self-check, the client's unit tests (inside the image build), the analysis self-test and a real session that ran a split network, an E3 network, the analysis and `publish` with its privacy scan all passed.

---

## Where the data of the earlier plans went

The sessions `smoke-1`, `smoke-2`, `trial-1` and the memory tests (`diag-1`) existed only in the git-ignored `results/raw/` of the Mac and were never published; they were deleted on 17 November after the numbers above were checked against them. Nothing from them enters the results.
