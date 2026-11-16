# Revert list

Rule (from the KPI study): **every change to the test machine is written here BEFORE it is made.** At the end of the study every row is reverted and the result is checked against the baseline below.

Test machine: the project lead's MacBook Air (the only machine of this study). The VM and the Windows laptop are not used.

## 1. Baseline (read-only, 16 November 2026, before any change)

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
| Power | on battery (60 %) at the time of the check; every run needs the adapter connected |
| Thermal | no warning level recorded |
| Background services seen running (paused during runs only, resumed afterwards) | suggestd, spotlightknowledged (importer, updater), knowledge-agent, siriknowledged, mediaanalysisd |

## 2. Planned changes (all "not made yet")

| # | Change | When | Revert | Status |
|---|---|---|---|---|
| R1 | `brew install colima docker docker-buildx` (plus the dependencies Homebrew adds: record them from `brew list` before and after). No docker-compose: the driver starts containers with `docker run` | step 3, right before testing | `brew uninstall colima docker docker-buildx`, then `brew autoremove` for the dependencies listed here; check against the baseline formulae | not made yet |
| R2 | Colima VM profile `qfp` (`colima start --profile qfp --vm-type vz --arch aarch64 -c 4 -m 5 -d 60`, through `scripts/run-mac.sh colima-up`); its disk lives under `~/.colima` | step 3 | `colima delete qfp`, remove `~/.colima` | not made yet |
| R3 | Docker CLI config `~/.docker` (created by the Docker CLI / Colima) | step 3 | remove `~/.docker` if it did not exist before (it did not) | not made yet |
| R4 | Docker images, containers, networks and volumes inside the Colima VM (arm64 builds of Fabric, Fabric CA, chaincode, client) | steps 3 to 6 | deleted with the VM (R2); `docker system prune -a --volumes` before that | not made yet |
| R5 | Wi-Fi switched off during runs, on again afterwards (by the launcher, on every exit path, only if it was on) | each run | automatic; verify Wi-Fi is on at the end | not made yet |
| R6 | Background services paused with SIGSTOP during runs and resumed (by the launcher) | each run | automatic; verify none is left stopped | not made yet |
| R7 | `caffeinate` during runs | each run | automatic (ends with the run) | not made yet |
| R8 | Run results and logs written inside this repository and, for large raw files, under the repository's ignored `results/raw/` | steps 5 to 7 | raw files deleted after the analysis; the repository stays | not made yet |
| R9 | Source clones (Fabric, Fabric CA, fabric-lib-go) are only read from `/Applications/Programs for Fun/teamqchain/`; they are copied into Docker build contexts, never modified | steps 3 to 4 | nothing to revert | not made yet |
| R10 | Go 1.27.4 toolchain (darwin-arm64 tarball from go.dev, checksum verified) unpacked in the assistant's session scratchpad (`/private/tmp/claude-501/.../scratchpad/gotool`), with its module cache and build cache in the same folder. Used only to compile-check and unit-test the client while coding. Nothing is installed: no Homebrew package, no file outside that folder, no PATH change | step 2 (16 Nov) | delete the folder `scratchpad/gotool` (a restart clears the scratchpad too) | **made 16 Nov** |

## 2b. Disk clean-up of 16 November 2026 (done with the project lead's approval; not revertable, caches only)

Free space before: 75 GiB. After: 80 GiB. Removed: VS Code `Cache`, `CachedData`, `CachedExtensionVSIXs`; `~/.gradle/wrapper` (Android build files); the pip cache; the Teams cache folder; conda's index cache (`conda clean --all`: nothing else was unused, the 5.1 GB in `miniconda3/pkgs` is in use by the base environment). Kept by decision: `Code-AI/Project - Coffee Plantation`, `Code-AI/AI-ENV`, `Desktop/Masters_Planning`, the Claude app's VM files, OneNote and Teams data.

## 3. Final check (to be filled in at the end)

- [ ] `brew list` equals the baseline formulae and casks
- [ ] colima, docker, docker-buildx absent; `~/.colima`, `~/.docker`, `~/.lima` absent
- [ ] Wi-Fi on, Low Power Mode off, no process left stopped, no `caffeinate`
- [ ] free disk back to about 80 GiB or more
