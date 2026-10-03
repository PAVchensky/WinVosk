"""A native Win32 window with a real EDIT control, used as a typing target.

The caret is placed at offset 0. The text and selection are mirrored to the
file given as argv[1] on a short timer, so a probe can assert on the caret
position. The window title carries the pid and the mirror path is per run, so
several targets can coexist without tainting each other's state.
"""

import ctypes
import os
import sys
from ctypes import wintypes as wt
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PREFIX = "СТРОКАДО"
SUFFIX = "СТРОКАПОСЛЕ"
CLASS_NAME = "WinVoskPasteTarget"
TITLE = f"WinVoskPasteTarget-{os.getpid()}"
MIRROR = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path(__file__).resolve().parent.parent / "tmp" / f"edit_target_{os.getpid()}.txt"
)
MIRROR.parent.mkdir(parents=True, exist_ok=True)

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_BORDER = 0x00800000
ES_MULTILINE = 0x0004
ES_AUTOVSCROLL = 0x0040
CW_USEDEFAULT = 0x80000000
WM_DESTROY = 0x0002
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_TIMER = 0x0113
EM_GETSEL = 0x00B0
EM_SETSEL = 0x00B1
IDC_ARROW = ctypes.cast(ctypes.c_void_p(32512), wt.LPCWSTR)

WPARAM = ctypes.c_ulonglong
LPARAM = ctypes.c_longlong
LRESULT = ctypes.c_longlong

user32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
user32.RegisterClassExW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p,
]
user32.CreateWindowExW.restype = wt.HWND
user32.SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, WPARAM, LPARAM]
user32.SendMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong, ctypes.c_void_p]
user32.SetFocus.argtypes = [wt.HWND]
user32.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPCWSTR]
user32.LoadCursorW.restype = wt.HANDLE
user32.GetMessageW.argtypes = [ctypes.c_void_p, wt.HWND, ctypes.c_uint, ctypes.c_uint]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.c_void_p]
user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
user32.DispatchMessageW.restype = LRESULT
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HINSTANCE

state = {"edit": 0}


class WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, ctypes.c_uint, WPARAM, LPARAM)


def wndproc(hwnd, message, wparam, lparam):
    if message == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    if message == WM_TIMER:
        write_mirror()
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def write_mirror():
    buffer_ = ctypes.create_unicode_buffer(2048)
    user32.SendMessageW(state["edit"], WM_GETTEXT, 2048, ctypes.addressof(buffer_))
    start = ctypes.c_ulong()
    end = ctypes.c_ulong()
    user32.SendMessageW(state["edit"], EM_GETSEL, ctypes.addressof(start), ctypes.addressof(end))
    with open(MIRROR, "w", encoding="utf-8") as handle:
        handle.write(f"{buffer_.value}\n@@SEL@@{start.value},{end.value}")


instance = kernel32.GetModuleHandleW(None)
procedure = WNDPROC(wndproc)
klass = WNDCLASSEX()
klass.cbSize = ctypes.sizeof(WNDCLASSEX)
klass.lpfnWndProc = ctypes.cast(procedure, ctypes.c_void_p).value
klass.hInstance = instance
klass.hCursor = user32.LoadCursorW(None, IDC_ARROW)
klass.lpszClassName = CLASS_NAME
if not user32.RegisterClassExW(ctypes.byref(klass)):
    raise SystemExit(f"RegisterClassEx failed: {ctypes.get_last_error()}")

window = user32.CreateWindowExW(
    0, CLASS_NAME, TITLE, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
    CW_USEDEFAULT, CW_USEDEFAULT, 700, 240, None, None, instance, None,
)
if not window:
    raise SystemExit(f"CreateWindowEx failed: {ctypes.get_last_error()}")

state["edit"] = user32.CreateWindowExW(
    0, "EDIT", "", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_MULTILINE | ES_AUTOVSCROLL,
    10, 10, 660, 160, window, None, instance, None,
)
if not state["edit"]:
    raise SystemExit("EDIT control creation failed")

initial = ctypes.create_unicode_buffer(f"{PREFIX} {SUFFIX}")
user32.SendMessageW(state["edit"], WM_SETTEXT, 0, ctypes.addressof(initial))
user32.SendMessageW(state["edit"], EM_SETSEL, 0, 0)
user32.SetFocus(state["edit"])
user32.SetTimer(window, 1, 80, None)
write_mirror()


print(f"ready hwnd={window} edit={state['edit']} pid={os.getpid()}", flush=True)

message = wt.MSG()
while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
    user32.TranslateMessage(ctypes.byref(message))
    user32.DispatchMessageW(ctypes.byref(message))
