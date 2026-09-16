# Full sweep of NVDA's GUI under dark mode: every settings category (reached through the
# category list, as a user would, audited at the top and scrolled to the bottom), every
# dialog the dev hook can open, and the menus. Flags dark text on dark backgrounds and
# light backgrounds. Needs NVDA running with the dev build.
#
#   python dev/sweep.py [--background <key>] [--accent <key>] [--bright-rows on|off] [--bright-controls on|off] [--outline 1..5]
#
# Each given setting is switched live first (keys as in themes.py) and left in place
# afterwards; without them the sweep runs under whatever is set.
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXEC = os.path.join(HERE, "nvda_exec.py")

ap = argparse.ArgumentParser()
ap.add_argument("--background")
ap.add_argument("--accent")
ap.add_argument("--bright-rows", dest="brightRows", choices=("on", "off"))
ap.add_argument("--bright-controls", dest="brightControls", choices=("on", "off"))
ap.add_argument("--outline", type=int, choices=(1, 2, 3, 4, 5))
args = ap.parse_args()


def run(*args, timeout=20):
	env = dict(os.environ, NVDA_EXEC_TIMEOUT=str(timeout))
	r = subprocess.run([sys.executable, EXEC, *args], capture_output=True, text=True, env=env)
	return (r.stdout + r.stderr).strip()


def section(title):
	print("\n=== " + title, flush=True)


def audit(title):
	out = run("audit", title)
	bad = [ln for ln in out.splitlines() if ln.startswith("!!")]
	summary = [ln for ln in out.splitlines() if ln.startswith("audited")]
	for ln in bad:
		print("  " + ln)
	print("  " + (summary[0] if summary else out[-200:]), flush=True)
	return bad


problems = {}

# --- theme under test ----------------------------------------------------------
for name, key in (("background", "background"), ("accent", "accent"), ("brightRows", "brightRows"), ("brightControls", "brightControls"), ("outline", "outlineWidth")):
	value = getattr(args, name)
	if value:
		section("Setting: %s = %s" % (key, value))
		print("  " + run("setting", key, str(value)))
		time.sleep(1)

# --- settings categories -----------------------------------------------------
cats = run("categories").strip().split("|")
run("close", "NVDA Settings")
time.sleep(1)
run("settings", "general")
time.sleep(3)
for cat in cats:
	section("Settings > " + cat)
	print("  " + run("category", cat))
	time.sleep(2.2)
	run("scroll", "NVDA Settings", "0")
	time.sleep(0.6)
	bad = audit("NVDA Settings")
	run("scroll", "NVDA Settings", "100000")
	time.sleep(0.8)
	bad += audit("NVDA Settings")
	if bad:
		problems["Settings > " + cat] = bad
run("close", "NVDA Settings")
time.sleep(1)

# --- dialogs ---------------------------------------------------------------------
dialogs = [
	("dictionary", "Dictionary"),
	("symbols", "Symbol Pronunciation"),
	("gestures", "Input Gestures"),
	("addons", "Add-on Store"),
	("about", "About"),
	("profiles", "Configuration Profiles"),
	("logviewer", "Log Viewer"),
	("console", "Python Console"),
	("exit", "Exit NVDA"),
]
for verb, title in dialogs:
	section("Dialog: " + title)
	print("  " + run("dialog", verb))
	time.sleep(8 if verb == "addons" else 3.5)
	bad = audit(title)
	if bad:
		problems["Dialog: " + title] = bad
	run("close", title)
	time.sleep(1.2)

section("Dialog: Welcome")
run("welcome")
time.sleep(3)
bad = audit("Welcome")
if bad:
	problems["Dialog: Welcome"] = bad
run("close", "Welcome")
time.sleep(1)

# sub-dialogs from settings
subs = [
	("general", "Change...", "Update Mirror"),
	("speech", "Change...", "Select Synthesizer"),
	("braille", "Change...", "Select Braille Display"),
]
for cat, button, title in subs:
	section("Dialog: " + title)
	run("settings", cat)
	time.sleep(3)
	print("  " + run("click", "NVDA Settings", button))
	time.sleep(2.5)
	bad = audit(title)
	if bad:
		problems["Dialog: " + title] = bad
	run("close", title)
	time.sleep(0.8)
	run("close", "NVDA Settings")
	time.sleep(1)

# dictionary entry dialog
section("Dialog: Dictionary entry")
run("dialog", "dictionary")
time.sleep(3)
print("  " + run("click", "Dictionary", "Add"))
time.sleep(2.5)
bad = audit("Dictionary Entry")
if bad:
	problems["Dialog: Dictionary entry"] = bad
run("close", "Dictionary Entry")
time.sleep(0.8)
run("close", "Dictionary")
time.sleep(1)

# --- menus -------------------------------------------------------------------------
from PIL import Image  # noqa: E402
from collections import Counter  # noqa: E402

shots = os.path.join(HERE, "shots")
for name, keys in (("sweep-menu-main", ""), ("sweep-menu-prefs", "down,right"), ("sweep-menu-tools", "down,down,right"), ("sweep-menu-help", "down,down,down,right")):
	section("Menu: " + name)
	run("menu", name, keys)
	time.sleep(3)
	path = os.path.join(shots, name + ".png")
	if not os.path.exists(path):
		print("  no screenshot")
		continue
	im = Image.open(path).convert("RGB")
	cnt = Counter(im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata())
	nearBlack = sum(n for col, n in cnt.items() if max(col) <= 12)
	light = sum(n for col, n in cnt.items() if min(col) >= 200)
	total = im.width * im.height
	print("  size=%s nearBlack=%d (%.1f%%) light=%d (%.1f%%) dominant=%s" % (im.size, nearBlack, 100 * nearBlack / total, light, 100 * light / total, cnt.most_common(1)[0][0]))
	if light > total * 0.3:
		problems["Menu: " + name] = ["light menu"]

section("SUMMARY")
print("  background=%s accent=%s brightRows=%s brightControls=%s outline=%s" % (args.background or "(as set)", args.accent or "(as set)", args.brightRows or "(as set)", args.brightControls or "(as set)", args.outline or "(as set)"))
if not problems:
	print("  nothing flagged")
for k, v in problems.items():
	print("  " + k)
	for ln in v:
		print("     " + ln)
