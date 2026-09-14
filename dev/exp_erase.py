# Experiment: what does each control look like between its ERASE and its first PAINT?
# Shows a dialog full of control types, then blocks the main thread for a second so
# WM_PAINT cannot run, while a thread photographs the dialog. Whatever is white in
# that photo is what flashes in NVDA (which is busy for ~100 ms after a dialog opens).
#   python dev/exp_erase.py [--light]
import ctypes
import os
import sys
import threading
import time

try:
	ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
	pass
ctypes.windll.user32.DisableProcessWindowsGhosting()  # keep the real window on screen while we block
_wd = threading.Timer(20, lambda: os._exit(3))
_wd.daemon = True
_wd.start()

NVDA_DIR = r"C:\Program Files\NVDA"
HERE = os.path.dirname(os.path.abspath(__file__))
ADDON_PLUGIN_DIR = os.path.join(HERE, "..", "addon", "globalPlugins", "nvdaDarkMode")
os.add_dll_directory(NVDA_DIR)
sys.path.insert(0, os.path.join(NVDA_DIR, "library.zip"))
sys.path.insert(0, NVDA_DIR)
sys.path.insert(0, os.path.abspath(ADDON_PLUGIN_DIR))

import wx  # noqa: E402
import theming  # noqa: E402
from PIL import ImageGrab  # noqa: E402
from collections import Counter  # noqa: E402

light = "--light" in sys.argv
app = wx.App()
if not light:
	theming.setProcessDark(True)
	engine = theming.DarkModeEngine(lambda: True)
	engine.start()

dlg = wx.Dialog(None, title="Erase test", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
s = wx.BoxSizer(wx.VERTICAL)
probes = {}


def add(name, ctrl, flag=0):
	probes[name] = ctrl
	s.Add(ctrl, 0, wx.ALL | flag, 6)
	return ctrl


add("staticText", wx.StaticText(dlg, label="A label"))
add("textCtrl", wx.TextCtrl(dlg, value="typed text", size=dlg.FromDIP(wx.Size(200, -1))))
add("readOnly", wx.TextCtrl(dlg, value="read only", style=wx.TE_READONLY, size=dlg.FromDIP(wx.Size(200, -1))))
add("richRO", wx.TextCtrl(dlg, value="rich read only", style=wx.TE_RICH2 | wx.TE_READONLY | wx.TE_MULTILINE, size=dlg.FromDIP(wx.Size(200, 40))))
add("button", wx.Button(dlg, label="A button"))
add("checkBox", wx.CheckBox(dlg, label="A check box"))
add("choice", wx.Choice(dlg, choices=["one", "two"]))
probes["choice"].SetSelection(0)
add("comboBox", wx.ComboBox(dlg, value="combo", choices=["one", "two"]))
add("spin", wx.SpinCtrl(dlg, value="5"))
add("slider", wx.Slider(dlg, value=3, minValue=0, maxValue=10, size=dlg.FromDIP(wx.Size(200, -1))))
add("gauge", wx.Gauge(dlg, range=10, size=dlg.FromDIP(wx.Size(200, -1))))
probes["gauge"].SetValue(4)
add("radioBox", wx.RadioBox(dlg, label="Radio box", choices=["a", "b"]))
add("listBox", wx.ListBox(dlg, choices=["l1", "l2"], size=dlg.FromDIP(wx.Size(200, 50))))
add("checkList", wx.CheckListBox(dlg, choices=["c1", "c2"], size=dlg.FromDIP(wx.Size(200, 50))))
lc = add("listCtrl", wx.ListCtrl(dlg, style=wx.LC_REPORT, size=dlg.FromDIP(wx.Size(200, 60))))
lc.InsertColumn(0, "Col")
lc.InsertItem(0, "row")
tree = add("tree", wx.TreeCtrl(dlg, size=dlg.FromDIP(wx.Size(200, 50))))
root = tree.AddRoot("root")
tree.AppendItem(root, "leaf")
tree.ExpandAll()
nb = add("notebook", wx.Notebook(dlg, size=dlg.FromDIP(wx.Size(200, 60))))
nb.AddPage(wx.Panel(nb), "Tab 1")
nb.AddPage(wx.Panel(nb), "Tab 2")
box = wx.StaticBox(dlg, label="Static box")
probes["staticBox"] = box
bs = wx.StaticBoxSizer(box, wx.VERTICAL)
bs.Add(wx.StaticText(box, label="inside the box"), 0, wx.ALL, 6)
s.Add(bs, 0, wx.ALL | wx.EXPAND, 6)
add("staticLine", wx.StaticLine(dlg, size=dlg.FromDIP(wx.Size(200, -1))))
panel = wx.Panel(dlg, size=dlg.FromDIP(wx.Size(200, 20)))
add("panel", panel)
dlg.SetSizerAndFit(s)


def rect(h):
	r = ctypes.wintypes.RECT()
	ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
	return r.left, r.top, r.right, r.bottom


def photograph(results):
	time.sleep(0.8)  # main thread is blocked: nothing has painted yet
	img = ImageGrab.grab(all_screens=True)
	img.save(os.path.join(HERE, "shots", "erase-%s.png" % ("light" if light else "dark")))
	for name, w in probes.items():
		l, t, r, b = rect(w.GetHandle())
		crop = img.crop((l + 2, t + 2, max(l + 3, r - 2), max(t + 3, b - 2)))
		c = Counter(crop.getdata()).most_common(2)
		results.append((name, c))
		if name in ("listCtrl", "comboBox"):
			# where exactly is the white? rows of the crop
			px = crop.load()
			rows = [y for y in range(crop.height) if all(px[x, y][0] > 250 for x in range(0, crop.width, 8))]
			results.append((name + " white rows", "%d..%d of %d" % (rows[0], rows[-1], crop.height) if rows else "none"))
			if name == "listCtrl":
				results.append(("listCtrl header hwnd", hex(headerHwnd)))


import ctypes.wintypes  # noqa: E402
import native  # noqa: E402
import time as _time  # noqa: E402

_t0 = _time.perf_counter()
_trace = []
_TR = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t)
_Def = ctypes.windll.comctl32.DefSubclassProc
_Def.argtypes = (ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
_Def.restype = ctypes.c_ssize_t
_Set = ctypes.windll.comctl32.SetWindowSubclass
_Set.argtypes = (ctypes.wintypes.HWND, _TR, ctypes.c_size_t, ctypes.c_size_t)
_names = {}
_MSGS = {0x14: "ERASEBKGND", 0xF: "PAINT", 0x85: "NCPAINT", 0x133: "CTLCOLOREDIT", 0x138: "CTLCOLORSTATIC", 0x18: "SHOWWINDOW"}


def _tr(hwnd, msg, w, l, uid, ref):
	lab = _MSGS.get(msg)
	if lab:
		_trace.append("%6.1f ms %-14s %s%s" % ((_time.perf_counter() - _t0) * 1000, _names.get(hwnd, hex(hwnd)), lab, " for=%s" % _names.get(l, hex(l)) if msg in (0x133, 0x138) else ""))
	return _Def(hwnd, msg, w, l)


_trProc = _TR(_tr)


def watch(name, hwnd):
	_names[hwnd] = name
	_Set(hwnd, _trProc, 97, 0)


watch("dialog", dlg.GetHandle())
watch("textCtrl", probes["textCtrl"].GetHandle())
watch("spinUpDown", probes["spin"].GetHandle())
watch("spinEdit", native.spinBuddy(probes["spin"].GetHandle()))
watch("combo", probes["comboBox"].GetHandle())
watch("comboEdit", ctypes.windll.user32.GetWindow(probes["comboBox"].GetHandle(), 5))
watch("listCtrl", lc.GetHandle())
watch("button", probes["button"].GetHandle())
_trace.append("%6.1f ms Show()" % ((_time.perf_counter() - _t0) * 1000))

results = []
headerHwnd = ctypes.windll.user32.SendMessageW(lc.GetHandle(), 0x101F, 0, 0)  # LVM_GETHEADER (main thread only)
th = threading.Thread(target=photograph, args=(results,), daemon=True)
dlg.Show()
th.start()
time.sleep(1.6)  # block WM_PAINT (the GIL is released while sleeping, so the thread can grab)
th.join()
print("between erase and first paint (%s):" % ("light" if light else "dark"))
for name, c in results:
	flag = "  <-- WHITE" if isinstance(c, list) and c and c[0][0][0] >= 250 and c[0][0][1] >= 250 else ""
	print("  %-12s %s%s" % (name, c, flag))
print("message trace:")
print(chr(10).join("  " + ln for ln in _trace))
dlg.Destroy()
wx.CallLater(50, app.ExitMainLoop)
app.MainLoop()
