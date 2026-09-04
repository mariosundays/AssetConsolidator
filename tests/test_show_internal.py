"""
Listing files that are already inside the project, and the case where a
variable path resolves outside the root.

The reported bug: a scene showing $JOB/tex/x.jpg parameters, while "Update
paths in scene" reported "All 79 relative path(s) already use $HIP". The $JOB
paths resolved to a folder ABOVE the project root, so find_internal() never
saw them and the message counted only what was inside.
"""
import os
import shutil
import sys
import tempfile

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got!r}")


# Real folders on disk: verdict() distinguishes present from missing, so a
# fictional path would come back as "missing" and hide what we are testing.
# Layout mirrors the report: $JOB sits two levels above the scene.
BASE = tempfile.mkdtemp()
JOB = os.path.join(BASE, "HD").replace("\\", "/")
ROOT = os.path.join(JOB, "MIC2657", "MIC2657_performance").replace("\\", "/")
os.makedirs(os.path.join(ROOT, "tex"))
os.makedirs(os.path.join(JOB, "tex"))
open(os.path.join(ROOT, "tex", "in_project.exr"), "w").write("A")
open(os.path.join(JOB, "tex", "GSG_Gobos.jpg"), "w").write("B")
EXT = os.path.join(BASE, "lib").replace("\\", "/")
os.makedirs(EXT)
open(os.path.join(EXT, "hdri.exr"), "w").write("C")

os.environ["HIP"] = ROOT
os.environ["JOB"] = JOB


class Node:
    def __init__(self, p):
        self._p = p

    def path(self):
        return self._p


class Parm:
    def __init__(self, node, name, raw, resolved):
        self._n = Node(node)
        self._name = name
        self.value = raw
        self._resolved = resolved

    def node(self):
        return self._n

    def name(self):
        return self._name

    def unexpandedString(self):
        return self.value

    def eval(self):
        return self._resolved

    def keyframes(self):
        return ()

    def set(self, v):
        self.value = v

    def parmTemplate(self):
        return None


PARMS = []
ac._iter_file_parms = lambda: iter(PARMS)

PARMS[:] = [
    # inside the root, already $HIP
    Parm("/obj/a", "map", "$HIP/tex/in_project.exr",
         ROOT + "/tex/in_project.exr"),
    # the reported case: $JOB resolves ABOVE the root
    Parm("/obj/rslight3", "map", "$JOB/tex/GSG_Gobos.jpg",
         JOB + "/tex/GSG_Gobos.jpg"),
    # plainly external
    Parm("/obj/c", "map", EXT + "/hdri.exr", EXT + "/hdri.exr"),
]

print("=== the $JOB path is NOT internal: it resolves above the root ===")
internal = ac.find_internal(ROOT)
check("only the $HIP one is internal", len(internal), 1)
check("and it is the $HIP parm", internal[0][1], "$HIP/tex/in_project.exr")

print("\n=== external_var_paths() finds the ones the message missed ===")
outside = ac.external_var_paths(ROOT)
check("one variable path points outside", len(outside), 1)
check("it is the $JOB one", outside[0][1], "$JOB/tex/GSG_Gobos.jpg")
check("a bare external path is not counted",
      any("/lib/" in e[2] for e in outside), False)

print("\n=== retoken still refuses to touch it ===")
changed, skipped, errors = ac.retoken_paths(ROOT, "$HIP")
check("the $JOB parm is untouched", PARMS[1].value, "$JOB/tex/GSG_Gobos.jpg")
check("the internal one was already correct", skipped, 1)
check("nothing changed", changed, 0)

print("\n=== scan(): internal files hidden by default ===")
refs = ac.scan(ROOT)
paths = sorted(r.resolved for r in refs)
check("two external references", len(refs), 2)
check("in-project file excluded",
      any("in_project" in p for p in paths), False)
check("the $JOB file IS listed as external",
      any("GSG_Gobos" in p for p in paths), True)

print("\n=== scan(include_internal=True): everything is listed ===")
refs = ac.scan(ROOT, include_internal=True)
check("all three listed", len(refs), 3)

by_location = {}
for r in refs:
    by_location.setdefault(r.location, []).append(r)
check("one is 'in project'", len(by_location.get(ac.PICK_INSIDE, [])), 1)

inside_ref = by_location[ac.PICK_INSIDE][0]
check("in-project file is never recommended", inside_ref.recommend, False)
check("and never pre-ticked", inside_ref.selected, False)

print("\n=== in-project entries have help text and a colour ===")
check("has a colour", ac.PICK_INSIDE in ac.PICK_COLOURS, True)
check("has help text", ac.PICK_INSIDE in ac.LOCATION_HELP, True)

print("\n=== the external ones are still recommended ===")
externals = [r for r in refs if r.location != ac.PICK_INSIDE]
check("both externals recommended",
      all(r.recommend for r in externals), True)

print("\n" + ("ALL PASS" if not fails
              else f"{len(fails)} FAILURES:\n" + "\n".join(fails)))
sys.exit(1 if fails else 0)
