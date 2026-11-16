package main

// The transactions' content. Writes are QChain's issueCredential with the
// argument shapes the Go backend sends (qchain-backend at b5a7ace; chaincode
// QChaincode.js in network/live): a registered holder with bound ML-KEM-768
// and ML-DSA-44 public keys, ten SHA3-256 field hashes, an IPFS CIDv0, the
// SHA3-256 credential hash, and the issuer's ML-DSA-44 signature and public
// key as lowercase hex. The keys and signatures are real (Go crypto/mldsa and
// crypto/mlkem) and made before the timed region; the chaincode checks their
// format, not the signature, as in production. The content is identical in
// both identity arms: only Fabric's own identities differ between them.
//
// Reads are getCredential of a credential issued during the network's setup.

import (
	"crypto/mldsa"
	"crypto/mlkem"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/rand"
	"sort"
	"strings"
	"time"

	"golang.org/x/crypto/sha3"
)

const (
	issuerOrg      = "GeneralMSP"
	credentialType = "Bachelor of Science"
	expiryDate     = "2031-06-30"
	nVariants      = 64 // distinct signed commitments per process, used in turn
)

// holderID is the backend's server-generated holder identifier (H-0001, ...).
func holderID(i int) string { return fmt.Sprintf("H-%04d", i+1) }

// fields are the ten credential attributes of the KPI study's E13 model.
var fields = []string{"fullName", "studentId", "programme", "degree", "major",
	"cgpa", "graduationDate", "college", "honours", "nationality"}

// Workload holds the precomputed parts of every transaction of one process.
type Workload struct {
	rng      *rand.Rand
	issuerPK string // 2,624 hex
	variants []variant
	loc      *time.Location
}

type variant struct {
	fieldHashes string // JSON object, sorted keys
	cid         string
	hash        string // 64 hex
	sig         string // 4,840 hex
}

// NewWorkload makes the issuer key and nVariants signed credential bodies.
func NewWorkload(seed int64) (*Workload, error) {
	sk, err := mldsa.GenerateKey(mldsa.MLDSA44())
	if err != nil {
		return nil, err
	}
	w := &Workload{rng: rand.New(rand.NewSource(seed)), issuerPK: hex.EncodeToString(sk.PublicKey().Bytes())}
	w.loc = time.FixedZone("+04", 4*3600) // the backend's issuedAt is UAE local time
	for v := 0; v < nVariants; v++ {
		salt := make([]byte, 16)
		w.rng.Read(salt)
		fh := map[string]string{}
		for _, f := range fields {
			val := fmt.Sprintf("%s-value-%d-%d", f, seed, v)
			sum := sha3.Sum256([]byte(hex.EncodeToString(salt) + ":" + f + ":" + val))
			fh[f] = hex.EncodeToString(sum[:])
		}
		fhJSON := sortedJSON(fh)
		cidSum := sha3.Sum256([]byte(fhJSON))
		commitment := sortedJSON(map[string]string{"v": "2", "credentialType": credentialType, "issuerOrgID": issuerOrg,
			"expiryDate": expiryDate, "fieldHashes": fhJSON, "variant": fmt.Sprint(v)})
		h := sha3.Sum256([]byte(commitment))
		sig, err := sk.Sign(nil, h[:], nil)
		if err != nil {
			return nil, err
		}
		w.variants = append(w.variants, variant{fieldHashes: fhJSON, cid: "Qm" + base58(cidSum[:])[:44],
			hash: hex.EncodeToString(h[:]), sig: hex.EncodeToString(sig)})
	}
	return w, nil
}

// IssueArgs are issueCredential's ten arguments for transaction i; issuedAt
// is the send time (the chaincode accepts 300 s of skew).
func (w *Workload) IssueArgs(i, holders int, now time.Time) []string {
	v := w.variants[i%len(w.variants)]
	return []string{holderID(i % holders), credentialType, now.In(w.loc).Format("2006-01-02T15:04:05-07:00"),
		expiryDate, issuerOrg, v.cid, v.fieldHashes, v.hash, v.sig, w.issuerPK}
}

// HolderKeys are real ML-KEM-768 and ML-DSA-44 public keys, as hex.
func HolderKeys() (kemHex, dsaHex string, err error) {
	dk, err := mlkem.GenerateKey768()
	if err != nil {
		return "", "", err
	}
	sk, err := mldsa.GenerateKey(mldsa.MLDSA44())
	if err != nil {
		return "", "", err
	}
	return hex.EncodeToString(dk.EncapsulationKey().Bytes()), hex.EncodeToString(sk.PublicKey().Bytes()), nil
}

func sortedJSON(m map[string]string) string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var b strings.Builder
	b.WriteByte('{')
	for i, k := range keys {
		if i > 0 {
			b.WriteByte(',')
		}
		kb, _ := json.Marshal(k)
		vb, _ := json.Marshal(m[k])
		b.Write(kb)
		b.WriteByte(':')
		b.Write(vb)
	}
	b.WriteByte('}')
	return b.String()
}

const b58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

func base58(in []byte) string {
	x := append([]byte(nil), in...)
	var out []byte
	for len(x) > 0 {
		var rem int
		var q []byte
		for _, d := range x {
			acc := rem*256 + int(d)
			if len(q) > 0 || acc/58 > 0 {
				q = append(q, byte(acc/58))
			}
			rem = acc % 58
		}
		out = append(out, b58[rem])
		x = q
	}
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	for len(out) < 46 {
		out = append([]byte{'1'}, out...)
	}
	return string(out)
}
