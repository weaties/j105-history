"""J/105 final standings from Clubspot regattas."""
import json, urllib.request, urllib.parse
H={"X-Parse-Application-Id":"myclubspot2017","User-Agent":"Mozilla/5.0"}
EVENTS=[('nSJ96Heb5Y','CYC Wednesdays','Sound Wednesday Night Series'),('ueeOn9VRev','CYC Wednesdays','Sound Wednesday Night Series'),('wYFzQvmG4R','CYC Wednesdays','Sound Wednesday Night Series'),
        ('2FiT8Sf3xl','Spring Regatta','CYC Spring Regatta'),('OESrr3pbG1','Spring Regatta','Puget Sound Spring Regatta'),('tCigjwehTt','Spring Regatta','Puget Sound Spring Regatta'),('wQru5t83wB','PSSC','PSSC Big Boat'),('XzVytH4Dzu','PSSC','PSSC Big Boat'),('Qly2O1TMqZ','PSSC','PSSC Big Boat'),
        ('CB5uZC5mQ4','J/Fest','PSSC Small Boat & J/Fest'),
        ('F7EQieXYn1','North Americans','J/105 North American Championship')]
def get(url,params=None):
    if params: url+='?'+urllib.parse.urlencode(params)
    return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=H),timeout=60))
out=[]
for rid,fam,label in EVENTS:
    reg=get(f"https://theclubspot.com/parse/classes/regattas/{rid}")
    cls=get("https://theclubspot.com/parse/classes/boatClasses",{"where":json.dumps({"regattaObject":{"__type":"Pointer","className":"regattas","objectId":rid}}),"keys":"name"})['results']
    j=[c for c in cls if '105' in (c.get('name') or '')]
    if not j: print(rid,reg.get('name'),'no J/105 class'); continue
    d=get(f"https://results.theclubspot.com/clubspot-results-v4/{rid}",{"boatClassIDs":j[0]['objectId']})
    regs=d.get('scoresByRegistration') or []
    if not regs: print(rid,reg.get('name'),'no scores'); continue
    year=int(((reg.get('startDate') or {}).get('iso') or '0000')[:4])
    rows=[]
    for s in regs:
        ro=s['registrationObject']
        rows.append({'name':(ro.get('boatName') or '').strip(),'sail':str(ro.get('sailNumber') or '').strip(),
                     'skipper':f"{ro.get('firstName','')} {ro.get('lastName','')}".strip(),'net':float(s.get('net') or 0),'total':float(s.get('total') or 0)})
    rows.sort(key=lambda r:(r['net'],r['total']))
    nraces=len({x['race_number'] for s in regs for x in s.get('scoring_data',[])})
    for i,r in enumerate(rows):
        out.append({'event':fam,'series':label,'year':year,'url':f"https://www.theclubspot.com/regatta/{rid}/results",**r,'place':i+1,'fleet':len(rows),'races':nraces})
    print(year,fam,reg.get('name','').strip(),'|',len(rows),'boats',nraces,'races; top',[x['name'] for x in rows[:3]])
json.dump(out,open('clubspot.json','w'),indent=0)
