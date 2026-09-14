import ctypes, os, sys, threading
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
wd = threading.Timer(20, lambda: os._exit(3)); wd.daemon = True; wd.start()
NVDA = r"C:\Program Files\NVDA"; HERE = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(NVDA); sys.path.insert(0, os.path.join(NVDA, "library.zip")); sys.path.insert(0, NVDA)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "addon", "globalPlugins", "darkMode")))
import wx, theming, native
from PIL import ImageGrab
from collections import Counter
u = ctypes.windll.user32
class R(ctypes.Structure): _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
def colours(win):
    r = R(); u.GetWindowRect(win.GetHandle(), ctypes.byref(r))
    im = ImageGrab.grab(bbox=(r.l + 4, r.t + 4, r.r - 30, r.b - 4), all_screens=True)
    c = Counter(im.getdata()); bg = c.most_common(1)[0][0]
    return bg, [x[0] for x in c.most_common(5) if x[0] != bg][:2]
seen = []
origProc = native._proc
def trace(hwnd, msg, wParam, lParam, idSub, ref):
    if idSub == native.ID_RICH: seen.append(hex(msg))
    return origProc(hwnd, msg, wParam, lParam, idSub, ref)
native._proc = trace
native._subclassProc = native._SUBCLASSPROC(trace)
app = wx.App(False)
engine = theming.DarkModeEngine(lambda: True); engine.start()
f = wx.Frame(None, title="rich experiment"); f.SetSize(f.FromDIP(wx.Size(500, 200)))
p = wx.Panel(f)
rich = wx.TextCtrl(p, style=wx.TE_RICH2 | wx.TE_MULTILINE | wx.TE_READONLY, size=p.FromDIP(wx.Size(300, 60)), pos=p.FromDIP(wx.Point(10, 10)))
print("class:", theming._className(rich.GetHandle()), "isRich:", native.isRichEdit(rich.GetHandle()), "subclassed:", native._subclassed.get(rich.GetHandle()))
f.Show()
def s1():
    print("before SetValue: colours", colours(rich))
    rich.SetValue("No mirror")
    wx.CallLater(300, s2)
def s2():
    print("after SetValue: colours", colours(rich), "msgs seen:", sorted(set(seen)))
    native.applyRichColours(rich.GetHandle(), (255,255,255), (43,43,43)); rich.Refresh()
    wx.CallLater(300, s3)
def s3():
    print("after manual applyRichColours: colours", colours(rich))
    f.Destroy(); app.ExitMainLoop()
wx.CallLater(700, s1)
app.MainLoop()
