# Revert list

Rule (from the KPI study): **every change to a machine is written here BEFORE it is made.** At the end of the study every row is reverted and each machine is checked against its baseline. Both machines are reverted together, at the end (project lead, 22 Nov).

| Part | Machine | Its role |
|---|---|---|
| [A](#a-the-test-machine) | **the test machine**: the university virtual machine of plan §3 | every session of the study runs here |
| [B](#b-the-development-laptop) | **the development laptop**: the project lead's MacBook Air | the code is written and checked here and the git bundles for the test machine are made here; Docker ran here in Colima for the first images and the sessions of the earlier plans ([history.md](history.md)) |

---

## A. The test machine

The machine is shared with another project's containers, which are never touched: only objects created by this study are removed (names starting with `qfp`, label `org.qchain.qfp=1`); never `docker system prune`, never `docker compose down`.

### A.1 Baseline (read-only checks, 22 November 2026, before any change)

| Item | State |
|---|---|
| System | Ubuntu 22.04.5 LTS, Linux 6.8.0-138-generic, VMware Virtual Platform; 8 vCPUs (Intel Xeon Silver 4210R, 2.40 GHz); 26.4 GiB memory, 2 GiB swap (unused); disk 251 GB with 81 GB free |
| Docker | 29.8.0 (cgroup v2), buildx 0.37.0; the project lead's account is in the `docker` group; five containers of another project running, 7 images, 4 volumes (the names are kept with the project lead, outside this repository) |
| Background load | the remote-access agent's login-screen process (`anydesk --backend`, user `gdm`) keeps one vCPU busy at all times (about 15 % of the machine when idle); `apt-daily.timer`, `apt-daily-upgrade.timer` and `unattended-upgrades` active |
| Access | remote desktop (AnyDesk) only; no access to the team's GitHub; `sudo` with the project lead's password |

### A.2 Changes (planned and made)

| # | Change | Revert | Status |
|---|---|---|---|
| V1 | The remote-access agent's login-screen process (`anydesk --backend`, user `gdm`) set to nice 19 on every thread (by `scripts/run-linux.sh isolate`); before the slices of V2 and V3 existed it was also pinned to vCPU 7 (`taskset`) | `scripts/run-linux.sh release` (nice 0) and `sudo taskset -a -pc 0-7 <pid>`, or a restart of the process, or a reboot | **reverted 23 Nov**: nice 0 (`release`); the pin of 22 Nov was still in place on all 7 threads and was removed with `sudo taskset -a -pc 0-7`; checked: 7 threads on vCPUs 0-7 |
| V2 | `system.slice` and `user.slice` limited to vCPU 7 (`systemctl set-property --runtime ... AllowedCPUs=7`, by `scripts/run-linux.sh isolate`); `scripts/run-linux.sh build` widens `system.slice` to every vCPU while it builds and narrows it again | `scripts/run-linux.sh release`, which allows every vCPU again and then drops the runtime settings; by hand `sudo systemctl set-property --runtime system.slice AllowedCPUs=0-7`, the same for `user.slice`, then `sudo systemctl revert system.slice user.slice` (an empty `AllowedCPUs=` or a `revert` alone leaves the kernel's CPU list at vCPU 7); or a reboot | **reverted 23 Nov**: `release` left both slices on vCPU 7 (its empty `AllowedCPUs=`, fixed in the script since); set to `0-7` by hand and the runtime settings dropped; checked: both slices and the other project's five containers on vCPUs 0-7 |
| V3 | `qfp.slice` with vCPUs 0 to 6 (`systemctl start qfp.slice` and `set-property --runtime qfp.slice AllowedCPUs=0-6`, by `scripts/run-linux.sh isolate`); the study's containers run under it (`docker run --cgroup-parent qfp.slice`) | `scripts/run-linux.sh release`, or a reboot | **reverted 23 Nov** (`release`: `qfp.slice` stopped) |
| V4 | Automatic package updates stopped (`systemctl stop apt-daily.timer apt-daily-upgrade.timer unattended-upgrades`, by `scripts/run-linux.sh isolate`); they stay stopped between sittings | `scripts/run-linux.sh release`, or `sudo systemctl start apt-daily.timer apt-daily-upgrade.timer unattended-upgrades` (a reboot also starts them again) | **reverted 23 Nov** (`release`; checked: the three units active) |
| V5 | Folder `~/qfp/` (clones made from the git bundles, the build contexts, `results/raw/`, the archive of the published results `~/qfp/<session>-results.tar.gz` with its `.sha256`, and the files of a network's earlier attempt, moved out of its session before the network was run again: `~/qfp/main-1-o8p8-mldsa44-attempt1/`) and the transfer folder `~/Desktop/qfp-vm-transfer/` (the bundles and their `SHA256SUMS`) | `rm -rf ~/qfp ~/Desktop/qfp-vm-transfer`, after the results are published | **reverted 23 Nov** (`~/qfp` and `~/Desktop/qfp-vm-transfer` deleted after the results were on GitHub) |
| V6 | Docker objects of the study: the images `qfp/*` and their build cache, the base images the build pulls by digest (`golang:1.27.4-trixie`, `debian:trixie-slim`, `node:18.20.8-bookworm-slim`, `python:3.13-slim-trixie`), the volumes `qfp-*` (one per network, and `qfp-results`), the network `qfp-net`, the containers `qfp_*` | `python3 -I scripts/qfp.py down --all`; `docker image rm` of the `qfp/*` images and of the four base images (each checked first: no other project's container may use it); `docker builder prune` only after checking that the other project has no build cache | **reverted 23 Nov**: `down --all` (volume `qfp-results`), network `qfp-net`, the four `qfp/*` images; the base images the build pulled by digest were in the build cache only; the build cache holds the other project's 23 entries from September, so the study's 71 entries (all from 22 Nov) were removed one by one by their id, in ten passes, and the September entries were checked unchanged |
| V7 | Leftovers of the qualification: the image `golang:1.27.4-trixie` by tag (about 300 MB) and, in `/tmp`, `cpubench.py`, `soak.py`, `soak2.py`, their `.out` and `.err` files, `gobench.out`, `noise.out`, `top_idle.out` | `docker image rm golang:1.27.4-trixie` (with V6); `ls -la /tmp`, then `rm` only these files | **reverted 23 Nov** (`golang:1.27.4-trixie` removed with V6; the ten `/tmp` files deleted, `soak2.out` with sudo) |
| V8 | Metadata the image builds wrote through `docker buildx build` (default builder): files under `~/.docker/buildx/` (build references naming the build folders under `~/qfp`, builder activity); found on 23 Nov, not recorded before | remove only the files written by the study's builds (from 22 Nov, naming `~/qfp`); files of `~/.docker` older than 22 Nov stay | **reverted 23 Nov** (the 12 references from 22 Nov on, all naming `~/qfp` or `~/qfp-stage1`, deleted; the older files of `~/.docker` kept) |

### A.3 Final check (to be filled in at the end)

- [x] The other project's five containers are still running, unchanged (`docker ps`; 23 Nov: all eight of its containers as at the baseline)
- [x] No `qfp*` container, volume, network or image is left; `docker images` shows the baseline's 7 images and nothing else (23 Nov; 81 GB free, as at the baseline)
- [x] `~/qfp`, `~/Desktop/qfp-vm-transfer`, the `/tmp` files of V7 and the study's files under `~/.docker/buildx/` (V8) are gone (23 Nov)
- [x] `apt-daily.timer`, `apt-daily-upgrade.timer` and `unattended-upgrades` are active again (23 Nov)
- [x] `system.slice` and `user.slice` allow vCPUs 0 to 7 again, `qfp.slice` is gone, and the agent's process runs at nice 0 on every vCPU (23 Nov)

---

## B. The development laptop

### B.1 Baseline (read-only, 16 November 2026, before any change)

| Item | State |
|---|---|
| Machine | MacBookAir10,1, Apple M1 (4 performance + 4 efficiency cores), 8 GB, arm64 |
| macOS | 27.2 (build 26B123) |
| Disk | 228 GiB volume, **75 GiB free** (Data volume 115 GiB used); container free space 80.8 GB |
| Homebrew | 7.0.9. Formulae: ca-certificates cairo fontconfig freetype gettext glib gmp gnupg gnutls gpgme gpgmepp jpeg-turbo libassuan libgcrypt libgpg-error libidn2 libksba libpng libtasn1 libtiff libunistring libusb libx11 libxau libxcb libxdmcp libxext libxrender little-cms2 lz4 lzo nettle npth nspr nss openjpeg p11-kit pcre2 pinentry pixman poppler readline xorgproto xz zstd. Casks: libreoffice, racket |
| Absent (must be absent again at the end) | colima, docker, docker-compose, go, node, npm, gh, cmake, pkg-config, limactl, qemu |
| Absent directories | `~/.colima`, `~/.docker`, `~/.lima` |
| Wi-Fi (en0) | On |
| Low Power Mode | Off |
| Power | on battery (60 %) at the time of the check |
| Thermal | no warning level recorded |
| Background services seen running | suggestd, spotlightknowledged (importer, updater), knowledge-agent, siriknowledged, mediaanalysisd |

### B.2 Changes (planned and made)

| # | Change | When | Revert | Status |
|---|---|---|---|---|
| R1 | `brew install colima docker docker-buildx` (plus the dependencies Homebrew adds: record them from `brew list` before and after). No docker-compose: the driver starts containers with `docker run` | 16 Nov | `brew uninstall colima docker docker-buildx`, then `brew autoremove` for the dependencies listed here; check against the baseline formulae | **reverted 23 Nov** (`brew uninstall colima docker docker-buildx lima`; formulae and casks equal the baseline) |
| R2 | Colima VM profile `qfp` (`colima start --profile qfp --vm-type vz --arch aarch64 -c 4 -m 5 -d 60`); its disk lives under `~/.colima` | 16 Nov | `colima delete qfp`, remove `~/.colima` | **reverted 23 Nov** (`colima delete qfp`, `~/.colima` removed) |
| R3 | Docker CLI config `~/.docker` (created by the Docker CLI / Colima), with `config.json` holding `"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]` so that Docker finds buildx | 16 Nov | remove `~/.docker` (it did not exist before) | **reverted 23 Nov** (`~/.docker` removed) |
| R4 | Docker images, containers, networks and volumes inside the Colima VM (arm64 builds of Fabric, Fabric CA, chaincode, client, analysis) | 16 to 17 Nov | deleted with the VM (R2); `docker system prune -a --volumes` before that | **reverted 23 Nov** (deleted with the VM, R2) |
| R5 | Wi-Fi switched off during sessions, on again afterwards (by the laptop's launcher of the time, on every exit path, only if it was on) | each session, 17 Nov | automatic; verify Wi-Fi is on at the end | used 17 Nov; no sessions run on this machine any more, so nothing is left to revert (checked in B.3) |
| R6 | Background services paused with SIGSTOP during sessions and resumed (by the same launcher) | each session, 17 Nov | automatic; verify none is left stopped | used 17 Nov; nothing is left to revert (checked in B.3) |
| R7 | `caffeinate` during sessions | each session, 16 to 17 Nov | automatic (ends with the session) | used 16 to 17 Nov; nothing is left to revert (checked in B.3) |
| R8 | Results and logs written inside this repository and, for large raw files, under the repository's ignored `results/raw/` | from 16 Nov | raw files deleted; the repository stays | **reverted** (`results/raw/` emptied on 22 Nov and the folder removed on 23 Nov) |
| R9 | Source clones (Fabric, Fabric CA, fabric-lib-go) are only read from `/Applications/Programs for Fun/teamqchain/`; they are copied into Docker build contexts and git bundles, never modified | from 16 Nov | nothing to revert | **in use** (checked clean on 17 and 22 Nov) |
| R10 | Go 1.27.4 toolchain (darwin-arm64 tarball from go.dev, checksum verified) unpacked in the assistant's session scratchpad (`/private/tmp/claude-501/.../scratchpad/gotool`), with its module cache and build cache in the same folder. Used only to compile-check and unit-test the client while coding. Nothing is installed: no Homebrew package, no file outside that folder, no PATH change | 16 Nov | delete the folder `scratchpad/gotool` (a restart clears the scratchpad too) | **reverted** (the scratchpad folder no longer exists, checked 23 Nov) |
| R11 | macOS automatic updates switched off by the project lead (System Settings > General > Software Update > Automatic updates: "Download new updates when available" and "Install macOS updates"); both were **on** at the check of 16 Nov (`AutomaticDownload=1`, `AutomaticallyInstallMacOSUpdates=1`) | 16 Nov | switch both back on | **reverted 23 Nov** (switched back on by the project lead; checked: `AutomaticDownload=1`, `AutomaticallyInstallMacOSUpdates=1`) |
| R12 | Folder `~/Desktop/qfp-vm-transfer/` with git bundles of this repository, the three Fabric forks and `qchain-network`, and their `SHA256SUMS`, for the transfer to the test machine by the remote desktop's file transfer; from the end of the main session also the archive of the published results and its `.sha256`, received from the test machine into this folder (the unpacked results are kept in the repository); also `/tmp/qfp-*` scratch from the checks | 22 Nov | delete the folder and the scratch at the end | **reverted 23 Nov** (folder deleted; its bundles and archive are on GitHub; no `/tmp/qfp-*`) |
| R13 | `~/.ssh/known_hosts`, created by a check of whether GitHub accepts an SSH key from the laptop (`ssh -T git@github.com`, which added GitHub's public host key); the file did not exist before | 23 Nov 13:26 | delete the file | **made and reverted 23 Nov** (deleted at once; GitHub accepts no SSH key from the laptop, so the results were pushed over HTTPS) |

### B.2b Disk clean-up of 16 November 2026 (done with the project lead's approval; not revertable, caches only)

Free space before: 75 GiB. After: 80 GiB. Removed: VS Code `Cache`, `CachedData`, `CachedExtensionVSIXs`; `~/.gradle/wrapper` (Android build files); the pip cache; the Teams cache folder; conda's index cache (`conda clean --all`: nothing else was unused, the 5.1 GB in `miniconda3/pkgs` is in use by the base environment). Kept by decision: `Code-AI/Project - Coffee Plantation`, `Code-AI/AI-ENV`, `Desktop/Masters_Planning`, the Claude app's VM files, OneNote and Teams data.

### B.3 Final check (to be filled in at the end)

- [x] `brew list` equals the baseline formulae and casks (23 Nov)
- [x] colima, docker, docker-buildx, lima absent; `~/.colima`, `~/.docker`, `~/.lima` absent (23 Nov)
- [x] Wi-Fi on, Low Power Mode off, no process left stopped, no `caffeinate` (23 Nov)
- [x] automatic macOS updates back on (R11) (23 Nov)
- [x] `~/Desktop/qfp-vm-transfer` and `/tmp/qfp-*` gone (R12) (23 Nov)
- [x] free disk back to about 80 GiB or more (23 Nov)
