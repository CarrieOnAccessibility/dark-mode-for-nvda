# Dark Mode: an NVDA add-on. Copyright (C) 2026 Carrie on Accessibility.
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, version 2.
# See the LICENSE file for details.
# Dark mode engine for the NVDA wxPython interface.
#
# NVDA draws its windows with wxPython 4.2 (wxWidgets 3.2), which has no dark
# mode support on Windows. This module reaches past wx and talks to Windows
# directly, using the same tricks File Explorer and many third-party apps use:
#
#   1. uxtheme undocumented SetPreferredAppMode / FlushMenuThemes to make
#      popup menus (the NVDA menu, right-click menus) dark.
#   2. DwmSetWindowAttribute to make title bars dark.
#   3. SetWindowTheme(hwnd, "DarkMode_Explorer") so buttons, scrollbars, lists
#      and trees use the dark visuals Windows already ships for Explorer.
#   4. Recolouring the wx windows that wx paints itself (panels, labels, fields).
#
# Accessibility rule that must never be broken here: NEVER set a foreground
# colour on wx.CheckBox / wx.RadioButton / wx.Button (or let one inherit from
# its parent). wxWidgets turns such controls into BS_OWNERDRAW, and MSAA/UIA
# then report them as plain "button" with no checked state, which would break
# NVDA reading its own settings. Containers therefore use SetOwn*Colour, which
# does not propagate to children.

import ctypes
from ctypes import wintypes
import winreg

import wx

try:
	from . import native, themes
except ImportError:  # imported as a plain module by the dev test bench
	import native
	import themes

try:
	from logHandler import log
except ImportError:  # running outside NVDA (test bench)
	import logging

	log = logging.getLogger("darkMode")

# --- Palette ----------------------------------------------------------------
# Windows 11 dark: app background #202020, raised surfaces #2b2b2b, text white.
# BG and LIST_BG follow the Background setting (themes.py); setBackground() below sets
# them and the matching constants in native.py. The accent colours live in native.py
# only and follow the Accent setting through setAccent().
BG = wx.Colour(0x20, 0x20, 0x20)  # dialog background: seeded from the default Background at import
LIST_BG = wx.Colour(0x2B, 0x2B, 0x2B)  # lists and trees: likewise
FIELD_BG = wx.Colour(0x2B, 0x2B, 0x2B)  # text fields, dropdowns, spin boxes: the same under every Background
FG = wx.Colour(0xFF, 0xFF, 0xFF)
_background = None  # the current themes.Background
_accent = None  # the current themes.Accent
_brightContrast = False  # selected rows in the accent colour itself, with black text

# --- Win32 plumbing ---------------------------------------------------------
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_uxtheme = ctypes.WinDLL("uxtheme", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

_SetWindowTheme = _uxtheme.SetWindowTheme
_SetWindowTheme.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
_SetWindowTheme.restype = ctypes.c_long

_DwmSetWindowAttribute = _dwmapi.DwmSetWindowAttribute
_DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
_DwmSetWindowAttribute.restype = ctypes.c_long

_SendMessage = _user32.SendMessageW
_SendMessage.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_SendMessage.restype = ctypes.c_ssize_t

_GetClassName = _user32.GetClassNameW
_GetClassName.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_GetClassName.restype = ctypes.c_int

_IsWindow = _user32.IsWindow
_IsWindow.argtypes = (wintypes.HWND,)
_IsWindow.restype = wintypes.BOOL

_GetWindow = _user32.GetWindow
_GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
_GetWindow.restype = wintypes.HWND
_GetParent = _user32.GetParent
_GetParent.argtypes = (wintypes.HWND,)
_GetParent.restype = wintypes.HWND
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_GetWindowLong = _user32.GetWindowLongW
_GetWindowLong.argtypes = (wintypes.HWND, ctypes.c_int)
_GetWindowLong.restype = ctypes.c_long
_EnumChildProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_EnumChildWindows = _user32.EnumChildWindows
_EnumChildWindows.argtypes = (wintypes.HWND, _EnumChildProc, wintypes.LPARAM)
_EnumChildWindows.restype = wintypes.BOOL

WM_THEMECHANGED = 0x031A
LVM_SETBKCOLOR = 0x1000 + 1
LVM_GETHEADER = 0x1000 + 31
LVM_GETTOOLTIPS = 0x1000 + 78
LVM_SETTEXTCOLOR = 0x1000 + 36
LVM_SETTEXTBKCOLOR = 0x1000 + 38
TVM_SETBKCOLOR = 0x1100 + 29
TVM_SETTEXTCOLOR = 0x1100 + 30
CLR_DEFAULT = 0xFF000000
SPI_GETHIGHCONTRAST = 0x0042
HCF_HIGHCONTRASTON = 0x0001


class _HIGHCONTRAST(ctypes.Structure):
	_fields_ = (("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD), ("lpszDefaultScheme", wintypes.LPWSTR))


def _winBuild() -> int:
	try:
		with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
			return int(winreg.QueryValueEx(k, "CurrentBuildNumber")[0])
	except OSError:
		return 0


WIN_BUILD = _winBuild()


def _ordinal(n: int, restype, *argtypes):
	"""Fetch an undocumented uxtheme export by ordinal. Returns None if missing."""
	try:
		f = _uxtheme[n]
	except (AttributeError, OSError):
		return None
	f.restype = restype
	f.argtypes = argtypes
	return f


# Ordinal layout is for Windows 10 1903 (build 18362) and later. On older builds
# ordinal 135 is a different function (AllowDarkModeForApp), so gate on build.
if WIN_BUILD >= 18362:
	_SetPreferredAppMode = _ordinal(135, ctypes.c_int, ctypes.c_int)
	_FlushMenuThemes = _ordinal(136, None)
	_AllowDarkModeForWindow = _ordinal(133, wintypes.BOOL, wintypes.HWND, wintypes.BOOL)
	_RefreshImmersiveColorPolicyState = _ordinal(104, None)
else:
	_SetPreferredAppMode = _FlushMenuThemes = _AllowDarkModeForWindow = _RefreshImmersiveColorPolicyState = None

APPMODE_DEFAULT = 0
APPMODE_ALLOW_DARK = 1
APPMODE_FORCE_DARK = 2
APPMODE_FORCE_LIGHT = 3

# DWMWA_USE_IMMERSIVE_DARK_MODE: 20 from build 19041, 19 on the 18985-19040 insider range.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20 if WIN_BUILD >= 19041 else 19
# Windows 11 lets an app pick its own window border colour.
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWA_COLOR_DEFAULT = 0xFFFFFFFF
WINDOW_BORDER = wx.Colour(0x8C, 0x8C, 0x8C)  # one-pixel ring around every NVDA dialog: same grey as the layout lines
TITLE_BG = wx.Colour(0x00, 0x00, 0x00)  # title bars: black (Windows 11 only; older builds keep the dark-mode grey)
TITLE_FG = wx.Colour(0xFF, 0xFF, 0xFF)


# --- System state -----------------------------------------------------------
def systemUsesDarkApps() -> bool:
	"""True when the Windows default app mode is set to Dark."""
	try:
		with winreg.OpenKey(
			winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
		) as k:
			return int(winreg.QueryValueEx(k, "AppsUseLightTheme")[0]) == 0
	except OSError:
		return False


def highContrastActive() -> bool:
	hc = _HIGHCONTRAST()
	hc.cbSize = ctypes.sizeof(hc)
	if not _user32.SystemParametersInfoW(SPI_GETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc), 0):
		return False
	return bool(hc.dwFlags & HCF_HIGHCONTRASTON)


# --- Per-window theming -----------------------------------------------------
def _colorref(c: wx.Colour) -> int:
	return c.Red() | (c.Green() << 8) | (c.Blue() << 16)


def _className(hwnd) -> str:
	buf = ctypes.create_unicode_buffer(256)
	_GetClassName(hwnd, buf, 256)
	return buf.value


def _setWindowTheme(hwnd, theme):
	if hwnd and _IsWindow(hwnd):
		_SetWindowTheme(hwnd, theme, None)


def _setTitleBarDark(hwnd, dark: bool):
	if not hwnd or not _IsWindow(hwnd):
		return
	value = wintypes.BOOL(1 if dark else 0)
	_DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
	if WIN_BUILD >= 22000:
		for attr, colour in (
			(DWMWA_BORDER_COLOR, WINDOW_BORDER),
			(DWMWA_CAPTION_COLOR, TITLE_BG),
			(DWMWA_TEXT_COLOR, TITLE_FG),
		):
			value = wintypes.DWORD(_colorref(colour) if dark else DWMWA_COLOR_DEFAULT)
			_DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
	if _AllowDarkModeForWindow:
		_AllowDarkModeForWindow(hwnd, dark)


def _radioBoxButtons(hwnd):
	"""The native radio buttons of a wx.RadioBox: wx creates them as SIBLINGS of the box (owned
	by the box's parent) that lie inside the box's rectangle, not as its children."""
	parent = _GetParent(hwnd)
	if not parent:
		return []
	box = wintypes.RECT()
	_GetWindowRect(hwnd, ctypes.byref(box))
	out = []
	buf = ctypes.create_unicode_buffer(32)
	child = _GetWindow(parent, 5)  # GW_CHILD
	while child:
		if child != hwnd:
			_GetClassName(child, buf, 32)
			style = _GetWindowLong(child, -16) & 0xFFFFFFFF
			if buf.value == "Button" and (style & 0xF) in (4, 9):  # BS_RADIOBUTTON, BS_AUTORADIOBUTTON
				r = wintypes.RECT()
				_GetWindowRect(child, ctypes.byref(r))
				if r.left >= box.left and r.top >= box.top and r.right <= box.right and r.bottom <= box.bottom:
					out.append(child)
		child = _GetWindow(child, 2)  # GW_HWNDNEXT
	return out


def _nativeChildren(hwnd):
	"""HWNDs of all descendant windows (includes ones with no wx wrapper, e.g. wx.RadioBox buttons)."""
	found = []

	@_EnumChildProc
	def cb(child, _lp):
		found.append(child)
		return True

	_EnumChildWindows(hwnd, cb, 0)
	return found


# Controls that draw themselves and must not get wx colours (see header comment).
_NO_COLOUR_TYPES = [
	wx.Button,
	wx.BitmapButton,
	wx.ToggleButton,
	wx.CheckBox,
	wx.RadioButton,
	wx.Slider,
	wx.Gauge,
	wx.SpinButton,
	wx.StaticLine,
	wx.StaticBitmap,
]
try:
	import wx.stc

	_NO_COLOUR_TYPES.append(wx.stc.StyledTextCtrl)
except ImportError:
	pass
try:
	import wx.html

	_NO_COLOUR_TYPES.append(wx.html.HtmlWindow)
except ImportError:
	pass
_NO_COLOUR_TYPES = tuple(_NO_COLOUR_TYPES)

# Input fields and lists: slightly lighter surface so they read as fields.
_FIELD_TYPES = (
	wx.TextCtrl,
	wx.ListCtrl,
	wx.ListBox,
	wx.TreeCtrl,
	wx.Choice,
	wx.ComboBox,
	wx.SpinCtrl,
	wx.SpinCtrlDouble,
)

# Lists and trees: their own background colour (black with the "black backgrounds" setting).
_LIST_TYPES = (wx.ListCtrl, wx.ListBox, wx.TreeCtrl)

# Controls whose dotted focus rectangle is replaced by our solid ring (see native.applyFocusRing).
_FOCUS_RING_TYPES = (wx.CheckBox, wx.Choice, wx.ComboBox, wx.ListCtrl, wx.TreeCtrl)

# Original colours per window HANDLE. Not an attribute on the wx object: windows that wx
# creates on the C++ side (a wx.StaticBoxSizer's box, for one) get a fresh Python wrapper
# every time they are looked up, so anything stored on the wrapper is lost.
_states = {}


def forgetWindow(hwnd):
	_states.pop(hwnd, None)


def pruneStates():
	"""Drop entries for windows that no longer exist."""
	for h in [h for h in _states if not _IsWindow(h)]:
		_states.pop(h, None)


def _nativeThemeFor(win, hwnd) -> str:
	if isinstance(win, (wx.Choice, wx.ComboBox)) or _className(hwnd) == "ComboBox":
		return "DarkMode_CFD"
	return "DarkMode_Explorer"


def _sysColour(which):
	return wx.SystemSettings.GetColour(which)


def _framedHwnds(win, hwnd):
	"""Native windows whose edge we repaint: the control itself if it has a
	frame, plus the edit box a wx.SpinCtrl keeps as a separate native child."""
	out = []
	if not isinstance(win, (wx.Choice, wx.ComboBox, wx.TopLevelWindow)):
		# Native frame styles, or a wx-drawn border (wx paints wx.BORDER_THEME itself).
		try:
			wxBorder = win.GetBorder() != wx.BORDER_NONE
		except Exception:
			wxBorder = False
		if native.hasFrame(hwnd) or wxBorder:
			out.append(hwnd)
	if isinstance(win, (wx.SpinCtrl, wx.SpinCtrlDouble)):
		buddy = native.spinBuddy(hwnd)
		if buddy:
			out.append(buddy)
	return out


MESSAGE_WINDOW_CLASS = "Internet Explorer_TridentDlgFrame"  # NVDA's browseable-message dialog (MSHTML)
MESSAGE_CONTENT_CLASS = "Internet Explorer_Server"
_darkMessageWindows = set()

# A WinEvent hook for our own process: MSHTML creates the message dialog on a thread of its
# own, where neither wx nor the CBT hook can see it, but window-creation events for every
# thread of the process arrive here, on the main thread, within a few milliseconds.
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_SHOW = 0x8002
WINEVENT_OUTOFCONTEXT = 0x0000
_WINEVENTPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, wintypes.DWORD, wintypes.HWND, ctypes.c_long, ctypes.c_long, wintypes.DWORD, wintypes.DWORD)
_SetWinEventHook = _user32.SetWinEventHook
_SetWinEventHook.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, _WINEVENTPROC, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD)
_SetWinEventHook.restype = ctypes.c_void_p
_UnhookWinEvent = _user32.UnhookWinEvent
_UnhookWinEvent.argtypes = (ctypes.c_void_p,)
_winEventHook = None
_user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
_user32.GetAncestor.restype = wintypes.HWND


def _darkenMessageWindowNow(hwnd):
	"""Dark title bar plus a dark fill of the window's surface (its own pixels only), so the
	first frame is not white while the page loads."""
	_setTitleBarDark(hwnd, True)
	_darkMessageWindows.add(hwnd)
	targets = [hwnd]

	@_EnumChildProc
	def cb(h, _):
		targets.append(h)
		return True

	_EnumChildWindows(hwnd, cb, 0)
	brush = native._CreateSolidBrush(native.colorref((BG.Red(), BG.Green(), BG.Blue())))
	try:
		for h in targets:
			hdc = native._GetDC(h)
			if hdc:
				try:
					rc = native.RECT()
					native._GetClientRect(h, ctypes.byref(rc))
					native._FillRect(hdc, ctypes.byref(rc), brush)
				finally:
					native._ReleaseDC(h, hdc)
	finally:
		native._DeleteObject(brush)


def _onWinEvent(hook, event, hwnd, idObject, idChild, thread, time):
	try:
		if idObject != 0 or idChild != 0 or not hwnd:
			return
		if _className(hwnd) == MESSAGE_WINDOW_CLASS:
			log.debug("darkMode: message window %#x event %#x" % (hwnd, event))
			_darkenMessageWindowNow(hwnd)
		elif event == EVENT_OBJECT_SHOW and _className(hwnd) == MESSAGE_CONTENT_CLASS:
			top = _user32.GetAncestor(hwnd, 2)  # GA_ROOT
			if top and _className(top) == MESSAGE_WINDOW_CLASS:
				_darkenMessageWindowNow(top)
	except Exception:
		log.exception("darkMode: window event hook failed")


_winEventProc = _WINEVENTPROC(_onWinEvent)  # must outlive the hook


def installMessageWindowWatch():
	global _winEventHook
	if _winEventHook:
		return
	_winEventHook = _SetWinEventHook(EVENT_OBJECT_CREATE, EVENT_OBJECT_SHOW, None, _winEventProc, _kernel32.GetCurrentProcessId(), 0, WINEVENT_OUTOFCONTEXT)
	if not _winEventHook:
		log.warning("darkMode: could not install the window event hook (error %d)" % ctypes.get_last_error())


def removeMessageWindowWatch():
	global _winEventHook
	if _winEventHook:
		_UnhookWinEvent(_winEventHook)
		_winEventHook = None


def darkenMessageWindows():
	"""Dark title bar on NVDA's browseable-message windows (Help > License and the like). MSHTML
	creates them on its own thread, so neither wx nor our window hook sees them; they are found
	by class after the message has been shown. Returns how many were newly darkened."""
	found = []
	EnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

	@EnumProc
	def cb(h, _):
		if _className(h) == MESSAGE_WINDOW_CLASS:
			pid = wintypes.DWORD()
			_user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
			if pid.value == _kernel32.GetCurrentProcessId():
				found.append(h)
		return True

	_user32.EnumWindows(cb, 0)
	for h in list(_darkMessageWindows):
		if not _IsWindow(h):
			_darkMessageWindows.discard(h)
	new = [h for h in found if h not in _darkMessageWindows]
	for h in new:
		_setTitleBarDark(h, True)
		_darkMessageWindows.add(h)
	return len(new)


ES_MULTILINE = 0x0004
ES_READONLY = 0x0800


def _inPythonConsole(win) -> bool:
	"""Whether a control belongs to NVDA's Python console window."""
	try:
		top = win.GetTopLevelParent()
		return type(top).__name__ == "ConsoleUI" and type(top).__module__ == "pythonConsole"
	except Exception:
		return False


def _followsDialogBackground(win, hwnd) -> bool:
	"""With a Background that asks for it (black), text areas that show rather than take text
	(the speech viewer, the Add-on Store's description and details, the Python console's
	output and its input) take the dialog background instead of keeping the field grey."""
	if not (_background and _background.textAreasFollow) or not isinstance(win, wx.TextCtrl):
		return False
	if _inPythonConsole(win):
		return True
	style = native._GetWindowLongW(hwnd, native.GWL_STYLE)
	return bool(style & ES_MULTILINE) and bool(style & ES_READONLY)


def _applyDark(win, hwnd):
	# Theme first: changing the theme makes list views forget their text colour.
	_setWindowTheme(hwnd, _nativeThemeFor(win, hwnd))
	if not isinstance(win, _NO_COLOUR_TYPES):
		field = isinstance(win, _FIELD_TYPES)
		win.SetOwnBackgroundColour(LIST_BG if isinstance(win, _LIST_TYPES) else FIELD_BG if field else BG)
		win.SetOwnForegroundColour(FG)
	# wx skips re-sending colours it believes are already set, so tell the
	# native list/tree directly (these get reset by theme changes).
	if isinstance(win, wx.ListCtrl):
		native.themeTooltip(_SendMessage(hwnd, LVM_GETTOOLTIPS, 0, 0), True)
		_SendMessage(hwnd, LVM_SETBKCOLOR, 0, _colorref(LIST_BG))
		_SendMessage(hwnd, LVM_SETTEXTBKCOLOR, 0, _colorref(LIST_BG))
		_SendMessage(hwnd, LVM_SETTEXTCOLOR, 0, _colorref(FG))
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			native.applyHeader(header, True)
	elif isinstance(win, wx.TreeCtrl):
		_SendMessage(hwnd, TVM_SETBKCOLOR, 0, _colorref(LIST_BG))
		_SendMessage(hwnd, TVM_SETTEXTCOLOR, 0, _colorref(FG))
	if isinstance(win, wx.CheckListBox):
		parent = win.GetParent()
		if parent:
			native.registerCheckList(hwnd, parent.GetHandle(), win, True)
	if isinstance(win, wx.ListCtrl):
		parent = win.GetParent()
		if parent:
			native.registerListView(hwnd, parent.GetHandle(), True)
	if isinstance(win, wx.Slider):
		parent = win.GetParent()
		if parent:
			native.registerSlider(hwnd, parent.GetHandle(), True)
	followsBg = _followsDialogBackground(win, hwnd)
	if followsBg:
		win.SetOwnBackgroundColour(BG)
	if isinstance(win, wx.TextCtrl) and native.isRichEdit(hwnd):
		native.applyRich(hwnd, True, (BG.Red(), BG.Green(), BG.Blue()) if followsBg else None)
	# Frames around layout (panels) are structure, not fields: draw them softer.
	layout = isinstance(win, (wx.Panel, wx.ScrolledWindow)) and not isinstance(win, _FIELD_TYPES)
	for h in _framedHwnds(win, hwnd):
		native.applyFrame(h, True, native.LAYOUT_LINE if layout else None)
	if isinstance(win, wx.Button) and native.isPlainPushButton(hwnd):
		native.applyButton(hwnd, True)
	if isinstance(win, wx.Notebook):
		native.applyTabs(hwnd, True)
	# These paint their background only at WM_PAINT and showed white until then.
	if isinstance(win, (wx.ListCtrl, wx.ComboBox, wx.Gauge)):
		native.applyEraseBase(hwnd, native.LIST_BG if isinstance(win, wx.ListCtrl) else native.FIELD_BG, True)
	if isinstance(win, (wx.StaticBox, wx.RadioBox)):
		native.applyStaticBox(hwnd, True)
	if isinstance(win, wx.StaticLine):
		native.applyStaticLine(hwnd, True)
	if isinstance(win, wx.ListCtrl):
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			_setWindowTheme(header, "DarkMode_ItemsView")
	if isinstance(win, wx.RadioBox):
		for child in _nativeChildren(hwnd) + _radioBoxButtons(hwnd):
			_setWindowTheme(child, "DarkMode_Explorer")
			native.applyRadio(child, True)
	if isinstance(win, wx.RadioButton):
		native.applyRadio(hwnd, True)
	# Windows draws these a dotted grey focus rectangle; ours is a solid ring in the accent blue.
	if isinstance(win, _FOCUS_RING_TYPES):
		native.applyFocusRing(hwnd, True)
	if isinstance(win, wx.ListBox) and not isinstance(win, wx.CheckListBox):
		native.applyListBox(hwnd, True)
	if isinstance(win, wx.TopLevelWindow):
		_setTitleBarDark(hwnd, True)
		native.applyShowPaint(hwnd, True)
		for grip in native.sizeGrips(hwnd):
			native.applyGrip(grip, True)


def _restoreLight(win, hwnd, state):
	if not isinstance(win, _NO_COLOUR_TYPES):
		if isinstance(win, _FIELD_TYPES):
			# wx gives these explicit system colours after creation, so "no colour"
			# is not a usable default for them; put the system ones back.
			bg = state["bg"] or _sysColour(wx.SYS_COLOUR_WINDOW)
			fg = state["fg"] or _sysColour(wx.SYS_COLOUR_WINDOWTEXT)
		else:
			bg = state["bg"] or wx.NullColour
			fg = state["fg"] or wx.NullColour
		win.SetOwnBackgroundColour(bg)
		win.SetOwnForegroundColour(fg)
	# wx applies "Explorer" to lists/trees itself; everything else gets the default theme.
	_setWindowTheme(hwnd, "Explorer" if isinstance(win, (wx.ListCtrl, wx.TreeCtrl)) else None)
	if isinstance(win, wx.ListCtrl):
		native.themeTooltip(_SendMessage(hwnd, LVM_GETTOOLTIPS, 0, 0), False)
		# Exactly what an untouched wx list has: explicit window colours, default text
		# background. (CLR_DEFAULT for the background makes Windows 11's hover overlay
		# blend over black instead of white.)
		_SendMessage(hwnd, LVM_SETBKCOLOR, 0, _colorref(win.GetBackgroundColour()))
		_SendMessage(hwnd, LVM_SETTEXTBKCOLOR, 0, CLR_DEFAULT)
		_SendMessage(hwnd, LVM_SETTEXTCOLOR, 0, _colorref(win.GetForegroundColour()))
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			native.applyHeader(header, False)
	elif isinstance(win, wx.TreeCtrl):
		_SendMessage(hwnd, TVM_SETBKCOLOR, 0, _colorref(win.GetBackgroundColour()))
		_SendMessage(hwnd, TVM_SETTEXTCOLOR, 0, _colorref(win.GetForegroundColour()))
	if isinstance(win, wx.CheckListBox):
		native.registerCheckList(hwnd, 0, win, False)
	if isinstance(win, wx.ListCtrl):
		native.registerListView(hwnd, 0, False)
	if isinstance(win, wx.Slider):
		native.registerSlider(hwnd, 0, False)
	if isinstance(win, wx.TextCtrl) and native.isRichEdit(hwnd):
		native.applyRich(hwnd, False)
	for h in _framedHwnds(win, hwnd):
		native.applyFrame(h, False)
	if isinstance(win, wx.Button):
		native.applyButton(hwnd, False)
	if isinstance(win, wx.Notebook):
		native.applyTabs(hwnd, False)
	if isinstance(win, (wx.ListCtrl, wx.ComboBox, wx.Gauge)):
		native.applyEraseBase(hwnd, None, False)
	if isinstance(win, (wx.StaticBox, wx.RadioBox)):
		native.applyStaticBox(hwnd, False)
	if isinstance(win, wx.StaticLine):
		native.applyStaticLine(hwnd, False)
	if isinstance(win, wx.ListCtrl):
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			_setWindowTheme(header, None)
	if isinstance(win, wx.RadioBox):
		for child in _nativeChildren(hwnd) + _radioBoxButtons(hwnd):
			_setWindowTheme(child, None)
			native.applyRadio(child, False)
	if isinstance(win, wx.RadioButton):
		native.applyRadio(hwnd, False)
	if isinstance(win, _FOCUS_RING_TYPES):
		native.applyFocusRing(hwnd, False)
	if isinstance(win, wx.ListBox) and not isinstance(win, wx.CheckListBox):
		native.applyListBox(hwnd, False)
	if isinstance(win, wx.TopLevelWindow):
		_setTitleBarDark(hwnd, False)
		native.applyShowPaint(hwnd, False)
		for grip in native.sizeGrips(hwnd):
			native.applyGrip(grip, False)


def themeWindow(win: wx.Window, dark: bool = True, force: bool = False):
	"""Apply (dark=True) or remove (dark=False) dark styling from one wx window.

	wx keeps configuring some controls after their window handle exists (tree
	controls get system colours, read-only text boxes get a default background,
	lists/trees get the "Explorer" theme), which undoes an early pass. Callers
	therefore re-run this with force=True once construction has finished.
	"""
	try:
		hwnd = win.GetHandle()
	except RuntimeError:  # C++ object already gone
		return
	if not hwnd:
		return
	state = _states.get(hwnd)
	if dark:
		if state is not None and not force:
			return
		if state is None:
			# Remember explicitly-set colours so we can put them back.
			state = {
				"bg": win.GetBackgroundColour() if win.UseBackgroundColour() else None,
				"fg": win.GetForegroundColour() if win.UseForegroundColour() else None,
			}
			_states[hwnd] = state
		_applyDark(win, hwnd)
	else:
		if state is None:
			return
		_states.pop(hwnd, None)
		_restoreLight(win, hwnd, state)
	if win.IsShownOnScreen():
		win.Refresh()


def _walk(win):
	yield win
	for child in win.GetChildren():
		yield from _walk(child)


def themeTree(top: wx.Window, dark: bool = True, force: bool = False):
	for w in list(_walk(top)):
		themeWindow(w, dark, force)


def themeAllWindows(dark: bool = True, force: bool = False):
	for tlw in list(wx.GetTopLevelWindows()):
		themeTree(tlw, dark, force)


def setBackground(key: str) -> bool:
	"""Switch the dialog background to the named themes.Background (fields, buttons and
	menus keep their own colours). Returns True if it changed; the caller re-themes."""
	global BG, LIST_BG, _background
	want = themes.background(key)
	if _background is not None and want.key == _background.key:
		return False
	_background = want
	BG = wx.Colour(*want.bg)
	LIST_BG = wx.Colour(*want.listBg)
	native.PARENT_BG = want.bg  # what our painters clear to behind buttons, radios, sliders, boxes, the grip
	native.MENUBAR_BG = want.bg  # the strip behind a window's menu bar
	native.LIST_BG = want.listBg  # check-list rows, list erase base
	return True


def setAccent(key: str, brightContrast: bool = False) -> bool:
	"""Switch focus rings, the menu outline, selected list rows and slider thumbs to the named
	themes.Accent; with brightContrast the selected row is the accent colour itself with black
	text. Returns True if anything changed; the painters read these at paint time, so the
	caller only repaints."""
	global _accent, _brightContrast
	want = themes.accent(key)
	brightContrast = bool(brightContrast)
	if _accent is not None and want.key == _accent.key and brightContrast == _brightContrast:
		return False
	_accent = want
	_brightContrast = brightContrast
	native.FOCUS = want.focus
	native.LIST_SEL_BG = want.focus if brightContrast else want.selection
	native.LIST_SEL_TEXT = themes.BLACK if brightContrast else themes.WHITE
	native.SLIDER_THUMB = want.focus
	native.SLIDER_THUMB_HOT = want.hot
	native.SLIDER_THUMB_PRESSED = want.pressed
	return True


def currentBackground() -> str:
	return _background.key if _background else themes.DEFAULT_BACKGROUND


def currentAccent() -> str:
	return _accent.key if _accent else themes.DEFAULT_ACCENT


def brightContrast() -> bool:
	return _brightContrast


# One source of truth: the defaults in themes.py, not the literals above or in native.py.
setBackground(themes.DEFAULT_BACKGROUND)
setAccent(themes.DEFAULT_ACCENT)


def repaintAllWindows():
	"""Repaint every window and control (after a purely visual setting changed)."""
	for tlw in list(wx.GetTopLevelWindows()):
		try:
			native._RedrawWindow(tlw.GetHandle(), None, None, native.RDW_FRAME | native.RDW_INVALIDATE | native.RDW_ERASE | native.RDW_ALLCHILDREN)
		except Exception:
			log.debugWarning("darkMode: repaint failed", exc_info=True)


# --- Process-wide switches --------------------------------------------------
def setProcessDark(dark: bool):
	"""Dark menus for the whole process (needs Windows 10 1903+)."""
	if _SetPreferredAppMode:
		_SetPreferredAppMode(APPMODE_FORCE_DARK if dark else APPMODE_DEFAULT)
	if _RefreshImmersiveColorPolicyState:
		_RefreshImmersiveColorPolicyState()
	if _FlushMenuThemes:
		_FlushMenuThemes()


# --- Engine -----------------------------------------------------------------
class DarkModeEngine:
	"""Keeps the NVDA GUI dark: themes existing windows, hooks new ones, follows system changes."""

	POLL_MS = 2000

	def __init__(self, wantDark):
		"""
		@param wantDark: callable returning True when the user setting asks for dark
			(system state and high contrast are handled here).
		"""
		self._wantDark = wantDark
		self._active = False
		self._pendingTrees = {}
		self.onStateChanged = None  # optional callable, run after dark mode turns on or off
		self._app = wx.GetApp()
		self._timer = wx.Timer()
		self._timer.Bind(wx.EVT_TIMER, self._onPoll)

	@property
	def active(self) -> bool:
		return self._active

	def shouldBeDark(self) -> bool:
		if highContrastActive():
			return False
		try:
			return bool(self._wantDark())
		except Exception:
			log.exception("darkMode: wantDark callback failed")
			return False

	def start(self):
		self._app.Bind(wx.EVT_WINDOW_CREATE, self._onWindowCreate)
		self._app.Bind(wx.EVT_WINDOW_DESTROY, self._onWindowDestroy)
		self._timer.Start(self.POLL_MS)
		self.refresh()

	def stop(self, restore: bool = True):
		"""restore=False: NVDA is exiting. Take our hooks off the windows (they must not
		outlive this module) but leave them looking dark: repainting everything light on the
		way out showed as a white flash."""
		self._timer.Stop()
		self._app.Unbind(wx.EVT_WINDOW_CREATE, handler=self._onWindowCreate)
		self._app.Unbind(wx.EVT_WINDOW_DESTROY, handler=self._onWindowDestroy)
		_states.clear()
		if restore:
			self._setActive(False)
		else:
			self._active = False
			native.detachAll()

	def refresh(self):
		"""Re-evaluate settings/system state and apply the result."""
		self._setActive(self.shouldBeDark())

	def _setActive(self, dark: bool):
		if dark == self._active:
			return
		self._active = dark
		log.info("darkMode: %s dark mode" % ("enabling" if dark else "disabling"))
		setProcessDark(dark)
		themeAllWindows(dark)
		if dark:
			native.installMenuHook()
			installMessageWindowWatch()
		else:
			removeMessageWindowWatch()
			native.detachAll()
		if self.onStateChanged:
			try:
				self.onStateChanged()
			except Exception:
				log.exception("darkMode: state change callback failed")

	def _onWindowDestroy(self, event):
		event.Skip()
		win = event.GetWindow()
		try:
			forgetWindow(win.GetHandle())
		except Exception:
			pass

	def _onWindowCreate(self, event):
		event.Skip()
		win = event.GetWindow()
		if win is None:
			return
		if isinstance(win, wx.TopLevelWindow):
			# Re-theme the whole dialog right before it first appears: every child
			# exists and wx has finished its own post-create colour/theme setup.
			win.Bind(wx.EVT_SHOW, self._onShow)
		if not self._active:
			return
		try:
			themeWindow(win, True)
		except Exception:
			log.exception("darkMode: failed to theme new window")
		# Second pass once construction has finished. Over the whole top-level window, not
		# this object: during creation wxPython may hand us a throwaway wrapper (the real
		# one is registered when the constructor returns), and anything that has to keep
		# hold of the control - the check list painter, for one - needs the real object,
		# which walking the tree later returns. One pass per creation burst.
		try:
			top = win.GetTopLevelParent() or win
		except Exception:
			top = win
		key = id(top)
		if key not in self._pendingTrees:
			self._pendingTrees[key] = top
			wx.CallAfter(self._reapplyTree, key)

	def _reapplyTree(self, key):
		top = self._pendingTrees.pop(key, None)
		if top is None or not self._active:
			return
		try:
			themeTree(top, True, force=True)
		except RuntimeError:
			pass  # the window was destroyed before we got here
		except Exception:
			log.exception("darkMode: failed to re-theme window tree")

	def _reapply(self, win):
		if not self._active:
			return
		try:
			themeWindow(win, True, force=True)
		except Exception:
			log.exception("darkMode: failed to re-theme window")

	def _onShow(self, event):
		event.Skip()
		if not self._active or not event.IsShown():
			return
		win = event.GetEventObject()
		try:
			themeTree(win, True, force=True)
		except Exception:
			log.exception("darkMode: failed to theme shown window")

	def _onPoll(self, event):
		try:
			pruneStates()
			self.refresh()
		except Exception:
			log.exception("darkMode: poll failed")
