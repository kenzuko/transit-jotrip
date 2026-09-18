const DATA_URL='./data/network.json';
const state={data:null,view:'network',type:'all'};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const text=(id,v)=>{const el=$(id);if(el)el.textContent=v};
const safe=(v,f='-')=>v===undefined||v===null||v===''?f:v;
function ageInfo(iso){
  if(!iso)return {label:'-',level:'loading',minutes:null};
  const ms=Date.now()-new Date(iso).getTime();
  const min=Math.max(0,Math.round(ms/60000));
  return {minutes:min,label:min<1?'vừa cập nhật':min<60?`${min} phút`:`${Math.round(min/60)} giờ`,level:min<=10?'good':min<=30?'watch':'bad'};
}
function fmtTime(v){if(!v)return '-';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);return d.toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Ho_Chi_Minh'});}
function statusClass(v=''){const s=String(v).toLowerCase();if(/normal|on time|departed|running|đúng giờ|đã xuất bến/.test(s))return'good';if(/delay|watch|limited|boarding|còn ít|gần hết|chậm/.test(s))return'watch';if(/cancel|suspend|closed|hết chỗ|ngừng|hủy/.test(s))return'bad';return'neutral';}
function filteredDepartures(){
  const list=state.data?.departures||[];
  const type=state.view==='sea'?'sea':state.view==='bus'?'bus':state.type;
  return list.filter(x=>type==='all'||x.type===type).sort((a,b)=>String(a.departure_time||'').localeCompare(String(b.departure_time||'')));
}
function renderDepartures(){
  const host=$('#departureList');const rows=filteredDepartures();
  if(!rows.length){host.innerHTML='<div class="empty-state">Chưa có dữ liệu chuyến để hiển thị.</div>';return}
  host.innerHTML=rows.map(r=>`<article class="departure-row">
    <div class="departure-time">${fmtTime(r.departure_time)}</div>
    <span class="type-pill ${r.type==='bus'?'bus':'sea'}">${r.type==='bus'?'BUS':(r.mode||'SEA')}</span>
    <div class="route"><strong>${safe(r.origin,'?')} → ${safe(r.destination,'?')}</strong><small>${safe(r.vessel_or_service,'')}</small></div>
    <div class="operator">${safe(r.operator,'-')}<small>${safe(r.source_label,'')}</small></div>
    <span class="status-pill ${statusClass(r.status)}">${safe(r.status,'Theo lịch')}</span>
  </article>`).join('');
}
function renderAlerts(){
  const alerts=(state.data?.alerts||[]).filter(a=>state.view==='network'||!a.type||a.type===state.view);
  text('#alertBadge',alerts.length);
  const host=$('#alertsList');
  if(!alerts.length){host.innerHTML='<div class="empty-state compact-empty">Chưa có cảnh báo.</div>';return}
  host.innerHTML=alerts.map(a=>`<div class="watch-item"><div class="watch-icon">!</div><div><strong>${safe(a.title,'Service alert')}</strong><p>${safe(a.description,'')}</p></div></div>`).join('');
}
function renderSummary(){
  const d=state.data||{};const departures=d.departures||[];
  const sea=departures.filter(x=>x.type==='sea').length,bus=departures.filter(x=>x.type==='bus').length;
  text('#seaCount',d.ready?sea:'-');text('#busCount',d.ready?bus:'-');
  text('#activeRoutes',d.ready?safe(d.summary?.active_routes,0):'-');
  text('#alertsCount',d.ready?(d.alerts||[]).length:'-');
  text('#seaState',safe(d.summary?.sea?.label,'Chưa có dữ liệu'));
  text('#seaDescription',safe(d.summary?.sea?.description,'Tàu cao tốc và phà.'));
  text('#busState',safe(d.summary?.bus?.label,'Chưa có dữ liệu'));
  text('#busDescription',safe(d.summary?.bus?.description,'Bus công cộng và tuyến cố định.'));
  const ns=$('#networkState');ns.textContent=safe(d.summary?.network?.label,'WAITING FOR DATA');ns.className=`ops-state ${statusClass(d.summary?.network?.label)}`;
}
function renderHealth(){
  const d=state.data||{},age=ageInfo(d.generated_at),ready=!!d.ready;
  text('#updatedAt',ready?`Cập nhật ${age.label}`:'Đang chờ dữ liệu...');
  text('#snapshotTime',d.generated_at?new Date(d.generated_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'-');
  text('#seaSource',safe(d.sources?.sea?.label,'-'));text('#busSource',safe(d.sources?.bus?.label,'-'));text('#freshness',age.label);
  const pill=$('#healthPill'),badge=$('#qaBadge'),icon=$('#healthIcon');
  if(!ready){pill.className='health-pill loading';pill.textContent='WAITING';badge.className='qa-badge';badge.textContent='WAITING';icon.className='health-icon';icon.textContent='⋯';text('#healthTitle','NO LIVE DATA YET');text('#healthDescription','Giao diện đã sẵn sàng. Collector chưa ghi snapshot vận hành.');return}
  const level=d.health?.status||age.level;const good=level==='good';
  pill.className=`health-pill ${level}`;pill.textContent=good?'FRESH':level==='watch'?'WATCH':'STALE';
  badge.className=`qa-badge ${good?'good':'bad'}`;badge.textContent=good?'GOOD':'CHECK';
  icon.className=`health-icon ${good?'good':level==='watch'?'watch':'bad'}`;icon.textContent=good?'✓':level==='watch'?'!':'×';
  text('#healthTitle',good?'DATA FRESH':level==='watch'?'DATA DELAYED':'DATA STALE');
  text('#healthDescription',safe(d.health?.description,good?'Snapshot đang đủ mới để theo dõi vận hành.':'Cần kiểm tra độ mới hoặc nguồn dữ liệu.'));
}
function render(){renderSummary();renderDepartures();renderAlerts();renderHealth()}
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
function setView(view){
  state.view=view;
  $$('#modeSwitch button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $$('[data-mobile-view]').forEach(b=>b.classList.toggle('active',b.dataset.mobileView===view));
  renderDepartures();renderAlerts();
}
$$('#modeSwitch button').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
$$('[data-mobile-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.mobileView)));
$$('#typeFilter button').forEach(b=>b.addEventListener('click',()=>{state.type=b.dataset.type;$$('#typeFilter button').forEach(x=>x.classList.toggle('active',x===b));state.view='network';setView('network')}));
$('#refreshBtn').addEventListener('click',load);$('#mobileRefresh').addEventListener('click',load);
load();setInterval(load,60000);