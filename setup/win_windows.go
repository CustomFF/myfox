package main

import (
	"syscall"
	"unsafe"
)

var (
	user32   = syscall.NewLazyDLL("user32.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	gdi32    = syscall.NewLazyDLL("gdi32.dll")
	comctl32 = syscall.NewLazyDLL("comctl32.dll")

	pAllowSetForegroundWindow = user32.NewProc("AllowSetForegroundWindow")
	pCreateWindowExW          = user32.NewProc("CreateWindowExW")
	pDefWindowProcW           = user32.NewProc("DefWindowProcW")
	pDestroyWindow            = user32.NewProc("DestroyWindow")
	pDispatchMessageW         = user32.NewProc("DispatchMessageW")
	pEnableWindow             = user32.NewProc("EnableWindow")
	pEnumWindows              = user32.NewProc("EnumWindows")
	pGetDpiForSystem          = user32.NewProc("GetDpiForSystem")
	pGetMessageW              = user32.NewProc("GetMessageW")
	pGetSystemMetrics         = user32.NewProc("GetSystemMetrics")
	pGetWindowRect            = user32.NewProc("GetWindowRect")
	pGetWindowThreadProcessId = user32.NewProc("GetWindowThreadProcessId")
	pIsDialogMessageW         = user32.NewProc("IsDialogMessageW")
	pIsWindowVisible          = user32.NewProc("IsWindowVisible")
	pLoadCursorW              = user32.NewProc("LoadCursorW")
	pLoadImageW               = user32.NewProc("LoadImageW")
	pMessageBoxW              = user32.NewProc("MessageBoxW")
	pPostMessageW             = user32.NewProc("PostMessageW")
	pPostQuitMessage          = user32.NewProc("PostQuitMessage")
	pRegisterClassExW         = user32.NewProc("RegisterClassExW")
	pSendMessageW             = user32.NewProc("SendMessageW")
	pSetWindowLongPtrW        = user32.NewProc("SetWindowLongPtrW")
	pGetWindowLongPtrW        = user32.NewProc("GetWindowLongPtrW")
	pSetWindowTextW           = user32.NewProc("SetWindowTextW")
	pShowWindow               = user32.NewProc("ShowWindow")
	pSystemParametersInfoW    = user32.NewProc("SystemParametersInfoW")
	pTranslateMessage         = user32.NewProc("TranslateMessage")

	pCreateToolhelp32Snapshot = kernel32.NewProc("CreateToolhelp32Snapshot")
	pGetModuleHandleW         = kernel32.NewProc("GetModuleHandleW")
	pGetUserDefaultUILanguage = kernel32.NewProc("GetUserDefaultUILanguage")
	pIsWow64Process2          = kernel32.NewProc("IsWow64Process2")
	pProcess32FirstW          = kernel32.NewProc("Process32FirstW")
	pProcess32NextW           = kernel32.NewProc("Process32NextW")

	pCreateFontIndirectW = gdi32.NewProc("CreateFontIndirectW")

	pInitCommonControlsEx = comctl32.NewProc("InitCommonControlsEx")
)

// GWL_STYLE (-16) as the argument it is.
var gwlStyle = ^uintptr(15)

const (
	wmDestroy  = 0x0002
	wmClose    = 0x0010
	wmSetFont  = 0x0030
	wmCommand  = 0x0111
	wmApp      = 0x8000
	wmUpdate   = wmApp + 1
	wmReady    = wmApp + 2
	wmFinished = wmApp + 3

	wsOverlapped  = 0x00000000
	wsCaption     = 0x00C00000
	wsSysMenu     = 0x00080000
	wsMinimizeBox = 0x00020000
	wsChild       = 0x40000000
	wsVisible     = 0x10000000
	wsTabStop     = 0x00010000
	wsExDlgModal  = 0x00000001

	bsDefPushButton = 0x00000001
	pbsMarquee      = 0x08
	pbmSetPos       = 0x0400 + 2
	pbmSetRange32   = 0x0400 + 6
	pbmSetMarquee   = 0x0400 + 10

	swHide = 0
	swShow = 5

	idCancel = 2

	mbOK           = 0x00000000
	mbIconError    = 0x00000010
	mbIconWarning  = 0x00000030
	mbYesNo        = 0x00000004
	mbIconQuestion = 0x00000020
	idYes          = 6

	imageIcon     = 1
	lrDefaultSize = 0x00000040
	idcArrow      = 32512
	colorBtnFace  = 15

	smCxScreen = 0
	smCyScreen = 1

	spiGetNonClientMetrics = 0x0029

	th32csSnapProcess = 0x00000002
	asfwAny           = 0xFFFFFFFF

	imageFileMachineARM64 = 0xAA64
)

type wndClassEx struct {
	Size       uint32
	Style      uint32
	WndProc    uintptr
	ClsExtra   int32
	WndExtra   int32
	Instance   uintptr
	Icon       uintptr
	Cursor     uintptr
	Background uintptr
	MenuName   *uint16
	ClassName  *uint16
	IconSm     uintptr
}

type msg struct {
	Hwnd    uintptr
	Message uint32
	WParam  uintptr
	LParam  uintptr
	Time    uint32
	Pt      struct{ X, Y int32 }
	Private uint32
}

type rect struct{ Left, Top, Right, Bottom int32 }

type logFont struct {
	Height, Width, Escapement, Orientation, Weight       int32
	Italic, Underline, StrikeOut, CharSet                byte
	OutPrecision, ClipPrecision, Quality, PitchAndFamily byte
	FaceName                                             [32]uint16
}

type nonClientMetrics struct {
	Size                                   uint32
	BorderWidth, ScrollWidth, ScrollHeight int32
	CaptionWidth, CaptionHeight            int32
	CaptionFont                            logFont
	SmCaptionWidth, SmCaptionHeight        int32
	SmCaptionFont                          logFont
	MenuWidth, MenuHeight                  int32
	MenuFont, StatusFont, MessageFont      logFont
	PaddedBorderWidth                      int32
}

type processEntry32 struct {
	Size            uint32
	Usage           uint32
	ProcessID       uint32
	DefaultHeapID   uintptr
	ModuleID        uint32
	Threads         uint32
	ParentProcessID uint32
	PriClassBase    int32
	Flags           uint32
	ExeFile         [260]uint16
}

func utf16(s string) *uint16 {
	p, _ := syscall.UTF16PtrFromString(s)
	return p
}

func messageBox(owner uintptr, text, title string, flags uintptr) {
	pMessageBoxW.Call(owner, uintptr(unsafe.Pointer(utf16(text))), uintptr(unsafe.Pointer(utf16(title))), flags)
}

// ask: Yes or No, Yes first.
func ask(text, title string) bool {
	r, _, _ := pMessageBoxW.Call(0, uintptr(unsafe.Pointer(utf16(text))), uintptr(unsafe.Pointer(utf16(title))), mbYesNo|mbIconQuestion)
	return r == idYes
}

func uiLanguage() string {
	id, _, _ := pGetUserDefaultUILanguage.Call()
	// The primary language: LANG_RUSSIAN.
	if id&0x3FF == 0x19 {
		return "ru"
	}
	return "en"
}

// nativeARM64: this x64 program runs emulated on ARM64 Windows.
func nativeARM64() bool {
	if pIsWow64Process2.Find() != nil {
		return false
	}
	var process, native uint16
	current, _ := syscall.GetCurrentProcess()
	r, _, _ := pIsWow64Process2.Call(uintptr(current), uintptr(unsafe.Pointer(&process)), uintptr(unsafe.Pointer(&native)))
	return r != 0 && native == imageFileMachineARM64
}

// descendants: the processes started, directly or not, by root.
func descendants(root uint32) map[uint32]bool {
	tree := map[uint32]bool{root: true}
	snap, _, _ := pCreateToolhelp32Snapshot.Call(th32csSnapProcess, 0)
	if snap == uintptr(syscall.InvalidHandle) {
		return tree
	}
	defer syscall.CloseHandle(syscall.Handle(snap))
	parents := map[uint32]uint32{}
	entry := processEntry32{Size: uint32(unsafe.Sizeof(processEntry32{}))}
	for r, _, _ := pProcess32FirstW.Call(snap, uintptr(unsafe.Pointer(&entry))); r != 0; r, _, _ = pProcess32NextW.Call(snap, uintptr(unsafe.Pointer(&entry))) {
		parents[entry.ProcessID] = entry.ParentProcessID
	}
	for grew := true; grew; {
		grew = false
		for pid, parent := range parents {
			if tree[parent] && !tree[pid] && pid != parent {
				tree[pid], grew = true, true
			}
		}
	}
	return tree
}

// killTree ends root and what it started.
func killTree(root uint32) {
	for pid := range descendants(root) {
		if h, err := syscall.OpenProcess(syscall.PROCESS_TERMINATE, false, pid); err == nil {
			syscall.TerminateProcess(h, 1)
			syscall.CloseHandle(h)
		}
	}
}

var (
	enumPids   map[uint32]bool
	enumFound  bool
	enumWindow = syscall.NewCallback(func(hwnd, _ uintptr) uintptr {
		if visible, _, _ := pIsWindowVisible.Call(hwnd); visible == 0 {
			return 1
		}
		var pid uint32
		pGetWindowThreadProcessId.Call(hwnd, uintptr(unsafe.Pointer(&pid)))
		if !enumPids[pid] {
			return 1
		}
		// Not the 1x1 window gui_deps opens to see whether a window works.
		var r rect
		pGetWindowRect.Call(hwnd, uintptr(unsafe.Pointer(&r)))
		if r.Right-r.Left < 100 || r.Bottom-r.Top < 100 {
			return 1
		}
		enumFound = true
		return 0
	})
)

// hasWindow: one of these processes shows a window of its own. Called
// from one goroutine only.
func hasWindow(pids map[uint32]bool) bool {
	enumPids, enumFound = pids, false
	pEnumWindows.Call(enumWindow, 0)
	return enumFound
}
