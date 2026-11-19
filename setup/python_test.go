package main

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"regexp"
	"testing"
)

func archive(t *testing.T, files map[string]string) []byte {
	t.Helper()
	path := filepath.Join(t.TempDir(), "a.zip")
	f, _ := os.Create(path)
	z := zip.NewWriter(f)
	for name, content := range files {
		w, err := z.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		w.Write([]byte(content))
	}
	z.Close()
	f.Close()
	data, _ := os.ReadFile(path)
	return data
}

func withPython(t *testing.T, version, sum string) {
	oldVersion, oldSum := pythonVersion, pythonSHA256
	pythonVersion, pythonSHA256 = version, sum
	t.Cleanup(func() { pythonVersion, pythonSHA256 = oldVersion, oldSum })
}

func TestUnpackDropsThePthAndMarksIt(t *testing.T) {
	withPython(t, "3.14.10", "")
	data := archive(t, map[string]string{"python.exe": "exe", "python314._pth": "x", "Lib/os.py": "os"})
	zipPath := filepath.Join(t.TempDir(), "p.zip")
	os.WriteFile(zipPath, data, 0o644)
	dir := filepath.Join(t.TempDir(), "python")
	if err := unpackPython(zipPath, dir); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, "python314._pth")); !os.IsNotExist(err) {
		t.Error("._pth kept")
	}
	if _, err := os.Stat(filepath.Join(dir, "Lib", "os.py")); err != nil {
		t.Error(err)
	}
	if !pythonReady(dir) {
		t.Error("not ready after unpacking")
	}
	pythonVersion = "3.14.11"
	if pythonReady(dir) {
		t.Error("another version taken as ready")
	}
}

func TestUnpackRefusesPathsOutside(t *testing.T) {
	data := archive(t, map[string]string{"../evil.txt": "x"})
	zipPath := filepath.Join(t.TempDir(), "p.zip")
	os.WriteFile(zipPath, data, 0o644)
	if err := unpackPython(zipPath, filepath.Join(t.TempDir(), "python")); err == nil {
		t.Error("accepted")
	}
}

func TestDownloadChecksTheSum(t *testing.T) {
	body := []byte("python")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.Write(body) }))
	defer server.Close()
	sum := sha256.Sum256(body)
	dest := filepath.Join(t.TempDir(), "p.zip")
	var last float64
	if err := download(server.Client(), server.URL, dest, hex.EncodeToString(sum[:]), func(f float64) { last = f }); err != nil {
		t.Fatal(err)
	}
	if last != 1 {
		t.Errorf("progress ended at %v", last)
	}
	err := download(server.Client(), server.URL, dest, hex.EncodeToString(make([]byte, 32)), func(float64) {})
	if !errors.Is(err, errChecksum) {
		t.Errorf("got %v", err)
	}
}

// The values the build reads out of get.ps1 still are there, in that form.
func TestGetPs1StillHasThePython(t *testing.T) {
	data, err := os.ReadFile("../get.ps1")
	if err != nil {
		t.Fatal(err)
	}
	for _, pattern := range []string{`(?m)^ *\$version = '[0-9.]+'$`, `(?m)^ *'amd64' = '[0-9a-f]{64}'$`} {
		if !regexpMatch(pattern, data) {
			t.Errorf("get.ps1 has no line matching %s", pattern)
		}
	}
}

func regexpMatch(pattern string, data []byte) bool {
	return regexp.MustCompile(pattern).Match(data)
}
