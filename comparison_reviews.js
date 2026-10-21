let comparisonReviewPairs=new Map();
function renderComparisonReviews(data){
 const pairs=data.review_pairs||[];
 comparisonReviewPairs=new Map(pairs.map(p=>[p.pair_key,p]));
 comparisonImagePending=Number(data.image_pending_count||0)>0;
 const card=x=>`<div><b>${esc(x.site)}</b>${x.image_url?`<img src="${esc(x.image_url)}" alt="${esc(x.model||'手錶')}" loading="lazy" referrerpolicy="no-referrer" style="width:100%;height:86px;object-fit:contain;margin:6px 0">`:''}<div style="font-weight:700">NT$ ${Number(x.price).toLocaleString('en-US')}</div><div class="muted" style="font-size:12px">${esc(x.year||'年份未提供')}｜${esc(x.condition||'錶況未提供')}</div>${warrantyMarkup(x)}<details><summary>商品資料</summary><p>${esc(x.title)}</p><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">查看${esc(x.site)} ↗</a></details></div>`;
 $('comparisonImageReview').innerHTML=`<p id="comparisonReviewStatus" role="status" style="color:#315d86"></p>${comparisonImagePending?`<p class="muted">另有 ${Number(data.image_pending_count)} 組圖片核對中，完成後會自動更新。</p>`:''}${pairs.length?`<details id="comparisonReview" ${location.hash==='#comparisonReview'?'open':''} style="margin-top:16px;padding:12px;background:#fff8e7;border-radius:12px"><summary>待確認比價 ${pairs.length} 組</summary><p class="muted">請對照兩件商品。需要比價就保留，不需要則移除此組合；相同資料不會重複詢問。</p>${pairs.slice(0,30).map(p=>`<article style="background:white;border:1px solid #dce4ed;border-radius:12px;padding:12px;margin:12px 0"><h4 style="margin:0 0 6px">${esc(p.model)}｜${esc(p.dial_color)}</h4><p class="muted" style="font-size:13px">${esc(p.reason)}</p><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">${card(p.baseline)}${card(p.other)}</div><div style="display:flex;gap:10px;margin-top:12px"><button data-pair-key="${esc(p.pair_key)}" onclick="decideComparison(this,'approved')" style="flex:1;background:#e5f7ed;color:#08784b">需要比價</button><button data-pair-key="${esc(p.pair_key)}" onclick="decideComparison(this,'rejected')" style="flex:1">不需要，移除</button></div></article>`).join('')}${pairs.length>30?'<p>先顯示前 30 組，確認後會繼續列出其他組合。</p>':''}</details>`:''}`;
 if(location.hash==='#comparisonReview'&&$('comparisonReview'))$('comparisonReview').scrollIntoView({block:'start'});
}
async function decideComparison(button,decision){
 const pair=comparisonReviewPairs.get(button.dataset.pairKey);
 if(!pair){$('comparisonReviewStatus').textContent='資料已更新，請重新選擇';return}
 const buttons=button.parentElement.querySelectorAll('button');buttons.forEach(x=>x.disabled=true);
 try{
  const r=await fetch('/api/comparison-review',{method:'POST',headers:{'Content-Type':'application/json','X-Watch-Monitor':'1'},body:JSON.stringify({pair_key:pair.pair_key,baseline_url:pair.baseline.url,other_site:pair.other.site,other_url:pair.other.url,decision})});
  const d=await r.json().catch(()=>null);if(!r.ok)throw Error(d?.error||'儲存失敗，請稍後重試');
  await loadComparisons();$('comparisonReviewStatus').textContent=decision==='approved'?'已確認，加入比價。':'已移除此比價組合，相同資料不再詢問。';
 }catch(e){$('comparisonReviewStatus').textContent=e.message;buttons.forEach(x=>x.disabled=false)}
}
