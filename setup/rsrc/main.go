// Command rsrc writes the .syso the Go linker takes MyFox-Setup.exe's
// Windows resources from: its icon, manifest and version information.
//
//	go run ./rsrc -icon icon.ico -version 1.6.0 -o rsrc_windows_amd64.syso
package main

import (
	"bytes"
	"encoding/binary"
	"flag"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
)

const (
	rtIcon      = 3
	rtGroupIcon = 14
	rtVersion   = 16
	rtManifest  = 24
	langEnUS    = 0x0409
)

// asInvoker: Windows would otherwise take a program named "…Setup" for an
// installer that needs administrator rights, and ask for them.
// Common Controls 6: today's look of the progress bar and button.
const manifest = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity type="win32" name="CustomFF.MyFox.Setup" version="%s" processorArchitecture="amd64"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application><supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/></application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings><dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware></windowsSettings>
  </application>
  <dependency><dependentAssembly>
    <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>
  </dependentAssembly></dependency>
</assembly>
`

type resource struct {
	typ, id uint16
	data    []byte
}

func main() {
	icon := flag.String("icon", "", ".ico file")
	version := flag.String("version", "", "MyFox's version, major.minor.patch")
	out := flag.String("o", "rsrc_windows_amd64.syso", "output")
	flag.Parse()
	if err := run(*icon, *version, *out); err != nil {
		fmt.Fprintln(os.Stderr, "rsrc:", err)
		os.Exit(1)
	}
}

func run(iconPath, version, out string) error {
	parts, err := versionParts(version)
	if err != nil {
		return err
	}
	ico, err := os.ReadFile(iconPath)
	if err != nil {
		return err
	}
	icons, group, err := iconResources(ico)
	if err != nil {
		return err
	}
	full := fmt.Sprintf("%d.%d.%d.%d", parts[0], parts[1], parts[2], parts[3])
	resources := append(icons,
		resource{rtGroupIcon, 1, group},
		resource{rtVersion, 1, versionInfo(parts, version)},
		resource{rtManifest, 1, []byte(fmt.Sprintf(manifest, full))},
	)
	return os.WriteFile(out, coff(resources), 0o644)
}

func versionParts(version string) ([4]uint16, error) {
	var parts [4]uint16
	fields := strings.Split(version, ".")
	if len(fields) != 3 {
		return parts, fmt.Errorf("version %q is not major.minor.patch", version)
	}
	for i, field := range fields {
		n, err := strconv.ParseUint(field, 10, 16)
		if err != nil {
			return parts, fmt.Errorf("version %q: %v", version, err)
		}
		parts[i] = uint16(n)
	}
	return parts, nil
}

// iconResources splits an .ico into its images (RT_ICON 1..n) and the
// directory that lists them (RT_GROUP_ICON): the .ico's own, with ids
// in place of file offsets.
func iconResources(ico []byte) ([]resource, []byte, error) {
	if len(ico) < 6 || binary.LittleEndian.Uint16(ico[2:]) != 1 {
		return nil, nil, fmt.Errorf("not an .ico file")
	}
	count := int(binary.LittleEndian.Uint16(ico[4:]))
	var icons []resource
	group := new(bytes.Buffer)
	binary.Write(group, binary.LittleEndian, [3]uint16{0, 1, uint16(count)})
	for i := 0; i < count; i++ {
		entry := 6 + 16*i
		if len(ico) < entry+16 {
			return nil, nil, fmt.Errorf("truncated .ico file")
		}
		size := binary.LittleEndian.Uint32(ico[entry+8:])
		offset := binary.LittleEndian.Uint32(ico[entry+12:])
		if uint64(offset)+uint64(size) > uint64(len(ico)) {
			return nil, nil, fmt.Errorf("truncated .ico file")
		}
		id := uint16(i + 1)
		icons = append(icons, resource{rtIcon, id, ico[offset : offset+size]})
		group.Write(ico[entry : entry+12]) // width … bytes in the image
		binary.Write(group, binary.LittleEndian, id)
	}
	return icons, group.Bytes(), nil
}

func utf16z(s string) []byte {
	buf := new(bytes.Buffer)
	binary.Write(buf, binary.LittleEndian, append(utf16.Encode([]rune(s)), 0))
	return buf.Bytes()
}

func pad4(buf *bytes.Buffer) {
	for buf.Len()%4 != 0 {
		buf.WriteByte(0)
	}
}

// node: one of VS_VERSIONINFO's blocks. text: the value is a string,
// whose length counts in characters.
func node(key string, value []byte, text bool, children ...[]byte) []byte {
	buf := new(bytes.Buffer)
	valueLength := len(value)
	kind := uint16(0)
	if text {
		valueLength, kind = len(value)/2, 1
	}
	binary.Write(buf, binary.LittleEndian, [3]uint16{0, uint16(valueLength), kind})
	buf.Write(utf16z(key))
	pad4(buf)
	buf.Write(value)
	for _, child := range children {
		pad4(buf)
		buf.Write(child)
	}
	data := buf.Bytes()
	binary.LittleEndian.PutUint16(data, uint16(len(data)))
	return data
}

func versionInfo(parts [4]uint16, version string) []byte {
	fixed := new(bytes.Buffer)
	ms, ls := uint32(parts[0])<<16|uint32(parts[1]), uint32(parts[2])<<16|uint32(parts[3])
	binary.Write(fixed, binary.LittleEndian, [13]uint32{
		0xFEEF04BD, 0x00010000, ms, ls, ms, ls,
		0x3F, 0, // flags mask, flags
		0x00040004, // VOS_NT_WINDOWS32
		1,          // VFT_APP
		0, 0, 0,
	})
	values := map[string]string{
		"CompanyName":      "CustomFF",
		"FileDescription":  "MyFox Setup",
		"FileVersion":      version,
		"InternalName":     "MyFox-Setup",
		"LegalCopyright":   "MyFox contributors, MPL-2.0",
		"OriginalFilename": "MyFox-Setup.exe",
		"ProductName":      "MyFox",
		"ProductVersion":   version,
	}
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	var entries [][]byte
	for _, key := range keys {
		entries = append(entries, node(key, utf16z(values[key]), true))
	}
	translation := new(bytes.Buffer)
	binary.Write(translation, binary.LittleEndian, [2]uint16{langEnUS, 1200}) // Unicode
	return node("VS_VERSION_INFO", fixed.Bytes(), false,
		node("StringFileInfo", nil, true, node("040904B0", nil, true, entries...)),
		node("VarFileInfo", nil, true, node("Translation", translation.Bytes(), false)),
	)
}

// coff: an object file with the resources in its .rsrc section, laid out
// as in an image (type, then id, then language directories); the linker
// relocates the data entries' addresses.
func coff(resources []resource) []byte {
	sort.Slice(resources, func(i, j int) bool {
		if resources[i].typ != resources[j].typ {
			return resources[i].typ < resources[j].typ
		}
		return resources[i].id < resources[j].id
	})
	byType := map[uint16][]resource{}
	var types []uint16
	for _, r := range resources {
		if byType[r.typ] == nil {
			types = append(types, r.typ)
		}
		byType[r.typ] = append(byType[r.typ], r)
	}

	// Sizes first: directories, then data entries, then the data.
	const dirSize, entrySize, dataEntrySize = 16, 8, 16
	dirs := dirSize + entrySize*len(types)
	for _, typ := range types {
		// Its directory, and per id an entry there and a language directory.
		dirs += dirSize + (entrySize+dirSize+entrySize)*len(byType[typ])
	}
	dataEntries := dirs
	dataStart := dataEntries + dataEntrySize*len(resources)

	sec := new(bytes.Buffer)
	w := func(v any) { binary.Write(sec, binary.LittleEndian, v) }
	directory := func(ids int) { w([4]uint32{0, 0, 0, uint32(ids) << 16}) }

	// Root: one entry per type.
	directory(len(types))
	next := dirSize + entrySize*len(types)
	typeDirs := map[uint16]int{}
	for _, typ := range types {
		typeDirs[typ] = next
		w([2]uint32{uint32(typ), 0x80000000 | uint32(next)})
		next += dirSize + entrySize*len(byType[typ])
	}
	// Per type: one entry per id, each to a language directory.
	langDirs := next
	index := 0
	for _, typ := range types {
		directory(len(byType[typ]))
		for _, r := range byType[typ] {
			w([2]uint32{uint32(r.id), 0x80000000 | uint32(langDirs+(dirSize+entrySize)*index)})
			index++
		}
	}
	// Per resource: a language directory with its one entry.
	for i := range resources {
		directory(1)
		w([2]uint32{langEnUS, uint32(dataEntries + dataEntrySize*i)})
	}
	var relocations []uint32
	offset := dataStart
	for _, typ := range types {
		for _, r := range byType[typ] {
			relocations = append(relocations, uint32(sec.Len()))
			w([4]uint32{uint32(offset), uint32(len(r.data)), 0, 0})
			offset += (len(r.data) + 7) &^ 7
		}
	}
	for _, typ := range types {
		for _, r := range byType[typ] {
			sec.Write(r.data)
			for sec.Len()%8 != 0 {
				sec.WriteByte(0)
			}
		}
	}

	const fileHeader, sectionHeader, relocationSize = 20, 40, 10
	rawStart := fileHeader + sectionHeader
	relocStart := rawStart + sec.Len()
	symbols := relocStart + relocationSize*len(relocations)

	out := new(bytes.Buffer)
	o := func(v any) { binary.Write(out, binary.LittleEndian, v) }
	o(uint16(0x8664)) // AMD64
	o(uint16(1))      // sections
	o(uint32(0))      // timestamp: reproducible
	o(uint32(symbols))
	o(uint32(1)) // symbols
	o(uint16(0)) // optional header
	o(uint16(0)) // characteristics
	o([8]byte{'.', 'r', 's', 'r', 'c'})
	o([2]uint32{0, 0}) // virtual size, address
	o(uint32(sec.Len()))
	o(uint32(rawStart))
	o(uint32(relocStart))
	o(uint32(0)) // line numbers
	o(uint16(len(relocations)))
	o(uint16(0))
	o(uint32(0x40000040)) // initialized data, readable
	out.Write(sec.Bytes())
	for _, at := range relocations {
		o(at)
		o(uint32(0)) // the section's symbol
		o(uint16(3)) // IMAGE_REL_AMD64_ADDR32NB
	}
	// The section's symbol, then an empty string table.
	o([8]byte{'.', 'r', 's', 'r', 'c'})
	o(uint32(0)) // value
	o(int16(1))  // section
	o(uint16(0)) // type
	o(uint8(3))  // IMAGE_SYM_CLASS_STATIC
	o(uint8(0))  // aux symbols
	o(uint32(4))
	return out.Bytes()
}
