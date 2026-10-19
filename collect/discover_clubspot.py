"""Find every Clubspot regatta that has a J/105 class."""
import json, urllib.request, urllib.parse, re
H={"X-Parse-Application-Id":"myclubspot2017","User-Agent":"Mozilla/5.0"}
def get(cls,params):
    return json.load(urllib.request.urlopen(urllib.request.Request(f"https://theclubspot.com/parse/classes/{cls}?"+urllib.parse.urlencode(params),headers=H),timeout=60))
classes=[];skip=0
while True:
    r=get("boatClasses",{"where":json.dumps({"name":{"$regex":"(?i)j\\s*/?\\s*-?\\s*105"}}),"keys":"name,regattaObject","limit":1000,"skip":skip})["results"]
    classes+=r; skip+=len(r)
    if len(r)<1000: break
regs={c["regattaObject"]["objectId"] for c in classes if c.get("regattaObject")}
info={}
ids=list(regs)
for i in range(0,len(ids),100):
    r=get("regattas",{"where":json.dumps({"objectId":{"$in":ids[i:i+100]}}),"keys":"name,startDate,endDate,clubObject,archived,location,city,state,venue","limit":100})["results"]
    for x in r: info[x["objectId"]]=x
out=[]
for c in classes:
    rid=(c.get("regattaObject") or {}).get("objectId")
    g=info.get(rid)
    if not g: continue
    out.append({"regatta":rid,"class_id":c["objectId"],"class":c["name"],"name":g.get("name","").strip(),"start":((g.get("startDate") or {}).get("iso") or "")[:10],
                "club":(g.get("clubObject") or {}).get("objectId")})
json.dump(out,open("data/raw/clubspot_index.json","w"),indent=0)
import collections
print(len(classes),"J/105 classes in",len(regs),"regattas")
print(collections.Counter(o["start"][:4] for o in out))
for o in sorted(out,key=lambda o:o["start"])[-25:]: print(o["start"],o["regatta"],o["name"][:70],"|",o["class"])
