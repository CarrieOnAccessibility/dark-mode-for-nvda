# Dark Mode: an NVDA add-on. Copyright (C) 2026 Carrie on Accessibility.
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, version 2.
# See the LICENSE file for details.
#
# Dark help files. NVDA's documentation (User Guide, Commands Quick Reference, What's New)
# and every add-on's help are HTML files that NVDA hands to the web browser, so nothing in
# theming.py can reach them. Instead, while dark mode is on, the function NVDA uses to find
# a help file is wrapped: it copies that file's folder into a per-version cache under TEMP,
# adds a dark stylesheet to each HTML file in the copy, and returns the copy's path. The
# original files are never touched, links between the copied pages keep working (the whole
# folder comes along), and with dark mode off NVDA gets its own files back.

import os
import re
import shutil
import tempfile

from logHandler import log

try:
	import documentationUtils
except ImportError:  # very old NVDA, or the test bench
	documentationUtils = None
try:
	import addonHandler
except ImportError:
	addonHandler = None

_isActive = lambda: False  # replaced by the plugin: True while dark mode is on
_bgGetter = lambda: None  # replaced by the plugin: the dialog background (a wx.Colour); black is a setting
_originals = {}

DARK_CSS = """/* Added by the Dark Mode add-on. The original page is untouched; this is a copy. */
:root { color-scheme: dark; }
body { background: %(bg)s; color: #f5f5f5; }
h1 { color: #ffffff; background-color: #472f5f; }
h2, h3, h4, h5, h6 { color: #d3b5f2; }
a { color: #8fd0ff; }
a:visited { color: #c9a2ea; }
a:focus-visible, button:focus-visible { outline: 3px solid #60cdff; outline-offset: 2px; }
strong { color: #ffffff; }
hr { border-color: #8c8c8c; }
/* Tables: the Commands Quick Reference is nothing but tables. */
table, td, th { border: 1px solid #a0a0a0; }
th { color: #ffffff; background-color: #472f5f; }
td { background-color: %(td)s; }
tr:nth-child(even) td { background-color: %(tdEven)s; }
/* Code */
/* File names, settings, command lines: white on NVDA's dark purple. */
code, pre { background: #472f5f; border-bottom: 1px solid #6b4a8a; color: #ffffff; border-radius: 3px; }
pre { border-left: 3px solid #a785d6; }
/* Keyboard shortcuts: NVDA writes them as <code> in prose and as plain text in the key columns of
   its tables; the copy marks both as <kbd>. A lighter tint of NVDA purple, visible on dark cells. */
kbd { background: #2e2838; color: #ffffff; border: 1px solid #a785d6; border-radius: 4px; padding: 1px 6px; white-space: nowrap; font-family: inherit; font-size: 0.95em; }
kbd code { background: none; border: none; padding: 0; }
blockquote { border-left: 3px solid #8c8c8c; color: #d1d5db; }
/* NVDA's stylesheet sets no colour on these; the browser default would be dark on dark. */
dl > dt, dl > dd { color: #f5f5f5; }
img { max-width: 100%%; }
"""
CSS_NAME = "darkMode-docs.css"


def _pageBackground():
	"""The help page's background: the dialog background, so black follows the setting."""
	try:
		c = _bgGetter()
		if c is not None:
			return "#%02x%02x%02x" % (c.Red(), c.Green(), c.Blue())
	except Exception:
		pass
	return "#202020"


def darkCss():
	bg = _pageBackground()
	black = bg == "#000000"
	# table cells a step lighter than the page, so a table still reads as a table
	return DARK_CSS % {"bg": bg, "td": "#141414" if black else "#262626", "tdEven": "#1c1c1c" if black else "#2b2b2b"}
LINK_TAG = '<link rel="stylesheet" href="%s">' % CSS_NAME


def _cacheRoot():
	return os.path.join(tempfile.gettempdir(), "darkMode-docs")


def _cacheDirFor(srcDir):
	"""A cache folder unique to this source folder (path + newest file time) and this stylesheet."""
	try:
		newest = max(os.path.getmtime(os.path.join(srcDir, n)) for n in os.listdir(srcDir))
	except (OSError, ValueError):
		newest = 0
	import hashlib

	key = hashlib.sha1(("%s|%d|%s" % (os.path.normcase(srcDir), int(newest), darkCss())).encode("utf-8")).hexdigest()[:12]
	return os.path.join(_cacheRoot(), key)


def _dropStaleCopies(srcDir, keep):
	"""Remove earlier copies of the same folder (older NVDA build, older stylesheet)."""
	root = _cacheRoot()
	try:
		names = os.listdir(root)
	except OSError:
		return
	for name in names:
		d = os.path.join(root, name)
		if d == keep or not os.path.isdir(d):
			continue
		try:
			with open(os.path.join(d, ".complete"), "r", encoding="utf-8", errors="replace") as f:
				same = f.read().strip() == srcDir
		except OSError:
			continue
		if same:  # after the marker is closed: Windows will not delete an open file
			shutil.rmtree(d, ignore_errors=True)


# Column headings whose cells hold a key or gesture, in NVDA's tables.
KEY_COLUMNS = {"key", "keys", "keystroke", "shortcut", "desktop key", "laptop key", "touch", "brltty command", "gesture"}
NOT_A_KEY = {"", "none", "n/a", "-", "–", "—"}
# One key name as NVDA writes them (the identifiers from Input Gestures), case-insensitive.
_KEY_TOKEN = re.compile(
	r"^(?:nvda|control|ctrl|shift|alt|windows|win|applications|enter|return|tab|escape|esc|space|spacebar|backspace"
	r"|delete|del|insert|ins|home|end|pageup|pagedown|uparrow|downarrow|leftarrow|rightarrow|capslock|numlock"
	r"|scrolllock|printscreen|pause|break|plus|minus|equals|f\d{1,2}|numpad\w*|dot[1-8]|dots?|routing|doublerouting"
	r"|joystick\d\w*|[a-z]{1,2}\d{1,2}|volume\w+|browser\w+|media\w+|launch\w+|.)$",
	re.I,
)


def _looksLikeKey(text):
	t = re.sub(r"<[^>]+>", "", text).strip()
	if not t or len(t) > 60:
		return False
	return all(_KEY_TOKEN.match(part.strip()) for part in t.split("+"))


def _markKeys(text):
	"""Wrap keyboard shortcuts in <kbd>: every cell of a key column, and <code> in prose whose text is a key combo."""

	def fixTable(m):
		table = m.group(0)
		heads = [re.sub(r"<[^>]+>", "", h).strip().lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
		cols = {i for i, h in enumerate(heads) if h in KEY_COLUMNS}
		if not cols:
			return table

		def fixRow(rm):
			row = rm.group(0)
			n = [-1]

			def fixCell(cm):
				n[0] += 1
				inner = cm.group(2)
				if n[0] not in cols or "<kbd" in inner:
					return cm.group(0)
				plain = re.sub(r"<[^>]+>", "", inner).strip().lower()
				if plain in NOT_A_KEY or re.search(r"\betc\b", plain):
					return cm.group(0)
				if "<code" in inner:
					# "<code>NVDA+q</code>, then <code>enter</code>": each key its own kbd, words left alone
					new = re.sub(r"<code>([^<]*)</code>", r"<kbd>\1</kbd>", inner)
				else:
					# plain text: "t1, etouch1" -> one kbd per key
					# "topRouting20 (last cell on display)": the note in brackets stays outside the key
					new = ", ".join(
						re.sub(r"^(.*?)(\s*\(.*\))?$", r"<kbd>\1</kbd>\2", part.strip(), flags=re.S)
						for part in inner.split(",")
						if part.strip()
					)
				return "<td%s>%s</td>" % (cm.group(1) or "", new)

			return re.sub(r"<td(\s[^>]*)?>(.*?)</td>", fixCell, row, flags=re.S)

		return re.sub(r"<tr[^>]*>.*?</tr>", fixRow, table, flags=re.S)

	text = re.sub(r"<table[^>]*>.*?</table>", fixTable, text, flags=re.S)
	# prose: <code>NVDA+n</code>, <code>enter</code>; not <code>nvda.ini</code>
	return re.sub(r"<code>([^<]*)</code>", lambda m: "<kbd>%s</kbd>" % m.group(1) if _looksLikeKey(m.group(1)) else m.group(0), text)


def _darkenHtml(text):
	if CSS_NAME in text:
		return text
	try:
		text = _markKeys(text)
	except Exception:
		log.exception("darkMode: could not mark keyboard shortcuts in a help page; leaving them as they are")
	# after the page's own stylesheets, so ours wins; else before </head>; else at the top
	m = list(re.finditer(r"<link[^>]+rel=[\"']stylesheet[\"'][^>]*>", text, re.I))
	if m:
		i = m[-1].end()
		return text[:i] + "\n" + LINK_TAG + text[i:]
	i = text.lower().find("</head>")
	if i >= 0:
		return text[:i] + LINK_TAG + "\n" + text[i:]
	return LINK_TAG + "\n" + text


def darkCopy(path):
	"""The dark copy of an HTML help file, building or refreshing the cached folder as needed."""
	if not path or not path.lower().endswith((".html", ".htm")) or not os.path.isfile(path):
		return path
	srcDir = os.path.dirname(path)
	dest = _cacheDirFor(srcDir)
	marker = os.path.join(dest, ".complete")
	if not os.path.isfile(marker):
		if os.path.isdir(dest):
			shutil.rmtree(dest, ignore_errors=True)
		shutil.copytree(srcDir, dest)
		for name in os.listdir(dest):
			if name.lower().endswith((".html", ".htm")):
				p = os.path.join(dest, name)
				with open(p, "r", encoding="utf-8", errors="replace") as f:
					text = f.read()
				with open(p, "w", encoding="utf-8") as f:
					f.write(_darkenHtml(text))
		with open(os.path.join(dest, CSS_NAME), "w", encoding="utf-8") as f:
			f.write(darkCss())
		with open(marker, "w", encoding="utf-8") as f:
			f.write(srcDir)
		_dropStaleCopies(srcDir, dest)
	return os.path.join(dest, os.path.basename(path))


def _wrap(module, name, transform):
	original = getattr(module, name, None)
	if original is None or (module, name) in _originals:
		return

	import functools

	@functools.wraps(original)  # carries the function's own attributes too: NVDA keeps
	def wrapped(*args, **kwargs):  # getDocFilePath.rootPath on the function object itself
		result = original(*args, **kwargs)
		if _isActive():
			try:
				return transform(result)
			except Exception:
				log.exception("darkMode: could not prepare a dark help file; opening the original")
		return result

	_originals[(module, name)] = original
	setattr(module, name, wrapped)


def install(isActive, bgGetter=None):
	"""Start handing NVDA dark copies of help files while isActive() is True."""
	global _isActive, _bgGetter
	_isActive = isActive
	if bgGetter is not None:
		_bgGetter = bgGetter
	if documentationUtils is not None:
		original = getattr(documentationUtils, "getDocFilePath", None)
		_wrap(documentationUtils, "getDocFilePath", darkCopy)
		# Modules that imported the function by name (from documentationUtils import
		# getDocFilePath) hold their own reference; give them the wrapped one too.
		import sys

		wrapped = getattr(documentationUtils, "getDocFilePath", None)
		if original is not None and wrapped is not original:
			for mod in list(sys.modules.values()):
				try:
					if mod is not documentationUtils and getattr(mod, "getDocFilePath", None) is original:
						_originals[(mod, "getDocFilePath")] = original
						setattr(mod, "getDocFilePath", wrapped)
				except Exception:
					continue
	if addonHandler is not None:
		# The Add-on Store's "Add-on help" reads the add-on's own doc path.
		for clsName in ("Addon", "AddonBundle", "AddonBase"):
			cls = getattr(addonHandler, clsName, None)
			if cls is not None and "getDocFilePath" in cls.__dict__:
				_wrap(cls, "getDocFilePath", darkCopy)


# --- Browseable messages -----------------------------------------------------------
# NVDA menu > Help > License (and other "browseable" messages) are HTML shown by an
# MSHTML dialog from NVDA's own message.html, which is white. The message text is
# handed to the page unstyled; while dark mode is on, a style block goes along with it.
MESSAGE_CSS = (
	"<style>html,body{background:%(bg)s !important;color:#f5f5f5 !important;"
	# MSHTML honours these old scrollbar colour properties
	"scrollbar-base-color:#2b2b2b;scrollbar-face-color:#5a5a5a;scrollbar-track-color:#202020;scrollbar-arrow-color:#c8c8c8;"
	"scrollbar-shadow-color:#2b2b2b;scrollbar-highlight-color:#2b2b2b;scrollbar-3dlight-color:#202020;scrollbar-darkshadow-color:#202020}"
	"a{color:#8fd0ff}a:visited{color:#c9a2ea}"
	"button{background:#333333;color:#ffffff;border:1px solid #c8c8c8;padding:2px 12px}"
	"h1,h2,h3{color:#d3b5f2}</style>"
)


def _bgHex(bgGetter):
	try:
		c = bgGetter()
		return "#%02x%02x%02x" % (c.Red(), c.Green(), c.Blue())
	except Exception:
		return "#202020"


def _darkBrowseableMessage(original, isActive, bgGetter, windowHook):
	import functools
	import html as _html

	defaults = original.__defaults__ or ()
	names = original.__code__.co_varnames[: original.__code__.co_argcount]
	defaultSanitizer = dict(zip(names[len(names) - len(defaults):], defaults)).get("sanitizeHtmlFunc")

	@functools.wraps(original)
	def wrapped(message, title=None, isHtml=False, closeButton=False, copyButton=False, sanitizeHtmlFunc=None, *args, **kwargs):
		if not isActive():
			extra = {} if sanitizeHtmlFunc is None else {"sanitizeHtmlFunc": sanitizeHtmlFunc}
			return original(message, title, isHtml, closeButton, copyButton, *args, **extra, **kwargs)
		css = MESSAGE_CSS % {"bg": _bgHex(bgGetter)}
		if not isHtml:
			# what NVDA itself does with plain text, then our style after it
			message = "<pre>%s</pre>" % _html.escape(str(message))
			sanitize = lambda h: h + css
		else:
			inner = sanitizeHtmlFunc or defaultSanitizer or (lambda h: h)
			sanitize = lambda h: inner(h) + css  # the caller's HTML is still cleaned; the style is ours
		result = original(message, title, True, closeButton, copyButton, sanitize, *args, **kwargs)
		if windowHook:
			# The window is created on another thread a moment later: look for it a few times.
			import wx

			for delay in (50, 200, 600, 1500):
				wx.CallLater(delay, windowHook)
		return result

	return wrapped


def installMessages(isActive, bgGetter, windowHook=None):
	"""Dark styling for NVDA's browseable message windows while isActive() is True; windowHook
	(called a few times after each message is shown) darkens the window frame."""
	try:
		import ui
	except ImportError:
		return
	original = getattr(ui, "browseableMessage", None)
	if original is None or (ui, "browseableMessage") in _originals:
		return
	_originals[(ui, "browseableMessage")] = original
	ui.browseableMessage = _darkBrowseableMessage(original, isActive, bgGetter, windowHook)


def uninstall():
	global _isActive
	for (module, name), original in _originals.items():
		setattr(module, name, original)
	_originals.clear()
	_isActive = lambda: False


def clearCache():
	shutil.rmtree(_cacheRoot(), ignore_errors=True)
