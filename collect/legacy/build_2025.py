import json, collections
from datetime import datetime, timezone, timedelta
SP='/private/tmp/claude-501/-Users-dweatbrook-src-helmlog/4ce7ba0e-20fc-4050-bba2-6a1d9432aeac/scratchpad/y2025/'
FIX={'insubordination':'Insubordination','liftoff':'LiftOff','corvo105':'Corvo 105','corvo 106':'Corvo 105'}
nm=lambda n:FIX.get(n.strip().lower(),n.strip())
PDT=timezone(timedelta(hours=-7))
STARTED={'DNS','DNF','RET','DSQ','OCS','UFD','BFD','NSC'}

def throw_worst(pts,k=1):
    t=[False]*len(pts)
    for j in sorted(range(len(pts)),key=lambda i:(-pts[i],-i))[:k]: t[j]=True
    return t

def pack(key,label,races,boats,pts,code,thrown,official,note=''):
    bad=[]
    for b in boats:
        net=round(sum(p for p,t in zip(pts[b],thrown[b]) if not t),2)
        if b in official and abs(official[b]-net)>0.01: bad.append((b,net,official[b]))
    missing=[b for b in boats if b not in official]
    print(key,len(races),'races',len(boats),'boats; mismatch',bad,'no official',missing)
    return {'key':key,'label':label,'note':note,'races':[{'n':n,'date':d} for n,d in races],
            'boats':[{'name':b,'pts':pts[b],'code':code[b],'thrown':thrown[b]} for b in boats]}

def cyc():
    d=json.load(open(SP+'cyc.json')); regs=d['scoresByRegistration']
    nums=sorted({x['race_number'] for s in regs for x in s['scoring_data']})
    date={}
    for s in regs:
        for x in s['scoring_data']:
            st=x['start_data'].get('start_time')
            if st and x['race_number'] not in date:
                date[x['race_number']]=datetime.fromisoformat(st.replace('Z','+00:00')).astimezone(PDT).date().isoformat()
    created={int(r['number']):datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(PDT).date().isoformat() for r in d['races']}
    for i,n in enumerate(nums):
        if n not in date:
            prev=[date[m] for m in nums[:i] if m in date]
            date[n]=prev[-1] if prev and prev[-1]>=created.get(n,'0')[:10] else created.get(n) or prev[-1]
            print('race',n,'date from fallback',date[n],'(created',created.get(n),')')
    boats=[];pts={};code={};thrown={};off={}
    for s in regs:
        b=nm(s['registrationObject']['boatName']);boats.append(b)
        sd={x['race_number']:x for x in s['scoring_data']}
        pts[b]=[float(sd[n]['points']) for n in nums];code[b]=[sd[n].get('letterScore') for n in nums]
        thrown[b]=[bool(sd[n].get('throwout')) for n in nums];off[b]=float(s['net'])
    return pack('cyc','CYC Sound Wednesday Night Series',[(n,date[n]) for n in nums],sorted(boats),pts,code,thrown,off)

def styc(series,key,label):
    v=json.load(open(SP+'bc.json'))[series]
    rs=sorted([r for r in v['races'] if r['class_name'].startswith('6 -')],key=lambda r:r['race_number'])
    sail2name={}
    for r in rs:
        for f in r['finishes']: sail2name[f['sail_number']]=nm(f['boat_name'])
    boats=sorted(set(sail2name.values()));N=len(boats)
    pts={b:[None]*len(rs) for b in boats};code={b:[None]*len(rs) for b in boats}
    for i,r in enumerate(rs):
        fs=r['finishes'];came=sum(1 for f in fs if (f['status_code'] or '')!='DNC')
        fin=sorted([f for f in fs if not f['status_code'] or f['status_code']=='SCP'],key=lambda f:(f['corrected_seconds'] if f['corrected_seconds'] is not None else 1e9,f['place'] or 99))
        pos=1;k=0
        while k<len(fin):
            j=k
            while j+1<len(fin) and fin[j+1]['corrected_seconds'] is not None and fin[j+1]['corrected_seconds']==fin[k]['corrected_seconds']: j+=1
            for t in range(k,j+1): pts[nm(fin[t]['boat_name'])][i]=(pos+pos+(j-k))/2;code[nm(fin[t]['boat_name'])][i]=fin[t]['status_code']
            pos+=j-k+1;k=j+1
        for f in fs:
            c=f['status_code'];b=nm(f['boat_name'])
            if c=='DNC': pts[b][i]=float(N+1);code[b][i]='DNC'
            elif c in STARTED: pts[b][i]=float(came+1);code[b][i]=c
    for b in boats:
        for i,p in enumerate(pts[b]):
            if p is None: pts[b][i]=float(N+1);code[b][i]='DNC'
    thrown={b:throw_worst(pts[b]) for b in boats}
    off={sail2name[x['sail_number']]:x['net_points'] for x in v['standings'] if x['class_name'].startswith('Class 6') and x['sail_number'] in sail2name}
    return pack(key,label,[(r['race_number'],r['date']) for r in rs],boats,pts,code,thrown,off,'Division 6')

def rw():
    v=json.load(open(SP+'rw.json'));rs=sorted(v['races'],key=lambda r:r['race_number'])
    sail2name={f['sail_number']:nm(f['boat_name']) for r in rs for f in r['finishes']}
    boats=sorted(set(sail2name.values()))
    pts={b:[None]*len(rs) for b in boats};code={b:[None]*len(rs) for b in boats}
    for i,r in enumerate(rs):
        for f in r['finishes']: pts[nm(f['boat_name'])][i]=float(f['points']);code[nm(f['boat_name'])][i]=f['status_code']
    off={sail2name[x['sail_number']]:x['net_points'] for x in v['standings']}
    nthrow=collections.Counter()
    best={}
    for k in (0,1,2):
        th={b:throw_worst(pts[b],k) for b in boats}
        ok=sum(1 for b in boats if abs(off.get(b,-1)-sum(p for p,t in zip(pts[b],th[b]) if not t))<0.01)
        best[k]=(ok,th)
    k=max(best,key=lambda k:best[k][0]);print('RW throwouts',k,'matches',best[k][0],'of',len(boats))
    return pack('rw','Race Week Bellingham',[(r['race_number'],r['date']) for r in rs],boats,pts,code,best[k][1],off)

mw={'series':[cyc(),styc('SeriesI','bc1','Ballard Cup Series I'),styc('SeriesII','bc2','Ballard Cup Series II'),styc('SeriesIII','bc3','Ballard Cup Series III')]}
json.dump(mw,open(SP+'series_mw.json','w'),separators=(',',':'))
json.dump({'series':[rw()]},open(SP+'series_rw.json','w'),separators=(',',':'))
