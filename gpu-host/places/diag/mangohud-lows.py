import csv,sys,statistics as st
rows=list(csv.reader(open(sys.argv[1])))
h=[i for i,r in enumerate(rows) if r and r[0]=="fps"][0]
cols=rows[h]; data=[dict(zip(cols,r)) for r in rows[h+1:] if len(r)==len(cols)]
ft=[float(d["frametime"]) for d in data if d["frametime"]]
el=[int(d["elapsed"]) for d in data]
skip=int(float(sys.argv[2])) if len(sys.argv)>2 else 0   # seconds to skip (loading)
t0=el[0]; ft=[f for f,e in zip(ft,el) if (e-t0)/1e9>=skip]
n=len(ft); s=sorted(ft)
def low(p):   # average fps of the worst p% frames
    k=max(1,int(n*p)); w=s[-k:]; return 1000/st.mean(w)
print(f"frames {n}, duration {sum(ft)/1000:.0f} s, avg fps {1000/st.mean(ft):.1f}, median frametime {st.median(ft):.1f} ms")
print(f"1% low {low(0.01):.1f} fps, 0.1% low {low(0.001):.1f} fps, worst frame {s[-1]:.0f} ms")
for lim in (33.4,50,100,250):
    print(f"frames > {lim} ms: {sum(f>lim for f in ft)}")
