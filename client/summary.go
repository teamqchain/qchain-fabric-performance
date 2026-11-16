package main

// A run's summary (M1 to M6 of docs/plan.md §6). The analysis recomputes
// everything from tx.csv.gz; the summary is the driver's quick view and the
// trial's input.

import (
	"math"
	"sort"
	"syscall"
	"time"
)

// Dist summarises a set of durations in milliseconds.
type Dist struct {
	N      int     `json:"n"`
	MeanMS float64 `json:"mean_ms"`
	P50MS  float64 `json:"p50_ms"`
	P95MS  float64 `json:"p95_ms"`
	P99MS  float64 `json:"p99_ms"`
	MaxMS  float64 `json:"max_ms"`
}

func dist(ns []int64) Dist {
	if len(ns) == 0 {
		return Dist{}
	}
	s := append([]int64(nil), ns...)
	sort.Slice(s, func(i, j int) bool { return s[i] < s[j] })
	var sum float64
	for _, v := range s {
		sum += float64(v)
	}
	ms := func(v float64) float64 { return math.Round(v/1e3) / 1e3 }
	return Dist{N: len(s), MeanMS: ms(sum / float64(len(s))), P50MS: ms(quantile(s, 0.50)),
		P95MS: ms(quantile(s, 0.95)), P99MS: ms(quantile(s, 0.99)), MaxMS: ms(float64(s[len(s)-1]))}
}

// quantile: linear interpolation between order statistics (numpy's default).
func quantile(sorted []int64, q float64) float64 {
	if len(sorted) == 1 {
		return float64(sorted[0])
	}
	h := q * float64(len(sorted)-1)
	lo := int(math.Floor(h))
	hi := int(math.Ceil(h))
	return float64(sorted[lo]) + (h-float64(lo))*float64(sorted[hi]-sorted[lo])
}

// RunSummary is summary.json.
type RunSummary struct {
	RunID             string         `json:"run_id"`
	Network           string         `json:"network"`
	Identity          string         `json:"identity"`
	ClientAlgorithm   string         `json:"client_algorithm"`
	ClientCertBytes   int            `json:"client_cert_der_bytes"`
	Blocks            string         `json:"blocks"`
	Orgs              int            `json:"orgs"`
	Peers             int            `json:"peers"`
	Endorsements      int            `json:"endorsements"`
	Function          string         `json:"function"`
	T                 int            `json:"t"`
	C                 int            `json:"c"`
	Seed              int64          `json:"seed"`
	T0UnixNS          int64          `json:"t0_unix_ns"`
	OK                int            `json:"ok"`
	Failed            int            `json:"failed"`
	Failures          map[string]int `json:"failures"`
	ExecAllS          float64        `json:"execution_time_all_peers_s"`
	ExecGwS           float64        `json:"execution_time_gateway_s"`
	TputAll           float64        `json:"throughput_all_peers_tps"`
	TputGw            float64        `json:"throughput_gateway_tps"`
	LatAll            Dist           `json:"latency_all_peers"`
	LatGw             Dist           `json:"latency_gateway"`
	Response          Dist           `json:"burst_response_all_peers"`
	Endorse           Dist           `json:"stage_endorse"`
	Order             Dist           `json:"stage_order"`
	Commit            Dist           `json:"stage_commit_gateway"`
	Spread            Dist           `json:"stage_spread_to_all_peers"`
	BlocksUsed        int            `json:"blocks_used"`
	AllPeersDelivered bool           `json:"all_peers_delivered"`
	ClientDoneS       float64        `json:"client_done_s"`
	ClientCPUS        float64        `json:"client_cpu_s"` // user + system CPU of this process
}

func processCPU() float64 {
	var ru syscall.Rusage
	if syscall.Getrusage(syscall.RUSAGE_SELF, &ru) != nil {
		return -1
	}
	return float64(ru.Utime.Nano()+ru.Stime.Nano()) / 1e9
}

// Summarise computes the run's metrics from its transactions.
func Summarise(p RunParams, cfg *NetConfig, s *Signer, recs []TxRec, t0 time.Time, gwDone int64) *RunSummary {
	sum := &RunSummary{RunID: p.RunID, Network: cfg.Network, Identity: cfg.Identity, ClientAlgorithm: s.Algorithm,
		ClientCertBytes: s.CertBytes, Blocks: cfg.Blocks, Orgs: cfg.Orgs, Peers: cfg.PeersTotal,
		Endorsements: cfg.Endorsements, Function: p.Function, T: p.T, C: p.C, Seed: p.Seed,
		T0UnixNS: t0.UnixNano(), Failures: map[string]int{}, ClientDoneS: float64(gwDone) / 1e9}
	var firstSend int64 = math.MaxInt64
	var lastAll, lastGw int64 = -1, -1
	var latAll, latGw, resp, endorse, order, commit, spread []int64
	blocks := map[uint64]bool{}
	for _, r := range recs {
		if r.Send >= 0 && r.Send < firstSend {
			firstSend = r.Send
		}
		if !r.OK {
			sum.Failed++
			sum.Failures[r.ErrStage+":"+r.ErrCode]++
			continue
		}
		sum.OK++
		latGw = append(latGw, r.GwCommit-r.Send)
		if r.GwCommit > lastGw {
			lastGw = r.GwCommit
		}
		if p.Function == "get" {
			continue
		}
		blocks[r.Block] = true
		endorse = append(endorse, r.Endorsed-r.Send)
		order = append(order, r.Submitted-r.Endorsed)
		commit = append(commit, r.GwCommit-r.Submitted)
		if r.AllCommit >= 0 {
			latAll = append(latAll, r.AllCommit-r.Send)
			resp = append(resp, r.AllCommit)
			if r.AllCommit > r.GwCommit {
				spread = append(spread, r.AllCommit-r.GwCommit)
			} else {
				spread = append(spread, 0)
			}
			if r.AllCommit > lastAll {
				lastAll = r.AllCommit
			}
		}
	}
	if p.Function == "get" { // a read is confirmed when its response arrives
		latAll, lastAll = latGw, lastGw
		for _, r := range recs {
			if r.OK {
				resp = append(resp, r.GwCommit)
			}
		}
	}
	if sum.OK > 0 && firstSend != math.MaxInt64 {
		if lastAll > firstSend {
			sum.ExecAllS = float64(lastAll-firstSend) / 1e9
			sum.TputAll = float64(len(latAll)) / sum.ExecAllS
		}
		if lastGw > firstSend {
			sum.ExecGwS = float64(lastGw-firstSend) / 1e9
			sum.TputGw = float64(sum.OK) / sum.ExecGwS
		}
	}
	sum.LatAll, sum.LatGw, sum.Response = dist(latAll), dist(latGw), dist(resp)
	sum.Endorse, sum.Order, sum.Commit, sum.Spread = dist(endorse), dist(order), dist(commit), dist(spread)
	sum.BlocksUsed = len(blocks)
	sum.ClientCPUS = processCPU()
	return sum
}
