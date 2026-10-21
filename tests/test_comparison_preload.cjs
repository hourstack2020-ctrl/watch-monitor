const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
(async()=>{
 let calls=0,finish;
 const context={document:{addEventListener(){}},fetch:()=>{calls++;return new Promise(resolve=>finish=resolve)}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('product-comparison.js','utf8'),context);
 const first=context.readComparisonSnapshot(),parallel=context.readComparisonSnapshot(true);
 assert.equal(first,parallel);assert.equal(calls,1);
 const data={groups:[{model:'126710GRNR',listings:[]}]};finish({ok:true,json:async()=>data});
 assert.equal(await first,data);
 assert.equal(await context.readComparisonSnapshot(),data);assert.equal(calls,1);
 const refresh=context.readComparisonSnapshot(true);assert.equal(calls,2);
 assert.equal(await context.readComparisonSnapshot(),data);
 finish({ok:false,status:503});await assert.rejects(refresh,/讀取失敗/);
 assert.equal(await context.readComparisonSnapshot(),data);assert.equal(calls,2);
 const retry=context.readComparisonSnapshot(true);const updated={groups:[]};finish({ok:true,json:async()=>updated});
 assert.equal(await retry,updated);assert.equal(await context.readComparisonSnapshot(),updated);
 console.log('Comparison preload: shared requests, instant cache, refresh and failure retention passed');
})().catch(e=>{console.error(e);process.exit(1)});
