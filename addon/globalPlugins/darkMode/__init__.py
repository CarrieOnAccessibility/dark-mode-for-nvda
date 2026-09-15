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

from . import darkdocs, native, theming

try:
	from . import devhook  # development builds only; absent from the packaged add-on
except ImportError:
	devhook = None

try:
	addonHandler.initTranslation()
except Exception:  # not running from an installed add-on (e.g. scratchpad)
	pass

CONF_SECTION = "darkMode"
config.conf.spec[CONF_SECTION] = {
	"mode": "option('dark', 'off', default='dark')",
	"restartWhenOff": "boolean(default=True)",
	"thickOutlines": "boolean(default=False)",
	"blackBackgrounds": "boolean(default=False)",
}


def wantDark() -> bool:
	"""The user's preference, before the engine applies its High Contrast override."""
	return config.conf[CONF_SECTION]["mode"] != "off"


def applyBackground(retheme: bool = True):
	"""Dialog backgrounds dark grey or black, per the setting; re-themes open windows if it changed."""
	changed = theming.setBlackBackgrounds(bool(config.conf[CONF_SECTION]["blackBackgrounds"]))
	plugin = GlobalPlugin.instance
	if changed and retheme and plugin and plugin.engine.active:
		theming.themeAllWindows(True, force=True)
		theming.repaintAllWindows()


def applyRingWidth(repaint: bool = True):
	"""Focus rings and the menu outline: one pixel, or two with the thicker-outlines setting."""
	native.setRingWidth(2 if config.conf[CONF_SECTION]["thickOutlines"] else 1)
	if repaint:
		theming.repaintAllWindows()


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


class DarkModeSettingsPanel(SettingsPanel):
	# Translators: title of the Dark Mode category in the NVDA Settings dialog.
	title = _("Dark Mode")
	helpId = ""

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: label of the check box that turns NVDA's dark mode on or off.
		self.enabledCheckBox = sHelper.addItem(wx.CheckBox(self, label=_("&Dark mode for NVDA's windows and menus")))
		self.enabledCheckBox.SetValue(config.conf[CONF_SECTION]["mode"] != "off")
		self.blackCheckBox = sHelper.addItem(
			# Translators: label of the check box that makes dialog backgrounds black instead of dark grey.
			wx.CheckBox(self, label=_("Use &black backgrounds"))
		)
		self.blackCheckBox.SetValue(bool(config.conf[CONF_SECTION]["blackBackgrounds"]))
		self.restartCheckBox = sHelper.addItem(
			# Translators: label of the check box that makes NVDA restart when dark mode is turned off.
			wx.CheckBox(self, label=_("&Restart NVDA when dark mode is turned off (recommended)"))
		)
		self.restartCheckBox.SetValue(bool(config.conf[CONF_SECTION]["restartWhenOff"]))
		self.thickCheckBox = sHelper.addItem(
			# Translators: label of the check box that makes focus rings and the menu outline two pixels thick.
			wx.CheckBox(self, label=_("&Thicker focus outlines"))
		)
		self.thickCheckBox.SetValue(bool(config.conf[CONF_SECTION]["thickOutlines"]))
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

	def onSave(self):
		config.conf[CONF_SECTION]["restartWhenOff"] = self.restartCheckBox.IsChecked()
		config.conf[CONF_SECTION]["thickOutlines"] = self.thickCheckBox.IsChecked()
		config.conf[CONF_SECTION]["blackBackgrounds"] = self.blackCheckBox.IsChecked()
		applyRingWidth()
		applyBackground()
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
			applyRingWidth(repaint=False)
			applyBackground(retheme=False)
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
		applyRingWidth()
		applyBackground()
		self.engine.refresh()

	@script(
		# Translators: description of the command that toggles NVDA's dark mode.
		description=_("Toggles dark mode for NVDA's windows and menus"),
	)
	def script_toggleDarkMode(self, gesture):
		toggle()
