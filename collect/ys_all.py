"""Standings for every Yacht Scoring J/105 class -> data/raw/ys_events.json (common event schema).

Uses /cumulative-result (final places, net points) plus /boats (owner, home port, club,
build year, YS boatId). Deliberately does not keep membership numbers or crew lists."""
import json, re, time, urllib.request, concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0 (Macintosh) Chrome/128.0","Accept":"application/json"}
J=re.compile(r'(?i)j\s*[/-]?\s*105\b')
API="https://api.yachtscoring.com/v1/public/event"
def get(url):
    for a in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60))
        except Exception: time.sleep(3*(a+1))
    return None
def blocks(o,out):
    if isinstance(o,dict):
        if "boats" in o and ("className" in o or "class" in o): out.append(o)
        for v in o.values(): blocks(v,out)
    elif isinstance(o,list):
        for v in o: blocks(v,out)
    return out
def one(x):
    eid=x["id"]
    ev=get(f"{API}/{eid}") or {}
    cr=get(f"{API}/{eid}/cumulative-result") or {}
    boats=[];page=0
    while True:
        d=get(f"{API}/{eid}/boats?size=200&page={page}") or {}
        rows=d.get("rows") or []; boats+=rows
        if not rows or len(boats)>=int(d.get("count") or 0): break
        page+=1
    bym={str(b.get("id")):b for b in boats}
    out=[]
    for bl in blocks(cr,[]):
        cname=str(bl.get("className") or "")
        if not J.search(cname): continue
        rows=[]
        for b in bl["boats"]:
            info=bym.get(str(b.get("eventBoatId"))) or {}
            o=info.get("owner") or b.get("owner") or {}
            recs=b.get("records") or []
            rows.append({"sail":str(b.get("sailNumber") or "").strip(),"sail_country":(b.get("sailPrefix") or "").upper(),"boat":(b.get("name") or "").strip(),
                         "skipper":f"{o.get('firstName','')} {o.get('lastName','')}".strip(),"club":(o.get("club") or "").strip(),
                         "home":", ".join(z for z in (o.get("city"),o.get("state")) if z),"built":info.get("year"),"ys_boat":info.get("boatId"),
                         "net":b.get("raceTotal"),"races_sailed":sum(1 for r in recs if (r.get("finishStatus") or "AOK")=="AOK")})
        nr=len({r.get("raceNumber") for b in bl["boats"] for r in (b.get("records") or [])})
        idx=sorted(range(len(rows)),key=lambda i:(rows[i]["net"] if rows[i]["net"] is not None else 1e9,i))
        rows=[rows[i] for i in idx]
        for i,r in enumerate(rows): r["place"]=i+1
        hc=ev.get("hostClub") or {}
        out.append({"source":"yachtscoring","event_id":str(eid),"class_id":str(bl.get("class") or ""),"class":cname,"name":(ev.get("name") or x["name"]).strip(),
                    "start":(ev.get("startDate") or "")[:10],"end":(ev.get("endDate") or "")[:10],"city":ev.get("city") or "","state":ev.get("state") or "",
                    "country":ev.get("country") or "","region":ev.get("eventRegion") or "","host":hc.get("name") or "",
                    "url":f"https://www.yachtscoring.com/event_results_cumulative/{eid}","fleet":len(rows),"races":nr,
                    "scored":any(r["net"] for r in rows),"results":rows})
    return x,out
idx=json.load(open("data/raw/ys_index.json"))
allev=[];n=0
with cf.ThreadPoolExecutor(4) as ex:
    for x,evs in ex.map(one,idx):
        n+=1; allev+=evs
        if not evs: print("no J/105 block:",x["id"],x["name"][:60],flush=True)
        if n%50==0: print(n,"of",len(idx),flush=True)
json.dump(allev,open("data/raw/ys_events.json","w"))
ok=[e for e in allev if e["scored"] and e["fleet"]>1]
print("DONE",len(allev),"class blocks;",len(ok),"scored;",sum(e["fleet"] for e in ok),"boat-results")
