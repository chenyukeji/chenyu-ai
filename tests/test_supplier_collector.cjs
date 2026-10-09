const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const collector = require('../plugins/chenyu-kaifa/skills/chenyu-gongyingshang/scripts/collect-lingxing-1688.cjs');
const offer = collector.parseOffer('123456789');
const png = Buffer.from([137,80,78,71,13,10,26,10,0]);

function fixture() {
  return {code:1,data:[{
    product_id:offer.id,subject:'Test <product>',supplier_login_id:'not-a-company',
    cross_basic_info:{supplierName:'Example Supplier'},category_name:'Test',
    sale_info:{unit:'套',min_order_quantity:1,amount_on_sale:0},
    image:{images:['https://cbu01.alicdn.com/main.png']},
    sku_infos:[
      {sku_id:'9007199254740993',spec_id:'a',price:null,amount_on_sale:0,attributes:[
        {attribute_display_name:'颜色',attribute_value:'黑色',sku_image_url:'https://cbu01.alicdn.com/a.png'},
        {attribute_display_name:'尺寸',attribute_value:'M'}]},
      {sku_id:'9007199254740994',spec_id:'b',price:0,amount_on_sale:6,attributes:[
        {attribute_display_name:'颜色',attribute_value:'黑色'},
        {attribute_display_name:'尺寸',attribute_value:'L'}]},
      {sku_id:'9007199254740995',price:2.5,attributes:[
        {attribute_display_name:'颜色',attribute_value:'红色'},
        {attribute_display_name:'尺寸',attribute_value:'M'}]}
    ]
  }]};
}
function data() {return collector.normalize(fixture(),offer,'2026-10-09T00:00:00Z');}

test('plugin manifests and developer routes include the packaged supplier Skill',()=>{
  const plugin=path.join(__dirname,'..','plugins','chenyu-kaifa');
  const outer=JSON.parse(fs.readFileSync(path.join(plugin,'plugin.json'),'utf8'));
  const inner=JSON.parse(fs.readFileSync(path.join(plugin,'.codex-plugin','plugin.json'),'utf8'));
  assert.equal(outer.version,inner.version); assert.match(outer.version,/^\d+\.\d+\.\d+$/);
  assert.equal(outer.name,inner.name); assert.equal(outer.description,inner.description);
  for(const manifest of [outer,inner]) assert.ok(manifest.interface.capabilities.includes('Read-only Lingxing 1688 supplier collection'));
  assert.equal(outer.skills,'./skills/');
  const supplier=path.join(plugin,'skills','chenyu-gongyingshang');
  for(const name of ['SKILL.md','references/collector.md','scripts/collect-lingxing-1688.cjs','scripts/package.json','agents/openai.yaml']) assert.ok(fs.existsSync(path.join(supplier,name)));
  for(const skill of ['chenyu-kaifa','chenyu-kaifawendang']) assert.ok(fs.readFileSync(path.join(plugin,'skills',skill,'SKILL.md'),'utf8').includes('../chenyu-gongyingshang/SKILL.md'));
  const metadata=fs.readFileSync(path.join(supplier,'agents','openai.yaml'),'utf8');
  assert.ok(metadata.includes('$chenyu-gongyingshang'));
  const dependencies=JSON.parse(fs.readFileSync(path.join(supplier,'scripts','package.json'),'utf8'));
  assert.equal(dependencies.dependencies.playwright,'1.62.1');
});

test('canonical offer links and invalid origins',()=>{
  assert.deepEqual(collector.parseOffer(offer.url+'?tracking=x#fragment'),offer);
  for (const input of ['http://detail.1688.com/offer/123456789.html','https://detail.1688.com.evil.test/offer/123456789.html','https://u:p@detail.1688.com/offer/123456789.html','https://detail.1688.com:8443/offer/123456789.html','123']) assert.throws(()=>collector.parseOffer(input));
});
test('normalization preserves null, zero and string identifiers',()=>{
  const result=data();
  assert.equal(result.variants[0].price,null);
  assert.equal(result.variants[1].price,0);
  assert.equal(result.variants[0].stock,0);
  assert.equal(result.variants[0].skuId,'9007199254740993');
  assert.deepEqual(result.priceRange,{min:0,max:2.5});
  assert.equal(result.supplier.name,'Example Supplier');
  const raw=fixture(); delete raw.data[0].cross_basic_info;
  const missing=collector.normalize(raw,offer);
  assert.equal(missing.supplier.name,'');
  assert.equal(collector.makePack(missing,collector.selectVariants(missing)).warnings.length,1);
});
test('invalid or mismatched response and unsafe SKU identity stop',()=>{
  const cases=[{code:0,msg:'not permitted',data:[]},{code:1,data:[]},fixture(),fixture(),fixture(),fixture(),fixture()];
  cases[2].data[0].subject='';
  cases[3].data[0].sku_infos=[];
  cases[4].data[0].sku_infos[0].sku_id=9007199254740993;
  cases[5].data[0].sku_infos[0].sku_id='';
  cases[6].data[0].sku_infos[1].sku_id=cases[6].data[0].sku_infos[0].sku_id;
  for(const raw of cases) assert.throws(()=>collector.normalize(raw,offer));
});
test('matching uses complete name or all attributes of one SKU',()=>{
  const result=data();
  for(const request of ['黑色 / M',{'颜色':'黑色','尺寸':'M'},{skuId:'9007199254740993'},{specId:'a'}]) {
    const selection=collector.selectVariants(result,request);
    assert.equal(selection.status,'MATCHED');
    assert.equal(selection.selectedVariants[0].skuId,'9007199254740993');
  }
  assert.equal(collector.selectVariants(result,{'颜色':'红色','尺寸':'L'}).status,'NEEDS_CONFIRMATION');
});
test('ambiguity, fuzzy suggestion and ALL never auto select',()=>{
  const result=data();
  const ambiguous=collector.selectVariants(result,{'颜色':'黑色'});
  assert.equal(ambiguous.requests[0].status,'AMBIGUOUS');
  assert.equal(ambiguous.requests[0].candidates.length,2);
  assert.deepEqual(ambiguous.selectedVariants,[]);
  const fuzzy=collector.selectVariants(result,'红色');
  assert.equal(fuzzy.requests[0].status,'NOT_FOUND');
  assert.equal(fuzzy.requests[0].candidates.length,1);
  assert.deepEqual(fuzzy.selectedVariants,[]);
  const all=collector.selectVariants(result);
  assert.equal(all.status,'ALL'); assert.deepEqual(all.selectedVariants,[]);
  const partial=collector.selectVariants(result,['黑色 / M','missing']);
  assert.equal(partial.status,'NEEDS_CONFIRMATION'); assert.equal(partial.selectedVariants.length,1);
  assert.equal(collector.selectVariants(result,['黑色 / M','黑色 / M']).selectedVariants.length,1);
  for(const request of [[],{},' ',{颜色:1},[null]]) assert.throws(()=>collector.selectVariants(result,request));
});
test('report escapes untrusted text and unsafe image URLs',()=>{
  const result=data(); result.variants[0].imageUrl='javascript:alert(1)';
  const html=collector.renderReport(result);
  assert.ok(html.includes('Test &lt;product&gt;'));
  assert.ok(!html.includes('javascript:'));
});
test('output directories never overwrite previous run',()=>{
  const parent=path.join(__dirname,'..','outputs','chenyu-kaifa','_tests');
  fs.mkdirSync(parent,{recursive:true});
  const root=fs.mkdtempSync(path.join(parent,'supplier-'));
  const first=collector.createRunDir(offer.id,undefined,root);
  const second=collector.createRunDir(offer.id,undefined,root);
  assert.match(path.basename(first),/^\d{4}-\d{2}-\d{2}_123456789$/);
  assert.equal(second,first+'_02');
  assert.throws(()=>collector.createRunDir(offer.id,first,root));
  assert.throws(()=>collector.resolveRuntime({workspace:root}));
  assert.equal(collector.resolveRuntime({output:first,profile:path.join(root,'profile')}).profile,path.join(root,'profile'));
  // Generated evidence stays under outputs; no destructive cleanup is needed.
});
test('CDP is explicit local-only and CDN host validation is exact',()=>{
  assert.equal(collector.validateEndpoint('http://127.0.0.1:19388'),'http://127.0.0.1:19388/');
  assert.ok(collector.validateEndpoint('http://[::1]:1234'));
  for(const value of ['http://remote.test:1234','https://127.0.0.1:1234','http://u:p@localhost:1234','http://localhost:1234/path']) assert.throws(()=>collector.validateEndpoint(value));
  assert.ok(collector.imageUrl('https://cbu01.alicdn.com/a.jpg'));
  for(const value of ['https://alicdn.com.evil.test/a.jpg','https://127.0.0.1/a.jpg','http://cbu01.alicdn.com/a.jpg','https://u:p@cbu01.alicdn.com/a.jpg']) assert.throws(()=>collector.imageUrl(value));
});
test('actual response identification works with ID in URL OR request body',()=>{
  const endpoint='https://erp.lingxing.com/api/module/purchase1688/Purchase1688Product/batchGetInfoByProductLink';
  const response=(url,body)=>({url:()=>url,request:()=>({url:()=>url,postData:()=>body})});
  assert.equal(collector.isTargetResponse(response(endpoint+'?productLinks='+encodeURIComponent(offer.url),null),offer),true);
  assert.equal(collector.isTargetResponse(response(endpoint,JSON.stringify({link:offer.url})),offer),true);
  assert.equal(collector.isTargetResponse(response(endpoint,'other'),offer),false);
  assert.equal(collector.isTargetResponse(response(endpoint.replace('erp.lingxing.com','evil.test'),offer.id),offer),false);
  assert.equal(collector.isTargetResponse(response(endpoint+'/other',offer.id),offer),false);
});
test('image signature verification',()=>{
  assert.equal(collector.imageType(png),'png');
  assert.equal(collector.imageType(Buffer.from([255,216,255,0])),'jpg');
  assert.equal(collector.imageType(Buffer.from('GIF89a')),'gif');
  assert.equal(collector.imageType(Buffer.from('RIFF0000WEBP')),'webp');
  assert.throws(()=>collector.imageType(Buffer.from('<html>')));
});
test('image fetch follows only safe redirects, validates MIME and size',async()=>{
  const calls=[];
  const result=await collector.fetchImage('https://cbu01.alicdn.com/a.png',async(url,options)=>{
    calls.push({url,options});
    return calls.length===1 ? new Response(null,{status:302,headers:{location:'/b.png'}}) : new Response(png,{headers:{'content-type':'image/png'}});
  });
  assert.equal(result.extension,'png'); assert.equal(calls.length,2);
  assert.equal(calls[1].url,'https://cbu01.alicdn.com/b.png');
  assert.equal(calls[0].options.redirect,'manual'); assert.equal(calls[0].options.headers,undefined);
  await assert.rejects(collector.fetchImage('https://cbu01.alicdn.com/a.png',async()=>new Response(null,{status:302,headers:{location:'https://127.0.0.1/private'}})));
  await assert.rejects(collector.fetchImage('https://cbu01.alicdn.com/a.png',async()=>new Response('<html>',{headers:{'content-type':'text/html'}})));
  await assert.rejects(collector.fetchImage('https://cbu01.alicdn.com/a.png',async()=>new Response('<html>',{headers:{'content-type':'image/png'}})));
  await assert.rejects(collector.fetchImage('https://cbu01.alicdn.com/a.png',async()=>new Response(png,{headers:{'content-type':'image/png','content-length':String(13*1024*1024)}})));
  await assert.rejects(collector.fetchImage('https://cbu01.alicdn.com/a.png',async()=>new Response(null,{status:302,headers:{location:'/loop.png'}})));
});
