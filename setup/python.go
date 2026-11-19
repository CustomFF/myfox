package main

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// Set at build time from get.ps1 (scripts/build-setup-exe.sh): the one
// place they are kept.
var (
	pythonVersion string
	pythonSHA256  string
)

const pythonArch = "amd64"

var errChecksum = errors.New("checksum mismatch")

func pythonURL() string {
	return fmt.Sprintf("https://www.python.org/ftp/python/%[1]s/python-%[1]s-embed-%[2]s.zip", pythonVersion, pythonArch)
}

// What get.ps1 writes into its marker (Set-Content: a CRLF after it).
func markerText() string {
	return pythonVersion + "-" + pythonArch
}

// pythonReady: the Python get.ps1 would reuse.
func pythonReady(dir string) bool {
	data, err := os.ReadFile(filepath.Join(dir, ".myfox-python"))
	if err != nil {
		return false
	}
	if _, err := os.Stat(filepath.Join(dir, "python.exe")); err != nil {
		return false
	}
	return strings.TrimSpace(string(data)) == markerText()
}

// download writes url into dest, verifying its sha256; progress gets the
// fraction done (or -1 while the size is unknown).
func download(client *http.Client, url, dest, sum string, progress func(float64)) error {
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s: %s", url, resp.Status)
	}
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()
	hash := sha256.New()
	var done int64
	buf := make([]byte, 64*1024)
	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			if _, werr := out.Write(buf[:n]); werr != nil {
				return werr
			}
			hash.Write(buf[:n])
			done += int64(n)
			if resp.ContentLength > 0 {
				progress(float64(done) / float64(resp.ContentLength))
			} else {
				progress(-1)
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
	}
	if sum != "" && !strings.EqualFold(hex.EncodeToString(hash.Sum(nil)), sum) {
		return errChecksum
	}
	return out.Close()
}

// unpackPython does what get.ps1 does with the archive: unpacks it into
// dir, drops its ._pth (so the Python reads PYTHONPATH, as MyFox's
// launcher needs) and marks it.
func unpackPython(archive, dir string) error {
	r, err := zip.OpenReader(archive)
	if err != nil {
		return err
	}
	defer r.Close()
	for _, f := range r.File {
		name := filepath.FromSlash(f.Name)
		if !filepath.IsLocal(name) {
			return fmt.Errorf("unsafe path in the archive: %s", f.Name)
		}
		if strings.HasSuffix(strings.ToLower(name), "._pth") {
			continue
		}
		path := filepath.Join(dir, name)
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(path, 0o755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return err
		}
		if err := extract(f, path); err != nil {
			return err
		}
	}
	return os.WriteFile(filepath.Join(dir, ".myfox-python"), []byte(markerText()+"\r\n"), 0o644)
}

func extract(f *zip.File, path string) error {
	in, err := f.Open()
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(path)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

// installPython puts the Python into root\python, through a sibling
// directory (a rename doesn't cross drives, as TEMP may).
func installPython(client *http.Client, root string, progress func(float64)) error {
	if err := os.MkdirAll(root, 0o755); err != nil {
		return err
	}
	// Left by a run that was cancelled.
	if stale, _ := filepath.Glob(filepath.Join(root, ".setup-*")); stale != nil {
		for _, dir := range stale {
			os.RemoveAll(dir)
		}
	}
	tmp, err := os.MkdirTemp(root, ".setup-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(tmp)
	archive := filepath.Join(tmp, "python.zip")
	if err := download(client, pythonURL(), archive, pythonSHA256, progress); err != nil {
		return err
	}
	unpacked := filepath.Join(tmp, "python")
	if err := unpackPython(archive, unpacked); err != nil {
		return err
	}
	python := filepath.Join(root, "python")
	if err := os.RemoveAll(python); err != nil {
		return err
	}
	return os.Rename(unpacked, python)
}
