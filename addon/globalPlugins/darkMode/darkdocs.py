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
_originals = {}

DARK_CSS = """/* Added by the Dark Mode add-on. The original page is untouched; this is a copy. */
:root { color-scheme: dark; }
body { background: #202020; color: #f5f5f5; }
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
td { background-color: #262626; }
tr:nth-child(even) td { background-color: #2b2b2b; }
/* Code */
code, pre { background: #343434; border-bottom: 1px solid #606060; color: #f5f5f5; }
pre { border-left: 2px solid #8fd0ff; }
kbd { background: #333333; color: #ffffff; border: 1px solid #8c8c8c; border-radius: 3px; padding: 0 4px; }
blockquote { border-left: 3px solid #8c8c8c; color: #d1d5db; }
/* NVDA's stylesheet sets no colour on these; the browser default would be dark on dark. */
dl > dt, dl > dd { color: #f5f5f5; }
img { max-width: 100%; }
"""
CSS_NAME = "darkMode-docs.css"
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

	key = hashlib.sha1(("%s|%d|%s" % (os.path.normcase(srcDir), int(newest), DARK_CSS)).encode("utf-8")).hexdigest()[:12]
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


def _darkenHtml(text):
	if CSS_NAME in text:
		return text
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
			f.write(DARK_CSS)
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


def install(isActive):
	"""Start handing NVDA dark copies of help files while isActive() is True."""
	global _isActive
	_isActive = isActive
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


def uninstall():
	global _isActive
	for (module, name), original in _originals.items():
		setattr(module, name, original)
	_originals.clear()
	_isActive = lambda: False


def clearCache():
	shutil.rmtree(_cacheRoot(), ignore_errors=True)
