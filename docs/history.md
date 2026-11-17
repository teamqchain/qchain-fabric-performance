# History of the plan

How the study's design reached its current version, with every earlier value and the reason it changed. **Nothing in this file is in force:** the current design is [plan.md](plan.md), its reasons are in [decisions-log.md](decisions-log.md). Newest last.

---

## 15 November 2026: the study starts

The project lead opens the study: the performance of QChain's Fabric network whose identities are all ML-DSA-44, as a separate journal paper from the KPI paper, in a new repository.

## 16 November 2026: plan v1 (proposed) and plan v1.0 (approved)

**Plan v1** (proposed in the planning chat, not approved): the network's identities from cryptogen only (no Fabric CAs), QChain's live channel settings, a main session of about 12 to 16 h. Replaced the same day by plan v1.0 after the project lead's answers (Fabric CAs as on the live network; larger blocks if the live ones would be a bottleneck).

**Plan v1.0** (approved 16 Nov). The parts of it that later changed:

| Item | Plan v1.0 | Changed to (17 Nov) |
|---|---|---|
| Rule for the settings | QChain's live settings, except where the literature showed a bottleneck | QChain gives only its architecture; every setting is the study's own |
| Blocks | 100 transactions / 16 MB / 99 MB / 2 s in E1, E2, E4; QChain's 10 transactions / 512 KB in E3 | 100 / 16 MB / 99 MB / 2 s in every network |
| Container memory | QChain's live limits: peer 512 MB, orderer 384 MB, chaincode 192 MB, CA 256 MB | no limits; peak memory measured |
| E3 | live-settings check: two extra (2,2) networks with QChain's blocks, 100 runs, "to tie the results to QChain as deployed" | dropped (not one of the research questions) |
| E4 | offered-load sweep, only if the trial projected E1 + E2 + E3 under 15 h, inside E1's (2,2) networks | renamed E3; always runs; in its own (2,2) networks |
| C | the smallest of 200, 300, 400, 480 within 5 % of the best throughput | the smallest of 100, 200, 300 within 5 % of the best in both the heaviest and the fastest case, among the values with no container down |
| Time | main session at most 2 to 3 days; budget 16 h (12 to 26 h) for 22 networks; T capped at 5,000 if the trial projected more than 36 h | no deadline; sittings allowed; the trial reports the projection and the project lead decides any reduction |
| Memory guard | if (8,8) passed 85 % of the VM's memory: stop the CAs during measurement, then drop P = 8 | the trial reports each network's peak; the project lead decides |
| Research question 4 | "Where does the cost come from: bytes, CPU or TLS connection setup?" | "What else do ML-DSA-44 identities cost: peak memory, CPU, sizes, ledger, traffic, TLS setup?" |

Also on 16 Nov: a proposal to change the figure colours to grey and purple was declined (blue and vermillion kept); the Mac had 75 GiB free (not the 90 GB seen on 15 Nov), so the Colima disk became 60 GiB instead of 80.

## 16 November 2026: images and smoke sessions

- The first chaincode image had two dependency versions different from the live image (`@grpc/grpc-js` 1.14.7 against 1.14.5, `json-stringify-deterministic` 1.0.18 against 1.0.16); they were pinned and the build now fails on any difference from the live tree.
- **smoke-1** and **smoke-2** passed: (1,1), both arms, writes and reads at T = 1, 10, 100, 12 runs each, no failure. A write was 20.6 KB with ECDSA and 39.9 KB with ML-DSA-44 at one endorsement (certificates 2.4 against 17.0 KB); networks came up in about 15 s, the setup took about 25 s.
- The driver's memory figure first read the whole cgroup usage, file cache included (a peer showed about 506 MB of 512 MB); it now reads usage minus the reclaimable file cache, as `docker stats` does.

## 17 November 2026: the first trial fails

**trial-1** (plan v1.0, C candidates 200 to 480) stopped within minutes. At T = 10,000 writes with C = 200 in the (2,2) ML-DSA-44 network, the gateway peer `peer0.general` was killed by the kernel at QChain's 512 MB peer limit (OOMKilled, exit code 137); every later run failed because Docker's DNS no longer resolved the dead peer. The ECDSA arm survived the same burst.

Tests that followed (session `diag-1`, 10,000 writes, blocks of 100 unless stated):

| Network | Memory limit | C | Result |
|---|---|---|---|
| (2,2) ML-DSA-44 | 512 MB | 200 | gateway peer killed |
| (2,2) ML-DSA-44 | 512 MB | 100 | completed, 163 writes/s, median latency 603 ms |
| (2,2) ML-DSA-44 | 512 MB | 50 | completed, 22 writes/s: with C below the block size the 2 s timer cuts every block |
| (2,2) ECDSA | 512 MB | 200 | completed, 392 writes/s, peak 339 MB |
| (2,2) ML-DSA-44 | 1 GiB | 200 | completed, 155 writes/s, peak 483 MB |
| (8,8) ML-DSA-44 | 512 MB | 100 | gateway peer killed after about 200 writes |
| (8,8) ML-DSA-44 | 512 MB | 75 | completed (3,000 writes), 16 writes/s, median 4.8 s, peak 339 MB |
| (8,8) ML-DSA-44 | 512 MB | 50 | completed, 12.8 writes/s |
| (8,8) ECDSA | 512 MB | 100 / 200 | completed, 45 / 42 writes/s (saturated), peak about 270 MB |

So the ML-DSA-44 gateway peer's memory under a burst grows with the endorsements, and the limit was reached at a lower C with more organisations; ECDSA never reached it. Two harness fixes came from these runs: the client's setup now waits up to 60 s for gossip discovery ("no combination of peers can be derived"), and the driver records every container's state and last log lines after each run.

## 17 November 2026: an interim plan, never run

To keep QChain's 512 MB limit, the study blocks were lowered to 50 transactions (so that C below 100 still filled blocks) and the trial was to test C = 60, 75, 90, 100. A margin test at (8,8) ML-DSA-44 with blocks of 50 completed 10,000 writes at C = 75 (18.9 writes/s, median 3.9 s, peak 291 MB) and C = 90 (19.1 writes/s, median 4.6 s, peak 300 MB). This plan was replaced before any trial ran with it.

## 17 November 2026: plan v1.1 (current)

The project lead set one rule for every setting: **QChain contributes its architecture** (the fork, the identity type, the chaincode, the endorsement policy, the Raft orderer, the node configuration files, the Fabric CAs); **every other setting is the study's own**, identical in both arms, from the literature or from the study's needs. Mixing QChain's deployed values with literature values would have been inconsistent. Consequences (the right-hand column of the table above): blocks of 100 everywhere, no container memory limits, the live-settings check dropped, the offered-load sweep renamed E3 and always run, C from 100, 200, 300, the time and memory guards turned into reports for the project lead.

Found while the code was updated: inside E1's (2,2) networks the offered-load sweep would have added about 540,000 writes to one ledger (about 44 GB with two peers and the orderer, near the 85 % disk guard of the 60 GiB disk) and would have distorted the (2,2) ledger growth (M9). E3 therefore runs in its own (2,2) networks, one per arm and repetition (10 networks). The agreed fallback for a network too large for the disk (two networks, repetitions 1 to 3 and 4 to 5) was added to the code as a split chosen at freeze time.

**Sessions of the earlier plans:** `smoke-1`, `smoke-2`, `trial-1` and `diag-1` exist only in the git-ignored `results/raw/` and are never published; they are deleted after the final trial. Their findings are recorded above.
