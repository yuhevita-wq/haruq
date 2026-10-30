"""Offline automatic formation on one saved HaruQ forecast (no result input).

python -m scripts.haruq_formation_replay --source forecast.json --out result.json
Optional --market JSON: {"race_id":"...", "odds":{"1>2>3":20.5, ...}}.
Only pre-race prices belong here; realized returns are a separate audit.
"""
import argparse
import json
from pathlib import Path
from scripts.haruq_formation import automatic_formation


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--market',type=Path)
    args = p.parse_args()
    source = json.loads(args.source.read_text())
    odds = None
    if args.market:
        market = json.loads(args.market.read_text())
        if market['race_id'] != source['race_id']:
            raise ValueError('オッズのレースIDが不一致')
        odds = {tuple(map(int,k.split('>'))):float(v) for k,v in market['odds'].items()}
    output = automatic_formation(source['ranked'],source.get('line_formation',[]),
        eligible=source['s3_policy']['trifecta_decision']=='BUY',odds=odds)
    args.out.write_text(json.dumps({'race_id':source['race_id'],
        'formation_strategy':output},ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    main()
