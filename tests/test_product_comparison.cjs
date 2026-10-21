const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context={document:{addEventListener(){}}};vm.createContext(context);vm.runInContext(fs.readFileSync('product-comparison.js','utf8'),context);
for(const [title,want] of [
 ['ROLEX 2026年新式保卡','新式保卡'],['2020年 木紋保卡','木紋保卡'],
 ['2010年紙本保單','紙本保單'],['電子保卡','電子保卡'],['舊式保卡','舊式保卡'],
 ['2026年保卡','未註明'],['2026年','未註明'],['原新式保卡遺失','無保卡'],['無保卡','無保卡'],
 ['','未註明']])assert.equal(context.warrantyStyle({title}),want,title);
const b={site:'鐘點站',url:'b'},o={site:'雷達站',url:'o'},other={site:'永生',url:'o'};
const groups=[{model:'126710GRNR',dial_color:'黑',listings:[b,o]},
 {model:'126710GRNR',dial_color:'白',listings:[b,other]},
 {model:'126710GRNR',dial_color:'黑',listings:[o,other]}];
assert.equal(context.listingComparisonGroups({groups},o).length,1);
assert.equal(context.listingComparisonGroups({groups},b).length,2);
assert.equal(context.listingComparisonGroups({groups},{site:'其他',url:'o'}).length,0);
assert.equal(context.listingComparisonGroups({},o).length,0);
console.log('Product comparison selection and warranty styles: passed');
context.esc=value=>String(value??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
context.comparisonUpdateNotice=()=>'<p>更新時間：今日</p>';
context.comparisonListings=g=>g.listings;
context.shortCondition=value=>value;
context.sameYearConditionBadge=()=>'<span>同年份同錶況</span>';
const markup=context.comparisonGroupMarkup({brand:'Rolex',model:'126710GRNR',dial_color:'黑',store_count:2,listing_count:2,minimum_price:600000,maximum_price:650000,spread:50000,listings:[{site:'鐘點站',url:'https://example.com/b',title:'新式保卡 <test>',year:'2026',condition:'9成9新',strap:'五株鍊帶',price:600000,difference_from_lowest:0,updated:'2026-10-21T13:00:00Z'},{site:'雷達站',url:'https://example.com/o',title:'紙本保單',price:650000,difference_from_lowest:50000,difference_percent:8.3,updated:'2026-10-21T13:00:00Z'}]});
for(const value of ['offer-price','offer-spec','offer-difference','鐘點站自家商品','五株鍊帶','新式保卡','組內最低價','50,000','8.3%','完整資料','更新時間：今日','同年份同錶況','&lt;test>'])assert.ok(markup.includes(value),value);
assert.ok(!markup.includes('<test>'));
console.log('Shared comparison card information and escaping: passed');
