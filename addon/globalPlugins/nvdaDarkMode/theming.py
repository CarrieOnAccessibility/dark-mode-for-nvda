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
	from . import native
except ImportError:  # imported as a plain module by the dev test bench
	import native

try:
	from logHandler import log
except ImportError:  # running outside NVDA (test bench)
	import logging

	log = logging.getLogger("nvdaDarkMode")

# --- Palette ----------------------------------------------------------------
# Windows 11 dark: app background #202020, raised surfaces #2b2b2b, text white.
BG = wx.Colour(0x20, 0x20, 0x20)
FIELD_BG = wx.Colour(0x2B, 0x2B, 0x2B)
FG = wx.Colour(0xFF, 0xFF, 0xFF)

# --- Win32 plumbing ---------------------------------------------------------
_user32 = ctypes.WinDLL("user32", use_last_error=True)
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

_EnumChildProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_EnumChildWindows = _user32.EnumChildWindows
_EnumChildWindows.argtypes = (wintypes.HWND, _EnumChildProc, wintypes.LPARAM)
_EnumChildWindows.restype = wintypes.BOOL

WM_THEMECHANGED = 0x031A
LVM_SETBKCOLOR = 0x1000 + 1
LVM_GETHEADER = 0x1000 + 31
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
DWMWA_COLOR_DEFAULT = 0xFFFFFFFF
WINDOW_BORDER = wx.Colour(0xC8, 0xC8, 0xC8)  # light grey ring around every NVDA dialog


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
		border = wintypes.DWORD(_colorref(WINDOW_BORDER) if dark else DWMWA_COLOR_DEFAULT)
		_DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(border), ctypes.sizeof(border))
	if _AllowDarkModeForWindow:
		_AllowDarkModeForWindow(hwnd, dark)


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

MARK = "_nvdaDarkMode"


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


def _applyDark(win, hwnd):
	# Theme first: changing the theme makes list views forget their text colour.
	_setWindowTheme(hwnd, _nativeThemeFor(win, hwnd))
	if not isinstance(win, _NO_COLOUR_TYPES):
		field = isinstance(win, _FIELD_TYPES)
		win.SetOwnBackgroundColour(FIELD_BG if field else BG)
		win.SetOwnForegroundColour(FG)
	# wx skips re-sending colours it believes are already set, so tell the
	# native list/tree directly (these get reset by theme changes).
	if isinstance(win, wx.ListCtrl):
		_SendMessage(hwnd, LVM_SETBKCOLOR, 0, _colorref(FIELD_BG))
		_SendMessage(hwnd, LVM_SETTEXTBKCOLOR, 0, _colorref(FIELD_BG))
		_SendMessage(hwnd, LVM_SETTEXTCOLOR, 0, _colorref(FG))
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			native.applyHeader(header, True)
	elif isinstance(win, wx.TreeCtrl):
		_SendMessage(hwnd, TVM_SETBKCOLOR, 0, _colorref(FIELD_BG))
		_SendMessage(hwnd, TVM_SETTEXTCOLOR, 0, _colorref(FG))
	if isinstance(win, wx.CheckListBox):
		parent = win.GetParent()
		if parent:
			native.registerCheckList(hwnd, parent.GetHandle(), win, True)
	if isinstance(win, wx.TextCtrl) and native.isRichEdit(hwnd):
		native.applyRich(hwnd, True)
	for h in _framedHwnds(win, hwnd):
		native.applyFrame(h, True)
	if isinstance(win, wx.Button) and native.isPlainPushButton(hwnd):
		native.applyButton(hwnd, True)
	if isinstance(win, wx.Notebook):
		native.applyTabs(hwnd, True)
	if isinstance(win, wx.ListCtrl):
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			_setWindowTheme(header, "DarkMode_ItemsView")
	if isinstance(win, wx.RadioBox):
		for child in _nativeChildren(hwnd):
			_setWindowTheme(child, "DarkMode_Explorer")
	if isinstance(win, wx.TopLevelWindow):
		_setTitleBarDark(hwnd, True)


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
		_SendMessage(hwnd, LVM_SETBKCOLOR, 0, CLR_DEFAULT)
		_SendMessage(hwnd, LVM_SETTEXTBKCOLOR, 0, CLR_DEFAULT)
		_SendMessage(hwnd, LVM_SETTEXTCOLOR, 0, CLR_DEFAULT)
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			native.applyHeader(header, False)
	elif isinstance(win, wx.TreeCtrl):
		_SendMessage(hwnd, TVM_SETBKCOLOR, 0, -1)
		_SendMessage(hwnd, TVM_SETTEXTCOLOR, 0, -1)
	if isinstance(win, wx.CheckListBox):
		native.registerCheckList(hwnd, 0, win, False)
	if isinstance(win, wx.TextCtrl) and native.isRichEdit(hwnd):
		native.applyRich(hwnd, False)
	for h in _framedHwnds(win, hwnd):
		native.applyFrame(h, False)
	if isinstance(win, wx.Button):
		native.applyButton(hwnd, False)
	if isinstance(win, wx.Notebook):
		native.applyTabs(hwnd, False)
	if isinstance(win, wx.ListCtrl):
		header = _SendMessage(hwnd, LVM_GETHEADER, 0, 0)
		if header:
			_setWindowTheme(header, None)
	if isinstance(win, wx.RadioBox):
		for child in _nativeChildren(hwnd):
			_setWindowTheme(child, None)
	if isinstance(win, wx.TopLevelWindow):
		_setTitleBarDark(hwnd, False)


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
	state = getattr(win, MARK, None)
	if dark:
		if state is not None and not force:
			return
		if state is None:
			# Remember explicitly-set colours so we can put them back.
			state = {
				"bg": win.GetBackgroundColour() if win.UseBackgroundColour() else None,
				"fg": win.GetForegroundColour() if win.UseForegroundColour() else None,
			}
			setattr(win, MARK, state)
		_applyDark(win, hwnd)
	else:
		if state is None:
			return
		delattr(win, MARK)
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
			log.exception("nvdaDarkMode: wantDark callback failed")
			return False

	def start(self):
		self._app.Bind(wx.EVT_WINDOW_CREATE, self._onWindowCreate)
		self._timer.Start(self.POLL_MS)
		self.refresh()

	def stop(self):
		self._timer.Stop()
		self._app.Unbind(wx.EVT_WINDOW_CREATE, handler=self._onWindowCreate)
		self._setActive(False)

	def refresh(self):
		"""Re-evaluate settings/system state and apply the result."""
		self._setActive(self.shouldBeDark())

	def _setActive(self, dark: bool):
		if dark == self._active:
			return
		self._active = dark
		log.info("nvdaDarkMode: %s dark mode" % ("enabling" if dark else "disabling"))
		setProcessDark(dark)
		themeAllWindows(dark)
		if not dark:
			native.detachAll()

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
			log.exception("nvdaDarkMode: failed to theme new window")
		wx.CallAfter(self._reapply, win)

	def _reapply(self, win):
		if not self._active:
			return
		try:
			themeWindow(win, True, force=True)
		except Exception:
			log.exception("nvdaDarkMode: failed to re-theme window")

	def _onShow(self, event):
		event.Skip()
		if not self._active or not event.IsShown():
			return
		win = event.GetEventObject()
		try:
			themeTree(win, True, force=True)
		except Exception:
			log.exception("nvdaDarkMode: failed to theme shown window")

	def _onPoll(self, event):
		try:
			self.refresh()
		except Exception:
			log.exception("nvdaDarkMode: poll failed")
