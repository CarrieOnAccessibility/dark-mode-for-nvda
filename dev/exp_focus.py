# Focus rings, selection colour, slider colours and the menu outline, checked on the bench
# (NVDA's bundled wxPython, no NVDA). Every capture is the window's OWN pixels via
# PrintWindow, never a screen grab. Prints measured colours; exits on its own.
#
#   python dev/exp_focus.py [--thick] [--out DIR]

import argparse
import ctypes
import os
import sys
import threading

try:
	ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
	pass
_wd = threading.Timer(30, lambda: os._exit(3))
_wd.daemon = True
_wd.start()

NVDA_DIR = r"C:\Program Files\NVDA"
HERE = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(NVDA_DIR)
sys.path.insert(0, os.path.join(NVDA_DIR, "library.zip"))
sys.path.insert(0, NVDA_DIR)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "addon", "globalPlugins", "darkMode")))

import wx  # noqa: E402
from PIL import Image  # noqa: E402

import native  # noqa: E402
import theming  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--thick", action="store_true")
parser.add_argument("--screen", action="store_true", help="sample the screen inside each control's window rect instead of PrintWindow")
parser.add_argument("--out", default=os.path.join(HERE, "shots"))
args = parser.parse_args()
os.makedirs(args.out, exist_ok=True)

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
WM_CHANGEUISTATE = 0x0127
UIS_CLEAR = 2
UISF_HIDEFOCUS = 1


class RECT(ctypes.Structure):
	_fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
	_fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
		("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
		("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
		("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


def printWindow(hwnd):
	"""The window's own pixels (PW_RENDERFULLCONTENT), as a PIL image; None on failure."""
	r = RECT()
	user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
	w, h = r.right - r.left, r.bottom - r.top
	if w <= 0 or h <= 0:
		return None
	user32.GetDC.restype = gdi32.CreateCompatibleDC.restype = gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
	gdi32.SelectObject.restype = ctypes.c_void_p
	screen = user32.GetDC(None)
	mem = gdi32.CreateCompatibleDC(ctypes.c_void_p(screen))
	bmp = gdi32.CreateCompatibleBitmap(ctypes.c_void_p(screen), w, h)
	old = gdi32.SelectObject(ctypes.c_void_p(mem), ctypes.c_void_p(bmp))
	img = None
	if user32.PrintWindow(ctypes.c_void_p(hwnd), ctypes.c_void_p(mem), 2):
		bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
		buf = ctypes.create_string_buffer(w * h * 4)
		if gdi32.GetDIBits(ctypes.c_void_p(mem), ctypes.c_void_p(bmp), 0, h, buf, ctypes.byref(bi), 0):
			img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).copy()
	gdi32.SelectObject(ctypes.c_void_p(mem), ctypes.c_void_p(old))
	gdi32.DeleteObject(ctypes.c_void_p(bmp))
	gdi32.DeleteDC(ctypes.c_void_p(mem))
	user32.ReleaseDC(None, ctypes.c_void_p(screen))
	return img


def clientRectInWindow(hwnd):
	"""The control's client rect in the coordinates of its own PrintWindow image."""
	wr = RECT()
	user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(wr))
	cr = RECT()
	user32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(cr))
	pt = ctypes.wintypes.POINT(0, 0) if hasattr(ctypes, "wintypes") else None
	from ctypes import wintypes

	pt = wintypes.POINT(0, 0)
	user32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(pt))
	ox, oy = pt.x - wr.left, pt.y - wr.top
	return ox, oy, ox + cr.right, oy + cr.bottom


def screenGrab(hwnd):
	"""The control's window rect from the screen (the bench dialog is on top; this is a window rect, not a region)."""
	from PIL import ImageGrab

	r = RECT()
	user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
	if r.right <= r.left or r.bottom <= r.top:
		return None
	return ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True).convert("RGB")


def ringSample(hwnd, rc=None):
	"""Colours along the top edge, left edge and just inside them, in the control's client area."""
	img = screenGrab(hwnd) if args.screen else printWindow(hwnd)
	if img is None:
		return None, None
	l, t, r, b = rc or clientRectInWindow(hwnd)
	midx, midy = (l + r) // 2, (t + b) // 2
	top = [img.getpixel((midx, t + i)) for i in range(3)]
	left = [img.getpixel((l + i, midy)) for i in range(3)]
	return img, {"top": top, "left": left}


class Bench(wx.Dialog):
	def __init__(self):
		super().__init__(None, title="Focus bench", size=wx.Size(560, 800))
		p = wx.Panel(self)
		s = wx.BoxSizer(wx.VERTICAL)
		self.cb = wx.CheckBox(p, label="Play sounds when starting or exiting NVDA")
		self.cb.SetValue(True)
		self.choice = wx.Choice(p, choices=["Default output device", "Speakers", "Headphones"])
		self.choice.SetSelection(0)
		self.combo = wx.ComboBox(p, value="No mirror", choices=["No mirror", "https://example.org"])
		self.slider = wx.Slider(p, value=50, minValue=0, maxValue=100, size=p.FromDIP(wx.Size(200, -1)))
		self.lb = wx.ListBox(p, choices=["(normal configuration)", "Say all", "Meeting", "Reading"], size=p.FromDIP(wx.Size(220, 90)))
		self.lb.SetSelection(0)
		self.lc = wx.ListCtrl(p, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=p.FromDIP(wx.Size(320, 110)))
		self.lc.InsertColumn(0, "Name", width=p.FromDIP(120))
		self.lc.InsertColumn(1, "Status", width=p.FromDIP(100))
		self.lc.InsertColumn(2, "Version", width=p.FromDIP(90), format=wx.LIST_FORMAT_RIGHT)
		for n, st, v in (("General", "Installed", "1.0"), ("Speech", "Update", "2.3.1"), ("Braille", "Installed", "0.9"), ("Audio", "Beta", "12")):
			i = self.lc.InsertItem(self.lc.GetItemCount(), n)
			self.lc.SetItem(i, 1, st)
			self.lc.SetItem(i, 2, v)
		self.lc.Select(1)
		self.lc.Focus(1)
		self.tree = wx.TreeCtrl(p, size=p.FromDIP(wx.Size(220, 90)), style=wx.TR_HAS_BUTTONS | wx.TR_DEFAULT_STYLE)
		root = self.tree.AddRoot("Gestures")
		for n in ("Braille", "Dark Mode", "Speech"):
			self.tree.AppendItem(root, n)
		self.tree.Expand(root)
		self.tree.SelectItem(self.tree.GetFirstChild(root)[0])
		for c in (self.cb, self.choice, self.combo, self.slider, self.lb, self.lc, self.tree):
			s.Add(c, 0, wx.ALL, 8)
		self.ok = wx.Button(p, wx.ID_OK, "OK")
		s.Add(self.ok, 0, wx.ALL, 8)
		p.SetSizer(s)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(p, 1, wx.EXPAND)
		self.SetSizerAndFit(outer)
		self.CentreOnScreen()


app = wx.App(False)
engine = theming.DarkModeEngine(lambda: True)
native.setRingWidth(2 if args.thick else 1)
engine.start()
dlg = Bench()
menu = wx.Menu()
for label in ("&Settings...", "Speech &dictionaries", "&Input gestures...", "Dar&k mode"):
	menu.Append(wx.ID_ANY, label)
results = {}


def showCues():
	# what the keyboard would do: focus cues on for the whole dialog
	user32.SendMessageW(ctypes.c_void_p(dlg.GetHandle()), WM_CHANGEUISTATE, (UISF_HIDEFOCUS << 16) | UIS_CLEAR, 0)


def step(fn, delay):
	wx.CallLater(delay, fn)


def checkControls():
	showCues()
	for name, win in (("checkbox", dlg.cb), ("choice", dlg.choice), ("combo", dlg.combo), ("slider", dlg.slider), ("listbox", dlg.lb), ("listctrl", dlg.lc), ("tree", dlg.tree), ("button", dlg.ok)):
		win.SetFocus()
		user32.UpdateWindow(ctypes.c_void_p(dlg.GetHandle()))
		h = win.GetHandle()
		rc = None
		if name in ("listctrl", "tree"):
			fr = native._focusRect(h)  # the focused row, in client coordinates
			if fr:
				l, t, _, _ = clientRectInWindow(h)
				rc = (l + fr.left, t + fr.top, l + fr.right, t + fr.bottom)
		wr = RECT()
		user32.GetWindowRect(ctypes.c_void_p(h), ctypes.byref(wr))
		if name in ("tree", "listctrl"):
			fr = native._focusRect(h)
			print("   debug %s: subclass ids=%s trueUI=%s hasFocus=%s cues=%s focusRect=%s class=%s" % (
				name, native._subclassed.get(h), native._trueUI.get(h), native._hasFocus(h), native._focusCuesVisible(h),
				(fr.left, fr.top, fr.right, fr.bottom) if fr else None, native._className(h)))
		img, cols = ringSample(h, rc)
		if img is None:
			print("   PrintWindow failed for", name, "rect", (wr.left, wr.top, wr.right, wr.bottom), "visible", user32.IsWindowVisible(ctypes.c_void_p(h)))
		if img is not None:
			img.save(os.path.join(args.out, "focus-%s.png" % name))
		results[name] = cols
		print("%-9s focus edge colours top=%s left=%s" % (name, cols["top"] if cols else None, cols["left"] if cols else None))


def checkListBoxAlignment():
	"""Row 0 drawn by us (selected) vs by Windows (not selected): the text must not move."""
	h = dlg.lb.GetHandle()
	dlg.lb.SetFocus()
	dlg.lb.SetSelection(0)
	user32.UpdateWindow(ctypes.c_void_p(h))
	a = printWindow(h)
	dlg.lb.SetSelection(1)
	user32.UpdateWindow(ctypes.c_void_p(h))
	b = printWindow(h)
	l, t, r, bt = clientRectInWindow(h)
	rc = RECT()
	user32.SendMessageW(ctypes.c_void_p(h), 0x0198, 0, ctypes.byref(rc))  # LB_GETITEMRECT row 0
	row = (l + rc.left, t + rc.top, l + rc.right, t + rc.bottom)

	def glyphBox(img):
		reg = img.crop((row[0] + 3, row[1] + 3, row[2] - 3, row[3] - 3)).convert("RGB")  # inside any ring
		bgc = reg.getpixel((reg.width - 3, reg.height // 2))
		xs, ys = [], []
		for y in range(reg.height):
			for x in range(reg.width):
				px = reg.getpixel((x, y))
				if max(abs(px[i] - bgc[i]) for i in range(3)) > 90:
					xs.append(x)
					ys.append(y)
		return (min(xs), min(ys), max(xs), max(ys)) if xs else None, bgc

	boxA, bgA = glyphBox(a)
	boxB, bgB = glyphBox(b)
	a.save(os.path.join(args.out, "listbox-ours.png"))
	b.save(os.path.join(args.out, "listbox-windows.png"))
	print("listbox row0 selected-by-us bg=%s glyphs=%s | drawn-by-Windows bg=%s glyphs=%s | %s" % (bgA, boxA, bgB, boxB, "ALIGNED" if boxA == boxB else "MISALIGNED"))
	# the ring on the caret row
	reg = a.crop(row)
	print("listbox caret ring top row px:", [reg.getpixel((reg.width // 2, i)) for i in range(2)])


def checkListViewAlignment():
	"""Row 1 painted by us (selected) vs by Windows (row 2 selected instead): text must not move."""
	h = dlg.lc.GetHandle()
	dlg.lc.SetFocus()
	dlg.lc.Select(1)
	dlg.lc.Focus(1)
	user32.UpdateWindow(ctypes.c_void_p(h))
	a = screenGrab(h)
	dlg.lc.Select(1, 0)
	dlg.lc.Select(2)
	dlg.lc.Focus(2)
	user32.UpdateWindow(ctypes.c_void_p(h))
	b = screenGrab(h)
	l, t, r, bt = clientRectInWindow(h)
	fr = native._focusRect(h)  # currently row 2; row 1 is one row up
	rowH = fr.bottom - fr.top
	row = (l + fr.left + 3, t + fr.top - rowH + 3, l + fr.right - 3, t + fr.bottom - rowH - 3)

	def glyphBox(img):
		reg = img.crop(row).convert("RGB")
		bgc = reg.getpixel((reg.width // 2, reg.height // 2))
		xs, ys = [], []
		for y in range(reg.height):
			for x in range(reg.width):
				px = reg.getpixel((x, y))
				if max(abs(px[i] - bgc[i]) for i in range(3)) > 90:
					xs.append(x)
					ys.append(y)
		return (min(xs), min(ys), max(xs), max(ys)) if xs else None, bgc

	boxA, bgA = glyphBox(a)
	boxB, bgB = glyphBox(b)
	a.save(os.path.join(args.out, "listview-ours.png"))
	b.save(os.path.join(args.out, "listview-windows.png"))
	print("listview row1 selected-by-us bg=%s glyphs=%s | drawn-by-Windows bg=%s glyphs=%s | %s" % (bgA, boxA, bgB, boxB, "ALIGNED" if boxA == boxB else "MISALIGNED"))
	# per column: where the ink starts and ends inside each subitem rect
	for col in range(3):
		cell = native.RECT(native.LVIR_LABEL, col, 0, 0)
		if col == 0:
			native._SendMessageW(h, native.LVM_GETITEMRECT, 1, ctypes.addressof(cell))
		else:
			native._SendMessageW(h, native.LVM_GETSUBITEMRECT, 1, ctypes.addressof(cell))
		box = (l + cell.left, t + cell.top + 3, l + cell.right, t + cell.bottom - 3)

		def ink(img, bgc):
			reg = img.crop(box).convert("RGB")
			xs = [x for x in range(reg.width) if any(max(abs(reg.getpixel((x, y))[i] - bgc[i]) for i in range(3)) > 90 for y in range(reg.height))]
			return (xs[0], xs[-1]) if xs else None

		print("  column %d rect %s: ink ours=%s Windows=%s" % (col, (cell.left, cell.right), ink(a, bgA), ink(b, bgB)))


def checkSlider():
	h = dlg.slider.GetHandle()
	rc = RECT()
	user32.SendMessageW(ctypes.c_void_p(h), 0x0400 + 25, 0, ctypes.byref(rc))  # TBM_GETTHUMBRECT
	dlg.ok.SetFocus()
	user32.UpdateWindow(ctypes.c_void_p(h))
	img = printWindow(h)
	l, t, r, b = clientRectInWindow(h)
	cx, cy = l + (rc.left + rc.right) // 2, t + (rc.top + rc.bottom) // 2 - 2
	print("slider thumb at rest:", img.getpixel((cx, cy)))
	# hover: a mouse-move MESSAGE to the control (the cursor does not move)
	x, y = (rc.left + rc.right) // 2, (rc.top + rc.bottom) // 2
	user32.SendMessageW(ctypes.c_void_p(h), 0x0200, 0, (y << 16) | x)
	user32.UpdateWindow(ctypes.c_void_p(h))
	img = printWindow(h)
	print("slider thumb hovered:", img.getpixel((cx, cy)))
	user32.SendMessageW(ctypes.c_void_p(h), 0x02A3, 0, 0)  # WM_MOUSELEAVE


def checkDropdown():
	h = dlg.choice.GetHandle()
	user32.SendMessageW(ctypes.c_void_p(h), 0x014F, 1, 0)  # CB_SHOWDROPDOWN

	def grab():
		lst = user32.FindWindowW("ComboLBox", None)
		if lst:
			img = screenGrab(lst) if args.screen else printWindow(lst)
			img.save(os.path.join(args.out, "dropdown.png"))
			rc = RECT()
			user32.SendMessageW(ctypes.c_void_p(lst), 0x0198, 0, ctypes.byref(rc))
			l, t, r, b = clientRectInWindow(lst)
			rowH = rc.bottom - rc.top
			print("dropdown list: selected row bg=%s, row 1 bg=%s" % (img.getpixel((l + rc.right - 4, t + (rc.top + rc.bottom) // 2)), img.getpixel((l + rc.right - 4, t + rc.bottom + rowH // 2))))
			# hover over row 2: a mouse-move MESSAGE to the list (the cursor does not move)
			x, y = (rc.left + rc.right) // 2, rc.top + 2 * rowH + rowH // 2
			user32.SendMessageW(ctypes.c_void_p(lst), 0x0200, 0, (y << 16) | x)
			user32.UpdateWindow(ctypes.c_void_p(lst))
			img2 = screenGrab(lst) if args.screen else printWindow(lst)
			img2.save(os.path.join(args.out, "dropdown-hover.png"))
			print("dropdown after hover on row 2: row 0 bg=%s, row 2 bg=%s" % (img2.getpixel((l + rc.right - 4, t + (rc.top + rc.bottom) // 2)), img2.getpixel((l + rc.right - 4, t + 2 * rowH + rowH // 2))))
		else:
			print("dropdown list window not found")
		user32.SendMessageW(ctypes.c_void_p(h), 0x014F, 0, 0)

	step(grab, 250)


def checkMenu():
	popups = []

	def arrow():
		hm = user32.FindWindowW("#32768", None)
		if hm:
			popups.append(hm)
			user32.PostMessageW(ctypes.c_void_p(hm), 0x0100, 0x28, 0)  # VK_DOWN
			user32.PostMessageW(ctypes.c_void_p(hm), 0x0101, 0x28, 0)

	def grab():
		for hm in popups[:1]:
			img = printWindow(hm)
			img.save(os.path.join(args.out, "menu-outline.png"))
			# highlighted item rect from the menu itself
			hmenu = user32.SendMessageW(ctypes.c_void_p(hm), 0x01E1, 0, 0)
			print("menu popup captured", img.size, "hmenu", hex(hmenu or 0))
			from collections import Counter

			c = Counter(img.convert("RGB").getdata())
			print("menu colours:", c.most_common(5))
		user32.EndMenu()

	step(arrow, 250)
	step(grab, 500)
	dlg.PopupMenu(menu, wx.Point(20, 20))


def run():
	checkControls()
	checkListBoxAlignment()
	checkListViewAlignment()
	checkSlider()
	checkDropdown()
	step(checkMenu, 600)
	step(lambda: (dlg.Destroy(), os._exit(0)), 1500)


dlg.Show()
step(run, 400)
app.MainLoop()
