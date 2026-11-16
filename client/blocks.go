package main

// The ledger's bytes (M7, M8). Every block is read back from the gateway peer
// (qscc GetBlockByNumber) after the network's runs, and every endorser
// transaction is split into the parts that change with the identity
// algorithm:
//
//   certificates  the id_bytes of every serialized identity in the
//                 transaction: the creator in the payload header, the
//                 creator again in the transaction action's header, and one
//                 endorser per endorsement
//   signatures    the envelope's signature and every endorsement's signature
//   input         the chaincode proposal payload (the call's arguments)
//   response      the proposal response payload (read-write set, result)
//   rest          everything else (headers, nonces, MSP ids, framing)
//
// orderer_bytes is what the orderer's block cutter counts against
// PreferredMaxBytes: len(payload) + len(signature)
// (fabric orderer/common/blockcutter).

import (
	"fmt"
	"strconv"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"github.com/hyperledger/fabric-protos-go-apiv2/common"
	"github.com/hyperledger/fabric-protos-go-apiv2/msp"
	"github.com/hyperledger/fabric-protos-go-apiv2/peer"
	"google.golang.org/protobuf/proto"
)

// TxBytes is one transaction's size breakdown.
type TxBytes struct {
	Block        uint64
	Index        int
	TxID         string
	Type         string // ENDORSER_TRANSACTION, CONFIG, ...
	Code         int32
	Envelope     int
	OrdererBytes int
	Certs        int
	NCerts       int
	Sigs         int
	NSigs        int
	Input        int
	Response     int
	Endorsements int
}

// BlockBytes is one block's size breakdown.
type BlockBytes struct {
	Number        uint64
	Bytes         int
	DataBytes     int
	MetadataBytes int
	OrdererSigs   int // signature bytes in the SIGNATURES metadata
	NTx           int
	OrdererSum    int
}

func idBytes(serialized []byte) (int, error) {
	var sid msp.SerializedIdentity
	if err := proto.Unmarshal(serialized, &sid); err != nil {
		return 0, err
	}
	return len(sid.IdBytes), nil
}

// DecodeBlock splits a marshalled block into its transactions' parts.
func DecodeBlock(raw []byte) (*BlockBytes, []TxBytes, error) {
	var b common.Block
	if err := proto.Unmarshal(raw, &b); err != nil {
		return nil, nil, fmt.Errorf("block: %w", err)
	}
	if b.Header == nil || b.Data == nil {
		return nil, nil, fmt.Errorf("block without header or data")
	}
	bb := &BlockBytes{Number: b.Header.Number, Bytes: len(raw), NTx: len(b.Data.Data)}
	for _, d := range b.Data.Data {
		bb.DataBytes += len(d)
	}
	var filter []byte
	if b.Metadata != nil {
		for _, m := range b.Metadata.Metadata {
			bb.MetadataBytes += len(m)
		}
		if len(b.Metadata.Metadata) > int(common.BlockMetadataIndex_SIGNATURES) {
			var md common.Metadata
			if proto.Unmarshal(b.Metadata.Metadata[common.BlockMetadataIndex_SIGNATURES], &md) == nil {
				for _, s := range md.Signatures {
					bb.OrdererSigs += len(s.Signature)
				}
			}
		}
		if len(b.Metadata.Metadata) > int(common.BlockMetadataIndex_TRANSACTIONS_FILTER) {
			filter = b.Metadata.Metadata[common.BlockMetadataIndex_TRANSACTIONS_FILTER]
		}
	}
	var txs []TxBytes
	for i, envBytes := range b.Data.Data {
		t := TxBytes{Block: b.Header.Number, Index: i, Envelope: len(envBytes), Code: -1}
		if i < len(filter) {
			t.Code = int32(filter[i])
		}
		var env common.Envelope
		if err := proto.Unmarshal(envBytes, &env); err != nil {
			return nil, nil, fmt.Errorf("block %d tx %d: %w", t.Block, i, err)
		}
		t.OrdererBytes = len(env.Payload) + len(env.Signature)
		bb.OrdererSum += t.OrdererBytes
		t.Sigs, t.NSigs = len(env.Signature), 1
		var pl common.Payload
		if err := proto.Unmarshal(env.Payload, &pl); err != nil {
			return nil, nil, err
		}
		if pl.Header != nil {
			var ch common.ChannelHeader
			if err := proto.Unmarshal(pl.Header.ChannelHeader, &ch); err == nil {
				t.TxID = ch.TxId
				t.Type = common.HeaderType(ch.Type).String()
			}
			var sh common.SignatureHeader
			if err := proto.Unmarshal(pl.Header.SignatureHeader, &sh); err == nil && len(sh.Creator) > 0 {
				if n, err := idBytes(sh.Creator); err == nil {
					t.Certs += n
					t.NCerts++
				}
			}
		}
		if t.Type == "ENDORSER_TRANSACTION" {
			var tx peer.Transaction
			if err := proto.Unmarshal(pl.Data, &tx); err != nil {
				return nil, nil, err
			}
			for _, a := range tx.Actions {
				var sh common.SignatureHeader
				if err := proto.Unmarshal(a.Header, &sh); err == nil && len(sh.Creator) > 0 {
					if n, err := idBytes(sh.Creator); err == nil {
						t.Certs += n
						t.NCerts++
					}
				}
				var cap peer.ChaincodeActionPayload
				if err := proto.Unmarshal(a.Payload, &cap); err != nil {
					return nil, nil, err
				}
				t.Input += len(cap.ChaincodeProposalPayload)
				if cap.Action != nil {
					t.Response += len(cap.Action.ProposalResponsePayload)
					for _, e := range cap.Action.Endorsements {
						t.Endorsements++
						t.Sigs += len(e.Signature)
						t.NSigs++
						if n, err := idBytes(e.Endorser); err == nil {
							t.Certs += n
							t.NCerts++
						}
					}
				}
			}
		}
		txs = append(txs, t)
	}
	return bb, txs, nil
}

// DumpBlocks reads blocks [from, height) from the session's peer and writes
// blocks.csv.gz and txbytes.csv.gz into dir.
func DumpBlocks(sess *Session, channel string, from uint64, dir string) (int, error) {
	h, err := Height(sess, channel)
	if err != nil {
		return 0, err
	}
	qscc := sess.GW.GetNetwork(channel).GetContract("qscc")
	var brows, trows [][]string
	for n := from; n < h; n++ {
		raw, err := qscc.Evaluate("GetBlockByNumber", client.WithArguments(channel, strconv.FormatUint(n, 10)))
		if err != nil {
			return 0, fmt.Errorf("block %d: %w", n, err)
		}
		bb, txs, err := DecodeBlock(raw)
		if err != nil {
			return 0, err
		}
		brows = append(brows, []string{u64(bb.Number), itoa(bb.Bytes), itoa(bb.DataBytes), itoa(bb.MetadataBytes),
			itoa(bb.OrdererSigs), itoa(bb.NTx), itoa(bb.OrdererSum)})
		for _, t := range txs {
			rest := t.Envelope - t.Certs - t.Sigs - t.Input - t.Response
			trows = append(trows, []string{u64(t.Block), itoa(t.Index), t.TxID, t.Type, itoa(int(t.Code)), itoa(t.Envelope),
				itoa(t.OrdererBytes), itoa(t.Certs), itoa(t.NCerts), itoa(t.Sigs), itoa(t.NSigs), itoa(t.Input),
				itoa(t.Response), itoa(rest), itoa(t.Endorsements)})
		}
	}
	if err := writeCSVGz(dir+"/blocks.csv.gz", []string{"block", "bytes", "data_bytes", "metadata_bytes",
		"orderer_sig_bytes", "ntx", "orderer_sum"}, brows); err != nil {
		return 0, err
	}
	return int(h - from), writeCSVGz(dir+"/txbytes.csv.gz", []string{"block", "index", "txid", "type", "code",
		"envelope", "orderer_bytes", "cert_bytes", "n_certs", "sig_bytes", "n_sigs", "input_bytes", "response_bytes",
		"rest_bytes", "endorsements"}, trows)
}

func u64(v uint64) string { return strconv.FormatUint(v, 10) }
func itoa(v int) string   { return strconv.Itoa(v) }
