'use strict';
(() => {
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => Number(v || 0).toLocaleString('ja-JP') + '円';
const today = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Tokyo'}).format(new Date());
const param = new URLSearchParams(location.search).get('date');
$('day').value = /^\d{4}-\d{2}-\d{2}$/.test(param || '') ? param : today;
let data, only = false;
function render() {
  if (!data) return;
  $('title').textContent = data.date + ' 全レース';
  $('all').textContent = data.venues.length + '場／' + data.total_races + 'R';
  $('counts').textContent = data.counts.predicted + '／' + data.counts.excluded + '／' + data.counts.error;
  const predictions = data.records.filter(r => r.status === 'predicted').map(r => r.prediction);
  $('buy').textContent = predictions.filter(p => p.total_yen > 0).length + 'R';
  $('money').textContent = money(predictions.reduce((n,p) => n + p.total_yen, 0));
  $('status').textContent = (data.complete ? '全レースの処理完了' : '未判定または開催一覧の取得失敗があります') + '｜更新 ' + new Date(data.created_at).toLocaleString('ja-JP', {timeZone:'Asia/Tokyo'});
  $('venues').innerHTML = (data.discovery_errors || []).map(v => '<div class="message">'+esc(v.name)+'：開催一覧を取得できません。'+esc(v.reason)+'</div>').join('') + data.venues.map(v => {
    const records = data.records.filter(r => r.race_id.slice(8,10) === v.code);
    const selected = records.filter(r => r.prediction?.total_yen > 0);
    const total = selected.reduce((n,r) => n + r.prediction.total_yen, 0);
    return '<section class="venue"><div class="venue-head"><div><h2>'+esc(v.name)+'</h2><small>全'+records.length+'R</small></div><span class="venue-sum">'+selected.length+'R採用・'+money(total)+'</span></div>'+records.filter(r => !only || r.prediction?.total_yen > 0).map(r => {
      const p = r.prediction, buy = p?.total_yen > 0;
      const label = r.status === 'excluded' ? '対象外' : r.status === 'error' ? '未判定' : buy ? 'HIGH採用' : '購入なし';
      const ranking = p ? p.ranked.map(x => x.bike).join(' → ') : '';
      const tickets = p ? ['trifecta','exacta'].map(k => {const b=p.bets[k];return '<div><div class="bethead">'+(k==='trifecta'?'3連単':'2車単')+'｜'+esc(b.label)+'｜'+b.points+'点</div>'+(b.points ? '<div class="combos">'+b.tickets.map(t=>'<span class="combo">'+esc(t.replaceAll('>',' - '))+'</span>').join('')+'</div><div class="tips">各'+money(b.stake_per_ticket_yen)+'／計'+money(b.total_yen)+'</div>' : '<div class="tips">購入なし</div>')+'</div>';}).join('') : '';
      return '<article class="race '+(buy?'buy':'')+'"><div class="race-top"><div><div class="rno">'+r.race_number+'R</div><div class="meta">'+esc(r.start_time||'時刻未取得')+'</div></div><div class="pick"><strong>'+esc(r.race_name||r.velodrome)+'</strong><small>'+esc(r.grade||'')+(p?'｜スコア差 '+Number(p.confidence).toFixed(4):'')+'</small></div><span class="badge '+(buy?'high':'skip')+'">'+label+'</span><span class="amt">'+(p?money(p.total_yen):r.status==='excluded'?'0円':'—')+'</span></div>'+(p?'<details '+(buy?'open':'')+'><summary style="cursor:pointer;font-size:12px;margin:10px 0">買い目・AI順位</summary><div class="bets">'+tickets+'</div><div class="tips">AI順位（車番）：'+esc(ranking)+'<br>'+p.ranked.map(x=>esc(x.rank+'位 '+x.bike+'番 '+x.name)).join(' ／ ')+'<br>予測作成：'+esc(new Date(p.web_record.created_at).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}))+'</div><a href="./?race='+r.race_id+'">個別レース →</a></details>':'<p class="tips">'+esc(r.reason)+'</p>')+'<div class="race-actions"><a href="https://keirin.netkeiba.com/race/entry/?race_id='+r.race_id+'" target="_blank" rel="noopener noreferrer">出走表 ↗</a></div></article>';
    }).join('')+'</section>';
  }).join('');
}
async function load() {
  const day = $('day').value;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return;
  $('status').textContent = '読み込み中…';
  const url = './days/' + day.replaceAll('-','') + '.json';
  $('json').href = url;
  history.replaceState(null,'','?date='+day);
  try {
    const res = await fetch(url+'?v='+Date.now(),{cache:'no-store'});
    if (!res.ok) throw Error(res.status===404 ? 'この日付の全レース一覧はまだ公開されていません。' : 'HTTP '+res.status);
    const incoming = await res.json();
    if (incoming.date !== day || incoming.records.length !== incoming.total_races) throw Error('日付または件数が一致しません');
    data = incoming;
    render();
  } catch(e) {
    data = null;
    $('title').textContent=day+' 全レース';
    for (const id of ['all','counts','buy','money']) $(id).textContent='—';
    $('venues').replaceChildren();
    $('status').textContent=e.message;
  }
}
$('reload').onclick=load;
$('day').onchange=load;
$('filter').onclick=()=>{only=!only;$('filter').textContent=only?'全レースを表示':'購入対象だけ表示';render();};
load();
})();
