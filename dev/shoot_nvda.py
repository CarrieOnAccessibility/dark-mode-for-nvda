# Drive the running NVDA with injected keystrokes and screenshot its windows.
#
#   python dev/shoot_nvda.py settings   -> NVDA+Ctrl+G, shoots "NVDA Settings" dialog, Escape
#   python dev/shoot_nvda.py menu       -> NVDA+N, shoots the popup menu, Escape
#   python dev/shoot_nvda.py addons     -> NVDA+N, T, A (Tools > Add-on store), shoots, Escape
#   python dev/shoot_nvda.py keys <vk...>  then shoots the foreground window
#
# NVDA processes injected keys ("Handle keys from other applications" is on by
# default). The NVDA modifier is sent as Insert.

import ctypes
from ctypes import wintypes
import os
import sys
import time

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
NVDA_DIR = r"C:\Program Files\NVDA"
os.add_dll_directory(NVDA_DIR)
sys.path.insert(0, os.path.join(NVDA_DIR, "library.zip"))
sys.path.insert(0, NVDA_DIR)
from PIL import ImageGrab  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots")
os.makedirs(OUT, exist_ok=True)
user32 = ctypes.windll.user32

VK = {"insert": 0x2D, "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "esc": 0x1B, "enter": 0x0D, "tab": 0x09, "down": 0x28, "up": 0x26, "right": 0x27, "left": 0x25, "space": 0x20, "f1": 0x70}


def vk(name):
	if name in VK:
		return VK[name]
	if len(name) == 1:
		return ord(name.upper())
	return int(name, 0)


def press(*names, hold=0.05):
	codes = [vk(n) for n in names]
	for c in codes:
		user32.keybd_event(c, 0, 0, 0)
		time.sleep(0.02)
	time.sleep(hold)
	for c in reversed(codes):
		user32.keybd_event(c, 0, 2, 0)
		time.sleep(0.02)


class RECT(ctypes.Structure):
	_fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


def rectOf(hwnd):
	r = RECT()
	user32.GetWindowRect(hwnd, ctypes.byref(r))
	return r.l, r.t, r.r, r.b


def findWindow(titlePart, cls=None):
	found = []
	EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

	@EnumProc
	def cb(h, _):
		if not user32.IsWindowVisible(h):
			return True
		buf = ctypes.create_unicode_buffer(512)
		user32.GetWindowTextW(h, buf, 512)
		cbuf = ctypes.create_unicode_buffer(256)
		user32.GetClassNameW(h, cbuf, 256)
		if (titlePart is None or titlePart.lower() in buf.value.lower()) and (cls is None or cbuf.value == cls):
			found.append((h, buf.value))
		return True

	user32.EnumWindows(cb, 0)
	return found


def shoot(hwnds, name, pad=8):
	rects = [rectOf(h) for h in hwnds]
	l = min(r[0] for r in rects) - pad
	t = min(r[1] for r in rects) - pad
	rr = max(r[2] for r in rects) + pad
	b = max(r[3] for r in rects) + pad
	img = ImageGrab.grab(bbox=(l, t, rr, b), all_screens=True)
	path = os.path.join(OUT, name)
	img.save(path)
	print("saved", path, img.size)


def waitFor(titlePart, cls=None, timeout=6):
	end = time.time() + timeout
	while time.time() < end:
		w = findWindow(titlePart, cls)
		if w:
			return w
		time.sleep(0.2)
	return []


mode = sys.argv[1] if len(sys.argv) > 1 else "settings"

if mode == "settings":
	press("insert", "ctrl", "g")
	wins = waitFor("NVDA Settings")
	print("windows:", wins)
	time.sleep(1.0)
	if wins:
		shoot([wins[0][0]], "nvda-settings.png")
	press("esc")
elif mode == "menu":
	press("insert", "n")
	time.sleep(0.8)
	popup = user32.FindWindowW("#32768", None)
	print("popup:", popup)
	if popup:
		shoot([popup], "nvda-menu.png", pad=20)
	press("esc")
elif mode == "addons":
	press("insert", "n")
	time.sleep(0.6)
	press("t")
	time.sleep(0.4)
	press("a")
	wins = waitFor("Add-on Store")
	print("windows:", wins)
	time.sleep(2.5)
	if wins:
		shoot([wins[0][0]], "nvda-addon-store.png")
	press("esc")
elif mode == "keys":
	for k in sys.argv[2:]:
		press(*k.split("+"))
		time.sleep(0.5)
	time.sleep(1.0)
	h = user32.GetForegroundWindow()
	buf = ctypes.create_unicode_buffer(512)
	user32.GetWindowTextW(h, buf, 512)
	print("foreground:", h, buf.value)
	shoot([h], "nvda-foreground.png")
