package main

import (
	"sync"
	"syscall"
	"unsafe"
)

// progressWindow: a small window the user watches while Python downloads
// and until the installer's own window shows. Its controls live on the
// thread that made it; other goroutines change it through set().
type progressWindow struct {
	hwnd, label, bar, cancel uintptr
	marquee                  bool
	onCancel                 func()
	onFinished               func()

	mu       sync.Mutex
	text     string
	fraction float64 // < 0: unknown, a marquee
}

var theWindow *progressWindow

var wndProc = syscall.NewCallback(func(hwnd uintptr, message uint32, wParam, lParam uintptr) uintptr {
	w := theWindow
	switch message {
	case wmCommand:
		if wParam&0xFFFF == idCancel {
			w.requestCancel()
		}
		return 0
	case wmClose:
		w.requestCancel()
		return 0
	case wmUpdate:
		w.refresh()
		return 0
	case wmReady:
		pShowWindow.Call(hwnd, swHide)
		return 0
	case wmFinished:
		w.onFinished()
		pDestroyWindow.Call(hwnd)
		return 0
	case wmDestroy:
		pPostQuitMessage.Call(0)
		return 0
	}
	r, _, _ := pDefWindowProcW.Call(hwnd, uintptr(message), wParam, lParam)
	return r
})

func (w *progressWindow) requestCancel() {
	pEnableWindow.Call(w.cancel, 0)
	if w.onCancel != nil {
		w.onCancel()
	}
}

func (w *progressWindow) set(text string, fraction float64) {
	w.mu.Lock()
	w.text, w.fraction = text, fraction
	w.mu.Unlock()
	pPostMessageW.Call(w.hwnd, wmUpdate, 0, 0)
}

func (w *progressWindow) refresh() {
	w.mu.Lock()
	text, fraction := w.text, w.fraction
	w.mu.Unlock()
	pSetWindowTextW.Call(w.label, uintptr(unsafe.Pointer(utf16(text))))
	marquee := fraction < 0
	if marquee != w.marquee {
		style, _, _ := pGetWindowLongPtrW.Call(w.bar, gwlStyle)
		if marquee {
			style |= pbsMarquee
		} else {
			style &^= pbsMarquee
		}
		pSetWindowLongPtrW.Call(w.bar, gwlStyle, style)
		on := uintptr(0)
		if marquee {
			on = 1
		}
		pSendMessageW.Call(w.bar, pbmSetMarquee, on, 30)
		w.marquee = marquee
	}
	if !marquee {
		pSendMessageW.Call(w.bar, pbmSetPos, uintptr(fraction*1000), 0)
	}
}

// ready hides the window: the installer's own one is up.
func (w *progressWindow) ready() { pPostMessageW.Call(w.hwnd, wmReady, 0, 0) }

// finish closes it, running onFinished on its thread first.
func (w *progressWindow) finish() { pPostMessageW.Call(w.hwnd, wmFinished, 0, 0) }

func scale(dpi uintptr, n int32) int32 { return int32(int64(n) * int64(dpi) / 96) }

// newProgressWindow: on the calling (locked) thread, which then runs loop().
func newProgressWindow() *progressWindow {
	w := &progressWindow{text: t("python"), fraction: -1}
	theWindow = w

	icc := struct{ Size, ICC uint32 }{8, 0x00000020 /* ICC_PROGRESS_CLASS */}
	pInitCommonControlsEx.Call(uintptr(unsafe.Pointer(&icc)))

	instance, _, _ := pGetModuleHandleW.Call(0)
	icon, _, _ := pLoadImageW.Call(instance, 1, imageIcon, 0, 0, lrDefaultSize)
	cursor, _, _ := pLoadCursorW.Call(0, idcArrow)
	class := utf16("MyFoxSetup")
	pRegisterClassExW.Call(uintptr(unsafe.Pointer(&wndClassEx{
		Size: uint32(unsafe.Sizeof(wndClassEx{})), WndProc: wndProc, Instance: instance,
		Icon: icon, Cursor: cursor, Background: colorBtnFace + 1, ClassName: class, IconSm: icon,
	})))

	dpi := uintptr(96)
	if pGetDpiForSystem.Find() == nil {
		dpi, _, _ = pGetDpiForSystem.Call()
	}
	// The client area, its margin and rows.
	width, margin, row := scale(dpi, 400), scale(dpi, 14), scale(dpi, 24)
	height := margin + row + scale(dpi, 8) + scale(dpi, 18) + scale(dpi, 14) + row + margin
	// The frame around it, roughly; exact sizes don't matter here.
	frameW, frameH := width+scale(dpi, 16), height+scale(dpi, 39)
	screenW, _, _ := pGetSystemMetrics.Call(smCxScreen)
	screenH, _, _ := pGetSystemMetrics.Call(smCyScreen)

	w.hwnd, _, _ = pCreateWindowExW.Call(wsExDlgModal, uintptr(unsafe.Pointer(class)),
		uintptr(unsafe.Pointer(utf16(t("title")))), wsOverlapped|wsCaption|wsSysMenu|wsMinimizeBox,
		(screenW-uintptr(frameW))/2, (screenH-uintptr(frameH))/2, uintptr(frameW), uintptr(frameH), 0, 0, instance, 0)

	child := func(class, text string, style uintptr, x, y, cx, cy int32, id uintptr) uintptr {
		h, _, _ := pCreateWindowExW.Call(0, uintptr(unsafe.Pointer(utf16(class))), uintptr(unsafe.Pointer(utf16(text))),
			wsChild|wsVisible|style, uintptr(x), uintptr(y), uintptr(cx), uintptr(cy), w.hwnd, id, instance, 0)
		return h
	}
	y := margin
	w.label = child("STATIC", w.text, 0, margin, y, width-2*margin, row, 0)
	y += row + scale(dpi, 8)
	w.bar = child("msctls_progress32", "", 0, margin, y, width-2*margin, scale(dpi, 18), 0)
	pSendMessageW.Call(w.bar, pbmSetRange32, 0, 1000)
	y += scale(dpi, 18) + scale(dpi, 14)
	buttonW := scale(dpi, 88)
	w.cancel = child("BUTTON", t("cancel"), wsTabStop|bsDefPushButton, width-margin-buttonW, y, buttonW, row, idCancel)

	// The system's message font, not the bitmap one controls start with.
	metrics := nonClientMetrics{Size: uint32(unsafe.Sizeof(nonClientMetrics{}))}
	if r, _, _ := pSystemParametersInfoW.Call(spiGetNonClientMetrics, uintptr(metrics.Size), uintptr(unsafe.Pointer(&metrics)), 0); r != 0 {
		font, _, _ := pCreateFontIndirectW.Call(uintptr(unsafe.Pointer(&metrics.MessageFont)))
		for _, h := range []uintptr{w.label, w.cancel} {
			pSendMessageW.Call(h, wmSetFont, font, 1)
		}
	}
	w.refresh()
	pShowWindow.Call(w.hwnd, swShow)
	return w
}

func (w *progressWindow) loop() {
	var m msg
	for {
		r, _, _ := pGetMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if int32(r) <= 0 {
			return
		}
		if handled, _, _ := pIsDialogMessageW.Call(w.hwnd, uintptr(unsafe.Pointer(&m))); handled != 0 {
			continue
		}
		pTranslateMessage.Call(uintptr(unsafe.Pointer(&m)))
		pDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
	}
}
