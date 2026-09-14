# Experiment: a copy of NVDA's Welcome dialog layout (intro text + "Options" static box
# whose children are parented to the box), to reproduce garbled group-box painting.
#   python dev/exp_welcome.py [--light] [--nobox] [--noshowpaint]
import ctypes
import os
import sys
import threading

try:
	ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
	pass
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
import native  # noqa: E402
from PIL import ImageGrab  # noqa: E402

light = "--light" in sys.argv
if "--nobox" in sys.argv:
	native.applyStaticBox = lambda hwnd, dark: None
if "--noshowpaint" in sys.argv:
	native.applyShowPaint = lambda hwnd, dark: None

app = wx.App()
if not light:
	theming.setProcessDark(True)
	engine = theming.DarkModeEngine(lambda: True)
	engine.start()


class Welcome(wx.Dialog):
	def __init__(self):
		super().__init__(None, title="Welcome to NVDA!")
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		welcomeText = wx.StaticText(self, label="Welcome to NVDA!")
		welcomeText.SetFont(wx.Font(18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
		mainSizer.Add(welcomeText, border=10, flag=wx.TOP | wx.LEFT | wx.RIGHT)
		msg = (
			"Most commands for controlling NVDA require you to hold down the NVDA key while pressing other keys.\n"
			"By default, the Insert and numpad Insert keys may both be used as the NVDA key.\n"
			"You can also configure NVDA to use the CapsLock as the NVDA key.\n"
			"Press NVDA+n at any time to activate the NVDA menu.\n"
			"From this menu, you can configure NVDA, get help, and access other NVDA functions."
		)
		mainSizer.Add(wx.StaticText(self, label=msg), border=10, flag=wx.ALL)
		optionsSizer = wx.StaticBoxSizer(wx.VERTICAL, self, label="Options")
		box = optionsSizer.GetStaticBox()
		row = wx.BoxSizer(wx.HORIZONTAL)
		row.Add(wx.StaticText(box, label="Keyboard layout:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
		ch = wx.Choice(box, choices=["desktop", "laptop"])
		ch.SetSelection(0)
		row.Add(ch)
		optionsSizer.Add(row, 0, wx.ALL, 6)
		for label, checked in (
			("Use CapsLock as an NVDA modifier key", True),
			("Start NVDA after I sign in", False),
			("Show this dialog when NVDA starts", False),
		):
			cb = wx.CheckBox(box, label=label)
			cb.SetValue(checked)
			optionsSizer.Add(cb, 0, wx.LEFT | wx.BOTTOM, 6)
		mainSizer.Add(optionsSizer, border=10, flag=wx.LEFT | wx.RIGHT | wx.EXPAND)
		mainSizer.Add(self.CreateButtonSizer(wx.OK), border=10, flag=wx.ALL | wx.ALIGN_RIGHT)
		self.SetSizer(mainSizer)
		mainSizer.Fit(self)
		self.CentreOnScreen()


dlg = Welcome()
dlg.Show()


def shoot():
	r = ctypes.wintypes.RECT()
	ctypes.windll.user32.GetWindowRect(dlg.GetHandle(), ctypes.byref(r))
	img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
	tag = "light" if light else "dark"
	for flag in ("--nobox", "--noshowpaint"):
		if flag in sys.argv:
			tag += flag.replace("--", "-")
	path = os.path.join(HERE, "shots", "welcome-%s.png" % tag)
	img.save(path)
	print("saved", path, img.size)
	dlg.Destroy()
	wx.CallLater(50, app.ExitMainLoop)


import ctypes.wintypes  # noqa: E402

wx.CallLater(800, shoot)
app.MainLoop()
