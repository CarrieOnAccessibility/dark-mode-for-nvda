# Win32 painting helpers for the dark mode engine.
#
# Two things Windows' dark theme gets wrong for us are fixed here by
# subclassing the native window (comctl32 SetWindowSubclass), which changes
# how a control is PAINTED but nothing about what it IS. Window class, styles,
# text and states stay untouched, so MSAA/UIA (and therefore NVDA reading its
# own dialogs) see exactly what they saw before.
#
#   * Frame painter (ID_FRAME): text boxes, lists and trees get a pure white
#     2px edge from the theme. After the default WM_NCPAINT we overdraw the
#     frame in a light grey, and a 2px white ring when the control has focus.
#   * Button painter (ID_BUTTON): push buttons are drawn entirely by us on
#     WM_PAINT (face, border, label), giving a clearer hover state and a
#     slightly softer disabled state than the theme provides.
#   * Tab painter (ID_TABS): the tab strip of a wx.Notebook (SysTabControl32)
#     has no dark theme at all, so its tabs are drawn by us on WM_PAINT.
#   * Header painter (ID_HEADER): list view column headers (SysHeader32) get
#     black text and invisible separators from the theme; painted by us.
#   * Owner-drawn rows (ID_OWNERDRAW): wx.CheckListBox rows are painted by wx
#     with system colours; the parent's WM_DRAWITEM is handled here instead.

import ctypes
from ctypes import wintypes
import weakref

try:
	from logHandler import log
except ImportError:
	import logging

	log = logging.getLogger("nvdaDarkMode")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
_uxtheme = ctypes.WinDLL("uxtheme", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HANDLE = ctypes.c_void_p


class RECT(ctypes.Structure):
	_fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class SIZE(ctypes.Structure):
	_fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class DRAWITEMSTRUCT(ctypes.Structure):
	_fields_ = [
		("CtlType", wintypes.UINT),
		("CtlID", wintypes.UINT),
		("itemID", wintypes.UINT),
		("itemAction", wintypes.UINT),
		("itemState", wintypes.UINT),
		("hwndItem", wintypes.HWND),
		("hDC", HANDLE),
		("rcItem", RECT),
		("itemData", ctypes.c_size_t),
	]


class TCITEMW(ctypes.Structure):
	_fields_ = [
		("mask", wintypes.UINT),
		("dwState", wintypes.DWORD),
		("dwStateMask", wintypes.DWORD),
		("pszText", wintypes.LPWSTR),
		("cchTextMax", ctypes.c_int),
		("iImage", ctypes.c_int),
		("lParam", ctypes.c_size_t),
	]


class HDITEMW(ctypes.Structure):
	_fields_ = [
		("mask", wintypes.UINT),
		("cxy", ctypes.c_int),
		("pszText", wintypes.LPWSTR),
		("hbm", HANDLE),
		("cchTextMax", ctypes.c_int),
		("fmt", ctypes.c_int),
		("lParam", ctypes.c_size_t),
		("iImage", ctypes.c_int),
		("iOrder", ctypes.c_int),
		("type", wintypes.UINT),
		("pvFilter", ctypes.c_void_p),
		("state", wintypes.UINT),
	]


class HDHITTESTINFO(ctypes.Structure):
	_fields_ = [("pt", wintypes.POINT), ("flags", wintypes.UINT), ("iItem", ctypes.c_int)]


class TCHITTESTINFO(ctypes.Structure):
	_fields_ = [("pt", wintypes.POINT), ("flags", wintypes.UINT)]


class TRACKMOUSEEVENT(ctypes.Structure):
	_fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("hwndTrack", wintypes.HWND), ("dwHoverTime", wintypes.DWORD)]


class CHARFORMATW(ctypes.Structure):
	_fields_ = [
		("cbSize", wintypes.UINT),
		("dwMask", wintypes.DWORD),
		("dwEffects", wintypes.DWORD),
		("yHeight", ctypes.c_long),
		("yOffset", ctypes.c_long),
		("crTextColor", wintypes.COLORREF),
		("bCharSet", ctypes.c_byte),
		("bPitchAndFamily", ctypes.c_byte),
		("szFaceName", ctypes.c_wchar * 32),
	]


class WINDOWPOS(ctypes.Structure):
	_fields_ = [
		("hwnd", wintypes.HWND),
		("hwndInsertAfter", wintypes.HWND),
		("x", ctypes.c_int),
		("y", ctypes.c_int),
		("cx", ctypes.c_int),
		("cy", ctypes.c_int),
		("flags", wintypes.UINT),
	]


class PAINTSTRUCT(ctypes.Structure):
	_fields_ = [
		("hdc", HANDLE),
		("fErase", wintypes.BOOL),
		("rcPaint", RECT),
		("fRestore", wintypes.BOOL),
		("fIncUpdate", wintypes.BOOL),
		("rgbReserved", ctypes.c_byte * 32),
	]


_SUBCLASSPROC = ctypes.WINFUNCTYPE(
	LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t
)
_SetWindowSubclass = _comctl32.SetWindowSubclass
_SetWindowSubclass.argtypes = (wintypes.HWND, _SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t)
_SetWindowSubclass.restype = wintypes.BOOL
_RemoveWindowSubclass = _comctl32.RemoveWindowSubclass
_RemoveWindowSubclass.argtypes = (wintypes.HWND, _SUBCLASSPROC, ctypes.c_size_t)
_RemoveWindowSubclass.restype = wintypes.BOOL
_DefSubclassProc = _comctl32.DefSubclassProc
_DefSubclassProc.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_DefSubclassProc.restype = LRESULT

_GetWindowDC = _user32.GetWindowDC
_GetWindowDC.argtypes = (wintypes.HWND,)
_GetWindowDC.restype = HANDLE
_ReleaseDC = _user32.ReleaseDC
_ReleaseDC.argtypes = (wintypes.HWND, HANDLE)
_BeginPaint = _user32.BeginPaint
_BeginPaint.argtypes = (wintypes.HWND, ctypes.POINTER(PAINTSTRUCT))
_BeginPaint.restype = HANDLE
_EndPaint = _user32.EndPaint
_EndPaint.argtypes = (wintypes.HWND, ctypes.POINTER(PAINTSTRUCT))
_GetWindowRect = _user32.GetWindowRect
_GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
_GetClientRect = _user32.GetClientRect
_GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
_FillRect = _user32.FillRect
_FillRect.argtypes = (HANDLE, ctypes.POINTER(RECT), HANDLE)
_FrameRect = _user32.FrameRect
_FrameRect.argtypes = (HANDLE, ctypes.POINTER(RECT), HANDLE)
_DrawTextW = _user32.DrawTextW
_DrawTextW.argtypes = (HANDLE, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(RECT), wintypes.UINT)
_GetFocus = _user32.GetFocus
_GetFocus.restype = wintypes.HWND
_GetWindowLongW = _user32.GetWindowLongW
_GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
_GetWindowLongW.restype = ctypes.c_long
_GetWindowTextW = _user32.GetWindowTextW
_GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_GetWindowTextLengthW = _user32.GetWindowTextLengthW
_GetWindowTextLengthW.argtypes = (wintypes.HWND,)
_IsWindowEnabled = _user32.IsWindowEnabled
_IsWindowEnabled.argtypes = (wintypes.HWND,)
_IsWindow = _user32.IsWindow
_IsWindow.argtypes = (wintypes.HWND,)
_SendMessageW = _user32.SendMessageW
_SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_SendMessageW.restype = LRESULT
_RedrawWindow = _user32.RedrawWindow
_RedrawWindow.argtypes = (wintypes.HWND, ctypes.c_void_p, HANDLE, wintypes.UINT)
_InvalidateRect = _user32.InvalidateRect
_InvalidateRect.argtypes = (wintypes.HWND, ctypes.c_void_p, wintypes.BOOL)
try:
	_GetDpiForWindow = _user32.GetDpiForWindow
	_GetDpiForWindow.argtypes = (wintypes.HWND,)
	_GetDpiForWindow.restype = wintypes.UINT
except AttributeError:
	_GetDpiForWindow = None

_OpenThemeData = _uxtheme.OpenThemeData
_OpenThemeData.argtypes = (wintypes.HWND, wintypes.LPCWSTR)
_OpenThemeData.restype = HANDLE
_CloseThemeData = _uxtheme.CloseThemeData
_CloseThemeData.argtypes = (HANDLE,)
_DrawThemeBackground = _uxtheme.DrawThemeBackground
_DrawThemeBackground.argtypes = (HANDLE, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.POINTER(RECT), ctypes.POINTER(RECT))
_GetThemePartSize = _uxtheme.GetThemePartSize
_GetThemePartSize.argtypes = (HANDLE, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.POINTER(RECT), ctypes.c_int, ctypes.POINTER(SIZE))
_DrawFocusRect = _user32.DrawFocusRect
_DrawFocusRect.argtypes = (HANDLE, ctypes.POINTER(RECT))
_GetSysColor = _user32.GetSysColor
_GetSysColor.argtypes = (ctypes.c_int,)
_GetSysColor.restype = wintypes.DWORD

_CreateSolidBrush = _gdi32.CreateSolidBrush
_CreateSolidBrush.argtypes = (wintypes.COLORREF,)
_CreateSolidBrush.restype = HANDLE
_CreatePen = _gdi32.CreatePen
_CreatePen.argtypes = (ctypes.c_int, ctypes.c_int, wintypes.COLORREF)
_CreatePen.restype = HANDLE
_SelectObject = _gdi32.SelectObject
_SelectObject.argtypes = (HANDLE, HANDLE)
_SelectObject.restype = HANDLE
_DeleteObject = _gdi32.DeleteObject
_DeleteObject.argtypes = (HANDLE,)
_RoundRect = _gdi32.RoundRect
_RoundRect.argtypes = (HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_SetBkMode = _gdi32.SetBkMode
_SetBkMode.argtypes = (HANDLE, ctypes.c_int)
_SetTextColor = _gdi32.SetTextColor
_SetTextColor.argtypes = (HANDLE, wintypes.COLORREF)

WM_ENABLE = 0x000A
WM_SETFOCUS = 0x0007
WM_KILLFOCUS = 0x0008
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_GETFONT = 0x0031
WM_DRAWITEM = 0x002B
WM_NCDESTROY = 0x0082
WM_NCPAINT = 0x0085
WM_UPDATEUISTATE = 0x0128
WM_MOUSEMOVE = 0x0200
WM_MOUSELEAVE = 0x02A3
TME_LEAVE = 0x2
HDM_GETITEMCOUNT = 0x1200
HDM_HITTEST = 0x1206
HDM_GETITEMRECT = 0x1207
HDM_GETITEMW = 0x120B
HDM_GETORDERARRAY = 0x1211
HDI_TEXT = 0x2
HDI_FORMAT = 0x4
HDF_JUSTIFYMASK = 0x3
HDF_CENTER = 0x2
HDF_RIGHT = 0x1
HDF_SORTUP = 0x400
HDF_SORTDOWN = 0x200
DT_RIGHT = 0x2
TCM_GETITEMCOUNT = 0x1304
TCM_GETITEMRECT = 0x130A
TCM_GETCURSEL = 0x130B
TCM_HITTEST = 0x130D
TCM_GETITEMW = 0x133C
TCIF_TEXT = 0x1
WM_SETTEXT = 0x000C
EM_REPLACESEL = 0x00C2
EM_SETBKGNDCOLOR = 0x0443
EM_SETCHARFORMAT = 0x0444
EM_SETTEXTEX = 0x0461
SCF_DEFAULT = 0x0000
SCF_ALL = 0x0004
CFM_COLOR = 0x40000000
WM_WINDOWPOSCHANGED = 0x0047
WS_CAPTION = 0x00C00000
_ExcludeClipRect = _gdi32.ExcludeClipRect
_ExcludeClipRect.argtypes = (HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_GetDC = _user32.GetDC
_GetDC.argtypes = (wintypes.HWND,)
_GetDC.restype = HANDLE
_IsWindowVisible = _user32.IsWindowVisible
_IsWindowVisible.argtypes = (wintypes.HWND,)
SWP_SHOWWINDOW = 0x0040
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100
WM_DARK_FRAME = 0x8000 + 0x37  # WM_APP + 0x37: "repaint our frame once everyone else is done"
WM_QUERYUISTATE = 0x0129
BM_GETSTATE = 0x00F2
BM_GETIMAGE = 0x00F6
UDM_GETBUDDY = 0x046A
BST_PUSHED = 0x0004
BST_FOCUS = 0x0008
BST_HOT = 0x0200
UISF_HIDEFOCUS = 0x1
UISF_HIDEACCEL = 0x2
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_EX_CLIENTEDGE = 0x00000200
WS_BORDER = 0x00800000
BS_TYPEMASK = 0x000F
BS_PUSHBUTTON = 0x0
BS_DEFPUSHBUTTON = 0x1
BS_MULTILINE = 0x2000
DT_CENTER = 0x1
DT_VCENTER = 0x4
DT_WORDBREAK = 0x10
DT_SINGLELINE = 0x20
DT_CALCRECT = 0x400
DT_HIDEPREFIX = 0x100000
PS_SOLID = 0
TRANSPARENT = 1
RDW_INVALIDATE = 0x1
RDW_ERASE = 0x4
RDW_FRAME = 0x400
RDW_UPDATENOW = 0x100

ODT_LISTBOX = 2
ODS_SELECTED = 0x0001
ODS_DISABLED = 0x0004
ODS_FOCUS = 0x0010
BP_CHECKBOX = 3
CBS_UNCHECKEDNORMAL = 1
CBS_UNCHECKEDDISABLED = 4
CBS_CHECKEDNORMAL = 5
CBS_CHECKEDDISABLED = 8
COLOR_HIGHLIGHT = 13
COLOR_HIGHLIGHTTEXT = 14
DT_LEFT = 0x0
DT_NOPREFIX = 0x800
DT_END_ELLIPSIS = 0x8000

ID_FRAME = 1
ID_BUTTON = 2
ID_OWNERDRAW = 3  # on the PARENT of owner-drawn check list boxes (WM_DRAWITEM goes there)
ID_TABS = 4
ID_RICH = 5  # rich edit controls: keep text colour applied after the text is replaced
ID_HEADER = 6
ID_GRIP = 7  # the size grip wx puts in the corner of resizable dialogs (a bare ScrollBar window)
ID_MENUPOPUP = 8  # popup menu windows (#32768): dark erase so they never flash light
ID_ERASE = 9  # controls that only paint their background at WM_PAINT: dark base on erase
ID_SHOWPAINT = 10  # top-level windows: paint everything synchronously the moment they appear; title separator
ID_STATICBOX = 11  # group boxes (wx.StaticBox / wx.RadioBox): our own border and label
ID_STATICLINE = 12  # wx.StaticLine: one soft line instead of the etched white/grey pair


def colorref(rgb):
	r, g, b = rgb
	return r | (g << 8) | (b << 16)


# --- Palette (RGB tuples). Tweak here. -------------------------------------
BORDER = (0xC8, 0xC8, 0xC8)  # light grey frame around fields, lists, buttons
FOCUS = (0x60, 0xCD, 0xFF)  # focus rings: the Windows 11 dark-mode accent blue, same as the check box glyphs
FRAME_INNER = (0x2B, 0x2B, 0x2B)  # covers the theme's inner white line (matches field background)
PARENT_BG = (0x20, 0x20, 0x20)  # dialog background, shows behind rounded button corners
GRIP_DOT = (0x62, 0x62, 0x62)  # size grip dots: visible if you look for them, nothing more
LAYOUT_LINE = (0x8C, 0x8C, 0x8C)  # structure, not controls: panel frames, group boxes, separators, under the title bar
MENU_BG = (0x2C, 0x2C, 0x2C)  # what Windows paints dark popup menus with (measured); used only for the erase
BTN_FACE = (0x33, 0x33, 0x33)
BTN_HOT = (0x50, 0x50, 0x50)  # hover: clearly lighter than the face
BTN_PRESSED = (0x28, 0x28, 0x28)
BTN_DISABLED_FACE = (0x2A, 0x2A, 0x2A)
BTN_HOT_BORDER = (0xE8, 0xE8, 0xE8)
BTN_DISABLED_BORDER = (0x80, 0x80, 0x80)
BTN_TEXT = (0xFF, 0xFF, 0xFF)
BTN_DISABLED_TEXT = (0x9C, 0x9C, 0x9C)  # readable, a step down from enabled
LIST_BG = (0x2B, 0x2B, 0x2B)
LIST_TEXT = (0xFF, 0xFF, 0xFF)
LIST_DISABLED_TEXT = (0x8A, 0x8A, 0x8A)
LIST_SEL_UNFOCUSED_BG = (0x50, 0x50, 0x50)  # selected row while the list does not have focus
TAB_TEXT = (0xC8, 0xC8, 0xC8)  # unselected tab label
TAB_SELECTED_FACE = (0x3A, 0x3A, 0x3A)
TAB_HOT_FACE = (0x50, 0x50, 0x50)
TAB_SELECTED_TEXT = (0xFF, 0xFF, 0xFF)
HEADER_BG = (0x2B, 0x2B, 0x2B)
HEADER_HOT_BG = (0x3A, 0x3A, 0x3A)
HEADER_TEXT = (0xFF, 0xFF, 0xFF)
HEADER_SEPARATOR = (0x80, 0x80, 0x80)  # vertical lines between columns
HEADER_BOTTOM = (0xC8, 0xC8, 0xC8)  # line under the header, matches the field frames

_tabHot = {}  # tab control hwnd -> hovered tab index

_subclassed = {}  # hwnd -> set of ids
_framePending = set()  # hwnds with a WM_DARK_FRAME already posted
_checkLists = {}  # hwnd of wx.CheckListBox -> weakref to the wx object


def _frameOf(hwnd):
	"""Frame thickness (pixels) on the left/top, i.e. the non-client edge width."""
	wr = RECT()
	cr = RECT()
	_GetWindowRect(hwnd, ctypes.byref(wr))
	_GetClientRect(hwnd, ctypes.byref(cr))
	pt = wintypes.POINT(0, 0)
	_user32.ClientToScreen(hwnd, ctypes.byref(pt))
	return max(0, min(pt.x - wr.left, pt.y - wr.top))


def _paintWith(hwnd, draw):
	"""Run a full-control drawing routine inside BeginPaint/EndPaint."""
	ps = PAINTSTRUCT()
	hdc = _BeginPaint(hwnd, ctypes.byref(ps))
	if not hdc:
		return
	try:
		draw(hwnd, hdc)
	finally:
		_EndPaint(hwnd, ctypes.byref(ps))


def _paintFrame(hwnd):
	hdc = _GetWindowDC(hwnd)
	if not hdc:
		return
	try:
		wr = RECT()
		_GetWindowRect(hwnd, ctypes.byref(wr))
		w, h = wr.right - wr.left, wr.bottom - wr.top
		thick = _frameOf(hwnd)
		if thick <= 0:
			return
		focused = _GetFocus() == hwnd
		outer = _CreateSolidBrush(colorref(FOCUS if focused else _frameColours.get(hwnd, BORDER)))
		inner = _CreateSolidBrush(colorref(FOCUS if focused else FRAME_INNER))
		try:
			for i in range(thick):
				rc = RECT(i, i, w - i, h - i)
				_FrameRect(hdc, ctypes.byref(rc), outer if i == 0 else inner)
		finally:
			_DeleteObject(outer)
			_DeleteObject(inner)
	finally:
		_ReleaseDC(hwnd, hdc)


def _paintButton(hwnd):
	_paintWith(hwnd, _drawButton)


def _drawButton(hwnd, hdc):
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	w, h = rc.right, rc.bottom
	style = _GetWindowLongW(hwnd, GWL_STYLE)
	state = _SendMessageW(hwnd, BM_GETSTATE, 0, 0)
	enabled = bool(_IsWindowEnabled(hwnd))
	hot = bool(state & BST_HOT)
	pushed = bool(state & BST_PUSHED)
	focused = bool(state & BST_FOCUS)
	default = (style & BS_TYPEMASK) == BS_DEFPUSHBUTTON
	uistate = _SendMessageW(hwnd, WM_QUERYUISTATE, 0, 0)

	if not enabled:
		face, border, text = BTN_DISABLED_FACE, BTN_DISABLED_BORDER, BTN_DISABLED_TEXT
	elif pushed:
		face, border, text = BTN_PRESSED, BTN_HOT_BORDER, BTN_TEXT
	elif hot:
		face, border, text = BTN_HOT, BTN_HOT_BORDER, BTN_TEXT
	else:
		face, border, text = BTN_FACE, BORDER, BTN_TEXT

	bg = _CreateSolidBrush(colorref(PARENT_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)
	_DeleteObject(bg)

	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	radius = max(2, round(4 * dpi / 96))
	pen = _CreatePen(PS_SOLID, 1, colorref(border))
	brush = _CreateSolidBrush(colorref(face))
	oldPen = _SelectObject(hdc, pen)
	oldBrush = _SelectObject(hdc, brush)
	_RoundRect(hdc, 0, 0, w, h, radius, radius)
	_SelectObject(hdc, oldPen)
	_SelectObject(hdc, oldBrush)
	_DeleteObject(pen)
	_DeleteObject(brush)

	ring = None
	if focused and not (uistate & UISF_HIDEFOCUS):
		ring = FOCUS
	elif default and enabled:
		ring = border
	if ring:
		pen = _CreatePen(PS_SOLID, 1, colorref(ring))
		hollow = _gdi32.GetStockObject(5)  # NULL_BRUSH
		oldPen = _SelectObject(hdc, pen)
		oldBrush = _SelectObject(hdc, hollow)
		_RoundRect(hdc, 1, 1, w - 1, h - 1, radius, radius)
		_SelectObject(hdc, oldPen)
		_SelectObject(hdc, oldBrush)
		_DeleteObject(pen)

	n = _GetWindowTextLengthW(hwnd)
	if n > 0:
		buf = ctypes.create_unicode_buffer(n + 1)
		_GetWindowTextW(hwnd, buf, n + 1)
		font = _SendMessageW(hwnd, WM_GETFONT, 0, 0)
		oldFont = _SelectObject(hdc, font) if font else None
		_SetBkMode(hdc, TRANSPARENT)
		_SetTextColor(hdc, colorref(text))
		flags = DT_CENTER
		if uistate & UISF_HIDEACCEL:
			flags |= DT_HIDEPREFIX
		if style & BS_MULTILINE:
			calc = RECT(0, 0, w - 6, 0)
			_DrawTextW(hdc, buf, -1, ctypes.byref(calc), flags | DT_WORDBREAK | DT_CALCRECT)
			top = max(0, (h - calc.bottom) // 2)
			trc = RECT(3, top, w - 3, top + calc.bottom)
			_DrawTextW(hdc, buf, -1, ctypes.byref(trc), flags | DT_WORDBREAK)
		else:
			trc = RECT(2, 0, w - 2, h)
			_DrawTextW(hdc, buf, -1, ctypes.byref(trc), flags | DT_VCENTER | DT_SINGLELINE)
		if oldFont:
			_SelectObject(hdc, oldFont)


def _excludeChildren(hwnd, hdc):
	"""Keep our background fill off the child controls sitting inside a group box."""
	child = _GetWindow(hwnd, GW_CHILD)
	while child:
		if _IsWindowVisible(child):
			r = RECT()
			_GetWindowRect(child, ctypes.byref(r))
			tl = wintypes.POINT(r.left, r.top)
			br = wintypes.POINT(r.right, r.bottom)
			_user32.ScreenToClient(hwnd, ctypes.byref(tl))
			_user32.ScreenToClient(hwnd, ctypes.byref(br))
			_ExcludeClipRect(hdc, tl.x, tl.y, br.x, br.y)
		child = _GetWindow(child, GW_HWNDNEXT)


def _windowText(hwnd):
	n = _GetWindowTextLengthW(hwnd)
	if n <= 0:
		return None
	buf = ctypes.create_unicode_buffer(n + 1)
	_GetWindowTextW(hwnd, buf, n + 1)
	return buf


def _paintStaticBox(hwnd):
	_paintWith(hwnd, _drawStaticBox)


def _drawStaticBox(hwnd, hdc):
	"""Group box: soft one-pixel frame, label breaking the top edge, like Windows draws it."""
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	w, h = rc.right, rc.bottom
	_excludeChildren(hwnd, hdc)
	bg = _CreateSolidBrush(colorref(PARENT_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	labelX = round(9 * dpi / 96)
	gap = round(2 * dpi / 96)
	text = _windowText(hwnd)
	font = _SendMessageW(hwnd, WM_GETFONT, 0, 0)
	oldFont = _SelectObject(hdc, font) if font else None
	labelH = 0
	labelW = 0
	flags = DT_LEFT | DT_SINGLELINE
	if _SendMessageW(hwnd, WM_QUERYUISTATE, 0, 0) & UISF_HIDEACCEL:
		flags |= DT_HIDEPREFIX
	if text:
		calc = RECT(0, 0, 0, 0)
		_DrawTextW(hdc, text, -1, ctypes.byref(calc), flags | DT_CALCRECT)
		labelW, labelH = calc.right, calc.bottom
	top = labelH // 2
	line = _CreateSolidBrush(colorref(LAYOUT_LINE))
	frame = RECT(0, top, w, h)
	_FrameRect(hdc, ctypes.byref(frame), line)
	if text:
		cover = RECT(labelX - gap, 0, min(w, labelX + labelW + gap), labelH)
		_FillRect(hdc, ctypes.byref(cover), bg)
		_SetBkMode(hdc, TRANSPARENT)
		_SetTextColor(hdc, colorref(BTN_TEXT if _IsWindowEnabled(hwnd) else BTN_DISABLED_TEXT))
		trc = RECT(labelX, 0, min(w, labelX + labelW), labelH)
		_DrawTextW(hdc, text, -1, ctypes.byref(trc), flags)
	if oldFont:
		_SelectObject(hdc, oldFont)
	_DeleteObject(line)
	_DeleteObject(bg)


def _paintStaticLine(hwnd):
	"""wx.StaticLine is all border (WS_EX_STATICEDGE, no client area): paint the window rect."""
	hdc = _GetWindowDC(hwnd)
	if not hdc:
		return
	try:
		_drawStaticLine(hwnd, hdc)
	finally:
		_ReleaseDC(hwnd, hdc)


def _drawStaticLine(hwnd, hdc):
	wr = RECT()
	_GetWindowRect(hwnd, ctypes.byref(wr))
	w, h = wr.right - wr.left, wr.bottom - wr.top
	rc = RECT(0, 0, w, h)
	bg = _CreateSolidBrush(colorref(PARENT_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)
	_DeleteObject(bg)
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	t = max(1, round(dpi / 96))
	if w >= h:
		y = max(0, h // 2 - t // 2)
		r = RECT(0, y, w, min(h, y + t))
	else:
		x = max(0, w // 2 - t // 2)
		r = RECT(x, 0, min(w, x + t), h)
	line = _CreateSolidBrush(colorref(LAYOUT_LINE))
	_FillRect(hdc, ctypes.byref(r), line)
	_DeleteObject(line)


def _drawTitleSeparator(hwnd, hdc):
	"""A soft line along the top of a dialog's client area, where the title bar ends."""
	if (_GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION) != WS_CAPTION:
		return
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	t = max(1, round(dpi / 96))
	r = RECT(0, 0, rc.right, min(rc.bottom, t))
	line = _CreateSolidBrush(colorref(LAYOUT_LINE))
	_FillRect(hdc, ctypes.byref(r), line)
	_DeleteObject(line)


def _paintCheckItem(dis):
	"""Draw one wx.CheckListBox row: background, check box glyph, label."""
	ref = _checkLists.get(dis.hwndItem)
	win = ref() if ref else None
	if win is None or dis.itemID == 0xFFFFFFFF:
		return False
	hdc = dis.hDC
	rc = dis.rcItem
	selected = bool(dis.itemState & ODS_SELECTED)
	disabled = bool(dis.itemState & ODS_DISABLED) or not _IsWindowEnabled(dis.hwndItem)
	hasFocus = _GetFocus() == dis.hwndItem
	try:
		checked = bool(win.IsChecked(dis.itemID))
		text = win.GetString(dis.itemID)
	except Exception:
		checked, text = False, ""

	if selected and hasFocus:
		bg = _GetSysColor(COLOR_HIGHLIGHT)
		fg = _GetSysColor(COLOR_HIGHLIGHTTEXT)
	elif selected:
		bg = colorref(LIST_SEL_UNFOCUSED_BG)
		fg = colorref(LIST_TEXT)
	else:
		bg = colorref(LIST_BG)
		fg = colorref(LIST_DISABLED_TEXT if disabled else LIST_TEXT)
	brush = _CreateSolidBrush(bg)
	_FillRect(hdc, ctypes.byref(rc), brush)
	_DeleteObject(brush)

	# Check box glyph from the (dark) Button theme of the list box itself.
	height = rc.bottom - rc.top
	glyph = max(12, height - 4)
	theme = _OpenThemeData(dis.hwndItem, "Button")
	if theme:
		size = SIZE()
		if _GetThemePartSize(theme, hdc, BP_CHECKBOX, CBS_UNCHECKEDNORMAL, None, 1, ctypes.byref(size)) == 0 and size.cx:
			glyph = min(size.cx, height)
	pad = max(2, glyph // 6)
	top = rc.top + (height - glyph) // 2
	box = RECT(rc.left + pad, top, rc.left + pad + glyph, top + glyph)
	if theme:
		if checked:
			state = CBS_CHECKEDDISABLED if disabled else CBS_CHECKEDNORMAL
		else:
			state = CBS_UNCHECKEDDISABLED if disabled else CBS_UNCHECKEDNORMAL
		_DrawThemeBackground(theme, hdc, BP_CHECKBOX, state, ctypes.byref(box), None)
		_CloseThemeData(theme)
	else:
		_user32.DrawFrameControl(hdc, ctypes.byref(box), 4, 0x0001 | (0x0400 if checked else 0))  # DFC_BUTTON, DFCS_BUTTONCHECK

	font = _SendMessageW(dis.hwndItem, WM_GETFONT, 0, 0)
	oldFont = _SelectObject(hdc, font) if font else None
	_SetBkMode(hdc, TRANSPARENT)
	_SetTextColor(hdc, fg)
	trc = RECT(box.right + pad * 2, rc.top, rc.right - 2, rc.bottom)
	_DrawTextW(hdc, text, -1, ctypes.byref(trc), DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS)
	if oldFont:
		_SelectObject(hdc, oldFont)
	if dis.itemState & ODS_FOCUS and hasFocus:
		ring = _CreateSolidBrush(colorref(FOCUS))
		_FrameRect(hdc, ctypes.byref(rc), ring)
		_DeleteObject(ring)
	return True


def _paintGrip(hwnd):
	"""Dialog size grip: dialog background with a small triangle of dim dots in the corner."""
	_paintWith(hwnd, _drawGrip)


def _drawGrip(hwnd, hdc):
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	bg = _CreateSolidBrush(colorref(PARENT_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)
	_DeleteObject(bg)
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	dot = max(1, round(1.5 * dpi / 96))
	step = dot * 2
	margin = max(2, round(4 * dpi / 96))
	dotBrush = _CreateSolidBrush(colorref(GRIP_DOT))
	# rows of 1, 2, 3 dots, anchored to the bottom-right corner
	for row in range(3):
		for col in range(row + 1):
			x = rc.right - margin - dot - (row - col) * step
			y = rc.bottom - margin - dot - (2 - row) * step
			r = RECT(x, y, x + dot, y + dot)
			_FillRect(hdc, ctypes.byref(r), dotBrush)
	_DeleteObject(dotBrush)


def _tabText(hwnd, index):
	buf = ctypes.create_unicode_buffer(256)
	item = TCITEMW()
	item.mask = TCIF_TEXT
	item.pszText = ctypes.cast(buf, wintypes.LPWSTR)
	item.cchTextMax = 256
	_SendMessageW(hwnd, TCM_GETITEMW, index, ctypes.addressof(item))
	return buf.value


def _paintTabs(hwnd):
	_paintWith(hwnd, _drawTabs)


def _drawTabs(hwnd, hdc):
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	bg = _CreateSolidBrush(colorref(PARENT_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)
	_DeleteObject(bg)
	count = _SendMessageW(hwnd, TCM_GETITEMCOUNT, 0, 0)
	selected = _SendMessageW(hwnd, TCM_GETCURSEL, 0, 0)
	hot = _tabHot.get(hwnd, -1)
	focused = _GetFocus() == hwnd
	uistate = _SendMessageW(hwnd, WM_QUERYUISTATE, 0, 0)
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	radius = max(2, round(4 * dpi / 96))
	font = _SendMessageW(hwnd, WM_GETFONT, 0, 0)
	oldFont = _SelectObject(hdc, font) if font else None
	_SetBkMode(hdc, TRANSPARENT)
	stripBottom = 0
	for i in range(count):
		r = RECT()
		_SendMessageW(hwnd, TCM_GETITEMRECT, i, ctypes.addressof(r))
		stripBottom = max(stripBottom, r.bottom)
		isSel = i == selected
		if isSel:
			face, border, text = TAB_SELECTED_FACE, BORDER, TAB_SELECTED_TEXT
		elif i == hot:
			face, border, text = TAB_HOT_FACE, BTN_HOT_BORDER, TAB_SELECTED_TEXT
		else:
			face, border, text = PARENT_BG, BTN_DISABLED_BORDER, TAB_TEXT
		pen = _CreatePen(PS_SOLID, 1, colorref(border))
		brush = _CreateSolidBrush(colorref(face))
		oldPen = _SelectObject(hdc, pen)
		oldBrush = _SelectObject(hdc, brush)
		# Rounded on top only: extend the rect below the strip and let the
		# separator line cover the bottom corners.
		_RoundRect(hdc, r.left, r.top, r.right, r.bottom + radius, radius, radius)
		_SelectObject(hdc, oldPen)
		_SelectObject(hdc, oldBrush)
		_DeleteObject(pen)
		_DeleteObject(brush)
		if isSel and focused and not (uistate & UISF_HIDEFOCUS):
			pen = _CreatePen(PS_SOLID, 1, colorref(FOCUS))
			hollow = _gdi32.GetStockObject(5)
			oldPen = _SelectObject(hdc, pen)
			oldBrush = _SelectObject(hdc, hollow)
			_RoundRect(hdc, r.left + 2, r.top + 2, r.right - 2, r.bottom + radius, radius, radius)
			_SelectObject(hdc, oldPen)
			_SelectObject(hdc, oldBrush)
			_DeleteObject(pen)
		_SetTextColor(hdc, colorref(text))
		trc = RECT(r.left + 2, r.top, r.right - 2, r.bottom)
		flags = DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS
		if uistate & UISF_HIDEACCEL:
			flags |= DT_HIDEPREFIX
		_DrawTextW(hdc, _tabText(hwnd, i), -1, ctypes.byref(trc), flags)
	if count:
		# Separator under the strip, tucking the selected tab into the page.
		line = _CreateSolidBrush(colorref(BORDER))
		sep = RECT(rc.left, stripBottom, rc.right, stripBottom + 1)
		_FillRect(hdc, ctypes.byref(sep), line)
		_DeleteObject(line)
		if 0 <= selected < count:
			r = RECT()
			_SendMessageW(hwnd, TCM_GETITEMRECT, selected, ctypes.addressof(r))
			gap = RECT(r.left + 1, stripBottom, r.right - 1, stripBottom + 1)
			face = _CreateSolidBrush(colorref(TAB_SELECTED_FACE))
			_FillRect(hdc, ctypes.byref(gap), face)
			_DeleteObject(face)
	if oldFont:
		_SelectObject(hdc, oldFont)


def _headerItem(hwnd, index):
	buf = ctypes.create_unicode_buffer(256)
	item = HDITEMW()
	item.mask = HDI_TEXT | HDI_FORMAT
	item.pszText = ctypes.cast(buf, wintypes.LPWSTR)
	item.cchTextMax = 256
	_SendMessageW(hwnd, HDM_GETITEMW, index, ctypes.addressof(item))
	return buf.value, item.fmt


def _paintHeader(hwnd):
	_paintWith(hwnd, _drawHeader)


def _drawHeader(hwnd, hdc):
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	bg = _CreateSolidBrush(colorref(HEADER_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)
	_DeleteObject(bg)
	count = _SendMessageW(hwnd, HDM_GETITEMCOUNT, 0, 0)
	hot = _tabHot.get(hwnd, -1)
	font = _SendMessageW(hwnd, WM_GETFONT, 0, 0)
	oldFont = _SelectObject(hdc, font) if font else None
	_SetBkMode(hdc, TRANSPARENT)
	sepBrush = _CreateSolidBrush(colorref(HEADER_SEPARATOR))
	hotBrush = _CreateSolidBrush(colorref(HEADER_HOT_BG))
	textBrush = _CreateSolidBrush(colorref(HEADER_TEXT))
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	pad = max(3, round(4 * dpi / 96))
	for i in range(count):
		r = RECT()
		_SendMessageW(hwnd, HDM_GETITEMRECT, i, ctypes.addressof(r))
		if i == hot:
			_FillRect(hdc, ctypes.byref(r), hotBrush)
		text, fmt = _headerItem(hwnd, i)
		align = fmt & HDF_JUSTIFYMASK
		flags = DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX
		flags |= DT_CENTER if align == HDF_CENTER else DT_RIGHT if align == HDF_RIGHT else DT_LEFT
		_SetTextColor(hdc, colorref(HEADER_TEXT))
		trc = RECT(r.left + pad, r.top, r.right - pad, r.bottom)
		_DrawTextW(hdc, text, -1, ctypes.byref(trc), flags)
		if fmt & (HDF_SORTUP | HDF_SORTDOWN):
			# small sort triangle at the top centre of the column
			size = max(3, round(3 * dpi / 96))
			cx = (r.left + r.right) // 2
			top = r.top + 1
			if fmt & HDF_SORTUP:
				pts = (wintypes.POINT * 3)(wintypes.POINT(cx - size, top + size), wintypes.POINT(cx + size, top + size), wintypes.POINT(cx, top))
			else:
				pts = (wintypes.POINT * 3)(wintypes.POINT(cx - size, top), wintypes.POINT(cx + size, top), wintypes.POINT(cx, top + size))
			pen = _CreatePen(PS_SOLID, 1, colorref(HEADER_TEXT))
			oldPen = _SelectObject(hdc, pen)
			oldBrush = _SelectObject(hdc, textBrush)
			_gdi32.Polygon(hdc, pts, 3)
			_SelectObject(hdc, oldPen)
			_SelectObject(hdc, oldBrush)
			_DeleteObject(pen)
		sep = RECT(r.right - 1, r.top + pad, r.right, r.bottom - pad)
		_FillRect(hdc, ctypes.byref(sep), sepBrush)
	bottomBrush = _CreateSolidBrush(colorref(HEADER_BOTTOM))
	bottom = RECT(rc.left, rc.bottom - 1, rc.right, rc.bottom)
	_FillRect(hdc, ctypes.byref(bottom), bottomBrush)
	_DeleteObject(bottomBrush)
	_DeleteObject(sepBrush)
	_DeleteObject(hotBrush)
	_DeleteObject(textBrush)
	if oldFont:
		_SelectObject(hdc, oldFont)


def _headerHitTest(hwnd, lParam):
	info = HDHITTESTINFO()
	info.pt.x = ctypes.c_short(lParam & 0xFFFF).value
	info.pt.y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
	_SendMessageW(hwnd, HDM_HITTEST, 0, ctypes.addressof(info))
	return info.iItem


def _tabHitTest(hwnd, lParam):
	info = TCHITTESTINFO()
	info.pt.x = ctypes.c_short(lParam & 0xFFFF).value
	info.pt.y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
	return _SendMessageW(hwnd, TCM_HITTEST, 0, ctypes.addressof(info))


def applyRichColours(hwnd, textRgb, bgRgb):
	"""Rich edits ignore WM_CTLCOLOR; set their default and current character colour directly."""
	cf = CHARFORMATW()
	cf.cbSize = ctypes.sizeof(cf)
	cf.dwMask = CFM_COLOR
	cf.crTextColor = colorref(textRgb)
	_SendMessageW(hwnd, EM_SETCHARFORMAT, SCF_DEFAULT, ctypes.addressof(cf))
	_SendMessageW(hwnd, EM_SETCHARFORMAT, SCF_ALL, ctypes.addressof(cf))
	_SendMessageW(hwnd, EM_SETBKGNDCOLOR, 0, colorref(bgRgb))


def _proc(hwnd, msg, wParam, lParam, idSubclass, refData):
	try:
		if msg == WM_NCDESTROY:
			_RemoveWindowSubclass(hwnd, _subclassProc, idSubclass)
			_subclassed.pop(hwnd, None)
			_checkLists.pop(hwnd, None)
			_eraseColours.pop(hwnd, None)
			_frameColours.pop(hwnd, None)
			_framePending.discard(hwnd)
			_tabHot.pop(hwnd, None)
			return _DefSubclassProc(hwnd, msg, wParam, lParam)
		if idSubclass == ID_OWNERDRAW:
			if msg == WM_DRAWITEM:
				dis = DRAWITEMSTRUCT.from_address(lParam)
				if dis.CtlType == ODT_LISTBOX and dis.hwndItem in _checkLists and _paintCheckItem(dis):
					return 1
		if idSubclass == ID_FRAME:
			if msg == WM_NCPAINT:
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_paintFrame(hwnd)
				# Some controls (list views) repaint their themed edge after this
				# returns, so come back once the queue has drained and paint again.
				if hwnd not in _framePending:
					_framePending.add(hwnd)
					_user32.PostMessageW(hwnd, WM_DARK_FRAME, 0, 0)
				return res
			if msg == WM_DARK_FRAME:
				_framePending.discard(hwnd)
				_paintFrame(hwnd)
				return 0
			if msg in (WM_SETFOCUS, WM_KILLFOCUS):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_RedrawWindow(hwnd, None, None, RDW_FRAME | RDW_INVALIDATE)
				return res
		elif idSubclass == ID_RICH:
			if msg in (WM_SETTEXT, EM_SETTEXTEX, EM_REPLACESEL):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				applyRichColours(hwnd, LIST_TEXT, LIST_BG)
				return res
		elif idSubclass == ID_HEADER:
			if msg == WM_PAINT:
				_paintHeader(hwnd)
				return 0
			if msg == WM_ERASEBKGND:
				_drawHeader(hwnd, wParam)  # look final from the first erase (see ID_ERASE)
				return 1
			if msg == WM_MOUSEMOVE:
				hit = _headerHitTest(hwnd, lParam)
				if _tabHot.get(hwnd, -1) != hit:
					_tabHot[hwnd] = hit
					_InvalidateRect(hwnd, None, False)
				tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE, hwnd, 0)
				_user32.TrackMouseEvent(ctypes.byref(tme))
			elif msg == WM_MOUSELEAVE:
				if _tabHot.pop(hwnd, None) is not None:
					_InvalidateRect(hwnd, None, False)
		elif idSubclass == ID_TABS:
			if msg == WM_PAINT:
				_paintTabs(hwnd)
				return 0
			if msg == WM_ERASEBKGND:
				_drawTabs(hwnd, wParam)
				return 1
			if msg == WM_MOUSEMOVE:
				hit = _tabHitTest(hwnd, lParam)
				if _tabHot.get(hwnd, -1) != hit:
					_tabHot[hwnd] = hit
					_InvalidateRect(hwnd, None, False)
				tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE, hwnd, 0)
				_user32.TrackMouseEvent(ctypes.byref(tme))
			elif msg == WM_MOUSELEAVE:
				if _tabHot.pop(hwnd, None) is not None:
					_InvalidateRect(hwnd, None, False)
			elif msg in (WM_SETFOCUS, WM_KILLFOCUS, WM_UPDATEUISTATE):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_InvalidateRect(hwnd, None, False)
				return res
		elif idSubclass == ID_GRIP:
			if msg == WM_PAINT:
				_paintGrip(hwnd)
				return 0
			if msg == WM_ERASEBKGND:
				_drawGrip(hwnd, wParam)
				return 1
		elif idSubclass == ID_STATICBOX:
			if msg == WM_PAINT:
				_paintStaticBox(hwnd)
				return 0
			if msg == WM_ERASEBKGND:
				_drawStaticBox(hwnd, wParam)
				return 1
			if msg in (WM_ENABLE, WM_UPDATEUISTATE):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_InvalidateRect(hwnd, None, False)
				return res
		elif idSubclass == ID_STATICLINE:
			if msg == WM_NCPAINT:
				_paintStaticLine(hwnd)
				return 0
			if msg == WM_PAINT:
				_paintWith(hwnd, lambda h, dc: None)  # validate the (empty) client area
				_paintStaticLine(hwnd)
				return 0
			if msg == WM_ERASEBKGND:
				return 1
		elif idSubclass == ID_SHOWPAINT:
			if msg == WM_ERASEBKGND:
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_drawTitleSeparator(hwnd, wParam)
				return res
			if msg == WM_PAINT:
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				hdc = _GetDC(hwnd)
				if hdc:
					try:
						_drawTitleSeparator(hwnd, hdc)
					finally:
						_ReleaseDC(hwnd, hdc)
				return res
			if msg == WM_WINDOWPOSCHANGED and WINDOWPOS.from_address(lParam).flags & SWP_SHOWWINDOW:
				# The window just became visible. Windows has erased it (dark, thanks to the
				# rest of this file) but the real painting would wait for the message loop,
				# and NVDA spends ~100 ms announcing a new dialog first. Paint the whole tree
				# now, inside the show call, so the first frame anyone sees is the finished one.
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)  # lets wx lay the dialog out
				_RedrawWindow(hwnd, None, None, RDW_UPDATENOW | RDW_ALLCHILDREN)
				return res
		elif idSubclass == ID_ERASE:
			if msg == WM_ERASEBKGND:
				# Some controls (list views, static boxes, gauges...) leave their background
				# alone until WM_PAINT. NVDA is busy for ~100 ms after a dialog appears, so
				# the raw white surface showed in between. Lay down the dark base now.
				rgb = _eraseColours.get(hwnd)
				if rgb is not None:
					rc = RECT()
					_GetClientRect(hwnd, ctypes.byref(rc))
					brush = _CreateSolidBrush(colorref(rgb))
					_FillRect(wParam, ctypes.byref(rc), brush)
					_DeleteObject(brush)
		elif idSubclass == ID_MENUPOPUP:
			if msg == WM_ERASEBKGND:
				# Windows erases a new popup menu with the light menu colour and paints the
				# dark menu later. In NVDA "later" is tens of ms (it reads its own menu in
				# between), long enough to see. Erase dark instead; the real paint follows.
				rc = RECT()
				_GetClientRect(hwnd, ctypes.byref(rc))
				brush = _CreateSolidBrush(colorref(MENU_BG))
				_FillRect(wParam, ctypes.byref(rc), brush)
				_DeleteObject(brush)
				return 1
		elif idSubclass == ID_BUTTON:
			if msg == WM_PAINT:
				_paintButton(hwnd)
				return 0
			if msg == WM_ERASEBKGND:
				_drawButton(hwnd, wParam)
				return 1
			if msg in (WM_ENABLE, WM_UPDATEUISTATE):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_InvalidateRect(hwnd, None, False)
				return res
	except Exception:
		log.exception("nvdaDarkMode: paint hook failed")
	return _DefSubclassProc(hwnd, msg, wParam, lParam)


_eraseColours = {}  # hwnd -> rgb laid down on WM_ERASEBKGND (ID_ERASE)
_frameColours = {}  # hwnd -> frame colour when not focused (ID_FRAME); default BORDER
_subclassProc = _SUBCLASSPROC(_proc)  # must stay alive for as long as any window is subclassed


def _attach(hwnd, idSubclass):
	if not hwnd or not _IsWindow(hwnd):
		return
	ids = _subclassed.setdefault(hwnd, set())
	if idSubclass in ids:
		return
	if _SetWindowSubclass(hwnd, _subclassProc, idSubclass, 0):
		ids.add(idSubclass)


def _detach(hwnd, idSubclass):
	ids = _subclassed.get(hwnd)
	if not ids or idSubclass not in ids:
		return
	if _IsWindow(hwnd):
		_RemoveWindowSubclass(hwnd, _subclassProc, idSubclass)
	ids.discard(idSubclass)
	if not ids:
		_subclassed.pop(hwnd, None)


# --- Public API --------------------------------------------------------------
def hasFrame(hwnd) -> bool:
	ex = _GetWindowLongW(hwnd, GWL_EXSTYLE)
	st = _GetWindowLongW(hwnd, GWL_STYLE)
	return bool(ex & WS_EX_CLIENTEDGE) or bool(st & WS_BORDER)


def isPlainPushButton(hwnd) -> bool:
	st = _GetWindowLongW(hwnd, GWL_STYLE)
	if (st & BS_TYPEMASK) not in (BS_PUSHBUTTON, BS_DEFPUSHBUTTON):
		return False
	# Buttons showing an image are left to the theme.
	return not _SendMessageW(hwnd, BM_GETIMAGE, 0, 0) and not _SendMessageW(hwnd, BM_GETIMAGE, 1, 0)


def spinBuddy(hwndUpDown):
	"""The edit box paired with an up-down control (wx.SpinCtrl has no wx wrapper for it)."""
	return _SendMessageW(hwndUpDown, UDM_GETBUDDY, 0, 0)


def applyFrame(hwnd, dark: bool, colour=None):
	if dark:
		if colour is not None:
			_frameColours[hwnd] = colour
		_attach(hwnd, ID_FRAME)
	else:
		_frameColours.pop(hwnd, None)
		_detach(hwnd, ID_FRAME)
	if _IsWindow(hwnd):
		_RedrawWindow(hwnd, None, None, RDW_FRAME | RDW_INVALIDATE | RDW_ERASE)


def applyButton(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_BUTTON)
	else:
		_detach(hwnd, ID_BUTTON)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def isRichEdit(hwnd) -> bool:
	buf = ctypes.create_unicode_buffer(64)
	_user32.GetClassNameW(hwnd, buf, 64)
	return buf.value.upper().startswith("RICHEDIT")


def applyRich(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_RICH)
		applyRichColours(hwnd, LIST_TEXT, LIST_BG)
	else:
		_detach(hwnd, ID_RICH)
		sysText = _GetSysColor(8)  # COLOR_WINDOWTEXT
		sysBg = _GetSysColor(5)  # COLOR_WINDOW
		applyRichColours(hwnd, (sysText & 0xFF, (sysText >> 8) & 0xFF, (sysText >> 16) & 0xFF), (sysBg & 0xFF, (sysBg >> 8) & 0xFF, (sysBg >> 16) & 0xFF))
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def applyHeader(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_HEADER)
	else:
		_detach(hwnd, ID_HEADER)
		_tabHot.pop(hwnd, None)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def applyTabs(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_TABS)
	else:
		_detach(hwnd, ID_TABS)
		_tabHot.pop(hwnd, None)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


SBS_SIZEBOX = 0x0008
SBS_SIZEGRIP = 0x0010
GW_CHILD = 5
GW_HWNDNEXT = 2
_GetWindow = _user32.GetWindow
_GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
_GetWindow.restype = wintypes.HWND


def sizeGrips(hwndParent):
	"""Size grip windows directly under a top-level window (wx creates one per resizable dialog)."""
	out = []
	buf = ctypes.create_unicode_buffer(64)
	h = _GetWindow(hwndParent, GW_CHILD)
	while h:
		_user32.GetClassNameW(h, buf, 64)
		if buf.value.lower() == "scrollbar" and _GetWindowLongW(h, GWL_STYLE) & (SBS_SIZEBOX | SBS_SIZEGRIP):
			out.append(h)
		h = _GetWindow(h, GW_HWNDNEXT)
	return out


def applyGrip(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_GRIP)
	else:
		_detach(hwnd, ID_GRIP)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def applyShowPaint(hwnd, dark: bool):
	"""Paint a top-level window and all its children synchronously whenever it is shown."""
	if dark:
		_attach(hwnd, ID_SHOWPAINT)
	else:
		_detach(hwnd, ID_SHOWPAINT)


def applyStaticBox(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_STATICBOX)
	else:
		_detach(hwnd, ID_STATICBOX)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def applyStaticLine(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_STATICLINE)
	else:
		_detach(hwnd, ID_STATICLINE)
	if _IsWindow(hwnd):
		_RedrawWindow(hwnd, None, None, RDW_FRAME | RDW_INVALIDATE | RDW_ERASE)


def applyEraseBase(hwnd, rgb, dark: bool):
	"""Dark base colour under a control's own (late) background painting; None/dark=False removes it."""
	if dark:
		_eraseColours[hwnd] = rgb
		_attach(hwnd, ID_ERASE)
	else:
		_eraseColours.pop(hwnd, None)
		_detach(hwnd, ID_ERASE)


def registerCheckList(hwnd, hwndParent, win, dark: bool):
	"""Owner-draw the rows of a wx.CheckListBox (its parent receives WM_DRAWITEM)."""
	if dark:
		_checkLists[hwnd] = weakref.ref(win)
		_attach(hwndParent, ID_OWNERDRAW)
	else:
		_checkLists.pop(hwnd, None)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


# --- Popup menu hook ---------------------------------------------------------
# A thread-local CBT hook sees every window created on this thread before it is
# shown; popup menu windows get the ID_MENUPOPUP subclass so their first erase is dark.
WH_CBT = 5
HCBT_CREATEWND = 3
MENU_POPUP_CLASS = "#32768"
_CBTPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_SetWindowsHookExW = _user32.SetWindowsHookExW
_SetWindowsHookExW.argtypes = (ctypes.c_int, _CBTPROC, wintypes.HINSTANCE, wintypes.DWORD)
_SetWindowsHookExW.restype = wintypes.HHOOK
_UnhookWindowsHookEx = _user32.UnhookWindowsHookEx
_UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
_CallNextHookEx = _user32.CallNextHookEx
_CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_CallNextHookEx.restype = ctypes.c_ssize_t
_menuHook = None


def _cbt(code, wParam, lParam):
	try:
		if code == HCBT_CREATEWND:
			buf = ctypes.create_unicode_buffer(64)
			_user32.GetClassNameW(wParam, buf, 64)
			if buf.value == MENU_POPUP_CLASS:
				_attach(wParam, ID_MENUPOPUP)
	except Exception:
		log.exception("nvdaDarkMode: menu hook failed")
	return _CallNextHookEx(_menuHook, code, wParam, lParam)


_cbtProc = _CBTPROC(_cbt)  # must stay alive while the hook is installed


def installMenuHook():
	"""Start giving popup menus a dark first erase. Call from the thread that shows the menus."""
	global _menuHook
	if _menuHook:
		return
	_menuHook = _SetWindowsHookExW(WH_CBT, _cbtProc, None, ctypes.windll.kernel32.GetCurrentThreadId())
	if not _menuHook:
		log.warning("nvdaDarkMode: could not install the popup menu hook (error %d)" % ctypes.get_last_error())


def removeMenuHook():
	global _menuHook
	if _menuHook:
		_UnhookWindowsHookEx(_menuHook)
		_menuHook = None


def detachAll():
	removeMenuHook()
	_eraseColours.clear()
	_frameColours.clear()
	_checkLists.clear()
	_tabHot.clear()
	for hwnd, ids in list(_subclassed.items()):
		for i in list(ids):
			_detach(hwnd, i)
		if _IsWindow(hwnd):
			_RedrawWindow(hwnd, None, None, RDW_FRAME | RDW_INVALIDATE | RDW_ERASE)
