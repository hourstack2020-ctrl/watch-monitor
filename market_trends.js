let marketData=null,marketPoll=null;
const marketHKD=value=>'HK$ '+Number(value).toLocaleString('zh-HK');
function marketChart(history){
  if(!history.length)return '<p class="muted">尚無歷史資料</p>';
  const points=history.map(p=>({...p,t:Date.parse(p.date+'T00:00:00Z')}));
  const min=Math.min(...points.map(p=>p.price)),max=Math.max(...points.map(p=>p.price)),pad=Math.max((max-min)*.15,max*.01,1);
  const first=points[0].t,last=points.at(-1).t;
  const x=p=>last===first?174:54+(p.t-first)/(last-first)*246,y=p=>110-(p.price-min+pad)/(max-min+2*pad)*90;
  let paths=[],segment=[];
  for(const p of points){if(segment.length&&p.t-segment.at(-1).t>86400000){paths.push(segment);segment=[]}segment.push(p)}paths.push(segment);
  const line=paths.map(s=>`<polyline points="${s.map(p=>x(p)+','+y(p)).join(' ')}" fill="none" stroke="#315d86" stroke-width="2.5"/>`).join('');
  return `<svg viewBox="0 0 320 150" role="img" aria-label="每日港幣售價走勢，共 ${points.length} 天"><line x1="54" y1="120" x2="300" y2="120" stroke="#d5dfeb"/><text x="0" y="24" font-size="10" fill="#687d93">${Math.round(max).toLocaleString('zh-HK')}</text><text x="0" y="112" font-size="10" fill="#687d93">${Math.round(min).toLocaleString('zh-HK')}</text>${line}${points.map(p=>`<circle cx="${x(p)}" cy="${y(p)}" r="3.5" fill="#315d86"><title>${esc(p.date)}：${marketHKD(p.price)}</title></circle>`).join('')}<text x="54" y="140" font-size="10" fill="#687d93">${esc(points[0].date)}</text><text x="300" y="140" text-anchor="end" font-size="10" fill="#687d93">${points.length>1?esc(points.at(-1).date):'開始累積'}</text></svg>`;
}
function marketOptions(){
 const brand=$('marketBrand').value,old=$('marketSeries').value;
 const series=[...new Set(marketData.items.filter(x=>!brand||x.brand===brand).map(x=>x.series))].sort();
 $('marketSeries').innerHTML='<option value="">全部系列</option>'+series.map(s=>`<option>${esc(s)}</option>`).join('');
 $('marketSeries').value=series.includes(old)?old:'';
 renderMarketTrends();
}
function renderMarketTrends(){
 if(!marketData)return;
 const brand=$('marketBrand').value,series=$('marketSeries').value,q=$('marketSearch').value.trim().toLowerCase(),days=Number($('marketDays').value);
 const order=marketData.brands;
 let rows=marketData.items.filter(x=>(!brand||x.brand===brand)&&(!series||x.series===series)&&(!q||[x.title,x.model,x.series].join(' ').toLowerCase().includes(q)));
 rows.sort((a,b)=>order.indexOf(a.brand)-order.indexOf(b.brand)||(a.series==='Nautilus'?0:1)-(b.series==='Nautilus'?0:1)||a.series.localeCompare(b.series)||a.model.localeCompare(b.model)||a.source_id.localeCompare(b.source_id));
 $('marketCount').textContent=rows.length+' 件';
 const cutoff=Date.parse((marketData.date||'2000-01-01')+'T00:00:00Z')-(days-1)*86400000;
 let heading='';
 $('marketCards').innerHTML=rows.map(x=>{
   let group='';const key=x.brand+'｜'+x.series;if(key!==heading){heading=key;group=`<h3 style="grid-column:1/-1;margin:12px 0 0">${esc(x.brand)} · ${esc(x.series)}</h3>`}
   const change=x.previous_price===null?null:x.price-x.previous_price;
   const changeText=change===null?'尚無前一天資料 · 待累積':change===0?'與前一天持平':`${change>0?'▲ 漲價':'▼ 降價'} ${marketHKD(Math.abs(change))}（${(Math.abs(change)/x.previous_price*100).toFixed(2)}%）`;
   const color=change>0?'#b42318':change<0?'#08784b':'#60748a';
   const history=(x.history||[]).filter(p=>Date.parse(p.date+'T00:00:00Z')>=cutoff);
   return group+`<article class="market-card"><div class="market-heading">${x.image_url?`<img src="${esc(x.image_url)}" loading="lazy" alt="${esc(x.model)}" onerror="this.hidden=true">`:''}<div><div class="muted">${esc(x.series)}</div><strong>${esc(x.model)}</strong><div class="muted" style="font-size:11px">貨品 ${esc(x.source_id)}</div></div></div><div style="font-size:23px;font-weight:750;margin-top:12px">${marketHKD(x.price)}</div><div style="color:${color};font-weight:700;font-size:14px;margin:8px 0">${changeText}</div>${change!==null?`<div class="muted" style="font-size:12px">前一天 ${marketHKD(x.previous_price)}</div>`:''}${marketChart(history)}<div class="muted" style="font-size:12px">${history.length} 天紀錄 · ${esc(marketData.date)} · 港幣</div><details style="margin-top:10px"><summary>品相／完整名稱</summary><p style="font-size:13px">${esc(x.title)}</p></details><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-top:12px">查看 VIP Station ↗</a></article>`;
 }).join('')||'<p class="muted">來源目前沒有符合條件的在售公開報價；不以售罄或詢價資料代替。</p>';
}
async function loadMarketTrends(){
 clearTimeout(marketPoll);
 $('marketUpdated').textContent='讀取行情資料…';
 try{
  const r=await fetch('/api/market-trends');const d=await r.json();if(!r.ok)throw Error(d.error||'讀取失敗');marketData=d;
  const selected=$('marketBrand').value;
  $('marketBrand').innerHTML='<option value="">全部品牌</option>'+d.brands.map(b=>`<option>${esc(b)}</option>`).join('');
  $('marketBrand').value=d.brands.includes(selected)?selected:'';
  const state=d.update_state||{};
  $('marketRefresh').disabled=!!state.running;
  $('marketRefresh').textContent=state.running?'行情更新中…':'更新行情';
  $('marketUpdateState').textContent=state.running?'只更新 VIP Station 行情，不會更新原本四家商品。':state.error||(state.status==='completed'?'行情更新完成':'行情可獨立手動更新');
  if(state.running)marketPoll=setTimeout(loadMarketTrends,4000);
  $('marketUpdated').textContent=d.updated?'資料更新：'+new Date(d.updated).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'})+'｜每日 12:00 更新（台灣時間）':'正在建立首日資料，請稍後重新開啟此頁籤';
  marketOptions();
 }catch(e){$('marketUpdated').textContent='行情資料暫時無法讀取：'+e.message}
}
async function refreshMarketManually(){
 $('marketRefresh').disabled=true;
 $('marketUpdateState').textContent='正在啟動獨立行情更新…';
 try{
  const r=await fetch('/api/market-trends/refresh',{method:'POST',headers:{'X-Watch-Monitor':'1'}});
  const d=await r.json();if(!r.ok&&r.status!==409)throw Error(d.error||'啟動失敗');
  await loadMarketTrends();
 }catch(e){$('marketUpdateState').textContent=e.message;$('marketRefresh').disabled=false}
}
setInterval(()=>{if(document.visibilityState==='visible'&&!document.getElementById('marketPanel').hidden)loadMarketTrends()},60000);
