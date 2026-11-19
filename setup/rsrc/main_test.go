package main

import (
	"bytes"
	"debug/pe"
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
)

func TestObjectHoldsTheResources(t *testing.T) {
	out := filepath.Join(t.TempDir(), "rsrc.syso")
	if err := run("../../myfox/ui/assets/icon.ico", "1.6.0", out); err != nil {
		t.Fatal(err)
	}
	f, err := pe.Open(out)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	sec := f.Section(".rsrc")
	if sec == nil {
		t.Fatal("no .rsrc section")
	}
	data, err := sec.Data()
	if err != nil {
		t.Fatal(err)
	}
	// The root directory lists ICON, GROUP_ICON, VERSION, MANIFEST, in order.
	if ids := binary.LittleEndian.Uint16(data[14:]); ids != 4 {
		t.Fatalf("%d types", ids)
	}
	var types []uint32
	for i := 0; i < 4; i++ {
		types = append(types, binary.LittleEndian.Uint32(data[16+8*i:]))
	}
	if want := []uint32{rtIcon, rtGroupIcon, rtVersion, rtManifest}; !equal(types, want) {
		t.Fatalf("types %v, want %v", types, want)
	}
	// One relocation per data entry: two icons, the group, version, manifest.
	if n := len(sec.Relocs); n != 5 {
		t.Fatalf("%d relocations", n)
	}
	// Every id leads, through its language directory, to its data.
	le := binary.LittleEndian
	var leaves [][]byte
	var walk func(off uint32)
	walk = func(off uint32) {
		n := uint32(le.Uint16(data[off+12:])) + uint32(le.Uint16(data[off+14:]))
		for i := uint32(0); i < n; i++ {
			to := le.Uint32(data[off+16+8*i+4:])
			if to&0x80000000 != 0 {
				walk(to &^ 0x80000000)
				continue
			}
			// Unrelocated, the address is the offset in the section.
			at, size := le.Uint32(data[to:]), le.Uint32(data[to+4:])
			if int(at+size) > len(data) {
				t.Fatalf("data entry at %d points past the section", to)
			}
			leaves = append(leaves, data[at:at+size])
		}
	}
	walk(0)
	if len(leaves) != 5 {
		t.Fatalf("%d resources", len(leaves))
	}
	if !bytes.HasPrefix(leaves[2], []byte{0, 0, 1, 0, 2, 0}) {
		t.Errorf("group icon starts %x", leaves[2][:6])
	}
	if !bytes.Contains(leaves[3], utf16z("VS_VERSION_INFO")) {
		t.Error("no version information")
	}
	if !bytes.HasPrefix(leaves[4], []byte("<?xml")) {
		t.Error("no manifest")
	}
	for _, text := range []string{"ProductName", "MyFox", "asInvoker"} {
		if !bytes.Contains(data, []byte(text)) && !bytes.Contains(data, utf16z(text)[:2*len(text)]) {
			t.Errorf("%q missing", text)
		}
	}
}

func TestVersionMustBeThreeNumbers(t *testing.T) {
	for _, version := range []string{"1.6", "1.6.0.1", "1.x.0", ""} {
		if _, err := versionParts(version); err == nil {
			t.Errorf("%q accepted", version)
		}
	}
}

func TestNotAnIcon(t *testing.T) {
	path := filepath.Join(t.TempDir(), "x.ico")
	os.WriteFile(path, []byte("not an icon"), 0o644)
	if err := run(path, "1.6.0", filepath.Join(t.TempDir(), "out")); err == nil {
		t.Error("accepted")
	}
}

func equal(a, b []uint32) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
