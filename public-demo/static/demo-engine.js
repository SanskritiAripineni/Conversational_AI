/* Browser-only rehearsal. No server, API key, shared cart, payment, or SMS. */
'use strict';
(function(root) {
  function createDemo(menus) {
    const clone = value => JSON.parse(JSON.stringify(value));
    const money = cents => `$${(cents / 100).toFixed(2)}`;
    const cents = item => Math.round(Number(item.price) * 100);
    const escape = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    let order;
    function say(text) { order.transcript.push({assistant:text}); }
    function reset() {
      order = {cart:{}, transcript:[], name:'', address:'', stage:'cart',
        order_id:root.crypto.randomUUID().replaceAll('-','').slice(0,8).toUpperCase()};
      say('Hey, welcome to 334 Food Now! Craving a little of everything? Order across our restaurants in one conversation. What sounds good?');
    }
    function totals() {
      const subtotal = Object.values(order.cart).flat().reduce((n,line) => n + line.quantity * line.unit_price_cents,0);
      const tax = Math.round(subtotal * 825 / 10000);
      const delivery = subtotal > 5000 ? 0 : 499;
      return {subtotal_cents:subtotal,tax_cents:tax,delivery_cents:delivery,total_cents:subtotal + tax + delivery};
    }
    function state() {
      return clone({cart:order.cart,transcript:order.transcript,stage:order.stage,order_id:order.order_id,totals:totals(),
        confirmation:order.stage === 'confirmed' ? `334-FOOD-NOW: Order #${order.order_id} confirmed. Total: ${money(totals().total_cents)}.` : null,
        mode:'Rehearsal',free_over:5000});
    }
    function deliverySummary() {
      const t = totals();
      if(!t.delivery_cents) return `Food is ${money(t.subtotal_cents)} and delivery is free.`;
      const needed = 5001 - t.subtotal_cents;
      let text = `Food is ${money(t.subtotal_cents)}. Delivery is $4.99, or free if you add at least ${money(needed)}.`;
      const options = Object.entries(menus).flatMap(([restaurant,menu]) => Object.entries(menu).map(([name,item]) => ({restaurant,name,price:cents(item)})))
        .filter(item => item.price >= needed).sort((a,b) => a.price - b.price || a.name.localeCompare(b.name));
      if(options.length) {const item=options[0]; text += ` ${item.name} from ${item.restaurant} for ${money(item.price)} would get you there.`;}
      return text;
    }
    function add(items) {
      const added=[];
      for(const item of items) {
        if(!menus[item.restaurant]?.[item.name] || !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 20) continue;
        const line={name:item.name,quantity:item.quantity,unit_price_cents:cents(menus[item.restaurant][item.name]),notes:(item.notes || '').slice(0,100)};
        (order.cart[item.restaurant] ||= []).push(line); added.push(describe(line));
      }
      return added;
    }
    function describe(line) { return `${line.quantity} ${line.name}${line.notes ? ', ' + line.notes : ''}`; }
    function interpret(speech) {
      const text=speech.toLowerCase(), matches=[], items=[];
      for(const [restaurant,menu] of Object.entries(menus)) for(const [name,item] of Object.entries(menu)) {
        const alias=name.toLowerCase().replace(/\s*\(.*?\)/g,''), words=alias.split(/\s+/);
        let match=new RegExp('\\b' + words.map(word => escape(word.replace(/s+$/,'')) + 's?').join('\\s+') + '\\b').exec(text);
        if(!match) {
          const short=words.at(-1).replace(/s+$/,'');
          if(Object.values(menus).flatMap(m => Object.keys(m)).filter(n => n.toLowerCase().includes(short)).length === 1)
            match=new RegExp('\\b' + escape(short) + 's?\\b').exec(text);
        }
        if(match) matches.push({restaurant,name,item,index:match.index});
      }
      const browsing=/\b(menu|have|recommend|vegetarian|veggie options|price|cost|what)\b/.test(text);
      const ordering=/\b(add|order|get|want|take|i ll|i'd like)\b/.test(text);
      if(matches.length && (ordering || !browsing)) {
        const numbers={a:1,an:1,one:1,two:2,three:3,four:4,five:5};
        for(const match of matches.sort((a,b) => a.index-b.index)) {
          const q=/(\d+|a|an|one|two|three|four|five)\s+$/.exec(text.slice(0,match.index));
          let quantity=q ? numbers[q[1]] ?? Number(q[1]) : 1;
          let notes=text.includes('mild') && match.name.toLowerCase().includes('biryani') ? 'mild' : '';
          if(notes && quantity > 1 && /one mild/.test(text)) {items.push({restaurant:match.restaurant,name:match.name,quantity:1,notes}); quantity--; notes='';}
          items.push({restaurant:match.restaurant,name:match.name,quantity,notes});
        }
        return {items,answer:''};
      }
      if(/\b(delivery|total|subtotal)\b/.test(text) && Object.keys(order.cart).length) return {items:[],answer:''};
      let selected=Object.entries(menus).flatMap(([restaurant,menu]) => Object.entries(menu).map(([name,item]) => ({restaurant,name,item})));
      const cuisines=Object.keys(menus).filter(name => text.includes(name.toLowerCase()));
      if(cuisines.length) selected=selected.filter(row => cuisines.includes(row.restaurant));
      if(text.includes('vegetarian') || text.includes('veggie')) selected=selected.filter(row => (row.item.tags || []).includes('veg'));
      if(matches.length && browsing) selected=matches;
      if(browsing || cuisines.length) return {items:[],answer:selected.map(row => `${row.name} from ${row.restaurant} (${money(cents(row.item))})`).join('; ') || 'No matching options are listed in this menu.'};
      return {items:[],answer:'In rehearsal mode, use a dish name or tap Add on the menu. Try “two chicken biryanis and a penne Alfredo”.'};
    }
    function advance(speech) {
      const choice=(speech.toLowerCase().match(/[a-z]+/g) || []).join(' ');
      order.transcript.push({customer:speech});
      if(order.stage === 'confirmed') return say('Your demo order is already confirmed.');
      if(order.stage === 'confirm') {
        const yes=['yes','yes please','yes confirm','yes that s correct','yes that is correct','yeah','yep','correct','that s correct','yep that s right','yeah that s right','yes that s right'];
        if(yes.includes(choice)) {order.stage='confirmed'; return say(`Order ${order.order_id} is confirmed. Thank you!`);}
        if(['no','nope','go back','no go back'].includes(choice)) {order.stage='cart'; return say("Okay. Anything to add? Say checkout when you're ready.");}
        return say('Please say yes to confirm or no to go back.');
      }
      if(order.stage === 'name') {order.name=speech; order.stage='address'; return say('What is your delivery address? Use a fictional address for this demo.');}
      if(order.stage === 'address') {
        order.address=speech; order.stage='confirm';
        const details=Object.entries(order.cart).map(([restaurant,lines]) => `From ${restaurant}, ${lines.map(describe).join('; ')}`).join('. ');
        return say(`${order.name}, here is your order. ${details}. Deliver to ${order.address}. Total including tax and delivery is ${money(totals().total_cents)}. Confirm this demo order? No text will be sent. Say yes to confirm, or no to go back.`);
      }
      const checkout=['checkout','check out','done','that s all','that is all','i m ready to check out','i m ready to checkout','that s it','check out please','checkout please','that s everything','i m ready to pay','ready to check out','ready to checkout'];
      if(checkout.includes(choice)) {
        if(!Object.keys(order.cart).length) return say('Your cart is empty. What would you like to order?');
        order.stage='name'; return say('What name should I put on the order? Use fictional details for this demo.');
      }
      const turn=interpret(speech), added=add(turn.items), replies=[];
      if(turn.answer) replies.push(turn.answer);
      if(added.length) replies.push('Added ' + added.join('; ') + '.');
      if(added.length !== turn.items.length) replies.push("I couldn't match part of that request. Please order between 1 and 20 of each dish.");
      if(Object.keys(order.cart).length) replies.push(deliverySummary(),"Anything else? Say checkout when you're ready.");
      say(replies.join(' ') || 'What would you like to order?');
    }
    reset();
    return {async api(path,data) {
      if(path === '/api/session') return {...state(),menus:clone(menus),token:'browser-only'};
      if(path === '/api/reset') {reset(); return state();}
      if(path === '/api/message') {
        const message=data?.message;
        if(typeof message !== 'string' || !message.trim() || message.length > 1000) throw new Error('Enter a message between 1 and 1,000 characters.');
        advance(message.trim()); return state();
      }
      if(path === '/api/cart') {
        if(order.stage !== 'cart') throw new Error('Finish checkout or go back before changing your order.');
        const restaurant=data?.restaurant,name=data?.name;
        if(!menus[restaurant]?.[name]) throw new Error("That dish isn't on the menu.");
        if(data.action === 'remove') {
          order.cart[restaurant]=(order.cart[restaurant] || []).filter(line => line.name !== name);
          if(!order.cart[restaurant].length) delete order.cart[restaurant];
          say(`Removed ${name} from your order.`);
        } else {add([{restaurant,name,quantity:1}]); say(`Added ${name}. ${deliverySummary()}`);}
        return state();
      }
      throw new Error('Unknown demo action.');
    }};
  }
  if(typeof module !== 'undefined' && module.exports) module.exports={createDemo};
  if(root.FoodNowMenu) root.FoodNowDemo=createDemo(root.FoodNowMenu);
})(globalThis);
