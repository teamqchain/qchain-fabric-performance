package main

// A network's untimed setup: holders registered with bound ML-KEM-768 and
// ML-DSA-44 public keys (registerHolder, bindHolderKeys, as the backend does
// when a holder joins), a pool of credentials for the reads, and a warm-up.

import (
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
)

// SetupParams are the setup's sizes.
type SetupParams struct {
	Holders   int
	Pool      int
	Warm      int
	C         int
	Seed      int64
	PoolFile  string
	SkipHolds bool // holders already registered (a resumed network)
}

// parallel runs f(0..n-1) with c workers and returns the first error.
func parallel(n, c int, f func(i int) error) error {
	if c > n {
		c = n
	}
	jobs := make(chan int, n)
	for i := 0; i < n; i++ {
		jobs <- i
	}
	close(jobs)
	var wg sync.WaitGroup
	var first atomic.Value
	for w := 0; w < c; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				if first.Load() != nil {
					return
				}
				if err := f(i); err != nil {
					first.CompareAndSwap(nil, err)
				}
			}
		}()
	}
	wg.Wait()
	if e := first.Load(); e != nil {
		return e.(error)
	}
	return nil
}

func submit(contract *client.Contract, fn string, args ...string) ([]byte, error) {
	var res []byte
	var err error
	for attempt := 0; attempt < 3; attempt++ {
		res, err = contract.SubmitTransaction(fn, args...)
		if err == nil {
			return res, nil
		}
		time.Sleep(time.Second)
	}
	return nil, err
}

// Setup registers the holders, issues the read pool and warms the network up.
func Setup(cfg *NetConfig, s *Signer, p SetupParams) error {
	gw, err := openSession(s, gatewayPeer(cfg))
	if err != nil {
		return err
	}
	defer gw.Close()
	contract := gw.GW.GetNetwork(cfg.Channel).GetContract(cfg.Chaincode)
	t := time.Now()
	if !p.SkipHolds {
		err = parallel(p.Holders, 20, func(i int) error {
			id := holderID(i)
			if _, err := submit(contract, "registerHolder", id, "Holder", fmt.Sprintf("Number %d", i+1)); err != nil {
				if !strings.Contains(err.Error(), "already registered") {
					return fmt.Errorf("registerHolder %s: %w", id, err)
				}
			}
			kem, dsa, err := HolderKeys()
			if err != nil {
				return err
			}
			if _, err := submit(contract, "bindHolderKeys", id, kem, dsa); err != nil {
				return fmt.Errorf("bindHolderKeys %s: %w", id, err)
			}
			return nil
		})
		if err != nil {
			return err
		}
		fmt.Printf("setup: %d holders in %.1f s\n", p.Holders, time.Since(t).Seconds())
	}
	wl, err := NewWorkload(p.Seed)
	if err != nil {
		return err
	}
	ids := make([]string, p.Pool)
	t = time.Now()
	err = parallel(p.Pool, p.C, func(i int) error {
		res, err := submit(contract, "issueCredential", wl.IssueArgs(i, p.Holders, time.Now())...)
		if err != nil {
			return fmt.Errorf("pool credential %d: %w", i, err)
		}
		var out struct {
			CredentialID string `json:"credentialID"`
		}
		if err := jsonUnmarshal(res, &out); err != nil || out.CredentialID == "" {
			return fmt.Errorf("pool credential %d: unexpected result %q", i, string(res))
		}
		ids[i] = out.CredentialID
		return nil
	})
	if err != nil {
		return err
	}
	fmt.Printf("setup: %d pool credentials in %.1f s\n", p.Pool, time.Since(t).Seconds())
	if err := writeFileAtomic(p.PoolFile, []byte(strings.Join(ids, "\n")+"\n")); err != nil {
		return err
	}
	t = time.Now()
	err = parallel(p.Warm, p.C, func(i int) error {
		_, err := submit(contract, "issueCredential", wl.IssueArgs(p.Pool+i, p.Holders, time.Now())...)
		return err
	})
	if err != nil {
		return fmt.Errorf("warm-up writes: %w", err)
	}
	err = parallel(p.Warm, p.C, func(i int) error {
		_, err := contract.EvaluateTransaction("getCredential", ids[i%len(ids)])
		return err
	})
	if err != nil {
		return fmt.Errorf("warm-up reads: %w", err)
	}
	fmt.Printf("setup: warm-up %d writes and %d reads in %.1f s\n", p.Warm, p.Warm, time.Since(t).Seconds())
	return nil
}
