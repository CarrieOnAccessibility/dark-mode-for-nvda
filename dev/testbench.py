# Test bench: exercises the dark mode engine against NVDA's own bundled wxPython
# without running NVDA. Builds a dialog with the same kinds of controls NVDA's
# settings dialogs use, applies the engine, takes screenshots, exits.
#
#   python dev/testbench.py [--light] [--out DIR]

import argparse
import ctypes
import os
import sys
import threading

# Per-monitor DPI aware (v2) BEFORE wx loads, so window rects are physical pixels.
try:
	ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
	pass

# Hard watchdog: whatever happens, this process dies on its own.
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
import wx.lib.scrolledpanel as scrolledpanel  # noqa: E402
from wx.lib.mixins import listctrl as listmix  # noqa: E402

import theming  # noqa: E402
from PIL import ImageGrab  # noqa: E402  (NVDA bundles PIL)

parser = argparse.ArgumentParser()
parser.add_argument("--light", action="store_true", help="do not apply dark mode (baseline shot)")
parser.add_argument("--out", default=os.path.join(HERE, "shots"))
parser.add_argument("--hold", type=int, default=0, help="keep the dialog open this many ms (0 = just screenshot)")
args = parser.parse_args()
os.makedirs(args.out, exist_ok=True)



class CatList(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
	def __init__(self, parent):
		wx.ListCtrl.__init__(self, parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES)
		listmix.ListCtrlAutoWidthMixin.__init__(self)


class FakeSettings(wx.Dialog):
	def __init__(self):
		super().__init__(None, title="NVDA Settings: General (normal configuration)")
		self.SetSize(self.FromDIP(wx.Size(900, 640)))
		outer = wx.BoxSizer(wx.VERTICAL)
		grid = wx.BoxSizer(wx.HORIZONTAL)

		left = wx.BoxSizer(wx.VERTICAL)
		left.Add(wx.StaticText(self, label="&Categories:"), 0, wx.ALL, 5)
		self.catList = CatList(self)
		self.catList.InsertColumn(0, "Name")
		self.catList.InsertColumn(1, "Status", width=self.FromDIP(90))
		for name in ["General", "Speech", "Braille", "Vision", "Keyboard", "Mouse", "Review Cursor", "Dark Mode"]:
			self.catList.Append((name, "Enabled"))
		self.catList.Select(0)
		self.probe = {"catList": self.catList}
		left.Add(self.catList, 1, wx.EXPAND | wx.ALL, 5)
		grid.Add(left, 0, wx.EXPAND)

		self.container = scrolledpanel.ScrolledPanel(self, style=wx.TAB_TRAVERSAL | wx.BORDER_THEME)
		self.container.SetupScrolling()
		panel = wx.Panel(self.container)
		ps = wx.BoxSizer(wx.VERTICAL)

		row = wx.BoxSizer(wx.HORIZONTAL)
		row.Add(wx.StaticText(panel, label="&Language (requires restart):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		ch = wx.Choice(panel, choices=["User default, English", "English, United States", "Deutsch", "Español"])
		ch.SetSelection(0)
		row.Add(ch, 0)
		disBtn = wx.Button(panel, label="Disabled")
		disBtn.Disable()
		row.Add(disBtn, 0, wx.LEFT, 12)
		ps.Add(row, 0, wx.ALL, 6)

		for label, val in [("&Save configuration when exiting NVDA", True), ("Show exit options when quitting NVDA", True), ("&Play sounds when starting or exiting NVDA", False), ("&Automatically check for NVDA updates", True)]:
			cb = wx.CheckBox(panel, label=label)
			cb.SetValue(val)
			ps.Add(cb, 0, wx.ALL, 6)

		sb = wx.StaticBoxSizer(wx.StaticBox(panel, label="Logging level"), wx.VERTICAL)
		for i, label in enumerate(["Disabled", "Info", "Debug warning", "Input/output"]):
			rb = wx.RadioButton(panel, label=label, style=wx.RB_GROUP if i == 0 else 0)
			if i == 1:
				rb.SetValue(True)
			sb.Add(rb, 0, wx.ALL, 3)
		ps.Add(sb, 0, wx.ALL | wx.EXPAND, 6)

		rbox = wx.RadioBox(panel, label="Capitalization (wx.RadioBox)", choices=["Off", "Say cap", "Beep"], majorDimension=3)
		ps.Add(rbox, 0, wx.ALL, 6)

		row = wx.BoxSizer(wx.HORIZONTAL)
		row.Add(wx.StaticText(panel, label="&Rate:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		sl = wx.Slider(panel, value=50, minValue=0, maxValue=100, size=panel.FromDIP(wx.Size(200, -1)))
		row.Add(sl, 0, wx.ALIGN_CENTER_VERTICAL)
		row.Add(wx.StaticText(panel, label="  &Volume:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		sp = wx.SpinCtrl(panel, value="80", min=0, max=100)
		row.Add(sp, 0)
		ps.Add(row, 0, wx.ALL, 6)

		row = wx.BoxSizer(wx.HORIZONTAL)
		row.Add(wx.StaticText(panel, label="&Update mirror URL:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
		tc = wx.TextCtrl(panel, value="https://download.nvaccess.org/", size=panel.FromDIP(wx.Size(260, -1)))
		row.Add(tc, 0)
		self.probe["textField"] = tc
		rich = wx.TextCtrl(panel, style=wx.TE_RICH2 | wx.TE_MULTILINE | wx.TE_READONLY, size=panel.FromDIP(wx.Size(220, 28)))
		self.probe["richText"] = rich
		wx.CallAfter(rich.SetValue, "No mirror")
		changeBtn = wx.Button(panel, label="&Change...")
		self.probe["button"] = changeBtn
		row.Add(changeBtn, 0, wx.LEFT, 6)
		self.probe["disabledButton"] = disBtn
		ps.Add(row, 0, wx.ALL, 6)
		ps.Add(rich, 0, wx.ALL, 6)

		row = wx.BoxSizer(wx.HORIZONTAL)
		clb = wx.CheckListBox(panel, choices=["Report fonts", "Report colors", "Report emphasis", "Report links", "Report headings"], size=panel.FromDIP(wx.Size(220, 90)))
		clb.Check(1)
		clb.Check(3)
		self.probe["checkList"] = clb
		row.Add(clb, 0, wx.RIGHT, 10)
		tree = wx.TreeCtrl(panel, size=panel.FromDIP(wx.Size(220, 90)), style=wx.TR_HAS_BUTTONS | wx.TR_DEFAULT_STYLE)
		root = tree.AddRoot("Add-ons")
		a = tree.AppendItem(root, "Installed")
		tree.AppendItem(a, "NVDA Dark Mode")
		tree.AppendItem(a, "Eloquence")
		tree.AppendItem(root, "Available")
		tree.ExpandAll()
		self.probe["tree"] = tree
		row.Add(tree, 0)
		ps.Add(row, 0, wx.ALL, 6)

		nb = wx.Notebook(panel, size=panel.FromDIP(wx.Size(-1, 90)))
		for name in ["Installed add-ons", "Updatable add-ons", "Available add-ons"]:
			pg = wx.Panel(nb)
			wx.StaticText(pg, label="page: " + name, pos=pg.FromDIP(wx.Point(8, 8)))
			nb.AddPage(pg, name)
		ps.Add(nb, 0, wx.ALL | wx.EXPAND, 6)
		self.probe["notebook"] = nb
		ro = wx.TextCtrl(panel, value="This is a read-only multi-line text box like the ones NVDA uses for add-on descriptions.\nLine two.\nLine three.", style=wx.TE_MULTILINE | wx.TE_READONLY, size=panel.FromDIP(wx.Size(-1, 70)))
		ps.Add(ro, 0, wx.ALL | wx.EXPAND, 6)
		self.probe["readOnlyText"] = ro
		self.probe["choice"] = ch

		dis = wx.CheckBox(panel, label="A disabled checkbox")
		dis.Disable()
		ps.Add(dis, 0, wx.ALL, 6)
		dist = wx.StaticText(panel, label="A disabled label")
		dist.Disable()
		ps.Add(dist, 0, wx.ALL, 6)

		panel.SetSizer(ps)
		cs = wx.BoxSizer(wx.VERTICAL)
		cs.Add(panel, 1, wx.EXPAND)
		self.container.SetSizer(cs)
		grid.Add(self.container, 1, wx.EXPAND | wx.ALL, 5)
		outer.Add(grid, 1, wx.EXPAND)

		btns = wx.StdDialogButtonSizer()
		ok = wx.Button(self, wx.ID_OK, "OK")
		ok.SetDefault()
		btns.AddButton(ok)
		btns.AddButton(wx.Button(self, wx.ID_CANCEL, "Cancel"))
		btns.AddButton(wx.Button(self, wx.ID_APPLY, "Apply"))
		btns.Realize()
		outer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		self.SetSizer(outer)
		self.CentreOnScreen()


class _RECT(ctypes.Structure):
	_fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


def hwndRect(hwnd):
	r = _RECT()
	ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
	return r.l, r.t, r.r, r.b


def screenshot(hwnds, path, pad=0):
	"""Grab the union of the given window rects from the screen (physical pixels)."""
	rects = [hwndRect(h) for h in hwnds if h]
	l = min(r[0] for r in rects) - pad
	t = min(r[1] for r in rects) - pad
	rr = max(r[2] for r in rects) + pad
	b = max(r[3] for r in rects) + pad
	img = ImageGrab.grab(bbox=(l, t, rr, b), all_screens=True)
	img.save(path)
	print("saved", path, img.size)


app = wx.App(False)
engine = None
if not args.light:
	engine = theming.DarkModeEngine(lambda: True)
	engine.start()
	print("engine active:", engine.active, "build", theming.WIN_BUILD, "ordinals:", bool(theming._SetPreferredAppMode), bool(theming._FlushMenuThemes))

dlg = FakeSettings()
tag = "light" if args.light else "dark"
menu = wx.Menu()
prefs = wx.Menu()
prefs.Append(wx.ID_ANY, "&Settings...")
prefs.Append(wx.ID_ANY, "Speech &dictionaries")
menu.AppendSubMenu(prefs, "&Preferences")
menu.Append(wx.ID_ANY, "&Tools")
menu.Append(wx.ID_ANY, "&Help")
menu.AppendSeparator()
menu.Append(wx.ID_ANY, "&Configuration profiles...")
menu.Append(wx.ID_ANY, "&Revert to saved configuration")
menu.AppendSeparator()
menu.Append(wx.ID_EXIT, "E&xit")


def _dominant(img):
	from collections import Counter

	c = Counter(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
	bg = c.most_common(1)[0][0]
	rest = [col for col, n in c.most_common(6) if col != bg]
	return bg, rest[:2]


def measure(win, name):
	"""Report background + text colour inside the control, and its edge colours."""
	l, t, r, b = hwndRect(win.GetHandle())
	# top-left portion only: avoids scrollbars and clipped edges
	inner = ImageGrab.grab(bbox=(l + 4, t + 4, l + 4 + max(8, (r - l) * 6 // 10), t + 4 + max(8, (b - t) * 4 // 10)), all_screens=True)
	bg, text = _dominant(inner)
	edge = ImageGrab.grab(bbox=(l, t, l + 3, b), all_screens=True)  # left edge, 3px wide
	edgeCols = [edge.getpixel((x, edge.height // 2)) for x in range(3)]
	print(f"  {name:15s} bg={bg} text={text} leftEdge={edgeCols}")


def report(dlg):
	import native as _n
	h = dlg.probe["catList"].GetHandle()
	print("catList hwnd", h, "hasFrame", _n.hasFrame(h), "exstyle", hex(_n._GetWindowLongW(h, -20) & 0xFFFFFFFF), "style", hex(_n._GetWindowLongW(h, -16) & 0xFFFFFFFF), "subclassed", _n._subclassed.get(h), "GetBorder", dlg.probe["catList"].GetBorder(), "BORDER_NONE", wx.BORDER_NONE, "BORDER_THEME", wx.BORDER_THEME)
	print("measurements (bg, text-ish colours, edge pixels):")
	for name, win in dlg.probe.items():
		try:
			measure(win, name)
		except Exception as e:
			print("  ", name, "failed:", e)


def popupExists():
	return bool(ctypes.windll.user32.FindWindowW("#32768", None))


def stepShotDialog():
	print("phase 1: popup visible before dialog shot?", popupExists())
	screenshot([dlg.GetHandle()], os.path.join(args.out, f"settings-{tag}.png"), pad=8)
	report(dlg)
	wx.CallLater(300, stepMenu)


def stepMenu():
	def shootMenu():
		popup = ctypes.windll.user32.FindWindowW("#32768", None)
		print("phase 2: popup hwnd", popup)
		screenshot([dlg.GetHandle(), popup], os.path.join(args.out, f"menu-{tag}.png"), pad=8)
		ctypes.windll.user32.EndMenu()

	wx.CallLater(400, shootMenu)
	dlg.PopupMenu(menu, dlg.FromDIP(wx.Point(200, 120)))
	print("phase 3: menu closed, popup visible?", popupExists())
	wx.CallLater(args.hold or 100, finish)


def finish():
	if engine:
		engine.stop()
	dlg.Destroy()
	app.ExitMainLoop()


dlg.Show()
wx.CallLater(700, stepShotDialog)
app.MainLoop()
print("done")
