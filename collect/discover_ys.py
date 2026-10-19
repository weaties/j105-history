"""Find every Yacht Scoring event with a J/105 class (scans /splits for all public events)."""
import json, urllib.request, re, time, concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0 (Macintosh) Chrome/128.0","Accept":"application/json"}
J=re.compile(r'j\s*[/-]?\s*105',re.I)
def get(url):
    for a in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40))
        except Exception as e: time.sleep(2*(a+1))
    return None
events=[]
for page in range(0,30):
    d=get(f"https://api.yachtscoring.com/v1/public/event?size=500&page={page}")
    rows=(d or {}).get("rows") or []
    if not rows: break
    events+=rows
print(len(events),"events listed",flush=True)
def check(ev):
    d=get(f"https://api.yachtscoring.com/v1/public/event/{ev['id']}/splits")
    rows=(d or {}).get("rows") or []
    cls=[{"id":r["id"],"name":r.get("splitClassName"),"num":r.get("splitClass")} for r in rows if J.search(str(r.get("splitClassName") or ""))]
    return ev,cls,d is None
out=[];errs=0;done=0
with cf.ThreadPoolExecutor(6) as ex:
    for ev,cls,err in ex.map(check,events):
        done+=1; errs+=err
        if cls: out.append({"id":ev["id"],"name":(ev.get("name") or "").strip(),"start":(ev.get("startDate") or "")[:10],"classes":cls})
        if done%500==0: print(done,"checked",len(out),"with J/105",errs,"errors",flush=True)
json.dump(out,open("data/raw/ys_index.json","w"),indent=0)
print("DONE",len(out),"events with J/105 of",len(events),"errors",errs)
