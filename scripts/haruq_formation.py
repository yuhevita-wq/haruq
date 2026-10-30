"""Manual-based formation construction and experimental automatic selection.

Source: keirin_3rentan_formation_manual_latest.pdf (40 pages).
The manual teaches shapes, not numeric selection rules. H1 selection below is
an explicit research hypothesis, never a calibrated probability or BUY signal.
"""
from itertools import product, permutations, combinations
import math

VERSION = 'HARUQ_MANUAL_FORMATION_H1_20261030'
SOURCE = 'libfile_30aa4d12f5e08191990a4239a0fd7780'
MAX_POINTS = 24
STAKE_YEN = 100


def expand(first, second, third, active):
    active = set(active)
    fields = [set(x) for x in (first, second, third)]
    if any(not x or not x <= active for x in fields):
        raise ValueError('着順候補に欠車・未知の車番・空欄があります')
    return tuple(sorted(t for t in product(*fields) if len(set(t)) == 3))


def block(first, second, third, active, reason, pages):
    fields = [sorted(set(x)) for x in (first, second, third)]
    tickets = expand(*fields, active)
    return {'fields': fields, 'notation': '-'.join(''.join(map(str, x)) for x in fields),
            'reason': reason, 'manual_pages': pages, 'tickets': tickets}


def generate_candidates(ranked, lines):
    """Use ranks to nominate candidates, line POSITION only to express relations.

    This does not claim who leads the race or that a teammate must finish second.
    Distinct scenarios remain distinct blocks when combined (manual p20/33).
    """
    bikes = [int(r['bike']) for r in ranked]
    if not 5 <= len(bikes) <= 9 or len(set(bikes)) != len(bikes):
        raise ValueError('出走車番が不完全または重複しています')
    valid = set(bikes)
    flat = [b for line in lines for b in line]
    if len(flat) != len(set(flat)) or set(flat) != valid:
        raise ValueError('全出走車の並びが必要です。未知の並びは推測しません')
    candidates, seen = [], set()

    def add(blocks, family):
        tickets = tuple(sorted(set(t for b in blocks for t in b['tickets'])))
        if 2 <= len(tickets) <= MAX_POINTS and tickets not in seen:
            seen.add(tickets)
            candidates.append({'family': family, 'blocks': blocks, 'tickets': tickets,
                               'points': len(tickets)})

    def make(a,b,c,reason,pages):
        return block(a,b,c,valid,reason,pages)

    for anchor in bikes[:3]:
        others = [b for b in bikes if b != anchor]
        for width in (3,4,5):
            pool = others[:width]
            add([make([anchor],pool,pool,'勝つ候補を固定し相手の順序を残す',[9,10])], 'first_fixed')
            add([make(pool,[anchor],pool,'2着を固定し前後の候補を残す',[16])], 'second_fixed')
            add([make(pool,pool,[anchor],'3着を固定し上位の順序を残す',[17])], 'third_fixed')
        add([make(bikes[:3],bikes[:3],bikes[:4],'勝つ候補を複数残す',[19])], 'multiple_winners')

    # Adjacent line roles, including second/third and third/fourth positions.
    pairs = [(a,b,'同ラインの連携順が隣接する2人')
             for line in lines for a,b in zip(line,line[1:])]
    # Cross-line candidates: each line's highest frozen score, not merely the
    # globally strongest two. This is H1 candidate nomination, not proven flow.
    representatives = [next(b for b in bikes if b in line) for line in lines]
    pairs += [(a,b,'異なるラインの代表候補が上位に入る')
              for a,b in combinations(representatives,2)]
    for a,b,relation in pairs:
        rest = [x for x in bikes if x not in (a,b)]
        for width in sorted(set((min(3,len(rest)),len(rest)))):
            pool = rest[:width]
            pair = make([a,b],[a,b],pool,relation+'。1・2着の順序を残す',[11,14,20])
            add([pair], 'pair_reverse')
            for winner,third in ((a,b),(b,a)):
                sandwich = make([winner],pool,[third],relation+'。一方を3着へ残す',[12,15])
                add([sandwich], 'sandwich')
                add([pair,sandwich], 'pair_plus_sandwich')
                add([make([winner],[third],pool,relation+'。1・2着順を限定する',[13])], 'ordered_pair')
    return candidates


def hypothesis_probabilities(ranked):
    """H1: temperature=1 Plackett-Luce from frozen scores; UNCALIBRATED.

    No odds used as labels. No fabricated line-strength bonus. This baseline
    lacks line interaction and must not be described as the V6 probability AI.
    """
    scores = {int(r['bike']):float(r['score']) for r in ranked}
    if any(not math.isfinite(s) for s in scores.values()):
        raise ValueError('予測スコアが非有限です')
    peak = max(scores.values())
    weights = {b:math.exp(max(-700.,s-peak)) for b,s in scores.items()}
    # Sum remaining weights directly rather than subtraction (extreme scores).
    result = {}
    for a,b,c in permutations(scores,3):
        result[a,b,c] = (weights[a]/sum(weights.values())
            * weights[b]/sum(v for k,v in weights.items() if k != a)
            * weights[c]/sum(v for k,v in weights.items() if k not in (a,b)))
    total = sum(result.values())
    return {t:p/total for t,p in result.items()}


def metrics(tickets, probabilities, odds=None):
    mass = sum(probabilities[t] for t in tickets)
    out = {'coverage_hypothesis':mass, 'points':len(tickets),
           'total_yen':len(tickets)*STAKE_YEN}
    if odds is None or any(t not in odds for t in tickets):
        return {**out,'price_status':'missing','expected_return_ratio_hypothesis':None,
                'composite_odds':None}
    values = [float(odds[t]) for t in tickets]
    if any(not math.isfinite(x) or x <= 1 for x in values):
        raise ValueError('オッズが不正です')
    # Uniform stake: expected return / full investment, not p(set)*one payout.
    ratio = sum(probabilities[t]*odds[t] for t in tickets)/len(tickets)
    return {**out,'price_status':'complete',
            'expected_return_ratio_hypothesis':ratio,
            'expected_net_yen_hypothesis':out['total_yen']*(ratio-1),
            'composite_odds':1/sum(1/x for x in values),
            'minimum_hit_return_ratio':min(values)/len(values)}


def automatic_formation(ranked, lines, *, eligible, odds=None):
    """Always generate and compare; return a research proposal, never live bets.

    H1: at most 24 points, 100 yen uniform. Without complete prices maximize
    probability mass minus 0.01 per point. With complete prices compare whole
    set expected profit subject to composite odds >=3.0 and modeled ROI >1.
    Neither threshold nor the H1 probability mechanism comes from the manual.
    """
    result = {'version':VERSION,'manual_source':SOURCE,
              'validation_status':'unvalidated_hypothesis',
              'probability_method':'uncalibrated_Plackett_Luce_temperature_1',
              'counts_as_purchase':False,'decision':'見送り',
              'stake_per_ticket_yen':STAKE_YEN,'selected':None}
    if not eligible:
        return {**result,'reason':'既存の3連単参加条件を満たさない'}
    if not lines:
        return {**result,'reason':'並びが取得できないため自動選択できない'}
    candidates = generate_candidates(ranked,lines)
    probs = hypothesis_probabilities(ranked)
    for c in candidates:
        c['metrics'] = metrics(c['tickets'],probs,odds)
    priced = [c for c in candidates if c['metrics']['price_status']=='complete']
    viable = [c for c in priced if c['metrics']['composite_odds'] >= 3.0
              and c['metrics']['expected_return_ratio_hypothesis'] > 1]
    if odds is not None and len(priced) != len(candidates):
        return {**result,'reason':'候補全体のオッズが不足している',
                'candidate_count':len(candidates)}
    if odds is not None and not viable:
        return {**result,'reason':'集合全体の価格条件を満たす形がない',
                'candidate_count':len(candidates)}
    if odds is None:
        key = lambda c:(c['metrics']['coverage_hypothesis']-.01*c['points'],-c['points'])
        selected = max(candidates,key=key)
        reason = '自動選択した研究候補。オッズ未取得・未知期間未検証のため購入対象外'
    else:
        selected = max(viable,key=lambda c:(c['metrics']['expected_net_yen_hypothesis'],-c['points']))
        reason = '集合全体の価格で自動選択した研究候補。未知期間未検証のため購入対象外'
    # Explain cost of each block, accounting for overlap with other scenarios.
    selected = dict(selected)
    selected['marginal_blocks'] = []
    for i,b in enumerate(selected['blocks']):
        other = set(t for j,x in enumerate(selected['blocks']) if i!=j for t in x['tickets'])
        extra = set(b['tickets'])-other
        selected['marginal_blocks'].append({'notation':b['notation'],
            'unique_additional_points':len(extra),'additional_cost_yen':len(extra)*STAKE_YEN,
            'additional_coverage_hypothesis':sum(probs[t] for t in extra)})
    def public(c):
        return {**c,'tickets':['>'.join(map(str,t)) for t in c['tickets']],
                'blocks':[{k:v for k,v in b.items() if k!='tickets'} for b in c['blocks']]}
    return {**result,'reason':reason,'candidate_count':len(candidates),
            'selected':public(selected),
            'alternatives':[public(c) for c in sorted(candidates,
                key=lambda c:c['metrics']['coverage_hypothesis']-.01*c['points'], reverse=True)[:5]]}
