# Catches brief flashes when the NVDA menu opens. Runs OUTSIDE NVDA (so it cannot slow
# NVDA down): grabs the screen region where the menu appears ~50x/s with a direct
# BitBlt, asks the dev hook to pop the menu, then reports how many white-ish pixels
# each frame had and saves the frames around any spike to dev/shots/<name>-NNN.png.
#
#   python dev/flashcap.py [name]
import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

try:
	ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
	pass

NVDA_DIR = r"C:\Program Files\NVDA"
HERE = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(NVDA_DIR)
sys.path.insert(0, os.path.join(NVDA_DIR, "library.zip"))
from PIL import Image  # noqa: E402  (NVDA's bundled PIL)

#   python dev/flashcap.py NAME            films 2.2 s and pops the menu through the dev hook
#   python dev/flashcap.py NAME --wait S   films S seconds; the user opens the menu with NVDA+N
#   python dev/flashcap.py NAME --verb "settings general" --full   films the whole screen while the
#                                                                    hook opens something else
name = sys.argv[1] if len(sys.argv) > 1 else "flash"
wait = float(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
verb = sys.argv[sys.argv.index("--verb") + 1] if "--verb" in sys.argv else "menupop"
full = "--full" in sys.argv
seconds = float(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 2.2
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = (ctypes.c_void_p,)
gdi32.CreateDIBSection.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD)
gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
gdi32.BitBlt.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.DWORD)
gdi32.DeleteDC.argtypes = (ctypes.c_void_p,)
gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
user32.GetDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = (wintypes.HWND, ctypes.c_void_p)

sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
cx, cy = sw // 2, sh // 2
if full:
	L, T, R, B = 0, 0, sw, sh
else:
	L, T = max(0, cx - 300), max(0, cy - 300)
	R, B = min(sw, cx + 1100), min(sh, cy + 1300)
W, H = R - L, B - T
REDUCE = 8 if full else 4


class BITMAPINFOHEADER(ctypes.Structure):
	_fields_ = [
		("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
		("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
		("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
		("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
	]


def capture(seconds, frames):
	screen = user32.GetDC(0)
	mem = gdi32.CreateCompatibleDC(screen)
	bmi = BITMAPINFOHEADER()
	bmi.biSize = ctypes.sizeof(bmi)
	bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount = W, -H, 1, 32
	bits = ctypes.c_void_p()
	bmp = gdi32.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
	old = gdi32.SelectObject(mem, bmp)
	size = W * H * 4
	t0 = time.perf_counter()
	lastLight = None
	while time.perf_counter() - t0 < seconds:
		gdi32.BitBlt(mem, 0, 0, W, H, screen, L, T, 0x00CC0020)  # SRCCOPY
		t = time.perf_counter() - t0
		img = Image.frombuffer("RGB", (W, H), ctypes.string_at(bits, size), "raw", "BGRX", 0, 1)
		# brightness on a 4x-reduced copy: fast, still catches a light rectangle
		light = img.reduce(REDUCE).convert("L").point(lambda v: 255 if v > 200 else 0).histogram()[255] * REDUCE * REDUCE
		# keep the picture only when something changed (long films would eat memory otherwise)
		frames.append((t, light, img if light != lastLight else None))
		lastLight = light
	gdi32.SelectObject(mem, old)
	gdi32.DeleteObject(bmp)
	gdi32.DeleteDC(mem)
	user32.ReleaseDC(0, screen)


frames = []
th = threading.Thread(target=capture, args=(wait or seconds, frames), daemon=True)
th.start()
if wait:
	print("filming for %.0f s: open the NVDA menu with NVDA+N, then press Escape" % wait, flush=True)
else:
	time.sleep(0.25)
	subprocess.run([sys.executable, os.path.join(HERE, "nvda_exec.py")] + verb.split(" "), check=False)
th.join()

out = os.path.join(HERE, "shots")
os.makedirs(out, exist_ok=True)
stats = frames
base = stats[0][1]
peak = max(range(len(stats)), key=lambda i: stats[i][1])
print("frames=%d (%.0f fps) region=%r baselineLight=%d" % (len(stats), len(stats) / stats[-1][0], (L, T, R, B), base))
prev = None
for i, (t, light, img) in enumerate(stats):
	if light != prev or i == peak:
		print("%3d t=%6.3f light=%7d delta=%+7d%s" % (i, t, light, light - base, "  <-- peak" if i == peak else ""))
	prev = light
keep = set(range(max(0, peak - 2), min(len(stats), peak + 3))) | {len(stats) - 1}
keep = [i for i in sorted(keep) if stats[i][2] is not None]
for i in keep:
	img = stats[i][2]
	if full:
		img = img.reduce(3)
	img.save(os.path.join(out, "%s-%03d.png" % (name, i)))
print("saved frames", sorted(keep), "to", out)
