// Keep uncertain pairs hidden until verification completes; no user prompts.
function renderComparisonReviews(data){
 const pending=Number(data.image_pending_count||0);
 comparisonImagePending=pending>0;
 $('comparisonImageReview').textContent='';
}


