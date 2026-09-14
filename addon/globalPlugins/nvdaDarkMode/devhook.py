# DEVELOPMENT ONLY. Not shipped: build.py excludes this file from the package.
#
# Lets dev/nvda_exec.py ask the live NVDA to open its own dialogs, screenshot
# them and report control colours, so dark mode can be checked without
# injecting keystrokes into whatever window has focus. Deliberately NOT a
# general "run code" hook: only the fixed verbs below, screenshots only ever
# land in this add-on's own dev/shots folder.
#
# Protocol: dev/nvda_exec.py writes %TEMP%\nvdaDarkMode-dev\cmd.txt with one
# line "verb arg1|arg2|..."; a timer here runs it and writes result.txt.

import ctypes
import io
import os
import re
import traceback

import wx
from logHandler import log

CMD_DIR = os.path.join(os.environ.get("TEMP", "."), "nvdaDarkMode-dev")
CMD = os.path.join(CMD_DIR, "cmd.txt")
RESULT = os.path.join(CMD_DIR, "result.txt")
# Screenshots go here and nowhere else: the project's dev/shots folder, whose
# path build.py --install records next to this file; else a folder under TEMP.
def _shotsDir():
	cfg = os.path.join(os.path.dirname(__file__), "dev_shots_dir.txt")
	try:
		with open(cfg, encoding="utf-8") as f:
			d = f.read().strip()
		if d:
			return d
	except OSError:
		pass
	return os.path.join(CMD_DIR, "shots")


SHOTS_DIR = _shotsDir()
_user32 = ctypes.windll.user32


class _RECT(ctypes.Structure):
	_fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


def _hwndRect(hwnd):
	r = _RECT()
	_user32.GetWindowRect(hwnd, ctypes.byref(r))
	return r.l, r.t, r.r, r.b


def _shotPath(name):
	name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
	if not name.endswith(".png"):
		name += ".png"
	os.makedirs(SHOTS_DIR, exist_ok=True)
	return os.path.join(SHOTS_DIR, name)


def _grab(hwnds, name, pad=8):
	from PIL import ImageGrab

	rects = [_hwndRect(h) for h in hwnds if h]
	if not rects:
		print("nothing to screenshot")
		return
	l = min(r[0] for r in rects) - pad
	t = min(r[1] for r in rects) - pad
	rr = max(r[2] for r in rects) + pad
	b = max(r[3] for r in rects) + pad
	img = ImageGrab.grab(bbox=(l, t, rr, b), all_screens=True)
	path = _shotPath(name)
	img.save(path)
	print("saved", path, img.size)


def _findTLW(titlePart):
	titlePart = titlePart.lower()
	for w in wx.GetTopLevelWindows():
		if w.IsShown() and titlePart in w.GetTitle().lower():
			return w
	return None


def _popups():
	found = []
	EnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

	@EnumProc
	def cb(h, _):
		buf = ctypes.create_unicode_buffer(64)
		_user32.GetClassNameW(h, buf, 64)
		if buf.value == "#32768" and _user32.IsWindowVisible(h):
			found.append(h)
		return True

	_user32.EnumWindows(cb, 0)
	return found


def _walk(win):
	yield win
	for c in win.GetChildren():
		yield from _walk(c)


def _dump(win, depth=0):
	hwnd = win.GetHandle()
	buf = ctypes.create_unicode_buffer(128)
	_user32.GetClassNameW(hwnd, buf, 128)
	try:
		label = win.GetLabel()[:50]
	except Exception:
		label = ""
	print(
		"  " * depth
		+ f"{type(win).__module__}.{type(win).__name__} [{buf.value}] {label!r} "
		+ f"bg={win.GetBackgroundColour().GetAsString(wx.C2S_HTML_SYNTAX)} "
		+ f"fg={win.GetForegroundColour().GetAsString(wx.C2S_HTML_SYNTAX)} "
		+ f"{'shown' if win.IsShown() else 'hidden'} {'enabled' if win.IsEnabled() else 'DISABLED'}"
	)
	for c in win.GetChildren():
		_dump(c, depth + 1)


class DevHook:
	def __init__(self, plugin):
		self.plugin = plugin
		os.makedirs(CMD_DIR, exist_ok=True)
		self.timer = wx.Timer()
		self.timer.Bind(wx.EVT_TIMER, self._poll)
		self.timer.Start(300)
		log.info("nvdaDarkMode: dev hook active (fixed verbs), shots -> %s" % SHOTS_DIR)

	def stop(self):
		self.timer.Stop()

	# --- verbs ---------------------------------------------------------------
	def v_ping(self):
		print("ok; dark active =", self.plugin.engine.active)
		print("open windows:", [w.GetTitle() for w in wx.GetTopLevelWindows() if w.IsShown()])

	def v_settings(self, category=""):
		"""Open NVDA Settings, optionally at the category whose title contains the text."""
		import gui
		from gui.settingsDialogs import NVDASettingsDialog

		cls = None
		if category:
			for c in NVDASettingsDialog.categoryClasses:
				if category.lower() in c.title.lower():
					cls = c
					break
		wx.CallAfter(gui.mainFrame.popupSettingsDialog, NVDASettingsDialog, cls)
		print("opening settings", cls.title if cls else "(default)")

	def v_dialog(self, which):
		"""Open one of NVDA's own dialogs by short name."""
		import gui

		actions = {
			"dictionary": "onDefaultDictionaryCommand",
			"symbols": "onSpeechSymbolsCommand",
			"gestures": "onInputGesturesCommand",
			"addons": "onAddonStoreCommand",
			"about": "onAboutCommand",
			"profiles": "onConfigProfilesCommand",
			"logviewer": "onViewLogCommand",
			"exit": "onExitCommand",
			"welcome": "onWelcomeCommand",
		}
		name = actions.get(which)
		if not name:
			print("unknown dialog; choose from", sorted(actions))
			return
		wx.CallAfter(getattr(gui.mainFrame, name), None)
		print("opening", which)

	def v_menu(self, name="nvda-menu", letter=""):
		"""Pop the NVDA menu, optionally open the submenu for a letter, screenshot it, close it."""
		import gui

		def grabAndClose():
			pops = _popups()
			log.info("devhook menu: popups=%r" % (pops,))
			try:
				_grab(pops, name, pad=20)
			except Exception:
				log.exception("devhook menu grab failed")
			_user32.EndMenu()

		def openSub():
			owner = _user32.GetForegroundWindow()
			log.info("devhook menu: posting keys %r to owner %r" % (letter, owner))
			# Menu loops read the thread queue, so posted keys reach the open menu.
			# Arrow keys only (letters also arrive as WM_CHAR and fire twice).
			keys = {"down": 0x28, "up": 0x26, "right": 0x27, "left": 0x25}
			for k in letter.split(","):
				vk = keys[k.strip().lower()]
				_user32.PostMessageW(owner, 0x0100, vk, 0)
				_user32.PostMessageW(owner, 0x0101, vk, 0)
			self._later = wx.CallLater(700, grabAndClose)

		def popup():
			log.info("devhook menu: popping")
			self._later = wx.CallLater(600, openSub if letter else grabAndClose)
			gui.mainFrame.sysTrayIcon.onActivate(None)
			log.info("devhook menu: popup returned")

		wx.CallAfter(popup)
		print("popping menu")

	def v_dropdown(self, titlePart, index="0", name="dropdown"):
		"""Open the Nth combo box in the dialog, screenshot the dialog + list, close it."""
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		combos = [c for c in _walk(w) if isinstance(c, (wx.Choice, wx.ComboBox)) and c.IsShownOnScreen()]
		if not combos:
			print("no combo boxes shown")
			return
		c = combos[int(index) % len(combos)]
		hwnd = c.GetHandle()
		print("opening combo", index, "of", len(combos), "hwnd", hwnd)

		def close():
			_user32.SendMessageW(hwnd, 0x014F, 0, 0)  # CB_SHOWDROPDOWN off

		def grab():
			lists = []
			EnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

			@EnumProc
			def cb(h, _):
				buf = ctypes.create_unicode_buffer(64)
				_user32.GetClassNameW(h, buf, 64)
				if buf.value == "ComboLBox" and _user32.IsWindowVisible(h):
					lists.append(h)
				return True

			_user32.EnumWindows(cb, 0)
			log.info("devhook dropdown: lists=%r" % (lists,))
			try:
				_grab([w.GetHandle()] + lists, name)
			except Exception:
				log.exception("devhook dropdown grab failed")
			close()

		c.SetFocus()
		_user32.SendMessageW(hwnd, 0x014F, 1, 0)  # CB_SHOWDROPDOWN on
		self._later = wx.CallLater(700, grab)

	def v_shot(self, titlePart, name=""):
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		_grab([w.GetHandle()], name or w.GetTitle())

	def v_dump(self, titlePart):
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		_dump(w)

	def v_click(self, titlePart, label):
		"""Press the button with this label in the given dialog (e.g. Cancel)."""
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		want = label.replace("&", "").lower()
		for c in _walk(w):
			if isinstance(c, wx.Button) and c.IsShownOnScreen() and c.GetLabel().replace("&", "").lower() == want:
				evt = wx.CommandEvent(wx.EVT_BUTTON.typeId, c.GetId())
				evt.SetEventObject(c)
				wx.PostEvent(c, evt)
				print("clicked", label, "in", w.GetTitle())
				return
		print("no button", repr(label), "in", w.GetTitle())

	def v_close(self, titlePart):
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		wx.CallAfter(w.Close)
		print("closing", w.GetTitle())

	def v_hover(self, titlePart, label):
		"""Move the mouse over the control with this label in the dialog (to see hover styling)."""
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		want = label.replace("&", "").lower()
		for c in _walk(w):
			try:
				if c.GetLabel().replace("&", "").lower() == want:
					r = _hwndRect(c.GetHandle())
					_user32.SetCursorPos((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
					print("hovering", label)
					return
			except Exception:
				continue
		print("no control", repr(label))

	def v_probe(self, titlePart, types="ListCtrl,CheckListBox,ListBox,TreeCtrl,TextCtrl,Button,Notebook,CheckBox,RadioButton,StaticText,Choice"):
		"""Report actual pixel colours (background, text-ish, left edge) of controls in a dialog."""
		from PIL import ImageGrab
		from collections import Counter

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		wanted = tuple(getattr(wx, t) for t in types.split(",") if hasattr(wx, t))
		seen = 0
		for c in _walk(w):
			if not isinstance(c, wanted) or not c.IsShownOnScreen():
				continue
			l, t, r, b = _hwndRect(c.GetHandle())
			if r - l < 12 or b - t < 8:
				continue
			inner = ImageGrab.grab(bbox=(l + 4, t + 4, l + 4 + max(8, (r - l) * 6 // 10), t + 4 + max(8, (b - t) * 4 // 10)), all_screens=True)
			cnt = Counter(inner.get_flattened_data() if hasattr(inner, "get_flattened_data") else inner.getdata())
			bg = cnt.most_common(1)[0][0]
			text = [col for col, n in cnt.most_common(6) if col != bg][:2]
			edge = ImageGrab.grab(bbox=(l, t, l + 3, b), all_screens=True)
			edgeCols = [edge.getpixel((x, edge.height // 2)) for x in range(3)]
			try:
				label = c.GetLabel()[:28]
			except Exception:
				label = ""
			print(f"{type(c).__name__:14s} {label!r:32s} bg={bg} text={text} edge={edgeCols}")
			seen += 1
			if seen >= 40:
				print("...")
				break

	def v_rows(self, titlePart, count="4"):
		"""Pixel colours of the first rows of every list control in the dialog."""
		from PIL import ImageGrab
		from collections import Counter

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			if not isinstance(c, wx.ListCtrl) or not c.IsShownOnScreen():
				continue
			print(type(c).__name__, "items:", c.GetItemCount(), "focused:", c.HasFocus())
			for i in range(min(int(count), c.GetItemCount())):
				r = c.GetItemRect(i)
				tl = c.ClientToScreen(wx.Point(r.x, r.y))
				img = ImageGrab.grab(bbox=(tl.x + 2, tl.y + 1, tl.x + min(r.width, 400), tl.y + r.height - 1), all_screens=True)
				cnt = Counter(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
				print(f"  row {i}: {c.GetItemText(i)[:24]!r:28s} {cnt.most_common(3)}")

	def v_header(self, titlePart, name="header"):
		"""Screenshot + colours of the column header of the first list control in the dialog."""
		from PIL import ImageGrab
		from collections import Counter

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			if not isinstance(c, wx.ListCtrl) or not c.IsShownOnScreen():
				continue
			header = _user32.SendMessageW(c.GetHandle(), 0x101F, 0, 0)  # LVM_GETHEADER
			buf = ctypes.create_unicode_buffer(64)
			_user32.GetClassNameW(header, buf, 64)
			ex = _user32.SendMessageW(c.GetHandle(), 0x1037, 0, 0)  # LVM_GETEXTENDEDLISTVIEWSTYLE
			print(type(c).__name__, "header hwnd", header, buf.value, "visible", bool(_user32.IsWindowVisible(header)), "ex style", hex(ex), "gridlines", bool(ex & 0x1))
			if header:
				l, t, r, b = _hwndRect(header)
				img = ImageGrab.grab(bbox=(l, t, min(r, l + 900), b), all_screens=True)
				img.save(_shotPath(name))
				cnt = Counter(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
				print("  header colours:", cnt.most_common(5))
				# one row below the header, for grid lines
				r0 = c.GetItemRect(0) if c.GetItemCount() else None
				if r0:
					tl = c.ClientToScreen(wx.Point(r0.x, r0.y))
					row = ImageGrab.grab(bbox=(tl.x, tl.y, tl.x + 900, tl.y + r0.height), all_screens=True)
					cols = Counter(row.get_flattened_data() if hasattr(row, "get_flattened_data") else row.getdata())
					print("  row 0 colours:", cols.most_common(5))
					line = [row.getpixel((x, r0.height - 1)) for x in range(0, 900, 150)]
					print("  row 0 bottom line samples:", line)
			return

	def v_type(self, titlePart, text="Typed text"):
		"""Type into the first shown text box of the dialog (posted straight to the control)."""
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			if isinstance(c, wx.TextCtrl) and c.IsShownOnScreen() and c.IsEditable():
				c.SetFocus()
				for ch in text:
					_user32.PostMessageW(c.GetHandle(), 0x0102, ord(ch), 0)  # WM_CHAR
				print("typed into", repr(c.GetName()), "hwnd", c.GetHandle())
				return
		print("no editable text box shown")

	def v_refresh(self):
		self.plugin.engine.refresh()
		print("refreshed; active =", self.plugin.engine.active)

	def v_retheme(self):
		"""Force re-apply dark styling to every window (after editing theming constants)."""
		from . import theming

		theming.themeAllWindows(True, force=True)
		print("re-themed all windows")

	# --- plumbing ------------------------------------------------------------
	def _poll(self, event):
		if not os.path.exists(CMD):
			return
		try:
			with open(CMD, encoding="utf-8") as f:
				line = f.read().strip()
		finally:
			try:
				os.remove(CMD)
			except OSError:
				pass
		buf = io.StringIO()
		verb, _, rest = line.partition(" ")
		args = [a for a in rest.split("|")] if rest else []
		fn = getattr(self, "v_" + verb, None)
		import contextlib

		with contextlib.redirect_stdout(buf):
			if not fn:
				print("unknown verb", repr(verb), "; known:", [n[2:] for n in dir(self) if n.startswith("v_")])
			else:
				try:
					fn(*args)
				except Exception:
					traceback.print_exc(file=buf)
		with open(RESULT + ".tmp", "w", encoding="utf-8") as f:
			f.write(buf.getvalue())
		os.replace(RESULT + ".tmp", RESULT)
