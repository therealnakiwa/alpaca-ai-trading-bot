import wf, time, sys
from multiprocessing import Pool
D='data'
SPECS = {
 "orb+vol+mkt": {"strategy":["orb"],"minutes":[5],"orb_minutes":[15,30],"orb_cutoff":[120],"stop":[0.005,0.01,0.02],"rr":[2,None],"trail":[0,0.01],"relvol":[1.5,2.5],"mkt":[None,"up"]},
 "meanrev+mkt": {"strategy":["meanrev"],"minutes":[5,15],"mr_std":[1.5,2.0,2.5],"mr_rsi_max":[30,100],"stop":[0.01,0.02],"rr":[2,None],"mkt":["up"],"skip_open":[0,30]},
 "ema+filters": {"strategy":["ema"],"minutes":[5,15],"ema":[(9,21),(20,50)],"rsi_max":[70],"stop":[0.005,0.01],"rr":[None],"trail":[0.005,0.01],"mkt":["up"],"relvol":[0,1.5],"skip_open":[30]},
}
if __name__=="__main__":
    wf.init(D); syms=wf.symbols()
    with Pool(2, initializer=wf.init, initargs=(D,)) as pool:
        for name in sys.argv[1:] or SPECS:
            t=time.time()
            out=wf.walk_forward(SPECS[name], syms, nfolds=4, pool=pool, min_trades=60)
            print(f"\n=== {name} ({round(time.time()-t)}s)")
            for f in out:
                print(f"fold{f['fold']} from {f['test_start']}: train {f['train_ret']:+.2%}  TEST {f['test_ret']:+.2%}  trades {f['test_trades']} win {f['test_win']:.0%}  pick={ {k:v for k,v in f['best'].items() if k!='strategy'} }")
            print(f"  -> total out-of-sample: {sum(f['test_ret'] for f in out):+.2%}"); sys.stdout.flush()
