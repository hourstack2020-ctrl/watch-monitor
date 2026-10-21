// Uncertain pairs wait for official reference verification; no user prompts.
function renderComparisonReviews(data){
 const pending=Number(data.image_pending_count||0);
 comparisonImagePending=pending>0;
 $('comparisonImageReview').textContent=pending?'有 '+pending+' 組商品配對尚待官網核對，暫不列入比價。':'';
}
