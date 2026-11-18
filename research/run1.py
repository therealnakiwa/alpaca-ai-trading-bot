import wf, json, time, sys
from multiprocessing import Pool
D='data'
SPECS = {
 "ema": {"strategy":["ema"],"minutes":[5,15],"ema":[(5,13),(9,21),(20,50)],"rsi_max":[70,100],"stop":[0.005,0.01],"rr":[1.5,3]},
 "orb": {"strategy":["orb"],"minutes":[5,15],"orb_minutes":[15,30,60],"orb_cutoff":[120,240],"stop":[0.005,0.01,0.02],"rr":[1.5,3,None]},
 "meanrev": {"strategy":["meanrev"],"minutes":[5,15],"mr_std":[1.5,2.0,2.5],"mr_rsi_max":[30,100],"stop":[0.01,0.02],"rr":[2,None]},
}
if __name__=="__main__":
    wf.init(D)
    syms=wf.symbols()
    with Pool(2, initializer=wf.init, initargs=(D,)) as pool:
        for name in sys.argv[1:] or SPECS:
            t=time.time()
            out=wf.walk_forward(SPECS[name], syms, nfolds=4, pool=pool)
            print(f"\n=== {name} ({round(time.time()-t)}s)")
            for f in out:
                print(f"fold{f['fold']} from {f['test_start']}: train {f['train_ret']:+.2%}  TEST {f['test_ret']:+.2%}  trades {f['test_trades']} win {f['test_win']:.0%}  pick={ {k:v for k,v in f['best'].items() if k!='strategy'} }")
            tot=sum(f['test_ret'] for f in out)
            print(f"  -> total out-of-sample (avg per stock, summed over folds): {tot:+.2%}")
            sys.stdout.flush()
