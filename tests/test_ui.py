"""Test drive colouring + context-menu grouping logic."""
import sys, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac

fails=[]
def check(label, got, want):
    ok=got==want
    if not ok: fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got!r}")

print("=== drive_of on Mario's real paths ===")
real = {
 "F:/FutureDeluxe Dropbox/FD-ALL/MIC2657_WEB_EXP/ASSETS/Common/_tex/normalTex.png":"F:",
 "E:/_1LIBRARY_/_HDRIs_/Area Lights HDRI/Misc/Grad_Horizontal_01.exr":"E:",
 "E:/_1LIBRARY_/_Bokehs_/GSG_Simulated/x.jpg":"E:",
 "C:/temp/x.exr":"C:",
 "//nas/proj/x.exr":"//nas/proj",
}
for path, want in real.items():
    check(os.path.basename(path)[:22], ac.drive_of(path), want)

print("\n=== stable drive->colour mapping ===")
class FakeDlg:
    def __init__(self): self._drive_map={}
    _drive_colour = ac.ConsolidatorDialog._drive_colour
d = FakeDlg()
c_f1 = d._drive_colour("F:")
c_e1 = d._drive_colour("E:")
c_f2 = d._drive_colour("F:")
check("F: stable across calls", c_f1, c_f2)
check("E: differs from F:", c_e1 != c_f1, True)
check("first colour is palette[0]", c_f1, ac.DRIVE_COLOURS[0])
check("second colour is palette[1]", c_e1, ac.DRIVE_COLOURS[1])
# exhaust palette -> must wrap, never crash
for i in range(20): d._drive_colour(f"X{i}:")
check("no crash past palette end", len(d._drive_map), 22)
check("all colours valid hex", all(v in ac.DRIVE_COLOURS for v in d._drive_map.values()), True)

print("\n=== type colours cover every routing target ===")
for folder in ["tex","geo","abc","misc"]:
    check(f"{folder} has colour", folder in ac.TYPE_COLOURS, True)
targets = set()
for _f,exts in ac.TYPE_FOLDERS: targets.add(_f)
targets.add(ac.MISC_FOLDER)
check("no routing target unpainted", targets - set(ac.TYPE_COLOURS), set())

print("\n=== context-menu grouping predicates ===")
class R:
    def __init__(s,p,sub): s.resolved=p; s.subfolder=sub
refs=[R("E:/lib/a.exr","tex"), R("E:/lib/b.exr","tex"),
      R("F:/proj/c.abc","abc"), R("E:/other/d.bgeo.sc","geo")]
same_drive=[i for i,r in enumerate(refs) if ac.drive_of(r.resolved)=="E:"]
check("select-by-drive E:", same_drive, [0,1,3])
same_type=[i for i,r in enumerate(refs) if r.subfolder=="tex"]
check("select-by-type tex", same_type, [0,1])
folder=os.path.dirname("E:/lib/a.exr")
same_folder=[i for i,r in enumerate(refs) if os.path.dirname(r.resolved)==folder]
check("select-by-folder E:/lib", same_folder, [0,1])

print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
