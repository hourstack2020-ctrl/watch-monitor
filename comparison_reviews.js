// Include uncertain pairs with a note; no user prompts.
function renderComparisonReviews(data){
 const pending=Number(data.image_pending_count||0);
 comparisonImagePending=pending>0;
 $('comparisonImageReview').textContent=pending?'已列入 '+pending+' 組待核對商品配對，資料不足或圖文差異已標示，官網核對持續進行。':'';
}

