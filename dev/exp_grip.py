# Experiment: what is the size grip on a resizable wx.Dialog, and what colours does it paint?
#   python dev/exp_grip.py [--theme] [--paint]
import argparse
import ctypes
import os
import sys
import threading
from ctypes import wintypes

try:
	ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
	pass
_wd = threading.Timer(15, lambda: os._exit(3))
_wd.daemon = True
_wd.start()

NVDA_DIR = r"C:\Program Files\NVDA"
HERE = os.path.dirname(os.path.abspath(__file__))
ADDON_PLUGIN_DIR = os.path.join(HERE, "..", "addon", "globalPlugins", "nvdaDarkMode")
os.add_dll_directory(NVDA_DIR)
sys.path.insert(0, os.path.join(NVDA_DIR, "library.zip"))
sys.path.insert(0, NVDA_DIR)
sys.path.insert(0, os.path.abspath(ADDON_PLUGIN_DIR))

import logging  # noqa: E402
logging.basicConfig(level=logging.DEBUG)
import wx  # noqa: E402
import theming  # noqa: E402
import native  # noqa: E402
from PIL import ImageGrab  # noqa: E402
from collections import Counter  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--light", action="store_true")
args = parser.parse_args()

user32 = ctypes.windll.user32
EnumChildProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def children(hwnd):
	out = []

	@EnumChildProc
	def cb(h, _):
		out.append(h)
		return True

	user32.EnumChildWindows(hwnd, cb, 0)
	return out


def className(h):
	buf = ctypes.create_unicode_buffer(64)
	user32.GetClassNameW(h, buf, 64)
	return buf.value


def rect(h):
	r = wintypes.RECT()
	user32.GetWindowRect(h, ctypes.byref(r))
	return r.left, r.top, r.right, r.bottom


_origProc = native._proc
_seen = []
def _traceProc(hwnd, msg, wParam, lParam, idSubclass, refData):
	if idSubclass == native.ID_GRIP:
		_seen.append(msg)
	return _origProc(hwnd, msg, wParam, lParam, idSubclass, refData)
native._subclassProc = native._SUBCLASSPROC(_traceProc)
app = wx.App()
if not args.light:
	theming.setProcessDark(True)
	engine = theming.DarkModeEngine(lambda: True)
	engine.start()

dlg = wx.Dialog(None, title="Grip test", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
dlg.SetSize(dlg.FromDIP(wx.Size(400, 300)))
# NVDA lays controls straight into the dialog (no full-size panel that would cover the grip)
s = wx.BoxSizer(wx.VERTICAL)
s.Add(wx.StaticText(dlg, label="Look at the bottom right corner"), 0, wx.ALL, 12)
s.AddStretchSpacer(1)
s.Add(wx.Button(dlg, label="Apply"), 0, wx.ALL, 4)
dlg.SetSizer(s)
dlg.Show()


def report(tag):
	for h in children(dlg.GetHandle()):
		cls = className(h)
		if cls.lower() == "scrollbar":
			st = user32.GetWindowLongW(h, -16)
			vis = user32.IsWindowVisible(h)
			l, t, r, b = rect(h)
			print(f"[{tag}] grip hwnd={h:#x} class={cls} style={st:#010x} visible={vis} rect={(l, t, r, b)} size={(r - l, b - t)}")
			print("      wx wrapper:", wx.FindWindowById(user32.GetDlgCtrlID(h)) if user32.GetDlgCtrlID(h) else "none (no wx id)")
			img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
			c = Counter(img.getdata()).most_common(4)
			print("      pixel colours:", c)
			img.save(os.path.join(HERE, "shots", f"grip-{tag}.png"))


def step1():
	report("light" if args.light else "dark")
	print("sizeGrips:", native.sizeGrips(dlg.GetHandle()), "subclassed:", {hex(k): v for k, v in native._subclassed.items()})
	print("grip msgs seen:", [hex(m) for m in _seen])
	g = native.sizeGrips(dlg.GetHandle())[0]
	l, t, r, b = rect(g)
	def grab(tag):
		import time; time.sleep(0.15)
		img = ImageGrab.grab(bbox=(l - 10, t - 10, r, b), all_screens=True)
		img.resize((img.width * 6, img.height * 6), 0).save(os.path.join(HERE, "shots", "grip-%s.png" % tag.replace(" ", "-")))
		print("   ", tag, Counter(img.getdata()).most_common(4))
	user32.ShowWindow(g, 0); user32.UpdateWindow(dlg.GetHandle()); wx.Yield(); grab("grip hidden")
	user32.ShowWindow(g, 5); user32.UpdateWindow(g); wx.Yield(); grab("grip shown again")
	native._InvalidateRect(g, None, True); user32.UpdateWindow(g); wx.Yield(); grab("after invalidate+update")
	print("grip msgs seen now:", [hex(m) for m in _seen[-12:]])
	print("parent of grip:", [hex(user32.GetParent(h)) for h in native.sizeGrips(dlg.GetHandle())], "dlg hwnd:", hex(dlg.GetHandle()))
	wx.CallLater(200, finish)


def finish():
	dlg.Destroy()
	wx.CallLater(50, app.ExitMainLoop)


wx.CallLater(600, step1)
app.MainLoop()
