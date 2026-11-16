package main

// Output files, in the KPI harness's conventions: writes go through a synced
// temporary file that is renamed; tables are gzip-compressed CSV with a header.

import (
	"bytes"
	"compress/gzip"
	"encoding/csv"
	"encoding/json"
	"os"
	"path/filepath"
)

func writeFileAtomic(path string, data []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp := path + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	if _, err := f.Write(data); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return writeFileAtomic(path, append(b, '\n'))
}

func writeCSVGz(path string, header []string, rows [][]string) error {
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	w := csv.NewWriter(gz)
	w.Write(header)
	w.WriteAll(rows)
	w.Flush()
	if err := w.Error(); err != nil {
		return err
	}
	if err := gz.Close(); err != nil {
		return err
	}
	return writeFileAtomic(path, buf.Bytes())
}

func jsonUnmarshal(b []byte, v any) error { return json.Unmarshal(b, v) }
