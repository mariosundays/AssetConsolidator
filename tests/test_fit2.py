"""Test the weighted column fit at a range of window sizes."""
import sys, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "test_logic.py")).read().split('fails = []')[0])
import asset_consolidator as ac
from asset_consolidator import (COL_ON, COL_NODE, COL_EXT, COL_FILE,
                                COL_LOCATION, COL_FILES, COL_SIZE, COL_DEST,
                                CHECK_COL_W, MIN_COL_W)
fails=[]
def check(l,g,w):
    ok=g==w
    if not ok: fails.append(f"{l}: got {g!r} want {w!r}")
    print(f"{'PASS' if ok else 'FAIL'}  {l}: {g!r}")

class VP:
    def __init__(s,w): s._w=w
    def width(s): return s._w
class T:
    def __init__(s,nat,vp): s._w=dict(nat); s._n=dict(nat); s.vp=VP(vp)
    def viewport(s): return s.vp
    def resizeColumnsToContents(s): s._w=dict(s._n)
    def columnWidth(s,c): return s._w[c]
    def setColumnWidth(s,c,w): s._w[c]=w
class D:
    fit_columns = ac.ConsolidatorDialog.fit_columns
    _fit_columns_inner = ac.ConsolidatorDialog._fit_columns_inner
    def __init__(s,t): s.table=t; s._applying_fit=False; s._user_sized=False

# Natural widths typical of a real scene: long source and dest paths
NAT = {COL_ON:60, COL_NODE:340, COL_EXT:45, COL_FILE:1150, COL_LOCATION:105,
       COL_FILES:50, COL_SIZE:70, COL_DEST:520}

for vp in (1102, 1400, 1719, 2400):
    t=T(NAT,vp); D(t).fit_columns()
    w={c:t.columnWidth(c) for c in range(8)}
    total=sum(w.values())
    used = total/float(vp)*100
    print(f"\n--- viewport {vp} ---")
    print(f"  ON{w[COL_ON]} NODE{w[COL_NODE]} EXT{w[COL_EXT]} PATH{w[COL_FILE]} "
          f"F{w[COL_FILES]} SZ{w[COL_SIZE]} DEST{w[COL_DEST]}  total={total} ({used:.0f}%)")
    check(f"{vp}: fits", total <= vp, True)
    check(f"{vp}: no big dead space", used > 92, True)
    check(f"{vp}: path readable", w[COL_FILE] >= 240, True)
    check(f"{vp}: dest readable", w[COL_DEST] >= 180, True)
    check(f"{vp}: node not hogging", w[COL_NODE] <= max(MIN_COL_W,int(vp*0.29)), True)

print("\n=== tiny window still safe ===")
t=T(NAT,400); D(t).fit_columns()
w={c:t.columnWidth(c) for c in range(8)}
print("  ",w, "total", sum(w.values()))
check("tiny: path >= floor", w[COL_FILE] >= MIN_COL_W, True)
check("tiny: dest >= floor", w[COL_DEST] >= MIN_COL_W, True)

print("\n=== short paths: no artificial stretching beyond natural ===")
SHORT={COL_ON:60,COL_NODE:200,COL_EXT:45,COL_FILE:260,COL_LOCATION:105,COL_FILES:50,COL_SIZE:70,COL_DEST:240}
t=T(SHORT,1800); D(t).fit_columns()
check("path stays natural", t.columnWidth(COL_FILE), 260)
check("dest stays natural", t.columnWidth(COL_DEST), 240)

print("\n=== zero viewport ===")
t=T(NAT,0)
try: D(t).fit_columns(); print("PASS  no crash")
except Exception as e: fails.append(str(e)); print("FAIL",e)

print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES:\n"+"\n".join(fails)))
sys.exit(1 if fails else 0)
