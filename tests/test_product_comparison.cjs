const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync('product-comparison.js','utf8'),context);
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
