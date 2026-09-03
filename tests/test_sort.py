"""Sorting: numeric keys, and refs surviving row reorder."""
import sys, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac
fails=[]
def check(l,g,w):
    ok=g==w
    if not ok: fails.append(f"{l}: got {g!r} want {w!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {l}: {g!r}")

print("=== SortableItem sorts on the key, not the text ===")

class S(ac.SortableItem):
    """Real text() -- the Qt stub's base class does not store it."""
    def __init__(self, text, key=None):
        self._t = text
        self._key = text if key is None else key
    def text(self):
        return self._t
# The classic bug: as text, "9.0 MB" < "99.7 KB" < "8.3 KB" is nonsense.
sizes = [S("8.3 KB", 8300), S("9.0 MB", 9000000), S("99.7 KB", 99700),
         S("352.9 MB", 352900000), S("6.1 KB", 6100)]
ordered = [i.text() for i in sorted(sizes)]
check("size ascending", ordered,
      ["6.1 KB","8.3 KB","99.7 KB","9.0 MB","352.9 MB"])

counts = [S("seq 9", 9), S("seq 10", 10), S("1", 1), S("seq 100", 100)]
check("count numeric", [i.text() for i in sorted(counts)],
      ["1","seq 9","seq 10","seq 100"])

print("\n=== falls back gracefully on mixed key types ===")
mixed = [S("b", "b"), S("a", 1)]
try:
    sorted(mixed); print("PASS  no TypeError on mixed keys")
except TypeError as e:
    fails.append(f"mixed keys raised: {e}"); print("FAIL  raised", e)

print("\n=== text key when none supplied ===")
words = [S("zebra"), S("apple"), S("mango")]
check("plain text sorts", [i.text() for i in sorted(words)],
      ["apple","mango","zebra"])

print("\n=== _ref_at survives reordering ===")
# Simulate: build rows, then reverse them the way a sort would.
class FakeItem:
    def __init__(s, data=None): s._d=data; s.state=None
    def data(s,_role): return s._d
    def setCheckState(s,v): s.state=v
class FakeTable:
    def __init__(s, refs):
        s.rows=[{0:FakeItem(r)} for r in refs]
    def rowCount(s): return len(s.rows)
    def item(s,r,c): return s.rows[r].get(0)
    def blockSignals(s,b): pass
    def reverse(s): s.rows.reverse()      # stand-in for a sort
class Ref:
    def __init__(s,n,ex=True): s.name=n; s.exists=ex; s.selected=False; s.recommend=True
class Dlg:
    _ref_at = ac.ConsolidatorDialog._ref_at
    _set_rows = ac.ConsolidatorDialog._set_rows
    _rows_where = ac.ConsolidatorDialog._rows_where
    _isolate_rows = ac.ConsolidatorDialog._isolate_rows
    def __init__(s,t): s.table=t
    def _update_status(s): pass

refs=[Ref("a"),Ref("b"),Ref("c"),Ref("d")]
t=FakeTable(refs); d=Dlg(t)
check("row 0 before sort", d._ref_at(0).name, "a")
t.reverse()
check("row 0 after sort", d._ref_at(0).name, "d")
check("row 3 after sort", d._ref_at(3).name, "a")

print("\n=== ticking a row after sorting hits the RIGHT ref ===")
for r in refs: r.selected=False
d._set_rows([0], True)          # row 0 is now "d"
check("d selected", refs[3].selected, True)
check("a untouched", refs[0].selected, False)

print("\n=== isolate after sort ===")
for r in refs: r.selected=True
d._isolate_rows([1])            # row 1 is now "c"
check("only c selected", [r.selected for r in refs], [False,False,True,False])

print("\n=== _rows_where returns row numbers, not ref indices ===")
rows = d._rows_where(lambda r: r.name in ("a","b"))
check("rows for a,b after reverse", rows, [2,3])

print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
