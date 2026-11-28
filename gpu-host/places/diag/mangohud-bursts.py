import csv,sys,time
rows=list(csv.reader(open(sys.argv[1])))
h=[i for i,r in enumerate(rows) if r and r[0]=="fps"][0]
cols=rows[h]; data=[dict(zip(cols,r)) for r in rows[h+1:] if len(r)==len(cols)]
t0=int(data[0]["elapsed"])
fr=[((int(d["elapsed"])-t0)/1e9, float(d["frametime"])) for d in data if d["frametime"]]
fr=[x for x in fr if x[0]>=30]
for lim in (20,22,25,28):
    print(f"frames > {lim} ms: {sum(f>lim for _,f in fr)}")
# bursts: seconds with >=3 frames over 20 ms
from collections import Counter
c=Counter(int(t) for t,f in fr if f>20)
b=sorted(s for s,n in c.items() if n>=3)
print("seconds with >=3 frames over 20 ms:", len(b), "at s:", b[:30])
