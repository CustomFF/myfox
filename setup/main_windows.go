// MyFox-Setup.exe: does what get.ps1 does, without PowerShell. Puts the
// Python MyFox runs on into %LOCALAPPDATA%\myfox\python (the same one, so
// either can follow the other), fetches bootstrap.py and runs it with
// --gui; all the logic lives there. With MyFox installed, it offers its
// update check instead.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	bootstrapURL     = "https://raw.githubusercontent.com/CustomFF/myfox/master/bootstrap.py"
	createNoWindow   = 0x08000000
	userAgent        = "myfox-setup"
	outputKeptBytes  = 8 * 1024
	outputShownBytes = 1500
)

type session struct {
	root   string
	window *progressWindow
	// The installed MyFox's GUI entry, if installed.
	installed string
	client    *http.Client

	mu        sync.Mutex
	child     *exec.Cmd
	temp      string
	err       error
	cancelled bool
}

func main() {
	runtime.LockOSThread()
	lang = uiLanguage()
	if pythonVersion == "" || pythonSHA256 == "" {
		messageBox(0, "Built without the Python version (scripts/build-setup-exe.sh sets it).", "MyFox", mbIconError)
		os.Exit(1)
	}
	if nativeARM64() {
		messageBox(0, t("arm")+"\n\n"+psCommand, t("title"), mbIconWarning)
		os.Exit(1)
	}
	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		messageBox(0, t("no_localdata"), t("title"), mbIconError)
		os.Exit(1)
	}
	s := &session{root: filepath.Join(local, "myfox"), client: &http.Client{Transport: &agent{http.DefaultTransport}}}
	// Installed already: what bootstrap.py asks in a terminal.
	if s.installed = s.installedScript(); s.installed != "" {
		if !ask(t("installed")+"\n\n"+t("check_updates"), t("title")) {
			return
		}
	}
	s.window = newProgressWindow()
	s.window.onCancel = s.cancel
	s.window.onFinished = s.report
	go s.run()
	s.window.loop()
	if s.err != nil {
		os.Exit(1)
	}
}

type agent struct{ next http.RoundTripper }

func (a *agent) RoundTrip(r *http.Request) (*http.Response, error) {
	r = r.Clone(r.Context())
	r.Header.Set("User-Agent", userAgent)
	return a.next.RoundTrip(r)
}

// cancel, on the window's thread: whatever runs stops, and this exits.
func (s *session) cancel() {
	s.mu.Lock()
	s.cancelled = true
	child, temp := s.child, s.temp
	s.mu.Unlock()
	if child != nil && child.Process != nil {
		killTree(uint32(child.Process.Pid))
	}
	if temp != "" {
		os.Remove(temp)
	}
	os.Exit(1)
}

// report, on the window's thread before it closes.
func (s *session) report() {
	if s.err == nil {
		return
	}
	text := t("failed") + "\n\n" + s.err.Error()
	if errors.Is(s.err, errChecksum) {
		text = t("checksum")
	}
	messageBox(0, text+"\n\n"+t("try_command")+"\n"+psCommand, t("title"), mbIconError)
}

func (s *session) run() {
	defer s.window.finish()
	cmd, err := s.command()
	if err != nil {
		s.err = err
		return
	}
	output := &tail{}
	cmd.Stdout, cmd.Stderr = output, output
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: createNoWindow}
	// The installer's window comes up in front, as this one did.
	pAllowSetForegroundWindow.Call(asfwAny)
	s.mu.Lock()
	if s.cancelled {
		s.mu.Unlock()
		return
	}
	err = cmd.Start()
	s.child = cmd
	s.mu.Unlock()
	if err != nil {
		s.err = err
		return
	}

	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	shown := false
	ticker := time.NewTicker(300 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case err = <-done:
			if s.temp != "" {
				os.Remove(s.temp)
			}
			// Once its window was up, the installer said what happened there.
			if !shown && err != nil {
				s.err = fmt.Errorf("%s", output.last(outputShownBytes))
				if output.empty() {
					s.err = err
				}
			}
			return
		case <-ticker.C:
			if !shown && hasWindow(descendants(uint32(cmd.Process.Pid))) {
				shown = true
				s.window.ready()
			}
		}
	}
}

// command: what to run, the Python fetched first where needed.
func (s *session) command() (*exec.Cmd, error) {
	python := filepath.Join(s.root, "python", "python.exe")
	env := append(os.Environ(), "PYTHONUTF8=1")
	if s.installed != "" {
		s.window.set(t("starting"), -1)
		cmd := exec.Command(python, s.installed, "refresh", "--gui")
		cmd.Env = env
		return cmd, nil
	}

	if !pythonReady(filepath.Dir(python)) {
		s.window.set(t("preparing"), 0)
		err := installPython(s.client, s.root, func(fraction float64) {
			if fraction < 0 {
				s.window.set(t("preparing"), -1)
			} else {
				s.window.set(fmt.Sprintf(t("preparing_pct"), int(fraction*100)), fraction)
			}
		})
		if err != nil {
			return nil, err
		}
	}
	s.window.set(t("starting"), -1)

	// Windows fetches a root certificate the first time its own checks need
	// it, and Python sees only those already fetched: have it check GitHub's.
	if resp, err := s.client.Head("https://github.com"); err == nil {
		resp.Body.Close()
	}
	script, err := s.fetchBootstrap()
	if err != nil {
		return nil, err
	}
	cmd := exec.Command(python, script, "--gui")
	cmd.Env = env
	return cmd, nil
}

// installedScript: the installed MyFox's GUI entry (bin\myfoxw.pyw), if
// it is installed, as bootstrap.py tells.
func (s *session) installedScript() string {
	data, err := os.ReadFile(filepath.Join(s.root, "state", "state.json"))
	if err != nil {
		return ""
	}
	var state struct {
		InstallDir string `json:"install_dir"`
	}
	if json.Unmarshal(data, &state) != nil || state.InstallDir == "" {
		return ""
	}
	script := filepath.Join(s.root, "bin", "myfoxw.pyw")
	for _, path := range []string{script, filepath.Join(s.root, "python", "python.exe")} {
		if _, err := os.Stat(path); err != nil {
			return ""
		}
	}
	return script
}

var remote = regexp.MustCompile(`^[a-z]+://`)

func (s *session) fetchBootstrap() (string, error) {
	url := os.Getenv("MYFOX_BOOTSTRAP_URL")
	if url == "" {
		url = bootstrapURL
	}
	file, err := os.CreateTemp("", "myfox-bootstrap-*.py")
	if err != nil {
		return "", err
	}
	s.mu.Lock()
	s.temp = file.Name()
	s.mu.Unlock()
	defer file.Close()
	var in io.ReadCloser
	if remote.MatchString(url) {
		resp, err := s.client.Get(url)
		if err != nil {
			return "", err
		}
		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			return "", fmt.Errorf("%s: %s", url, resp.Status)
		}
		in = resp.Body
	} else if in, err = os.Open(url); err != nil {
		return "", err
	}
	defer in.Close()
	if _, err := io.Copy(file, in); err != nil {
		return "", err
	}
	return file.Name(), file.Close()
}

// tail keeps the end of what the installer printed, for an error message.
type tail struct {
	mu   sync.Mutex
	data []byte
}

func (b *tail) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.data = append(b.data, p...)
	if len(b.data) > outputKeptBytes {
		b.data = b.data[len(b.data)-outputKeptBytes:]
	}
	return len(p), nil
}

func (b *tail) empty() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(strings.TrimSpace(string(b.data))) == 0
}

func (b *tail) last(n int) string {
	b.mu.Lock()
	defer b.mu.Unlock()
	text := strings.ToValidUTF8(strings.TrimSpace(strings.ReplaceAll(string(b.data), "\r\n", "\n")), "")
	if len(text) > n {
		text = "…" + strings.ToValidUTF8(text[len(text)-n:], "")
	}
	return text
}
