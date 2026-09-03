"""Test extension column, root token, and isolate semantics."""
import sys, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac
fails=[]
def check(l,g,w):
    ok=g==w
    if not ok: fails.append(f"{l}: got {g!r} want {w!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {l}: {g!r}")

print("=== ext_label ===")
for path,want in [("/x/a.exr","EXR"),("/x/a.EXR","EXR"),("/x/b.jpg","JPG"),
                  ("/x/c.bgeo.sc","BGEO.SC"),("/x/d.abc","ABC"),
                  ("/x/e.vdb","VDB"),("/x/f.tif","TIF"),("/x/noext","-"),
                  ("/x/g.USDA","USDA")]:
    check(path.split('/')[-1], ac.ext_label(path), want)

print("\n=== property resolves to module fn (not recursion) ===")
class R:
    resolved="/x/shot.exr"
    ext_label = ac.Reference.ext_label
check("property works", R().ext_label, "EXR")

print("\n=== ext colours ===")
check("exr coloured", ac.ext_colour("EXR") != ac.DEFAULT_EXT_COLOUR, True)
check("jpg differs from exr", ac.ext_colour("JPG") != ac.ext_colour("EXR"), True)
check("unknown -> default", ac.ext_colour("XYZ"), ac.DEFAULT_EXT_COLOUR)
check("empty -> default", ac.ext_colour(""), ac.DEFAULT_EXT_COLOUR)
check("case insensitive", ac.ext_colour("exr"), ac.ext_colour("EXR"))

print("\n=== root_token ===")
os.environ["HIP"]="C:/proj/shot01"; os.environ["JOB"]="C:/proj"
check("root==HIP -> $HIP", ac.root_token("C:/proj/shot01"), "$HIP")
check("root==JOB -> $JOB", ac.root_token("C:/proj"), "$JOB")
check("other -> absolute", ac.root_token("D:/elsewhere"), "D:/elsewhere")
check("empty -> empty", ac.root_token(""), "")

print("\n=== project_root prefers HIP ===")
# JOB set but hip NOT under it -> HIP wins
os.environ["HIP"]="C:/proj/shot01"; os.environ["JOB"]="D:/unrelated"
check("hip not under job -> HIP", ac.project_root(), "C:/proj/shot01")

print("\n=== isolate semantics ===")
class Row:
    def __init__(s,st): s.setState=st
class FakeItem:
    def __init__(s): s.state=None
    def setCheckState(s,v): s.state=v
class FakeTable:
    def __init__(s,n): s.items={(r,0):FakeItem() for r in range(n)}
    def blockSignals(s,b): pass
    def item(s,r,c): return s.items[(r,0)]
class Ref2:
    def __init__(s,e=True): s.exists=e; s.selected=True
class Dlg:
    _isolate_rows = ac.ConsolidatorDialog._isolate_rows
    def __init__(s,refs): s.refs=refs; s.table=FakeTable(len(refs))
    def _update_status(s): pass

refs=[Ref2() for _ in range(5)]
d=Dlg(refs)
d._isolate_rows([2])
check("only row 2 selected", [r.selected for r in refs], [False,False,True,False,False])

# isolating a missing row selects nothing
refs2=[Ref2(), Ref2(e=False), Ref2()]
for r in refs2: r.selected=True
d2=Dlg(refs2); d2._isolate_rows([1])
check("missing row cannot isolate", [r.selected for r in refs2], [False,False,False])

# multi-row isolate
refs3=[Ref2() for _ in range(4)]
d3=Dlg(refs3); d3._isolate_rows([0,3])
check("rows 0+3 only", [r.selected for r in refs3], [True,False,False,True])

print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
