// qfp-client: the load generator and ledger reader of qchain-fabric-performance.
//
// One fresh process per run (the KPI study's rule). It runs in a container on
// the network's Docker network, with the network's files at /qfp/net (the
// generated folder: client.json and crypto-material/) and the results volume
// at /out. Subcommands:
//
//	setup    holders, read pool, warm-up                   (untimed)
//	run      one burst of T transactions (E0, E1)          -> <out>/tx.csv.gz, arrivals.csv.gz, summary.json
//	conn     the connection-setup test (E2)                -> <out>/conn.csv.gz, summary.json
//	load     the offered-load sweep, one rate (E3)         -> <out>/tx.csv.gz, summary.json
//	blocks   every block's bytes, read from the gateway    -> <out>/blocks.csv.gz, txbytes.csv.gz
//	heights  every peer's ledger height (JSON on stdout)
//	canary   the KPI canary (JSON on stdout)
//	version  build information
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"runtime"
	"strings"
	"time"
)

var buildCommit = "unknown"

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: qfp-client setup|run|conn|load|blocks|heights|canary|version [flags]")
		os.Exit(2)
	}
	cmd, args := os.Args[1], os.Args[2:]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	netCfg := fs.String("net", "/qfp/net/client.json", "the network's client.json")
	out := fs.String("out", "", "output folder")
	fn := fs.String("fn", "issue", "issue | get")
	t := fs.Int("t", 1, "transactions in the burst")
	c := fs.Int("c", 200, "maximum transactions in flight")
	holders := fs.Int("holders", 100, "registered holders")
	poolN := fs.Int("pool", 1000, "credentials in the read pool")
	warm := fs.Int("warm", 200, "warm-up writes and reads")
	pool := fs.String("poolfile", "", "credential ids for reads (one per line)")
	seed := fs.Int64("seed", 1, "seed of the run's workload")
	runID := fs.String("id", "", "run id")
	n := fs.Int("n", 200, "E2: connections (and open-connection reads)")
	rate := fs.Float64("rate", 10, "E3: offered transactions per second")
	dur := fs.Duration("dur", 60*time.Second, "E3: duration")
	maxIn := fs.Int("maxinflight", 480, "E3: maximum in flight (below the gateway's concurrency limit of 500)")
	from := fs.Uint64("from", 0, "blocks: first block")
	skipHolders := fs.Bool("skip-holders", false, "setup: holders already registered")
	fs.Parse(args)

	if cmd == "version" {
		fmt.Printf("qfp-client %s %s %s/%s\n", buildCommit, runtime.Version(), runtime.GOOS, runtime.GOARCH)
		return
	}
	if cmd == "canary" {
		emit(RunCanary(15, 100*time.Millisecond))
		return
	}
	cfg, err := loadNetConfig(*netCfg)
	check(err)
	signer, err := loadSigner(*cfg.mspdirOverride(), cfg.MSPID)
	check(err)
	if *out != "" {
		check(os.MkdirAll(*out, 0o755))
	}
	switch cmd {
	case "setup":
		need(*pool != "", "-poolfile")
		check(Setup(cfg, signer, SetupParams{Holders: *holders, Pool: *poolN, Warm: *warm, C: *c, Seed: *seed,
			PoolFile: *pool, SkipHolds: *skipHolders}))
	case "run":
		need(*out != "" && *runID != "", "-out and -id")
		var ids []string
		if *fn == "get" {
			ids, err = readLines(*pool)
			check(err)
		} else if *fn != "issue" {
			check(fmt.Errorf("-fn must be issue or get"))
		}
		sum, err := RunBurst(cfg, signer, RunParams{Function: *fn, T: *t, C: *c, Holders: *holders, Seed: *seed,
			Pool: ids, RunID: *runID, Out: *out})
		if sum != nil {
			emit(map[string]any{"ok": sum.OK, "failed": sum.Failed, "exec_s": sum.ExecAllS, "tps": sum.TputAll,
				"lat_p50_ms": sum.LatAll.P50MS, "all_peers_delivered": sum.AllPeersDelivered})
		}
		check(err)
	case "conn":
		need(*out != "", "-out")
		ids, err := readLines(*pool)
		check(err)
		res, err := ConnTest(cfg, signer, ids, *n, *seed, *out)
		check(err)
		emit(res)
	case "load":
		need(*out != "", "-out")
		res, err := LoadTest(cfg, signer, *rate, *dur, *holders, *maxIn, *seed, *out)
		check(err)
		emit(res)
	case "blocks":
		need(*out != "", "-out")
		sess, err := openSession(signer, gatewayPeer(cfg))
		check(err)
		nb, err := DumpBlocks(sess, cfg.Channel, *from, *out)
		sess.Close()
		check(err)
		emit(map[string]any{"blocks": nb})
	case "heights":
		h, err := Heights(cfg, signer)
		check(err)
		emit(h)
	default:
		check(fmt.Errorf("unknown subcommand %q", cmd))
	}
}

// mspdirOverride lets QFP_MSPDIR point at another identity (tests only).
func (c *NetConfig) mspdirOverride() *string {
	if v := os.Getenv("QFP_MSPDIR"); v != "" {
		return &v
	}
	return &c.MSPDir
}

func readLines(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []string
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		if l := strings.TrimSpace(sc.Text()); l != "" {
			out = append(out, l)
		}
	}
	return out, sc.Err()
}

func emit(v any) {
	b, _ := json.Marshal(v)
	fmt.Println(string(b))
}

func need(ok bool, what string) {
	if !ok {
		check(fmt.Errorf("missing %s", what))
	}
}

func check(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, "qfp-client:", err)
		os.Exit(1)
	}
}
