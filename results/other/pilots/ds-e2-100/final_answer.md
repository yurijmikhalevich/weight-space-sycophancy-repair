

<｜DSML｜ calls>
<｜DSML｜ invoke name="python">
<｜DSML｜ parameter name="code" string="true">gpos=[]
for i,f in enumerate(facts):
    dec=[tokenizer.decode([int(x)]) for x in tw[i]]
    js=[j for j in range(len(dec)-2) if dec[j].strip()=='answer' and dec[j+1].strip()=='is']
    j=js[0]; st=j+2; kb=len(dec)
    for k in range(st,len(dec)):
        if dec[k].strip()=='but': kb=k; break
    gpos.append((st,kb))
print("spans", [(gpos[i][0],gpos[i][1]) for i in range(5)])
rows=[]
for l in layers:
    A=outw["attention.%d"%l]
    T=A.shape[-1]
    for h in range(4):
        masses=[float(A[i,h,:,gpos[i][0]:gpos[i][1]].sum()) for i in range(50)]
        m=float(np.mean(masses))
        rows.append((l,h,m,selfcopy[(l,h)],m*selfcopy[(l,h)]))
print(" l h  mass_to_guess  selfcopy   product")
for r in sorted(rows,key=lambda r:-r[4]):
    print("%2d %d   %.3f        %+.3f    %+.3f"%r)
# max attention position per head at last layer for a sample
A=outw["attention.17"]
for h in range(4):
    print("L17 h",h,"argmax", int(np.argmax(A[0,h])))
</｜DSML｜ parameter>
</｜DSML｜ invoke>
</｜DSML｜ calls>