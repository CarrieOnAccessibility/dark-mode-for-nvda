import ctypes, os, sys, threading
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
wd = threading.Timer(20, lambda: os._exit(3)); wd.daemon = True; wd.start()
NVDA = r"C:\Program Files\NVDA"; HERE = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(NVDA); sys.path.insert(0, os.path.join(NVDA, "library.zip")); sys.path.insert(0, NVDA)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "addon", "globalPlugins", "nvdaDarkMode")))
import wx, theming, native
from PIL import ImageGrab
u = ctypes.windll.user32
class R(ctypes.Structure): _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
def edge(win):
    r = R(); u.GetWindowRect(win.GetHandle(), ctypes.byref(r))
    im = ImageGrab.grab(bbox=(r.l, r.t + (r.b - r.t)//2, r.l + 4, r.t + (r.b - r.t)//2 + 1), all_screens=True)
    return [im.getpixel((x, 0)) for x in range(4)]
app = wx.App(False)
engine = theming.DarkModeEngine(lambda: True); engine.start()
f = wx.Frame(None, title="frame experiment"); f.SetSize(f.FromDIP(wx.Size(600, 300)))
p = wx.Panel(f)
lc = wx.ListCtrl(p, style=wx.LC_REPORT | wx.LC_NO_HEADER, size=p.FromDIP(wx.Size(250, 120)), pos=p.FromDIP(wx.Point(10, 10)))
lc.InsertColumn(0, "x"); [lc.Append((t,)) for t in ["General", "Speech"]]
tc = wx.TextCtrl(p, value="text", size=p.FromDIP(wx.Size(250, -1)), pos=p.FromDIP(wx.Point(280, 10)))
f.Show()
calls = []
orig = native._paintFrame
def spy(h):
    calls.append(h); return orig(h)
native._paintFrame = spy
# trace every message our subclass sees on the list, with edge colour before/after
origProc = native._proc
seen = []
def px(hwnd):
    dc = u.GetWindowDC(hwnd); v = ctypes.windll.gdi32.GetPixel(dc, 0, 40); u.ReleaseDC(hwnd, dc)
    return (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)
def traceProc(hwnd, msg, wParam, lParam, idSub, ref):
    if hwnd == lc.GetHandle() and msg in (0x85, 0x86, 0x83, 0x0F, 0x14, 0x47, 0x46, 0x7c, 0x7d, 0x31a):
        before = px(hwnd)
        r = origProc(hwnd, msg, wParam, lParam, idSub, ref)
        seen.append((hex(msg), before, px(hwnd)))
        return r
    return origProc(hwnd, msg, wParam, lParam, idSub, ref)
native._proc = traceProc
native._subclassProc = native._SUBCLASSPROC(traceProc)
def step():
    h = lc.GetHandle()
    print("thickness list", native._frameOf(h), "text", native._frameOf(tc.GetHandle()))
    print("subclassed", native._subclassed.get(h), native._subclassed.get(tc.GetHandle()))
    print("edge list", edge(lc), "edge text", edge(tc))
    print("paintFrame calls so far for list:", calls.count(h), "for text:", calls.count(tc.GetHandle()))
    native._RedrawWindow(h, None, None, native.RDW_FRAME | native.RDW_INVALIDATE | native.RDW_UPDATENOW)
    wx.CallLater(300, step2)
def step2():
    h = lc.GetHandle()
    print("after redraw: calls", calls.count(h), "edge list", edge(lc))
    orig(h)
    print("after direct _paintFrame: edge list", edge(lc))
    u.InvalidateRect(h, None, True); u.UpdateWindow(h)
    print("after client-only repaint (WM_PAINT): edge list", edge(lc))
    orig(h)
    u.SendMessageW(h, 0x0085, 1, 0)  # WM_NCPAINT with whole-frame region
    print("after direct _paintFrame + WM_NCPAINT: edge list", edge(lc))
    for x in seen[-8:]: print("   msg", x)
    f.Destroy(); app.ExitMainLoop()
wx.CallLater(800, step)
app.MainLoop()
