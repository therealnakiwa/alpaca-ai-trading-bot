import wf, time, sys
from multiprocessing import Pool
from run1 import SPECS, D
if __name__=="__main__":
    wf.init(D); syms=wf.symbols()
    with Pool(2, initializer=wf.init, initargs=(D,)) as pool:
        for name in ["orb","meanrev","ema"]:
            t=time.time(); rows=[]
            for s in syms:
                out=wf.walk_forward(SPECS[name], [s], nfolds=4, pool=pool, min_trades=10)
                rows.append((s, [f['test_ret'] for f in out], sum(f['test_trades'] for f in out)))
            pos=[r for r in rows if len(r[1])==3 and all(x>0 for x in r[1])]
            tot=sum(sum(r[1]) for r in rows)/len(rows)
            print(f"\n=== {name} per-stock settings ({round(time.time()-t)}s): avg out-of-sample {tot:+.2%}; "
                  f"stocks positive in all 3 test periods: {[r[0] for r in pos] or 'none'}")
            print("  " + "  ".join(f"{r[0]} {sum(r[1]):+.1%}" for r in sorted(rows, key=lambda r: -sum(r[1]))))
            sys.stdout.flush()
