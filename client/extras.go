package main

// E2 (connection setup), E4 (offered load), the peers' heights and the canary.

import (
	"fmt"
	"math/rand"
	"sort"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"golang.org/x/crypto/sha3"
)

// ConnTest is E2: n times, the backend's pattern for one read (a new gRPC
// connection, a new Gateway, one getCredential: the TLS handshake with the
// peer's certificate chain happens on this first call), then n reads on one
// open connection. Every call is timed.
func ConnTest(cfg *NetConfig, s *Signer, pool []string, n int, seed int64, out string) (map[string]Dist, error) {
	rng := rand.New(rand.NewSource(seed))
	p := gatewayPeer(cfg)
	var rows [][]string
	var fresh, open []int64
	for i := 0; i < n; i++ {
		id := pool[rng.Intn(len(pool))]
		t0 := time.Now()
		sess, err := openSession(s, p)
		if err != nil {
			return nil, err
		}
		t1 := time.Now()
		_, err = sess.GW.GetNetwork(cfg.Channel).GetContract(cfg.Chaincode).EvaluateTransaction("getCredential", id)
		t2 := time.Now()
		sess.Close()
		if err != nil {
			return nil, fmt.Errorf("fresh read %d: %w", i, err)
		}
		fresh = append(fresh, t2.Sub(t0).Nanoseconds())
		rows = append(rows, []string{"fresh", itoa(i), i64(t1.Sub(t0).Nanoseconds()), i64(t2.Sub(t1).Nanoseconds()), i64(t2.Sub(t0).Nanoseconds())})
	}
	sess, err := openSession(s, p)
	if err != nil {
		return nil, err
	}
	defer sess.Close()
	contract := sess.GW.GetNetwork(cfg.Channel).GetContract(cfg.Chaincode)
	if _, err := contract.EvaluateTransaction("getCredential", pool[0]); err != nil { // handshake, untimed
		return nil, err
	}
	for i := 0; i < n; i++ {
		id := pool[rng.Intn(len(pool))]
		t0 := time.Now()
		if _, err := contract.EvaluateTransaction("getCredential", id); err != nil {
			return nil, fmt.Errorf("open read %d: %w", i, err)
		}
		d := time.Since(t0).Nanoseconds()
		open = append(open, d)
		rows = append(rows, []string{"open", itoa(i), "0", i64(d), i64(d)})
	}
	if err := writeCSVGz(out+"/conn.csv.gz", []string{"mode", "i", "connect_ns", "call_ns", "total_ns"}, rows); err != nil {
		return nil, err
	}
	res := map[string]Dist{"fresh_connection": dist(fresh), "open_connection": dist(open)}
	return res, writeJSON(out+"/summary.json", map[string]any{"identity": cfg.Identity, "network": cfg.Network, "n": n, "result": res})
}

// LoadTest is E4: writes sent open-loop at a fixed rate for a duration (a
// send every 1/rate s, whether or not earlier ones have finished), at most
// maxInFlight at once (sends beyond it are counted as dropped, not queued).
func LoadTest(cfg *NetConfig, s *Signer, rate float64, dur time.Duration, holders, maxInFlight int, seed int64, out string) (map[string]any, error) {
	gw, err := openSession(s, gatewayPeer(cfg))
	if err != nil {
		return nil, err
	}
	defer gw.Close()
	contract := gw.GW.GetNetwork(cfg.Channel).GetContract(cfg.Chaincode)
	wl, err := NewWorkload(seed)
	if err != nil {
		return nil, err
	}
	n := int(rate * dur.Seconds())
	recs := make([]TxRec, n)
	var inflight, dropped int64
	var wg sync.WaitGroup
	interval := time.Duration(float64(time.Second) / rate)
	t0 := time.Now()
	since := func() int64 { return time.Since(t0).Nanoseconds() }
	for i := 0; i < n; i++ {
		if d := time.Until(t0.Add(time.Duration(i) * interval)); d > 0 {
			time.Sleep(d)
		}
		recs[i] = TxRec{Idx: i, Send: -1, Endorsed: -1, Submitted: -1, GwCommit: -1, AllCommit: -1, Code: -1}
		if atomic.LoadInt64(&inflight) >= int64(maxInFlight) {
			atomic.AddInt64(&dropped, 1)
			recs[i].ErrStage, recs[i].ErrCode = "client", "dropped"
			continue
		}
		atomic.AddInt64(&inflight, 1)
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			defer atomic.AddInt64(&inflight, -1)
			r := &recs[i]
			args := wl.IssueArgs(i, holders, time.Now())
			r.Send = since()
			prop, err := contract.NewProposal("issueCredential", client.WithArguments(args...))
			if err != nil {
				r.ErrStage, r.ErrCode = "proposal", "error"
				return
			}
			r.TxID = prop.TransactionID()
			tx, err := prop.Endorse()
			if err != nil {
				r.ErrStage, r.ErrCode = classify("endorse", err)
				return
			}
			r.Endorsed = since()
			commit, err := tx.Submit()
			if err != nil {
				r.ErrStage, r.ErrCode = classify("submit", err)
				return
			}
			r.Submitted = since()
			st, err := commit.Status()
			if err != nil {
				r.ErrStage, r.ErrCode = classify("commit_status", err)
				return
			}
			r.GwCommit = since()
			r.Block, r.Code = st.BlockNumber, int32(st.Code)
			r.OK = st.Successful
			if !r.OK {
				r.ErrStage, r.ErrCode = "validation", st.Code.String()
			}
		}(i)
	}
	wg.Wait()
	var lat []int64
	var last int64
	ok := 0
	var rows [][]string
	for _, r := range recs {
		rows = append(rows, []string{itoa(r.Idx), r.TxID, i64(r.Send), i64(r.Endorsed), i64(r.Submitted), i64(r.GwCommit),
			u64(r.Block), itoa(int(r.Code)), strconv.FormatBool(r.OK), r.ErrStage, r.ErrCode})
		if r.OK {
			ok++
			lat = append(lat, r.GwCommit-r.Send)
			if r.GwCommit > last {
				last = r.GwCommit
			}
		}
	}
	if err := writeCSVGz(out+"/tx.csv.gz", []string{"idx", "txid", "send_ns", "endorsed_ns", "submitted_ns",
		"gw_commit_ns", "block", "code", "ok", "err_stage", "err_code"}, rows); err != nil {
		return nil, err
	}
	res := map[string]any{"identity": cfg.Identity, "network": cfg.Network, "offered_tps": rate, "duration_s": dur.Seconds(),
		"sent": n - int(dropped), "dropped": dropped, "ok": ok, "t0_unix_ns": t0.UnixNano(),
		"achieved_tps": float64(ok) / (float64(last) / 1e9), "latency_gateway": dist(lat)}
	return res, writeJSON(out+"/summary.json", res)
}

// Heights asks every peer for its height.
func Heights(cfg *NetConfig, s *Signer) (map[string]uint64, error) {
	out := map[string]uint64{}
	for _, p := range cfg.Peers {
		sess, err := openSession(s, p)
		if err != nil {
			return nil, err
		}
		h, err := Height(sess, cfg.Channel)
		sess.Close()
		if err != nil {
			return nil, fmt.Errorf("%s: %w", p.Name, err)
		}
		out[p.Name] = h
	}
	return out, nil
}

// ---- canary: copied from qchain-kpi fabric/client/canary.go (f1aca562),
// itself a verbatim copy of the KPI harness's internal/canary: SHA3-256 of a
// 64-byte message, 15 windows of 100 ms, the median rate.

// Canary is the result of one canary run.
type Canary struct {
	WindowMS   int       `json:"window_ms"`
	Windows    int       `json:"windows"`
	RatesPerS  []float64 `json:"rates_per_s"`   // SHA3-256 hashes per second in each window
	MedianRate float64   `json:"median_rate_per_s"`
	Digest     string    `json:"digest_check"` // proves the work was done
}

// message is a fixed 64-byte input (the size QChain signs: a 64-char hex string).
var message = []byte("4f1c8a2b9d3e6071c5a4f2b8e9d1c3a7b6e5f4d3c2b1a09f8e7d6c5b4a392817")

// RunCanary executes windows x window of SHA3-256 hashing and reports the median
// rate. The default canary is 15 windows of 100 ms (1.5 s).
func RunCanary(windows int, window time.Duration) Canary {
	if windows < 1 {
		windows = 15
	}
	if window <= 0 {
		window = 100 * time.Millisecond
	}
	rates := make([]float64, 0, windows)
	var acc [32]byte
	in := make([]byte, len(message))
	copy(in, message)
	for w := 0; w < windows; w++ {
		n := 0
		start := time.Now()
		deadline := start.Add(window)
		for {
			// 64 hashes between clock reads keep timer overhead negligible.
			for j := 0; j < 64; j++ {
				acc = sha3.Sum256(in)
				in[0] ^= acc[0]
			}
			n += 64
			if !time.Now().Before(deadline) {
				break
			}
		}
		el := time.Since(start).Seconds()
		rates = append(rates, float64(n)/el)
	}
	sorted := append([]float64(nil), rates...)
	sort.Float64s(sorted)
	med := sorted[len(sorted)/2]
	if len(sorted)%2 == 0 {
		med = (sorted[len(sorted)/2-1] + sorted[len(sorted)/2]) / 2
	}
	const hexdigits = "0123456789abcdef"
	d := make([]byte, 8)
	for i := 0; i < 4; i++ {
		d[2*i] = hexdigits[acc[i]>>4]
		d[2*i+1] = hexdigits[acc[i]&15]
	}
	return Canary{WindowMS: int(window / time.Millisecond), Windows: windows, RatesPerS: rates, MedianRate: med, Digest: string(d)}
}

// ---- end of the copy
