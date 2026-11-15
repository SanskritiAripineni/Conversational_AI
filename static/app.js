'use strict';
const $ = id => document.getElementById(id);
const cash = cents => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(cents / 100);
let state, menus, token, busy = false, filter = 'All';
const icons = {'Chicken Biryani':'🍛','Paneer Tikka':'🥘','Garlic Naan':'🫓','Penne Alfredo':'🍝','Margherita Pizza':'🍕','Chicken Tacos (3)':'🌮','Veggie Burrito':'🌯'};
function node(tag, className, text) { const e = document.createElement(tag); if(className) e.className = className; if(text !== undefined) e.textContent = text; return e; }
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
async function api(path, data) {
  const result = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Demo-Token':token},body:JSON.stringify(data)});
  const body = await result.json();
  if (!result.ok) throw new Error(body.error || 'Something went wrong. Please try again.');
  return body;
}
async function act(path, data) {
  if(busy) return;
  busy = true; showError(''); $('typing').hidden = false; renderControls();
  try { state = await api(path, data); render(); }
  catch(error) { showError(error.message); }
  finally { busy = false; $('typing').hidden = true; renderControls(); }
}
function renderMenu() {
  $('filters').replaceChildren();
  ['All', ...Object.keys(menus)].forEach(name => {
    const button = node('button','filter' + (filter === name ? ' active' : ''),name);
    button.setAttribute('aria-pressed',String(filter === name));
    button.onclick = () => {filter = name; renderMenu();}; $('filters').append(button);
  });
  $('menu').replaceChildren();
  for(const [restaurant, dishes] of Object.entries(menus)) {
    if(filter !== 'All' && filter !== restaurant) continue;
    $('menu').append(node('p','restaurant-title',restaurant.toUpperCase()));
    for(const [name, dish] of Object.entries(dishes)) {
      const row = node('div','menu-item'), art = node('span','dish-art',icons[name] || '🍽️'); art.setAttribute('aria-hidden','true');
      const info = node('div','dish-info'); info.append(node('div','dish-name',name));
      const details = node('div','dish-details',cash(Math.round(Number(dish.price) * 100)));
      if((dish.tags || []).includes('veg')) details.append(node('span','veg','● Veg'));
      info.append(details);
      const add = node('button','add-button','+'); add.setAttribute('aria-label',`Add ${name}`);
      add.disabled = busy || state.stage !== 'cart'; add.onclick = () => act('/api/cart',{restaurant,name});
      row.append(art,info,add); $('menu').append(row);
    }
  }
  $('dish-count').textContent = `${Object.values(menus).reduce((n,m) => n + Object.keys(m).length,0)} dishes`;
}
function renderMessages() {
  $('messages').replaceChildren();
  for(const turn of state.transcript) {
    const customer = 'customer' in turn, row = node('div','message' + (customer ? ' customer' : ''));
    row.append(node('p','message-label',customer ? 'YOU' : 'FOOD NOW'),node('div','bubble',turn.customer ?? turn.assistant));
    $('messages').append(row);
  }
  const body = document.querySelector('.chat-body'); body.scrollTop = body.scrollHeight;
}
function renderCart() {
  $('cart').replaceChildren();
  const groups = Object.entries(state.cart), totals = state.totals;
  const quantity = groups.reduce((n,[,lines]) => n + lines.reduce((a,l) => a + l.quantity,0),0);
  $('item-count').textContent = `${quantity} item${quantity === 1 ? '' : 's'}`;
  if(!groups.length) {
    const empty = node('div','empty-cart'); empty.append(node('div','empty-icon','♧'),node('strong',null,'Room for your favorites.'),node('p',null,'Pick a dish from the menu or tell your concierge what you’re craving.')); $('cart').append(empty);
  }
  for(const [restaurant, lines] of groups) {
    const group = node('div'); group.append(node('p','cart-group',restaurant));
    for(const line of lines) {
      const row = node('div','cart-line'), info = node('div','cart-line-info',line.name);
      if(line.notes) info.append(node('small',null,line.notes));
      row.append(node('span','quantity',String(line.quantity)),info,node('span',null,cash(line.quantity * line.unit_price_cents)));
      if(state.stage === 'cart') { const remove = node('button','remove','×'); remove.disabled = busy; remove.setAttribute('aria-label',`Remove ${line.name}`); remove.onclick = () => act('/api/cart',{action:'remove',restaurant,name:line.name}); row.append(remove); }
      group.append(row);
    } $('cart').append(group);
  }
  $('subtotal').textContent = cash(totals.subtotal_cents); $('tax').textContent = cash(totals.tax_cents);
  $('delivery-price').textContent = !quantity ? '—' : totals.delivery_cents ? cash(totals.delivery_cents) : 'FREE';
  $('total').textContent = cash(quantity ? totals.total_cents : 0);
  $('delivery-progress').max = state.free_over + 1; $('delivery-progress').value = Math.min(state.free_over + 1,totals.subtotal_cents);
  $('delivery-title').textContent = !quantity ? 'Good things add up.' : totals.delivery_cents ? 'A little closer to free delivery.' : 'Delivery is on us.';
  $('delivery-note').textContent = !quantity ? 'Free delivery on food orders over $50.' : totals.delivery_cents ? `Add ${cash(state.free_over + 1 - totals.subtotal_cents)} more in food to unlock free delivery.` : 'You’ve unlocked free delivery for this order.';
  $('confirmation').hidden = state.stage !== 'confirmed'; $('confirmation').textContent = state.confirmation || '';
  $('download').hidden = state.stage !== 'confirmed';
}
function renderControls() {
  if(!state) return;
  const stage = state.stage, empty = !Object.keys(state.cart).length;
  $('mode').textContent = state.mode;
  $('assistant-status').textContent = busy ? 'Putting it all together…' : stage === 'confirmed' ? 'Demo order complete' : 'Ready when you are';
  $('privacy-note').textContent = state.mode === 'Rehearsal' ? 'Rehearsal · Menu matching only · No texts or payments' : 'Gemini live · Messages sent to Google · No texts or payments';
  $('message').disabled = busy || stage === 'confirmed'; $('send').disabled = busy || stage === 'confirmed'; $('restart').disabled = busy;
  document.querySelectorAll('.add-button, .remove').forEach(e => e.disabled = busy || stage !== 'cart');
  const checkout = $('checkout'); checkout.disabled = busy || empty || stage !== 'cart';
  checkout.replaceChildren(document.createTextNode(stage === 'confirmed' ? '✓ Demo order confirmed' : stage !== 'cart' ? 'Continue in the conversation' : empty ? 'Start with something delicious' : 'Review & check out'),node('span',null,'↗'));
  const placeholders = {cart:'Tell us what sounds good…',name:'Enter a fictional customer name…',address:'Enter a fictional delivery address…',confirm:'Say yes to confirm, or no to go back…',confirmed:'All together. All confirmed.'};
  $('message').placeholder = placeholders[stage];
  const suggestions = {cart:[['Browse the menu','What is on the menu?'],['Try the sample order','Two chicken biryanis, one mild, and a penne Alfredo. Is delivery free?'],['Add chicken tacos','Add chicken tacos']],name:[['Use Alex Morgan','Alex Morgan']],address:[['Use a demo address','123 Demo Lane, Sample City']],confirm:[['Confirm demo order','yes'],['Go back','no']],confirmed:[['Start a new order',null]]};
  $('prompt-label').textContent = stage === 'cart' ? 'A LITTLE INSPIRATION' : stage === 'confirmed' ? 'THANKS FOR COMING TO THE TABLE' : 'DEMO CHECKOUT · FICTIONAL DETAILS ONLY';
  $('suggestions').replaceChildren();
  for(const [label,message] of suggestions[stage]) {const button = node('button','suggestion',label); button.disabled = busy; button.onclick = () => act(message === null ? '/api/reset' : '/api/message',message === null ? {} : {message}); $('suggestions').append(button);}
}
function render() { renderMenu(); renderMessages(); renderCart(); renderControls(); }
$('chat-form').addEventListener('submit', async event => {event.preventDefault(); const input = $('message'), message = input.value.trim(); if(!message || busy) return; input.value = ''; await act('/api/message',{message}); if(state.stage !== 'confirmed') input.focus();});
$('checkout').onclick = () => {document.querySelector('.chat-panel').scrollIntoView({behavior:'smooth',block:'nearest'}); act('/api/message',{message:'checkout'});};
$('restart').onclick = () => { $('message').value = ''; act('/api/reset',{}); };
$('download').onclick = () => {
  const lines = ['334 FOOD NOW — DEMO RECEIPT',`Order #${state.order_id}`,'No real order, payment, or SMS.',''];
  for(const [restaurant, items] of Object.entries(state.cart)) {lines.push(restaurant); for(const i of items) lines.push(`  ${i.quantity} × ${i.name}${i.notes ? ` (${i.notes})` : ''} — ${cash(i.quantity * i.unit_price_cents)}`);}
  lines.push('',`Food: ${cash(state.totals.subtotal_cents)}`,`Tax: ${cash(state.totals.tax_cents)}`,`Delivery: ${cash(state.totals.delivery_cents)}`,`Total: ${cash(state.totals.total_cents)}`,'',state.confirmation);
  const url = URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/plain'})), a = node('a'); a.href=url; a.download=`334-food-now-${state.order_id}.txt`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
};
api('/api/session').then(data => {state = data; menus = data.menus; token = data.token; render();}).catch(error => {showError(`Could not connect. ${error.message}`); $('mode').textContent = 'Disconnected';});
