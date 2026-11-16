package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/mldsa"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"regexp"
	"testing"
	"time"

	"github.com/hyperledger/fabric-protos-go-apiv2/common"
	"github.com/hyperledger/fabric-protos-go-apiv2/msp"
	"github.com/hyperledger/fabric-protos-go-apiv2/peer"
	"google.golang.org/protobuf/proto"
)

// The chaincode's input rules (network/live/chaincode/QChaincode.js).
var (
	hexRe      = regexp.MustCompile(`^[0-9a-fA-F]+$`)
	hashRe     = regexp.MustCompile(`^[0-9a-f]{64}$`)
	issuedAtRe = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$`)
	cidRe      = regexp.MustCompile(`^[A-Za-z0-9]{10,128}$`)
	dateRe     = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
)

func TestIssueArgsMeetChaincodeRules(t *testing.T) {
	w, err := NewWorkload(7)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	for i := 0; i < 2*nVariants; i++ {
		a := w.IssueArgs(i, 100, now)
		if len(a) != 10 {
			t.Fatalf("issueCredential takes 10 arguments, got %d", len(a))
		}
		if a[0] != holderID(i%100) || a[1] == "" || a[4] != "GeneralMSP" {
			t.Fatalf("holder/type/org wrong: %v", a[:5])
		}
		if !issuedAtRe.MatchString(a[2]) {
			t.Fatalf("issuedAt %q", a[2])
		}
		ts, _ := time.Parse(time.RFC3339, a[2])
		if d := ts.Sub(now); d > time.Second || d < -time.Second {
			t.Fatalf("issuedAt %s is not the send time", a[2])
		}
		if !dateRe.MatchString(a[3]) || !cidRe.MatchString(a[5]) {
			t.Fatalf("expiry %q or cid %q", a[3], a[5])
		}
		var fh map[string]string
		if err := json.Unmarshal([]byte(a[6]), &fh); err != nil || len(fh) != 10 {
			t.Fatalf("fieldHashes %q", a[6])
		}
		for k, v := range fh {
			if k == "" || k[0] == '_' || !hashRe.MatchString(v) {
				t.Fatalf("field %q = %q", k, v)
			}
		}
		if !hashRe.MatchString(a[7]) {
			t.Fatalf("credentialHash %q", a[7])
		}
		if !hexRe.MatchString(a[8]) || len(a[8]) != 2*2420 {
			t.Fatalf("issuerSignature: %d hex characters", len(a[8]))
		}
		if !hexRe.MatchString(a[9]) || len(a[9]) != 2624 {
			t.Fatalf("issuerPublicKey: %d hex characters, want 2624", len(a[9]))
		}
	}
	// the signature is a real ML-DSA-44 signature over the credential hash
	a := w.IssueArgs(3, 100, now)
	pkb, _ := hex.DecodeString(a[9])
	pk, err := mldsa.NewPublicKey(mldsa.MLDSA44(), pkb)
	if err != nil {
		t.Fatal(err)
	}
	h, _ := hex.DecodeString(a[7])
	sig, _ := hex.DecodeString(a[8])
	if err := mldsa.Verify(pk, h, sig, nil); err != nil {
		t.Fatalf("signature does not verify: %v", err)
	}
}

func TestHolderKeysLengths(t *testing.T) {
	kem, dsa, err := HolderKeys()
	if err != nil {
		t.Fatal(err)
	}
	if len(kem) != 2368 || len(dsa) != 2624 { // KEM_PUBLIC_KEY_HEX_LENGTH, DSA_PUBLIC_KEY_HEX_LENGTH
		t.Fatalf("kem %d, dsa %d hex characters", len(kem), len(dsa))
	}
}

func TestBase58CID(t *testing.T) {
	c := "Qm" + base58(make([]byte, 32))[:44]
	if len(c) != 46 || !cidRe.MatchString(c) {
		t.Fatalf("cid %q", c)
	}
}

func serialized(t *testing.T, mspid string, idBytes int) []byte {
	b, err := proto.Marshal(&msp.SerializedIdentity{Mspid: mspid, IdBytes: make([]byte, idBytes)})
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func mustMarshal(t *testing.T, m proto.Message) []byte {
	b, err := proto.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

// A synthetic endorser transaction with known part sizes must be split back
// into exactly those sizes.
func TestDecodeBlockParts(t *testing.T) {
	const certSize, sigSize, inSize, respSize = 5400, 2420, 9000, 8800
	endorsements := []*peer.Endorsement{
		{Endorser: serialized(t, "GeneralMSP", certSize), Signature: make([]byte, sigSize)},
		{Endorser: serialized(t, "GovernmentMSP", certSize), Signature: make([]byte, sigSize)},
	}
	cap := &peer.ChaincodeActionPayload{
		ChaincodeProposalPayload: make([]byte, inSize),
		Action:                   &peer.ChaincodeEndorsedAction{ProposalResponsePayload: make([]byte, respSize), Endorsements: endorsements},
	}
	sh := mustMarshal(t, &common.SignatureHeader{Creator: serialized(t, "GeneralMSP", certSize), Nonce: make([]byte, 24)})
	tx := &peer.Transaction{Actions: []*peer.TransactionAction{{Header: sh, Payload: mustMarshal(t, cap)}}}
	ch := mustMarshal(t, &common.ChannelHeader{Type: int32(common.HeaderType_ENDORSER_TRANSACTION), TxId: "abc", ChannelId: "mychannel"})
	pl := mustMarshal(t, &common.Payload{Header: &common.Header{ChannelHeader: ch, SignatureHeader: sh}, Data: mustMarshal(t, tx)})
	env := mustMarshal(t, &common.Envelope{Payload: pl, Signature: make([]byte, sigSize)})
	md := mustMarshal(t, &common.Metadata{Signatures: []*common.MetadataSignature{{Signature: make([]byte, sigSize)}}})
	blk := &common.Block{Header: &common.BlockHeader{Number: 5}, Data: &common.BlockData{Data: [][]byte{env}},
		Metadata: &common.BlockMetadata{Metadata: [][]byte{md, {}, {0}, {}, {}}}}
	bb, txs, err := DecodeBlock(mustMarshal(t, blk))
	if err != nil {
		t.Fatal(err)
	}
	if bb.Number != 5 || bb.NTx != 1 || bb.OrdererSigs != sigSize || len(txs) != 1 {
		t.Fatalf("block %+v", bb)
	}
	x := txs[0]
	if x.TxID != "abc" || x.Type != "ENDORSER_TRANSACTION" || x.Code != 0 {
		t.Fatalf("tx header %+v", x)
	}
	if x.NCerts != 4 || x.Certs != 4*certSize {
		t.Fatalf("certificates: %d in %d bytes", x.NCerts, x.Certs)
	}
	if x.NSigs != 3 || x.Sigs != 3*sigSize || x.Endorsements != 2 {
		t.Fatalf("signatures: %d in %d bytes", x.NSigs, x.Sigs)
	}
	if x.Input != inSize || x.Response != respSize || x.Envelope != len(env) {
		t.Fatalf("input %d response %d envelope %d", x.Input, x.Response, x.Envelope)
	}
	if rest := x.Envelope - x.Certs - x.Sigs - x.Input - x.Response; rest <= 0 || rest > 400 {
		t.Fatalf("rest %d bytes", rest)
	}
}

func TestSummariseDefinitions(t *testing.T) {
	cfg := &NetConfig{Network: "n", Identity: "mldsa44", PeersTotal: 2}
	s := &Signer{Algorithm: "ML-DSA-44"}
	ms := int64(time.Millisecond)
	recs := []TxRec{
		{Send: 0, Endorsed: 10 * ms, Submitted: 20 * ms, GwCommit: 100 * ms, AllCommit: 110 * ms, OK: true, Block: 3},
		{Send: 5 * ms, Endorsed: 15 * ms, Submitted: 25 * ms, GwCommit: 200 * ms, AllCommit: 205 * ms, OK: true, Block: 4},
		{Send: 6 * ms, ErrStage: "endorse", ErrCode: "Unavailable", Endorsed: -1, Submitted: -1, GwCommit: -1, AllCommit: -1},
	}
	sum := Summarise(RunParams{Function: "issue", T: 3, C: 3}, cfg, s, recs, time.Now(), 0)
	if sum.OK != 2 || sum.Failed != 1 || sum.Failures["endorse:Unavailable"] != 1 {
		t.Fatalf("counts %+v", sum)
	}
	// execution time: last confirmation on all peers (205 ms) minus first send (0)
	if sum.ExecAllS != 0.205 || sum.TputAll < 9.75 || sum.TputAll > 9.76 {
		t.Fatalf("execution %.3f s, throughput %.3f", sum.ExecAllS, sum.TputAll)
	}
	if sum.LatAll.N != 2 || sum.LatAll.MeanMS != 155 || sum.LatAll.MaxMS != 200 {
		t.Fatalf("latency %+v", sum.LatAll)
	}
	if sum.BlocksUsed != 2 || sum.Spread.MaxMS != 10 {
		t.Fatalf("blocks %d spread %+v", sum.BlocksUsed, sum.Spread)
	}
}

func TestQuantile(t *testing.T) {
	s := []int64{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
	if q := quantile(s, 0.5); q != 5.5 {
		t.Fatalf("median %v", q)
	}
	if q := quantile(s, 0.95); q < 9.54 || q > 9.56 {
		t.Fatalf("p95 %v", q)
	}
}

func writeMSP(t *testing.T, dir string, key any, pub any) {
	tmpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "issuer1"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour)}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, pub, key)
	if err != nil {
		t.Fatal(err)
	}
	p8, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	os.MkdirAll(filepath.Join(dir, "signcerts"), 0o700)
	os.MkdirAll(filepath.Join(dir, "keystore"), 0o700)
	os.WriteFile(filepath.Join(dir, "signcerts", "cert.pem"), pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o600)
	os.WriteFile(filepath.Join(dir, "keystore", "aaaa_sk"), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: p8}), 0o600)
	os.WriteFile(filepath.Join(dir, "keystore", "aaaa_pk"), []byte("not a key"), 0o600) // as in a PQC keystore
}

func TestLoadSignerBothAlgorithms(t *testing.T) {
	d := t.TempDir()
	mk, err := mldsa.GenerateKey(mldsa.MLDSA44())
	if err != nil {
		t.Fatal(err)
	}
	writeMSP(t, filepath.Join(d, "pq"), mk, mk.PublicKey())
	ek, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	writeMSP(t, filepath.Join(d, "ec"), ek, &ek.PublicKey)
	for _, c := range []struct{ dir, alg string }{{"pq", "ML-DSA-44"}, {"ec", "ECDSA"}} {
		s, err := loadSigner(filepath.Join(d, c.dir), "GeneralMSP")
		if err != nil {
			t.Fatalf("%s: %v", c.dir, err)
		}
		if s.Algorithm != c.alg {
			t.Fatalf("%s: algorithm %s", c.dir, s.Algorithm)
		}
		sig, err := s.Sign(make([]byte, 32))
		if err != nil || len(sig) == 0 {
			t.Fatalf("%s: sign %v", c.dir, err)
		}
		if c.alg == "ML-DSA-44" && len(sig) != 2420 {
			t.Fatalf("ML-DSA-44 signature %d bytes", len(sig))
		}
	}
}

func TestCanary(t *testing.T) {
	c := RunCanary(3, 20*time.Millisecond)
	if c.Windows != 3 || c.MedianRate <= 0 || len(c.Digest) != 8 {
		t.Fatalf("canary %+v", c)
	}
}
