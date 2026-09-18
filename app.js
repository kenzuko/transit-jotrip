const DATA_URL='./data/network.json';
const state={data:null,view:'next',query:''};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const setText=(s,v)=>{const el=$(s);if(el)el.textContent=v};
const safe=(v,f='-')=>v===undefined||v===null||v===''?f:v;
const FOLD=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLowerCase();

function clock(){
  setText('#clockNow',new Intl.DateTimeFormat('vi-VN',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Ho_Chi_Minh'}).format(new Date()));
}
function fmtTime(v){
  if(!v)return '-';
  const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);
  return d.toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Ho_Chi_Minh'});
}
function ageInfo(iso){
  if(!iso)return {label:'-',level:'loading'};
  const min=Math.max(0,Math.round((Date.now()-new Date(iso).getTime())/60000));
  return {label:min<1?'vừa cập nhật':min<60?`${min} phút`:`${Math.round(min/60)} giờ`,level:min<=10?'good':min<=30?'watch':'bad'};
}
function statusTone(v=''){
  const s=FOLD(v);
  if(/da xuat ben|departed|running|on time/.test(s))return'good';
  if(/mo ban|boarding/.test(s))return'blue';
  if(/delay|watch|limited|cham|gan het|con it/.test(s))return'watch';
  if(/cancel|suspend|closed|het cho|ngung|huy/.test(s))return'bad';
  return'neutral';
}
function networkTone(v=''){
  const s=FOLD(v);
  if(/data online|operational/.test(s))return'good';
  if(/partial|watch/.test(s))return'watch';
  if(/no data|offline/.test(s))return'bad';
  return'';
}
function direction(r){
  const o=FOLD(r.origin),d=FOLD(r.destination);
  if(d.includes('phu quoc'))return'inbound';
  if(o.includes('phu quoc'))return'outbound';
  return'other';
}
function kindLabel(r){
  if(r.data_kind==='operational_public')return'PUBLIC STATUS';
  if(r.data_kind==='schedule_frequency')return'FREQUENCY';
  return'SCHEDULE';
}
function modeLabel(r){
  if(r.type==='bus')return'BUS';
  return r.mode==='FERRY'?'PHÀ':'TÀU NHANH';
}
function modeClass(r){
  if(r.type==='bus')return'bus';
  return r.mode==='FERRY'?'ferry':'fast';
}
function minsUntil(v){
  const t=Date.parse(v||'');if(!Number.isFinite(t))return null;
  return Math.round((t-Date.now())/60000);
}
function countdown(r){
  if(r.type==='bus')return r.frequency||'Theo lịch';
  const m=minsUntil(r.departure_time);
  if(m===null)return'-';
  if(/đã xuất bến/i.test(r.status||''))return'Đã đi';
  if(m<=0&&m>=-5)return'Đang giờ';
  if(m<0)return'Đã qua';
  if(m<60)return`${m} phút`;
  const h=Math.floor(m/60),rm=m%60;
  return rm?`${h}g ${rm}p`:`${h} giờ`;
}
function seaRows(){
  return (state.data?.departures||[]).filter(r=>r.type==='sea');
}
function busRows(){
  return (state.data?.services||[]).filter(r=>r.type==='bus').map(r=>({...r,mode:'BUS',vessel_or_service:`Bus ${r.route_id}`,departure_time:null}));
}
function nextSea(){
  return seaRows().filter(r=>{
    const m=minsUntil(r.departure_time);
    return m!==null&&m>=-5&&!/đã xuất bến/i.test(r.status||'');
  }).sort((a,b)=>Date.parse(a.departure_time)-Date.parse(b.departure_time));
}
function quickNext(dir){
  return nextSea().find(r=>direction(r)===dir)||null;
}
function rowMatches(r){
  if(!state.query)return true;
  const hay=FOLD([r.origin,r.destination,r.operator,r.vessel_or_service,r.route_id,r.mode,r.status].join(' '));
  return hay.includes(FOLD(state.query));
}
function rowsForView(){
  let rows=[];
  if(state.view==='bus')rows=busRows();
  else{
    rows=seaRows();
    if(state.view==='next')rows=nextSea();
    if(state.view==='inbound')rows=rows.filter(r=>direction(r)==='inbound');
    if(state.view==='outbound')rows=rows.filter(r=>direction(r)==='outbound');
    rows=rows.sort((a,b)=>Date.parse(a.departure_time)-Date.parse(b.departure_time));
    if(state.view!=='next'){
      const now=Date.now()-45*60000;
      rows=rows.filter(r=>Date.parse(r.departure_time)>=now);
    }
  }
  return rows.filter(rowMatches).slice(0,state.view==='next'?16:22);
}
function renderSummary(){
  const sea=seaRows(),inbound=sea.filter(r=>direction(r)==='inbound'),outbound=sea.filter(r=>direction(r)==='outbound'),next=nextSea()[0];
  setText('#seaCount',state.data?.ready?sea.length:'-');
  setText('#inboundCount',state.data?.ready?inbound.length:'-');
  setText('#outboundCount',state.data?.ready?outbound.length:'-');
  setText('#nextTime',next?fmtTime(next.departure_time):'--:--');
  setText('#nextRoute',next?`${next.origin} → ${next.destination}`:'Chưa có chuyến');
  const net=state.data?.summary?.network?.label||'WAITING FOR DATA';
  const ns=$('#networkState');ns.textContent=net;ns.className=`network-state ${networkTone(net)}`;
}
function renderQuick(){
  const inbound=quickNext('inbound'),outbound=quickNext('outbound');
  setText('#quickInbound',inbound?fmtTime(inbound.departure_time):'-');
  setText('#quickInboundRoute',inbound?`${inbound.origin} → ${inbound.destination}`:'Chưa có chuyến');
  setText('#quickOutbound',outbound?fmtTime(outbound.departure_time):'-');
  setText('#quickOutboundRoute',outbound?`${outbound.origin} → ${outbound.destination}`:'Chưa có chuyến');
}
function renderTicker(){
  const t=$('#ticker'),alerts=state.data?.alerts||[],next=nextSea()[0],sea=seaRows().length,bus=busRows().length;
  if(alerts.length){
    t.className='ticker watch';
    t.innerHTML=`<span class="ticker-dot"></span><span>${safe(alerts[0].title,'Service Watch')}: ${safe(alerts[0].description,'')}</span>`;
  }else if(next){
    t.className='ticker';
    t.innerHTML=`<span class="ticker-dot"></span><span>${sea} chuyến biển hôm nay · ${bus} tuyến bus · Chuyến kế tiếp ${fmtTime(next.departure_time)} ${next.origin} → ${next.destination} · còn ${countdown(next)}</span>`;
  }else{
    t.className='ticker';
    t.innerHTML='<span class="ticker-dot"></span><span>Không còn chuyến biển sắp chạy trong snapshot hiện tại.</span>';
  }
}
function renderRows(){
  const rows=rowsForView(),host=$('#boardRows');
  if(!rows.length){
    host.innerHTML='<div class="empty-state">Không có dữ liệu phù hợp bộ lọc hiện tại.</div>';
    return;
  }
  host.innerHTML=rows.map((r,i)=>{
    const m=r.type==='bus'?null:minsUntil(r.departure_time),imminent=m!==null&&m>=0&&m<=30;
    const time=r.type==='bus'?`Bus ${safe(r.route_id,'-')}`:fmtTime(r.departure_time);
    const timeSub=r.type==='bus'?safe(r.operating_window,'Khung giờ'):(r.arrival_time?`đến ${fmtTime(r.arrival_time)}`:'giờ khởi hành');
    const c=countdown(r);
    const cSub=r.type==='bus'?'tần suất':'so với hiện tại';
    return `<article class="transit-row ${imminent?'imminent':''}" data-row="${i}">
      <div class="cell time-cell" data-label="GIỜ"><strong>${time}</strong><small>${timeSub}</small></div>
      <div class="cell countdown ${imminent?'now':''}" data-label="CÒN"><strong>${c}</strong><small>${cSub}</small></div>
      <div class="cell mode-cell" data-label="LOẠI"><span class="mode-pill ${modeClass(r)}">${modeLabel(r)}</span></div>
      <div class="cell route-cell" data-label="HÀNH TRÌNH"><strong>${safe(r.origin,'?')} → ${safe(r.destination,'?')}</strong><small>${r.type==='bus'?'Tuyến cố định':direction(r)==='inbound'?'Đến Phú Quốc':direction(r)==='outbound'?'Rời Phú Quốc':'Liên tuyến'}</small></div>
      <div class="cell service-cell" data-label="ĐƠN VỊ / TÀU"><strong>${safe(r.operator,'-')}</strong><small>${safe(r.vessel_or_service,r.type==='bus'?`Bus ${safe(r.route_id,'')}`:'-')}</small></div>
      <div class="cell status-cell" data-label="TRẠNG THÁI"><span class="status-pill ${statusTone(r.status)}">${safe(r.status,'Theo lịch')}</span></div>
      <div class="cell kind-cell" data-label="DỮ LIỆU"><span class="kind-pill">${kindLabel(r)}</span></div>
    </article>`;
  }).join('');
  $$('#boardRows .transit-row').forEach((el,i)=>el.addEventListener('click',()=>openDrawer(rows[i])));
}
function renderAlerts(){
  const alerts=state.data?.alerts||[];
  setText('#alertBadge',alerts.length);
  const host=$('#alertsList');
  if(!alerts.length){host.innerHTML='<div class="empty-state compact-empty">Chưa có cảnh báo vận hành.</div>';return}
  host.innerHTML=alerts.map(a=>`<div class="watch-item"><div class="watch-icon">!</div><div><strong>${safe(a.title,'Service Watch')}</strong><p>${safe(a.description,'')}</p></div></div>`).join('');
}
function renderHealth(){
  const d=state.data||{},age=ageInfo(d.generated_at),ready=!!d.ready,level=d.health?.status||age.level;
  setText('#updatedAt',ready?`Cập nhật ${age.label}`:'Đang chờ dữ liệu...');
  setText('#snapshotTime',d.generated_at?new Date(d.generated_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'-');
  setText('#seaSource',safe(d.sources?.sea?.label,'-'));
  setText('#busSource',safe(d.sources?.bus?.label,'-'));
  setText('#freshness',age.label);
  const pill=$('#healthPill'),badge=$('#qaBadge'),icon=$('#healthIcon');
  if(!ready){
    pill.className='health-pill loading';pill.textContent='WAITING';
    badge.className='qa-badge';badge.textContent='WAITING';
    icon.className='health-icon';icon.textContent='⋯';
    setText('#healthTitle','NO LIVE DATA YET');setText('#healthDescription','Đang kiểm tra nguồn vận hành.');
    return;
  }
  const good=level==='good';
  pill.className=`health-pill ${level}`;pill.textContent=good?'FRESH':level==='watch'?'WATCH':'STALE';
  badge.className=`qa-badge ${good?'good':'bad'}`;badge.textContent=good?'GOOD':'CHECK';
  icon.className=`health-icon ${good?'good':level==='watch'?'watch':'bad'}`;icon.textContent=good?'✓':level==='watch'?'!':'×';
  setText('#healthTitle',good?'DATA FRESH':level==='watch'?'DATA DELAYED':'DATA STALE');
  setText('#healthDescription',safe(d.health?.description,good?'Nguồn đang đủ mới để theo dõi.':'Cần kiểm tra nguồn.'));
  setText('#boardStatus',good?'Board đang cập nhật':level==='watch'?'Một số nguồn cần kiểm tra':'Dữ liệu cũ');
  setText('#boardFootRight',d.generated_at?`Snapshot ${new Date(d.generated_at).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Ho_Chi_Minh'})}`:'');
}
function render(){renderSummary();renderQuick();renderTicker();renderRows();renderAlerts();renderHealth();}

function setView(view){
  state.view=view;
  $$('#boardTabs button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $$('[data-mobile-view]').forEach(b=>b.classList.toggle('active',b.dataset.mobileView===view));
  renderRows();
}
function openDrawer(r){
  const drawer=$('#detailDrawer'),back=$('#drawerBackdrop'),content=$('#drawerContent');
  const isBus=r.type==='bus';
  const dep=isBus?safe(r.operating_window,'-'):fmtTime(r.departure_time);
  const arr=isBus?safe(r.frequency,'-'):safe(r.arrival_time?fmtTime(r.arrival_time):null,'Chưa có giờ đến');
  content.innerHTML=`
    <div class="drawer-kicker">${modeLabel(r)} · ${kindLabel(r)}</div>
    <h2 class="drawer-title">${isBus?`Bus ${safe(r.route_id,'-')}`:dep}</h2>
    <div class="drawer-route">${safe(r.origin,'?')} → ${safe(r.destination,'?')}</div>
    <div class="drawer-journey">
      <div class="journey-dot ${!isBus&&/đã xuất bến/i.test(r.status||'')?'done':''}"></div><div class="journey-copy"><strong>${safe(r.origin,'Điểm đi')}</strong><p>${isBus?`Khung hoạt động ${dep}`:`Khởi hành ${dep}`}</p></div>
      <div class="journey-dot last"></div><div class="journey-copy"><strong>${safe(r.destination,'Điểm đến')}</strong><p>${isBus?`Tần suất ${arr}`:`Dự kiến đến ${arr}`}</p></div>
    </div>
    <div class="drawer-meta">
      <div><span>Đơn vị</span><b>${safe(r.operator,'-')}</b></div>
      <div><span>Phương tiện</span><b>${safe(r.vessel_or_service,isBus?`Bus ${safe(r.route_id,'')}`:'-')}</b></div>
      <div><span>Trạng thái</span><b>${safe(r.status,'Theo lịch')}</b></div>
      <div><span>Cấp dữ liệu</span><b>${kindLabel(r)}</b></div>
      <div><span>Độ tin cậy</span><b>${safe(r.confidence,isBus?'schedule':'-')}</b></div>
    </div>
    ${r.source_url?`<a class="source-link" href="${r.source_url}" target="_blank" rel="noopener">Mở nguồn công khai ↗</a>`:''}`;
  drawer.classList.remove('hidden');back.classList.remove('hidden');drawer.setAttribute('aria-hidden','false');
}
function closeDrawer(){
  $('#detailDrawer').classList.add('hidden');$('#drawerBackdrop').classList.add('hidden');$('#detailDrawer').setAttribute('aria-hidden','true');
}
async function load(){
  $('#errorBox').classList.add('hidden');
  try{
    const res=await fetch(`${DATA_URL}?t=${Date.now()}`,{cache:'no-store'});
    if(!res.ok)throw new Error(`HTTP ${res.status}`);
    state.data=await res.json();render();
  }catch(err){
    $('#errorBox').textContent='Không đọc được snapshot Transit lúc này. Trang không dùng dữ liệu giả để thay thế.';
    $('#errorBox').classList.remove('hidden');console.error(err);
  }
}
$$('#boardTabs button').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
$$('[data-mobile-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.mobileView)));
$('#searchInput').addEventListener('input',e=>{state.query=e.target.value;renderRows();});
$('#refreshBtn').addEventListener('click',load);
$('#drawerClose').addEventListener('click',closeDrawer);
$('#drawerBackdrop').addEventListener('click',closeDrawer);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer();});
clock();setInterval(clock,1000);
load();setInterval(()=>{renderSummary();renderQuick();renderTicker();renderRows();renderHealth();},60000);