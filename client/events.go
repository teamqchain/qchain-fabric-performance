package main

// Commit on every peer. The Hyperledger performance working group defines a
// transaction's latency until its result is usable across the network
// (confirmation at the network threshold, 100 % of the peers for a
// deterministic protocol). The Gateway reports the commit on its own peer
// only, so the client also listens to the filtered block events of every
// peer and records when each block arrives there; a transaction is committed
// on all peers when the last peer has delivered its block.

import (
	"context"
	"fmt"
	"strconv"
	"sync"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"github.com/hyperledger/fabric-protos-go-apiv2/common"
	"google.golang.org/protobuf/proto"
)

// BlockArrivals records, per peer, when each block arrived (ns since t0).
type BlockArrivals struct {
	mu    sync.Mutex
	peers []string
	t     map[string]map[uint64]int64
	last  map[string]uint64
	seen  map[string]bool
	errs  []string
	t0    time.Time
}

func (b *BlockArrivals) add(peer string, n uint64) {
	ns := time.Since(b.t0).Nanoseconds()
	b.mu.Lock()
	if _, ok := b.t[peer][n]; !ok {
		b.t[peer][n] = ns
	}
	if !b.seen[peer] || n > b.last[peer] {
		b.last[peer] = n
		b.seen[peer] = true
	}
	b.mu.Unlock()
}

// AllCommit is when block n had reached every peer, and on how many peers it
// was seen.
func (b *BlockArrivals) AllCommit(n uint64) (int64, int) {
	b.mu.Lock()
	defer b.mu.Unlock()
	var max int64 = -1
	seen := 0
	for _, p := range b.peers {
		if ns, ok := b.t[p][n]; ok {
			seen++
			if ns > max {
				max = ns
			}
		}
	}
	return max, seen
}

// WaitFor returns when every peer has delivered block n, or after timeout.
func (b *BlockArrivals) WaitFor(n uint64, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		b.mu.Lock()
		ok := true
		for _, p := range b.peers {
			if !b.seen[p] || b.last[p] < n {
				ok = false
				break
			}
		}
		b.mu.Unlock()
		if ok {
			return true
		}
		time.Sleep(20 * time.Millisecond)
	}
	return false
}

// Rows returns (peer, block, ns) for every arrival, for the run's files.
func (b *BlockArrivals) Rows() [][]string {
	b.mu.Lock()
	defer b.mu.Unlock()
	var rows [][]string
	for _, p := range b.peers {
		for n, ns := range b.t[p] {
			rows = append(rows, []string{p, strconv.FormatUint(n, 10), strconv.FormatInt(ns, 10)})
		}
	}
	return rows
}

// Listeners holds one Gateway session per peer for block events.
type Listeners struct {
	Arrivals *BlockArrivals
	sessions []*Session
	cancel   context.CancelFunc
	wg       sync.WaitGroup
}

// StartListeners opens a session to every peer and receives filtered blocks
// from block `start` on. The caller sets Arrivals.t0 through SetT0 before the
// first transaction is sent.
func StartListeners(cfg *NetConfig, s *Signer, start uint64) (*Listeners, error) {
	ctx, cancel := context.WithCancel(context.Background())
	l := &Listeners{cancel: cancel, Arrivals: &BlockArrivals{
		t: map[string]map[uint64]int64{}, last: map[string]uint64{}, seen: map[string]bool{}, t0: time.Now()}}
	for _, p := range cfg.Peers {
		sess, err := openSession(s, p)
		if err != nil {
			l.Close()
			return nil, err
		}
		l.sessions = append(l.sessions, sess)
		l.Arrivals.peers = append(l.Arrivals.peers, p.Name)
		l.Arrivals.t[p.Name] = map[uint64]int64{}
		events, err := sess.GW.GetNetwork(cfg.Channel).FilteredBlockEvents(ctx, client.WithStartBlock(start))
		if err != nil {
			l.Close()
			return nil, fmt.Errorf("block events from %s: %w", p.Name, err)
		}
		l.wg.Add(1)
		go func(name string) {
			defer l.wg.Done()
			for blk := range events {
				l.Arrivals.add(name, blk.GetNumber())
			}
		}(p.Name)
	}
	return l, nil
}

func (l *Listeners) SetT0(t0 time.Time) {
	l.Arrivals.mu.Lock()
	l.Arrivals.t0 = t0
	l.Arrivals.mu.Unlock()
}

func (l *Listeners) Close() {
	l.cancel()
	for _, s := range l.sessions {
		s.Close()
	}
	l.wg.Wait()
}

// Height asks a peer for the channel height (qscc GetChainInfo).
func Height(sess *Session, channel string) (uint64, error) {
	raw, err := sess.GW.GetNetwork(channel).GetContract("qscc").Evaluate("GetChainInfo", client.WithArguments(channel))
	if err != nil {
		return 0, err
	}
	var info common.BlockchainInfo
	if err := proto.Unmarshal(raw, &info); err != nil {
		return 0, err
	}
	return info.Height, nil
}
