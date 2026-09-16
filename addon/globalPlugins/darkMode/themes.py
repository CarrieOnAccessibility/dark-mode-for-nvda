# Dark Mode: an NVDA add-on. Copyright (C) 2026 Carrie on Accessibility.
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, version 2.
# See the LICENSE file for details.
# Colour choices for the Dark Mode settings: a Background and an Accent.
#
# A Background is what dialogs, panels, lists and the help pages are filled with. An
# Accent is the colour of everything that points at something: focus rings, the outline
# on the highlighted menu item, the selected row of a list, a slider's thumb. The two
# are independent, so any background goes with any accent. "Bright contrast" (a check
# box, not a table) makes the selected row the accent colour itself with black text.
#
# Adding one is adding an entry below; the settings panel lists them in this order and
# the config spec is built from the keys. Every new entry needs a sweep (dev/sweep.py)
# with each background or accent it can be paired with, and the numbers checked, not the
# eyes: a focus ring wants at least 3:1 against the dialog, field and button faces, and
# the white text on a selected row at least 4.5:1 (these all measure 7:1 or better).
# Chosen 2026-09-16 from the swatch page; the coloured backgrounds are deliberately dark.

from collections import namedtuple

try:
	import addonHandler

	addonHandler.initTranslation()
except Exception:  # not running from an installed add-on (test bench, scratchpad)
	pass
try:
	_  # noqa: B018 - injected into this module by initTranslation above
except NameError:

	def _(s):
		return s


WHITE = (0xFF, 0xFF, 0xFF)
BLACK = (0x00, 0x00, 0x00)


def _step(rgb, n):
	"""The colour n steps lighter per channel: lists sit one step up from their dialog."""
	return tuple(min(255, c + n) for c in rgb)


def _shade(rgb, k):
	"""The colour darkened by the fraction k: the slider thumb under the mouse and pressed."""
	return tuple(int(round(c * (1 - k))) for c in rgb)


# bg: dialogs, panels, the menu bar strip, behind buttons and radio buttons.
# listBg: lists, trees and check lists (text fields and dropdowns keep their own grey).
# textAreasFollow: read-only text areas (speech viewer, Add-on Store details, the
#   Python console) take the dialog background instead of the field grey.
Background = namedtuple("Background", "key label bg listBg textAreasFollow")


def _background(key, label, bg, listBg=None, textAreasFollow=False):
	return Background(key, label, bg, _step(bg, 11) if listBg is None else listBg, textAreasFollow)


# focus: focus rings, the menu outline, the tab focus line, a slider's thumb at rest, and the
#   checked glyph of check boxes and radio buttons; with Bright contrast also the selected
#   row (then with black text).
# selection: the selected row of a focused list, with white text.
# hot / pressed: the slider thumb and the checked glyphs under the mouse, and while pressed.
# windowsGlyphs: leave check boxes and radio buttons to Windows, which draws them in its own
#   accent colour. Off for every accent (her call, 2026-09-16: Blue too, so they all match);
#   kept so an accent can opt back into Windows' glyphs with one word.
Accent = namedtuple("Accent", "key label focus selection hot pressed windowsGlyphs")


def _accent(key, label, focus, selection, hot=None, pressed=None, windowsGlyphs=False):
	return Accent(key, label, focus, selection, hot or _shade(focus, 0.22), pressed or _shade(focus, 0.38), windowsGlyphs)


BACKGROUNDS = (
	# Translators: a background choice in the Dark Mode settings (Windows' usual dark grey).
	_background("grey", _("Dark grey"), (0x20, 0x20, 0x20), (0x2B, 0x2B, 0x2B)),
	# Translators: a background choice in the Dark Mode settings.
	_background("black", _("Black"), BLACK, BLACK, textAreasFollow=True),
	# Translators: a background choice in the Dark Mode settings (a grey a little lighter than the default).
	_background("lightgrey", _("Lighter grey"), (0x2E, 0x2E, 0x2E)),
	# Translators: a background choice in the Dark Mode settings (a very dark red).
	_background("red", _("Red"), (0x33, 0x14, 0x14)),
	# Translators: a background choice in the Dark Mode settings (a very dark orange).
	_background("orange", _("Orange"), (0x33, 0x20, 0x0F)),
	# Translators: a background choice in the Dark Mode settings (a very dark green).
	_background("green", _("Green"), (0x14, 0x33, 0x1C)),
	# Translators: a background choice in the Dark Mode settings (a very dark blue).
	_background("blue", _("Blue"), (0x14, 0x21, 0x3A)),
	# Translators: a background choice in the Dark Mode settings (a very dark purple).
	_background("purple", _("Purple"), (0x26, 0x16, 0x38)),
	# Translators: a background choice in the Dark Mode settings (a very dark teal).
	_background("teal", _("Teal"), (0x14, 0x33, 0x33)),
	# Translators: a background choice in the Dark Mode settings (a very dark pink).
	_background("pink", _("Pink"), (0x38, 0x14, 0x2A)),
)

ACCENTS = (
	# Windows 11's dark-mode accent blue for the rings; the selected row sits between the
	# settings sidebar's dark blue and Windows' bright accent. Hover/pressed as before 0.9.4.
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("blue", _("Blue"), (0x60, 0xCD, 0xFF), (0x1E, 0x5A, 0x8C), (0x00, 0x78, 0xD7), (0x00, 0x5F, 0xB8)),
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("red", _("Red"), (0xFF, 0x8A, 0x80), (0x8C, 0x1E, 0x1E)),
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("orange", _("Orange"), (0xFF, 0xB8, 0x70), (0x8A, 0x45, 0x12)),
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("green", _("Green"), (0x8E, 0xE5, 0x9F), (0x1B, 0x64, 0x37)),
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("purple", _("Purple"), (0xC9, 0xA0, 0xFF), (0x63, 0x43, 0x99)),
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("teal", _("Teal"), (0x8A, 0xED, 0xE6), (0x17, 0x60, 0x60)),
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("pink", _("Pink"), (0xFF, 0xA6, 0xE2), (0x96, 0x24, 0x6B)),
	# Translators: an accent colour choice in the Dark Mode settings.
	_accent("yellow", _("Yellow"), (0xFF, 0xD4, 0x00), (0x6E, 0x4A, 0x00)),
)

DEFAULT_BACKGROUND = "grey"
DEFAULT_ACCENT = "blue"


def _find(entries, key, default):
	for entry in entries:
		if entry.key == key:
			return entry
	return _find(entries, default, None) if default else entries[0]


def background(key: str) -> Background:
	"""The Background with this key, or the default for an unknown one."""
	return _find(BACKGROUNDS, key, DEFAULT_BACKGROUND)


def accent(key: str) -> Accent:
	"""The Accent with this key, or the default for an unknown one."""
	return _find(ACCENTS, key, DEFAULT_ACCENT)


def index(entries, key: str) -> int:
	"""Position of a key in BACKGROUNDS or ACCENTS (the default's position if unknown)."""
	keys = [entry.key for entry in entries]
	default = DEFAULT_BACKGROUND if entries is BACKGROUNDS else DEFAULT_ACCENT
	return keys.index(key) if key in keys else keys.index(default)


def optionSpec(entries, default: str) -> str:
	"""A configobj 'option(...)' spec listing every key, for the add-on's config section."""
	return "option(%s, default=%r)" % (", ".join(repr(entry.key) for entry in entries), default)
