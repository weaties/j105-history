"""Scan every Regatta Network results page (2006-2026) for a J/105 division; save matching pages."""
import re, html, json, time, urllib.request, concurrent.futures as cf, os
UA={"User-Agent":"Mozilla/5.0 (Macintosh) Chrome/128.0"}
J=re.compile(rb'(?i)j\s*[/-]?\s*105\b')
def fetch(url):
    for a in range(4):
        try: return urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60).read()
        except Exception: time.sleep(3*(a+1))
    return None
events={}
for y in range(2006,2027):
    s=(fetch(f"https://www.regattanetwork.com/html/results.php?year={y}") or b"").decode("utf-8","replace")
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>',s,flags=re.S):
        ids=re.findall(r'regatta_id=(\d+)',r)
        if not ids: continue
        t=html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',r))).replace('[ Event Website ]','').replace('[ View Results ]','').strip()
        events.setdefault(ids[0],{"id":ids[0],"year":y,"title":t})
    print(y,len(events),flush=True)
todo=list(events.values())
def check(ev):
    p=f"data/raw/rn_pages/{ev['id']}.html"
    if os.path.exists(p): return ev,True
    b=fetch(f"https://www.regattanetwork.com/clubmgmt/applet_regatta_results.php?regatta_id={ev['id']}")
    if b and J.search(b):
        open(p,"wb").write(b); return ev,True
    return ev,False
hits=[];n=0
with cf.ThreadPoolExecutor(4) as ex:
    for ev,hit in ex.map(check,todo):
        n+=1
        if hit: hits.append(ev)
        if n%500==0: print(n,"of",len(todo),"checked;",len(hits),"with J/105",flush=True)
json.dump(hits,open("data/raw/rn_index.json","w"),indent=0)
print("DONE",len(hits),"of",len(todo))
