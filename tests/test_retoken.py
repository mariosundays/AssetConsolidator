"""retoken_paths() rewriting real parameter values."""
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
os.environ["HIP"]=ROOT
os.environ["JOB"]="F:/proj"

class Node:
    def __init__(s,p): s._p=p
    def path(s): return s._p
class Parm:
    def __init__(s,node,name,raw,resolved):
        s._n=Node(node); s._name=name; s.value=raw; s._resolved=resolved
    def node(s): return s._n
    def name(s): return s._name
    def unexpandedString(s): return s.value
    def eval(s): return s._resolved
    def keyframes(s): return ()
    def set(s,v): s.value=v
    def parmTemplate(s): return None

# Patch the scene walk to return our fake parms.
PARMS=[]
ac._iter_file_parms = lambda: iter(PARMS)

PARMS[:] = [
    Parm("/obj/a","map","$JOB/tex/wood.exr",      ROOT+"/tex/wood.exr"),
    Parm("/obj/b","map",ROOT+"/tex/metal.exr",    ROOT+"/tex/metal.exr"),
    Parm("/obj/c","file","$HIP/geo/cache.bgeo.sc",ROOT+"/geo/cache.bgeo.sc"),
    Parm("/obj/d","map","E:/lib/outside.exr",     "E:/lib/outside.exr"),
]

print("=== leading_var ===")
for raw, want in [("$HIP/tex/a.exr","$HIP"), ("$JOB/tex/a.exr","$JOB"),
                  ("${HIP}/tex/a.exr","$HIP"), ("$hip/a.exr","$HIP"),
                  ("F:/proj/tex/a.exr",""), ("tex/a.exr",""),
                  ("",""), ("$HIP","$HIP")]:
    check(repr(raw), ac.leading_var(raw), want)

print("\n=== find_internal skips hard-coded absolute paths ===")
internal = ac.find_internal(ROOT)
check("only the 2 relative ones", len(internal), 2)
check("no absolute path included",
      any(e[1].startswith("F:/") for e in internal), False)

print("\n=== rewrite only touches already-relative paths ===")
changed, skipped, errors = ac.retoken_paths(ROOT, "$HIP")
check("no errors", errors, [])
check("$JOB path rewritten", PARMS[0].value, "$HIP/tex/wood.exr")
check("ABSOLUTE path left alone", PARMS[1].value, ROOT+"/tex/metal.exr")
check("already $HIP left alone", PARMS[2].value, "$HIP/geo/cache.bgeo.sc")
check("outside project untouched", PARMS[3].value, "E:/lib/outside.exr")
check("changed count", changed, 1)
check("skipped count", skipped, 1)

print("\n=== idempotent: running again changes nothing ===")
changed2, skipped2, _ = ac.retoken_paths(ROOT, "$HIP")
check("second run changes 0", changed2, 0)
check("second run skips 2", skipped2, 2)

print("\n=== sequences keep their frame token ===")
os.environ["HIP"]=ROOT
PARMS[:] = [Parm("/obj/s","map","$JOB/tex/smoke.$F4.exr",
                 ROOT+"/tex/smoke.0001.exr")]
ac.retoken_paths(ROOT, "$HIP")
check("frame token preserved", PARMS[0].value, "$HIP/tex/smoke.$F4.exr")

print("\n=== switching to a custom var ===")
os.environ["SHOW"]=ROOT
PARMS[:] = [Parm("/obj/a","map","$HIP/tex/a.exr", ROOT+"/tex/a.exr")]
ac.retoken_paths(ROOT, "$SHOW")
check("rewritten to $SHOW", PARMS[0].value, "$SHOW/tex/a.exr")

print("\n=== a scene of only absolute paths is left entirely alone ===")
PARMS[:] = [Parm("/obj/a","map",ROOT+"/tex/a.exr", ROOT+"/tex/a.exr"),
            Parm("/obj/b","map",ROOT+"/tex/b.exr", ROOT+"/tex/b.exr")]
os.environ["HIP"]=ROOT
changed4, skipped4, errors4 = ac.retoken_paths(ROOT, "$HIP")
check("nothing changed", changed4, 0)
check("first still absolute", PARMS[0].value, ROOT+"/tex/a.exr")
check("second still absolute", PARMS[1].value, ROOT+"/tex/b.exr")

print("\n=== locked parm reported, not silently skipped ===")
class Locked(Parm):
    def set(s,v): raise ac.hou.PermissionError("locked")
PARMS[:] = [Locked("/obj/x","map","$JOB/tex/a.exr", ROOT+"/tex/a.exr")]
changed3, _, errors3 = ac.retoken_paths(ROOT, "$HIP")
check("locked not counted", changed3, 0)
check("locked reported", len(errors3), 1)

print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
