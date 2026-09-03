"""End-to-end test of consolidate() with fake parms and real files."""
import sys, os, tempfile, shutil
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "test_logic.py")).read().split('fails = []')[0])  # reuse stubs
import asset_consolidator as ac

fails=[]
def check(label, got, want):
    ok = got==want
    if not ok: fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got!r}")

class FakeNode:
    def __init__(self,p): self._p=p
    def path(self): return self._p
class FakeParm:
    def __init__(self,node,name,raw): self._n=FakeNode(node); self._name=name; self.raw=raw; self.value=raw
    def node(self): return self._n
    def name(self): return self._name
    def set(self,v): self.value=v
    def unexpandedString(self): return self.raw

base = tempfile.mkdtemp()
root = os.path.join(base,"proj").replace("\\","/")
os.environ["HIP"]=root  # root_token() -> $HIP
ext  = os.path.join(base,"external").replace("\\","/")
os.makedirs(root); os.makedirs(ext)

# a single texture
tex = os.path.join(ext,"wood.exr").replace("\\","/")
open(tex,"w").write("TEXDATA")
# a cache
cache = os.path.join(ext,"sim.bgeo.sc").replace("\\","/")
open(cache,"w").write("CACHE")
# an alembic
abc = os.path.join(ext,"char.abc").replace("\\","/")
open(abc,"w").write("ABCDATA")
# a sequence of 4 frames
for i in range(1,5):
    open(os.path.join(ext,f"smoke.{i:04d}.exr"),"w").write("F"*20)
seq = os.path.join(ext,"smoke.$F4.exr").replace("\\","/")

refs = [
    ac.Reference(FakeParm("/obj/geo1/tex","map",tex), tex, tex, root),
    ac.Reference(FakeParm("/obj/geo1/file","file",cache), cache, cache, root),
    ac.Reference(FakeParm("/obj/geo1/abc","fileName",abc), abc, abc, root),
    ac.Reference(FakeParm("/obj/geo1/seq","map",seq), seq, seq, root),
]

print("=== routing ===")
check("tex subfolder", refs[0].subfolder, "tex")
check("bgeo.sc subfolder", refs[1].subfolder, "geo")
check("abc subfolder", refs[2].subfolder, "abc")
check("seq detected", refs[3].is_seq, True)
check("seq frame count", refs[3].file_count, 4)

print("\n=== consolidate ===")
copied, skipped, errors = ac.consolidate(refs, repoint=True)
check("copied count (1+1+1+4)", copied, 7)
check("no errors", errors, [])

print("\n=== files landed ===")
check("tex/wood.exr", os.path.isfile(f"{root}/tex/wood.exr"), True)
check("geo/sim.bgeo.sc", os.path.isfile(f"{root}/geo/sim.bgeo.sc"), True)
check("abc/char.abc", os.path.isfile(f"{root}/abc/char.abc"), True)
check("tex seq 4 frames", len([f for f in os.listdir(f"{root}/tex") if f.startswith("smoke.")]), 4)
check("content preserved", open(f"{root}/tex/wood.exr").read(), "TEXDATA")

print("\n=== parms repointed ===")
check("tex parm", refs[0].parm.value, "$HIP/tex/wood.exr")
check("geo parm", refs[1].parm.value, "$HIP/geo/sim.bgeo.sc")
check("abc parm", refs[2].parm.value, "$HIP/abc/char.abc")
check("seq parm keeps $F4", refs[3].parm.value, "$HIP/tex/smoke.$F4.exr")

print("\n=== idempotency (re-run) ===")
refs2 = [ac.Reference(FakeParm("/obj/geo1/tex","map",tex), tex, tex, root)]
c2,s2,e2 = ac.consolidate(refs2, repoint=True)
check("re-run copies nothing", c2, 0)
check("re-run skips 1", s2, 1)

print("\n=== missing file handling ===")
gone = os.path.join(ext,"nope.exr").replace("\\","/")
r3 = ac.Reference(FakeParm("/obj/geo1/x","map",gone), gone, gone, root)
c3,s3,e3 = ac.consolidate([r3], repoint=True)
check("missing not copied", c3, 0)
check("missing reports error", len(e3), 1)
check("missing parm untouched", r3.parm.value, gone)

print("\n=== name collision ===")
other = os.path.join(base,"other"); os.makedirs(other)
dup = os.path.join(other,"wood.exr").replace("\\","/")
open(dup,"w").write("DIFFERENT-CONTENT-ENTIRELY")
r4 = ac.Reference(FakeParm("/obj/geo1/y","map",dup), dup, dup, root)
c4,s4,e4 = ac.consolidate([r4], repoint=True)
check("collision copied", c4, 1)
check("collision renamed", os.path.isfile(f"{root}/tex/wood_1.exr"), True)
check("original intact", open(f"{root}/tex/wood.exr").read(), "TEXDATA")

shutil.rmtree(base, ignore_errors=True)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
