# NVDA Dark Mode add-on: global plugin entry point.
#
# Wires the theming engine (see theming.py) into NVDA: starts it at load,
# adds a "Dark Mode" category to NVDA's Settings dialog, and provides a
# toggle command that users can bind in Input Gestures.

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
	addonHandler.initTranslation()
except Exception:  # not running from an installed add-on (e.g. scratchpad)
	pass

CONF_SECTION = "nvdaDarkMode"
# Order matters: index into MODES is what the settings panel's choice control uses.
MODES = ("followSystem", "dark", "off")
config.conf.spec[CONF_SECTION] = {
	"mode": "option('followSystem', 'dark', 'off', default='followSystem')",
}


def wantDark() -> bool:
	"""The user's preference, before the engine applies its High Contrast override."""
	mode = config.conf[CONF_SECTION]["mode"]
	if mode == "dark":
		return True
	if mode == "off":
		return False
	return theming.systemUsesDarkApps()


class DarkModeSettingsPanel(SettingsPanel):
	# Translators: title of the Dark Mode category in the NVDA Settings dialog.
	title = _("Dark Mode")
	helpId = ""

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: label of the combo box choosing when NVDA's interface is dark.
		label = _("&Dark mode for NVDA's windows and menus:")
		choices = [
			# Translators: dark mode option: follow the Windows light/dark app setting.
			_("Follow Windows setting"),
			# Translators: dark mode option: always dark.
			_("Always on"),
			# Translators: dark mode option: never dark.
			_("Off"),
		]
		self.modeChoice = sHelper.addLabeledControl(label, wx.Choice, choices=choices)
		self.modeChoice.SetSelection(MODES.index(config.conf[CONF_SECTION]["mode"]))
		note = wx.StaticText(
			self,
			# Translators: explanatory text shown in the Dark Mode settings category.
			label=_(
				"Dark mode switches itself off while a Windows High Contrast theme is active. "
				"A command to toggle dark mode can be assigned under Input Gestures, in the Dark Mode category."
			),
		)
		note.Wrap(self.scaleSize(500))
		sHelper.addItem(note)

	def onSave(self):
		config.conf[CONF_SECTION]["mode"] = MODES[self.modeChoice.GetSelection()]
		if GlobalPlugin.instance:
			GlobalPlugin.instance.engine.refresh()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: category of the add-on's commands in the Input Gestures dialog.
	scriptCategory = _("Dark Mode")
	instance = None

	def __init__(self):
		super().__init__()
		GlobalPlugin.instance = self
		self.engine = theming.DarkModeEngine(wantDark)
		NVDASettingsDialog.categoryClasses.append(DarkModeSettingsPanel)
		config.post_configProfileSwitch.register(self.onConfigChanged)
		config.post_configReset.register(self.onConfigChanged)
		try:
			self.engine.start()
		except Exception:
			log.exception("nvdaDarkMode: engine failed to start")

	def terminate(self):
		config.post_configProfileSwitch.unregister(self.onConfigChanged)
		config.post_configReset.unregister(self.onConfigChanged)
		try:
			NVDASettingsDialog.categoryClasses.remove(DarkModeSettingsPanel)
		except ValueError:
			pass
		try:
			self.engine.stop()
		except Exception:
			log.exception("nvdaDarkMode: engine failed to stop cleanly")
		GlobalPlugin.instance = None
		super().terminate()

	def onConfigChanged(self, **kwargs):
		self.engine.refresh()

	@script(
		# Translators: description of the command that toggles NVDA's dark mode.
		description=_("Toggles dark mode for NVDA's windows and menus"),
	)
	def script_toggleDarkMode(self, gesture):
		if theming.highContrastActive():
			# Translators: spoken when the toggle command is used during a Windows High Contrast theme.
			ui.message(_("Dark mode is unavailable while a Windows High Contrast theme is active"))
			return
		config.conf[CONF_SECTION]["mode"] = "off" if self.engine.active else "dark"
		self.engine.refresh()
		if self.engine.active:
			# Translators: spoken when NVDA's dark mode is switched on.
			ui.message(_("NVDA dark mode on"))
		else:
			# Translators: spoken when NVDA's dark mode is switched off.
			ui.message(_("NVDA dark mode off"))
