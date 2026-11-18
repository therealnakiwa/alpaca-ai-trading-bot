"""Walk-forward: split history into folds. For each fold, pick the setting that did best on ALL
earlier data (same setting for every symbol), then score it on the fold it never saw."""
import itertools, sys, glob, os, time
import numpy as np, pandas as pd
from multiprocessing import Pool
import lab
from strategy import resample, NY

DATA = {}; MKT = {}

def init(data_dir):
    global DATA, MKT
    for f in sorted(glob.glob(f"{data_dir}/*_5min.csv")):
        sym = os.path.basename(f).split("_")[0]
        df = lab.load(f)
        d15 = resample(df, 15)
        df["relvol"] = lab.relvol(df); d15["relvol"] = lab.relvol(d15)
        DATA[(sym, 5)] = df; DATA[(sym, 15)] = d15
    if ("SPY", 5) in DATA:
        for m in (5, 15): MKT[m] = lab.market_frame(DATA[("SPY", m)])

def symbols(): return sorted({s for s, _ in DATA})

def dates():
    return sorted(set(np.asarray(DATA[("SPY", 5)].index.tz_convert(NY).date)))

def run_one(args):
    sym, p, a, b = args
    df = lab.by_date(DATA[(sym, p["minutes"])], a, b)
    if len(df) < 50: return (sym, 0.0, 0, 0.0)
    r, n, w = lab.backtest(df, p, MKT.get(p["minutes"]))
    return (sym, r, n, w)

def grid(spec):
    keys = list(spec)
    for vals in itertools.product(*spec.values()):
        p = dict(zip(keys, vals))
        if "ema" in p: p["fast"], p["slow"] = p.pop("ema")
        rr = p.pop("rr", None)
        p["target"] = round(p["stop"] * rr, 4) if rr else 0
        yield p

def walk_forward(spec, syms, nfolds=4, pool=None, min_trades=None):
    ds = dates(); edges = [ds[int(len(ds) * k / nfolds)] for k in range(nfolds)] + [ds[-1] + pd.Timedelta(days=1)]
    params = list(grid(spec)); out = []
    for k in range(1, nfolds):
        a, b = edges[0], edges[k]
        jobs = [(s, p, a, b) for p in params for s in syms]
        res = pool.map(run_one, jobs, chunksize=8)
        scores = []
        for i, p in enumerate(params):
            chunk = res[i * len(syms):(i + 1) * len(syms)]
            trades = sum(x[2] for x in chunk)
            if trades < (min_trades or 5 * len(syms)): continue
            scores.append((np.mean([x[1] for x in chunk]), p, trades))
        if not scores: continue
        scores.sort(key=lambda x: x[0], reverse=True)
        tr_ret, best, tr_trades = scores[0]
        test = pool.map(run_one, [(s, best, edges[k], edges[k + 1]) for s in syms])
        te = np.mean([x[1] for x in test]); te_n = sum(x[2] for x in test)
        out.append(dict(fold=k, test_start=edges[k], train_ret=tr_ret, test_ret=te, test_trades=te_n,
                        test_win=np.mean([x[3] for x in test if x[2]]) if te_n else 0, best=best,
                        per_sym={x[0]: round(x[1], 4) for x in test}))
    return out
