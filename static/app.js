// HACK STORE frontend — vanilla JS, talks ONLY over HTTP JSON API
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let products = [];
let cart = []; // {product, qty}
let lat = null, lng = null;
let currentFilter = 'all';

// ---- helpers
function fmtINR(n){ return '₹' + Number(n).toLocaleString('en-IN'); }
function toast(msg){
  const el = $('#toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  setTimeout(()=> el.classList.add('hidden'), 2600);
}
function api(path, opts={}){
  return fetch(path, {headers:{'Content-Type':'application/json'}, ...opts})
    .then(async r=>{
      const text = await r.text();
      let data;
      try{ data = JSON.parse(text); }catch{ data = {detail:text, traceback:text}; }
      if(!r.ok){
        const err = new Error(data.detail || `HTTP ${r.status}`);
        err.status = r.status;
        err.data = data;
        err.traceback = data.traceback;
        throw err;
      }
      return data;
    });
}

// ---- products
async function loadProducts(){
  try{
    const data = await api('/api/products');
    products = data;
    renderProducts();
    updateCartTotals();
  }catch(e){
    $('#product-grid').innerHTML = `<div style="grid-column:1/-1"><pre class="error-pre">${escapeHtml(e.traceback||e.message)}</pre></div>`;
  }
}
function renderProducts(){
  const grid = $('#product-grid');
  let list = products;
  if(currentFilter !== 'all') list = list.filter(p=>p.category===currentFilter);
  if(!list.length){ grid.innerHTML = '<div class="muted">No products in this category.</div>'; return; }
  grid.innerHTML = list.map(p=>`
    <div class="card">
      <div class="card-top">
        <div class="card-emoji">${p.image}</div>
        <div class="card-info">
          <div class="card-cat">${p.category}</div>
          <div class="card-name">${escapeHtml(p.name)}</div>
          <div class="card-desc">${escapeHtml(p.description)}</div>
        </div>
      </div>
      <div class="card-foot">
        <div class="price">
          <span class="mrp">${fmtINR(p.mrp_inr)}</span>
          <span class="sale">${fmtINR(p.price_inr)}</span>
          <span class="stock ${p.stock<10?'low':''}">${p.stock} in stock</span>
        </div>
        <button class="add-btn" ${p.stock===0?'disabled':''} onclick="addToCart(${p.id})">${p.stock===0?'Out of stock':'Add to cart'}</button>
      </div>
    </div>
  `).join('');
}
function escapeHtml(s){ return String(s).replace(/[&<>"']/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// filters
$$('.filter-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    $$('.filter-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.cat;
    renderProducts();
  });
});

// ---- cart
window.addToCart = (id)=>{
  const p = products.find(x=>x.id===id);
  if(!p) return;
  const existing = cart.find(c=>c.product.id===id);
  if(existing){
    if(existing.qty >= p.stock){ toast('No more stock'); return; }
    existing.qty++;
  }else{
    cart.push({product:p, qty:1});
  }
  renderCart();
  toast(`${p.name} added`);
}
function renderCart(){
  const count = cart.reduce((s,c)=>s+c.qty,0);
  $('#cart-count').textContent = count;
  const box = $('#cart-items');
  if(!cart.length){
    box.innerHTML = '<div class="empty">Cart is empty. Add some gear →</div>';
  }else{
    box.innerHTML = cart.map((c,i)=>`
      <div class="cart-row">
        <div class="cart-row-emoji">${c.product.image}</div>
        <div class="cart-row-main">
          <div class="cart-row-title">${escapeHtml(c.product.name)}</div>
          <div class="cart-row-price">${fmtINR(c.product.price_inr)} × ${c.qty} = <b>${fmtINR(c.product.price_inr*c.qty)}</b></div>
        </div>
        <div class="qty">
          <button onclick="changeQty(${i},-1)">−</button>
          <span class="mono">${c.qty}</span>
          <button onclick="changeQty(${i},1)">+</button>
        </div>
      </div>
    `).join('');
  }
  updateCartTotals();
}
window.changeQty = (idx, delta)=>{
  cart[idx].qty += delta;
  if(cart[idx].qty<=0) cart.splice(idx,1);
  const p = cart[idx]?.product;
  if(p && cart[idx] && cart[idx].qty > p.stock){ cart[idx].qty = p.stock; toast('Max stock reached'); }
  renderCart();
}
function updateCartTotals(){
  const subtotal = cart.reduce((s,c)=>s+c.product.price_inr*c.qty,0);
  $('#cart-subtotal').textContent = fmtINR(subtotal);
  // checkout summary
  $('#sum-total').textContent = fmtINR(subtotal);
  // pay amount includes delivery estimate? We'll update after pincode? For now just subtotal
  // delivery fee will be computed server-side; we can estimate 49
  const estFee = subtotal>0 ? 49 : 0;
  $('#pay-amount').textContent = (subtotal+estFee).toLocaleString('en-IN');
}
function openCart(){ $('#cart-drawer').classList.add('open'); $('#cart-overlay').classList.remove('hidden'); }
function closeCart(){ $('#cart-drawer').classList.remove('open'); $('#cart-overlay').classList.add('hidden'); }
$('#cart-btn').addEventListener('click', openCart);
$('#cart-close').addEventListener('click', closeCart);
$('#cart-overlay').addEventListener('click', closeCart);

// ---- checkout
function openCheckout(){
  if(!cart.length){ toast('Cart is empty'); return; }
  closeCart();
  $('#checkout-overlay').classList.remove('hidden');
  $('#checkout-modal').classList.remove('hidden');
  $('#order-success').classList.add('hidden');
  $('#order-error').classList.add('hidden');
  $('#checkout-form').classList.remove('hidden');
  // reset lat/lng display
  updateLocUI();
}
function closeCheckout(){ $('#checkout-overlay').classList.add('hidden'); $('#checkout-modal').classList.add('hidden'); }
$('#checkout-btn').addEventListener('click', openCheckout);
$('#checkout-close').addEventListener('click', closeCheckout);
$('#checkout-overlay').addEventListener('click', closeCheckout);
$('#success-close').addEventListener('click', ()=>{ closeCheckout(); cart=[]; renderCart(); loadProducts(); });
$('#error-close').addEventListener('click', ()=>{
  $('#order-error').classList.add('hidden');
  $('#checkout-form').classList.remove('hidden');
});

$('#loc-btn').addEventListener('click', ()=>{
  if(!navigator.geolocation){ toast('Geolocation not supported'); return; }
  $('#loc-status').textContent = 'Locating…';
  navigator.geolocation.getCurrentPosition(async pos=>{
    lat = pos.coords.latitude;
    lng = pos.coords.longitude;
    updateLocUI();
    // try reverse geocode via Nominatim (free), fallback to mock city
    try{
      const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=10&addressdetails=1`;
      const r = await fetch(url, {headers:{'Accept':'application/json'}});
      const j = await r.json();
      const city = j.address?.city || j.address?.town || j.address?.village || j.address?.county || 'India';
      const postcode = j.address?.postcode || '';
      $('#city-hint').textContent = `≈ ${city}${postcode?' • '+postcode:''}`;
      if(postcode && !$('#cust-pincode').value) $('#cust-pincode').value = postcode.replace(/\D/g,'').slice(0,6);
      toast(`Location: ${city}`);
    }catch{
      $('#city-hint').textContent = `lat ${lat.toFixed(4)}, lng ${lng.toFixed(4)}`;
    }
  }, err=>{
    $('#loc-status').textContent = 'Failed: ' + err.message;
    toast('Location denied — use pincode');
  }, {enableHighAccuracy:true, timeout:8000});
});
function updateLocUI(){
  $('#lat-val').textContent = lat===null ? '—' : lat.toFixed(5);
  $('#lng-val').textContent = lng===null ? '—' : lng.toFixed(5);
  const has = lat!==null && lng!==null;
  $('#loc-status').textContent = has ? 'Coordinates captured ✓' : 'No coordinates yet';
}

$('#checkout-form').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const name = $('#cust-name').value.trim();
  const email = $('#cust-email').value.trim();
  const pincode = $('#cust-pincode').value.trim();
  if(!name || !email){ toast('Fill name & email'); return; }
  if(pincode && !/^\d{6}$/.test(pincode)){ toast('Pincode must be 6 digits'); return; }
  if(lat===null && lng===null && !pincode){ toast('Provide location or pincode'); return; }

  const btn = $('#place-order-btn');
  btn.disabled = true; btn.textContent = 'Placing…';

  const payload = {
    items: cart.map(c=>({product_id:c.product.id, qty:c.qty})),
    customer:{name,email},
    delivery:{pincode: pincode||null, lat, lng}
  };

  try{
    const res = await api('/api/orders', {method:'POST', body:JSON.stringify(payload)});
    // success
    $('#checkout-form').classList.add('hidden');
    $('#order-error').classList.add('hidden');
    $('#order-success').classList.remove('hidden');
    $('#success-details').textContent =
`Order #${res.order_id}
Customer: ${name} <${email}>
Total: ${fmtINR(res.total_inr)}
Delivery fee: ${fmtINR(res.delivery_fee_inr)} → ${res.delivery_city}
Grand total: ${fmtINR(res.grand_total_inr)}
ETA: ${res.eta}
Payment: ${res.payment?.id || 'captured'} (${res.payment?.status||'—'})`;
    toast('Order placed ✓');
  }catch(err){
    $('#checkout-form').classList.add('hidden');
    $('#order-success').classList.add('hidden');
    $('#order-error').classList.remove('hidden');
    const detail = err.data?.detail || err.message;
    const tb = err.data?.traceback || err.traceback || '';
    $('#error-pre').textContent = `Error: ${detail}\n\nTraceback:\n${tb}`;
  }finally{
    btn.disabled = false;
    btn.innerHTML = `Place Order • Pay ₹ <span id="pay-amount">${$('#pay-amount').textContent}</span>`;
  }
});

// ---- orders view
async function loadOrders(){
  $('#orders-error').classList.add('hidden');
  const tbody = $('#orders-tbody');
  tbody.innerHTML = '<tr><td colspan="9" class="muted">Loading…</td></tr>';
  try{
    const data = await api('/api/orders');
    if(!data.length){
      tbody.innerHTML = '<tr><td colspan="9" class="muted">No orders yet. Place one!</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(o=>`
      <tr>
        <td class="mono">#${o.order_id}</td>
        <td><b>${escapeHtml(o.customer.name)}</b><br><span class="muted mono">${escapeHtml(o.customer.email)}</span></td>
        <td>${o.items.map(it=>`${escapeHtml(it.name)} ×${it.qty}`).join('<br>')}</td>
        <td class="mono">${fmtINR(o.total_inr)}</td>
        <td class="mono">${fmtINR(o.delivery_fee_inr)}</td>
        <td class="mono"><b>${fmtINR(o.grand_total_inr)}</b></td>
        <td><span class="status status-${o.status}">${o.status}</span></td>
        <td>${escapeHtml(o.delivery_city||'')} ${o.delivery_pincode?'<br><span class="mono muted">'+o.delivery_pincode+'</span>':''}</td>
        <td class="mono">${escapeHtml(o.eta||'—')}</td>
      </tr>
    `).join('');
  }catch(err){
    tbody.innerHTML = '<tr><td colspan="9" class="muted">Failed to load — see error above</td></tr>';
    $('#orders-error').classList.remove('hidden');
    $('#orders-error-pre').textContent = `Error: ${err.data?.detail||err.message}\n\nTraceback:\n${err.data?.traceback||err.traceback||''}`;
  }
}
function openOrders(){
  $('#orders-overlay').classList.remove('hidden');
  $('#orders-modal').classList.remove('hidden');
  loadOrders();
}
function closeOrders(){ $('#orders-overlay').classList.add('hidden'); $('#orders-modal').classList.add('hidden'); }
$('#orders-btn').addEventListener('click', openOrders);
$('#orders-close').addEventListener('click', closeOrders);
$('#orders-overlay').addEventListener('click', closeOrders);
$('#orders-refresh').addEventListener('click', loadOrders);

// ---- health
async function refreshHealth(){
  try{
    const h = await api('/api/health');
    const checks = h.checks;
    const allUp = h.status==='ok';
    const pill = $('#health-pill');
    if(allUp){ pill.className='pill pill-ok'; pill.textContent='● all systems up'; }
    else { pill.className='pill pill-bad'; pill.textContent='● degraded'; }
    // rows
    const map = {db:'#h-db', payment:'#h-pay', delivery:'#h-del', notifier:'#h-not'};
    for(const [k,sel] of Object.entries(map)){
      const v = checks[k]||'—';
      const el = $(sel);
      if(!el) continue;
      const low = String(v).toLowerCase();
      let cls='dot-up';
      if(low.includes('down')) cls='dot-down';
      else if(low.includes('degrad')) cls='dot-deg';
      el.className='dot '+cls;
      el.textContent=v;
    }
    // update debug status
    const flags = h.flags || {};
    $('#debug-status').textContent = 'flags: ' + Object.entries(flags).map(([k,v])=>`${k}=${v?'on':'off'}`).join(' • ');
    // sync toggles without firing events
    $$('.toggle input').forEach(inp=>{
      const sc = inp.dataset.scenario;
      inp.checked = !!flags[sc];
    });
  }catch(e){
    const pill = $('#health-pill');
    pill.className='pill pill-bad';
    pill.textContent='● health down';
  }
}
setInterval(refreshHealth, 5000);
refreshHealth();

// ---- debug toggles
$$('.toggle input').forEach(inp=>{
  inp.addEventListener('change', async ()=>{
    const scenario = inp.dataset.scenario;
    const on = inp.checked;
    inp.disabled = true;
    try{
      await api(`/api/debug/bug?scenario=${encodeURIComponent(scenario)}&on=${on}`, {method:'POST'});
      toast(`${scenario} → ${on?'ON':'OFF'}`);
      refreshHealth();
    }catch(e){
      toast('Toggle failed');
      inp.checked = !on;
    }finally{ inp.disabled=false; }
  });
});
$('#debug-reset').addEventListener('click', async ()=>{
  for(const inp of $$('.toggle input')){
    if(inp.checked){
      inp.checked=false;
      const sc = inp.dataset.scenario;
      try{ await api(`/api/debug/bug?scenario=${sc}&on=false`, {method:'POST'});}catch{}
    }
  }
  refreshHealth();
  toast('All flags reset');
});

// init
loadProducts();
renderCart();
