const fs = require('node:fs');
const path = require('node:path');
const PRODUCT_PAGE = 'https://erp.lingxing.com/erp/productManage';
const PARSE_PATH = '/api/module/purchase1688/Purchase1688Product/batchGetInfoByProductLink';

function parseOffer(input) {
  if (/^\d{6,20}$/.test(input || '')) return { id: input, url: `https://detail.1688.com/offer/${input}.html` };
  let url;
  try { url = new URL(input); } catch { throw new Error('请输入1688商品链接或商品编号。'); }
  const match = url.pathname.match(/^\/offer\/(\d{6,20})\.html$/);
  if (url.protocol !== 'https:' || url.hostname !== 'detail.1688.com' || url.username || url.password || url.port || !match) {
    throw new Error('仅支持https://detail.1688.com/offer/商品编号.html形式的链接。');
  }
  return { id: match[1], url: `https://detail.1688.com/offer/${match[1]}.html` };
}

function normalize(payload, offer, capturedAt = new Date().toISOString()) {
  if (payload.code !== 1 || !Array.isArray(payload.data)) throw new Error(`领星解析失败：${payload.msg || '响应结构已变化'}`);
  const product = payload.data.find(p => String(p.product_id) === offer.id);
  if (!product) throw new Error('返回结果不包含目标商品，已停止导出。');
  if (!product.subject || !Array.isArray(product.sku_infos) || !product.sku_infos.length) {
    throw new Error('领星未返回商品名称或规格数据，已停止导出。');
  }
  const variants = product.sku_infos.map(sku => ({
    skuId: String(sku.sku_id || ''), specId: sku.spec_id || '',
    attributes: (sku.attributes || []).map(a => ({
      id: a.attribute_id, name: a.attribute_display_name || '', value: a.attribute_value || '', imageUrl: a.sku_image_url || null
    })),
    name: (sku.attributes || []).map(a => a.attribute_value).filter(Boolean).join(' / '),
    imageUrl: (sku.attributes || []).find(a => a.sku_image_url)?.sku_image_url || null,
    price: sku.price ?? null, consignPrice: sku.consign_price ?? null, retailPrice: sku.retail_price ?? null,
    stock: sku.amount_on_sale ?? null, cargoNumber: sku.cargo_number || ''
  }));
  if (variants.some(v => !v.skuId) || product.sku_infos.some(v => typeof v.sku_id === 'number' && !Number.isSafeInteger(v.sku_id))) throw new Error('缺少或不安全的SKU编号，无法可靠匹配。');
  const ids = variants.map(v => v.skuId);
  if (new Set(ids).size !== ids.length) throw new Error('响应包含重复SKU编号，已停止导出。');
  const prices = variants.map(v => v.price).filter(p => p !== null && p !== '').map(Number).filter(Number.isFinite);
  const basic = product.cross_basic_info || {};
  const sale = product.sale_info || {};
  return {
    offerId: offer.id, sourceUrl: offer.url, sourceSystem: '领星ERP商品链接解析', capturedAt,
    title: product.subject, status: product.status, currency: 'CNY',
    supplier: { name: basic.supplierName || basic.companyName || '', loginId: product.supplier_login_id || basic.loginId || '', shopUrl: basic.shopUrl || null },
    category: { id: String(product.category_id || ''), name: product.category_name || '' },
    unit: sale.unit || null, minOrderQuantity: sale.min_order_quantity ?? null,
    reportedTotalStock: sale.amount_on_sale ?? null,
    referencePrice: product.reference_price ?? null, priceTiers: sale.price_ranges || [],
    variantCount: variants.length,
    priceRange: prices.length ? { min: Math.min(...prices), max: Math.max(...prices) } : null,
    mainImages: Array.isArray(product.image?.images) ? product.image.images : [], variants,
    attributeOptions: product.effective_attributes || [],
    returnedFields: Object.keys(product),
    notes: ['价格、库存为采集时领星接口返回值；最终成交价以供应商及订单结算结果为准。']
  };
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function safeUrl(value) {
  try { const u = new URL(value); return u.protocol === 'https:' ? u.href : ''; } catch { return ''; }
}

function renderReport(data) {
  const rows = data.variants.map((v, i) => `<tr><td>${i + 1}</td><td>${v.imageUrl ? `<img loading="lazy" src="${escapeHtml(safeUrl(v.imageUrl))}" alt="${escapeHtml(v.name)}">` : ''}</td><td>${escapeHtml(v.name)}</td><td>${escapeHtml(v.price ?? '未返回')}</td><td>${escapeHtml(v.consignPrice ?? '未返回')}</td><td>${escapeHtml(v.stock ?? '未返回')}</td><td class="id">${escapeHtml(v.skuId)}</td></tr>`).join('\n');
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>1688商品 ${data.offerId}</title>
<style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#1d2939;background:#f7f8fa;max-width:1200px;margin:32px auto;padding:0 20px}h1{font-size:24px}section{background:white;border:1px solid #e4e7ec;border-radius:10px;padding:20px;margin:18px 0}.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.meta span{color:#667085}.images{display:flex;gap:12px;overflow:auto}.images img{width:170px;height:170px;object-fit:contain}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;border-bottom:1px solid #e4e7ec;padding:10px}th{background:#f2f4f7}td img{width:75px;height:75px;object-fit:contain}.id{font-family:monospace}.scroll{overflow-x:auto}.note{color:#667085;font-size:13px}a{color:#175cd3}</style>
<h1>${escapeHtml(data.title)}</h1><p><a href="${escapeHtml(data.sourceUrl)}" target="_blank" rel="noopener">商品链接 · ${escapeHtml(data.offerId)}</a></p>
<section class="meta"><div><span>供应商</span><br>${escapeHtml(data.supplier.name)}</div><div><span>规格数</span><br>${data.variantCount}</div><div><span>规格价格范围（元）</span><br>${data.priceRange ? `${data.priceRange.min.toFixed(2)}–${data.priceRange.max.toFixed(2)}` : '未返回'}</div><div><span>起订量</span><br>${escapeHtml(data.minOrderQuantity)} ${escapeHtml(data.unit)}</div><div><span>品类</span><br>${escapeHtml(data.category.name)}</div><div><span>采集时间</span><br>${escapeHtml(new Date(data.capturedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }))}</div></section>
<section><h2>主图</h2><div class="images">${data.mainImages.map(u => `<img src="${escapeHtml(safeUrl(u))}" alt="商品主图">`).join('')}</div></section>
<section><h2>全部规格</h2><div class="scroll"><table><thead><tr><th>序号</th><th>图片</th><th>规格</th><th>价格（元）</th><th>代发价（元）</th><th>库存</th><th>SKU编号</th></tr></thead><tbody>${rows}</tbody></table></div></section>
<p class="note">${escapeHtml(data.notes.join(' '))}</p></html>`;
}

function createRunDir(offerId, requestedOutput, root) {
  if (requestedOutput) {
    const resolved = path.resolve(requestedOutput);
    if (fs.existsSync(resolved)) throw new Error('指定输出目录已存在，请选择新目录以免覆盖。');
    fs.mkdirSync(resolved, { recursive: true });
    return resolved;
  }
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const parent = path.join(root, 'outputs', 'chenyu-kaifa', 'supplier-data');
  fs.mkdirSync(parent, { recursive: true });
  for (let i = 1; i < 10000; i++) {
    const candidate = path.join(parent, `${date}_${offerId}${i === 1 ? '' : '_' + String(i).padStart(2, '0')}`);
    try { fs.mkdirSync(candidate); return candidate; } catch (error) { if (error.code !== 'EEXIST') throw error; }
  }
  throw new Error('无法创建新的输出目录。');
}

async function waitForLogin(page, seconds) {
  const started = Date.now();
  const end = Date.now() + seconds * 1000;
  let notified = false;
  while (Date.now() < end) {
    if (page.isClosed()) throw new Error('Chrome窗口已关闭。');
    if (page.url().startsWith('https://erp.lingxing.com/erp/') && await page.getByText('产品', { exact: true }).filter({ visible: true }).count()) return;
    if (!notified && (/login|bindMobile|signin/i.test(page.url()) || Date.now() - started > 10000)) {
      console.log('请在Chrome中登录领星并完成二次验证，脚本会自动继续。'); notified = true;
    }
    await page.waitForTimeout(1500);
  }
  throw new Error('等待领星登录超时；完成登录后可重新运行。');
}


function comparable(value) {
  return String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim();
}

function selectVariants(data, requested) {
  if (requested === undefined || requested === null) return { status: 'ALL', requests: [], selectedVariants: [], candidateSkuIds: data.variants.map(v => v.skuId) };
  const requests = Array.isArray(requested) ? requested : [requested];
  if (!requests.length) throw new Error('属性列表不能为空；不传属性可读取全部规格。');
  const results = requests.map(request => {
    if (typeof request === 'string' ? !comparable(request) : !request || typeof request !== 'object' || Array.isArray(request) || !Object.keys(request).length) throw new Error('属性必须是完整规格名或非空属性字典。');
    if (typeof request === 'object' && Object.entries(request).some(([k,v]) => !comparable(k) || typeof v !== 'string' || !comparable(v))) throw new Error('属性字典必须使用非空字符串键和值。');
    const matches = data.variants.filter(v => typeof request === 'string' ? comparable(v.name) === comparable(request) : Object.entries(request).every(([key,value]) => {
      if (key === 'skuId' || key === 'specId') return comparable(v[key]) === comparable(value);
      return v.attributes.some(a => comparable(a.name) === comparable(key) && comparable(a.value) === comparable(value));
    }));
    const status = matches.length === 1 ? 'MATCHED' : matches.length ? 'AMBIGUOUS' : 'NOT_FOUND';
    const candidates = matches.length ? matches : data.variants.filter(v => typeof request === 'string' ? comparable(v.name).includes(comparable(request)) : Object.entries(request).every(([k,val]) => v.attributes.some(a => comparable(a.name) === comparable(k) && comparable(a.value).includes(comparable(val)))));
    return { request, status, matchedSkuIds: matches.map(v => v.skuId), candidates: candidates.map(v => ({ skuId:v.skuId, name:v.name, attributes:v.attributes, imageUrl:v.imageUrl })) };
  });
  const selected = new Set(results.filter(r => r.status === 'MATCHED').flatMap(r => r.matchedSkuIds));
  return { status:results.every(r => r.status === 'MATCHED') ? 'MATCHED' : 'NEEDS_CONFIRMATION', requests:results, selectedVariants:data.variants.filter(v => selected.has(v.skuId)) };
}

function validateEndpoint(value) {
  const u = new URL(value);
  if (u.protocol !== 'http:' || !['127.0.0.1','localhost','[::1]'].includes(u.hostname) || u.username || u.password || u.pathname !== '/' || u.search || u.hash) throw new Error('仅允许本机专用浏览器的loopback CDP端点。');
  return u.href;
}

function imageUrl(value) {
  const u = new URL(value);
  if (u.protocol !== 'https:' || !(u.hostname === 'alicdn.com' || u.hostname.endsWith('.alicdn.com')) || u.username || u.password || u.port) throw new Error('只下载阿里CDN的HTTPS图片。');
  return u.href;
}

function imageType(b) {
  if (b.subarray(0,3).equals(Buffer.from([255,216,255]))) return 'jpg';
  if (b.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) return 'png';
  if (/^GIF8[79]a/.test(b.subarray(0,6).toString())) return 'gif';
  if (b.subarray(0,4).toString() === 'RIFF' && b.subarray(8,12).toString() === 'WEBP') return 'webp';
  throw new Error('不是支持的JPEG/PNG/GIF/WebP图片。');
}

async function fetchImage(url, fetcher=fetch) {
  let next = imageUrl(url);
  for (let i=0; i<4; i++) {
    const response = await fetcher(next, {redirect:'manual', signal:AbortSignal.timeout(20000)});
    if (response.status >= 300 && response.status < 400) {
      try {
        const location = response.headers.get('location');
        if (!location) throw new Error('图片重定向缺少地址。');
        next = imageUrl(new URL(location, next).href);
      } finally { await response.body?.cancel(); }
      continue;
    }
    const limit = 12*1024*1024;
    if (!response.ok || !/^image\//i.test(response.headers.get('content-type') || '')) { await response.body?.cancel(); throw new Error('图片HTTP状态或类型错误：'+response.status); }
    if (Number(response.headers.get('content-length')) > limit) { await response.body?.cancel(); throw new Error('图片超过12MiB。'); }
    const reader = response.body.getReader(); const parts=[]; let size=0;
    try {
      while (true) {
        const {done,value} = await reader.read(); if (done) break;
        size += value.length; if (size > limit) throw new Error('图片超过12MiB。');
        parts.push(Buffer.from(value));
      }
    } finally { await reader.cancel().catch(()=>{}); }
    const buffer = Buffer.concat(parts);
    return {buffer, extension:imageType(buffer)};
  }
  throw new Error('图片重定向次数超限。');
}

async function downloadImages(data, selection, output) {
  const items = data.mainImages.map((url,i)=>({role:'product-main',index:i+1,url}));
  const variants = selection.status === 'ALL' ? data.variants : selection.selectedVariants;
  items.push(...variants.filter(v=>v.imageUrl).map(v=>({role:'variant',skuId:v.skuId,name:v.name,url:v.imageUrl})));
  const urls = [...new Set(items.map(i=>i.url))]; const cache = new Map();
  fs.mkdirSync(path.join(output,'images'));
  // Small bounded concurrency; no account requests or credentials are sent to the image CDN.
  let position=0;
  await Promise.all(Array.from({length:Math.min(2,urls.length)},async()=>{
    while (position < urls.length) {
      const index=position++; const url=urls[index];
      try {
        const result=await fetchImage(url); const file='images/'+String(index+1).padStart(3,'0')+'.'+result.extension;
        fs.writeFileSync(path.join(output,file),result.buffer);
        cache.set(url,{status:'SAVED',file,bytes:result.buffer.length});
      } catch(e) { cache.set(url,{status:'FAILED',error:e.message}); }
      console.log('图片 '+(index+1)+'/'+urls.length+' '+cache.get(url).status);
    }
  }));
  return items.map(item=>({...item,...cache.get(item.url)}));
}

function resolveRuntime(options) {
  let root;
  if (!options.output || !options.profile) {
    root = path.resolve(options.workspace || process.cwd());
    if (!fs.existsSync(path.join(root,'plugins','chenyu-kaifa','plugin.json'))) throw new Error('从chenyu-ai仓库运行或传--workspace；无仓库时同时传--output和--profile。');
  }
  const profile = path.resolve(options.profile || path.join(root,'outputs','chenyu-kaifa','_sessions','lingxing'));
  return {root,profile};
}

function isTargetResponse(response, offer) {
  const u = new URL(response.url());
  const requestText = response.request().url()+' '+(response.request().postData() || '');
  return u.origin === 'https://erp.lingxing.com' && u.pathname === PARSE_PATH && requestText.includes(offer.id);
}

function makePack(data, selection) {
  return {
    schemaVersion:1,status:selection.status,offerId:data.offerId,sourceUrl:data.sourceUrl,sourceSystem:data.sourceSystem,capturedAt:data.capturedAt,
    title:data.title,supplier:data.supplier,currency:data.currency,unit:data.unit,minOrderQuantity:data.minOrderQuantity,
    mainImages:data.mainImages,selection,notes:data.notes,
    missingFields:['weight','dimensions','material','leadTime','negotiatedPrice'],
    warnings:data.supplier.name ? [] : ['供应商公司名称未返回，不从会员名或标题推测。']
  };
}

async function collect(offer, options={}) {
  const {chromium} = require('playwright');
  const {root,profile} = resolveRuntime(options);
  let browser, context, page, dialog; let owned=false, openedDialog=false;
  try {
    if (options.endpoint) {
      browser=await chromium.connectOverCDP(validateEndpoint(options.endpoint),{timeout:5000});
      context=browser.contexts()[0]; if (!context) throw new Error('专用浏览器没有可用上下文。');
    } else {
      owned=true; context=await chromium.launchPersistentContext(profile,{channel:'chrome',headless:false,viewport:null,args:['--start-maximized']});
    }
    page=context.pages().find(p=>p.url().startsWith('https://erp.lingxing.com/')) || await context.newPage();
    if (!page.url().startsWith('https://erp.lingxing.com/erp/')) await page.goto(PRODUCT_PAGE,{waitUntil:'domcontentloaded',timeout:90000});
    await waitForLogin(page,options.loginTimeout || 900);
    if (!page.url().startsWith(PRODUCT_PAGE)) await page.goto(PRODUCT_PAGE,{waitUntil:'domcontentloaded',timeout:90000});
    await waitForLogin(page,options.loginTimeout || 900);
    if (await page.locator('[role="dialog"]').filter({visible:true}).count()) throw new Error('专用浏览器已有弹窗；请先手动处理，不覆盖未保存操作。');
    const more=page.getByText('更多',{exact:true}).filter({visible:true});
    await more.waitFor({state:'visible',timeout:60000}); await more.click();
    await page.getByText('添加1688配对',{exact:true}).filter({visible:true}).click();
    openedDialog=true;
    dialog=page.locator('[role="dialog"]').filter({hasText:'批量添加1688配对'}).filter({visible:true});
    await dialog.waitFor({state:'visible',timeout:15000});
    await dialog.getByPlaceholder('请输入商品链接',{exact:true}).fill(offer.url);
    // Product identity may be carried in query parameters, not only the POST body.
    const pending=context.waitForEvent('response',{predicate:r=>isTargetResponse(r,offer),timeout:90000});
    pending.catch(()=>{});
    await dialog.getByText('解 析',{exact:true}).click();
    const response=await pending;
    if (!response.ok()) throw new Error('领星解析HTTP错误：'+response.status());
    const raw=await response.json();
    const data=normalize(raw,offer);
    const selection=selectVariants(data,options.attributes);
    const pack=makePack(data,selection);
    const output=createRunDir(offer.id,options.output,root);
    const write=(file,value)=>fs.writeFileSync(path.join(output,file),JSON.stringify(value,null,2));
    write('product.json',data);
    write('raw-product.json',raw.data.find(p=>String(p.product_id)===offer.id));
    write('supplier-data.json',pack);
    write('image-urls.json',{mainImages:data.mainImages,variants:data.variants.map(v=>({skuId:v.skuId,name:v.name,url:v.imageUrl}))});
    fs.writeFileSync(path.join(output,'report.html'),renderReport(data));
    await dialog.getByText(data.title,{exact:true}).first().waitFor({state:'visible',timeout:10000}).catch(()=>{});
    await dialog.screenshot({path:path.join(output,'lingxing-parsed.png')}).catch(()=>{});
    // Close the parse-only dialog before downloads; never save pairing or supplier.
    await dialog.getByText('取消',{exact:true}).click(); openedDialog=false;
    if (options.downloadImages) { pack.assets=await downloadImages(data,selection,output); write('supplier-data.json',pack); }
    const result={success:true,selectionStatus:selection.status,output,offerId:data.offerId,supplier:data.supplier.name,variants:data.variantCount,selected:selection.selectedVariants.length,mainImages:data.mainImages.length,priceRange:data.priceRange,imageFailures:pack.assets?.filter(a=>a.status==='FAILED').length || 0};
    console.log(JSON.stringify(result)); return {data,pack,output};
  } finally {
    if (openedDialog && dialog) { try { if (await dialog.count()) await dialog.getByText('取消',{exact:true}).click({timeout:5000}); } catch {} }
    if (owned && context) await context.close(); else if (browser) await browser.close();
  }
}

async function main() {
  const args=process.argv.slice(2);
  if (!args.length || args.includes('--help')) {
    console.log('node collect-lingxing-1688.cjs <1688链接或编号> [--attributes 完整规格名或JSON] [--download-images] [--workspace 仓库] [--output 新目录] [--profile 专用会话目录] [--endpoint 本机CDP] [--login-timeout 秒]\n首次由用户在可见Chrome完成领星登录及验证。只解析，不保存配对。'); return;
  }
  const offer=parseOffer(args[0]);
  const known=new Set(['--attributes','--download-images','--workspace','--output','--profile','--endpoint','--login-timeout']);
  for (let i=1;i<args.length;i++) {
    if (!known.has(args[i])) throw new Error('未知参数：'+args[i]);
    if (args[i] !== '--download-images') { if (!args[i+1] || args[i+1].startsWith('--')) throw new Error('缺少参数值：'+args[i]); i++; }
  }
  const value=n=>{const i=args.indexOf(n);return i<0 ? undefined : args[i+1];};
  const attr=value('--attributes');
  const attributes=attr && /^[\[{]/.test(attr.trim()) ? JSON.parse(attr) : attr;
  selectVariants({variants:[]},attributes);
  const timeout=value('--login-timeout');
  if (timeout && (!Number.isFinite(Number(timeout)) || Number(timeout)<=0)) throw new Error('登录超时必须是正秒数。');
  await collect(offer,{attributes,downloadImages:args.includes('--download-images'),workspace:value('--workspace'),output:value('--output'),profile:value('--profile'),endpoint:value('--endpoint'),loginTimeout:timeout ? Number(timeout) : undefined});
}

module.exports={parseOffer,normalize,selectVariants,makePack,renderReport,createRunDir,resolveRuntime,validateEndpoint,imageUrl,imageType,fetchImage,isTargetResponse,collect};
if (require.main === module) main().catch(e=>{console.error(e.message);process.exitCode=1;});

