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

from . import theming

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
}


def wantDark() -> bool:
	"""The user's preference, before the engine applies its High Contrast override."""
	return config.conf[CONF_SECTION]["mode"] != "off"


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
		wx.CallAfter(restartNVDA)


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


class DarkModeSettingsPanel(SettingsPanel):
	# Translators: title of the Dark Mode category in the NVDA Settings dialog.
	title = _("Dark Mode")
	helpId = ""

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: label of the check box that turns NVDA's dark mode on or off.
		self.enabledCheckBox = sHelper.addItem(wx.CheckBox(self, label=_("&Dark mode for NVDA's windows and menus")))
		self.enabledCheckBox.SetValue(config.conf[CONF_SECTION]["mode"] != "off")
		self.restartCheckBox = sHelper.addItem(
			# Translators: label of the check box that makes NVDA restart when dark mode is turned off.
			wx.CheckBox(self, label=_("&Restart NVDA when dark mode is turned off"))
		)
		self.restartCheckBox.SetValue(bool(config.conf[CONF_SECTION]["restartWhenOff"]))
		note = wx.StaticText(
			self,
			# Translators: explanatory text shown in the Dark Mode settings category.
			label=_(
				"Also in the NVDA menu under Preferences, and as a command in Input Gestures. "
				"Off automatically while Windows High Contrast is on."
			),
		)
		note.Wrap(self.scaleSize(500))
		sHelper.addItem(note)

	def onSave(self):
		config.conf[CONF_SECTION]["restartWhenOff"] = self.restartCheckBox.IsChecked()
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
			self.engine.start()
		except Exception:
			log.exception("darkMode: engine failed to start")
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
		self.engine.refresh()

	@script(
		# Translators: description of the command that toggles NVDA's dark mode.
		description=_("Toggles dark mode for NVDA's windows and menus"),
	)
	def script_toggleDarkMode(self, gesture):
		toggle()
