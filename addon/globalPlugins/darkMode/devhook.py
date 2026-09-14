# Dark Mode: an NVDA add-on. Copyright (C) 2026 Carrie on Accessibility.
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, version 2.
# See the LICENSE file for details.
# DEVELOPMENT ONLY. Not shipped: build.py excludes this file from the package.
#
# Lets dev/nvda_exec.py ask the live NVDA to open its own dialogs, screenshot
# them and report control colours, so dark mode can be checked without
# injecting keystrokes into whatever window has focus. Deliberately NOT a
# general "run code" hook: only the fixed verbs below, screenshots only ever
# land in this add-on's own dev/shots folder.
#
# Protocol: dev/nvda_exec.py writes %TEMP%\darkMode-dev\cmd.txt with one
# line "verb arg1|arg2|..."; a timer here runs it and writes result.txt.

import ctypes
import io
import os
import re
import traceback

import wx
from logHandler import log

CMD_DIR = os.path.join(os.environ.get("TEMP", "."), "darkMode-dev")
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
		log.info("darkMode: dev hook active (fixed verbs), shots -> %s" % SHOTS_DIR)

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
			"update": "onCheckForUpdateCommand",
			"console": "onPythonConsoleCommand",
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

	def v_menupop(self):
		"""Pop the NVDA menu at the screen centre (as NVDA+N does) and close it after 900 ms.
		dev/flashcap.py films the screen from outside NVDA while this runs."""
		import gui

		sw = _user32.GetSystemMetrics(0)
		sh = _user32.GetSystemMetrics(1)
		_user32.SetCursorPos(sw // 2, sh // 2)

		def popup():
			self._later = wx.CallLater(900, _user32.EndMenu)
			gui.mainFrame.sysTrayIcon.onActivate(None)

		wx.CallAfter(popup)
		print("popping menu")

	def v_menuhook(self, state="on"):
		"""Turn the popup-menu dark-erase hook off/on (A/B test for dev/flashcap.py)."""
		from . import native

		if state.lower() == "off":
			native.removeMenuHook()
		else:
			native.installMenuHook()
		print("menu hook", "installed" if native._menuHook else "removed")

	def v_painttrace(self, verb="settings", arg="general", name="painttrace"):
		"""Open a dialog while logging, per created window: creation time, whether its parent
		was already on screen, first WM_ERASEBKGND / WM_PAINT / WM_CTLCOLOR* times, and when
		the engine's deferred re-theme ran. Answers "what painted light before we got to it?"."""
		import time
		from ctypes import wintypes

		comctl32 = ctypes.windll.comctl32
		SUBCLASSPROC = ctypes.WINFUNCTYPE(
			ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t
		)
		_Def = comctl32.DefSubclassProc
		_Def.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
		_Def.restype = ctypes.c_ssize_t
		_Set = comctl32.SetWindowSubclass
		_Set.argtypes = (wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t)
		_Rem = comctl32.RemoveWindowSubclass
		_Rem.argtypes = (wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t)
		t0 = time.perf_counter()
		lines = []
		seen = {}  # hwnd -> set of msgs already logged
		names = {}
		CTLCOLOR = {0x0133: "CTLCOLOREDIT", 0x0134: "CTLCOLORLISTBOX", 0x0135: "CTLCOLORBTN", 0x0138: "CTLCOLORSTATIC"}
		WATCH = {0x0014: "ERASEBKGND", 0x000F: "PAINT", 0x0018: "SHOWWINDOW", 0x0085: "NCPAINT", 0x031A: "THEMECHANGED"}

		def now():
			return time.perf_counter() - t0

		def sub(hwnd, msg, wParam, lParam, uId, ref):
			try:
				label = WATCH.get(msg) or CTLCOLOR.get(msg)
				if label and label not in seen.setdefault(hwnd, set()):
					seen[hwnd].add(label)
					extra = ""
					if msg in CTLCOLOR:
						extra = " for=%#x" % lParam
					lines.append("%7.1f ms  %-22s %s%s" % (now() * 1000, names.get(hwnd, "%#x" % hwnd), label, extra))
				if msg == 0x0082:  # NCDESTROY
					_Rem(hwnd, subProc, 98)
			except Exception:
				log.exception("painttrace sub")
			return _Def(hwnd, msg, wParam, lParam)

		subProc = SUBCLASSPROC(sub)
		self._keep = [subProc]

		def onCreate(evt):
			evt.Skip()
			w = evt.GetWindow()
			try:
				h = w.GetHandle()
				parent = w.GetParent()
				pshown = parent.IsShownOnScreen() if parent else None
				label = "%s[%s]" % (type(w).__name__, (w.GetLabel() or "")[:18].replace("\n", " ")) if hasattr(w, "GetLabel") else type(w).__name__
				names[h] = label
				lines.append("%7.1f ms  %-22s CREATED parentOnScreen=%s" % (now() * 1000, label, pshown))
				_Set(h, subProc, 98, 0)
				# the parent gets WM_CTLCOLOR* for this child; watch the parent too
				if parent and parent.GetHandle() not in names:
					names[parent.GetHandle()] = "%s(parent)" % type(parent).__name__
					_Set(parent.GetHandle(), subProc, 98, 0)
			except Exception:
				log.exception("painttrace create")

		engine = self.plugin.engine
		origReapply = engine._reapply

		def tracedReapply(win):
			try:
				lines.append("%7.1f ms  %-22s REAPPLY (deferred re-theme)" % (now() * 1000, names.get(win.GetHandle(), type(win).__name__)))
			except Exception:
				pass
			return origReapply(win)

		engine._reapply = tracedReapply
		app = wx.GetApp()
		app.Bind(wx.EVT_WINDOW_CREATE, onCreate)

		def finish():
			app.Unbind(wx.EVT_WINDOW_CREATE, handler=onCreate)
			engine._reapply = origReapply
			os.makedirs(SHOTS_DIR, exist_ok=True)
			with open(_shotPath(name + ".txt").replace(".png", ""), "w", encoding="utf-8") as f:
				f.write("\n".join(lines))
			log.info("painttrace: %d lines" % len(lines))

		self._later = wx.CallLater(4000, finish)
		lines.append("%7.1f ms  opening %s %s" % (now() * 1000, verb, arg))
		getattr(self, "v_" + verb)(arg)

	def v_census(self, seconds="3", name="census"):
		"""For N seconds, record every visible top-level window of this process that appears:
		hwnd, class, title, thread, whether wx knows it. Runs in a thread so the main thread is free."""
		import threading
		import time
		from ctypes import wintypes

		EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
		pid = os.getpid()
		seen = {}
		lines = []
		t0 = time.perf_counter()
		mainThread = ctypes.windll.kernel32.GetCurrentThreadId()

		def info(h):
			buf = ctypes.create_unicode_buffer(128)
			_user32.GetClassNameW(h, buf, 128)
			cls = buf.value
			_user32.GetWindowTextW(h, buf, 128)
			title = buf.value
			tid = _user32.GetWindowThreadProcessId(h, None)
			return cls, title, tid

		def poll():
			while time.perf_counter() - t0 < float(seconds):
				found = []

				@EnumProc
				def cb(h, _):
					p = wintypes.DWORD()
					_user32.GetWindowThreadProcessId(h, ctypes.byref(p))
					if p.value == pid and _user32.IsWindowVisible(h):
						found.append(h)
					return True

				_user32.EnumWindows(cb, 0)
				for h in found:
					if h not in seen:
						cls, title, tid = info(h)
						seen[h] = True
						lines.append("%6.0f ms hwnd=%#x class=%r title=%r thread=%s" % ((time.perf_counter() - t0) * 1000, h, cls, title, "main" if tid == mainThread else tid))
				time.sleep(0.02)
			os.makedirs(SHOTS_DIR, exist_ok=True)
			with open(_shotPath(name + ".txt").replace(".png", ""), "w", encoding="utf-8") as f:
				f.write("\n".join(lines))

		threading.Thread(target=poll, daemon=True).start()
		print("census running for", seconds, "s")

	def v_commands(self):
		"""List the on*Command handlers NVDA's main frame offers (for the dialog verb)."""
		import gui

		print(sorted(n for n in dir(gui.mainFrame) if n.startswith("on") and n.endswith("Command")))
		try:
			import gui.startupDialogs as sd

			print("startupDialogs:", [n for n in dir(sd) if "Dialog" in n])
		except Exception as e:
			print("startupDialogs:", e)

	def v_boxtrace(self, name="boxtrace"):
		"""Open the Welcome dialog while logging every group-box draw: when, which message,
		where the box was, whether its dialog was visible. Finds draws at stale positions."""
		import time

		from . import native
		from gui.startupDialogs import WelcomeDialog

		t0 = time.perf_counter()
		lines = []
		orig = native._drawStaticBox

		def traced(hwnd, hdc, excludeChildren=True):
			r = _RECT()
			_user32.GetWindowRect(hwnd, ctypes.byref(r))
			top = _user32.GetAncestor(hwnd, 2)  # GA_ROOT
			lines.append("%7.1f ms box=%#x rect=(%d,%d %dx%d) erase=%s topVisible=%s" % (
				(time.perf_counter() - t0) * 1000, hwnd, r.l, r.t, r.r - r.l, r.b - r.t, not excludeChildren, bool(_user32.IsWindowVisible(top))))
			return orig(hwnd, hdc, excludeChildren)

		native._drawStaticBox = traced
		origClean = native._cleanUpAfterBoxMove

		def tracedClean(hwnd):
			before = native._boxRects.get(hwnd)
			origClean(hwnd)
			lines.append("%7.1f ms CLEANUP box=%#x old=%r new=%r" % ((time.perf_counter() - t0) * 1000, hwnd, before, native._boxRects.get(hwnd)))

		native._cleanUpAfterBoxMove = tracedClean

		def finish():
			native._drawStaticBox = orig
			native._cleanUpAfterBoxMove = origClean
			os.makedirs(SHOTS_DIR, exist_ok=True)
			with open(_shotPath(name + ".txt").replace(".png", ""), "w", encoding="utf-8") as f:
				f.write(chr(10).join(lines))

		self._later = wx.CallLater(4000, finish)
		wx.CallAfter(WelcomeDialog.run)
		print("box trace running")

	def v_mirror(self, _arg=""):
		"""Open the Set NVDA Update Mirror dialog (Settings > General > Change...)."""
		self.v_click("NVDA Settings", "Change...")

	def v_mode(self, mode="dark"):
		"""Set the add-on mode (dark|off) and apply it, like the settings panel does."""
		import globalPlugins.darkMode as pkg

		pkg.setMode(mode)
		print("mode", mode, "-> active", self.plugin.engine.active)

	def v_marks(self, titlePart):
		"""Show the theming state stored on each control of a dialog (what restore would put back)."""
		from . import theming

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		n = 0
		for c in _walk(w):
			st = theming._states.get(c.GetHandle())
			desc = None
			if st:
				desc = {k: (v.GetAsString(wx.C2S_HTML_SYNTAX) if v is not None else None) for k, v in st.items()}
			print(f"{type(c).__name__:28s} own={c.UseBackgroundColour()} bg={c.GetBackgroundColour().GetAsString(wx.C2S_HTML_SYNTAX)} mark={desc}")
			n += 1
			if n >= 80:
				break

	def v_lvcolors(self, titlePart):
		"""Raw list-view colour settings (LVM_GETBKCOLOR / TEXTCOLOR / TEXTBKCOLOR) of each list in a dialog."""
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			if isinstance(c, wx.ListCtrl):
				h = c.GetHandle()
				vals = [(_user32.SendMessageW(h, m, 0, 0) & 0xFFFFFFFF) for m in (0x1000, 0x1023, 0x1025)]
				names = {0xFF000000: "CLR_DEFAULT", 0xFFFFFFFF: "CLR_NONE"}
				print(type(c).__name__, "bk=%s text=%s textbk=%s" % tuple(names.get(v, "#%06X" % v) for v in vals), "theme?", "wxbg", c.GetBackgroundColour().GetAsString(wx.C2S_HTML_SYNTAX))

	def v_richtrace(self, category="speech", name="richtrace"):
		"""Open a settings category and log every message reaching rich edit controls created
		meanwhile, plus each time the add-on applies rich colours. Finds what resets the text colour."""
		import time
		from ctypes import wintypes

		from . import native

		comctl32 = ctypes.windll.comctl32
		SUBCLASSPROC = ctypes.WINFUNCTYPE(
			ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t
		)
		_Def = comctl32.DefSubclassProc
		_Def.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
		_Def.restype = ctypes.c_ssize_t
		_Set = comctl32.SetWindowSubclass
		_Set.argtypes = (wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t)
		t0 = time.perf_counter()
		lines = []
		NAMES = {0xC: "WM_SETTEXT", 0x461: "EM_SETTEXTEX", 0xC2: "EM_REPLACESEL", 0x449: "EM_STREAMIN", 0x30: "WM_SETFONT",
			0x444: "EM_SETCHARFORMAT", 0x443: "EM_SETBKGNDCOLOR", 0x31A: "WM_THEMECHANGED", 0xCF: "EM_SETREADONLY",
			0x45D: "EM_SETLANGOPTIONS", 0x44D: "EM_SETPARAFORMAT", 0xB1: "EM_SETSEL", 0x18: "WM_SHOWWINDOW", 0x0A: "WM_ENABLE",
			0x4CE: "EM_SETEDITSTYLE", 0x0405: "EM_SETRECT"}

		def sub(hwnd, msg, w, l, uid, ref):
			nm = NAMES.get(msg)
			if nm:
				extra = ""
				if msg == 0x444 and l:
					cf = native.CHARFORMATW.from_address(l)
					extra = " mask=%#x effects=%#x colour=%#06x" % (cf.dwMask & 0xFFFFFFFF, cf.dwEffects & 0xFFFFFFFF, cf.crTextColor & 0xFFFFFF)
				lines.append("%7.1f ms %#x %s w=%#x%s" % ((time.perf_counter() - t0) * 1000, hwnd, nm, w & 0xFFFFFFFF, extra))
			return _Def(hwnd, msg, w, l)

		subProc = SUBCLASSPROC(sub)
		self._keep = [subProc]
		origApply = native.applyRichColours

		def tracedApply(hwnd, textRgb, bgRgb):
			lines.append("%7.1f ms %#x APPLY rich colours text=%s" % ((time.perf_counter() - t0) * 1000, hwnd, textRgb))
			return origApply(hwnd, textRgb, bgRgb)

		native.applyRichColours = tracedApply

		def onCreate(evt):
			evt.Skip()
			w = evt.GetWindow()
			try:
				h = w.GetHandle()
				if native.isRichEdit(h):
					lines.append("%7.1f ms %#x CREATED %s" % ((time.perf_counter() - t0) * 1000, h, type(w).__name__))
					_Set(h, subProc, 96, 0)
			except Exception:
				pass

		app = wx.GetApp()
		app.Bind(wx.EVT_WINDOW_CREATE, onCreate)

		def finish():
			app.Unbind(wx.EVT_WINDOW_CREATE, handler=onCreate)
			native.applyRichColours = origApply
			os.makedirs(SHOTS_DIR, exist_ok=True)
			with open(_shotPath(name + ".txt").replace(".png", ""), "w", encoding="utf-8") as f:
				f.write(chr(10).join(lines))

		self._later = wx.CallLater(5000, finish)
		if category.startswith("category:"):
			self.v_category(category.split(":", 1)[1])
		else:
			self.v_settings(category)

	def v_richinfo(self, titlePart):
		"""Rich edit controls in a dialog: default and whole-text character colour, auto-colour effect, styles."""
		from . import native

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			try:
				h = c.GetHandle()
			except Exception:
				continue
			if not native.isRichEdit(h):
				continue
			cf = native.CHARFORMATW()
			cf.cbSize = ctypes.sizeof(cf)
			native._SendMessageW(h, 0x043A, 0, ctypes.addressof(cf))  # EM_GETCHARFORMAT, SCF_DEFAULT
			d = (cf.dwMask & 0xFFFFFFFF, cf.dwEffects & 0xFFFFFFFF, cf.crTextColor & 0xFFFFFF)
			_user32.SendMessageW(h, 0x00B1, 0, -1)  # EM_SETSEL all
			cf2 = native.CHARFORMATW()
			cf2.cbSize = ctypes.sizeof(cf2)
			native._SendMessageW(h, 0x043A, 1, ctypes.addressof(cf2))  # SCF_SELECTION
			_user32.SendMessageW(h, 0x00B1, 0, 0)
			sel = (cf2.dwMask & 0xFFFFFFFF, cf2.dwEffects & 0xFFFFFFFF, cf2.crTextColor & 0xFFFFFF)
			print("%s %#x text=%r default(mask=%#x effects=%#x colour=%#06x) selection(mask=%#x effects=%#x colour=%#06x) autocolor=%s" % (
				type(c).__name__, h, c.GetValue()[:30], d[0], d[1], d[2], sel[0], sel[1], sel[2], bool(sel[1] & 0x40000000)))

	def v_category(self, name):
		"""Switch the open NVDA Settings dialog to a category by selecting it in the list (as arrow keys do)."""
		w = _findTLW("NVDA Settings")
		if not w:
			print("Settings dialog is not open")
			return
		lst = w.catListCtrl
		for i in range(lst.GetItemCount()):
			if name.lower() in lst.GetItemText(i).lower():
				lst.Select(i)
				lst.Focus(i)
				print("selected category", lst.GetItemText(i))
				return
		print("no category containing", repr(name))

	def v_tipshot(self, name="tooltip"):
		"""Screenshot every visible tooltip window of this process (hover something first)."""
		from ctypes import wintypes

		EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
		pid = os.getpid()
		found = []

		@EnumProc
		def cb(h, _):
			p = wintypes.DWORD()
			_user32.GetWindowThreadProcessId(h, ctypes.byref(p))
			buf = ctypes.create_unicode_buffer(64)
			_user32.GetClassNameW(h, buf, 64)
			if p.value == pid and _user32.IsWindowVisible(h) and buf.value == "tooltips_class32":
				found.append(h)
			return True

		_user32.EnumWindows(cb, 0)
		if not found:
			print("no visible tooltip")
			return
		_grab(found, name, pad=4)

	def v_hoveritem(self, name):
		"""Move the mouse onto the Settings category whose name contains the text."""
		w = _findTLW("NVDA Settings")
		if not w:
			print("Settings dialog is not open")
			return
		lst = w.catListCtrl
		for i in range(lst.GetItemCount()):
			if name.lower() in lst.GetItemText(i).lower():
				lst.EnsureVisible(i)
				r = lst.GetItemRect(i)
				pt = lst.ClientToScreen(wx.Point(r.x + r.width // 2, r.y + r.height // 2))
				_user32.SetCursorPos(pt.x, pt.y)
				print("hovering", lst.GetItemText(i), "at", pt.x, pt.y)
				return
		print("no category containing", repr(name))

	def v_tipinfo(self, titlePart):
		"""For each list in a dialog: its tooltip window, class, and whether the dark theme applies (HRESULT)."""
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			if isinstance(c, wx.ListCtrl):
				tip = _user32.SendMessageW(c.GetHandle(), 0x1000 + 78, 0, 0)
				buf = ctypes.create_unicode_buffer(64)
				_user32.GetClassNameW(tip, buf, 64)
				hr = ctypes.windll.uxtheme.SetWindowTheme(tip, "DarkMode_Explorer", None)
				print(type(c).__name__, "tooltip hwnd=%#x class=%r SetWindowTheme->%#x visible=%s" % (tip, buf.value, hr & 0xFFFFFFFF, bool(_user32.IsWindowVisible(tip))))

	def v_tippop(self, name="tooltip"):
		"""Hover the first truncated category, force its tooltip to pop (TTM_POPUP) and screenshot it."""
		w = _findTLW("NVDA Settings")
		if not w:
			print("Settings dialog is not open")
			return
		lst = w.catListCtrl
		tip = _user32.SendMessageW(lst.GetHandle(), 0x1000 + 78, 0, 0)
		target = None
		for i in range(lst.GetItemCount()):
			if "Document Formatting" in lst.GetItemText(i):
				target = i
				break
		if target is None:
			print("no truncated item found")
			return
		lst.EnsureVisible(target)
		r = lst.GetItemRect(target)
		pt = lst.ClientToScreen(wx.Point(r.x + r.width // 2, r.y + r.height // 2))
		_user32.SetCursorPos(pt.x, pt.y)

		def pop():
			_user32.SendMessageW(tip, 0x0400 + 34, 0, 0)  # TTM_POPUP
			wx.CallLater(400, shoot)

		def shoot():
			if _user32.IsWindowVisible(tip):
				rc = _hwndRect(tip)
				print("tooltip rect", rc)
				_grab([tip], name, pad=4)
			else:
				print("tooltip not visible")

		wx.CallLater(700, pop)
		print("popping tooltip")

	def v_classinfo(self, titlePart, typeName):
		"""Python class hierarchy (MRO) of controls of a given type name in a dialog, plus parent subclass ids."""
		from . import native

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			if typeName.lower() in type(c).__name__.lower() or any(typeName.lower() in b.__name__.lower() for b in type(c).__mro__):
				mro = [b.__name__ for b in type(c).__mro__][:6]
				parent = c.GetParent()
				print(type(c).__name__, mro, "isCheckListBox=%s" % isinstance(c, wx.CheckListBox), "parentSubclass=%s" % native._subclassed.get(parent.GetHandle() if parent else 0), "registered=%s" % (c.GetHandle() in native._checkLists))

	AUDIT_TYPES = ("StaticText", "TextCtrl", "CheckBox", "RadioButton", "Button", "Choice", "ComboBox", "ListCtrl",
		"ListBox", "CheckListBox", "TreeCtrl", "SpinCtrl", "SpinCtrlDouble", "StaticBox", "Notebook", "RadioBox")

	def v_audit(self, titlePart, showAll="0"):
		"""Flag controls in a dialog whose pixels look like dark text on a dark background, or a
		light background. Prints only offenders (and a count) unless showAll=1."""
		from PIL import ImageGrab
		from collections import Counter

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		wanted = tuple(getattr(wx, n) for n in self.AUDIT_TYPES if hasattr(wx, n))
		L, T, R, B = _hwndRect(w.GetHandle())
		checked = flagged = 0
		for c in _walk(w):
			if not isinstance(c, wanted) or not c.IsShownOnScreen():
				continue
			l, t, r, b = _hwndRect(c.GetHandle())
			# clip to the dialog (scrolled panels hide the rest)
			l, t, r, b = max(l, L), max(t, T), min(r, R), min(b, B)
			# and to the visible part of a scrolled container
			parent = c.GetParent()
			while parent is not None and parent is not w:
				pl, pt, pr, pb = _hwndRect(parent.GetHandle())
				l, t, r, b = max(l, pl), max(t, pt), min(r, pr), min(b, pb)
				parent = parent.GetParent()
			if r - l < 14 or b - t < 10:
				continue
			img = ImageGrab.grab(bbox=(l + 2, t + 2, r - 2, b - 2), all_screens=True)
			px = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
			cnt = Counter(px)
			bg = cnt.most_common(1)[0][0]
			nearBlack = sum(n for col, n in cnt.items() if max(col) <= 12)
			light = sum(n for col, n in cnt.items() if min(col) >= 200)
			total = len(px)
			checked += 1
			try:
				label = c.GetLabel()[:30]
			except Exception:
				label = ""
			problems = []
			if max(bg) < 90 and nearBlack > 25 and nearBlack < total * 0.9:
				problems.append("DARK TEXT ON DARK (%d px)" % nearBlack)
			if min(bg) >= 200:
				problems.append("LIGHT BACKGROUND %s" % (bg,))
			if problems or showAll == "1":
				flagged += bool(problems)
				print(f"{'!! ' if problems else '   '}{type(c).__name__:26s} {label!r:32s} bg={bg} {'; '.join(problems)}")
		print(f"audited {checked} controls, {flagged} flagged")

	def v_categories(self):
		"""List the titles of NVDA's settings categories."""
		from gui.settingsDialogs import NVDASettingsDialog

		print("|".join(c.title for c in NVDASettingsDialog.categoryClasses))

	def v_scroll(self, titlePart, y="100000"):
		"""Scroll the open Settings dialog's panel container to a vertical position (0 = top)."""
		w = _findTLW(titlePart)
		if not w or not hasattr(w, "container"):
			print("no settings dialog")
			return
		w.container.Scroll(0, int(y))
		print("scrolled")

	def v_clbtrace(self, titlePart):
		"""Repaint the check lists in a dialog while logging each owner-draw call and its outcome."""
		from . import native

		lines = []
		orig = native._paintCheckItem

		def traced(dis):
			ref = native._checkLists.get(dis.hwndItem)
			win = ref() if ref else None
			try:
				res = orig(dis)
				lines.append("item=%d hwnd=%#x win=%s -> %s" % (dis.itemID, dis.hwndItem, type(win).__name__ if win else None, res))
			except Exception as e:
				lines.append("item=%d EXC %r" % (dis.itemID, e))
				raise
			return res

		native._paintCheckItem = traced
		w = _findTLW(titlePart)
		n = 0
		for c in _walk(w) if w else []:
			if isinstance(c, wx.CheckListBox) and c.IsShownOnScreen():
				_user32.RedrawWindow(c.GetHandle(), None, None, 0x1 | 0x4 | 0x100)
				n += 1

		def finish():
			native._paintCheckItem = orig
			os.makedirs(SHOTS_DIR, exist_ok=True)
			with open(_shotPath("clbtrace.txt").replace(".png", ""), "w", encoding="utf-8") as f:
				f.write("lists repainted: %d%s%s" % (n, chr(10), chr(10).join(lines[:30]) or "(no owner-draw calls reached the painter)"))

		self._later = wx.CallLater(800, finish)
		print("tracing; see clbtrace.txt")

	def v_radioinfo(self, titlePart):
		"""Native radio buttons inside wx.RadioBox controls: class, style, theme handle, label pixels."""
		from PIL import ImageGrab
		from collections import Counter

		from . import theming

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		for c in _walk(w):
			if isinstance(c, wx.RadioBox):
				print("RadioBox", repr(c.GetLabel()), "hwnd=%#x parent=%#x siblings-found=%r" % (c.GetHandle(), _user32.GetParent(c.GetHandle()), [hex(h) for h in theming._radioBoxButtons(c.GetHandle())]))
				l, t, r, b = _hwndRect(c.GetHandle())
				print("   box rect", (l, t, r, b))
				for h in theming._nativeChildren(_user32.GetParent(c.GetHandle())):
					buf = ctypes.create_unicode_buffer(64)
					_user32.GetClassNameW(h, buf, 64)
					cls = buf.value
					_user32.GetWindowTextW(h, buf, 64)
					txt = buf.value
					st = _user32.GetWindowLongW(h, -16) & 0xFFFFFFFF
					theme = ctypes.windll.uxtheme.GetWindowTheme(h)
					l, t, r, b = _hwndRect(h)
					img = ImageGrab.grab(bbox=(l + 30, t + 2, r - 2, b - 2), all_screens=True)
					cnt = Counter(img.getdata()).most_common(3)
					print("   %#x %s %r style=%#x theme=%#x parent=%#x pixels=%s" % (h, cls, txt, st, theme, _user32.GetParent(h), cnt))

	def v_ctlcolor(self, titlePart):
		"""Ask a dialog what text colour it answers for each native Button child (WM_CTLCOLORSTATIC)."""
		from . import native, theming

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		parent = w.GetHandle()
		for h in theming._nativeChildren(parent):
			buf = ctypes.create_unicode_buffer(64)
			_user32.GetClassNameW(h, buf, 64)
			if buf.value != "Button":
				continue
			_user32.GetWindowTextW(h, buf, 64)
			txt = buf.value
			hdc = native._GetDC(h)
			try:
				brush = native._SendMessageW(_user32.GetParent(h), 0x0138, hdc, h)
				tc = ctypes.windll.gdi32.GetTextColor(hdc) & 0xFFFFFF
				bk = ctypes.windll.gdi32.GetBkColor(hdc) & 0xFFFFFF
			finally:
				native._ReleaseDC(h, hdc)
			print("%#x %r style=%#x -> brush=%#x textColour=%#06x bk=%#06x" % (h, txt, _user32.GetWindowLongW(h, -16) & 0xFF, brush, tc, bk))

	def v_slidersim(self, titlePart, name="slider-sim"):
		"""Send the first slider WM_MOUSEMOVE over its thumb, then WM_MOUSELEAVE, measuring the thumb each time."""
		from PIL import ImageGrab
		from collections import Counter

		from . import native

		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		sl = next((c for c in _walk(w) if isinstance(c, wx.Slider) and c.IsShownOnScreen()), None)
		if not sl:
			print("no slider")
			return
		h = sl.GetHandle()
		rc = native.RECT()
		native._SendMessageW(h, 0x0400 + 25, 0, ctypes.addressof(rc))  # TBM_GETTHUMBRECT
		cx, cy = (rc.left + rc.right) // 2, (rc.top + rc.bottom) // 2
		l, t, r, b = _hwndRect(h)

		def measure(tag):
			img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
			print(tag, Counter(img.getdata()).most_common(4))

		import time

		measure("idle:  ")
		native._SendMessageW(h, 0x0200, 0, (cy << 16) | cx)  # WM_MOUSEMOVE over the thumb
		_user32.UpdateWindow(h)
		time.sleep(0.15)
		measure("hover: ")
		native._SendMessageW(h, 0x02A3, 0, 0)  # WM_MOUSELEAVE
		_user32.UpdateWindow(h)
		time.sleep(0.15)
		measure("leave: ")
		print("thumb rect", (rc.left, rc.top, rc.right, rc.bottom))

	def v_welcome(self):
		"""Open NVDA's Welcome dialog the way Help > Welcome does."""
		from gui.startupDialogs import WelcomeDialog

		wx.CallAfter(WelcomeDialog.run)
		print("opening welcome")

	def v_menutrace(self, name="menutrace"):
		"""Pop the NVDA menu with a thread-local CBT hook that subclasses the popup menu
		window (#32768) and logs every message it gets, with timestamps, to dev/shots/<name>.txt."""
		import threading
		import time
		from ctypes import wintypes

		import gui

		comctl32 = ctypes.windll.comctl32
		SUBCLASSPROC = ctypes.WINFUNCTYPE(
			ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t
		)
		CBTPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
		_DefSubclassProc = comctl32.DefSubclassProc
		_DefSubclassProc.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
		_DefSubclassProc.restype = ctypes.c_longlong
		_SetWindowSubclass = comctl32.SetWindowSubclass
		_SetWindowSubclass.argtypes = (wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t)
		_CallNextHookEx = _user32.CallNextHookEx
		_CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
		_CallNextHookEx.restype = ctypes.c_longlong
		_SetWindowsHookExW = _user32.SetWindowsHookExW
		_SetWindowsHookExW.argtypes = (ctypes.c_int, CBTPROC, wintypes.HINSTANCE, wintypes.DWORD)
		_SetWindowsHookExW.restype = wintypes.HHOOK
		WH_CBT = 5
		HCBT_CREATEWND = 3
		t0 = time.perf_counter()
		lines = []
		state = {"hook": None}

		def clsName(h):
			buf = ctypes.create_unicode_buffer(64)
			_user32.GetClassNameW(h, buf, 64)
			return buf.value

		def sub(hwnd, msg, wParam, lParam, uId, ref):
			try:
				lines.append("%7.3f hwnd=%#x msg=%#06x w=%#x l=%#x" % (time.perf_counter() - t0, hwnd, msg, wParam & 0xFFFFFFFF, lParam & 0xFFFFFFFF))
				if msg == 0x000F:  # WM_PAINT: how long does the default paint take?
					t1 = time.perf_counter()
					res = _DefSubclassProc(hwnd, msg, wParam, lParam)
					lines.append("%7.3f   WM_PAINT default took %.1f ms" % (time.perf_counter() - t0, (time.perf_counter() - t1) * 1000))
					return res
			except Exception:
				log.exception("menutrace sub")
			return _DefSubclassProc(hwnd, msg, wParam, lParam)

		subProc = SUBCLASSPROC(sub)
		self._keep = [subProc]

		def cbt(code, wParam, lParam):
			try:
				if code == HCBT_CREATEWND and clsName(wParam) == "#32768":
					lines.append("%7.3f CBT create popup hwnd=%#x" % (time.perf_counter() - t0, wParam))
					_SetWindowSubclass(wParam, subProc, 99, 0)
			except Exception:
				log.exception("menutrace cbt")
			return _CallNextHookEx(state["hook"], code, wParam, lParam)

		cbtProc = CBTPROC(cbt)
		self._keep.append(cbtProc)

		def finish():
			_user32.EndMenu()
			lines.append("%7.3f EndMenu called" % (time.perf_counter() - t0))

		def popup():
			state["hook"] = _SetWindowsHookExW(WH_CBT, cbtProc, None, ctypes.windll.kernel32.GetCurrentThreadId())
			lines.append("%7.3f hook=%r" % (time.perf_counter() - t0, state["hook"]))
			self._later = wx.CallLater(700, finish)
			lines.append("%7.3f popping" % (time.perf_counter() - t0))
			gui.mainFrame.sysTrayIcon.onActivate(None)
			lines.append("%7.3f popup returned" % (time.perf_counter() - t0))
			_user32.UnhookWindowsHookEx(state["hook"])
			os.makedirs(SHOTS_DIR, exist_ok=True)
			with open(_shotPath(name + ".txt").replace(".png", ""), "w", encoding="utf-8") as f:
				f.write("\n".join(lines))

		wx.CallAfter(popup)
		print("menu trace started")

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

	def v_hoverat(self, titlePart, dx, dy):
		"""Move the mouse to (dx, dy) pixels from the dialog's top-left (e.g. onto a scrollbar)."""
		w = _findTLW(titlePart)
		if not w:
			print("no shown window with title containing", repr(titlePart))
			return
		r = _hwndRect(w.GetHandle())
		_user32.SetCursorPos(r[0] + int(dx), r[1] + int(dy))
		print("hovering at", dx, dy)

	def v_probe(self, titlePart, types="ListCtrl,CheckListBox,ListBox,TreeCtrl,TextCtrl,Button,Notebook,CheckBox,RadioButton,StaticText,Choice"):
		"""Report actual pixel colours (background, text-ish, left edge) of controls in a dialog."""
		from . import native
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
			print(f"{type(c).__name__:14s} {label!r:32s} bg={bg} text={text} edge={edgeCols} rect={(l, t, r - l, b - t)} best={tuple(c.GetBestSize())} size={tuple(c.GetSize())} style={_user32.GetWindowLongW(c.GetHandle(), -16) & 0xFFFFFFFF:#x} ex={_user32.GetWindowLongW(c.GetHandle(), -20) & 0xFFFFFFFF:#x} subclass={native._subclassed.get(c.GetHandle())} parent={type(c.GetParent()).__name__}")
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
