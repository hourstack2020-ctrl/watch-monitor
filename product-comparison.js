/* Shared product details and per-listing comparison dialog. */
function warrantyStyle(item){
 const text=String(item?.title||'').normalize('NFKC').replace(/\s+/g,'');
 if(/無(?:原廠)?保卡|無保單|無保證書|不附保卡|保卡遺失|保單遺失|單錶無附件/.test(text))return '無保卡';
 const styles=[];
 if(/新式保卡|新版保卡|新款保卡/.test(text))styles.push('新式保卡');
 if(/舊式保卡|舊版保卡|舊款保卡/.test(text))styles.push('舊式保卡');
 if(/木紋(?:式)?保卡/.test(text))styles.push('木紋保卡');
 if(/電子(?:式)?保卡|電子保單|電子保證書/.test(text))styles.push('電子保卡');
 if(/紙(?:本|質|式)?(?:保卡|保單|保證書)/.test(text))styles.push('紙本保單');
 return styles.length?styles.join('／'):'未註明';
}
function warrantyMarkup(item){return '<span class="warranty-style">保卡樣式：'+esc(warrantyStyle(item))+'</span>'}
function listingComparisonButton(item){return `<button type="button" class="listing-compare" data-site="${esc(item.site||'鐘點站')}" data-url="${esc(item.url)}" onclick="openListingComparison(this)">與鐘點站同款比價</button>`}
function listingComparisonGroups(data,item){
 return (data.groups||[]).filter(g=>g.listings.some(x=>x.site===item.site&&x.url===item.url)&&g.listings.some(x=>x.site==='鐘點站'));
}
let listingComparisonRequest=0;
async function openListingComparison(button){
 let dialog=document.getElementById('listingComparisonDialog');
 if(!dialog){
  dialog=document.createElement('dialog');dialog.id='listingComparisonDialog';dialog.setAttribute('aria-labelledby','listingComparisonTitle');
  dialog.innerHTML='<div class="top"><h2 id="listingComparisonTitle">與鐘點站同款比價</h2><button type="button" onclick="document.getElementById(\'listingComparisonDialog\').close()" aria-label="關閉比價視窗">關閉 ✕</button></div><div id="listingComparisonContent" aria-live="polite"></div>';
  document.body.append(dialog);
  dialog.addEventListener('close',()=>listingComparisonRequest++);
 }
 const content=document.getElementById('listingComparisonContent'),requestId=++listingComparisonRequest;
 const item={site:button.dataset.site,url:button.dataset.url};
 content.textContent='正在讀取同型號、同面盤商品…';
 if(!dialog.open)dialog.showModal();
 try{
  const response=await fetch('/api/comparisons');
  if(!response.ok)throw Error(response.status===401?'登入已過期，請重新登入':'比價資料讀取失敗，請關閉後重試');
  const data=await response.json();
  if(requestId!==listingComparisonRequest||!dialog.open)return;
  const groups=listingComparisonGroups(data,item);
  const selected=all.find(x=>x.site===item.site&&x.url===item.url);
  content.innerHTML=(selected?'<p><b>'+esc(selected.model||'')+'</b> '+esc(selected.site)+'</p>':'')+'<p class="muted">同型號、同面盤比較；年份、錶況與錶帶可不同，請對照各商品資料。</p>';
  if(groups.length){
   content.innerHTML+=groups.map(g=>`<section class="comparison-group"><h3>${esc(g.brand)} ${esc(g.model)}</h3><p>面盤：${esc(g.dial_color)}</p><div class="comparison-listings">${comparisonListings(g).map(x=>`<article class="comparison-offer${x.site==='鐘點站'?' clock-offer':''}"><h4>${esc(x.site)}</h4>${x.site==='鐘點站'?'<span class="clock-offer-label">鐘點站自家商品</span>':''}${x.site===item.site&&x.url===item.url?'<p class="offer-spec">目前選取商品</p>':''}${comparisonCard(x)}${sameYearConditionBadge(g,x)}<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">查看商品 ↗</a></article>`).join('')}</div></section>`).join('');
  }else content.innerHTML+='<p>目前沒有與鐘點站同型號、同面盤且已確認的比價商品。</p>';
  const pending=(data.review_pairs||[]).filter(p=>[p.baseline,p.other].some(x=>x.site===item.site&&x.url===item.url));
  if(pending.length)content.innerHTML+=`<p class="muted">另有 ${pending.length} 組面盤待確認。<button type="button" onclick="document.getElementById('listingComparisonDialog').close();location.hash='#comparisonReview';showPageTab('comparison');loadComparisons()">查看待確認商品</button></p>`;
  if(!groups.length&&data.image_pending_count)content.innerHTML+='<p class="muted">部分商品圖片仍在核對中，完成後可重新查看。</p>';
 }catch(error){if(requestId===listingComparisonRequest&&dialog.open)content.textContent=error.message}
}
