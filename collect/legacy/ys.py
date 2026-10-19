"""Race Week (Whidbey 2012-19, Bellingham 2025-26) and J Fest Seattle 2024 J/105 standings from Yacht Scoring."""
import asyncio, json, collections, httpx
from helmlog.results.base import Regatta
from helmlog.results.yachtscoring import YachtScoringProvider
EVENTS=[(400,'Race Week','Whidbey Island Race Week'),(813,'Race Week','Whidbey Island Race Week'),(1046,'Race Week','Whidbey Island Race Week'),
        (1607,'Race Week','Whidbey Island Race Week'),(3013,'Race Week','Whidbey Island Race Week'),(4546,'Race Week','Whidbey Island Race Week'),
        (6142,'Race Week','Whidbey Island Race Week'),(14265,'Race Week','Race Week Anacortes'),(14925,'Race Week','Race Week Anacortes'),(15582,'Race Week','Race Week Anacortes'),(16303,'Race Week','Race Week Anacortes'),(16998,'Race Week','Race Week Bellingham'),(50583,'Race Week','Race Week Bellingham'),
        (16398,'J/Fest','J Fest Seattle')]
async def main():
    out=[]
    async with httpx.AsyncClient(follow_redirects=True,timeout=60) as c:
        p=YachtScoringProvider(c)
        for eid,fam,label in EVENTS:
            url=f"https://www.yachtscoring.com/event_results_cumulative/{eid}"
            info=await p.discover_regatta(url)
            cls=[k for k in info.classes if '105' in k.name]
            if not cls: print(eid,'no J105 class',[k.name for k in info.classes]); continue
            res=await p.fetch(Regatta(source='yachtscoring',source_id=str(eid),name=info.name,url=url,default_class=cls[0].id))
            races=[r for r in res.races if '105' in r.class_name]
            st=[s for s in res.standings if '105' in s.class_name]
            who=collections.defaultdict(collections.Counter); nm={}
            for r in races:
                for f in r.finishes:
                    if f.skipper: who[f.sail_number][f.skipper]+=1
                    if f.boat_name: nm[f.sail_number]=f.boat_name
            year=int(info.name[:4]) if info.name[:4].isdigit() else int((races[0].date if races else '0')[:4])
            st=sorted(st,key=lambda s:(s.place_in_class or 99, s.net_points or 999))
            for i,s in enumerate(st):
                out.append({'event':fam,'series':label,'year':year,'url':url,'sail':s.sail_number,'name':nm.get(s.sail_number,''),
                            'skipper':(who[s.sail_number].most_common(1) or [('',0)])[0][0],'place':s.place_in_class or i+1,'fleet':len(st),'races':len({r.race_number for r in races}),'net':s.net_points})
            print(year,label,len(st),'boats',len({r.race_number for r in races}),'races; sample',[(x['name'],x['skipper'],x['place']) for x in out[-len(st):]][:3])
    json.dump(out,open('ys.json','w'),indent=0)
asyncio.run(main())
