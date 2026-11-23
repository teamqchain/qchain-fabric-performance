# History of the study

How the study went, from the first plan to the current one, in the order things happened. It is written for someone who joins later, a reviewer, or an assistant that has to pick the work up. Every date is 2026; times are UAE local time (UTC+4) unless a run id or a log line is quoted (those are UTC). **This is the only document that describes earlier versions of the plan:** the current design is [plan.md](plan.md), and the *why* of every decision in force is in the [decisions log](decisions-log.md).

---

## At a glance

```
 Nov 15            study opened; context and repositories checked
 Nov 16            reference paper, literature review (45 papers), plan v1.0 approved                   docs/plan.md v1.0 (replaced)
 Nov 16 (day)      repository, harness code, Colima, arm64 images
 Nov 16 19:39      smoke sessions 1 and 2 passed
 Nov 17 01:29      first trial: stopped after 9 minutes, the live memory limit killed a peer
 Nov 17 01:45-03:13  memory tests on (2,2) and (8,8); interim plan (blocks of 50), never run
 Nov 17 (daytime)  one rule for every setting: plan v1.1 approved, code, images and documents updated   docs/plan.md v1.1 (replaced)
 Nov 17 13:45      second trial on the laptop: throttled by heat, (8,8) ML-DSA-44 out of memory
 Nov 22 (day)      a dedicated university virtual machine checked and qualified; first sessions passed
 Nov 22 (evening)  plan v1.2: the study moves to it                                                     docs/plan.md v1.2
 Nov 22 22:29      trial on the new machine: 7 networks, 30 runs, finished 23:11 without a failure
 Nov 23 01:15      C = 300, E3 reference 346.2 writes/s, no split: values frozen
 Nov 23 01:19      main session started: 30 networks, 1,000 runs
 Nov 23 02:13      disk guard (85 %) stopped (8,8) ML-DSA-44 after its 50 runs; raised to 90 %
 Nov 23 09:22      (8,8) ML-DSA-44 run again, alone: 50 runs, disk 86 %; the session is complete
 Nov 23 11:40      analysis, publication, transfer to the laptop; CPU isolation released
 Nov 23 (afternoon)  figures finished, results document written, both machines reverted
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
| Memory guard | above 85 % of the Colima VM at (8,8): stop the CAs during measurement, then drop P = 8 | the trial reports each network's peak; the project lead decides |
| Research question 4 | where the cost comes from: bytes, CPU or TLS setup | what else ML-DSA-44 costs: peak memory, CPU, sizes, ledger, traffic, TLS setup |

- **Found while the code was updated.** (1) Inside E1's (2,2) networks the offered-load sweep would have added about 540,000 writes to one ledger (roughly 45 GB, close to the disk guard of the 60 GiB disk) and distorted that network's ledger growth, so E3 runs in its own (2,2) networks, one per arm and repetition. (2) The fallback agreed on 16 November for a network too large for the disk (two networks, repetitions 1 to 3 and 4 to 5) had not been coded; it is now a split chosen at freeze time. (3) The trial report would have stopped on a wrong key name; a load level with no successful write would have produced an invalid summary; a failed extra test or ledger read-back would have discarded the whole network. All three were fixed. (4) The trial report's memory share counted only the containers; the Colima VM's own use (about 0.6 GB, no swap) is now included. The first trial's (8,8) network, with the gateway peer still capped at 512 MB, already held 3.7 GB in its containers (75 % of the Colima VM's 4.9 GB), so with the Colima VM's own use it was above the 85 % line the report warns at.
- **Found while the documents were checked against the data.** Three statements of the plan were wrong and were corrected: a credential write is 20.0 and 39.4 KB at one endorsement (the plan said 20.6 and 39.9 KB), a further endorsement adds 0.9 and 8.1 KB (it said 1 and 7.8 KB), and at T = 100 a block of 100 fills at once, so the 2 s timer does not hide a difference; only T = 1 and 10 wait for the timer. Single runs at (1,1), T = 100 are noisy and do not yet show how large the difference is: 578 against 334 writes/s for ECDSA and ML-DSA-44 in the first trial (C = 480), 243 against 220 in a smoke run on 17 November (C = 100); the study measures it with five repetitions.
- **Tests before the trial.** The generator's self-check, the client's unit tests (inside the image build), the analysis self-test and a real session that ran a split network, an E3 network, the analysis and `publish` with its privacy scan all passed.

---

## 6. The second trial and the move to a dedicated machine (17 to 22 November)

Until 22 November the study's machine was the project lead's MacBook Air (Apple M1, 8 GB), with Docker in a Colima VM (arm64, 4 vCPUs, 5 GiB, 60 GiB disk), a cooling pad, and macOS kept quiet by the launcher of the time (background services paused, Wi-Fi off, apps closed, automatic updates off).

- **17 November, 13:45 to 15:28: trial-2.** Plan v1.1's trial ran to its end (1 h 43 min) and showed that the design did not fit that machine, for two reasons.
  - **Heat.** The fanless laptop reached thermal level 1 after about 10 minutes and level 2 from about 30 minutes to the end (72 % of the host monitor's samples). The "other CPU" flag pointed at `kernel_task`, macOS's own throttling, not at another program. The throughput of the same run fell with every attempt (ECDSA (8,8) at C = 100: 50.8, 29.9 and 22.5 writes/s; ML-DSA-44 (2,2): 179, 123 and 88), so the rule that repeats a flagged run only added time and heat (the ECDSA (8,8) network took 58 minutes).
  - **Memory.** With no container limits, the kernel killed the gateway peer of the (8,8) ML-DSA-44 network at the lowest C, 100, after 6,200 of 10,000 writes (23.1 writes/s until then): the containers held 4,020 MB and the Colima VM's own processes 593 MB, 94 % of its 4,905 MB. (8,8) ECDSA came through at 88.5 %, (1,8) ML-DSA-44 reached 79 % and (2,2) 38 to 45 %.
  - **What it meant.** No C could be chosen: the heaviest case never finished, and in the fastest case heat confounded the candidates. The projected 10 hours for the main session ignored heat and repeats. The rest of the pipeline worked (E2 and E3, the split proposal, the reports). The ledger grew by 27 to 33 KB per write and peer with ECDSA and 47 to 82 KB with ML-DSA-44.
- **17 November, 17:00: an invalid memory test.** A test of a Go memory target (`GOMEMLIMIT`) on the (8,8) ML-DSA-44 network was started without the launcher and with other programs open; the Colima VM froze (its clock 593 s behind, macOS holding 2.2 GB of swap). A session kind for a proper test was written but never run: the machine changed first, and that session kind was removed.
- **22 November: a second machine.** The project lead obtained a dedicated university virtual machine, separate from QChain's live host (its specification is in [plan.md](plan.md) §3). It is reached by remote desktop only, so every check was a command relayed by the project lead:
  - **Speed.** One vCPU is 1.7 to 1.9 times slower than one M1 core in the same Go benchmarks (ML-DSA-44 sign 565 against 291 µs, verify 169 against 93 µs; ECDSA P-256 sign 46 against 25 µs, verify 97 against 58 µs).
  - **Steadiness.** With every vCPU under load the machine held 6.28 million SHA3-256 hashes per second for 40 minutes, with a spread under 1 % and no steal reported.
  - **Background load.** The remote-access agent's login-screen process kept one vCPU busy at all times (about 15 % of the machine when idle), which cut each of eight workers to 0.785 million hashes per second. With every process outside the study confined to vCPU 7 (systemd slices) and the study on vCPUs 0 to 6, seven workers each ran at the speed of one worker alone (0.92 million), steady over 10 minutes.
  - **Room.** 26.4 GiB of memory (about 3.5 GB in use by the machine itself) and about 81 GB of free disk.
- **22 November: first sessions on the new machine.** With the fewest possible changes to the driver (Linux readings of memory, disk and swap; the CPU slice), the code went over as git bundles and the four images were built natively for x86-64. A smoke session passed (12 runs, no failure; networks up in 20 to 23 s; a read on a new connection 11 to 13 ms). The heaviest network, (8,8) with ML-DSA-44, completed 10,000 writes at C = 100 (44.0 writes/s, median latency 2.3 s, network peak 4,343 MB) and at C = 300 (46.9 writes/s, median 6.4 s, peak 4,774 MB) with no container lost; its gateway peer peaked at 528 and 717 MB. On that network the laptop had managed about 23 writes/s before losing its gateway peer, so the new machine is about twice as fast there: more cores and no throttling outweigh the slower core.
- **22 November: plan v1.2.** The project lead moved the study to the new machine for good. The launcher and the host monitor were rewritten for Linux (CPU isolation, preflight, `tmux`, sleep inhibition), the driver keeps only Linux readings, the images are rebuilt natively, and the trial starts again from the beginning on this machine. The questions, the grid, the network settings, the C rule and the quality rules of plan v1.1 are unchanged. The laptop remains the development machine; both machines are reverted at the end, by the revert list (both reverted on 23 November and the list then removed from the repository).

| | Plan v1.1 | Plan v1.2 |
|---|---|---|
| Test machine | MacBook Air M1, Docker in a Colima VM (arm64, 4 vCPUs, 5 GiB, 60 GiB disk) | a dedicated university virtual machine (x86-64, Intel Xeon Silver 4210R, 8 vCPUs, 26.4 GiB, about 81 GB free) |
| CPUs for the study | the Colima VM's 4 vCPUs, beside macOS | vCPUs 0 to 6; every other process on vCPU 7 |
| Memory ceiling | 5 GiB | 26.4 GiB |
| Images | arm64 | x86-64 |
| Session conditions | apps closed, adapter, cooling pad, automatic macOS updates off; background services paused and Wi-Fi off by the launcher | CPU isolation, automatic package updates stopped, no package manager, the study's CPUs quiet; detached in `tmux` with sleep blocked |
| Flags that repeat a run | other CPU, thermal, battery, Low Power Mode, swap, canary | other CPU on the study's CPUs, steal, CPU isolation, system activity, swap, canary |

---

## 7. The trial, the freeze and the main session (22 to 23 November)

- **22 November, 22:29 to 23:11: trial-1.** The trial of plan v1.2 ran to its end in 42 minutes (7 networks, 30 runs, no failed run, no container lost). Before it, a smoke session had found a fault in the launcher's preflight: the machine's `awk` printed large tick counts in scientific notation, which broke the reading of the study's CPU load. It was fixed (`printf "%.0f"`), the images were rebuilt at the new commit, and a second smoke session passed.
- **What the trial showed.** The heaviest network, (8,8) with ML-DSA-44, peaked at 4,865 MB, 31 % of the machine's memory with the machine's own use included, so no memory warning. At (2,2) the best write throughput was 346.2 writes/s with ECDSA and 236.4 writes/s with ML-DSA-44. The projected time of the main session is 8.3 hours.
- **23 November, 01:15: the freeze, decided by the project lead.**
  - **C = 300.** It is the only candidate within 5 % of the best throughput in both cases: in the fastest case, (2,2) ECDSA, C = 300 gave 346.2 writes/s against 309.2 at 200 and 197.9 at 100. In the heaviest case, (8,8) ML-DSA-44, 200 and 300 were within 5 % of the best (45.8 and 46.6 writes/s). C is a setting of this harness and this machine, not a value from the literature; the same C is used for both arms.
  - **E3's reference rate: 346.2 writes/s**, the best ECDSA write throughput at (2,2).
  - **No split.** The report proposed running (8,8) ML-DSA-44 as two networks, because its projected ledger (42 GB) would bring Docker's disk to 80.8 %, above the 80 % line for a proposal. The project lead chose the cleaner comparison and kept the disk guard at 85 %: the ledger's bytes per write is measured, so the projection would have to be about 27 % too low to reach the guard. Every network runs whole.
- **23 November, 01:19: the main session.** It started after a clean preflight: 30 networks, 1,000 runs.
- **02:13: the disk guard stopped (8,8) ML-DSA-44.** The session's second network finished its 50 runs; at the disk check after the last run Docker's disk stood at 86 %, above the guard of 85 %, so the driver stopped the network before its ledger read-back, removed its containers and volumes, and went on with the other networks. No other network reached the guard.
  - **Why.** The trial report's projection of the network's size was close: 42 GB projected, between about 41 and 45 GB written by the disk readings. Its percentage was the wrong scale: the report divided by the disk's full size, while the guard reads `df`'s use, which leaves out the space the file system reserves for the system (about 5 % of this disk) and rounds up. On the guard's scale the projection was about 85 %, at the guard, not 80.8 %.
  - **What the project lead decided.** The guard was raised to 90 % (`DISK_GUARD_PCT` in `scripts/qfp.py`) and the network stays whole: it runs again, alone, after the other networks, with the same plan, seeds and images (`resume main-1`), under the commit that carries the new value. The guard only decides when a network stops, and it stopped no other network, so the other 29 networks are the same under either value. Before the rerun the first attempt's files are moved out of the session, so they are not published; the driver's log and the session's state keep the record of the failure.
- **09:22 to 09:54: the rerun.** The commit with the new guard reached the test machine as a bundle (fast-forward, no rebuild); the first attempt's files were moved out of the session to `~/qfp/main-1-o8p8-mldsa44-attempt1/` and its leftover folder in the results volume was removed; `resume main-1` then ran the network alone: 50 runs, no error, Docker's disk at 86 % after the ledger read-back. The session is complete: 30 networks, 1,000 runs, every run clean on its first attempt (no flag, no repeat, no error).
- **Repeatability.** The rerun repeated the first attempt's 50 runs with the same seeds. For bursts of 100 or more, its write throughput was 0.99 of the first attempt's at the median (single runs 0.78 to 1.05) and its read throughput 1.08 (0.83 to 1.26). Between two networks of the same configuration, reads can therefore differ by about 8 %, more than the bootstrap intervals show, since those cover only the repetitions inside one network.
- **Analysis, publication and transfer.** `analyse` (11:40, on the test machine) found 1,000 runs, 200 cells, 100 comparisons and 30 networks, and exited with code 3: the layout check found the tick labels of F9 overlapping. `publish` copied 3,933 files (311 MB) after the privacy scan. The folder went to the development laptop as one archive (289 MB) with its sha256, which matched; every file matched `SHA256SUMS`, and a second scan on the laptop found nothing identifying.
- **Figures finished on the laptop** (plan §14, step 6), with the same analysis image built for arm64, after the project lead's review. Every figure of F2 to F8 now holds one function, writes or reads, never both; F2 to F5 and F7 are each drawn as a line chart and as a bar chart; F5 and F7 gained the reads, F7 the execution time, and the heatmaps F6 and F8 were split by function: 73 figures in all. F9, F11 and F14 show the two arms side by side, named once per setting; value axes carry their units; times under a second are shown in milliseconds; values have thousands separators; the labels of the line charts sit on a light backing; the line charts against peers and organisations zoom to their data (their bar charts start at zero); a logarithmic axis spanning little gets ticks at 1, 2 and 5; the layout check also covers labelled minor ticks. Run on the published raw data, the laptop's tables were byte-identical to the test machine's (all nine), so the published `analysis/` folder was replaced by the laptop's and `SHA256SUMS` written again.
- **CPU isolation released.** `release` stopped `qfp.slice`, set the remote-access agent back to nice 0 and started the automatic updates, but left `system.slice` and `user.slice` on vCPU 7: an empty `AllowedCPUs=` makes systemd stop managing the CPU list without resetting it. Both slices were set to every vCPU by hand and their runtime settings dropped; the remote-access agent, still pinned to vCPU 7 since 22 November, was unpinned. `release` now sets every vCPU first.
- **Results.** [results.md](results.md) answers RQ1 to RQ4 from the session. The whole published session (4,031 files, 310 MB) is in the repository, committed in four parts because GitHub's HTTPS endpoint dropped one upload of that size.
- **Both machines reverted (23 November).** The test machine: the study's folders, its Docker volume, network and images, its 71 build-cache entries (removed one by one; the other project's 23 entries stayed), the build references it left in `~/.docker` and the qualification files; the final check matched the baseline (the other project's eight containers, seven images and four volumes, 81 GB free). The development laptop: Colima, Docker, buildx and Lima uninstalled, their folders deleted, automatic macOS updates back on. The revert list's final state is commit `ab479dd`; it then left the repository. Only the paper draft is left.

---

## Where the data of the earlier plans went

The sessions `smoke-1`, `smoke-2`, `trial-1` and the memory tests (`diag-1`) existed only in the git-ignored `results/raw/` of the laptop and were never published; they were deleted on 17 November after the numbers above were checked against them. `trial-2` and the laptop's build logs, and the first sessions on the new machine (`s1`, `fit-1`), were deleted on 22 November after the numbers in section 6 were recorded. Nothing from them enters the results. Session names start again on the test machine: its `trial-1` is not the trial of 17 November. The first attempt of (8,8) ML-DSA-44 on 23 November was moved out of the session and deleted with the test machine's revert; its record stays in the published `driver.log` and `state.json`.
