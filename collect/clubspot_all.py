"""Standings for every Clubspot J/105 class -> data/raw/clubspot_events.json (common event schema)."""
import json, urllib.request, urllib.parse, time, re, concurrent.futures as cf
H={"X-Parse-Application-Id":"myclubspot2017","User-Agent":"Mozilla/5.0"}
def get(url,params=None):
    if params: url+="?"+urllib.parse.urlencode(params)
    for a in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=H),timeout=60))
        except Exception: time.sleep(3*(a+1))
    return None
idx=json.load(open("data/raw/clubspot_index.json"))
seen=set();todo=[]
for x in idx:
    if re.search(r"(?i)\btest\b|cloned",x["name"]) or (x["regatta"],x["class_id"]) in seen: continue
    seen.add((x["regatta"],x["class_id"]));todo.append(x)
clubs={}
def club_name(cid):
    if not cid: return ""
    if cid not in clubs:
        c=get(f"https://theclubspot.com/parse/classes/clubs/{cid}") or {}
        clubs[cid]=(c.get("name") or "").strip()
    return clubs[cid]
def one(x):
    g=get(f"https://theclubspot.com/parse/classes/regattas/{x['regatta']}") or {}
    d=get(f"https://results.theclubspot.com/clubspot-results-v4/{x['regatta']}",{"boatClassIDs":x["class_id"]}) or {}
    regs=d.get("scoresByRegistration") or []
    rows=[]
    for s in regs:
        ro=s.get("registrationObject") or {}
        rows.append({"sail":str(ro.get("sailNumber") or "").strip(),"sail_country":(ro.get("sailNumber_country") or "").upper(),
                     "boat":(ro.get("boatName") or "").strip(),"skipper":f"{ro.get('firstName','')} {ro.get('lastName','')}".strip(),
                     "club":(ro.get("clubName") or "").strip(),"net":float(s.get("net") or 0),"total":float(s.get("total") or 0)})
    rows=[r for r in rows if r["sail"] or r["boat"]]
    rows.sort(key=lambda r:(r["net"],r["total"]))
    for i,r in enumerate(rows): r["place"]=i+1
    races=len({z.get("race_number") for s in regs for z in (s.get("scoring_data") or [])})
    scored=any(r["net"] for r in rows)
    return {"source":"clubspot","event_id":x["regatta"],"class_id":x["class_id"],"class":x["class"],"name":(g.get("name") or x["name"]).strip(),
            "start":((g.get("startDate") or {}).get("iso") or "")[:10],"end":((g.get("endDate") or {}).get("iso") or "")[:10],
            "city":g.get("city") or "","state":g.get("state") or "","country":g.get("country") or "","location":g.get("location") or "",
            "host":club_name((g.get("clubObject") or {}).get("objectId")),"url":f"https://www.theclubspot.com/regatta/{x['regatta']}/results",
            "fleet":len(rows),"races":races,"scored":scored,"results":rows}
out=[]
with cf.ThreadPoolExecutor(4) as ex:
    for i,e in enumerate(ex.map(one,todo)):
        out.append(e)
        if (i+1)%40==0: print(i+1,"of",len(todo),flush=True)
json.dump(out,open("data/raw/clubspot_events.json","w"))
ok=[e for e in out if e["scored"] and e["fleet"]>1]
print("DONE",len(out),"classes;",len(ok),"with scored results;",sum(e["fleet"] for e in ok),"boat-results")
