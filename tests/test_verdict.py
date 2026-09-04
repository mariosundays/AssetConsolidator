"""Verdict logic against representative production paths."""
import sys, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac
fails=[]
def check(l,g,w):
    ok=g==w
    if not ok: fails.append(f"{l}: got {g!r} want {w!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {l}: {g!r}")

ROOT = "F:/FutureDeluxe Dropbox/FD-ALL/MIC2657_WEB_EXP/DESIGN/MarioD/HD"

print("=== representative production paths ===")
cases = [
 # (path, exists, expect_recommend, expect_location)
 ("E:/_1LIBRARY_/_HDRIs_/GSG_Pro Studios Metal/GSG_PRO_STUDIOS_METAL_037_sm.exr",
  True, True, ac.PICK_OTHER_DRIVE),
 ("E:/_1LIBRARY_/_Bokehs_/GSG_Simulated/GSG_Bokeh_Simulated_04_CA2.jpg",
  True, True, ac.PICK_OTHER_DRIVE),
 ("F:/FD-ALL/MIC2657_WEB_EXP/ASSETS/Common/_tex/tex/normalTex.png",
  True, True, ac.PICK_LIBRARY),   # same drive, /assets/ -> library
 ("F:/FutureDeluxe Dropbox/FD-ALL/MIC2657_WEB_EXP/REVIEWS/Internal/x.jpg",
  True, True, ac.PICK_OUTSIDE),
 # A path that is genuinely absent is missing...
 ("F:/FD-ALL/MIC2657_WEB_EXP/ASSETS/Common/Houdini_Product_Master/gone/geo",
  False, False, ac.PICK_MISSING),
 ("C:/Users/artist/AppData/Local/Temp/grab.exr", True, True, ac.PICK_VOLATILE),
 ("C:/Users/artist/Downloads/hdri.exr", True, True, ac.PICK_VOLATILE),
 ("//nas/projects/shared/x.exr", True, True, ac.PICK_NETWORK),
]
for path, exists, want_rec, want_location in cases:
    rec, location = ac.verdict(path, ROOT, exists)
    label = path[:52]
    check(label+" [rec]", rec, want_rec)
    check(label+" [location]", location, want_location)

print("\n=== every reason has a colour and help text ===")
for r in [ac.PICK_MISSING, ac.PICK_VOLATILE, ac.PICK_NETWORK,
          ac.PICK_OTHER_DRIVE, ac.PICK_LIBRARY, ac.PICK_OUTSIDE]:
    check(f"colour {r}", r in ac.PICK_COLOURS, True)
    check(f"help {r}", r in ac.LOCATION_HELP, True)

print("\n=== missing never recommended, regardless of location ===")
for path in ["E:/lib/a.exr","//nas/x.exr","C:/temp/y.exr",ROOT+"/z.exr"]:
    rec,location = ac.verdict(path, ROOT, False)
    check(f"missing {path[:20]}", (rec,location), (False, ac.PICK_MISSING))

print("\n=== volatile beats drive check (temp on same drive) ===")
rec,location = ac.verdict("F:/temp/scratch.exr", ROOT, True)
check("same-drive temp -> volatile", location, ac.PICK_VOLATILE)

print("\n=== selected defaults to recommend ===")
class P:
    def node(s): return None
    def name(s): return "map"
r = ac.Reference(P(), "E:/lib/a.exr", "E:/lib/a.exr", ROOT)
check("missing file not pre-ticked", r.selected, False)
check("location recorded", r.location, ac.PICK_MISSING)  # file does not exist

print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
