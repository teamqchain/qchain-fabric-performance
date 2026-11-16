package main

// The client's identity and connections, made as QChain's backend makes them
// (qchain-backend ledger/fabric.go at commit b5a7ace, see docs/provenance.md):
// the issuer's X.509 certificate and PKCS#8 key, a TLS gRPC connection to the
// organisation's peer with the backend's receive limit, a Gateway with the
// backend's timeouts, and the backend's signer (newSign, copied verbatim
// below). One difference, by design (docs/live-differences.md): the backend
// opens a new connection for every call; the load generator keeps one open per
// run, and E2 measures what reconnecting costs.

import (
	"crypto"
	"crypto/mldsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"github.com/hyperledger/fabric-gateway/pkg/identity"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
)

// PeerInfo is one peer as network/gen/qfp_gen.py describes it in client.json.
type PeerInfo struct {
	Name     string `json:"name"`
	Endpoint string `json:"endpoint"`
	Org      string `json:"org"`
	MSP      string `json:"msp"`
	TLSCA    string `json:"tlsca"`
}

// NetConfig is client.json, written by the generator for each network.
type NetConfig struct {
	Network           string     `json:"network"`
	Orgs              int        `json:"orgs"`
	PeersTotal        int        `json:"peers_total"`
	Identity          string     `json:"identity"`
	Blocks            string     `json:"blocks"`
	Endorsements      int        `json:"endorsements"`
	Channel           string     `json:"channel"`
	Chaincode         string     `json:"chaincode"`
	MSPID             string     `json:"mspid"`
	MSPDir            string     `json:"mspdir"`
	Gateway           PeerInfo   `json:"gateway"`
	Peers             []PeerInfo `json:"peers"`
	MaxMessageCount   int        `json:"max_message_count"`
	PreferredMaxBytes int        `json:"preferred_max_bytes"`
	BatchTimeoutS     int        `json:"batch_timeout_s"`
}

func loadNetConfig(path string) (*NetConfig, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var c NetConfig
	if err := json.Unmarshal(b, &c); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if c.Channel == "" || c.Chaincode == "" || c.MSPID == "" || c.Gateway.Endpoint == "" || len(c.Peers) == 0 {
		return nil, fmt.Errorf("%s: incomplete network description", path)
	}
	return &c, nil
}

// Signer is the client identity and its signing function.
type Signer struct {
	ID        *identity.X509Identity
	Sign      identity.Sign
	Algorithm string // "ML-DSA-44" or "ECDSA" (from the certificate)
	CertBytes int    // DER size of the client certificate
}

// loadSigner reads the MSP folder the Fabric CA client wrote: the certificate
// in signcerts/ and, of the keystore's *_sk files, the key that matches it
// (as qchain-backend cmd/mkwallet does: a PQC keystore also holds _pk files).
func loadSigner(mspDir, mspID string) (*Signer, error) {
	certPEM, err := onlyFile(filepath.Join(mspDir, "signcerts"))
	if err != nil {
		return nil, err
	}
	cb, _ := pem.Decode(certPEM)
	if cb == nil {
		return nil, errors.New("signing certificate is not PEM")
	}
	cert, err := x509.ParseCertificate(cb.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parsing certificate: %w", err)
	}
	keys, err := filepath.Glob(filepath.Join(mspDir, "keystore", "*_sk"))
	if err != nil {
		return nil, err
	}
	var priv any
	for _, f := range keys {
		data, err := os.ReadFile(f)
		if err != nil {
			return nil, err
		}
		k, err := identity.PrivateKeyFromPEM(data)
		if err != nil {
			continue
		}
		s, ok := k.(crypto.Signer)
		if !ok {
			continue
		}
		if pub, ok := s.Public().(interface{ Equal(crypto.PublicKey) bool }); ok && pub.Equal(cert.PublicKey) {
			if priv != nil {
				return nil, fmt.Errorf("more than one key in %s matches the certificate", mspDir)
			}
			priv = k
		}
	}
	if priv == nil {
		return nil, fmt.Errorf("no key in %s/keystore matches the certificate", mspDir)
	}
	id, err := identity.NewX509Identity(mspID, cert)
	if err != nil {
		return nil, err
	}
	sign, err := newSign(priv)
	if err != nil {
		return nil, err
	}
	alg := "ECDSA"
	if _, ok := priv.(*mldsa.PrivateKey); ok {
		alg = "ML-DSA-44"
	}
	return &Signer{ID: id, Sign: sign, Algorithm: alg, CertBytes: len(cb.Bytes)}, nil
}

func onlyFile(dir string) ([]byte, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var files []string
	for _, e := range ents {
		if !e.IsDir() {
			files = append(files, e.Name())
		}
	}
	if len(files) != 1 {
		return nil, fmt.Errorf("expected exactly one file in %s, found %d", dir, len(files))
	}
	return os.ReadFile(filepath.Join(dir, files[0]))
}

// ---- copied verbatim from qchain-backend ledger/fabric.go (b5a7ace) -------

// newSign returns the Gateway signing function for privateKey. fabric-gateway's
// identity.NewPrivateKeySign only supports ECDSA and Ed25519, so ML-DSA keys get
// their own signer. The Gateway hashes each message with its default SHA-256
// before calling sign, and the Fabric MSP verifies ML-DSA signatures over that
// SHA-256 digest (msp/identities.go), so the signer must sign the digest as
// given: pure ML-DSA, empty context.
func newSign(privateKey any) (identity.Sign, error) {
	if key, ok := privateKey.(*mldsa.PrivateKey); ok {
		return func(digest []byte) ([]byte, error) {
			return key.Sign(nil, digest, nil)
		}, nil
	}
	return identity.NewPrivateKeySign(privateKey)
}

// ---- end of the verbatim copy ---------------------------------------------

// dial opens a TLS gRPC connection to a peer, as the backend's getContract
// does (grpc.Dial, the peer's TLS CA, 64 MB receive limit).
func dial(endpoint, tlsCAFile string) (*grpc.ClientConn, error) {
	caPEM, err := os.ReadFile(tlsCAFile)
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("no certificate in %s", tlsCAFile)
	}
	host := strings.Split(endpoint, ":")[0]
	return grpc.Dial(endpoint, //nolint:staticcheck // the backend's call
		grpc.WithTransportCredentials(credentials.NewClientTLSFromCert(pool, host)),
		grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(64<<20)),
	)
}

// connectGateway is the backend's client.Connect with its four timeouts.
func connectGateway(s *Signer, conn *grpc.ClientConn) (*client.Gateway, error) {
	return client.Connect(s.ID,
		client.WithSign(s.Sign),
		client.WithClientConnection(conn),
		client.WithEvaluateTimeout(30*time.Second),
		client.WithEndorseTimeout(30*time.Second),
		client.WithSubmitTimeout(30*time.Second),
		client.WithCommitStatusTimeout(60*time.Second),
	)
}

// Session is an open connection and Gateway to one peer.
type Session struct {
	Peer PeerInfo
	Conn *grpc.ClientConn
	GW   *client.Gateway
}

func openSession(s *Signer, p PeerInfo) (*Session, error) {
	conn, err := dial(p.Endpoint, p.TLSCA)
	if err != nil {
		return nil, fmt.Errorf("dial %s: %w", p.Endpoint, err)
	}
	gw, err := connectGateway(s, conn)
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("gateway %s: %w", p.Endpoint, err)
	}
	return &Session{Peer: p, Conn: conn, GW: gw}, nil
}

func (s *Session) Close() {
	s.GW.Close()
	s.Conn.Close()
}

func gatewayPeer(c *NetConfig) PeerInfo {
	for _, p := range c.Peers {
		if p.Endpoint == c.Gateway.Endpoint {
			return p
		}
	}
	return PeerInfo{Name: c.Gateway.Name, Endpoint: c.Gateway.Endpoint, TLSCA: c.Gateway.TLSCA}
}
