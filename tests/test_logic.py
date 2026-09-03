"""Test the non-Houdini logic of asset_consolidator by stubbing hou + Qt."""
import sys, os, types, tempfile, shutil

# --- stub hou ---
hou = types.ModuleType("hou")
hou.getenv = lambda k: os.environ.get(k)
class _PT: pass
hou.StringParmTemplate = _PT
hou.stringParmType = types.SimpleNamespace(FileReference="fileref")
hou.OperationFailed = Exception
hou.PermissionError = Exception
hou.InterruptableOperation = object
hou.node = lambda p: None
hou.hipFile = types.SimpleNamespace(path=lambda: "x.hip")
hou.ui = types.SimpleNamespace()
hou.undos = types.SimpleNamespace()
hou.severityType = types.SimpleNamespace(Warning=1)
hou.qt = types.SimpleNamespace(mainWindow=lambda: None)
hou.paneTabType = types.SimpleNamespace(NetworkEditor=1)
sys.modules["hou"] = hou

# --- stub PySide6 ---
for name in ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]:
    m = types.ModuleType(name); sys.modules[name] = m
class _Any:
    """Stub that is usable as a value AND as a base class."""
    def __init__(self,*a,**k): pass
    def __getattr__(self,n): return _Any()
    def __call__(self,*a,**k): return _Any()
    def __mro_entries__(self, bases): return (_Base,)

class _Base:
    def __init__(self,*a,**k): pass
    def __getattr__(self,n): return _Any()
sys.modules["PySide6.QtCore"].Qt = _Any()
sys.modules["PySide6.QtCore"].__getattr__ = lambda n: _Any()
for mod in ["PySide6.QtCore","PySide6.QtGui","PySide6.QtWidgets"]:
    sys.modules[mod].__class__ = type("M",(types.ModuleType,),
        {"__getattr__": lambda s,n: _Any()})
sys.modules["PySide6"].QtCore = sys.modules["PySide6.QtCore"]
sys.modules["PySide6"].QtGui = sys.modules["PySide6.QtGui"]
sys.modules["PySide6"].QtWidgets = sys.modules["PySide6.QtWidgets"]

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "python"))
import asset_consolidator as ac

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got!r}")

print("=== classify ===")
check("exr -> tex", ac.classify("/x/a.exr"), "tex")
check("EXR upper", ac.classify("/x/A.EXR"), "tex")
check("bgeo.sc -> geo", ac.classify("/x/c.bgeo.sc"), "geo")
check("abc -> abc", ac.classify("/x/c.abc"), "abc")
check("vdb -> geo", ac.classify("/x/c.vdb"), "geo")
check("rat -> tex", ac.classify("/x/t.rat"), "tex")
check("unknown -> misc", ac.classify("/x/n.xyz"), "misc")
check("no ext -> misc", ac.classify("/x/noext"), "misc")

print("\n=== is_inside ===")
root = "C:/proj/shot01"
check("inside", ac.is_inside("C:/proj/shot01/tex/a.exr", root), True)
check("inside nested", ac.is_inside("C:/proj/shot01/a/b/c.exr", root), True)
check("outside sibling", ac.is_inside("C:/proj/shot02/a.exr", root), False)
check("outside other drive", ac.is_inside("D:/lib/a.exr", root), False)
check("case-insensitive", ac.is_inside("c:/PROJ/Shot01/a.exr", root), True)
# the classic prefix trap: shot01_old must NOT count as inside shot01
check("prefix trap shot01_old", ac.is_inside("C:/proj/shot01_old/a.exr", root), False)
check("empty root", ac.is_inside("C:/a.exr", ""), False)

print("\n=== is_sequence ===")
check("$F4", ac.is_sequence("/x/a.$F4.exr"), True)
check("$F", ac.is_sequence("/x/a.$F.exr"), True)
check("%04d", ac.is_sequence("/x/a.%04d.exr"), True)
check("####", ac.is_sequence("/x/a.####.exr"), True)
check("<UDIM>", ac.is_sequence("/x/a.<UDIM>.exr"), True)
check("plain", ac.is_sequence("/x/a.exr"), False)

print("\n=== sequence_glob on real files ===")
tmp = tempfile.mkdtemp()
try:
    for i in range(1, 6):
        open(os.path.join(tmp, f"render.{i:04d}.exr"), "w").write("x"*10)
    open(os.path.join(tmp, "other.exr"), "w").write("y")
    found = ac.sequence_glob(f"{tmp}/render.$F4.exr".replace("\\","/"))
    check("glob finds 5 frames", len(found), 5)
    found2 = ac.sequence_glob(f"{tmp}/render.%04d.exr".replace("\\","/"))
    check("glob %04d finds 5", len(found2), 5)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n=== _human ===")
check("bytes", ac._human(512), "512 B")
check("kb", ac._human(2048), "2.0 KB")
check("mb", ac._human(5*1024*1024), "5.0 MB")

print("\n=== _unique_dest / _same_file ===")
tmp2 = tempfile.mkdtemp()
try:
    p = os.path.join(tmp2, "a.exr")
    open(p,"w").write("data")
    u = ac._unique_dest(p)
    check("unique adds suffix", os.path.basename(u), "a_1.exr")
    check("unique passthrough", os.path.basename(ac._unique_dest(os.path.join(tmp2,"zz.exr"))), "zz.exr")
    q = os.path.join(tmp2,"b.exr")
    shutil.copy2(p,q)
    check("same_file copy2", ac._same_file(p,q), True)
    open(os.path.join(tmp2,"c.exr"),"w").write("different length")
    check("same_file differs", ac._same_file(p, os.path.join(tmp2,"c.exr")), False)
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n" + "\n".join(fails)))
sys.exit(1 if fails else 0)
