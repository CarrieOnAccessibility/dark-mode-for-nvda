# Send one command to the live NVDA via the dev hook (see addon/.../devhook.py).
#   python dev/nvda_exec.py ping
#   python dev/nvda_exec.py settings "Speech"        (open Settings at a category)
#   python dev/nvda_exec.py shot "NVDA Settings" name (screenshot -> dev/shots/name.png)
#   python dev/nvda_exec.py menu nvda-menu p         (pop NVDA menu, open submenu P, shoot, close)
#   python dev/nvda_exec.py click "NVDA Settings" Cancel
# Verbs: ping settings dialog menu shot dump click close hover refresh retheme.
# Extra arguments are joined with | for the hook.
import os
import sys
import time

CMD_DIR = os.path.join(os.environ["TEMP"], "darkMode-dev")
CMD = os.path.join(CMD_DIR, "cmd.txt")
RESULT = os.path.join(CMD_DIR, "result.txt")
os.makedirs(CMD_DIR, exist_ok=True)

verb = sys.argv[1]
line = verb + (" " + "|".join(sys.argv[2:]) if len(sys.argv) > 2 else "")
timeout = float(os.environ.get("NVDA_EXEC_TIMEOUT", "15"))
if os.path.exists(RESULT):
	os.remove(RESULT)
with open(CMD + ".tmp", "w", encoding="utf-8") as f:
	f.write(line)
os.replace(CMD + ".tmp", CMD)
end = time.time() + timeout
while time.time() < end:
	if os.path.exists(RESULT):
		time.sleep(0.05)
		with open(RESULT, encoding="utf-8") as f:
			print(f.read(), end="")
		sys.exit(0)
	time.sleep(0.1)
print("TIMEOUT: no result from NVDA (running with the dev install?)")
sys.exit(1)
