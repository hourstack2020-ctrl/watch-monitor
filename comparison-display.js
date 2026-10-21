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
// Shared display helpers for the original comparison page.
function comparisonGroupMarkup(g){return `<article class="comparison-group"><h3>${esc(g.brand)} ${esc(g.model)}</h3>${comparisonUpdateNotice(g)}<p>面盤：${esc(g.dial_color)}｜${g.store_count} 家店・${g.listing_count} 筆商品</p><p class="muted">最低 NT$ ${Number(g.minimum_price).toLocaleString('en-US')}｜最高 NT$ ${Number(g.maximum_price).toLocaleString('en-US')}｜差價 NT$ ${Number(g.spread).toLocaleString('en-US')}</p><div class="comparison-listings">${comparisonListings(g).map(x=>`<div class="comparison-offer${x.site==='鐘點站'?' clock-offer':''}"><h4>${esc(x.site)}</h4>${x.comparison_note?`<p class="offer-spec">${esc(x.comparison_note)}</p>`:''}${x.site==='鐘點站'?'<span class="clock-offer-label">鐘點站自家商品</span>':''}${x.image_url?`<img class="offer-image" src="${esc(x.image_url)}" alt="${esc(g.model)} ${esc(x.site)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true">`:''}<p class="offer-price">NT$ ${Number(x.price).toLocaleString('en-US')}</p><p class="offer-spec">${esc(x.year||'年份未提供')}｜${esc(shortCondition(x.condition))}</p><p class="offer-spec">帶身：${esc(x.strap||'未辨識')}</p><p class="offer-spec">錶圈：${esc(x.bezel||'未辨識')}<br>核對：${esc(x.bezel_method||'未辨識')}</p>${x.official_source_url?`<p class="offer-spec"><a href="${esc(x.official_source_url)}" target="_blank" rel="noopener noreferrer">官方規格已核對 ↗</a><br>${esc(new Date(x.official_checked_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'}))}</p>`:''}${warrantyMarkup(x)}${sameYearConditionBadge(g,x)}<p class="offer-difference ${x.difference_from_lowest===0?'change-down':'change-up'}">${x.difference_from_lowest===0?'組內最低價':'＋NT$ '+Number(x.difference_from_lowest).toLocaleString('en-US')+'（'+x.difference_percent+'%）'}</p><details><summary>完整資料</summary><p>${esc(x.title)}</p><p>錶況：${esc(x.condition||'未提供')}</p><p>更新：${esc(new Date(x.updated).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'}))}</p></details><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">查看${esc(x.site)} ↗</a></div>`).join('')}</div></article>`}

