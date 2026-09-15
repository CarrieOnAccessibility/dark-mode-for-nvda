# Dark Mode: an NVDA add-on. Copyright (C) 2026 Carrie on Accessibility.
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, version 2.
# See the LICENSE file for details.
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

	log = logging.getLogger("darkMode")

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


class NMHDR(ctypes.Structure):
	_fields_ = [("hwndFrom", wintypes.HWND), ("idFrom", ctypes.c_size_t), ("code", wintypes.UINT)]


class NMCUSTOMDRAW(ctypes.Structure):
	_fields_ = [
		("hdr", NMHDR),
		("dwDrawStage", wintypes.DWORD),
		("hdc", HANDLE),
		("rc", RECT),
		("dwItemSpec", ctypes.c_size_t),
		("uItemState", wintypes.UINT),
		("lItemlParam", ctypes.c_ssize_t),
	]


class LVITEMW(ctypes.Structure):
	_fields_ = [
		("mask", wintypes.UINT),
		("iItem", ctypes.c_int),
		("iSubItem", ctypes.c_int),
		("state", wintypes.UINT),
		("stateMask", wintypes.UINT),
		("pszText", wintypes.LPWSTR),
		("cchTextMax", ctypes.c_int),
		("iImage", ctypes.c_int),
		("lParam", ctypes.c_ssize_t),
		("iIndent", ctypes.c_int),
		("iGroupId", ctypes.c_int),
		("cColumns", wintypes.UINT),
		("puColumns", ctypes.c_void_p),
		("piColFmt", ctypes.c_void_p),
		("iGroup", ctypes.c_int),
	]


class LVCOLUMNW(ctypes.Structure):
	_fields_ = [
		("mask", wintypes.UINT),
		("fmt", ctypes.c_int),
		("cx", ctypes.c_int),
		("pszText", wintypes.LPWSTR),
		("cchTextMax", ctypes.c_int),
		("iSubItem", ctypes.c_int),
		("iImage", ctypes.c_int),
		("iOrder", ctypes.c_int),
		("cxMin", ctypes.c_int),
		("cxDefault", ctypes.c_int),
		("cxIdeal", ctypes.c_int),
	]


class NMLVCUSTOMDRAW(ctypes.Structure):
	_fields_ = [
		("nmcd", NMCUSTOMDRAW),
		("clrText", wintypes.COLORREF),
		("clrTextBk", wintypes.COLORREF),
		("iSubItem", ctypes.c_int),
		("dwItemType", wintypes.DWORD),
		("clrFace", wintypes.COLORREF),
		("iIconEffect", ctypes.c_int),
		("iIconPhase", ctypes.c_int),
		("iPartId", ctypes.c_int),
		("iStateId", ctypes.c_int),
		("rcText", RECT),
		("uAlign", wintypes.UINT),
	]


# Menu bar drawing hooks. Windows sends these undocumented "UAH" messages to a window
# with a menu bar so that themed apps can draw the bar themselves; the menu items are
# untouched (still in the HMENU, still read by screen readers), only the pixels change.
WM_UAHDRAWMENU = 0x0091
WM_UAHDRAWMENUITEM = 0x0092
WM_NCACTIVATE = 0x0086
OBJID_MENU = 0xFFFFFFFD
MIIM_STRING = 0x0040
ODS_SELECTED = 0x0001
ODS_GRAYED = 0x0002
ODS_DISABLED = 0x0004
ODS_HOTLIGHT = 0x0040
ODS_INACTIVE = 0x0080
ODS_NOACCEL = 0x0100


class UAHMENU(ctypes.Structure):
	_fields_ = [("hmenu", HANDLE), ("hdc", HANDLE), ("dwFlags", wintypes.DWORD)]


class UAHDRAWMENUITEM(ctypes.Structure):
	_fields_ = [("dis", DRAWITEMSTRUCT), ("um", UAHMENU), ("iPosition", ctypes.c_int)]


class MENUBARINFO(ctypes.Structure):
	_fields_ = [
		("cbSize", wintypes.DWORD),
		("rcBar", RECT),
		("hMenu", HANDLE),
		("hwndMenu", wintypes.HWND),
		("flags", wintypes.DWORD),
	]


class MENUITEMINFOW(ctypes.Structure):
	_fields_ = [
		("cbSize", wintypes.UINT),
		("fMask", wintypes.UINT),
		("fType", wintypes.UINT),
		("fState", wintypes.UINT),
		("wID", wintypes.UINT),
		("hSubMenu", HANDLE),
		("hbmpChecked", HANDLE),
		("hbmpUnchecked", HANDLE),
		("dwItemData", ctypes.c_size_t),
		("dwTypeData", wintypes.LPWSTR),
		("cch", wintypes.UINT),
		("hbmpItem", HANDLE),
	]


_GetMenu = _user32.GetMenu
_GetMenu.argtypes = (wintypes.HWND,)
_GetMenu.restype = HANDLE
_GetMenuBarInfo = _user32.GetMenuBarInfo
_GetMenuBarInfo.argtypes = (wintypes.HWND, ctypes.c_long, ctypes.c_long, ctypes.POINTER(MENUBARINFO))
_GetMenuItemInfoW = _user32.GetMenuItemInfoW
_GetMenuItemInfoW.argtypes = (HANDLE, wintypes.UINT, wintypes.BOOL, ctypes.POINTER(MENUITEMINFOW))


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
_Polygon = _gdi32.Polygon
_Polygon.argtypes = (HANDLE, ctypes.c_void_p, ctypes.c_int)
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
WM_SETFONT = 0x0030
WM_THEMECHANGED = 0x031A
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
WM_NOTIFY = 0x004E
NM_CUSTOMDRAW = 0xFFFFFFF4  # (UINT)(-12)
CDDS_PREPAINT = 0x0001
CDDS_ITEMPREPAINT = 0x00010001
CDRF_DODEFAULT = 0x0
CDRF_SKIPDEFAULT = 0x4
CDRF_NOTIFYITEMDRAW = 0x20
CDRF_NEWFONT = 0x2
CDIS_FOCUS = 0x0010
TBCD_CHANNEL = 0x3
TBCD_THUMB = 0x2
TBM_GETTHUMBRECT = 0x0400 + 25
CDIS_SELECTED = 0x0001
CDIS_DISABLED = 0x0004
CDIS_HOT = 0x0040
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
WM_DARK_RELAYOUT = 0x8000 + 0x38  # WM_APP + 0x38: "the dialog has been laid out; repaint it all"
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
BP_RADIOBUTTON = 2
BM_GETCHECK = 0x00F0
BST_CHECKED = 0x0001
RADIO_TEXT = (0xFF, 0xFF, 0xFF)
RADIO_DISABLED_TEXT = (0x9C, 0x9C, 0x9C)
CBS_UNCHECKEDNORMAL = 1
CBS_UNCHECKEDDISABLED = 4
CBS_CHECKEDNORMAL = 5
CBS_CHECKEDDISABLED = 8
COLOR_HIGHLIGHT = 13
COLOR_HIGHLIGHTTEXT = 14
UIS_SET = 1
UIS_CLEAR = 2
LB_GETSEL = 0x0187
LB_GETCURSEL = 0x0188
LB_GETTEXT = 0x0189
LB_GETTEXTLEN = 0x018A
LB_GETCOUNT = 0x018B
LB_GETTOPINDEX = 0x018E
LB_GETITEMRECT = 0x0198
LB_GETCARETINDEX = 0x019F
LBS_MULTIPLESEL = 0x0008
LB_SETSEL = 0x0185
LB_SETCURSEL = 0x0186
LB_SETTOPINDEX = 0x0197
LB_SELITEMRANGE = 0x019B
LB_SETCARETINDEX = 0x019E
WM_KEYDOWN = 0x0100
WM_CHAR = 0x0102
WM_TIMER = 0x0113
WM_VSCROLL = 0x0115
WM_MOUSEWHEEL = 0x020A
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
LISTBOX_REDRAW_MESSAGES = (
	WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_KEYDOWN, WM_CHAR, WM_TIMER, WM_VSCROLL, WM_MOUSEWHEEL,
	LB_SETSEL, LB_SETCURSEL, LB_SETTOPINDEX, LB_SELITEMRANGE, LB_SETCARETINDEX,
)
LBS_EXTENDEDSEL = 0x0800
LVM_GETNEXTITEM = 0x1000 + 12
LVM_GETITEMRECT = 0x1000 + 14
LVNI_FOCUSED = 0x0001
LVIR_BOUNDS = 0
TVM_GETITEMRECT = 0x1100 + 4
TVM_GETNEXTITEM = 0x1100 + 10
TVGN_CARET = 9
LVM_GETIMAGELIST = 0x1000 + 2
LVM_GETHEADER = 0x1000 + 31
LVM_GETITEMSTATE = 0x1000 + 44
LVM_GETEXTENDEDLISTVIEWSTYLE = 0x1000 + 55
LVM_GETSUBITEMRECT = 0x1000 + 56
LVM_GETCOLUMNW = 0x1000 + 95
LVM_GETITEMTEXTW = 0x1000 + 115
LVIS_SELECTED = 0x0002
LVIS_STATEIMAGEMASK = 0xF000
LVS_EX_CHECKBOXES = 0x0004
LVS_EX_FULLROWSELECT = 0x0020
LVSIL_SMALL = 1
LVIR_ICON = 1
LVIR_LABEL = 2
LVCF_FMT = 0x1
LVCFMT_JUSTIFYMASK = 0x3
LVCFMT_RIGHT = 0x1
LVCFMT_CENTER = 0x2
LISTVIEW_TEXT_X = 2  # first column: text inset inside the label rect, measured against Windows' own rows (dev/exp_focus.py)
LISTVIEW_SUBITEM_LEFT = 6  # other columns: Windows pads their text more
LISTVIEW_SUBITEM_RIGHT = 8
_NEG1 = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1  # -1 as an unsigned WPARAM
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
ID_RADIO = 13  # radio buttons: theme glyph plus a label we draw (the dark theme has no light radio text)
ID_SLIDER = 14  # trackbars: track whether the mouse is over the thumb (custom draw does not say)
ID_FOCUS = 15  # check boxes, dropdowns, list views, trees: a solid focus ring instead of Windows' dotted one
ID_FOCUSCHILD = 16  # the edit inside an editable combo box: repaint the combo's ring when focus moves
ID_LISTBOX = 17  # plain list boxes and dropdown lists: our selection colour over Windows' bright accent


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
SLIDER_TRACK = (0x8C, 0x8C, 0x8C)  # the groove a slider thumb runs in
SLIDER_THUMB = (0x60, 0xCD, 0xFF)  # the thumb: the same accent blue as a checked check box
SLIDER_THUMB_HOT = (0x00, 0x78, 0xD7)  # hovered: the darker accent (Windows painted it black)
SLIDER_THUMB_PRESSED = (0x00, 0x5F, 0xB8)
SLIDER_THUMB_DISABLED = (0x70, 0x70, 0x70)
MENUBAR_BG = (0x20, 0x20, 0x20)  # menu bar strip (log viewer, Python console): same as the window
MENUBAR_HOT_BG = (0x3A, 0x3A, 0x3A)  # menu bar item under the mouse / open
MENUBAR_TEXT = (0xFF, 0xFF, 0xFF)
MENUBAR_DISABLED_TEXT = (0x9C, 0x9C, 0x9C)
TITLE_SEPARATOR = (0x70, 0x70, 0x70)  # the line where the title bar meets the dialog: a step darker than the layout lines
MENU_BG = (0x2C, 0x2C, 0x2C)  # what Windows paints dark popup menus with (measured); used only for the erase
BTN_FACE = (0x33, 0x33, 0x33)
BTN_HOT = (0x50, 0x50, 0x50)  # hover: clearly lighter than the face
BTN_PRESSED = (0x28, 0x28, 0x28)
BTN_DISABLED_FACE = (0x2A, 0x2A, 0x2A)
BTN_HOT_BORDER = (0xE8, 0xE8, 0xE8)
BTN_DISABLED_BORDER = (0x80, 0x80, 0x80)
BTN_TEXT = (0xFF, 0xFF, 0xFF)
BTN_DISABLED_TEXT = (0x9C, 0x9C, 0x9C)  # readable, a step down from enabled
LIST_BG = (0x2B, 0x2B, 0x2B)  # lists and trees (black with the "black backgrounds" setting)
FIELD_BG = (0x2B, 0x2B, 0x2B)  # text fields and dropdowns: stays
LIST_TEXT = (0xFF, 0xFF, 0xFF)
LIST_DISABLED_TEXT = (0x8A, 0x8A, 0x8A)
LIST_SEL_UNFOCUSED_BG = (0x50, 0x50, 0x50)  # selected row while the list does not have focus
LIST_SEL_BG = (0x1E, 0x5A, 0x8C)  # selected row: between the sidebar's dark blue and Windows' bright accent (white text 7.3:1)
LIST_SEL_TEXT = (0xFF, 0xFF, 0xFF)
RING = 1  # focus rings and the menu outline, in pixels; 2 with the "thicker outlines" setting
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
		inner = _CreateSolidBrush(colorref(FRAME_INNER))
		try:
			for i in range(thick):
				rc = RECT(i, i, w - i, h - i)
				# focused: the ring is RING lines deep; the rest stays the field colour
				_FrameRect(hdc, ctypes.byref(rc), outer if (i == 0 or (focused and i < RING)) else inner)
		finally:
			_DeleteObject(outer)
			_DeleteObject(inner)
	finally:
		_ReleaseDC(hwnd, hdc)


def _drawRing(hdc, rc, rgb, width=None):
	"""A solid frame just inside rc, RING pixels thick (or width)."""
	width = RING if width is None else width
	brush = _CreateSolidBrush(colorref(rgb))
	try:
		for i in range(width):
			r = RECT(rc.left + i, rc.top + i, rc.right - i, rc.bottom - i)
			if r.right <= r.left or r.bottom <= r.top:
				break
			_FrameRect(hdc, ctypes.byref(r), brush)
	finally:
		_DeleteObject(brush)


def _hasFocus(hwnd):
	"""Keyboard focus is on this window or inside it (an editable combo's edit box)."""
	f = _GetFocus()
	return bool(f) and (f == hwnd or bool(_user32.IsChild(hwnd, f)))


def _focusCuesVisible(hwnd):
	"""Whether Windows would show a focus rectangle: it hides them until the keyboard is used.
	We keep the real answer ourselves (see _uiStateMessage), because the control is told to hide its own."""
	state = _trueUI.get(hwnd)
	if state is None:
		state = _SendMessageW(hwnd, WM_QUERYUISTATE, 0, 0)
	return not (state & UISF_HIDEFOCUS)


def _uiStateMessage(hwnd, msg, wParam, lParam):
	"""Shared by the controls whose dotted focus rectangle we replace. Windows' rectangle is
	suppressed by telling the control focus cues are hidden; the real state is kept in _trueUI
	so our ring appears exactly when Windows' rectangle would have. Returns (handled, result)."""
	if msg == WM_UPDATEUISTATE:
		res = _DefSubclassProc(hwnd, msg, wParam, lParam)
		_trueUI[hwnd] = _DefSubclassProc(hwnd, WM_QUERYUISTATE, 0, 0)
		_DefSubclassProc(hwnd, WM_UPDATEUISTATE, (UISF_HIDEFOCUS << 16) | UIS_SET, 0)
		_InvalidateRect(hwnd, None, False)
		return True, res
	if msg == WM_QUERYUISTATE:
		return True, _DefSubclassProc(hwnd, msg, wParam, lParam) | UISF_HIDEFOCUS
	return False, 0


def _className(hwnd):
	buf = ctypes.create_unicode_buffer(64)
	_user32.GetClassNameW(hwnd, buf, 64)
	return buf.value


def _focusRect(hwnd):
	"""Where the focus ring goes: the focused row of a list view or tree, else the whole control."""
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	cls = _className(hwnd)
	if cls == "SysListView32":
		i = _SendMessageW(hwnd, LVM_GETNEXTITEM, _NEG1, LVNI_FOCUSED)
		if i < 0:
			return None
		row = RECT(LVIR_BOUNDS, 0, 0, 0)
		if not _SendMessageW(hwnd, LVM_GETITEMRECT, i, ctypes.addressof(row)):
			return None
		return RECT(max(rc.left, row.left), max(rc.top, row.top), min(rc.right, row.right), min(rc.bottom, row.bottom))
	if cls == "SysTreeView32":
		item = _SendMessageW(hwnd, TVM_GETNEXTITEM, TVGN_CARET, 0)
		if not item:
			return None
		row = RECT()
		ctypes.cast(ctypes.addressof(row), ctypes.POINTER(ctypes.c_size_t))[0] = item  # the item goes in first
		if not _SendMessageW(hwnd, TVM_GETITEMRECT, 0, ctypes.addressof(row)):  # 0: the whole line
			return None
		return RECT(rc.left, max(rc.top, row.top), rc.right, min(rc.bottom, row.bottom))
	return rc


def _listViewItemText(hwnd, item, sub):
	buf = ctypes.create_unicode_buffer(512)
	lvi = LVITEMW()
	lvi.iSubItem = sub
	lvi.pszText = ctypes.cast(buf, wintypes.LPWSTR)
	lvi.cchTextMax = 512
	n = _SendMessageW(hwnd, LVM_GETITEMTEXTW, item, ctypes.addressof(lvi))
	return buf.value if n > 0 else ""


def _listViewColumnFormat(hwnd, col):
	lvc = LVCOLUMNW()
	lvc.mask = LVCF_FMT
	if _SendMessageW(hwnd, LVM_GETCOLUMNW, col, ctypes.addressof(lvc)):
		return lvc.fmt & LVCFMT_JUSTIFYMASK
	return 0


def _drawListViewRow(hwnd, hdc, item):
	"""A selected list view row, in our selection colour: the theme would paint its own highlight
	and ignore any colour we hand it. Returns False (let Windows draw) for lists with icons."""
	if _SendMessageW(hwnd, LVM_GETIMAGELIST, LVSIL_SMALL, 0):
		return False
	bounds = RECT(LVIR_BOUNDS, 0, 0, 0)
	label = RECT(LVIR_LABEL, 0, 0, 0)
	if not _SendMessageW(hwnd, LVM_GETITEMRECT, item, ctypes.addressof(bounds)):
		return False
	if not _SendMessageW(hwnd, LVM_GETITEMRECT, item, ctypes.addressof(label)):
		return False
	ex = _SendMessageW(hwnd, LVM_GETEXTENDEDLISTVIEWSTYLE, 0, 0)
	client = RECT()
	_GetClientRect(hwnd, ctypes.byref(client))
	focused = _hasFocus(hwnd)
	fill = RECT(bounds.left, bounds.top, min(bounds.right, client.right), bounds.bottom)
	if not ex & LVS_EX_FULLROWSELECT:
		fill = RECT(label.left, label.top, label.right, label.bottom)
	brush = _CreateSolidBrush(colorref(LIST_SEL_BG if focused else LIST_SEL_UNFOCUSED_BG))
	_FillRect(hdc, ctypes.byref(fill), brush)
	_DeleteObject(brush)
	if ex & LVS_EX_CHECKBOXES:
		# the state image (check box) sits between the row's left edge and the label
		stateImage = (_SendMessageW(hwnd, LVM_GETITEMSTATE, item, LVIS_STATEIMAGEMASK) & LVIS_STATEIMAGEMASK) >> 12
		if stateImage:
			height = bounds.bottom - bounds.top
			glyph = max(12, min(height - 4, label.left - bounds.left - 2))
			theme = _OpenThemeData(hwnd, "Button")
			if theme:
				size = SIZE()
				if _GetThemePartSize(theme, hdc, BP_CHECKBOX, CBS_UNCHECKEDNORMAL, None, 1, ctypes.byref(size)) == 0 and size.cx:
					glyph = min(size.cx, height)
				x = bounds.left + max(0, (label.left - bounds.left - glyph) // 2)
				y = bounds.top + (height - glyph) // 2
				box = RECT(x, y, x + glyph, y + glyph)
				_DrawThemeBackground(theme, hdc, BP_CHECKBOX, CBS_CHECKEDNORMAL if stateImage == 2 else CBS_UNCHECKEDNORMAL, ctypes.byref(box), None)
				_CloseThemeData(theme)
	font = _SendMessageW(hwnd, WM_GETFONT, 0, 0)
	oldFont = _SelectObject(hdc, font) if font else None
	_SetBkMode(hdc, TRANSPARENT)
	_SetTextColor(hdc, colorref(LIST_SEL_TEXT))
	header = _SendMessageW(hwnd, LVM_GETHEADER, 0, 0)
	columns = _SendMessageW(header, HDM_GETITEMCOUNT, 0, 0) if header else 1
	for col in range(max(1, columns)):
		if col == 0:
			cell = label
		else:
			cell = RECT(LVIR_LABEL, col, 0, 0)
			if not _SendMessageW(hwnd, LVM_GETSUBITEMRECT, item, ctypes.addressof(cell)):
				continue
		text = _listViewItemText(hwnd, item, col)
		if not text:
			continue
		fmt = _listViewColumnFormat(hwnd, col)
		flags = DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS
		flags |= DT_RIGHT if fmt == LVCFMT_RIGHT else DT_CENTER if fmt == LVCFMT_CENTER else DT_LEFT
		if col == 0:
			trc = RECT(cell.left + LISTVIEW_TEXT_X, cell.top, cell.right - LISTVIEW_TEXT_X, cell.bottom)
		else:
			trc = RECT(cell.left + LISTVIEW_SUBITEM_LEFT, cell.top, cell.right - LISTVIEW_SUBITEM_RIGHT, cell.bottom)
		_DrawTextW(hdc, text, -1, ctypes.byref(trc), flags)
	if oldFont:
		_SelectObject(hdc, oldFont)
	return True


def _paintFocusOverlay(hwnd):
	"""After the control has painted itself: our ring where Windows would have put dotted lines."""
	if not _hasFocus(hwnd) or not _focusCuesVisible(hwnd):
		return
	rc = _focusRect(hwnd)
	if rc is None:
		return
	hdc = _GetDC(hwnd)
	if not hdc:
		return
	try:
		_drawRing(hdc, rc, FOCUS)
	finally:
		_ReleaseDC(hwnd, hdc)


def _listBoxText(hwnd, index):
	n = _SendMessageW(hwnd, LB_GETTEXTLEN, index, 0)
	if n < 0:
		return None
	buf = ctypes.create_unicode_buffer(n + 1)
	_SendMessageW(hwnd, LB_GETTEXT, index, ctypes.addressof(buf))
	return buf


def _overdrawListBox(hwnd):
	"""A plain list box (or a dropdown's list) after Windows painted it: selected rows in our
	selection colour rather than the system accent, and our ring on the row with the caret."""
	count = _SendMessageW(hwnd, LB_GETCOUNT, 0, 0)
	if count <= 0:
		return
	style = _GetWindowLongW(hwnd, GWL_STYLE)
	multi = bool(style & (LBS_MULTIPLESEL | LBS_EXTENDEDSEL))
	cur = _SendMessageW(hwnd, LB_GETCURSEL, 0, 0)
	top = max(0, _SendMessageW(hwnd, LB_GETTOPINDEX, 0, 0))
	client = RECT()
	_GetClientRect(hwnd, ctypes.byref(client))
	focused = _hasFocus(hwnd)
	caret = _SendMessageW(hwnd, LB_GETCARETINDEX, 0, 0) if focused and _focusCuesVisible(hwnd) else -1
	hdc = _GetDC(hwnd)
	if not hdc:
		return
	try:
		font = _SendMessageW(hwnd, WM_GETFONT, 0, 0)
		oldFont = _SelectObject(hdc, font) if font else None
		_SetBkMode(hdc, TRANSPARENT)
		_SetTextColor(hdc, colorref(LIST_SEL_TEXT))
		brush = _CreateSolidBrush(colorref(LIST_SEL_BG))
		for i in range(top, count):
			rc = RECT()
			if _SendMessageW(hwnd, LB_GETITEMRECT, i, ctypes.addressof(rc)) == -1 or rc.top >= client.bottom:
				break
			selected = (_SendMessageW(hwnd, LB_GETSEL, i, 0) > 0) if multi else (i == cur)
			if selected:
				_FillRect(hdc, ctypes.byref(rc), brush)
				text = _listBoxText(hwnd, i)
				if text:
					# Where the list box itself puts the text: two pixels in from the left, top-aligned.
					trc = RECT(rc.left + LISTBOX_TEXT_X, rc.top, rc.right, rc.bottom)
					_DrawTextW(hdc, text, -1, ctypes.byref(trc), DT_LEFT | DT_SINGLELINE | DT_NOPREFIX)
			if i == caret:
				_drawRing(hdc, rc, FOCUS)
		_DeleteObject(brush)
		if oldFont:
			_SelectObject(hdc, oldFont)
	finally:
		_ReleaseDC(hwnd, hdc)


LISTBOX_TEXT_X = 2  # measured against Windows' own rows on the bench (dev/exp_focus.py); keep the two in step


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
	focusRing = focused and not (uistate & UISF_HIDEFOCUS)
	if focusRing:
		border = FOCUS  # the border is the ring's first pixel

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
	if focusRing:
		ring = FOCUS if RING >= 2 else None  # thick: a second line inside the border
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


def _drawStaticBox(hwnd, hdc, excludeChildren=True):
	"""Group box: soft one-pixel frame, label breaking the top edge, like Windows draws it.

	excludeChildren is for our own WM_PAINT only. WM_ERASEBKGND also arrives on behalf of a
	transparent child (check box, label) that wants the background painted UNDER it, via
	DrawThemeParentBackground; excluding children there leaves that child unerased.
	"""
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	w, h = rc.right, rc.bottom
	if excludeChildren:
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


def _menuBarRect(hwnd):
	"""The menu bar rectangle in window coordinates, or None if the window has no menu bar."""
	if not _GetMenu(hwnd):
		return None
	mbi = MENUBARINFO()
	mbi.cbSize = ctypes.sizeof(mbi)
	if not _GetMenuBarInfo(hwnd, ctypes.c_long(-3), 0, ctypes.byref(mbi)):  # OBJID_MENU
		return None
	wr = RECT()
	_GetWindowRect(hwnd, ctypes.byref(wr))
	return RECT(mbi.rcBar.left - wr.left, mbi.rcBar.top - wr.top, mbi.rcBar.right - wr.left, mbi.rcBar.bottom - wr.top)


def _drawMenuBar(hwnd, um):
	rc = _menuBarRect(hwnd)
	if rc is None:
		return False
	brush = _CreateSolidBrush(colorref(MENUBAR_BG))
	_FillRect(um.hdc, ctypes.byref(rc), brush)
	_DeleteObject(brush)
	return True


def _drawMenuBarItem(hwnd, dmi):
	dis = dmi.dis
	state = dis.itemState
	mii = MENUITEMINFOW()
	mii.cbSize = ctypes.sizeof(mii)
	mii.fMask = MIIM_STRING
	buf = ctypes.create_unicode_buffer(256)
	mii.dwTypeData = ctypes.cast(buf, wintypes.LPWSTR)
	mii.cch = 255
	_GetMenuItemInfoW(dmi.um.hmenu, dmi.iPosition, True, ctypes.byref(mii))
	hot = bool(state & (ODS_HOTLIGHT | ODS_SELECTED)) and not (state & ODS_INACTIVE)
	bg = _CreateSolidBrush(colorref(MENUBAR_HOT_BG if hot else MENUBAR_BG))
	_FillRect(dis.hDC, ctypes.byref(dis.rcItem), bg)
	_DeleteObject(bg)
	text = MENUBAR_DISABLED_TEXT if state & (ODS_GRAYED | ODS_DISABLED | ODS_INACTIVE) else MENUBAR_TEXT
	_SetBkMode(dis.hDC, TRANSPARENT)
	_SetTextColor(dis.hDC, colorref(text))
	flags = DT_CENTER | DT_VCENTER | DT_SINGLELINE
	if state & ODS_NOACCEL:
		flags |= DT_HIDEPREFIX
	_DrawTextW(dis.hDC, buf, -1, ctypes.byref(dis.rcItem), flags)


def _drawMenuBarBottomLine(hwnd):
	"""Windows paints a light line under the menu bar after WM_NCPAINT; cover it."""
	rc = _menuBarRect(hwnd)
	if rc is None:
		return
	hdc = _GetWindowDC(hwnd)
	if not hdc:
		return
	try:
		line = RECT(rc.left, rc.bottom, rc.right, rc.bottom + 1)
		brush = _CreateSolidBrush(colorref(MENUBAR_BG))
		_FillRect(hdc, ctypes.byref(line), brush)
		_DeleteObject(brush)
	finally:
		_ReleaseDC(hwnd, hdc)


def _boxRectInParent(hwnd):
	"""The box's rectangle in its parent's client coordinates (the dialog itself may move)."""
	parent = _user32.GetParent(hwnd)
	if not parent:
		return None
	r = RECT()
	_GetWindowRect(hwnd, ctypes.byref(r))
	tl = wintypes.POINT(r.left, r.top)
	br = wintypes.POINT(r.right, r.bottom)
	_user32.ScreenToClient(parent, ctypes.byref(tl))
	_user32.ScreenToClient(parent, ctypes.byref(br))
	return (tl.x, tl.y, br.x, br.y)


def _cleanUpAfterBoxMove(hwnd):
	new = _boxRectInParent(hwnd)
	if new is None:
		return
	old = _boxRects.get(hwnd)
	_boxRects[hwnd] = new
	if old is None or old == new:
		return
	# Siblings that overlapped the old spot carry our stale pixels with them when THEY move
	# (Windows copies a moved window's bits instead of repainting), and by now they may
	# already have moved. Invalidations only accumulate until the next paint, so simply
	# repaint the parent and everything in it.
	_RedrawWindow(_user32.GetParent(hwnd), None, None, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN)


def _drawTitleSeparator(hwnd, hdc):
	"""A soft line along the top of a dialog's client area, where the title bar ends."""
	if (_GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION) != WS_CAPTION:
		return
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	t = max(1, round(dpi / 96))
	r = RECT(0, 0, rc.right, min(rc.bottom, t))
	line = _CreateSolidBrush(colorref(TITLE_SEPARATOR))
	_FillRect(hdc, ctypes.byref(r), line)
	_DeleteObject(line)


def _drawSliderChannel(hwnd, hdc, rc):
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	radius = max(2, round(2 * dpi / 96))
	brush = _CreateSolidBrush(colorref(SLIDER_TRACK))
	pen = _CreatePen(PS_SOLID, 1, colorref(SLIDER_TRACK))
	oldBrush = _SelectObject(hdc, brush)
	oldPen = _SelectObject(hdc, pen)
	_RoundRect(hdc, rc.left, rc.top, rc.right, rc.bottom, radius, radius)
	_SelectObject(hdc, oldPen)
	_SelectObject(hdc, oldBrush)
	_DeleteObject(pen)
	_DeleteObject(brush)


TBS_VERT = 0x0002
TBS_TOP = 0x0004  # (also TBS_LEFT for vertical bars)
TBS_BOTH = 0x0008


def _drawSliderThumb(hwnd, hdc, rc, state):
	"""The thumb in Windows' own pointer shape (a block tapering to a point on the tick side),
	in Windows' blue; accent blue when hovered (Windows drew it black), grey when disabled."""
	if not _IsWindowEnabled(hwnd) or state & CDIS_DISABLED:
		colour = SLIDER_THUMB_DISABLED
	elif state & CDIS_SELECTED:
		colour = SLIDER_THUMB_PRESSED
	elif state & CDIS_HOT or _sliderHot.get(hwnd):
		colour = SLIDER_THUMB_HOT
	else:
		colour = SLIDER_THUMB
	bg = _CreateSolidBrush(colorref(PARENT_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)  # clear what the theme may have painted underneath
	_DeleteObject(bg)
	style = _GetWindowLongW(hwnd, GWL_STYLE)
	l, t, r, b = rc.left, rc.top, rc.right - 1, rc.bottom - 1
	w, h = r - l, b - t
	if style & TBS_BOTH:
		pts = [(l, t), (r, t), (r, b), (l, b)]
	elif style & TBS_VERT:
		tip = h // 2
		if style & TBS_TOP:  # point on the left
			pts = [(l + tip, t), (r, t), (r, b), (l + tip, b), (l, t + h // 2)]
		else:  # point on the right
			pts = [(l, t), (r - tip, t), (r, t + h // 2), (r - tip, b), (l, b)]
	else:
		tip = w // 2
		if style & TBS_TOP:  # point at the top
			pts = [(l + w // 2, t), (r, t + tip), (r, b), (l, b), (l, t + tip)]
		else:  # point at the bottom (the usual)
			pts = [(l, t), (r, t), (r, b - tip), (l + w // 2, b), (l, b - tip)]
	arr = (wintypes.POINT * len(pts))(*[wintypes.POINT(x, y) for x, y in pts])
	brush = _CreateSolidBrush(colorref(colour))
	pen = _CreatePen(PS_SOLID, 1, colorref(colour))
	oldBrush = _SelectObject(hdc, brush)
	oldPen = _SelectObject(hdc, pen)
	_Polygon(hdc, arr, len(pts))
	_SelectObject(hdc, oldPen)
	_SelectObject(hdc, oldBrush)
	_DeleteObject(pen)
	_DeleteObject(brush)


def _paintCheckItem(dis):
	"""Draw one wx.CheckListBox row: background, check box glyph, label."""
	win = _checkLists.get(dis.hwndItem)
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
		return False  # wrapper gone: let Windows draw rather than draw wrong

	if selected and hasFocus:
		bg = colorref(LIST_SEL_BG)
		fg = colorref(LIST_SEL_TEXT)
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
		_drawRing(hdc, rc, FOCUS)
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


def _paintRadio(hwnd):
	_paintWith(hwnd, _drawRadio)


def _drawRadio(hwnd, hdc):
	"""A radio button: the theme's own glyph (dark style, accent when checked) and the
	label in our text colour. Windows' dark theme draws radio labels black."""
	rc = RECT()
	_GetClientRect(hwnd, ctypes.byref(rc))
	w, h = rc.right, rc.bottom
	bg = _CreateSolidBrush(colorref(PARENT_BG))
	_FillRect(hdc, ctypes.byref(rc), bg)
	_DeleteObject(bg)
	enabled = bool(_IsWindowEnabled(hwnd))
	checked = bool(_SendMessageW(hwnd, BM_GETCHECK, 0, 0) & BST_CHECKED)
	state = _SendMessageW(hwnd, BM_GETSTATE, 0, 0)
	hot = bool(state & BST_HOT)
	pushed = bool(state & BST_PUSHED)
	focused = bool(state & BST_FOCUS)
	uistate = _SendMessageW(hwnd, WM_QUERYUISTATE, 0, 0)
	dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
	glyph = round(13 * dpi / 96)
	theme = _OpenThemeData(hwnd, "Button")
	if theme:
		size = SIZE()
		if _GetThemePartSize(theme, hdc, BP_RADIOBUTTON, 1, None, 1, ctypes.byref(size)) == 0 and size.cx:
			glyph = min(size.cx, h)
	top = max(0, (h - glyph) // 2)
	box = RECT(0, top, glyph, top + glyph)
	if theme:
		# RBS_*: 1 unchecked normal, 2 hot, 3 pressed, 4 disabled; +4 for checked
		part = 1
		if not enabled:
			part = 4
		elif pushed:
			part = 3
		elif hot:
			part = 2
		if checked:
			part += 4
		_DrawThemeBackground(theme, hdc, BP_RADIOBUTTON, part, ctypes.byref(box), None)
		_CloseThemeData(theme)
	text = _windowText(hwnd)
	if text:
		font = _SendMessageW(hwnd, WM_GETFONT, 0, 0)
		oldFont = _SelectObject(hdc, font) if font else None
		_SetBkMode(hdc, TRANSPARENT)
		_SetTextColor(hdc, colorref(RADIO_TEXT if enabled else RADIO_DISABLED_TEXT))
		flags = DT_LEFT | DT_VCENTER | DT_SINGLELINE
		if uistate & UISF_HIDEACCEL:
			flags |= DT_HIDEPREFIX
		gap = round(3 * dpi / 96)
		trc = RECT(glyph + gap, 0, w, h)
		_DrawTextW(hdc, text, -1, ctypes.byref(trc), flags)
		if focused and not (uistate & UISF_HIDEFOCUS):
			calc = RECT(0, 0, 0, 0)
			_DrawTextW(hdc, text, -1, ctypes.byref(calc), flags | DT_CALCRECT)
			fr = RECT(glyph + gap - 1, max(0, (h - calc.bottom) // 2 - 1), min(w, glyph + gap + calc.right + 2), min(h, (h + calc.bottom) // 2 + 1))
			_drawRing(hdc, fr, FOCUS)
		if oldFont:
			_SelectObject(hdc, oldFont)


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
			pen = _CreatePen(PS_SOLID, RING, colorref(FOCUS))
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
			_Polygon(hdc, pts, 3)
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
			_sliders.discard(hwnd)
			_listViews.discard(hwnd)
			_sliderHot.pop(hwnd, None)
			_boxRects.pop(hwnd, None)
			_framePending.discard(hwnd)
			_tabHot.pop(hwnd, None)
			_trueUI.pop(hwnd, None)
			return _DefSubclassProc(hwnd, msg, wParam, lParam)
		if idSubclass in (ID_FOCUS, ID_SLIDER, ID_LISTBOX):
			handled, res = _uiStateMessage(hwnd, msg, wParam, lParam)
			if handled:
				return res
		if idSubclass == ID_OWNERDRAW:
			if msg == WM_DRAWITEM:
				dis = DRAWITEMSTRUCT.from_address(lParam)
				if dis.CtlType == ODT_LISTBOX and dis.hwndItem in _checkLists and _paintCheckItem(dis):
					return 1
			elif msg == WM_NOTIFY:
				hdr = NMHDR.from_address(lParam)
				if hdr.code == NM_CUSTOMDRAW and hdr.hwndFrom in _listViews:
					# Selected rows of a list view in our selection colour. The theme paints its
					# own highlight and ignores any colour handed back through custom draw, so
					# selected rows are painted here in full and Windows skips them.
					cd = NMLVCUSTOMDRAW.from_address(lParam)
					if cd.nmcd.dwDrawStage == CDDS_PREPAINT:
						return _DefSubclassProc(hwnd, msg, wParam, lParam) | CDRF_NOTIFYITEMDRAW
					if cd.nmcd.dwDrawStage == CDDS_ITEMPREPAINT:
						# uItemState says "selected" for every row under the Explorer theme; ask the list.
						sel = _SendMessageW(hdr.hwndFrom, LVM_GETITEMSTATE, cd.nmcd.dwItemSpec, LVIS_SELECTED) & LVIS_SELECTED
						if sel and _drawListViewRow(hdr.hwndFrom, cd.nmcd.hdc, cd.nmcd.dwItemSpec):
							return CDRF_SKIPDEFAULT
					return _DefSubclassProc(hwnd, msg, wParam, lParam)
				if hdr.code == NM_CUSTOMDRAW and hdr.hwndFrom in _sliders:
					cd = NMCUSTOMDRAW.from_address(lParam)
					if cd.dwDrawStage == CDDS_PREPAINT:
						return CDRF_NOTIFYITEMDRAW
					if cd.dwDrawStage == CDDS_ITEMPREPAINT and cd.dwItemSpec == TBCD_CHANNEL:
						_drawSliderChannel(hdr.hwndFrom, cd.hdc, cd.rc)
						return CDRF_SKIPDEFAULT
					if cd.dwDrawStage == CDDS_ITEMPREPAINT and cd.dwItemSpec == TBCD_THUMB:
						_drawSliderThumb(hdr.hwndFrom, cd.hdc, cd.rc, cd.uItemState)
						return CDRF_SKIPDEFAULT
					return CDRF_DODEFAULT
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
			# Text replacement and font changes both reset a rich edit's default character
			# colour to "automatic" (black); put ours back after each.
			if msg in (WM_SETTEXT, EM_SETTEXTEX, EM_REPLACESEL, WM_SETFONT, WM_THEMECHANGED):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				applyRichColours(hwnd, LIST_TEXT, FIELD_BG)
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
				_drawStaticBox(hwnd, wParam, excludeChildren=False)
				return 1
			if msg in (WM_ENABLE, WM_UPDATEUISTATE):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_InvalidateRect(hwnd, None, False)
				return res
			if msg == WM_WINDOWPOSCHANGED:
				# Dialogs can be visible while still being laid out (NVDA's Welcome dialog is),
				# so the box gets painted at a provisional spot and then moved. Windows leaves
				# our old frame and label behind on siblings (labels don't repaint); clean up.
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_cleanUpAfterBoxMove(hwnd)
				return res
		elif idSubclass == ID_FOCUS:
			if msg == WM_PAINT:
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_paintFocusOverlay(hwnd)
				return res
			if msg in (WM_SETFOCUS, WM_KILLFOCUS):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_InvalidateRect(hwnd, None, False)
				return res
		elif idSubclass == ID_FOCUSCHILD:
			if msg in (WM_SETFOCUS, WM_KILLFOCUS):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				parent = _user32.GetParent(hwnd)
				if parent:
					_InvalidateRect(parent, None, False)
				return res
		elif idSubclass == ID_LISTBOX:
			if msg == WM_PAINT or msg in LISTBOX_REDRAW_MESSAGES:
				# A list box draws a selection change straight away (mouse over a dropdown's
				# list, arrow keys, LB_SETCURSEL), without a WM_PAINT: paint over after each.
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_overdrawListBox(hwnd)
				return res
			if msg in (WM_SETFOCUS, WM_KILLFOCUS):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_InvalidateRect(hwnd, None, False)
				return res
		elif idSubclass == ID_SLIDER:
			if msg == WM_PAINT:
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_paintFocusOverlay(hwnd)
				return res
			if msg in (WM_SETFOCUS, WM_KILLFOCUS):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_InvalidateRect(hwnd, None, False)
				return res
			if msg == WM_MOUSEMOVE:
				rc = RECT()
				_SendMessageW(hwnd, TBM_GETTHUMBRECT, 0, ctypes.addressof(rc))
				x, y = lParam & 0xFFFF, (lParam >> 16) & 0xFFFF
				hot = rc.left <= x < rc.right and rc.top <= y < rc.bottom
				if _sliderHot.get(hwnd, False) != hot:
					_sliderHot[hwnd] = hot
					_InvalidateRect(hwnd, None, False)
				tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE, hwnd, 0)
				_user32.TrackMouseEvent(ctypes.byref(tme))
			elif msg == WM_MOUSELEAVE:
				if _sliderHot.pop(hwnd, None):
					_InvalidateRect(hwnd, None, False)
		elif idSubclass == ID_RADIO:
			if msg == WM_PAINT:
				_paintRadio(hwnd)
				return 0
			if msg == WM_ERASEBKGND:
				_drawRadio(hwnd, wParam)
				return 1
			if msg in (WM_ENABLE, WM_UPDATEUISTATE, WM_SETFOCUS, WM_KILLFOCUS):
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
			if msg == WM_UAHDRAWMENU:
				if _drawMenuBar(hwnd, UAHMENU.from_address(lParam)):
					return 0
			elif msg == WM_UAHDRAWMENUITEM:
				if _GetMenu(hwnd):
					_drawMenuBarItem(hwnd, UAHDRAWMENUITEM.from_address(lParam))
					return 0
			elif msg in (WM_NCPAINT, WM_NCACTIVATE):
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_drawMenuBarBottomLine(hwnd)
				return res
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
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				_RedrawWindow(hwnd, None, None, RDW_UPDATENOW | RDW_ALLCHILDREN)
				# wx lays many dialogs out only AFTER showing them (every control still sits at
				# the top-left corner at this point), and Windows moves controls by copying
				# their pixels, not repainting. So once the show call has returned and layout
				# has run, repaint everything at its final place. Posted messages are handled
				# before any WM_PAINT, so this still lands ahead of NVDA's announcing.
				_user32.PostMessageW(hwnd, WM_DARK_RELAYOUT, 0, 0)
				return res
			if msg == WM_DARK_RELAYOUT:
				_RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW)
				return 0
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
			if msg == WM_UAHDRAWMENUITEM:
				# Windows draws each item of a dark popup menu through this message, the
				# highlighted one included (arrow keys and mouse hover alike). Outline it.
				res = _DefSubclassProc(hwnd, msg, wParam, lParam)
				dmi = UAHDRAWMENUITEM.from_address(lParam)
				if dmi.dis.itemState & (ODS_SELECTED | ODS_HOTLIGHT) and MENU_OUTLINE:
					# Windows' own highlight sits MENU_ITEM_MARGIN (3 DIP) in from the item's
					# sides; draw on exactly that rectangle, so what Windows repaints when the
					# highlight moves on covers our outline too (a wider one left its ends behind).
					dpi = _GetDpiForWindow(hwnd) if _GetDpiForWindow else 96
					margin = round(MENU_ITEM_MARGIN * dpi / 96)
					rc = dmi.dis.rcItem
					_drawRing(dmi.dis.hDC, RECT(rc.left + margin, rc.top, rc.right - margin, rc.bottom), FOCUS)
				return res
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
		log.exception("darkMode: paint hook failed")
	return _DefSubclassProc(hwnd, msg, wParam, lParam)


_sliders = set()  # trackbar hwnds whose channel we draw (their parent carries ID_OWNERDRAW)
_listViews = set()  # list view hwnds whose selected rows we colour (their parent carries ID_OWNERDRAW)
_sliderHot = {}  # trackbar hwnd -> mouse is over its thumb
_boxRects = {}  # group box hwnd -> last known window rect (screen coords), to clean up after a move
_eraseColours = {}  # hwnd -> rgb laid down on WM_ERASEBKGND (ID_ERASE)
_frameColours = {}  # hwnd -> frame colour when not focused (ID_FRAME); default BORDER
_trueUI = {}  # hwnd -> the UI state Windows really has for it (focus cues shown or hidden); see _uiStateMessage
MENU_OUTLINE = True  # outline the highlighted popup menu item
MENU_ITEM_MARGIN = 3  # DIP between a popup menu item's rect and Windows' highlight (measured: 7 px at 225%)
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
		applyRichColours(hwnd, LIST_TEXT, FIELD_BG)
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
		if hwnd not in _boxRects and _IsWindow(hwnd):
			rc = _boxRectInParent(hwnd)
			if rc:
				_boxRects[hwnd] = rc
	else:
		_detach(hwnd, ID_STATICBOX)
		_boxRects.pop(hwnd, None)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def applyRadio(hwnd, dark: bool):
	if dark:
		_attach(hwnd, ID_RADIO)
	else:
		_detach(hwnd, ID_RADIO)
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


def _hideFocusCues(hwnd, idSubclass, dark: bool):
	"""Attach/detach a subclass that replaces Windows' dotted focus rectangle with our ring.
	The control is told its focus cues are hidden (so Windows draws none) while the real
	state is remembered; on the way out the real state is put back."""
	if dark:
		if hwnd in _trueUI:
			return
		_trueUI[hwnd] = _SendMessageW(hwnd, WM_QUERYUISTATE, 0, 0)  # the truth, before we intercept
		_SendMessageW(hwnd, WM_UPDATEUISTATE, (UISF_HIDEFOCUS << 16) | UIS_SET, 0)
		_attach(hwnd, idSubclass)
	else:
		_detach(hwnd, idSubclass)
		state = _trueUI.pop(hwnd, None)
		if state is not None and _IsWindow(hwnd):
			action = UIS_SET if state & UISF_HIDEFOCUS else UIS_CLEAR
			_SendMessageW(hwnd, WM_UPDATEUISTATE, (UISF_HIDEFOCUS << 16) | action, 0)


def applyFocusRing(hwnd, dark: bool):
	"""Our focus ring on a check box, dropdown, list view or tree (Windows' dotted one is hidden)."""
	_hideFocusCues(hwnd, ID_FOCUS, dark)
	if _className(hwnd) == "ComboBox":
		child = _GetWindow(hwnd, GW_CHILD)
		while child:
			if _className(child) == "Edit":
				if dark:
					_attach(child, ID_FOCUSCHILD)
				else:
					_detach(child, ID_FOCUSCHILD)
			child = _GetWindow(child, GW_HWNDNEXT)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, False)


def applyListBox(hwnd, dark: bool):
	"""Our selection colour and focus ring on a plain list box (or a dropdown's list)."""
	_hideFocusCues(hwnd, ID_LISTBOX, dark)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, False)


def setRingWidth(pixels: int):
	global RING
	RING = 2 if pixels >= 2 else 1


def registerSlider(hwnd, hwndParent, dark: bool):
	"""Grey groove for a wx.Slider (custom draw arrives at the parent as WM_NOTIFY)."""
	if dark:
		_sliders.add(hwnd)
		_attach(hwndParent, ID_OWNERDRAW)
		_hideFocusCues(hwnd, ID_SLIDER, True)
	else:
		_sliders.discard(hwnd)
		_sliderHot.pop(hwnd, None)
		_hideFocusCues(hwnd, ID_SLIDER, False)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def registerListView(hwnd, hwndParent, dark: bool):
	"""Our selection colour on a list view's selected rows (custom draw arrives at the parent)."""
	if dark:
		_listViews.add(hwnd)
		_attach(hwndParent, ID_OWNERDRAW)
	else:
		_listViews.discard(hwnd)
	if _IsWindow(hwnd):
		_InvalidateRect(hwnd, None, True)


def registerCheckList(hwnd, hwndParent, win, dark: bool):
	"""Owner-draw the rows of a wx.CheckListBox (its parent receives WM_DRAWITEM)."""
	if dark:
		# A strong reference: a weak one died whenever nothing else in Python held the
		# control (NVDA's own panels often do not), and the rows fell back to black.
		# WM_NCDESTROY on the list drops the entry.
		_checkLists[hwnd] = win
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


TOOLTIP_CLASS = "tooltips_class32"
COMBO_LIST_CLASS = "ComboLBox"
_SetWindowTheme = ctypes.windll.uxtheme.SetWindowTheme
_SetWindowTheme.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)


def themeTooltip(hwnd, dark: bool):
	"""Tooltips (list view truncation tips, control tips) follow the dark theme like Explorer's."""
	if hwnd and _IsWindow(hwnd):
		_SetWindowTheme(hwnd, "DarkMode_Explorer" if dark else None, None)


def _cbt(code, wParam, lParam):
	try:
		if code == HCBT_CREATEWND:
			buf = ctypes.create_unicode_buffer(64)
			_user32.GetClassNameW(wParam, buf, 64)
			if buf.value == MENU_POPUP_CLASS:
				_attach(wParam, ID_MENUPOPUP)
			elif buf.value == TOOLTIP_CLASS:
				themeTooltip(wParam, True)
			elif buf.value == COMBO_LIST_CLASS:
				_attach(wParam, ID_LISTBOX)  # the list a combo box drops down
	except Exception:
		log.exception("darkMode: menu hook failed")
	return _CallNextHookEx(_menuHook, code, wParam, lParam)


_cbtProc = _CBTPROC(_cbt)  # must stay alive while the hook is installed


def installMenuHook():
	"""Start giving popup menus a dark first erase. Call from the thread that shows the menus."""
	global _menuHook
	if _menuHook:
		return
	_menuHook = _SetWindowsHookExW(WH_CBT, _cbtProc, None, ctypes.windll.kernel32.GetCurrentThreadId())
	if not _menuHook:
		log.warning("darkMode: could not install the popup menu hook (error %d)" % ctypes.get_last_error())


def removeMenuHook():
	global _menuHook
	if _menuHook:
		_UnhookWindowsHookEx(_menuHook)
		_menuHook = None


def detachAll():
	removeMenuHook()
	_eraseColours.clear()
	_frameColours.clear()
	_sliders.clear()
	_listViews.clear()
	_sliderHot.clear()
	_boxRects.clear()
	_checkLists.clear()
	_tabHot.clear()
	for hwnd, ids in list(_subclassed.items()):
		for i in list(ids):
			_detach(hwnd, i)
		if _IsWindow(hwnd):
			_RedrawWindow(hwnd, None, None, RDW_FRAME | RDW_INVALIDATE | RDW_ERASE)
	# Only now (nothing of ours intercepts the message any more): put Windows' own focus
	# cues back on the controls where we hid them.
	for hwnd in list(_trueUI):
		state = _trueUI.pop(hwnd, None)
		if state is not None and _IsWindow(hwnd):
			action = UIS_SET if state & UISF_HIDEFOCUS else UIS_CLEAR
			_SendMessageW(hwnd, WM_UPDATEUISTATE, (UISF_HIDEFOCUS << 16) | action, 0)
