package main

// One run (E1, E3): a burst of T transactions of one function, all released
// at t0 as in the reference paper ("requested simultaneously"), with at most C
// in flight at once (the Gateway refuses more than 500 concurrent requests;
// C is calibrated in the trial, E0, and then frozen). Every transaction is
// timed in stages; the run's summary follows the paper's definitions:
//
//   execution time  last confirmation minus first send (Pongnumkul et al.)
//   throughput      successful transactions / execution time
//   latency         per transaction: commit on all peers minus send
//
// Writes go through the Gateway's four steps (proposal, endorse, submit,
// commit status), taken one by one so that each is timed; reads are a
// proposal evaluated on the gateway peer.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math/rand"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"google.golang.org/grpc/status"
)

// TxRec is one transaction of a run. Times are ns since t0; -1 = not reached.
type TxRec struct {
	Idx        int
	Arg        string // holder (writes) or credential id (reads)
	TxID       string
	Send       int64
	Endorsed   int64
	Submitted  int64
	GwCommit   int64 // commit status from the gateway peer (writes), response (reads)
	AllCommit  int64 // block delivered by every peer (writes)
	PeersSeen  int
	Block      uint64
	Code       int32 // validation code, 0 = VALID; -1 = none
	OK         bool
	ErrStage   string
	ErrCode    string
	ResultSize int
}

// RunParams are one run's settings.
type RunParams struct {
	Function string // issue | get
	T        int
	C        int
	Holders  int
	Seed     int64
	Pool     []string // credential ids for reads
	RunID    string
	Out      string
}

func classify(stage string, err error) (string, string) {
	code := "error"
	if st, ok := status.FromError(errors.Unwrap(err)); ok && st != nil {
		code = st.Code().String()
	}
	var ee *client.EndorseError
	var se *client.SubmitError
	var cs *client.CommitStatusError
	switch {
	case errors.As(err, &ee):
		stage = "endorse"
		code = status.Code(ee.Unwrap()).String()
	case errors.As(err, &se):
		stage = "submit"
		code = status.Code(se.Unwrap()).String()
	case errors.As(err, &cs):
		stage = "commit_status"
		code = status.Code(cs.Unwrap()).String()
	}
	if strings.Contains(err.Error(), "context deadline exceeded") {
		code = "DeadlineExceeded"
	}
	return stage, code
}

// RunBurst executes one run and writes its files.
func RunBurst(cfg *NetConfig, s *Signer, p RunParams) (*RunSummary, error) {
	if p.T < 1 || p.C < 1 {
		return nil, fmt.Errorf("T and C must be positive")
	}
	if p.Function == "get" && len(p.Pool) == 0 {
		return nil, fmt.Errorf("no credential pool for reads")
	}
	gw, err := openSession(s, gatewayPeer(cfg))
	if err != nil {
		return nil, err
	}
	defer gw.Close()
	contract := gw.GW.GetNetwork(cfg.Channel).GetContract(cfg.Chaincode)

	// Before t0, untimed: the workload, the start height and the listeners.
	wl, err := NewWorkload(p.Seed)
	if err != nil {
		return nil, err
	}
	rng := rand.New(rand.NewSource(p.Seed))
	recs := make([]TxRec, p.T)
	for i := range recs {
		recs[i] = TxRec{Idx: i, Send: -1, Endorsed: -1, Submitted: -1, GwCommit: -1, AllCommit: -1, Code: -1}
		if p.Function == "get" {
			recs[i].Arg = p.Pool[rng.Intn(len(p.Pool))]
		} else {
			recs[i].Arg = holderID(i % p.Holders)
		}
	}
	var lis *Listeners
	if p.Function == "issue" {
		h, err := Height(gw, cfg.Channel)
		if err != nil {
			return nil, fmt.Errorf("height: %w", err)
		}
		if lis, err = StartListeners(cfg, s, h); err != nil {
			return nil, err
		}
		defer lis.Close()
	}
	// One warm-up call on the connection (TLS handshake, Gateway set-up), untimed.
	if _, err := Height(gw, cfg.Channel); err != nil {
		return nil, err
	}
	time.Sleep(300 * time.Millisecond)

	workers := p.C
	if p.T < workers {
		workers = p.T
	}
	jobs := make(chan int, p.T)
	for i := 0; i < p.T; i++ {
		jobs <- i
	}
	close(jobs)
	start := make(chan struct{})
	var wg sync.WaitGroup
	var t0 time.Time
	since := func() int64 { return time.Since(t0).Nanoseconds() }
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for i := range jobs {
				r := &recs[i]
				if p.Function == "get" {
					r.Send = since()
					prop, err := contract.NewProposal("getCredential", client.WithArguments(r.Arg))
					if err != nil {
						r.ErrStage, r.ErrCode = "proposal", "error"
						continue
					}
					res, err := prop.Evaluate()
					r.GwCommit = since()
					r.TxID = prop.TransactionID()
					if err != nil {
						r.ErrStage, r.ErrCode = classify("evaluate", err)
						continue
					}
					r.ResultSize = len(res)
					var rec struct{ ID string }
					if json.Unmarshal(res, &rec) != nil || rec.ID != r.Arg {
						r.ErrStage, r.ErrCode = "read_check", "mismatch"
						continue
					}
					r.OK = true
					continue
				}
				args := wl.IssueArgs(i, p.Holders, time.Now())
				r.Send = since()
				prop, err := contract.NewProposal("issueCredential", client.WithArguments(args...))
				if err != nil {
					r.ErrStage, r.ErrCode = "proposal", "error"
					continue
				}
				r.TxID = prop.TransactionID()
				tx, err := prop.Endorse()
				if err != nil {
					r.ErrStage, r.ErrCode = classify("endorse", err)
					continue
				}
				r.Endorsed = since()
				commit, err := tx.Submit()
				if err != nil {
					r.ErrStage, r.ErrCode = classify("submit", err)
					continue
				}
				r.Submitted = since()
				st, err := commit.Status()
				if err != nil {
					r.ErrStage, r.ErrCode = classify("commit_status", err)
					continue
				}
				r.GwCommit = since()
				r.Block = st.BlockNumber
				r.Code = int32(st.Code)
				r.ResultSize = len(tx.Result())
				if !st.Successful {
					r.ErrStage, r.ErrCode = "validation", st.Code.String()
					continue
				}
				if !strings.Contains(string(tx.Result()), r.TxID) {
					r.ErrStage, r.ErrCode = "result_check", "mismatch"
					continue
				}
				r.OK = true
			}
		}()
	}
	t0 = time.Now()
	if lis != nil {
		lis.SetT0(t0)
	}
	close(start)
	wg.Wait()
	gwDone := since()

	// Commit on every peer (writes): wait for the highest block, then join.
	allPeersOK := true
	if lis != nil {
		var maxBlock uint64
		for _, r := range recs {
			if r.Code >= 0 && r.Block > maxBlock {
				maxBlock = r.Block
			}
		}
		if maxBlock > 0 {
			allPeersOK = lis.Arrivals.WaitFor(maxBlock, 120*time.Second)
		}
		for i := range recs {
			if recs[i].Code >= 0 {
				recs[i].AllCommit, recs[i].PeersSeen = lis.Arrivals.AllCommit(recs[i].Block)
				if recs[i].PeersSeen < len(cfg.Peers) {
					recs[i].AllCommit = -1
				}
			}
		}
	}
	sum := Summarise(p, cfg, s, recs, t0, gwDone)
	sum.AllPeersDelivered = allPeersOK
	if err := writeRun(p, recs, lis, sum); err != nil {
		return sum, err
	}
	return sum, nil
}

func writeRun(p RunParams, recs []TxRec, lis *Listeners, sum *RunSummary) error {
	header := []string{"idx", "arg", "txid", "send_ns", "endorsed_ns", "submitted_ns", "gw_commit_ns",
		"all_commit_ns", "peers_seen", "block", "code", "ok", "err_stage", "err_code", "result_bytes"}
	rows := make([][]string, 0, len(recs))
	for _, r := range recs {
		rows = append(rows, []string{strconv.Itoa(r.Idx), r.Arg, r.TxID, i64(r.Send), i64(r.Endorsed), i64(r.Submitted),
			i64(r.GwCommit), i64(r.AllCommit), strconv.Itoa(r.PeersSeen), strconv.FormatUint(r.Block, 10),
			strconv.Itoa(int(r.Code)), strconv.FormatBool(r.OK), r.ErrStage, r.ErrCode, strconv.Itoa(r.ResultSize)})
	}
	if err := writeCSVGz(p.Out+"/tx.csv.gz", header, rows); err != nil {
		return err
	}
	if lis != nil {
		if err := writeCSVGz(p.Out+"/arrivals.csv.gz", []string{"peer", "block", "recv_ns"}, lis.Arrivals.Rows()); err != nil {
			return err
		}
	}
	return writeJSON(p.Out+"/summary.json", sum)
}

func i64(v int64) string { return strconv.FormatInt(v, 10) }

// ctxTimeout is a helper for the setup's calls.
func ctxTimeout(d time.Duration) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), d)
}
