import json
t=open('series_template.html').read()
URL={
 "2026-cyc":("https://cycseattle.org/regatta/wYFzQvmG4R/results","Clubspot"),
 "2025-cyc":("https://cycseattle.org/regatta/ueeOn9VRev/results","Clubspot"),
 "2026-rw":("https://www.yachtscoring.com/event_results_cumulative/50583","Yacht Scoring"),
 "2025-rw":("https://www.yachtscoring.com/event_results_cumulative/16998","Yacht Scoring"),
}
for y in ("2025","2026"):
    for k,s in (("bc1","SeriesI"),("bc2","SeriesII"),("bc3","SeriesIII")):
        URL[f"{y}-{k}"]=(f"https://race.styc.org/race_info/Ballard_Cup/{s}/{y}/series.htm","Sloop Tavern YC")
def load(path,year,bcfile=None):
    d=json.load(open(path))
    if bcfile:
        bc=json.load(open(bcfile))
        d['series']=[s if s['key']=='cyc' else {**s,**{k:bc[s['key']][k] for k in ('races','boats')}} for s in d['series']]
    for s in d['series']:
        s['key']=f"{year}-{s['key']}"
        s['url'],s['source']=URL[s['key']]
        for b in s['boats']: b.pop('place',None)
    return d['series']
mw=load('series_mw.json','2026')+load('y2025/series_mw.json','2025','y2025/bc_series.json')
rw=load('series_rw.json','2026')+load('y2025/series_rw.json','2025')
shorts={"cyc":"W","bc1":"I·","bc2":"II·","bc3":"III·"}
for s in mw: s['short']=shorts[s['key'].split('-',1)[1]]
for s in rw: s['short']=''
def mwviews(y):
    p=lambda k:f"{y}-{k}"
    return [{"key":p("cyc"),"kind":"cyc","year":y,"group":"Wednesdays","label":"CYC season","title":f"the {y} CYC Wednesday season","series":[p("cyc")]},
      {"key":p("bc"),"kind":"bc","year":y,"group":"Ballard Cup","label":"All three","title":f"all three {y} Ballard Cup series","series":[p("bc1"),p("bc2"),p("bc3")]},
      {"key":p("bc1"),"kind":"bc1","year":y,"group":"Ballard Cup","label":"Series I","title":f"{y} Ballard Cup Series I","series":[p("bc1")]},
      {"key":p("bc2"),"kind":"bc2","year":y,"group":"Ballard Cup","label":"Series II","title":f"{y} Ballard Cup Series II","series":[p("bc2")]},
      {"key":p("bc3"),"kind":"bc3","year":y,"group":"Ballard Cup","label":"Series III","title":f"{y} Ballard Cup Series III","series":[p("bc3")]},
      {"key":p("season"),"kind":"season","year":y,"group":"Whole season","label":"CYC + Ballard Cup","title":f"CYC Wednesdays and the Ballard Cup in {y}","series":[p("cyc"),p("bc1"),p("bc2"),p("bc3")]}]
def page(out,title,eyebrow,heading,lede,footer,series,views):
    h=(t.replace('__TITLE__',title).replace('__EYEBROW__',eyebrow).replace('__HEADING__',heading).replace('__LEDE__',lede).replace('__FOOTER__',footer)
       .replace('__DATA__',json.dumps({'series':series},separators=(',',':'),ensure_ascii=False)).replace('__VIEWS__',json.dumps(views,ensure_ascii=False)))
    open(out,'w').write(h)
page('series-mw.html','Puget Sound J/105 Series','J/105 · Puget Sound weeknight racing · 2025 and 2026','Monday and Wednesday series',
 'J/105 standings from CYC Wednesdays and the Ballard Cup on Mondays. Pick a year, then a single series, all three Ballard Cup series together, or the whole season. Pick boats to follow them; the first boat you pick is the baseline the others are compared against.',
 '<p>CYC Sound Wednesday Night Series results from Clubspot with Clubspot\'s own throwouts: 43 races scored in 2026 (races 6, 15, 18 and 33 not sailed) and 39 in 2025. Some 2025 race dates are taken from when the race was entered in Clubspot.</p>'
 '<p>Ballard Cup results from Sloop Tavern YC. In 2026 the J/105s sailed Division 6 in Series I and Division 7 in Series II and III; race scores are rebuilt from corrected times (low point, ties sharing places, DNC as entries + 1, DNS, DNF or RET as boats that came to the start + 1, one throwout) and match the official totals for every boat. In 2025 the J/105s sailed Division 6 and the scores are STYC\'s published race-by-race scores. Boat names follow each year\'s results (for example Double Trouble in 2025 became Debonair in 2026); "Mazu (Counterpoint)" and "Creative / Bluelight" are entry names used in one series.</p>'
 '<p>Charts follow the running total before throwouts; the final column and the table rank on net points after throwouts. When series are combined, a boat that was not entered in one of them takes that series\' DNC score for each of its races and the usual number of throwouts, shown as – in the table. Race Week has its own page.</p>'
 '<p>Codes: DNC did not come to the start, DNS did not start, DNF did not finish, RET retired, OCS on course side, DSQ disqualified, ZFP 20% penalty, SCP scoring penalty, CB as scored by STYC.</p>',
 mw, mwviews("2026")+mwviews("2025"))
page('race-week.html','Race Week Bellingham','J/105 one design · Bellingham Race Week · 2025 and 2026','Race Week standings',
 'J/105 one design at Bellingham Race Week: 11 boats and 12 races in 2026, 10 boats and 15 races in 2025, one throwout each year. Pick boats to follow them; the first boat you pick is the baseline the others are compared against.',
 '<p>Results from Yacht Scoring, J/105 class. Charts follow the running total before the throwout; the final column and the table rank on net points after the throwout, and match the official series totals for both years. Boat names follow each year\'s results.</p><p>Codes: DNC did not come to the start, DNS did not start, DNF did not finish, RET retired, OCS on course side, DSQ disqualified, UFD black flag, NSC did not sail the course, SCP scoring penalty.</p>',
 rw,[{"key":"2026-rw","kind":"rw","year":"2026","group":"","label":"Race Week","title":"Race Week 2026","series":["2026-rw"]},{"key":"2025-rw","kind":"rw","year":"2025","group":"","label":"Race Week","title":"Race Week 2025","series":["2025-rw"]}])
print('generated')
