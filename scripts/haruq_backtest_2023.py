"""All-universe 2023 replay of frozen HARUQ V5 and manual H1 proposals.

Never retrains, changes thresholds, or calls final odds purchase-time prices.
H1 proposals are hypothetical purchases for this user-requested simulation only.
2023 belongs to the frozen model's training period: this is IN-SAMPLE replay.
"""
import argparse
from collections import Counter,defaultdict
from datetime import date,timedelta
import gzip,hashlib,itertools,json,math,re,sqlite3
from pathlib import Path
import pandas as pd
from scripts.flagship_live_predict import verified_model,strict_tickets
from scripts.haruq_operating_policy import apply_user_policy
from scripts.haruq_formation import automatic_formation,VERSION


class HistoryGuard:
    def __init__(self,con,day):self.con,self.day=con,day
    def execute(self,q,p=()):
        if 'race_results' in q.lower():
            if 'r.date < ?' not in q or self.day not in p or 'rr.rider_id = ?' not in q:
                raise RuntimeError('Current/future result read in inference: STOP')
        return self.con.execute(q,p)


def netid(source):
    if not re.fullmatch(r'\d{16}',source):raise ValueError('Unexpected archive race ID')
    day=date.fromisoformat(source[2:6]+'-'+source[6:8]+'-'+source[8:10])+timedelta(days=int(source[10:12])-1)
    return day.strftime('%Y%m%d')+source[:2]+f'{int(source[12:]):02d}'


def load_calendar(path):
    quotes=defaultdict(list);final=set()
    with gzip.open(path,'rt') as f:
        for line in f:
            obj=json.loads(line);rid=netid(str(obj['race_id']))
            if not rid.startswith('2023'):continue
            quotes[rid].append(obj)
            if '決勝' in str(obj.get('race_type','')):final.add(rid[:10])
    return quotes,final


def settle(tickets,stake,pay,prefix,actual):
    if not tickets:return {'points':0,'investment_yen':0,'returned_yen':0,'status':'no_purchase'}
    combo=tuple(int(x) for x in re.findall(r'\d+',str(pay.get(prefix+'_combo',''))))
    dividend=pay.get(prefix+'_payout')
    if not actual or combo!=actual or dividend is None or not math.isfinite(float(dividend)) or float(dividend)<100:
        return {'points':len(tickets),'planned_investment_yen':len(tickets)*stake,
                'investment_yen':None,'returned_yen':None,'status':'unverified_settlement'}
    hit='>'.join(map(str,actual)) in tickets
    return {'points':len(tickets),'investment_yen':len(tickets)*stake,
            'returned_yen':int(float(dividend)*stake/100) if hit else 0,
            'hit':hit,'status':'settled','actual':actual,'payout_per_100_yen':dividend}


def main():
    p=argparse.ArgumentParser();p.add_argument('--month',required=True)
    p.add_argument('--db',required=True,type=Path);p.add_argument('--model',required=True)
    p.add_argument('--odds',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();assert re.fullmatch('2023-(0[1-9]|1[012])',args.month)
    args.out.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(args.db);con.row_factory=sqlite3.Row
    model,builder=verified_model(args.model)
    con.execute('CREATE INDEX IF NOT EXISTS haruq_replay_rider_race ON race_results(rider_id,race_id)')
    con.execute('CREATE INDEX IF NOT EXISTS haruq_replay_entries_race ON entries(race_id)');con.commit()
    archive,final=load_calendar(args.odds)
    races={r['race_id']:dict(r) for r in con.execute("SELECT * FROM races WHERE date LIKE ? ORDER BY date,race_id",(args.month+'%',))}
    # Actual final-race programme is positive final-day proof; never max(date).
    for row in con.execute("SELECT race_id,round,race_name FROM races WHERE date LIKE '2023-%'"):
        if '決勝' in str(row['round'] or '')+' '+str(row['race_name'] or ''):final.add(row['race_id'][:10])
    ids=sorted(set(races)|{rid for rid in archive if rid[:6]==args.month.replace('-','')})
    stats=Counter();totals=defaultdict(Counter);fout=(args.out/'races.jsonl').open('w')
    policy={'period':['2023-01-01','2023-12-31'],'month':args.month,
        'scope':'ALL_DB_RACES_UNION_ARCHIVED_CALENDAR_NO_VENUE_OR_GRADE_SUBSET',
        'formation_version':VERSION,'model_sha256':hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
        'in_sample':True,'new_training':False,'production_bets_changed':False,
        'h1':'Hypothetically settle default unpriced automatic selection at 100 yen each; preserve V5 entry gate',
        'final_odds':'Used ONLY to audit calendar; default H1 never selects from archived final prices',
        'missing':'Missing inputs/outcomes/payouts are unresolved, never automatic losses',
        'ordering':'record each race before aggregation; no after-result parameter changes'}
    (args.out/'policy.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2))
    def record(row):
        stats[row['status']]+=1
        for variant,markets in row.get('settlements',{}).items():
            for market,obj in markets.items():
                key=variant+'/'+market
                if obj['status']=='settled':
                    totals[key]['settled_races']+=1
                    totals[key]['investment_yen']+=obj['investment_yen']
                    totals[key]['returned_yen']+=obj['returned_yen']
                    totals[key]['hits']+=int(obj['hit'])
                elif obj['status']=='unverified_settlement':totals[key]['unresolved_races']+=1
        fout.write(json.dumps(row,ensure_ascii=False)+'\n');fout.flush()
    print('FULL_YEAR_SHARD_START',args.month,'universe',len(ids),flush=True)
    for index,rid in enumerate(ids):
        meta=races.get(rid);row={'race_id':rid,'date':args.month,'status':'pending'}
        if meta is None:
            record({**row,'status':'missing_race_metadata'});continue
        day=meta['date'];row.update(date=day,grade=meta.get('grade'))
        entries=[dict(e) for e in con.execute('SELECT * FROM entries WHERE race_id=? ORDER BY id',(rid,))]
        if len(entries)!=meta['rider_count'] or not 5<=len(entries)<=9:
            record({**row,'status':'incomplete_entries'});continue
        classes=[str(e['class'] or '') for e in entries]
        if any(c.upper().startswith(('L','Ｌ')) for c in classes) or all(not c or c in ('0','0.0') for c in classes) or 'ガール' in str(meta.get('race_name','')):
            record({**row,'status':'excluded_girls_or_unknown_class'});continue
        if meta['grade'] not in {'F1','F2','G1','G2','G3','GP'}:
            record({**row,'status':'unknown_grade'});continue
        bikes={str(e['rider_id']):e['bike_number'] for e in entries}
        if len(bikes)!=len(entries) or None in bikes.values() or len(set(bikes.values()))!=len(entries):
            record({**row,'status':'invalid_entry_roster'});continue
        # Make historical rider master class match today's entry, as live code does.
        con.execute('SAVEPOINT inference')
        try:
            for e in entries:con.execute('UPDATE riders SET class=? WHERE rider_id=?',(e['class'],e['rider_id']))
            frame=builder.build_race_features(rid,day,HistoryGuard(con,day))
            if set(frame['rider_id'].astype(str))!=set(bikes):raise RuntimeError('Feature/entry roster mismatch')
            frame['bike_number']=frame['rider_id'].astype(str).map(bikes)
            frame['score']=model.predict(frame[builder.feature_names].apply(pd.to_numeric,errors='coerce').fillna(0)).values
            frame=frame.sort_values(['score','bike_number'],ascending=[False,True],kind='stable')
            gap=float(frame.iloc[0]['score']-frame.iloc[1]['score'])
            eligible=strict_tickets(frame,gap,meta['grade'],allow_f2=True)
            confirmed=rid[:10] in final
            proof={'status':'confirmed' if confirmed else 'unverified','is_final_day':True if confirmed else None,
                   'source':'explicit_final_race_programme_on_same_venue_day','race_id':rid}
            operation=apply_user_policy(eligible,grade=meta['grade'],score_gap=gap,meeting_day=proof)
            ranked=[{'bike':int(r.bike_number),'score':round(float(r.score),6)} for r in frame.itertuples()]
            raw=con.execute('SELECT payload FROM source_records WHERE race_id=?',(rid,)).fetchone()
            line_data=json.loads(raw[0]).get('entry',{}).get('line_formation',[]) if raw else []
            lines=[[int(member['bike_number']) for member in line] for line in line_data]
            formation=automatic_formation(ranked,lines,eligible=operation['trifecta_decision']=='BUY')
            row.update(ranked=ranked,score_gap=gap,meeting_day=proof,line_formation=lines,
                legacy_bets=operation['approved_bets'],formation_strategy=formation)
        finally:
            con.execute('ROLLBACK TO inference');con.execute('RELEASE inference')
        # Current outcomes are loaded only AFTER forecast and choice are fixed.
        result=[dict(r) for r in con.execute('SELECT bike_number,finish_position FROM race_results WHERE race_id=?',(rid,))]
        def actual(n):
            positions={i:[r['bike_number'] for r in result if r['finish_position']==i] for i in range(1,n+1)}
            return tuple(positions[i][0] for i in range(1,n+1)) if all(len(x)==1 for x in positions.values()) else None
        payrow=con.execute('SELECT * FROM race_payouts WHERE race_id=?',(rid,)).fetchone();pay=dict(payrow) if payrow else {}
        settlements={}
        legacy=operation['approved_bets']
        settlements['legacy_V5']={k:settle(legacy[k]['tickets'],legacy[k]['stake_per_ticket_yen'],pay,prefix,actual(n))
            for k,prefix,n in [('exacta','nisyatan',2),('trifecta','sanrentan',3)]}
        selected=formation['selected']
        settlements['manual_H1']={'exacta':settlements['legacy_V5']['exacta'],
            'trifecta':settle(selected['tickets'] if selected else [],100,pay,'sanrentan',actual(3))}
        record({**row,'status':'processed','settlements':settlements})
        if index%100==0:print('SHARD_PROGRESS',args.month,index+1,len(ids),dict(stats),flush=True)
    fout.close();con.close()
    report={'month':args.month,'universe':len(ids),'recorded':sum(stats.values()),'statuses':dict(stats),
            'totals':{k:dict(v) for k,v in totals.items()},'all_records_accounted':sum(stats.values())==len(ids),
            'data_complete':set(stats)<= {'processed','excluded_girls_or_unknown_class'}
                and all(v['unresolved_races']==0 for v in totals.values()),
            'model_test_status':'IN_SAMPLE_RETROSPECTIVE_NOT_UNKNOWN_PERIOD'}
    assert report['all_records_accounted']
    (args.out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('FULL_YEAR_SHARD_DONE',args.month,'recorded',report['recorded'],flush=True)


if __name__=='__main__':main()
