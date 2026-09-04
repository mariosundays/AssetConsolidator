"""Variable selection, token choice, and the retoken rewrite."""
import sys, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac
fails=[]
def check(l,g,w):
    ok=g==w
    if not ok: fails.append(f"{l}: got {g!r} want {w!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {l}: {g!r}")

ROOT="F:/proj/shot01"

print("=== normalise_var ===")
for raw,want in [("HIP","$HIP"),("$HIP","$HIP"),("${HIP}","$HIP"),
                 ("hip","$HIP"),("  $job  ","$JOB"),("","")]:
    check(repr(raw), ac.normalise_var(raw), want)

print("\n=== HIP is now the default root ===")
os.environ["HIP"]=ROOT; os.environ["JOB"]="F:/proj"
check("project_root is HIP", ac.project_root(), ROOT)
# even when the hip sits under a real JOB (the case that used to pick JOB)
check("token defaults to $HIP", ac.root_token(ROOT), "$HIP")

print("\n=== explicit preference wins ===")
os.environ["HIP"]=ROOT; os.environ["JOB"]=ROOT   # both point at root
check("prefer $JOB honoured", ac.root_token(ROOT,"$JOB"), "$JOB")
check("prefer $HIP honoured", ac.root_token(ROOT,"$HIP"), "$HIP")

print("\n=== an unusable preference is refused, not written ===")
os.environ["HIP"]=ROOT; os.environ["JOB"]="F:/somewhere/else"
check("JOB not at root -> falls back", ac.root_token(ROOT,"$JOB"), "$HIP")
os.environ.pop("NOPE",None)
check("unset var -> falls back", ac.root_token(ROOT,"$NOPE"), "$HIP")

print("\n=== no variable matches -> absolute path ===")
os.environ["HIP"]="C:/other"; os.environ["JOB"]="C:/other2"
check("absolute fallback", ac.root_token(ROOT,"$HIP"), ROOT)

print("\n=== var_is_usable ===")
os.environ["HIP"]=ROOT
check("HIP usable", ac.var_is_usable("$HIP",ROOT), True)
check("unset unusable", ac.var_is_usable("$NOTSET",ROOT), False)
check("case tolerant", ac.var_is_usable("hip",ROOT), True)

print("\n=== custom studio variable ===")
os.environ["SHOW"]=ROOT
check("$SHOW usable", ac.var_is_usable("$SHOW",ROOT), True)
check("$SHOW chosen when preferred", ac.root_token(ROOT,"$SHOW"), "$SHOW")

print("\n=== dest_relative uses the preferred var ===")
class P:
    def node(s): return None
    def name(s): return "map"
os.environ["HIP"]=ROOT; os.environ["JOB"]=ROOT
r = ac.Reference(P(), ROOT+"/tex/a.exr", ROOT+"/tex/a.exr", ROOT, "$JOB")
check("uses $JOB when asked", r.dest_relative(), "$JOB/tex/a.exr")
r2 = ac.Reference(P(), ROOT+"/tex/a.exr", ROOT+"/tex/a.exr", ROOT, "$HIP")
check("uses $HIP when asked", r2.dest_relative(), "$HIP/tex/a.exr")
r3 = ac.Reference(P(), ROOT+"/tex/a.exr", ROOT+"/tex/a.exr", ROOT)
check("defaults to $HIP", r3.dest_relative(), "$HIP/tex/a.exr")

print("\n=== retoken refuses a variable that does not resolve to root ===")
os.environ["JOB"]="F:/elsewhere"
changed,skipped,errors = ac.retoken_paths(ROOT, "$JOB")
check("nothing changed", changed, 0)
check("error explains why", len(errors), 1)

print("\n=== real case: $JOB is an ANCESTOR of the project root ===")
REAL_ROOT = "F:/FD/DESIGN/MarioD/HD/MIC2657/MIC2657_performance"
REAL_JOB = "F:/FD/DESIGN/MarioD/HD"
os.environ["HIP"] = REAL_ROOT
os.environ["JOB"] = REAL_JOB
check("$JOB not usable (points higher up)",
      ac.var_is_usable("$JOB", REAL_ROOT), False)
check("choosing $JOB still yields $HIP",
      ac.root_token(REAL_ROOT, "$JOB"), "$HIP")
check("$JOB usable once the root matches it",
      ac.var_is_usable("$JOB", REAL_JOB), True)
check("and then $JOB is written",
      ac.root_token(REAL_JOB, "$JOB"), "$JOB")

print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
