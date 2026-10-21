// Comparison candidates are shown directly; no approval controls or prompts.
function renderComparisonReviews(data){
 comparisonImagePending=Number(data.image_pending_count||0)>0;
 $('comparisonImageReview').textContent='';
}
