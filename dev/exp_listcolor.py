# Experiment: why is wx.ListCtrl / wx.ListBox text black under the engine?
import ctypes, os, sys, threading
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
wd = threading.Timer(20, lambda: os._exit(3)); wd.daemon = True; wd.start()
NVDA = r"C:\Program Files\NVDA"; HERE = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(NVDA); sys.path.insert(0, os.path.join(NVDA, "library.zip")); sys.path.insert(0, NVDA)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "addon", "globalPlugins", "darkMode")))
import wx
import theming
from PIL import ImageGrab
from collections import Counter
u = ctypes.windll.user32
LVM_GETTEXTCOLOR = 0x1000 + 35; LVM_SETTEXTCOLOR = 0x1000 + 36; LVM_GETBKCOLOR = 0x1000 + 0

class R(ctypes.Structure): _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
def textColour(win):
    r = R(); u.GetWindowRect(win.GetHandle(), ctypes.byref(r))
    im = ImageGrab.grab(bbox=(r.l + 6, r.t + 6, r.r - 30, r.b - 6), all_screens=True)
    c = Counter(im.getdata()); bg = c.most_common(1)[0][0]
    nxt = [x for x in c.most_common(6) if x[0] != bg][:2]
    return bg, nxt

app = wx.App(False)
mode = sys.argv[1] if len(sys.argv) > 1 else "engine"
engine = theming.DarkModeEngine(lambda: True)
if mode != "none":
    engine.start()
f = wx.Frame(None, title="list colour experiment")
f.SetSize(f.FromDIP(wx.Size(700, 400)))
p = wx.Panel(f)
lc = wx.ListCtrl(p, style=wx.LC_REPORT | wx.LC_NO_HEADER, size=p.FromDIP(wx.Size(300, 150)), pos=(10, 10))
lc.InsertColumn(0, "x"); [lc.Append((t,)) for t in ["General", "Speech", "Braille"]]
lb = wx.ListBox(p, choices=["alpha", "beta", "gamma"], size=p.FromDIP(wx.Size(300, 150)), pos=p.FromDIP(wx.Point(330, 10)))
f.Show()

def report(tag):
    print(f"[{tag}] listctrl fg={lc.GetForegroundColour().GetAsString(wx.C2S_HTML_SYNTAX)} use={lc.UseForegroundColour()} LVM_GETTEXTCOLOR=0x{u.SendMessageW(lc.GetHandle(), LVM_GETTEXTCOLOR, 0, 0) & 0xFFFFFFFF:06X} bk=0x{u.SendMessageW(lc.GetHandle(), LVM_GETBKCOLOR, 0, 0) & 0xFFFFFFFF:06X}  pixels={textColour(lc)}")
    print(f"[{tag}] listbox  fg={lb.GetForegroundColour().GetAsString(wx.C2S_HTML_SYNTAX)} use={lb.UseForegroundColour()} pixels={textColour(lb)}")

def step1():
    report("after show")
    if mode == "engine":
        u.SendMessageW(lc.GetHandle(), LVM_SETTEXTCOLOR, 0, 0x00FFFFFF); lc.Refresh(); lb.Refresh()
        wx.CallLater(400, lambda: (report("after raw LVM_SETTEXTCOLOR white"), step2()))
    else:
        finish()

def step2():
    lb.SetForegroundColour(wx.WHITE); lb.Refresh()
    wx.CallLater(400, lambda: (report("after listbox SetForegroundColour(white)"), step3()))

def step3():
    theming._setWindowTheme(lb.GetHandle(), None); lb.Refresh()
    wx.CallLater(400, lambda: (report("after listbox theme reset to default"), finish()))

def finish():
    f.Destroy(); app.ExitMainLoop()

wx.CallLater(800, step1)
app.MainLoop()
