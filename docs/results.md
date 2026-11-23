# Results: ECDSA against ML-DSA-44 identities in QChain's Fabric network

Analysis of the main session `main-1`, run on the test machine on 23 November 2026. It answers the four research questions of [the plan](plan.md) in turn. Every number below comes from the published session in [`results/main-1/`](../results/main-1/): tables in `analysis/tables/` (`cells.csv`, `ratios.csv`, `bytes.csv`, `e2.csv`, `e3.csv`, `setup.csv`, `runs.csv`) and figures in `analysis/figures/`. They are regenerated from the session's raw files with `python3 analysis/run_all.py`; `SHA256SUMS` lists every file.

| | |
|---|---|
| Machine | the test machine of [plan §3](plan.md): Intel Xeon Silver 4210R, 8 vCPUs (7 for the study), 26.4 GiB, Ubuntu 22.04 |
| Networks | 30: 20 for E1 (10 topologies × 2 arms, E2 inside the (2,2) networks) and 10 for E3 |
| Runs | 1,000 E1 runs (50 per network), every one clean on its first attempt: no quality flag, no repeat, no error |
| Frozen values | C = 300 transactions in flight; E3's reference rate 346.2 writes/s |
| Statistics | the median of 5 repetitions per cell with a 95 % bootstrap interval; a comparison is ML-DSA-44 / ECDSA of the medians, a difference when its interval excludes 1 |
| Cells and comparisons | 200 cells, 100 comparisons |

## Summary

1. **ML-DSA-44 identities cost QChain about a quarter to two fifths of its write throughput.** For bursts of 100 writes or more, ML-DSA-44 reaches 0.60 to 0.77 of ECDSA's write throughput; at one organisation and one peer it is 325 against 445 writes/s at 10,000 writes (0.73). Every write comparison from 100 writes up is a difference.
2. **The cost grows with the organisations, not with the peers.** At 10,000 writes the throughput ratio stays at 0.72 to 0.73 from 1 to 8 peers in one organisation, but falls from 0.72 (1 organisation) to 0.60 (8 organisations) at 8 peers, because every extra organisation adds an endorsement, and with it an ML-DSA-44 certificate and signature, to each transaction.
3. **Reads cost less.** For reads of 1,000 and 10,000, ML-DSA-44 reaches 0.81 to 0.86 of ECDSA's throughput in every topology. Short read bursts (10 and 100 reads) show no difference.
4. **Small bursts hide the cost.** Bursts of 1 and 10 writes wait for the 2 s block timer in both arms (about 2.0 s), so the identities do not matter there.
5. **Size is the largest effect.** A credential write is 20.6 KB with ECDSA and 39.9 KB with ML-DSA-44 at one endorsement (1.94×), and 24.1 against 72.3 KB at five (3.0×). Certificates make most of the difference: 811 against 5,681 bytes each; signatures are 70 against 2,420 bytes. The ledger grows by 30 to 33 GB per million writes per peer with ECDSA and by 49 to 82 GB with ML-DSA-44, and the orderer sends twice as many bytes per write.
6. **CPU and memory follow.** At 8 peers, a write costs 1.5 to 1.7 times the CPU time with ML-DSA-44 (148.5 against 89.6 ms at 8 organisations), and the whole network's peak memory is 1.18 to 1.29 times as high (4.9 against 3.8 GB at 8 organisations).
7. **A new connection costs 1.4 times as much.** A read on a new connection (with its TLS handshake) takes 6.6 ms with ML-DSA-44 against 4.7 ms with ECDSA; on an open connection 3.7 against 2.4 ms.
8. **Under offered load, ML-DSA-44 saturates at about two thirds of ECDSA's rate.** At (2,2), ECDSA keeps up to about 333 writes/s; ML-DSA-44 tops out at 229 to 242 writes/s and drops sends from 260 writes/s on, where its median latency rises to 1.7 to 1.9 s.

## 1. Data quality

All 1,000 runs of E1 are clean on their first attempt (`runs.csv`: no flag, no repeat, no error), so every cell uses all five repetitions. The host monitor saw no CPU use on the study's CPUs outside the study above the 5 % threshold and no steal; the canary stayed within its 3 % band.

The intervals of reads are wider than those of writes (for example 0.71 to 1.51 for the ratio of 10 reads at one peer), because a read burst is short and one slow repetition moves its median. Read ratios close to 1 are therefore reported as no difference, and small read differences (under about 10 %) should be read with care.

## 2. RQ1: more transactions (one organisation, one peer)

Figures F2 (execution time), F3 (mean latency) and F4 (throughput), each for writes and reads, as line and bar charts; table `cells.csv` at `orgs = 1, peers = 1`.

| Burst (T) | Writes: throughput ECDSA / ML-DSA-44 | Ratio (95 % interval) | Mean latency ECDSA / ML-DSA-44 | Reads: throughput ECDSA / ML-DSA-44 | Ratio (95 % interval) |
|---|---|---|---|---|---|
| 1 | 0.5 / 0.5 /s | 0.99 (0.99–1.00) | 2.02 / 2.04 s | 157 / 88.5 /s | 0.57 (0.46–0.72) |
| 10 | 4.8 / 4.8 /s | 0.99 (0.97–1.00), none | 2.06 / 2.09 s | 446 / 465 /s | 1.04 (0.71–1.51), none |
| 100 | 269 / 164 /s | 0.61 (0.53–0.68) | 362 / 596 ms | 584 / 592 /s | 1.01 (0.62–1.26), none |
| 1,000 | 385 / 286 /s | 0.74 (0.69–0.78) | 757 ms / 1.02 s | 1,081 / 879 /s | 0.81 (0.69–0.99) |
| 10,000 | 445 / 325 /s | 0.73 (0.72–0.75) | 673 / 922 ms | 1,168 / 982 /s | 0.84 (0.81–0.91) |

- **Writes.** Bursts of 1 and 10 fill no block of 100, so the orderer cuts them on its 2 s timer and both arms take about 2 s. From 100 writes, blocks fill at once and the cost of the identity shows: ML-DSA-44 reaches 0.61 to 0.74 of ECDSA's throughput, and 10,000 writes take 30.7 against 22.5 s. The ratio is lowest at 100 writes, a single block.
- **Reads.** A single read takes 11.3 ms with ML-DSA-44 against 6.4 ms with ECDSA; the gateway peer checks the client's larger certificate and signature on every proposal. Bursts of 10 and 100 reads show no difference; from 1,000 reads ML-DSA-44 reaches 0.81 to 0.84 of ECDSA's throughput.

## 3. RQ2: more peers (one organisation)

Figures F5 (execution time, latency and throughput against 1, 2, 4 and 8 peers, at 1,000 and 10,000 transactions, writes and reads) and F6 (the throughput ratio over peers and burst size, writes and reads).

| Peers | Writes, 10,000: ECDSA / ML-DSA-44 | Ratio | Reads, 10,000: ECDSA / ML-DSA-44 | Ratio |
|---|---|---|---|---|
| 1 | 445 / 325 /s | 0.73 (0.72–0.75) | 1,168 / 982 /s | 0.84 (0.81–0.91) |
| 2 | 424 / 306 /s | 0.72 (0.70–0.73) | 1,147 / 953 /s | 0.83 (0.77–0.88) |
| 4 | 348 / 253 /s | 0.73 (0.68–0.78) | 1,173 / 982 /s | 0.84 (0.80–0.99) |
| 8 | 239 / 171 /s | 0.72 (0.65–0.79) | 1,134 / 974 /s | 0.86 (0.80–0.88) |

More peers in one organisation lower both arms' write throughput alike (each peer validates and commits every block on the same machine), so the ratio stays at 0.72 to 0.73. One endorsement is enough in one organisation, so the transaction itself does not grow with the peers. Reads go to the gateway peer only and stay flat for both arms. At 1,000 transactions the pattern is the same (F5).

## 4. RQ3: more organisations (4 and 8 peers)

Figures F7 (execution time, latency and throughput against organisations at 4 and 8 peers, 10,000 transactions, writes and reads) and F8 (the throughput ratio over organisations and peers, writes and reads).

| Organisations (8 peers) | Endorsements | Writes: ECDSA / ML-DSA-44 | Ratio | Mean latency ECDSA / ML-DSA-44 | Reads ratio |
|---|---|---|---|---|---|
| 1 | 1 | 239 / 171 /s | 0.72 (0.65–0.79) | 1.25 / 1.75 s | 0.86 |
| 2 | 2 | 189 / 124 /s | 0.66 (0.59–0.72) | 1.59 / 2.45 s | 0.83 |
| 4 | 3 | 141 / 88.8 /s | 0.63 (0.58–0.70) | 2.14 / 3.42 s | 0.84 |
| 8 | 5 | 76.5 / 45.8 /s | 0.60 (0.56–0.64) | 3.94 / 6.56 s | 0.83 |

Each organisation adds an endorsement under the majority policy, and each endorsement adds a certificate and a signature to the transaction and a signature check to every peer's validation. The ratio therefore falls with the organisations, from 0.72 to 0.60 at 8 peers and from 0.73 to 0.64 at 4 peers; 10,000 writes at 8 organisations take 218 against 131 s. Reads need one endorsement whatever the organisations, and their ratio stays at 0.83 to 0.86.

## 5. RQ4: other costs

### Size and ledger growth

Figures F9 and F10; table `bytes.csv`.

| Endorsements (8 peers) | Write, ECDSA | Write, ML-DSA-44 | Certificates in it | Signatures in it |
|---|---|---|---|---|
| 1 | 20.6 KB | 39.9 KB (1.94×) | 3: 2.4 / 17.0 KB | 2: 141 B / 4.8 KB |
| 2 | 21.5 KB | 48.0 KB (2.23×) | 4: 3.3 / 22.7 KB | 3: 211 B / 7.3 KB |
| 3 | 22.4 KB | 56.1 KB (2.51×) | 5: 4.0 / 28.4 KB | 4: 282 B / 9.7 KB |
| 5 | 24.1 KB | 72.3 KB (3.00×) | 7: 5.6 / 39.7 KB | 6: 423 B / 14.5 KB |

A write carries the client's certificate and one per endorsement, so its size grows with the endorsements, steeply with ML-DSA-44. The call arguments and the read-write set (the credential with its ML-KEM-768 and ML-DSA-44 keys, the same in both arms) are about 18 KB of every write. Each peer's ledger grows by 29.7 to 33.3 GB per million writes with ECDSA and by 49.1 to 81.6 GB with ML-DSA-44 (F10).

### CPU, memory and network

Figures F11 to F13.

- **CPU per write** (8 peers, 10,000 writes): 24.5, 32.8, 47.0 and 89.6 ms with ECDSA against 36.7, 51.8, 74.6 and 148.5 ms with ML-DSA-44 at 1, 2, 4 and 8 organisations (1.50 to 1.66×). The peers that validate and commit (the "other peers") take most of it.
- **Peak memory** (8 peers): the whole network 3.2 to 3.8 GB with ECDSA against 3.8 to 4.9 GB with ML-DSA-44; the gateway peer 391 to 445 MB against 611 to 699 MB.
- **Orderer egress** (one organisation): 20.8, 41.5, 82.9 and 165.6 KB per write with ECDSA against 40.3, 80.5, 160.9 and 321.5 KB with ML-DSA-44 at 1, 2, 4 and 8 peers: it doubles with ML-DSA-44 and with every doubling of the peers.

### Stages of a write

Figure F14, 1,000 writes (median per write, ECDSA against ML-DSA-44): at (1,1) endorse 217 / 263 ms, order 18 / 38 ms, commit 461 / 625 ms; at (8,8) endorse 1,714 / 2,143 ms, order 52 / 166 ms, commit 2,142 / 4,187 ms. The commit stage, where every peer validates the block's signatures, grows most.

### E2: connection set-up

Figure F15; table `e2.csv` (200 reads per repetition, the median of 5).

| | ECDSA | ML-DSA-44 | Ratio |
|---|---|---|---|
| Read on an open connection | 2.4 ms | 3.7 ms | 1.54 |
| Read on a new connection (with the TLS handshake) | 4.7 ms | 6.6 ms | 1.42 |

### E3: latency against offered load

Figure F16; table `e3.csv` ((2,2), 60 s per level, the median of 5 repetitions).

| Offered (writes/s) | ECDSA: achieved, median latency | ML-DSA-44: achieved, median latency, dropped sends |
|---|---|---|
| 35 | 34 /s, 1.13 s | 34 /s, 1.20 s, 0 |
| 87 | 85 /s, 731 ms | 85 /s, 859 ms, 0 |
| 173 | 169 /s, 455 ms | 168 /s, 638 ms, 0 |
| 260 | 252 /s, 401 ms | 229 /s, 1.76 s, 1,248 |
| 312 | 302 /s, 379 ms | 242 /s, 1.72 s, 3,579 |
| 346 | 333 /s, 625 ms | 232 /s, 1.83 s, 6,220 |
| 381 | 347 /s, 1.17 s (1,195 dropped) | 224 /s, 1.92 s, 8,769 |

At low rates both arms wait for the 2 s block timer, so latency falls as the rate rises. ECDSA keeps up to its reference rate; ML-DSA-44 saturates between 173 and 260 writes/s, after which its latency jumps and the client's cap of 480 writes in flight drops sends.

### Network set-up

Table `setup.csv`: bringing a network up took 20 to 76 s with ECDSA and 22 to 64 s with ML-DSA-44, and the untimed set-up (holders, credentials, warm-up) 26 to 55 s; the identity does not change these noticeably.

## 6. What it means for QChain

QChain's live network (two organisations, two peers) corresponds to the (2,2) cells: switching its identities from ECDSA to ML-DSA-44 costs about 31 % of write throughput (0.69 at 10,000 writes), 15 % of read throughput, and roughly doubles the ledger and the orderer's traffic per credential. For a credential registry these are moderate costs; they grow with every organisation that must endorse a credential.
