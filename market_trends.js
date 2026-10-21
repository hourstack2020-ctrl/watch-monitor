async function marketResponse(r){
 let d;try{d=await r.json()}catch(e){throw Error('行情服務暫時異常（HTTP '+r.status+'），請稍後重試')}
 if(!r.ok&&r.status!==409)throw Error(d.error||'行情服務暫時異常（HTTP '+r.status+'）');
 return d;
}
const marketVisibleSeries={
  "Patek Philippe 百達翡麗": [
    "Aquanaut",
    "Calatrava",
    "Nautilus",
    "Twenty-4",
    "周年紀念系列",
    "周年紀念系列 Anniversary Series",
    "時計系列 Cubitus",
    "超級複雜功能時計系列 Grand Complications",
    "複雜功能時計系列 Complications"
  ],
  "Audemars Piguet 愛彼": [
    "Royal Oak Concept 皇家橡樹概念系列",
    "Royal Oak 皇家橡樹系列",
    "皇家橡樹系列 Royal Oak",
    "皇家橡樹概念系列 Royal Oak Concept"
  ]
};
function marketSeriesAllowed(brand,series){return !marketVisibleSeries[brand]||marketVisibleSeries[brand].includes(series)}
let marketData=null,marketPoll=null,marketLimit=20;
const marketHKD=value=>'HK$ '+Number(value).toLocaleString('zh-HK');
function marketChart(history){
  if(!history.length)return '<p class="muted">尚無歷史資料</p>';
  const points=history.map(p=>({...p,t:Date.parse(p.date+'T00:00:00Z')}));
  const min=Math.min(...points.map(p=>p.price)),max=Math.max(...points.map(p=>p.price)),pad=Math.max((max-min)*.15,max*.01,1);
  const first=points[0].t,last=points.at(-1).t;
  const x=p=>last===first?12:12+(p.t-first)/(last-first)*296,y=p=>110-(p.price-min+pad)/(max-min+2*pad)*90;
  let paths=[],segment=[];
  for(const p of points){if(segment.length&&p.t-segment.at(-1).t>86400000){paths.push(segment);segment=[]}segment.push(p)}paths.push(segment);
  const line=paths.map(s=>`<polyline points="${s.map(p=>x(p)+','+y(p)).join(' ')}" fill="none" stroke="#315d86" stroke-width="2.5"/>`).join('');
  return `<div class="market-chart" style="position:relative"><svg viewBox="0 0 320 150" role="group" aria-label="每日港幣售價走勢，共 ${points.length} 天，點選資料點查看價格"><line x1="12" y1="120" x2="308" y2="120" stroke="#d5dfeb"/>${line}${points.map(p=>`<g role="button" tabindex="0" aria-label="${esc(p.date)}，查看價格" data-date="${esc(p.date)}" data-price="${p.price}" onclick="selectMarketPoint(event,this)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();selectMarketPoint(event,this)}else if(event.key==='Escape'){hideMarketPrices()}" style="cursor:pointer"><circle cx="${x(p)}" cy="${y(p)}" r="12" fill="transparent"/><circle cx="${x(p)}" cy="${y(p)}" r="3.5" fill="#315d86" pointer-events="none"/></g>`).join('')}<text x="12" y="140" font-size="10" fill="#687d93">${esc(points[0].date)}</text><text x="308" y="140" text-anchor="end" font-size="10" fill="#687d93">${points.length>1?esc(points.at(-1).date):'開始累積'}</text></svg><output class="market-price-tip" hidden aria-live="polite" style="position:absolute;top:0;left:8px;max-width:calc(100% - 16px);box-sizing:border-box;padding:7px 10px;border-radius:8px;background:#172538;color:white;font-size:12px;pointer-events:none"></output></div>`;
}
function hideMarketPrices(){
 document.querySelectorAll('.market-price-tip').forEach(tip=>{tip.hidden=true});
 document.querySelectorAll('.market-chart [aria-pressed]').forEach(point=>point.removeAttribute('aria-pressed'));
}
function selectMarketPoint(event,point){
 event.stopPropagation();
 const selected=point.getAttribute('aria-pressed')==='true';
 hideMarketPrices();
 if(selected)return;
 const tip=point.closest('.market-chart').querySelector('.market-price-tip');
 tip.textContent=point.dataset.date+' · '+marketHKD(point.dataset.price);
 tip.hidden=false;
 point.setAttribute('aria-pressed','true');
}
document.addEventListener('click',hideMarketPrices);
document.addEventListener('keydown',event=>{if(event.key==='Escape')hideMarketPrices()});

function marketOptions(reset=true){
 const brand=$('marketBrand').value,old=$('marketSeries').value;
 const menus=(marketData.source_menu?.menus||[]).filter(x=>!brand||x.brand===brand);
 const series=[...new Set(menus.flatMap(x=>(x.series||[]).filter(s=>marketSeriesAllowed(x.brand,s))))];
 $('marketSeries').innerHTML='<option value="">全部系列</option>'+series.map(s=>`<option>${esc(s)}</option>`).join('');
 $('marketSeries').value=series.includes(old)?old:'';
 updateMarketButton();
 renderMarketTrends(reset);
}
function updateMarketButton(){
 const running=!!marketData?.update_state?.running;
 $('marketRefresh').disabled=running;
 $('marketRefresh').textContent=running?'行情更新中…':$('marketBrand').value?'更新所選品牌':'更新全部品牌';
 const selected=$('marketBrand').value,stamp=marketData?.brand_updates?.[selected]?.updated||marketData?.updated;
 $('marketUpdated').textContent=stamp?'資料更新：'+new Date(stamp).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'})+'｜各品牌獨立發布，每日 12:00 更新':'尚未取得此品牌行情資料';
}
function marketLatestInfo(item){
 // Reading an unchanged quote again does not count as new information.
 const history=[...(item.history||[])].sort((a,b)=>a.date.localeCompare(b.date));
 let latest=history[0]?.date||item.date||'';
 for(let i=1;i<history.length;i++){
  if(Number(history[i].price)!==Number(history[i-1].price))latest=history[i].date;
 }
 if(item.previous_price!=null&&Number(item.price)!==Number(item.previous_price))latest=item.date||latest;
 return Date.parse(latest+'T00:00:00Z')||0;
}
function marketChangePercent(item){
 const previous=Number(item.previous_price),price=Number(item.price);
 return item.previous_price==null||item.price==null||!Number.isFinite(previous)||previous<=0||!Number.isFinite(price)?null:(price-previous)/previous*100;
}
function compareMarketRows(a,b,order,sort){
 if(sort==='percent_desc'||sort==='percent_asc'){
  const left=marketChangePercent(a),right=marketChangePercent(b);
  if(left===null&&right!==null)return 1;
  if(right===null&&left!==null)return -1;
  if(left!==null&&right!==null&&left!==right)return sort==='percent_desc'?right-left:left-right;
 }
 return compareMarketInfo(a,b,order);
}
function compareMarketInfo(a,b,order){
 return marketLatestInfo(b)-marketLatestInfo(a)
  ||order.indexOf(a.brand)-order.indexOf(b.brand)
  ||(a.series==='Nautilus'?0:1)-(b.series==='Nautilus'?0:1)
  ||a.series.localeCompare(b.series)||a.model.localeCompare(b.model)||a.source_id.localeCompare(b.source_id);
}
function renderMarketTrends(reset=true){
 if(reset)marketLimit=20;
 if(!marketData)return;
 const brand=$('marketBrand').value,series=$('marketSeries').value,q=$('marketSearch').value.trim().toLowerCase(),days=Number($('marketDays').value);
 const order=marketData.brands;
 let rows=marketData.items.filter(x=>marketSeriesAllowed(x.brand,x.series)&&(!brand||x.brand===brand)&&(!series||x.series===series)&&(!q||[x.title,x.model,x.series].join(' ').toLowerCase().includes(q)));
 rows.sort((a,b)=>compareMarketRows(a,b,order,$('marketSort').value));
 $('marketCount').textContent=rows.length+' 件';
 const cutoff=Date.parse((marketData.date||'2000-01-01')+'T00:00:00Z')-(days-1)*86400000;
 let heading='';
 $('marketMore').hidden=rows.length<=marketLimit;
 $('marketCards').innerHTML=rows.slice(0,marketLimit).map(x=>{
   let group='';const key=x.brand+'｜'+x.series;if(key!==heading){heading=key;group=`<h3 style="grid-column:1/-1;margin:12px 0 0">${esc(x.brand)} · ${esc(x.series)}</h3>`}
   const change=x.previous_price===null?null:x.price-x.previous_price;
   const changeText=change===null?'尚無前一天資料 · 待累積':change===0?'與前一天持平':`${change>0?'▲ 漲價':'▼ 降價'} ${marketHKD(Math.abs(change))}（${(Math.abs(change)/x.previous_price*100).toFixed(2)}%）`;
   const color=change>0?'#b42318':change<0?'#08784b':'#60748a';
   const itemCutoff=Date.parse((x.date||marketData.date||'2000-01-01')+'T00:00:00Z')-(days-1)*86400000;
   const history=(x.history||[]).filter(p=>Date.parse(p.date+'T00:00:00Z')>=itemCutoff);
   return group+`<article class="market-card"><div class="market-heading">${x.image_url?`<img src="${esc(x.image_url)}" loading="lazy" alt="${esc(x.model)}" onerror="this.hidden=true">`:''}<div><div class="muted">${esc(x.series)}</div><strong>${esc(x.model)}</strong><div class="muted" style="font-size:11px">貨品 ${esc(x.source_id)}</div></div></div><div style="font-size:23px;font-weight:750;margin-top:12px">${marketHKD(x.price)}</div><div style="color:${color};font-weight:700;font-size:14px;margin:8px 0">${changeText}</div>${change!==null?`<div class="muted" style="font-size:12px">前一天 ${marketHKD(x.previous_price)}</div>`:''}${marketChart(history)}<div class="muted" style="font-size:12px">${history.length} 天紀錄 · ${esc(x.date||marketData.date)} · 港幣</div><details style="margin-top:10px"><summary>品相／完整名稱</summary><p style="font-size:13px">${esc(x.title)}</p></details><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-top:12px">查看 VIP Station ↗</a></article>`;
 }).join('')||'<p class="muted">來源目前沒有符合條件的在售公開報價；不以售罄或詢價資料代替。</p>';
}
async function loadMarketTrends(){
 clearTimeout(marketPoll);
 $('marketUpdated').textContent='讀取行情資料…';
 try{
  const r=await fetch('/api/market-trends');const d=await marketResponse(r);marketData=d;
  const selected=$('marketBrand').value;
  $('marketBrand').innerHTML='<option value="">全部品牌</option>'+d.brands.map(b=>`<option>${esc(b)}</option>`).join('');
  $('marketBrand').value=d.brands.includes(selected)?selected:'';
  const state=d.update_state||{};
  $('marketRefresh').disabled=!!state.running;
  $('marketRefresh').textContent=state.running?'行情更新中…':'更新行情';
  $('marketUpdateState').textContent=state.running?(state.progress||'只更新 VIP Station 行情，不會更新原本四家商品。'):state.error||(state.status==='completed'?'行情更新完成':'行情可獨立手動更新');
  if(state.running)marketPoll=setTimeout(loadMarketTrends,4000);
  $('marketUpdated').textContent=d.updated?'資料更新：'+new Date(d.updated).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'})+'｜每日 12:00 更新（台灣時間）':'正在建立首日資料，請稍後重新開啟此頁籤';
  marketOptions(false);
 }catch(e){$('marketUpdated').textContent=e.message;$('marketUpdateState').textContent='尚未確認更新狀態，請稍後重試';$('marketRefresh').disabled=false;$('marketRefresh').textContent=$('marketBrand').value?'更新所選品牌':'更新全部品牌';marketPoll=setTimeout(loadMarketTrends,15000)}
}
async function refreshMarketManually(){
 $('marketRefresh').disabled=true;
 $('marketUpdateState').textContent='正在啟動獨立行情更新…';
 try{
  const slugs={'Patek Philippe 百達翡麗':'patek-philippe','Rolex 勞力士':'rolex','Richard Mille 理查德米勒':'richard-mille','Audemars Piguet 愛彼':'audemars-piguet'};
  const brand=slugs[$('marketBrand').value];
  const r=await fetch('/api/market-trends/refresh',{method:'POST',headers:{'X-Watch-Monitor':'1','Content-Type':'application/json'},body:JSON.stringify(brand?{brand}:{})});
  const d=await marketResponse(r);
  await loadMarketTrends();
 }catch(e){$('marketUpdateState').textContent=e.message;$('marketRefresh').disabled=false}
}
setInterval(()=>{if(document.visibilityState==='visible'&&!document.getElementById('marketPanel').hidden)loadMarketTrends()},60000);
