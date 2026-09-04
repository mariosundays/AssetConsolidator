"""
Keyframed file parameters.

hou.Parm.unexpandedString() RAISES on a keyframed parameter --
"Cannot get unexpanded string for parms with keyframes" -- rather than
returning a value. Calling it before testing for keyframes meant the
exception handler swallowed the parameter entirely, so a keyframed file path
was invisible to the whole tool rather than deliberately skipped.

Observed live in Houdini 21.0.512 while querying an RSLight.
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


BASE = tempfile.mkdtemp()
ROOT = os.path.join(BASE, "proj").replace("\\", "/")
EXT = os.path.join(BASE, "lib").replace("\\", "/")
os.makedirs(ROOT)
os.makedirs(EXT)
open(os.path.join(EXT, "plain.exr"), "w").write("A")
open(os.path.join(EXT, "animated.exr"), "w").write("B")
os.environ["HIP"] = ROOT
os.environ["JOB"] = ROOT


class Node:
    def __init__(self, p):
        self._p = p

    def path(self):
        return self._p


class Parm:
    """A normal file parameter."""

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


class KeyframedParm(Parm):
    """Behaves the way Houdini really does on a keyframed parm."""

    def unexpandedString(self):
        raise ac.hou.OperationFailed(
            "Cannot get unexpanded string for parms with keyframes")

    def keyframes(self):
        return ("<keyframe>",)


PARMS = []
ac._iter_file_parms = lambda: iter(PARMS)

plain = Parm("/obj/a", "map", EXT + "/plain.exr", EXT + "/plain.exr")
animated = KeyframedParm("/obj/b", "map", EXT + "/animated.exr",
                         EXT + "/animated.exr")
PARMS[:] = [plain, animated]

print("=== raw_value() ===")
check("plain parm returns its value", ac.raw_value(plain), EXT + "/plain.exr")
check("keyframed parm returns None", ac.raw_value(animated), None)

print("\n=== the keyframe test runs BEFORE unexpandedString ===")
# If the order were wrong this raises out of raw_value instead of returning.
try:
    ac.raw_value(animated)
    print("PASS  no exception escaped raw_value")
except Exception as exc:
    fails.append(f"exception escaped: {exc}")
    print("FAIL  exception escaped:", exc)

print("\n=== scan() skips the keyframed one, keeps the plain one ===")
refs = ac.scan(ROOT)
paths = [os.path.basename(r.resolved) for r in refs]
check("one reference found", len(refs), 1)
check("the plain file is it", paths, ["plain.exr"])

print("\n=== find_internal() and external_var_paths() do not choke ===")
PARMS[:] = [
    Parm("/obj/c", "map", "$HIP/tex/inside.exr", ROOT + "/tex/inside.exr"),
    animated,
]
try:
    internal = ac.find_internal(ROOT)
    print("PASS  find_internal survived a keyframed parm")
    check("it found the one real internal path", len(internal), 1)
except Exception as exc:
    fails.append(f"find_internal raised: {exc}")
    print("FAIL  find_internal raised:", exc)

try:
    outside = ac.external_var_paths(ROOT)
    print("PASS  external_var_paths survived a keyframed parm")
    check("no variable paths point outside here", len(outside), 0)
except Exception as exc:
    fails.append(f"external_var_paths raised: {exc}")
    print("FAIL  external_var_paths raised:", exc)

print("\n=== a keyframed parm is never rewritten ===")
PARMS[:] = [animated]
changed, skipped, errors = ac.retoken_paths(ROOT, "$HIP")
check("nothing changed", changed, 0)
check("its value is untouched", animated.value, EXT + "/animated.exr")

shutil.rmtree(BASE, ignore_errors=True)

print("\n" + ("ALL PASS" if not fails
              else f"{len(fails)} FAILURES:\n" + "\n".join(fails)))
sys.exit(1 if fails else 0)
