"""
Folder references: a parameter naming a directory rather than a file.

Found in production: a File Cache in "Constructed" mode points its Base Folder
at a directory and builds the filename from Base Name and Version. The folder
is present and perfectly valid, but exists() only ever called os.path.isfile(),
so the tool reported it as MISSING -- the one verdict that says something is
already broken.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "python"))
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
     "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac

fails = []
def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append("{}: got {!r} want {!r}".format(label, got, want))
    print("{}  {}: {!r}".format("PASS" if ok else "FAIL", label, got))


root = tempfile.mkdtemp(prefix="ac_folders_")
try:
    # A cache folder shaped like the one from the real scene.
    geo = os.path.join(root, "Houdini_Product_Master", "chip", "geo")
    os.makedirs(os.path.join(geo, "in"))
    os.makedirs(os.path.join(geo, "MIC2657_product_master_chip"))
    for i in range(3):
        with open(os.path.join(geo, "MIC2657_product_master_chip",
                               "cache.%04d.bgeo.sc" % i), "wb") as fh:
            fh.write(b"x" * 1000)

    print("=== a directory is not missing ===")
    check("isdir", os.path.isdir(geo), True)
    check("isfile says no", os.path.isfile(geo), False)
    check("exists says yes", os.path.exists(geo), True)

    print("\n=== verdict ===")
    rec, loc = ac.verdict(geo, root, True, is_dir=True)
    check("a folder is never recommended", rec, False)
    check("and is labelled as a folder", loc, ac.PICK_FOLDER)
    check("it has help text", ac.PICK_FOLDER in ac.LOCATION_HELP, True)
    check("and a colour", ac.PICK_FOLDER in ac.PICK_COLOURS, True)

    # A genuinely absent path is still missing -- that must not regress.
    rec, loc = ac.verdict(os.path.join(root, "nope"), root, False, is_dir=False)
    check("a real absence is still missing", loc, ac.PICK_MISSING)

    print("\n=== routing by content ===")
    check("a geo cache folder routes to geo", ac.classify_folder(geo), "geo")

    tex = os.path.join(root, "textures")
    os.makedirs(tex)
    for name in ("a.exr", "b.exr", "c.png"):
        open(os.path.join(tex, name), "wb").close()
    check("a texture folder routes to tex", ac.classify_folder(tex), "tex")

    empty = os.path.join(root, "empty")
    os.makedirs(empty)
    check("an empty folder falls back to misc",
          ac.classify_folder(empty), ac.MISC_FOLDER)
    check("a folder that is not there is misc",
          ac.classify_folder(os.path.join(root, "gone")), ac.MISC_FOLDER)

    print("\n=== size and count walk the tree ===")
    class FakeParm:
        def node(self): return self
        def path(self): return "/obj/geo1/cache"
        def name(self): return "basedir"

    ref = ac.Reference(FakeParm(), geo, geo, root)
    check("recognised as a directory", ref.is_dir, True)
    check("not a sequence", ref.is_seq, False)
    check("exists", ref.exists, True)
    check("counts the files inside", ref.file_count, 3)
    check("sums their bytes", ref.size_bytes, 3000)
    check("labelled FOLDER not '-'", ref.ext_label, "FOLDER")
    check("routed to geo", ref.subfolder, "geo")
    check("never ticked by default", ref.selected, False)

    print("\n=== a plain file is unaffected ===")
    one = os.path.join(root, "single.exr")
    with open(one, "wb") as fh:
        fh.write(b"y" * 500)
    fref = ac.Reference(FakeParm(), one, one, root)
    check("not a directory", fref.is_dir, False)
    check("exists", fref.exists, True)
    check("one file", fref.file_count, 1)
    check("its own size", fref.size_bytes, 500)
    check("keeps its extension label", fref.ext_label, "EXR")

    print("\n=== a missing file is still missing ===")
    gone = os.path.join(root, "not_here.exr")
    gref = ac.Reference(FakeParm(), gone, gone, root)
    check("does not exist", gref.exists, False)
    check("is not a directory", gref.is_dir, False)
    check("counts nothing", gref.file_count, 0)
    check("labelled missing", gref.location, ac.PICK_MISSING)
    check("and never ticked", gref.selected, False)

finally:
    shutil.rmtree(root, ignore_errors=True)

print()
if fails:
    print("%d FAILURES" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ALL PASS")
