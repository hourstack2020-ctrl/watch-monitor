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
let listingComparisonRequest=0,listingComparisonFocus=null,listingComparisonOverflow='';
function closeListingComparison(){
 const overlay=document.getElementById('listingComparisonOverlay');
 if(!overlay||overlay.hidden)return;
 overlay.hidden=true;listingComparisonRequest++;
 document.body.style.overflow=listingComparisonOverflow;
 listingComparisonFocus?.focus({preventScroll:true});
}
function listingComparisonIsOpen(){return document.getElementById('listingComparisonOverlay')?.hidden===false}
function ensureListingComparison(){
 let overlay=document.getElementById('listingComparisonOverlay');
 if(!overlay){
  overlay=document.createElement('div');overlay.id='listingComparisonOverlay';overlay.hidden=true;
  overlay.innerHTML='<div id="listingComparisonDialog" role="dialog" aria-modal="true" aria-labelledby="listingComparisonTitle" tabindex="-1"><div class="top"><h2 id="listingComparisonTitle">與鐘點站同款比價</h2><button type="button" id="listingComparisonClose" aria-label="關閉比價視窗">關閉 ✕</button></div><div id="listingComparisonContent" aria-live="polite"></div></div>';
  document.body.append(overlay);
  document.getElementById('listingComparisonClose').addEventListener('click',closeListingComparison);
  overlay.addEventListener('click',event=>{if(event.target===overlay)closeListingComparison()});
  overlay.addEventListener('keydown',event=>{
   if(event.key==='Escape'){event.preventDefault();closeListingComparison()}
   if(event.key==='Tab'){
    const controls=[...overlay.querySelectorAll('button:not([disabled]),a[href],summary,[tabindex="0"]')];
    const first=controls[0],last=controls[controls.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
   }
  });
 }
 return overlay;
}
// Capture taps so previously rendered inline buttons and newly rendered cards both work.
document.addEventListener('click',event=>{
 const button=event.target.closest?.('.listing-compare');
 if(!button)return;
 event.preventDefault();event.stopPropagation();openListingComparison(button);
},true);
async function openListingComparison(button){
 const overlay=ensureListingComparison();
 if(overlay.hidden){listingComparisonFocus=button;listingComparisonOverflow=document.body.style.overflow;overlay.hidden=false;document.body.style.overflow='hidden'}
 document.getElementById('listingComparisonClose').focus({preventScroll:true});
 const content=document.getElementById('listingComparisonContent'),requestId=++listingComparisonRequest;
 const item={site:button.dataset.site,url:button.dataset.url};
 content.textContent='正在讀取同型號、同面盤商品…';
 try{
  const response=await fetch('/api/comparisons');
  if(!response.ok)throw Error(response.status===401?'登入已過期，請重新登入':'比價資料讀取失敗，請關閉後重試');
  const data=await response.json();
  if(requestId!==listingComparisonRequest||!listingComparisonIsOpen())return;
  const groups=listingComparisonGroups(data,item);
  const selected=all.find(x=>x.site===item.site&&x.url===item.url);
  content.innerHTML=(selected?'<p><b>'+esc(selected.model||'')+'</b> '+esc(selected.site)+'</p>':'')+'<p class="muted">同型號、同面盤比較；年份、錶況與錶帶可不同，請對照各商品資料。</p>';
  if(groups.length){
   content.innerHTML+=groups.map(comparisonGroupMarkup).join('');
  }else content.innerHTML+='<p>目前沒有與鐘點站同型號、同面盤且已確認的比價商品。</p>';
  const pending=(data.review_pairs||[]).filter(p=>[p.baseline,p.other].some(x=>x.site===item.site&&x.url===item.url));
  if(pending.length)content.innerHTML+=`<p class="muted">另有 ${pending.length} 組面盤待確認。<button type="button" onclick="closeListingComparison();location.hash='#comparisonReview';showPageTab('comparison');loadComparisons()">查看待確認商品</button></p>`;
  if(!groups.length&&data.image_pending_count)content.innerHTML+='<p class="muted">部分商品圖片仍在核對中，完成後可重新查看。</p>';
 }catch(error){if(requestId===listingComparisonRequest&&listingComparisonIsOpen())content.textContent=error.message}
}

// Keep the dialog and comparison page on the same information and card layout.
function comparisonGroupMarkup(g){return `<article class="comparison-group"><h3>${esc(g.brand)} ${esc(g.model)}</h3>${comparisonUpdateNotice(g)}${g.manual_review_count?'<p class="muted">含使用者確認的比價組合</p>':''}<p>面盤：${esc(g.dial_color)}｜${g.store_count} 家店・${g.listing_count} 筆商品</p><p class="muted">最低 NT$ ${Number(g.minimum_price).toLocaleString('en-US')}｜最高 NT$ ${Number(g.maximum_price).toLocaleString('en-US')}｜差價 NT$ ${Number(g.spread).toLocaleString('en-US')}</p><div class="comparison-listings">${comparisonListings(g).map(x=>`<div class="comparison-offer${x.site==='鐘點站'?' clock-offer':''}"><h4>${esc(x.site)}</h4>${x.site==='鐘點站'?'<span class="clock-offer-label">鐘點站自家商品</span>':''}${x.image_url?`<img class="offer-image" src="${esc(x.image_url)}" alt="${esc(g.model)} ${esc(x.site)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true">`:''}<p class="offer-price">NT$ ${Number(x.price).toLocaleString('en-US')}</p><p class="offer-spec">${esc(x.year||'年份未提供')}｜${esc(shortCondition(x.condition))}</p><p class="offer-spec">帶身：${esc(x.strap||'未辨識')}</p>${warrantyMarkup(x)}${sameYearConditionBadge(g,x)}<p class="offer-difference ${x.difference_from_lowest===0?'change-down':'change-up'}">${x.difference_from_lowest===0?'組內最低價':'＋NT$ '+Number(x.difference_from_lowest).toLocaleString('en-US')+'（'+x.difference_percent+'%）'}</p><details><summary>完整資料</summary><p>${esc(x.title)}</p><p>錶況：${esc(x.condition||'未提供')}</p><p>更新：${esc(new Date(x.updated).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'}))}</p></details><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">查看${esc(x.site)} ↗</a></div>`).join('')}</div></article>`}
