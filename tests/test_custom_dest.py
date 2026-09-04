"""Custom per-reference destination folders."""
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


ROOT = "F:/proj/shot01"
os.environ["HIP"] = ROOT
os.environ["JOB"] = ROOT


class P:
    def node(self):
        return None

    def name(self):
        return "map"


def make(path, raw=None):
    return ac.Reference(P(), raw or path, path, ROOT)


print("=== default routing is unchanged ===")
r = make("E:/lib/wood.exr")
check("default dest_dir", r.dest_dir, ROOT + "/tex")
check("default dest", r.dest, ROOT + "/tex/wood.exr")
check("default relative", r.dest_relative(), "$HIP/tex/wood.exr")
check("not custom", r.is_custom, False)

print("\n=== a custom folder inside the project keeps the variable ===")
r = make("E:/lib/wood.exr")
r.custom_dir = ROOT + "/textures/wood"
check("dest_dir follows", r.dest_dir, ROOT + "/textures/wood")
check("dest follows", r.dest, ROOT + "/textures/wood/wood.exr")
check("is custom", r.is_custom, True)
check("inside project", r.dest_inside_project, True)
check("still uses $HIP", r.dest_relative(), "$HIP/textures/wood/wood.exr")

print("\n=== custom folder AT the root needs no subfolder ===")
r = make("E:/lib/wood.exr")
r.custom_dir = ROOT
check("no double slash", r.dest_relative(), "$HIP/wood.exr")

print("\n=== a custom folder outside the project goes absolute ===")
r = make("E:/lib/wood.exr")
r.custom_dir = "D:/fast_cache/textures"
check("outside detected", r.dest_inside_project, False)
check("absolute path written", r.dest_relative(),
      "D:/fast_cache/textures/wood.exr")
check("dest is the custom folder", r.dest, "D:/fast_cache/textures/wood.exr")

print("\n=== sequences keep their frame token in a custom folder ===")
r = make("E:/lib/smoke.0001.exr", raw="E:/lib/smoke.$F4.exr")
r.custom_dir = ROOT + "/seq"
check("token preserved", r.dest_relative(), "$HIP/seq/smoke.$F4.exr")
r.custom_dir = "D:/elsewhere"
check("token preserved when absolute", r.dest_relative(),
      "D:/elsewhere/smoke.$F4.exr")

print("\n=== clearing the override restores type routing ===")
r = make("E:/lib/wood.exr")
r.custom_dir = "D:/somewhere"
r.custom_dir = ""
check("back to default", r.dest_relative(), "$HIP/tex/wood.exr")
check("not custom again", r.is_custom, False)

print("\n=== the dest setter (used for collision renames) ===")
r = make("E:/lib/wood.exr")
r.dest = ROOT + "/tex/wood_1.exr"
check("name updated", r.dest_name, "wood_1.exr")
check("dest reads back", r.dest, ROOT + "/tex/wood_1.exr")
check("relative uses new name", r.dest_relative(), "$HIP/tex/wood_1.exr")

print("\n=== the variable choice still applies to custom folders ===")
os.environ["SHOW"] = ROOT
r = make("E:/lib/wood.exr")
r.prefer_var = "$SHOW"
r.custom_dir = ROOT + "/textures"
check("custom honours $SHOW", r.dest_relative(), "$SHOW/textures/wood.exr")

print("\n=== end to end: copy into a custom folder ===")
base = tempfile.mkdtemp()
try:
    root = os.path.join(base, "proj").replace("\\", "/")
    ext = os.path.join(base, "ext").replace("\\", "/")
    custom = os.path.join(base, "proj", "custom_tex").replace("\\", "/")
    os.makedirs(root)
    os.makedirs(ext)
    os.environ["HIP"] = root

    src = os.path.join(ext, "wood.exr").replace("\\", "/")
    open(src, "w").write("TEXDATA")

    class RealParm(P):
        def __init__(self):
            self.value = src

        def set(self, v):
            self.value = v

        def node(self):
            class N:
                def path(self_inner):
                    return "/obj/geo1"
            return N()

    parm = RealParm()
    ref = ac.Reference(parm, src, src, root)
    ref.custom_dir = custom

    copied, skipped, errors = ac.consolidate([ref], repoint=True)
    check("copied", copied, 1)
    check("no errors", errors, [])
    check("landed in custom folder",
          os.path.isfile(os.path.join(custom, "wood.exr")), True)
    check("content intact",
          open(os.path.join(custom, "wood.exr")).read(), "TEXDATA")
    check("parm repointed to $HIP", parm.value, "$HIP/custom_tex/wood.exr")
finally:
    shutil.rmtree(base, ignore_errors=True)

print("\n" + ("ALL PASS" if not fails
              else f"{len(fails)} FAILURES:\n" + "\n".join(fails)))
sys.exit(1 if fails else 0)
