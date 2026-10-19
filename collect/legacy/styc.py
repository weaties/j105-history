"""Ballard Cup J/105 final standings 2014-2026 from STYC series pages."""
import re, html, json, urllib.request, time
J105=re.compile(r'J\s*[/-]?\s*105',re.I)
def cells(row): return [html.unescape(re.sub(r'<[^>]+>','',c)).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',row,flags=re.S)]
out=[]
for y in range(2014,2027):
    for s,label in (("SeriesI","I"),("SeriesII","II"),("SeriesIII","III")):
        url=f"https://race.styc.org/race_info/Ballard_Cup/{s}/{y}/series.htm"
        try: page=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=30).read().decode('latin-1')
        except Exception as e: continue
        if len(page)<5000: continue
        # split into class tables by heading text "Class N"
        parts=re.split(r'(?=Class \d+[^<]{0,60})',page)
        rows=[]
        for p in parts:
            m=re.match(r'(Class \d+[^<]{0,60})',p)
            if not m: continue
            cls=html.unescape(m.group(1)).strip()
            hdr=None
            for r in re.findall(r'<tr[^>]*>(.*?)</tr>',p,flags=re.S):
                c=cells(r)
                if 'Boat Name' in c: hdr=c; continue
                if hdr and len(c)>=len(hdr) and c[0]:
                    d=dict(zip(hdr,c)); d['_class']=cls; rows.append(d)
        jr=[d for d in rows if J105.search(d.get('Boat Type',''))]
        if not jr: 
            print(y,s,'no J/105 rows'); continue
        classes={d['_class'] for d in jr}
        # J/105 fleet place: order J/105 rows by their class place (one class) or total
        def num(v):
            try: return float(re.sub(r'[^\d.]','',v) or 'nan')
            except: return float('nan')
        jr.sort(key=lambda d:(num(d.get('Place','')),num(d.get('Total',''))))
        nr=len([h for h in jr[0] if h.startswith('Race ')])
        for i,d in enumerate(jr):
            out.append({'event':'Ballard Cup','series':label,'year':y,'url':url,'sail':d.get('SailNo','').strip(),'name':d['Boat Name'],
                        'skipper':d.get('Skipper',''),'type':d.get('Boat Type',''),'place':i+1,'fleet':len(jr),'races':nr,'net':d.get('Total'),'class':d['_class']})
        print(y,s,len(jr),'J/105s in',classes)
        time.sleep(0.3)
json.dump(out,open('styc.json','w'),indent=0)
