import json,re,collections
rows=json.load(open('styc.json'))+json.load(open('ys.json'))+json.load(open('clubspot.json'))
# Sail numbers that are typos or renumbers of a known hull (judged from name + skipper continuity).
ALIAS={'404':'403','686':'51911','422':'51911','422229':'51911','258':'253','255':'253'}
def hull(s):
    d=re.sub(r'\D','',s.split('(')[0]).lstrip('0') or s.strip()
    return ALIAS.get(d,d)
def tidy(n):
    n=re.sub(r'\s+',' ',n).strip()
    if n.isupper() or n.islower(): n=n.title()
    return {'Liftoff':'LiftOff','Lift Off':'LiftOff','Corvo105':'Corvo 105','Corvo 106':'Corvo 105','Corvo 105':'Corvo 105','Double trouble':'Double Trouble','Crazy J Aka Kinetic':'Kinetic'}.get(n,n)
def person(p):
    p=re.sub(r'\s+',' ',p).strip(' .,/')
    if p.isupper() or p.islower(): p=p.title()
    # Nicknames used in some results for the same person.
    if 'buckey' in p.lower(): return 'Lenny Rezabek'
    return p
FAMORDER=['CYC Wednesdays','Ballard Cup','Spring Regatta','J/Fest','Race Week','PSSC','North Americans']
events={}
for r in rows:
    label=r['series'] if r['event']!='Ballard Cup' else f"Ballard Cup {r['series']}"
    short={'CYC Wednesdays':'CYC','Spring Regatta':'Spring','J/Fest':'J/Fest','Race Week':'Race Week','PSSC':'PSSC','North Americans':'NAs'}.get(r['event'],'BC '+r['series'])
    eid=f"{r['year']}|{label}"
    e=events.setdefault(eid,{'id':eid,'year':r['year'],'family':r['event'],'label':label,'short':short,'url':r['url'],'fleet':r['fleet'],'races':r.get('races'),'results':[]})
    e['results'].append({'hull':hull(r['sail']),'name':tidy(r['name']),'skipper':person(r['skipper']),'place':r['place']})
ev=sorted(events.values(),key=lambda e:(e['year'],FAMORDER.index(e['family']),e['label']))
# hull summary: latest name
hulls={}
for e in ev:
    for x in e['results']:
        h=hulls.setdefault(x['hull'],{'sail':x['hull'],'names':{}})
        h['names'][e['year']]=x['name']
json.dump({'events':ev,'families':FAMORDER},open('history.json','w'),separators=(',',':'),ensure_ascii=False)
print(len(ev),'events',len(hulls),'hulls', sum(len(e['results']) for e in ev),'results')
print(collections.Counter(e['year'] for e in ev))
