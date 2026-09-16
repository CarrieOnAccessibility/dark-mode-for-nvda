# Dark Mode: an NVDA add-on. Copyright (C) 2026 Carrie on Accessibility.
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, version 2.
# See the LICENSE file for details.
# Dark Mode add-on for NVDA: global plugin entry point.
#
# Wires the theming engine (see theming.py) into NVDA: starts it at load,
# adds a "Dark Mode" category to NVDA's Settings dialog, a check item in the
# NVDA menu (Preferences > Dark mode), and a toggle command that users can
# bind in Input Gestures.

import addonHandler
import config
import globalPluginHandler
import gui
from gui import guiHelper
from gui.settingsDialogs import NVDASettingsDialog, SettingsPanel
from logHandler import log
from scriptHandler import script
import ui
import wx

from . import darkdocs, native, themes, theming

try:
	from . import devhook  # development builds only; absent from the packaged add-on
except ImportError:
	devhook = None

try:
	addonHandler.initTranslation()
except Exception:  # not running from an installed add-on (e.g. scratchpad)
	pass

CONF_SECTION = "darkMode"
# The defaults of the look settings, also what the panel's "Reset to defaults" button sets.
DEFAULT_BRIGHT_ROWS = False
DEFAULT_BRIGHT_CONTROLS = False
DEFAULT_OUTLINE_WIDTH = 2
DEFAULT_RESTART_WHEN_OFF = True
config.conf.spec[CONF_SECTION] = {
	"mode": "option('dark', 'off', default='dark')",
	"restartWhenOff": "boolean(default=%s)" % DEFAULT_RESTART_WHEN_OFF,
	"background": themes.optionSpec(themes.BACKGROUNDS, themes.DEFAULT_BACKGROUND),
	"accent": themes.optionSpec(themes.ACCENTS, themes.DEFAULT_ACCENT),
	"brightRows": "boolean(default=%s)" % DEFAULT_BRIGHT_ROWS,
	"brightControls": "boolean(default=%s)" % DEFAULT_BRIGHT_CONTROLS,
	# One "Bright contrast" check box for a day (dev builds only); split in two, migrated once.
	"brightContrast": "boolean(default=False)",
	"outlineWidth": "integer(min=1, max=%d, default=%d)" % (native.RING_MAX, DEFAULT_OUTLINE_WIDTH),
	# Up to 0.9.3 the background was a "Use black backgrounds" check box and the outline a
	# "Thicker focus outlines" one. Kept so the old values can still be read; migrateConfig()
	# carries them into "background" / "outlineWidth" once and clears them.
	"blackBackgrounds": "boolean(default=False)",
	"thickOutlines": "boolean(default=False)",
}


def wantDark() -> bool:
	"""The user's preference, before the engine applies its High Contrast override."""
	return config.conf[CONF_SECTION]["mode"] != "off"


def migrateConfig():
	"""Carry the 0.9.3 check boxes into the settings that replaced them, once."""
	section = config.conf[CONF_SECTION]
	changed = False
	if section["blackBackgrounds"]:
		section["background"] = "black"
		section["blackBackgrounds"] = False
		changed = True
	if section["thickOutlines"]:
		section["outlineWidth"] = 2
		section["thickOutlines"] = False
		changed = True
	if section["brightContrast"]:
		section["brightRows"] = section["brightControls"] = True
		section["brightContrast"] = False
		changed = True
	if changed:
		saveConfig()


def setLook(background: str, accent: str, brightRows: bool, brightControls: bool, outlineWidth: int, live: bool = True):
	"""Push a set of look values into the engine. With live, open windows follow: a new
	background re-themes them (wx holds the old colours); an accent or bright contrast change
	only needs a repaint, the painters read those at paint time; a new outline width only
	touches the focused control's ring."""
	backgroundChanged = theming.setBackground(background)
	accentChanged = theming.setAccent(accent, brightRows, brightControls)
	ringChanged = native.setRingWidth(outlineWidth)
	plugin = GlobalPlugin.instance
	if not (live and plugin and plugin.engine.active):
		return
	if backgroundChanged:
		theming.themeAllWindows(True, force=True)
	if backgroundChanged or accentChanged:
		theming.repaintAllWindows()
	elif ringChanged:
		native.repaintFocusRing()


def applyLook(live: bool = True):
	"""The look as saved in the settings (after OK, Cancel, a profile switch, at start)."""
	section = config.conf[CONF_SECTION]
	setLook(section["background"], section["accent"], section["brightRows"], section["brightControls"], section["outlineWidth"], live)


def setMode(mode: str):
	"""Store a mode and apply it live. Turning off restarts NVDA if that option is on: open
	windows are put back in place, but a fresh start is the one true native state."""
	plugin = GlobalPlugin.instance
	wasActive = bool(plugin and plugin.engine.active)
	config.conf[CONF_SECTION]["mode"] = mode
	saveConfig()  # both directions: an unclean exit must not leave the other state behind
	if plugin:
		plugin.engine.refresh()
	if mode == "off" and wasActive and config.conf[CONF_SECTION]["restartWhenOff"]:
		wx.CallLater(1500, restartNVDA)  # after the spoken "Dark mode off" has been heard


def saveConfig():
	try:
		config.conf.save()
	except Exception:
		log.debugWarning("darkMode: could not save config", exc_info=True)


def restartNVDA():
	saveConfig()
	import core
	import queueHandler

	queueHandler.queueFunction(queueHandler.eventQueue, core.restart)


def toggle():
	"""Switch dark mode on or off and say what happened; used by the menu item and the command."""
	plugin = GlobalPlugin.instance
	if not plugin:
		return
	if theming.highContrastActive():
		# Translators: spoken when dark mode is toggled during a Windows High Contrast theme.
		ui.message(_("Dark mode is unavailable while a Windows High Contrast theme is active"))
		return
	turningOn = not plugin.engine.active
	setMode("dark" if turningOn else "off")
	# Translators: spoken when NVDA's dark mode is switched on / off.
	ui.message(_("Dark mode on") if turningOn else _("Dark mode off"))


def _sliderClass():
	"""NVDA's slider (arrow keys and page keys behave), or wx's if it is not there."""
	try:
		from gui import nvdaControls

		return nvdaControls.EnhancedInputSlider
	except Exception:
		return wx.Slider


class DarkModeSettingsPanel(SettingsPanel):
	"""The look settings preview live: changing a colour or the outline width re-themes the open
	windows at once, this dialog included, so the dialog is its own preview. OK and Apply keep
	it (onSave); Cancel and Escape put the saved look back (onDiscard). Only the on/off check
	box waits for OK, since turning off can restart NVDA."""

	# Translators: title of the Dark Mode category in the NVDA Settings dialog.
	title = _("Dark Mode")
	helpId = ""
	PREVIEW_DELAY_MS = 120  # arrowing through a dropdown fires a change per item; re-theme once it settles

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		section = config.conf[CONF_SECTION]
		self._preview = None
		# Translators: label of the check box that turns NVDA's dark mode on or off.
		self.enabledCheckBox = sHelper.addItem(wx.CheckBox(self, label=_("&Use Dark mode for NVDA")))
		self.enabledCheckBox.SetValue(section["mode"] != "off")
		self.backgroundChoice = sHelper.addLabeledControl(
			# Translators: label of the dropdown that picks the background colour of NVDA's windows.
			_("&Background:"),
			wx.Choice,
			choices=[entry.label for entry in themes.BACKGROUNDS],
		)
		self.backgroundChoice.SetSelection(themes.index(themes.BACKGROUNDS, section["background"]))
		self.accentChoice = sHelper.addLabeledControl(
			# Translators: label of the dropdown that picks the colour of focus rings and selected list rows.
			_("&Accent:"),
			wx.Choice,
			choices=[entry.label for entry in themes.ACCENTS],
		)
		self.accentChoice.SetSelection(themes.index(themes.ACCENTS, section["accent"]))
		self.brightRowsCheckBox = sHelper.addItem(
			# Translators: label of the check box that paints selected list rows in the accent colour with black text.
			wx.CheckBox(self, label=_("Bright contrast for &selected rows"))
		)
		self.brightRowsCheckBox.SetValue(bool(section["brightRows"]))
		self.brightControlsCheckBox = sHelper.addItem(
			# Translators: label of the check box that paints checked check boxes and slider thumbs in the accent colour.
			wx.CheckBox(self, label=_("Bright contrast for &checkboxes and slider handles"))
		)
		self.brightControlsCheckBox.SetValue(bool(section["brightControls"]))
		self.outlineSlider = sHelper.addLabeledControl(
			# Translators: label of the slider that sets how thick focus rings and the menu outline are, in pixels.
			_("Focus outline &thickness:"),
			_sliderClass(),
			value=int(section["outlineWidth"]),
			minValue=1,
			maxValue=native.RING_MAX,
		)
		self.restartCheckBox = sHelper.addItem(
			# Translators: label of the check box that makes NVDA restart when dark mode is turned off.
			wx.CheckBox(self, label=_("&Restart NVDA when dark mode is turned off (recommended)"))
		)
		self.restartCheckBox.SetValue(bool(section["restartWhenOff"]))
		# Translators: label of the button that puts every Dark Mode setting but the on/off switch back to its default.
		self.resetButton = sHelper.addItem(wx.Button(self, label=_("Reset to &Dark Mode defaults")))
		note = wx.StaticText(
			self,
			# Translators: explanatory text shown in the Dark Mode settings category.
			label=_(
				"You can toggle dark mode in the NVDA menu under Preferences, or add a keyboard shortcut "
				"in Input Gestures. Dark mode turns off automatically while Windows High Contrast is on."
			),
		)
		note.Wrap(self.scaleSize(500))
		sHelper.addItem(note)
		self.backgroundChoice.Bind(wx.EVT_CHOICE, self.onLookChanged)
		self.accentChoice.Bind(wx.EVT_CHOICE, self.onLookChanged)
		self.brightRowsCheckBox.Bind(wx.EVT_CHECKBOX, self.onLookChanged)
		self.brightControlsCheckBox.Bind(wx.EVT_CHECKBOX, self.onLookChanged)
		self.outlineSlider.Bind(wx.EVT_SLIDER, self.onLookChanged)
		self.resetButton.Bind(wx.EVT_BUTTON, self.onReset)

	def _chosenLook(self):
		return (
			themes.BACKGROUNDS[max(0, self.backgroundChoice.GetSelection())].key,
			themes.ACCENTS[max(0, self.accentChoice.GetSelection())].key,
			self.brightRowsCheckBox.IsChecked(),
			self.brightControlsCheckBox.IsChecked(),
			int(self.outlineSlider.GetValue()),
		)

	def _cancelPreview(self):
		if self._preview:
			self._preview.Stop()
			self._preview = None

	def onLookChanged(self, evt):
		evt.Skip()
		self._cancelPreview()
		# plain values only: a timer that outlives the dialog must not hold on to it
		self._preview = wx.CallLater(self.PREVIEW_DELAY_MS, setLook, *self._chosenLook())

	def onReset(self, evt):
		"""Every setting here but the on/off switch back to its default, previewed at once
		(OK keeps it, Cancel still puts the saved look back)."""
		self.backgroundChoice.SetSelection(themes.index(themes.BACKGROUNDS, themes.DEFAULT_BACKGROUND))
		self.accentChoice.SetSelection(themes.index(themes.ACCENTS, themes.DEFAULT_ACCENT))
		self.brightRowsCheckBox.SetValue(DEFAULT_BRIGHT_ROWS)
		self.brightControlsCheckBox.SetValue(DEFAULT_BRIGHT_CONTROLS)
		self.outlineSlider.SetValue(DEFAULT_OUTLINE_WIDTH)
		self.restartCheckBox.SetValue(DEFAULT_RESTART_WHEN_OFF)
		self._cancelPreview()
		setLook(*self._chosenLook())

	def onDiscard(self):
		"""Cancel: the saved look again."""
		self._cancelPreview()
		applyLook()

	def onSave(self):
		self._cancelPreview()
		section = config.conf[CONF_SECTION]
		section["restartWhenOff"] = self.restartCheckBox.IsChecked()
		background, accent, brightRows, brightControls, outlineWidth = self._chosenLook()
		section["background"] = background
		section["accent"] = accent
		section["brightRows"] = brightRows
		section["brightControls"] = brightControls
		section["outlineWidth"] = outlineWidth
		applyLook()
		setMode("dark" if self.enabledCheckBox.IsChecked() else "off")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: category of the add-on's commands in the Input Gestures dialog.
	scriptCategory = _("Dark Mode")
	instance = None

	def __init__(self):
		super().__init__()
		GlobalPlugin.instance = self
		self.engine = theming.DarkModeEngine(wantDark)
		self.engine.onStateChanged = self._syncMenuItem
		NVDASettingsDialog.categoryClasses.append(DarkModeSettingsPanel)
		config.post_configProfileSwitch.register(self.onConfigChanged)
		config.post_configReset.register(self.onConfigChanged)
		self._menuItem = None
		try:
			self._addMenuItem()
		except Exception:
			log.exception("darkMode: could not add the menu item")
		try:
			migrateConfig()
			applyLook(live=False)
			self.engine.start()
		except Exception:
			log.exception("darkMode: engine failed to start")
		try:
			darkdocs.install(lambda: self.engine.active, lambda: theming.BG)
			darkdocs.installMessages(lambda: self.engine.active, lambda: theming.BG, theming.darkenMessageWindows)
		except Exception:
			log.exception("darkMode: could not hook the help files")
		self._syncMenuItem()
		self._devhook = devhook.DevHook(self) if devhook else None

	def _addMenuItem(self):
		menu = gui.mainFrame.sysTrayIcon.preferencesMenu
		self._menuItem = menu.AppendCheckItem(
			wx.ID_ANY,
			# Translators: check item in the NVDA menu (Preferences) that toggles dark mode.
			_("Dar&k mode"),
			# Translators: help text of the Dark mode item in the NVDA menu.
			_("Turn dark mode for NVDA's windows and menus on or off"),
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onMenuItem, self._menuItem)

	def _removeMenuItem(self):
		if not self._menuItem:
			return
		try:
			gui.mainFrame.sysTrayIcon.preferencesMenu.Remove(self._menuItem)
		except Exception:
			log.debugWarning("darkMode: could not remove the menu item", exc_info=True)
		self._menuItem = None

	def _syncMenuItem(self):
		"""Keep the menu item's check mark matching what is actually on screen."""
		if self._menuItem:
			try:
				self._menuItem.Check(self.engine.active)
			except Exception:
				pass

	def onMenuItem(self, evt):
		toggle()
		self._syncMenuItem()

	def terminate(self):
		if self._devhook:
			self._devhook.stop()
		config.post_configProfileSwitch.unregister(self.onConfigChanged)
		config.post_configReset.unregister(self.onConfigChanged)
		try:
			NVDASettingsDialog.categoryClasses.remove(DarkModeSettingsPanel)
		except ValueError:
			pass
		self._removeMenuItem()
		try:
			darkdocs.uninstall()
		except Exception:
			log.exception("darkMode: could not unhook the help files")
		try:
			import core

			exiting = bool(getattr(core, "_hasShutdownBeenTriggered", False))
		except Exception:
			exiting = False
		try:
			self.engine.onStateChanged = None
			self.engine.stop(restore=not exiting)
		except Exception:
			log.exception("darkMode: engine failed to stop cleanly")
		GlobalPlugin.instance = None
		super().terminate()

	def onConfigChanged(self, **kwargs):
		applyLook()
		self.engine.refresh()

	@script(
		# Translators: description of the command that toggles NVDA's dark mode.
		description=_("Toggles dark mode for NVDA's windows and menus"),
	)
	def script_toggleDarkMode(self, gesture):
		toggle()
