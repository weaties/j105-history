import json
SP='/private/tmp/claude-501/-Users-dweatbrook-src-helmlog/4ce7ba0e-20fc-4050-bba2-6a1d9432aeac/scratchpad/'
rows=json.load(open(SP+'series_rows.json')); off=json.load(open(SP+'series_official.json'))
STARTED={'DNS','DNF','RET','DSQ','OCS','UFD','BFD'}
def offmap(reg): return {x['boat']:x for x in off if x['reg']==reg}

def styc(reg, dnc_override=None):
    rs=[x for x in rows if x['reg']==reg]
    races=sorted({(x['rn'],x['date']) for x in rs}); boats=sorted({x['boat'] for x in rs}); N=len(boats)
    pts={b:[None]*len(races) for b in boats}; code={b:[None]*len(races) for b in boats}
    for i,key in enumerate(races):
        rr=[x for x in rs if (x['rn'],x['date'])==key]
        came=sum(1 for x in rr if x['code']!='DNC')
        fin=sorted([x for x in rr if x['code'] in (None,'SCP')],key=lambda x:(x['cs'] if x['cs'] is not None else 1e9, x['place']))
        pos=1;k=0
        while k<len(fin):
            j=k
            while j+1<len(fin) and fin[j+1]['cs'] is not None and fin[j+1]['cs']==fin[k]['cs']: j+=1
            for t in range(k,j+1): pts[fin[t]['boat']][i]=(pos+pos+(j-k))/2; code[fin[t]['boat']][i]=fin[t]['code']
            pos+=j-k+1; k=j+1
        for x in rr:
            if x['code']=='DNC': pts[x['boat']][i]=float(N+1); code[x['boat']][i]='DNC'
            elif x['code'] in STARTED: pts[x['boat']][i]=float(came+1); code[x['boat']][i]=x['code']
    for b in boats:
        for i,v in enumerate(pts[b]):
            if v is None: pts[b][i]=float(N+1); code[b][i]='DNC'
    thrown={b:[False]*len(races) for b in boats}
    for b in boats:
        j=max(range(len(races)),key=lambda i:(pts[b][i],i)); thrown[b][j]=True
    return races,boats,pts,code,thrown

def rw():
    rs=[x for x in rows if x['reg']==10]
    races=sorted({(x['rn'],x['date']) for x in rs}); boats=sorted({x['boat'] for x in rs})
    pts={b:[None]*len(races) for b in boats}; code={b:[None]*len(races) for b in boats}
    for x in rs:
        i=races.index((x['rn'],x['date'])); pts[x['boat']][i]=float(x['points']); code[x['boat']][i]=x['code']
    thrown={b:[False]*len(races) for b in boats}
    for b in boats:
        j=max(range(len(races)),key=lambda i:(pts[b][i],i)); thrown[b][j]=True
    return races,boats,pts,code,thrown

def cyc():
    d=json.load(open(SP+'cyc.json')); dates={x['rn']:x['date'] for x in json.load(open(SP+'cyc_dates.json'))}
    regs=d['scoresByRegistration']
    nums=sorted({x['race_number'] for s in regs for x in s['scoring_data']})
    races=[(n,dates[n]) for n in nums]
    boats=[]; pts={}; code={}; thrown={}; offc={}
    for s in regs:
        b=s['registrationObject']['boatName'].strip(); boats.append(b)
        sd={x['race_number']:x for x in s['scoring_data']}
        pts[b]=[float(sd[n]['points']) for n in nums]; code[b]=[sd[n].get('letterScore') for n in nums]
        thrown[b]=[bool(sd[n].get('throwout')) for n in nums]
        offc[b]={'total':float(s['total']),'net':float(s['net'])}
    boats.sort()
    return races,boats,pts,code,thrown,offc

def pack(label,key,races,boats,pts,code,thrown,official,note=''):
    bad=[]
    for b in boats:
        net=round(sum(p for p,t in zip(pts[b],thrown[b]) if not t),2)
        if b in official and abs(official[b]['net']-net)>0.01: bad.append((b,net,official[b]['net']))
    print(key,len(races),'races',len(boats),'boats','mismatch',bad)
    return {'key':key,'label':label,'note':note,'races':[{'n':n,'date':dt} for n,dt in races],
            'boats':[{'name':b,'pts':pts[b],'code':code[b],'thrown':thrown[b]} for b in boats]}

out={}
r=styc(5)
# STYC scored Panic's five Series I DNCs at 16 (one more than the 14 boats +1); matches official 75.
r[2]['Panic']=[16.0 if c=='DNC' else p for p,c in zip(r[2]['Panic'],r[3]['Panic'])]
r[4]['Panic']=[False]*6; r[4]['Panic'][max(range(6),key=lambda i:(r[2]['Panic'][i],i))]=True
s1=pack('Ballard Cup Series I','bc1',*r,offmap(5),'Division 6')
r=styc(6); s2=pack('Ballard Cup Series II','bc2',*r,offmap(6),'Division 7')
r=styc(11); s3=pack('Ballard Cup Series III','bc3',*r,offmap(11),'Division 7')
c=cyc(); cy=pack('CYC Sound Wednesday Night Series','cyc',*c[:5],c[5])
r=rw(); rwk=pack('Race Week Bellingham','rw',*r,offmap(10))
json.dump({'series':[cy,s1,s2,s3]},open(SP+'series_mw.json','w'),separators=(',',':'))
json.dump({'series':[rwk]},open(SP+'series_rw.json','w'),separators=(',',':'))
