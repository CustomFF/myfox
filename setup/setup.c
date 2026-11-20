/* MyFox-Setup.exe: does what get.ps1 does, without PowerShell. Puts the
 * Python MyFox runs on into %LOCALAPPDATA%\myfox\python (the same one, so
 * either can follow the other), fetches bootstrap.py and runs it with --gui;
 * all the logic lives there. With MyFox installed, it offers its update
 * check instead.
 *
 * Only what Windows has: WinHTTP downloads, BCrypt checks the sum, the
 * tar.exe of Windows 10 1803+ unpacks the zip. PYTHON_VERSION and
 * PYTHON_SHA256 come from get.ps1 (scripts/build-setup-exe.sh). */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <commctrl.h>
#include <tlhelp32.h>
#include <winhttp.h>
#include <stdio.h>
#include <wchar.h>

#ifndef PYTHON_VERSION
#error PYTHON_VERSION is set by scripts/build-setup-exe.sh
#endif
#define WIDE2(s) L##s
#define WIDE(s) WIDE2(s)
#define PY_VERSION WIDE(PYTHON_VERSION)
#define PY_SHA256 PYTHON_SHA256
#define PY_ARCH L"amd64"

#define BOOTSTRAP_URL L"https://raw.githubusercontent.com/CustomFF/myfox/master/bootstrap.py"
/* The PowerShell command the site gives, for where this can't install. */
#define PS_COMMAND L"irm https://raw.githubusercontent.com/CustomFF/myfox/master/get.ps1 | iex"
#define USER_AGENT L"myfox-setup"

#define OUTPUT_KEPT 8192   /* bytes of the installer's output kept */
#define OUTPUT_SHOWN 1500  /* characters of it shown */

#define WM_UPDATE (WM_APP + 1)
#define WM_READY (WM_APP + 2)
#define WM_FINISHED (WM_APP + 3)

/* ─── Messages ──────────────────────────────────────────────────────────── */

enum { T_TITLE, T_PREPARING, T_PREPARING_PCT, T_STARTING, T_CANCEL, T_FAILED, T_CHECKSUM, T_ARM, T_TRY,
       T_NO_LOCALDATA, T_INSTALLED, T_CHECK_UPDATES, T_COUNT };

static const wchar_t *const EN[T_COUNT] = {
    L"MyFox Setup",
    L"Preparing…",
    L"Preparing… %d%%",
    L"Starting the installer…",
    L"Cancel",
    L"MyFox could not be installed.",
    L"A downloaded file is damaged (checksum mismatch).",
    L"This installer is for x64 Windows. On ARM64, install MyFox from PowerShell:",
    L"You can also install MyFox from PowerShell:",
    L"%LOCALAPPDATA% is not set.",
    L"MyFox is already installed.",
    L"Check for updates?",
};

static const wchar_t *const RU[T_COUNT] = {
    L"Установка MyFox",
    L"Подготовка…",
    L"Подготовка… %d%%",
    L"Запуск установщика…",
    L"Отмена",
    L"Не удалось установить MyFox.",
    L"Загруженный файл повреждён (контрольная сумма не совпала).",
    L"Этот установщик для Windows x64. На ARM64 установите MyFox из PowerShell:",
    L"MyFox можно установить и из PowerShell:",
    L"Не задана переменная %LOCALAPPDATA%.",
    L"MyFox уже установлен.",
    L"Проверить обновления?",
};

static const wchar_t *const *texts = EN;
#define T(key) (texts[key])

/* ─── State shared by the window and the worker ─────────────────────────── */

static wchar_t root[MAX_PATH];       /* %LOCALAPPDATA%\myfox */
static wchar_t installed[MAX_PATH];  /* bin\myfoxw.pyw when installed */
static HWND window, label, bar, cancel_button;
static BOOL marquee;

static CRITICAL_SECTION lock;
static wchar_t status_text[128];
static double status_fraction = -1;  /* < 0: unknown, a marquee */
static HANDLE child;                 /* the running installer */
static DWORD child_pid;
static wchar_t temp_script[MAX_PATH];
static BOOL cancelled;
static HANDLE worker;
static HINTERNET current_request;  /* a download, for cancel() to cut */
static wchar_t setup_dir[MAX_PATH]; /* where the Python is unpacked */

static wchar_t error[4096];  /* set by the worker when it failed */
static BOOL checksum_failed;
static BOOL transient;  /* the last fetch() failed in a way worth another try */

static char output[OUTPUT_KEPT];  /* the end of what the installer printed */
static size_t output_len;

static void fail(const wchar_t *format, ...)
{
    va_list args;
    va_start(args, format);
    _vsnwprintf(error, ARRAYSIZE(error) - 1, format, args);
    va_end(args);
}

/* The system's text for an error code (WinHTTP's come from its own DLL). */
static const wchar_t *describe(DWORD code)
{
    static wchar_t text[512];
    DWORD flags = FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS;
    HMODULE from = NULL;
    if (code >= WINHTTP_ERROR_BASE && code <= WINHTTP_ERROR_LAST) {
        from = GetModuleHandleW(L"winhttp.dll");
        flags = FORMAT_MESSAGE_FROM_HMODULE | FORMAT_MESSAGE_IGNORE_INSERTS;
    }
    if (!FormatMessageW(flags, from, code, 0, text, ARRAYSIZE(text), NULL))
        swprintf(text, ARRAYSIZE(text), L"error %lu", code);
    for (size_t n = wcslen(text); n && (text[n - 1] == L'\r' || text[n - 1] == L'\n' || text[n - 1] == L' '); n--)
        text[n - 1] = 0;
    return text;
}

/* ─── Small file helpers ────────────────────────────────────────────────── */

static BOOL exists(const wchar_t *path)
{
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

static void join(wchar_t *out, const wchar_t *dir, const wchar_t *name)
{
    swprintf(out, MAX_PATH, L"%ls\\%ls", dir, name);
}

/* Reads a small file whole (NUL-terminated); NULL if it can't. */
static char *read_file(const wchar_t *path, DWORD limit)
{
    HANDLE f = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE)
        return NULL;
    char *data = HeapAlloc(GetProcessHeap(), 0, limit + 1);
    DWORD got = 0;
    if (!data || !ReadFile(f, data, limit, &got, NULL)) {
        CloseHandle(f);
        if (data)
            HeapFree(GetProcessHeap(), 0, data);
        return NULL;
    }
    CloseHandle(f);
    data[got] = 0;
    return data;
}

static void delete_tree(const wchar_t *path)
{
    wchar_t pattern[MAX_PATH], child_path[MAX_PATH];
    WIN32_FIND_DATAW found;
    join(pattern, path, L"*");
    HANDLE h = FindFirstFileW(pattern, &found);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!wcscmp(found.cFileName, L".") || !wcscmp(found.cFileName, L".."))
                continue;
            join(child_path, path, found.cFileName);
            if ((found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) &&
                !(found.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
                delete_tree(child_path);
            } else {
                SetFileAttributesW(child_path, FILE_ATTRIBUTE_NORMAL);
                DeleteFileW(child_path);
            }
        } while (FindNextFileW(h, &found));
        FindClose(h);
    }
    RemoveDirectoryW(path);
}

/* ─── The progress window ───────────────────────────────────────────────── */

static void set_status(const wchar_t *text, double fraction)
{
    EnterCriticalSection(&lock);
    wcsncpy(status_text, text, ARRAYSIZE(status_text) - 1);
    status_fraction = fraction;
    LeaveCriticalSection(&lock);
    PostMessageW(window, WM_UPDATE, 0, 0);
}

static void refresh_status(void)
{
    wchar_t text[ARRAYSIZE(status_text)];
    EnterCriticalSection(&lock);
    wcscpy(text, status_text);
    double fraction = status_fraction;
    LeaveCriticalSection(&lock);
    SetWindowTextW(label, text);
    BOOL want = fraction < 0;
    if (want != marquee) {
        LONG_PTR style = GetWindowLongPtrW(bar, GWL_STYLE);
        SetWindowLongPtrW(bar, GWL_STYLE, want ? style | PBS_MARQUEE : style & ~PBS_MARQUEE);
        SendMessageW(bar, PBM_SETMARQUEE, want, 30);
        marquee = want;
    }
    if (!want)
        SendMessageW(bar, PBM_SETPOS, (WPARAM)(fraction * 1000), 0);
}

static void kill_tree(DWORD root_pid);

/* On the window's thread: whatever runs stops, nothing half-done stays,
 * and this exits. */
static void cancel(void)
{
    EnableWindow(cancel_button, FALSE);
    ShowWindow(window, SW_HIDE);
    EnterCriticalSection(&lock);
    cancelled = TRUE;
    DWORD pid = child ? child_pid : 0;
    /* Closing it ends a read waiting on the network. */
    if (current_request)
        WinHttpCloseHandle(current_request);
    current_request = NULL;
    LeaveCriticalSection(&lock);
    if (pid)
        kill_tree(pid);
    /* The worker stops at its next step and lets go of its files. */
    WaitForSingleObject(worker, 10000);
    if (temp_script[0])
        DeleteFileW(temp_script);
    if (setup_dir[0])
        delete_tree(setup_dir);
    RemoveDirectoryW(root);  /* only if this run made it and left it empty */
    ExitProcess(1);
}

/* On the window's thread before it closes. */
static void report(void)
{
    if (!error[0] && !checksum_failed)
        return;
    static wchar_t text[ARRAYSIZE(error) + 512];
    if (checksum_failed)
        swprintf(text, ARRAYSIZE(text), L"%ls\n\n%ls\n%ls", T(T_CHECKSUM), T(T_TRY), PS_COMMAND);
    else
        swprintf(text, ARRAYSIZE(text), L"%ls\n\n%ls\n\n%ls\n%ls", T(T_FAILED), error, T(T_TRY), PS_COMMAND);
    MessageBoxW(NULL, text, T(T_TITLE), MB_OK | MB_ICONERROR);
}

static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam)
{
    switch (message) {
    case WM_COMMAND:
        if (LOWORD(wparam) == IDCANCEL)
            cancel();
        return 0;
    case WM_CLOSE:
        cancel();
        return 0;
    case WM_UPDATE:
        refresh_status();
        return 0;
    case WM_READY:
        ShowWindow(hwnd, SW_HIDE);
        return 0;
    case WM_FINISHED:
        report();
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

static int scaled(UINT dpi, int n)
{
    return MulDiv(n, (int)dpi, 96);
}

static void create_window(HINSTANCE instance)
{
    INITCOMMONCONTROLSEX icc = {.dwSize = sizeof icc, .dwICC = ICC_PROGRESS_CLASS};
    InitCommonControlsEx(&icc);
    HICON icon = LoadIconW(instance, MAKEINTRESOURCEW(1));
    WNDCLASSEXW cls = {.cbSize = sizeof cls};
    cls.lpfnWndProc = window_proc;
    cls.hInstance = instance;
    cls.hIcon = cls.hIconSm = icon;
    cls.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    cls.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    cls.lpszClassName = L"MyFoxSetup";
    RegisterClassExW(&cls);

    UINT dpi = 96;
    UINT(WINAPI * dpi_for_system)(void) = (void *)GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForSystem");
    if (dpi_for_system)
        dpi = dpi_for_system();
    int width = scaled(dpi, 400), margin = scaled(dpi, 14), row = scaled(dpi, 24), bar_h = scaled(dpi, 18);
    int height = margin + row + scaled(dpi, 8) + bar_h + scaled(dpi, 14) + row + margin;
    DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    RECT frame = {0, 0, width, height};
    AdjustWindowRectEx(&frame, style, FALSE, WS_EX_DLGMODALFRAME);
    int fw = frame.right - frame.left, fh = frame.bottom - frame.top;
    window = CreateWindowExW(WS_EX_DLGMODALFRAME, cls.lpszClassName, T(T_TITLE), style,
                             (GetSystemMetrics(SM_CXSCREEN) - fw) / 2, (GetSystemMetrics(SM_CYSCREEN) - fh) / 2, fw,
                             fh, NULL, NULL, instance, NULL);

    int y = margin;
    label = CreateWindowExW(0, L"STATIC", status_text, WS_CHILD | WS_VISIBLE | SS_LEFT | SS_ENDELLIPSIS, margin, y,
                            width - 2 * margin, row, window, NULL, instance, NULL);
    y += row + scaled(dpi, 8);
    bar = CreateWindowExW(0, PROGRESS_CLASSW, NULL, WS_CHILD | WS_VISIBLE, margin, y, width - 2 * margin, bar_h,
                          window, NULL, instance, NULL);
    SendMessageW(bar, PBM_SETRANGE32, 0, 1000);
    y += bar_h + scaled(dpi, 14);
    int button_w = scaled(dpi, 88);
    cancel_button = CreateWindowExW(0, L"BUTTON", T(T_CANCEL), WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
                                    width - margin - button_w, y, button_w, row, window, (HMENU)IDCANCEL, instance,
                                    NULL);

    /* The system's message font, not the bitmap one controls start with. */
    NONCLIENTMETRICSW metrics = {.cbSize = sizeof metrics};
    if (SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof metrics, &metrics, 0)) {
        HFONT font = CreateFontIndirectW(&metrics.lfMessageFont);
        SendMessageW(label, WM_SETFONT, (WPARAM)font, TRUE);
        SendMessageW(cancel_button, WM_SETFONT, (WPARAM)font, TRUE);
    }
    marquee = FALSE;
    refresh_status();
    ShowWindow(window, SW_SHOW);
}

/* ─── Processes ─────────────────────────────────────────────────────────── */

#define MAX_TREE 256

/* The processes started, directly or not, by root_pid (root_pid first). */
static int descendants(DWORD root_pid, DWORD *tree)
{
    static DWORD pids[4096], parents[4096];
    int n = 0, count = 1;
    tree[0] = root_pid;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE)
        return count;
    PROCESSENTRY32W entry = {.dwSize = sizeof entry};
    for (BOOL ok = Process32FirstW(snap, &entry); ok && n < 4096; ok = Process32NextW(snap, &entry)) {
        pids[n] = entry.th32ProcessID;
        parents[n++] = entry.th32ParentProcessID;
    }
    CloseHandle(snap);
    for (BOOL grew = TRUE; grew;) {
        grew = FALSE;
        for (int i = 0; i < n && count < MAX_TREE; i++) {
            BOOL parent_in = FALSE, in = FALSE;
            for (int j = 0; j < count; j++) {
                parent_in |= tree[j] == parents[i];
                in |= tree[j] == pids[i];
            }
            if (parent_in && !in && pids[i] != parents[i]) {
                tree[count++] = pids[i];
                grew = TRUE;
            }
        }
    }
    return count;
}

static void kill_tree(DWORD root_pid)
{
    DWORD tree[MAX_TREE];
    int count = descendants(root_pid, tree);
    for (int i = 0; i < count; i++) {
        HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, tree[i]);
        if (h) {
            TerminateProcess(h, 1);
            CloseHandle(h);
        }
    }
}

struct window_search {
    DWORD *pids;
    int count;
    BOOL found;
};

static BOOL CALLBACK check_window(HWND hwnd, LPARAM param)
{
    struct window_search *search = (struct window_search *)param;
    if (!IsWindowVisible(hwnd))
        return TRUE;
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    for (int i = 0; i < search->count; i++) {
        if (search->pids[i] != pid)
            continue;
        /* Not the 1x1 window gui_deps opens to see whether a window works. */
        RECT r;
        if (GetWindowRect(hwnd, &r) && r.right - r.left >= 100 && r.bottom - r.top >= 100) {
            search->found = TRUE;
            return FALSE;
        }
    }
    return TRUE;
}

/* Whether the installer, or what it started, shows a window yet. */
static BOOL installer_shown(DWORD pid)
{
    DWORD tree[MAX_TREE];
    struct window_search search = {tree, descendants(pid, tree), FALSE};
    EnumWindows(check_window, (LPARAM)&search);
    return search.found;
}

/* Runs a command line hidden and waits: its exit code, or -1. */
static long run_hidden(wchar_t *command)
{
    STARTUPINFOW si = {.cb = sizeof si};
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, command, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
        return -1;
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (long)code;
}

/* ─── Downloads ─────────────────────────────────────────────────────────── */

typedef void (*progress_fn)(double fraction);

/* Fetches url (GET, or HEAD when out is NULL) into out, hashing what it
 * writes when hash is given. FALSE with `error` set on failure. */
static BOOL fetch(const wchar_t *url, HANDLE out, BCRYPT_HASH_HANDLE hash, progress_fn progress)
{
    transient = FALSE;
    wchar_t host[256], path[2048];
    URL_COMPONENTS parts = {.dwStructSize = sizeof parts};
    parts.lpszHostName = host;
    parts.dwHostNameLength = ARRAYSIZE(host);
    parts.lpszUrlPath = path;
    parts.dwUrlPathLength = ARRAYSIZE(path);
    if (!WinHttpCrackUrl(url, 0, 0, &parts)) {
        fail(L"%ls: %ls", url, describe(GetLastError()));
        return FALSE;
    }
    BOOL ok = FALSE;
    HINTERNET session = NULL, connection = NULL, request = NULL;
    session = WinHttpOpen(USER_AGENT, WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY, WINHTTP_NO_PROXY_NAME,
                          WINHTTP_NO_PROXY_BYPASS, 0);
    if (!session)
        session = WinHttpOpen(USER_AGENT, WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME,
                              WINHTTP_NO_PROXY_BYPASS, 0);
    if (session)
        connection = WinHttpConnect(session, host, parts.nPort, 0);
    if (connection)
        request = WinHttpOpenRequest(connection, out ? L"GET" : L"HEAD", path, NULL, WINHTTP_NO_REFERER,
                                     WINHTTP_DEFAULT_ACCEPT_TYPES,
                                     parts.nScheme == INTERNET_SCHEME_HTTPS ? WINHTTP_FLAG_SECURE : 0);
    if (request) {
        EnterCriticalSection(&lock);
        if (cancelled) {
            WinHttpCloseHandle(request);
            request = NULL;
        }
        current_request = request;
        LeaveCriticalSection(&lock);
        if (!request)
            goto done;
    }
    if (!request || !WinHttpSendRequest(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
        !WinHttpReceiveResponse(request, NULL)) {
        fail(L"%ls: %ls", url, describe(GetLastError()));
        transient = TRUE;
        goto done;
    }
    DWORD status = 0, size = sizeof status;
    WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX,
                        &status, &size, WINHTTP_NO_HEADER_INDEX);
    if (status != 200) {
        fail(L"%ls: HTTP %lu", url, status);
        transient = status >= 500 || status == 429;
        goto done;
    }
    if (!out) {
        ok = TRUE;
        goto done;
    }
    DWORD length = 0;
    size = sizeof length;
    if (!WinHttpQueryHeaders(request, WINHTTP_QUERY_CONTENT_LENGTH | WINHTTP_QUERY_FLAG_NUMBER,
                             WINHTTP_HEADER_NAME_BY_INDEX, &length, &size, WINHTTP_NO_HEADER_INDEX))
        length = 0;
    static BYTE buffer[64 * 1024];
    unsigned long long done_bytes = 0;
    for (;;) {
        DWORD got = 0, written = 0;
        if (cancelled)
            goto done;
        if (!WinHttpReadData(request, buffer, sizeof buffer, &got)) {
            fail(L"%ls: %ls", url, describe(GetLastError()));
            transient = TRUE;
            goto done;
        }
        if (!got)
            break;
        if (!WriteFile(out, buffer, got, &written, NULL) || written != got) {
            fail(L"%ls", describe(GetLastError()));
            goto done;
        }
        if (hash)
            BCryptHashData(hash, buffer, got, 0);
        done_bytes += got;
        if (progress)
            progress(length ? (double)done_bytes / length : -1);
    }
    ok = TRUE;
done:
    /* Unless cancel() closed it already. */
    EnterCriticalSection(&lock);
    if (request && current_request == request) {
        WinHttpCloseHandle(request);
        current_request = NULL;
    }
    LeaveCriticalSection(&lock);
    if (connection)
        WinHttpCloseHandle(connection);
    if (session)
        WinHttpCloseHandle(session);
    return ok;
}

static BOOL download_once(const wchar_t *url, const wchar_t *dest, const char *sum, progress_fn progress)
{
    BCRYPT_ALG_HANDLE alg = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    BYTE digest[32];
    if (BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, NULL, 0) ||
        BCryptCreateHash(alg, &hash, NULL, 0, NULL, 0, 0)) {
        fail(L"SHA-256 is not available");
        return FALSE;
    }
    HANDLE out = CreateFileW(dest, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    BOOL ok = out != INVALID_HANDLE_VALUE;
    if (!ok)
        fail(L"%ls: %ls", dest, describe(GetLastError()));
    else {
        ok = fetch(url, out, hash, progress);
        CloseHandle(out);
    }
    if (ok && !BCryptFinishHash(hash, digest, sizeof digest, 0)) {
        char hex[65];
        for (int i = 0; i < 32; i++)
            sprintf(hex + 2 * i, "%02x", digest[i]);
        if (_stricmp(hex, sum)) {
            checksum_failed = TRUE;
            ok = FALSE;
        }
    }
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(alg, 0);
    return ok;
}

/* After a failed try: TRUE once the pause before the next one is over,
 * FALSE when there's none left (or the user cancelled). */
static BOOL retry_wait(int *tries)
{
    static const DWORD delays[] = {2000, 5000, 10000};
    if (!transient || *tries >= (int)ARRAYSIZE(delays))
        return FALSE;
    for (DWORD waited = 0; waited < delays[*tries]; waited += 100) {
        if (cancelled)
            return FALSE;
        Sleep(100);
    }
    ++*tries;
    return !cancelled;
}

/* Downloads url into dest, checking its sha256 (lowercase hex); tried
 * again from the start after a dropped connection. */
static BOOL download_checked(const wchar_t *url, const wchar_t *dest, const char *sum, progress_fn progress)
{
    BOOL ok;
    int tries = 0;
    do
        ok = download_once(url, dest, sum, progress);
    while (!ok && retry_wait(&tries));
    return ok;
}

/* ─── Python ────────────────────────────────────────────────────────────── */

/* What get.ps1 writes into its marker (Set-Content: a CRLF after it). */
static void marker_text(wchar_t *out, size_t size)
{
    swprintf(out, size, L"%ls-%ls", PY_VERSION, PY_ARCH);
}

/* The Python get.ps1 would reuse. */
static BOOL python_ready(const wchar_t *dir)
{
    wchar_t path[MAX_PATH], want[64];
    join(path, dir, L"python.exe");
    if (!exists(path))
        return FALSE;
    join(path, dir, L".myfox-python");
    char *data = read_file(path, 256);
    if (!data)
        return FALSE;
    char *end = data + strlen(data);
    while (end > data && (end[-1] == '\r' || end[-1] == '\n' || end[-1] == ' '))
        *--end = 0;
    marker_text(want, ARRAYSIZE(want));
    wchar_t have[64];
    MultiByteToWideChar(CP_UTF8, 0, data, -1, have, ARRAYSIZE(have));
    HeapFree(GetProcessHeap(), 0, data);
    return !wcscmp(have, want);
}

static void python_progress(double fraction)
{
    if (fraction < 0) {
        set_status(T(T_PREPARING), -1);
    } else {
        wchar_t text[ARRAYSIZE(status_text)];
        swprintf(text, ARRAYSIZE(text), T(T_PREPARING_PCT), (int)(fraction * 100));
        set_status(text, fraction);
    }
}

/* Puts the Python into root\python as get.ps1 does: unpacked through a
 * sibling directory (a rename doesn't cross drives, as TEMP may), its ._pth
 * dropped (so it reads PYTHONPATH, as MyFox's launcher needs), marked. */
static BOOL install_python(void)
{
    wchar_t tmp[MAX_PATH], pattern[MAX_PATH], path[MAX_PATH], archive[MAX_PATH], unpacked[MAX_PATH],
        python[MAX_PATH], url[256];
    WIN32_FIND_DATAW found;
    CreateDirectoryW(root, NULL);
    /* Left by a run that was cancelled. */
    join(pattern, root, L".setup-*");
    HANDLE h = FindFirstFileW(pattern, &found);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            join(path, root, found.cFileName);
            delete_tree(path);
        } while (FindNextFileW(h, &found));
        FindClose(h);
    }
    swprintf(tmp, MAX_PATH, L"%ls\\.setup-%lu", root, GetCurrentProcessId());
    wcscpy(setup_dir, tmp);
    if (!CreateDirectoryW(tmp, NULL)) {
        fail(L"%ls: %ls", tmp, describe(GetLastError()));
        return FALSE;
    }
    BOOL ok = FALSE;
    join(archive, tmp, L"python.zip");
    swprintf(url, ARRAYSIZE(url), L"https://www.python.org/ftp/python/%ls/python-%ls-embed-%ls.zip", PY_VERSION,
             PY_VERSION, PY_ARCH);
    if (!download_checked(url, archive, PY_SHA256, python_progress))
        goto done;

    join(unpacked, tmp, L"python");
    CreateDirectoryW(unpacked, NULL);
    wchar_t system[MAX_PATH], command[3 * MAX_PATH];
    GetSystemDirectoryW(system, MAX_PATH);
    swprintf(command, ARRAYSIZE(command), L"\"%ls\\tar.exe\" -xf \"%ls\" -C \"%ls\"", system, archive, unpacked);
    long code = run_hidden(command);
    if (code) {
        fail(code < 0 ? L"tar.exe: %ls" : L"tar.exe could not unpack %ls", code < 0 ? describe(GetLastError()) : url);
        goto done;
    }
    join(pattern, unpacked, L"*._pth");
    h = FindFirstFileW(pattern, &found);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            join(path, unpacked, found.cFileName);
            DeleteFileW(path);
        } while (FindNextFileW(h, &found));
        FindClose(h);
    }
    wchar_t marker[64];
    char text[128];
    marker_text(marker, ARRAYSIZE(marker));
    int n = WideCharToMultiByte(CP_UTF8, 0, marker, -1, text, sizeof text - 2, NULL, NULL);
    strcpy(text + n - 1, "\r\n");
    join(path, unpacked, L".myfox-python");
    HANDLE f = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    DWORD written;
    if (f == INVALID_HANDLE_VALUE || !WriteFile(f, text, (DWORD)strlen(text), &written, NULL)) {
        fail(L"%ls: %ls", path, describe(GetLastError()));
        if (f != INVALID_HANDLE_VALUE)
            CloseHandle(f);
        goto done;
    }
    CloseHandle(f);

    join(python, root, L"python");
    delete_tree(python);
    if (!MoveFileW(unpacked, python)) {
        fail(L"%ls: %ls", python, describe(GetLastError()));
        goto done;
    }
    ok = TRUE;
done:
    delete_tree(tmp);
    return ok;
}

/* ─── The installer ─────────────────────────────────────────────────────── */

/* The installed MyFox's GUI entry (bin\myfoxw.pyw), if it is installed, as
 * bootstrap.py tells: state.json names an install_dir. */
static BOOL find_installed(void)
{
    wchar_t path[MAX_PATH];
    swprintf(path, MAX_PATH, L"%ls\\state\\state.json", root);
    char *state = read_file(path, 1 << 20);
    if (!state)
        return FALSE;
    /* "install_dir": "<something>" – enough of JSON for this. */
    BOOL named = FALSE;
    char *key = strstr(state, "\"install_dir\"");
    if (key) {
        char *p = key + strlen("\"install_dir\"");
        while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')
            p++;
        if (*p == ':') {
            p++;
            while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')
                p++;
            named = p[0] == '"' && p[1] && p[1] != '"';
        }
    }
    HeapFree(GetProcessHeap(), 0, state);
    swprintf(installed, MAX_PATH, L"%ls\\bin\\myfoxw.pyw", root);
    swprintf(path, MAX_PATH, L"%ls\\python\\python.exe", root);
    if (!named || !exists(installed) || !exists(path)) {
        installed[0] = 0;
        return FALSE;
    }
    return TRUE;
}

/* bootstrap.py into a temp file (MYFOX_BOOTSTRAP_URL: a URL or a path). */
static BOOL fetch_bootstrap(void)
{
    wchar_t url[2048], dir[MAX_PATH];
    if (!GetEnvironmentVariableW(L"MYFOX_BOOTSTRAP_URL", url, ARRAYSIZE(url)))
        wcscpy(url, BOOTSTRAP_URL);
    GetTempPathW(MAX_PATH, dir);
    EnterCriticalSection(&lock);
    swprintf(temp_script, MAX_PATH, L"%lsmyfox-bootstrap-%lu.py", dir, GetCurrentProcessId());
    LeaveCriticalSection(&lock);
    if (!wcsstr(url, L"://")) {
        if (CopyFileW(url, temp_script, FALSE))
            return TRUE;
        fail(L"%ls: %ls", url, describe(GetLastError()));
        return FALSE;
    }
    BOOL ok;
    int tries = 0;
    do {
        HANDLE out = CreateFileW(temp_script, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
        if (out == INVALID_HANDLE_VALUE) {
            fail(L"%ls: %ls", temp_script, describe(GetLastError()));
            return FALSE;
        }
        ok = fetch(url, out, NULL, NULL);
        CloseHandle(out);
    } while (!ok && retry_wait(&tries));
    return ok;
}

static DWORD WINAPI read_output(LPVOID pipe)
{
    char chunk[4096];
    DWORD got;
    while (ReadFile((HANDLE)pipe, chunk, sizeof chunk, &got, NULL) && got) {
        EnterCriticalSection(&lock);
        /* chunk is smaller than output: only the oldest bytes go. */
        if (output_len + got > OUTPUT_KEPT) {
            size_t drop = output_len + got - OUTPUT_KEPT;
            memmove(output, output + drop, output_len - drop);
            output_len -= drop;
        }
        memcpy(output + output_len, chunk, got);
        output_len += got;
        LeaveCriticalSection(&lock);
    }
    return 0;
}

/* The end of what the installer printed, for the error message. */
static BOOL output_tail(wchar_t *out, size_t size)
{
    static wchar_t text[OUTPUT_KEPT + 1];
    EnterCriticalSection(&lock);
    int n = MultiByteToWideChar(CP_UTF8, 0, output, (int)output_len, text, OUTPUT_KEPT);
    LeaveCriticalSection(&lock);
    text[n] = 0;
    /* CRLF to LF, then trimmed. */
    wchar_t *w = text;
    for (wchar_t *r = text; *r; r++)
        if (*r != L'\r')
            *w++ = *r;
    *w = 0;
    wchar_t *start = text;
    while (*start == L'\n' || *start == L' ')
        start++;
    while (w > start && (w[-1] == L'\n' || w[-1] == L' '))
        *--w = 0;
    if (!*start)
        return FALSE;
    size_t len = wcslen(start);
    if (len > OUTPUT_SHOWN)
        swprintf(out, size, L"…%ls", start + len - OUTPUT_SHOWN);
    else
        swprintf(out, size, L"%ls", start);
    return TRUE;
}

static DWORD WINAPI work(LPVOID unused)
{
    (void)unused;
    wchar_t python[MAX_PATH], command[4 * MAX_PATH];
    swprintf(python, MAX_PATH, L"%ls\\python\\python.exe", root);
    if (installed[0]) {
        set_status(T(T_STARTING), -1);
        swprintf(command, ARRAYSIZE(command), L"\"%ls\" \"%ls\" refresh --gui", python, installed);
    } else {
        wchar_t dir[MAX_PATH];
        join(dir, root, L"python");
        if (!python_ready(dir)) {
            set_status(T(T_PREPARING), 0);
            if (!install_python())
                goto finished;
        }
        set_status(T(T_STARTING), -1);
        /* Windows fetches a root certificate the first time its own checks
         * need it, and Python sees only those already fetched: have it check
         * GitHub's. */
        fetch(L"https://github.com", NULL, NULL, NULL);
        error[0] = 0;
        if (!fetch_bootstrap())
            goto finished;
        swprintf(command, ARRAYSIZE(command), L"\"%ls\" \"%ls\" --gui", python, temp_script);
    }

    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SECURITY_ATTRIBUTES inherit = {.nLength = sizeof inherit, .bInheritHandle = TRUE};
    HANDLE read_end, write_end;
    if (!CreatePipe(&read_end, &write_end, &inherit, 0)) {
        fail(L"%ls", describe(GetLastError()));
        goto finished;
    }
    SetHandleInformation(read_end, HANDLE_FLAG_INHERIT, 0);
    /* Python leaves sys.stdin None without a handle; MyFox asks it isatty(). */
    HANDLE nul = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &inherit, OPEN_EXISTING, 0, NULL);
    STARTUPINFOW si = {.cb = sizeof si};
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = nul;
    si.hStdOutput = si.hStdError = write_end;
    PROCESS_INFORMATION pi;
    /* The installer's window comes up in front, as this one did. */
    AllowSetForegroundWindow(ASFW_ANY);
    EnterCriticalSection(&lock);
    BOOL started = !cancelled && CreateProcessW(NULL, command, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    DWORD start_error = GetLastError();
    if (started) {
        child = pi.hProcess;
        child_pid = pi.dwProcessId;
    }
    LeaveCriticalSection(&lock);
    CloseHandle(write_end);
    if (nul != INVALID_HANDLE_VALUE)
        CloseHandle(nul);
    if (!started) {
        CloseHandle(read_end);
        if (!cancelled)
            fail(L"%ls: %ls", python, describe(start_error));
        goto finished;
    }
    CloseHandle(pi.hThread);
    HANDLE reader = CreateThread(NULL, 0, read_output, read_end, 0, NULL);

    BOOL shown = FALSE;
    while (WaitForSingleObject(pi.hProcess, 300) == WAIT_TIMEOUT) {
        if (!shown && installer_shown(pi.dwProcessId)) {
            shown = TRUE;
            PostMessageW(window, WM_READY, 0, 0);
        }
    }
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    WaitForSingleObject(reader, 2000);
    CloseHandle(read_end);
    /* Once its window was up, the installer said what happened there. */
    if (!shown && code && !output_tail(error, ARRAYSIZE(error)))
        fail(L"exit code %lu", code);
finished:
    if (temp_script[0])
        DeleteFileW(temp_script);
    PostMessageW(window, WM_FINISHED, 0, 0);
    return 0;
}

/* This x64 program runs emulated on ARM64 Windows. */
static BOOL native_arm64(void)
{
    BOOL(WINAPI * wow64_2)(HANDLE, USHORT *, USHORT *) =
        (void *)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "IsWow64Process2");
    USHORT process = 0, native = 0;
    return wow64_2 && wow64_2(GetCurrentProcess(), &process, &native) && native == IMAGE_FILE_MACHINE_ARM64;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show)
{
    (void)previous, (void)args, (void)show;
    if (PRIMARYLANGID(GetUserDefaultUILanguage()) == LANG_RUSSIAN)
        texts = RU;
    InitializeCriticalSection(&lock);
    if (native_arm64()) {
        wchar_t text[512];
        swprintf(text, ARRAYSIZE(text), L"%ls\n\n%ls", T(T_ARM), PS_COMMAND);
        MessageBoxW(NULL, text, T(T_TITLE), MB_OK | MB_ICONWARNING);
        return 1;
    }
    wchar_t local[MAX_PATH];
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH)) {
        MessageBoxW(NULL, T(T_NO_LOCALDATA), T(T_TITLE), MB_OK | MB_ICONERROR);
        return 1;
    }
    join(root, local, L"myfox");
    /* Installed already: what bootstrap.py asks in a terminal. */
    if (find_installed()) {
        wchar_t text[256];
        swprintf(text, ARRAYSIZE(text), L"%ls\n\n%ls", T(T_INSTALLED), T(T_CHECK_UPDATES));
        if (MessageBoxW(NULL, text, T(T_TITLE), MB_YESNO | MB_ICONQUESTION) != IDYES)
            return 0;
    }
    wcscpy(status_text, T(T_PREPARING));
    create_window(instance);
    worker = CreateThread(NULL, 0, work, NULL, 0, NULL);
    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        if (IsDialogMessageW(window, &msg))
            continue;
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return error[0] || checksum_failed ? 1 : 0;
}
