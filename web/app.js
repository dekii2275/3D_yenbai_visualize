'use strict';
const $ = id => document.getElementById(id);
const canvas = $('map'), ctx = canvas.getContext('2d');
let terrain, terrainRenderer = null, layers = {}, points = [], visible = [], selected = null, projectedPoints = [], frame = 0;
let angle = -.45, tilt = .83, zoom = 1, panX = 0, panY = 0, panMode = false, dragging = false, moved = false, lastX = 0, lastY = 0, startX = 0, startY = 0, dragPan = false;
const IMPACT_RADIUS = 100; // m — bán kính minh họa, chưa phải ngưỡng chính thức
const LEVELS = {binh_thuong:{name:'Bình thường',color:'#4cb87a'},theo_doi:{name:'Theo dõi',color:'#e9c53f'},canh_bao:{name:'Cảnh báo',color:'#f0883a'},nguy_co_cao:{name:'Nguy cơ cao',color:'#e2453a'}};
// Dữ liệu chưa có mức cảnh báo thời gian thực: tạm gán theo trạng thái (Đã xảy ra → Nguy cơ cao, Nguy cơ → Cảnh báo).
const levelOf = p => LEVELS[p.muc_canh_bao] ? p.muc_canh_bao : (p.trang_thai==='Đã xảy ra' ? 'nguy_co_cao' : 'canh_bao');
const hexRgb = hex => [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
const rgba = (hex,a) => `rgba(${hexRgb(hex).join(',')},${a})`;
const shadeHex = (hex,k) => `rgb(${hexRgb(hex).map(v=>Math.max(0,Math.min(255,Math.round(v*k)))).join(',')})`;
const bufCanvas = document.createElement('canvas'), bctx = bufCanvas.getContext('2d');
let impacted = new Set();
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label = p => p.ten_diem || p.thon_ban || p.ma_vi_tri || 'Chưa có tên';
let fit=null, VIEW={s:1,ox:0,oy:0};
// Bounding box of the model (surface + soil walls) in unscaled screen units for the fixed camera.
function computeFit(){
  const ca=Math.cos(angle),sa=Math.sin(angle),st=Math.sin(tilt),ct=Math.cos(tilt);let x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
  for(const row of terrain.worldGrid) for(const p of row){ if(!p) continue; const X=p[0]*ca-p[2]*sa, Z=p[0]*sa+p[2]*ca;
    for(const y of [p[1],-.035]){const Y=Z*st-y*ct;if(X<x0)x0=X;if(X>x1)x1=X;if(Y<y0)y0=Y;if(Y>y1)y1=Y;} }
  fit={cx:(x0+x1)/2,cy:(y0+y1)/2,w:x1-x0,h:y1-y0};
}
function baseScale(w,h){return Math.min(w*.9/fit.w,(h-60)*.9/fit.h);}
function view(w,h){const s=baseScale(w,h)*zoom;return {s,ox:w/2+panX-fit.cx*s,oy:h/2+18+panY-fit.cy*s};}
function clampPan(){const w=canvas.clientWidth,h=canvas.clientHeight,s=baseScale(w,h)*zoom;
  if(zoom<=1){panX=panY=0;return;}
  const mx=Math.max(0,(fit.w*s-w*.9)/2+w*.05), my=Math.max(0,(fit.h*s-h*.9)/2+h*.05);
  panX=Math.max(-mx,Math.min(mx,panX));panY=Math.max(-my,Math.min(my,panY));}
function schedule() { if (!frame) frame = requestAnimationFrame(() => { frame = 0; render(); }); }
function resize() { const r = canvas.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2); canvas.width = Math.round(r.width*dpr); canvas.height = Math.round(r.height*dpr); ctx.setTransform(dpr,0,0,dpr,0,0); bufCanvas.width=canvas.width; bufCanvas.height=canvas.height; bctx.setTransform(dpr,0,0,dpr,0,0); schedule(); }
function terrainHeight(lon, lat) {
  const x = Math.round((lon-terrain.west)/(terrain.east-terrain.west)*(terrain.width-1));
  const y = Math.round((terrain.north-lat)/(terrain.north-terrain.south)*(terrain.height-1));
  for (let r=0;r<=5;r++) for (let dy=-r;dy<=r;dy++) for (let dx=-r;dx<=r;dx++) {
    const v = terrain.heights[y+dy]?.[x+dx]; if (v != null) return v;
  }
  return null;
}
function world(lon,lat,height) {
  const x = (lon-terrain.west)/(terrain.east-terrain.west)-.5;
  const z = ((terrain.north-lat)/(terrain.north-terrain.south)-.5)*.78;
  return [x, Math.max(0,(height-terrain.minHeight))*0.00065, z];
}
function project(p,w,h) {
  const [x,y,z]=p, ca=Math.cos(angle), sa=Math.sin(angle), x1=x*ca-z*sa, z1=x*sa+z*ca;
  return {x:VIEW.ox+x1*VIEW.s,y:VIEW.oy+(z1*Math.sin(tilt)-y*Math.cos(tilt))*VIEW.s,depth:z1*Math.cos(tilt)+y*Math.sin(tilt)};
}
function render() {
  if (!terrain||!fit) return;
  const w=canvas.clientWidth,h=canvas.clientHeight;ctx.clearRect(0,0,w,h);VIEW=view(w,h);
  const useImagery=terrainRenderer && terrainRenderer.render(angle,tilt,VIEW.s,VIEW.ox-w*.5,VIEW.oy-h*.54,true);
  if (!useImagery) {
  const rows=terrain.heights, grid=terrain.worldGrid.map(row=>row.map(p=>p && project(p,w,h))), faces=[];
  for(let y=0;y<terrain.height-1;y++) for(let x=0;x<terrain.width-1;x++) {
    const a=grid[y][x], b=grid[y][x+1], c=grid[y+1][x], d=grid[y+1][x+1];
    if(a&&b&&c&&d) {
      const avg=(rows[y][x]+rows[y][x+1]+rows[y+1][x]+rows[y+1][x+1])/4;
      const slope=(rows[y][x]-rows[y+1][x+1])*1.1;
      const v=Math.max(0,Math.min(1,(avg-terrain.minHeight)/(terrain.maxHeight-terrain.minHeight)));
      const shade=Math.max(-35,Math.min(35,slope));
      const stops=[[30,73,45],[42,110,55],[106,145,57],[196,147,61],[202,91,45]];
      const f=Math.min(3.999,v*4), i=Math.floor(f), a=f-i;
      const rgb=stops[i].map((n,j)=>Math.round(Math.max(0,Math.min(255,n*(1-a)+stops[i+1][j]*a+shade))));
      faces.push({a,b,c,d,depth:(a.depth+b.depth+c.depth+d.depth)/4,color:`rgb(${rgb.join(',')})`});
    }
  }
  faces.sort((a,b)=>a.depth-b.depth);
  for(const f of faces) {ctx.fillStyle=f.color;ctx.beginPath();ctx.moveTo(f.a.x,f.a.y);ctx.lineTo(f.b.x,f.b.y);ctx.lineTo(f.d.x,f.d.y);ctx.lineTo(f.c.x,f.c.y);ctx.closePath();ctx.fill();}
  }
  function pathLine(vertices, stroke, width) {
    ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();let drawing=false;
    for(const pt of vertices){if(!pt){drawing=false;continue;}const q=project(pt,w,h);if(!drawing){ctx.moveTo(q.x,q.y);drawing=true;}else ctx.lineTo(q.x,q.y);}ctx.stroke();
  }
  function polygon(vertices,color) {
    if(vertices.length<3)return;ctx.fillStyle=color;ctx.beginPath();vertices.forEach((v,i)=>{const q=project(v,w,h);if(i===0)ctx.moveTo(q.x,q.y);else ctx.lineTo(q.x,q.y);});ctx.closePath();ctx.fill();
  }
  if(!useImagery && $('layer-water').checked){
    for(const p of layers.water) polygon(p.vertices.filter(Boolean),'#397b80');
    for(const p of layers.waterways) pathLine(p.vertices,'#58a0a0',1.4);
  }
  if($('layer-roads').checked){
    for(const p of layers.roads){const major=['primary','secondary','trunk','motorway'].includes(p.kind);pathLine(p.vertices,major?'rgba(244,226,160,.85)':'rgba(226,232,206,.32)',major?1.7:0.7);}
  }
  const showPts=$('layer-points').checked;
  if(showPts) for(const p of visible){
    if(!p.ring) continue;const col=LEVELS[levelOf(p)].color, sel=p===selected;
    ctx.beginPath();p.ring.forEach((v,i)=>{const q=project(v,w,h);i?ctx.lineTo(q.x,q.y):ctx.moveTo(q.x,q.y);});ctx.closePath();
    ctx.fillStyle=rgba(col,sel?.24:.09);ctx.fill();ctx.setLineDash([4,3]);ctx.lineWidth=sel?1.6:1;ctx.strokeStyle=rgba(col,sel?.95:.5);ctx.stroke();ctx.setLineDash([]);
  }
  if($('layer-buildings').checked){
    const detail=zoom>=2.2, list=[];
    for(const b of layers.buildings){const q=project(b.center,w,h);if(q.x<-30||q.x>w+30||q.y<-30||q.y>h+30)continue;list.push({b,d:q.depth});}
    list.sort((a,b)=>a.d-b.d);
    bctx.clearRect(0,0,w,h);const hot=[];
    for(const {b} of list){if(impacted.has(b)){hot.push(b);continue;}drawBuilding(bctx,b,detail,'#7b8c78','#e9e5cc',false);}
    ctx.save();ctx.globalAlpha=.5;ctx.drawImage(bufCanvas,0,0,w,h);ctx.restore();
    for(const b of hot) drawBuilding(ctx,b,detail,'#8e3920','#ff9550',true);
  }
  drawContext(w,h);
  projectedPoints=[];
  if(showPts){
    const fl=[];
    for(const p of visible){if(!p.base)continue;const q=project(p.base,w,h);if(q.x<-40||q.x>w+40||q.y<-60||q.y>h+40)continue;fl.push({p,q});}
    fl.sort((a,b)=>a.q.depth-b.q.depth);
    for(const f of fl) if(f.p!==selected) drawFlag(f.p,f.q,false);
    const s=fl.find(f=>f.p===selected); if(s) drawFlag(s.p,s.q,true);
  }
  function drawBuilding(c,b,detail,wall,roof,hot){
    const poly=(vs,col)=>{c.fillStyle=col;c.beginPath();vs.forEach((v,i)=>{const q=project(v,w,h);i?c.lineTo(q.x,q.y):c.moveTo(q.x,q.y);});c.closePath();c.fill();};
    if(detail){const base=b.vertices,top=b.roof;for(let i=0;i<base.length-1;i++) poly([base[i],base[i+1],top[i+1],top[i]],wall);}
    poly(detail?b.roof:b.vertices,roof);
    if(hot){c.lineWidth=detail?.8:1.1;c.strokeStyle=roof;c.stroke();}
  }
  function drawFlag(p,q,sel){
    const col=LEVELS[levelOf(p)].color, H=sel?42:28, fw=sel?21:15, fh=sel?14:10, r=sel?28:18;
    ctx.save();ctx.translate(q.x,q.y);ctx.scale(1,.42);
    const g=ctx.createRadialGradient(0,0,0,0,0,r);g.addColorStop(0,rgba(col,.8));g.addColorStop(.35,rgba(col,.35));g.addColorStop(1,rgba(col,0));
    ctx.fillStyle=g;ctx.beginPath();ctx.arc(0,0,r,0,7);ctx.fill();ctx.restore();
    ctx.fillStyle='rgba(8,18,14,.6)';ctx.beginPath();ctx.ellipse(q.x,q.y,3.4,1.5,0,0,7);ctx.fill();
    const top=q.y-H;
    ctx.lineCap='round';ctx.strokeStyle='rgba(10,20,16,.55)';ctx.lineWidth=3.2;ctx.beginPath();ctx.moveTo(q.x,q.y);ctx.lineTo(q.x,top);ctx.stroke();
    ctx.strokeStyle='#f3f0e2';ctx.lineWidth=1.6;ctx.beginPath();ctx.moveTo(q.x,q.y);ctx.lineTo(q.x,top);ctx.stroke();
    const x0=q.x+.8,y0=top+1;
    ctx.beginPath();ctx.moveTo(x0,y0);ctx.bezierCurveTo(x0+fw*.35,y0-3,x0+fw*.65,y0+3,x0+fw,y0+1);ctx.lineTo(x0+fw,y0+fh+1);
    ctx.bezierCurveTo(x0+fw*.65,y0+fh+3,x0+fw*.35,y0+fh-3,x0,y0+fh);ctx.closePath();
    const fg=ctx.createLinearGradient(x0,y0,x0+fw,y0+fh);fg.addColorStop(0,shadeHex(col,1.18));fg.addColorStop(1,shadeHex(col,.75));
    ctx.fillStyle=fg;ctx.fill();ctx.lineWidth=sel?1.6:.8;ctx.strokeStyle=sel?'#ffe27a':'rgba(20,18,12,.5)';ctx.stroke();
    ctx.fillStyle=sel?'#ffe27a':'#fbf8ec';ctx.beginPath();ctx.arc(q.x,top,sel?2.7:1.9,0,7);ctx.fill();
    projectedPoints.push({p,x:q.x+fw*.4,y:top+fh*.5,fx:q.x,fy:q.y});
  }
}
function updateList() {
 const query=$('search').value.trim().toLocaleLowerCase('vi'), status=$('status').value;
 visible=points.filter(p=>(!status||p.trang_thai===status)&&[p.ten_diem,p.thon_ban,p.xa_cu,p.ma_vi_tri].some(v=>String(v||'').toLocaleLowerCase('vi').includes(query)));
 $('visible-count').textContent=visible.length;
 impacted=new Set();for(const p of visible) for(const b of p.nearBuildings||[]) impacted.add(b);
 for(const k in LEVELS){const el=$('lv-'+k);if(el)el.textContent=visible.filter(p=>levelOf(p)===k).length;}
 $('point-list').innerHTML=visible.length ? visible.map((p,i)=>`<button class="point-item ${p===selected?'active':''}" data-index="${points.indexOf(p)}"><span class="point-index">${String(i+1).padStart(2,'0')}</span><span class="point-info"><strong>${escapeHTML(label(p))}</strong><small>${escapeHTML(p.ma_vi_tri||'—')} · ${escapeHTML(p.trang_thai||'Chưa rõ')}</small></span><span class="point-arrow">↗</span></button>`).join('') : '<div class="empty">Không tìm thấy vị trí phù hợp.</div>';
 schedule();
}
function contextBlock(p){
 const stat=(n,t)=>`<div class="ctx-stat"><strong>${n}</strong><span>${t}</span></div>`;
 const pois=(p.poisNear||[]).slice(0,4).map(({o,d})=>`<li><i style="background:${POI_STYLE[o.group].c}">${POI_STYLE[o.group].g}</i>${escapeHTML(o.name||POI_KIND[o.kind]||o.kind)}<small>${Math.round(d)} m</small></li>`).join('');
 return `<div class="ctx"><div class="ctx-grid">${stat((p.nearBuildings||[]).length,`công trình trong ${IMPACT_RADIUS} m`)}${stat(p.yagiNear??'—','vết trượt Yagi trong 300 m')}${stat(p.yagiNearest!=null?Math.round(p.yagiNearest)+' m':'—','tới vết trượt gần nhất')}${stat(isFinite(p.faultNear)?(p.faultNear>=1000?(p.faultNear/1000).toFixed(1)+' km':Math.round(p.faultNear)+' m'):'—','tới đứt gãy gần nhất')}</div>`+
  (p.geo?`<div class="ctx-geo"><span>NỀN ĐỊA CHẤT</span><b>${escapeHTML(p.geo.group||'')}</b><small>${escapeHTML(p.geo.unit||'')}</small></div>`:'')+
  (pois?`<div class="ctx-poi"><span>CƠ SỞ THIẾT YẾU TRONG 500 M</span><ul>${pois}</ul></div>`:'')+`</div>`;
}
function row(name,value) {return value===null||value===undefined||value===''?'':`<div class="detail-row"><span>${name}</span><strong>${escapeHTML(value)}</strong></div>`;}
function selectPoint(p,fly=true) {
 selected=p;if(fly)flyTo(p);$('details').classList.add('open');
 $('detail-content').innerHTML=`<div class="detail-kicker" style="color:${LEVELS[levelOf(p)].color}">● ${escapeHTML(LEVELS[levelOf(p)].name.toUpperCase())} · ${escapeHTML(p.trang_thai||'CHƯA RÕ')}</div><h3>${escapeHTML(label(p))}</h3>`+
 contextBlock(p)+row('MÃ VỊ TRÍ',p.ma_vi_tri)+row('ĐỊA DANH CŨ',p.xa_cu)+row('NHÓM VỊ TRÍ',p.nhom_vi_tri)+row('TỌA ĐỘ WGS84',`${(+p.lat_wgs84).toFixed(6)}, ${(+p.lon_wgs84).toFixed(6)}`)+row('ĐỘ CAO',p.cao_do_m!=null?`${p.cao_do_m} m`:null)+row('ĐỘ DỐC',p.do_doc_do!=null?`${p.do_doc_do}°`:null)+row('MƯA TRUNG BÌNH NĂM',p.mua_tb_nam_mm!=null?`${p.mua_tb_nam_mm} mm`:null)+row('NGUỒN DỮ LIỆU',p.nguon)+row('ĐỘ TIN CẬY VỊ TRÍ',p.do_tin_cay_vi_tri)+row('THỜI GIAN XẢY RA',p.thoi_gian_xay_ra)+row('KIỂU TRƯỢT',p.kieu_truot)+row('NGUY CƠ TRƯỢT TIẾP',p.nguy_co_truot_tiep)+row('THIỆT HẠI',p.thiet_hai)+row('MÔ TẢ',p.mo_ta)+ (p.co_cap_trung_can_ra_soat ? row('LƯU Ý','Có cặp trùng cần rà soát') : '');
 updateList();
}
$('point-list').addEventListener('click',e=>{const button=e.target.closest('[data-index]');if(button)selectPoint(points[Number(button.dataset.index)]);});
$('close-details').onclick=()=>{selected=null;$('details').classList.remove('open');updateList();};
$('search').addEventListener('input',updateList);$('status').addEventListener('change',updateList);
$('reset-filter').onclick=()=>{$('search').value='';$('status').value='';updateList();};
const MIN_ZOOM=.6, MAX_ZOOM=16;
function changeZoom(factor,x=canvas.clientWidth/2,y=canvas.clientHeight/2) {
  if(!fit) return;
  const w=canvas.clientWidth,h=canvas.clientHeight,v=view(w,h),next=Math.max(MIN_ZOOM,Math.min(MAX_ZOOM,zoom*factor));
  const ux=(x-v.ox)/v.s, uy=(y-v.oy)/v.s; zoom=next; const s2=baseScale(w,h)*zoom;
  panX=x-w/2+fit.cx*s2-ux*s2; panY=y-h/2-18+fit.cy*s2-uy*s2; clampPan();
  $('zoom-level').textContent=zoom.toFixed(1)+'×';schedule();
}
$('zoom-in').onclick=()=>changeZoom(1.35);
$('zoom-out').onclick=()=>changeZoom(1/1.35);
$('reset-view').onclick=()=>{zoom=1;panX=panY=0;$('zoom-level').textContent='1.0×';schedule();};
canvas.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('pointerdown',e=>{if(e.button!==0&&e.button!==2)return;dragging=true;moved=false;dragPan=false;lastX=startX=e.clientX;lastY=startY=e.clientY;canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(dragging&&Math.hypot(e.clientX-startX,e.clientY-startY)>3)moved=true;});
canvas.addEventListener('pointerup',e=>{if(!dragging)return;dragging=false;if(!moved&&e.button===0&&!dragPan){const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;let closest=null,dist=16;for(let i=projectedPoints.length-1;i>=0;i--){const q=projectedPoints[i];const d=Math.min(Math.hypot(q.x-x,q.y-y),Math.hypot(q.fx-x,q.fy-y)+4);if(d<dist){dist=d;closest=q.p;}}if(closest)selectPoint(closest);}});
canvas.addEventListener('pointercancel',()=>dragging=false);
canvas.addEventListener('wheel',e=>{e.preventDefault();const rect=canvas.getBoundingClientRect();changeZoom(Math.exp(-e.deltaY*.001),e.clientX-rect.left,e.clientY-rect.top);},{passive:false});
window.addEventListener('resize',resize);
for(const id of ['layer-roads','layer-buildings','layer-water','layer-points']) $(id).addEventListener('change',schedule);
fetch('/assets/data.json').then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}).then(data=>{
 terrain=data.terrain;layers=data.layers;points=data.points;const vals=terrain.heights.flat().filter(v=>v!=null);terrain.minHeight=Math.min(...vals);terrain.maxHeight=Math.max(...vals);
 $('elevation-min').textContent=Math.round(terrain.minHeight)+' m';$('elevation-max').textContent=Math.round(terrain.maxHeight)+' m';
 for(const key of ['roads','waterways','water','buildings','railways']) for(const item of layers[key]||[]) item.vertices=item.coords.map(p=>p&&p[2]!=null?world(p[0],p[1],p[2]):null);
 terrain.worldGrid=terrain.heights.map((row,y)=>row.map((height,x)=>height==null?null:world(terrain.west+(terrain.east-terrain.west)*x/(terrain.width-1),terrain.north-(terrain.north-terrain.south)*y/(terrain.height-1),height)));
 try { terrainRenderer=window.createTerrainRenderer($('terrain-gl'),terrain,world,schedule,layers); } catch (e) { $('imagery-status').textContent='Không thể khởi tạo ảnh vệ tinh; đang dùng bản đồ địa hình.'; console.error(e); }
 computeFit();
 points.forEach(p=>{p.mapHeight=terrainHeight(p.lon_wgs84,p.lat_wgs84);});
 const mLat=110540, mLon=lat=>111320*Math.cos(lat*Math.PI/180);
 for(const b of layers.buildings){const c=b.coords.filter(Boolean);b.lon=c.reduce((s,q)=>s+q[0],0)/c.length;b.lat=c.reduce((s,q)=>s+q[1],0)/c.length;const hh=c.reduce((s,q)=>s+q[2],0)/c.length;b.center=world(b.lon,b.lat,hh);b.roof=b.vertices.map(v=>[v[0],v[1]+.0022,v[2]]);}
 points.forEach(p=>{
   p.nearBuildings=[];const kx=mLon(p.lat_wgs84);
   for(const b of layers.buildings){const dx=(b.lon-p.lon_wgs84)*kx,dy=(b.lat-p.lat_wgs84)*mLat;if(dx*dx+dy*dy<=IMPACT_RADIUS*IMPACT_RADIUS)p.nearBuildings.push(b);}
   if(p.mapHeight==null) return;
   p.base=world(p.lon_wgs84,p.lat_wgs84,p.mapHeight);p.ring=[];
   for(let i=0;i<48;i++){const a=i/48*Math.PI*2,lon=p.lon_wgs84+Math.cos(a)*IMPACT_RADIUS/kx,lat=p.lat_wgs84+Math.sin(a)*IMPACT_RADIUS/mLat;p.ring.push(world(lon,lat,terrainHeight(lon,lat)??p.mapHeight));}
 });
 $('total').textContent=points.length;$('risk-total').textContent=points.filter(p=>p.trang_thai==='Nguy cơ').length;$('occurred-total').textContent=points.filter(p=>p.trang_thai==='Đã xảy ra').length;
 prepareContext();
 $('loading').hidden=true;updateList();resize();syncOverlays();setMode('satellite');
}).catch(err=>{$('loading').textContent='Không thể tải dữ liệu. Vui lòng kiểm tra máy chủ và tải lại trang.';console.error(err);});

// Header list dropdown toggle
(()=>{const t=document.getElementById('list-toggle'),p=document.getElementById('list-panel');if(!t||!p)return;
const set=o=>{p.hidden=!o;t.setAttribute('aria-expanded',String(o));};
t.addEventListener('click',e=>{e.stopPropagation();set(p.hidden);});
document.getElementById('search').addEventListener('focus',()=>set(true));
document.getElementById('status').addEventListener('change',()=>set(true));
document.addEventListener('click',e=>{if(!e.target.closest('.list-dropdown')&&!e.target.closest('#search')&&!e.target.closest('#status'))set(false);});
document.addEventListener('keydown',e=>{if(e.key==='Escape')set(false);});})();

// ================= Context layers, hover tooltip, fly-to, base modes =================
const POI_STYLE={y_te:{c:'#e2574c',g:'+',n:'Y tế'},giao_duc:{c:'#4b8fe0',g:'T',n:'Giáo dục'},hanh_chinh:{c:'#8a6ae0',g:'★',n:'Cơ quan, an ninh'},cong_cong:{c:'#3aa39a',g:'●',n:'Công trình công cộng'}};
const POI_KIND={hospital:'Bệnh viện',clinic:'Phòng khám',pharmacy:'Nhà thuốc',school:'Trường học',college:'Trường cao đẳng',kindergarten:'Trường mầm non',university:'Trường đại học',police:'Công an',townhall:'Trụ sở UBND',community_centre:'Nhà văn hóa',fire_station:'PCCC',stadium:'Sân vận động',museum:'Bảo tàng',library:'Thư viện',mall:'Trung tâm thương mại',supermarket:'Siêu thị',marketplace:'Chợ'};
let projectedPois=[], projectedYagi=[], hoverKey=null;
const mLatK=110540, mLonK=lat=>111320*Math.cos(lat*Math.PI/180);
const distM=(lon1,lat1,lon2,lat2)=>Math.hypot((lon2-lon1)*mLonK(lat1),(lat2-lat1)*mLatK);
function pointInRings(lon,lat,rings){let inside=false;for(const r of rings){for(let i=0,j=r.length-1;i<r.length;j=i++){const [xi,yi]=r[i],[xj,yj]=r[j];if(((yi>lat)!==(yj>lat))&&(lon<(xj-xi)*(lat-yi)/(yj-yi)+xi))inside=!inside;}}return inside;}
function prepareContext(){
  for(const k of ['places','pois']) for(const o of layers[k]||[]) o.base=world(o.lon,o.lat,o.h??terrainHeight(o.lon,o.lat)??terrain.minHeight);
  for(const y of layers.yagi||[]) {const h=terrainHeight(y.lon,y.lat);y.base=h==null?null:world(y.lon,y.lat,h);}
  for(const p of points){
    const lon=p.lon_wgs84,lat=p.lat_wgs84;
    const g=(layers.geology||[]).find(g=>pointInRings(lon,lat,g.rings)); p.geo=g||null;
    const ys=(layers.yagi||[]).map(y=>({y,d:distM(lon,lat,y.lon,y.lat)})).sort((a,b)=>a.d-b.d);
    p.yagiNear=ys.filter(o=>o.d<=300).length; p.yagiNearest=ys[0]?ys[0].d:null;
    p.poisNear=(layers.pois||[]).map(o=>({o,d:distM(lon,lat,o.lon,o.lat)})).filter(o=>o.d<=500).sort((a,b)=>a.d-b.d);
    p.faultNear=Math.min(Infinity,...(layers.faults||[]).flatMap(f=>f.coords.map(c=>distM(lon,lat,c[0],c[1]))));
  }
  $('n-yagi').textContent=(layers.yagi||[]).length;$('n-faults').textContent=(layers.faults||[]).length;$('n-points').textContent=points.length;
}
function drawContext(w,h){
  if($('layer-roads').checked) for(const r of layers.railways||[]){
    pathLineCtx(r.vertices,'rgba(25,25,25,.85)',3.4,[]);pathLineCtx(r.vertices,'#f4f1e6',1.6,[5,5]);
  }
  projectedYagi=[];
  if($('layer-yagi').checked) for(const y of layers.yagi||[]){if(!y.base)continue;const q=project(y.base,w,h);if(q.x>-10&&q.x<w+10&&q.y>-10&&q.y<h+10)projectedYagi.push({y,x:q.x,y0:q.y});}
  projectedPois=[];
  if(!$('layer-places').checked) return;
  const showPoi=zoom>=1.4, taken=[];
  function placeLabel(t,x,y,size){ctx.font=`600 ${size}px Inter,system-ui,sans-serif`;const tw=ctx.measureText(t).width+6,r={x0:x-tw/2,x1:x+tw/2,y0:y-size,y1:y+size*.6};
    if(taken.some(o=>r.x0<o.x1&&r.x1>o.x0&&r.y0<o.y1&&r.y1>o.y0))return;taken.push(r);label(t,x,y,size,'#fff',false);}
  if(showPoi) for(const o of layers.pois||[]){
    const q=project(o.base,w,h);if(q.x<-20||q.x>w+20||q.y<-20||q.y>h+20)continue;const st=POI_STYLE[o.group];
    ctx.fillStyle='rgba(0,0,0,.35)';ctx.beginPath();ctx.ellipse(q.x,q.y+1,5,2,0,0,7);ctx.fill();
    ctx.beginPath();ctx.arc(q.x,q.y-7,7,0,7);ctx.fillStyle=st.c;ctx.fill();ctx.lineWidth=1.5;ctx.strokeStyle='#fff';ctx.stroke();
    ctx.fillStyle='#fff';ctx.font='bold 9px Inter,system-ui,sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(st.g,q.x,q.y-6.5);
    if(zoom>=3.5&&o.name) placeLabel(o.name,q.x,q.y-20,10);
    projectedPois.push({o,x:q.x,y:q.y-7});
  }
  for(const pl of layers.places||[]){const q=project(pl.base,w,h);if(q.x<-80||q.x>w+80||q.y<-20||q.y>h+20)continue;
    const big=pl.kind==='city';label((big?'':'')+pl.name.toUpperCase(),q.x,q.y,big?13:11,big?'#fff7dc':'#eef3e6',true);}
  function label(t,x,y,size,col,spaced){ctx.font=`${spaced?700:600} ${size}px Inter,system-ui,sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';
    if(spaced&&'letterSpacing' in ctx)ctx.letterSpacing='2px';ctx.lineWidth=3.5;ctx.strokeStyle='rgba(10,22,18,.85)';ctx.lineJoin='round';ctx.strokeText(t,x,y);ctx.fillStyle=col;ctx.fillText(t,x,y);if('letterSpacing' in ctx)ctx.letterSpacing='0px';}
  function pathLineCtx(vs,stroke,width,dash){ctx.save();ctx.setLineDash(dash);ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.lineJoin='round';ctx.lineCap='butt';ctx.beginPath();let on=false;for(const pt of vs){if(!pt){on=false;continue;}const q=project(pt,w,h);on?ctx.lineTo(q.x,q.y):ctx.moveTo(q.x,q.y);on=true;}ctx.stroke();ctx.restore();}
}
// ---- hover tooltip ----
const tip=$('tip');
function showTip(html,x,y){tip.innerHTML=html;tip.hidden=false;const r=canvas.getBoundingClientRect(),tw=tip.offsetWidth,th=tip.offsetHeight;
  let X=x+16,Y=y-th-10;if(X+tw>r.width-8)X=x-tw-16;if(Y<8)Y=y+18;tip.style.left=X+'px';tip.style.top=Y+'px';}
function hideTip(){tip.hidden=true;hoverKey=null;canvas.style.cursor='default';}
canvas.addEventListener('pointerleave',hideTip);
canvas.addEventListener('pointermove',e=>{
  if(dragging) return;const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  let best=null,bd=16;
  for(let i=projectedPoints.length-1;i>=0;i--){const q=projectedPoints[i];const d=Math.min(Math.hypot(q.x-x,q.y-y),Math.hypot(q.fx-x,q.fy-y)+4);if(d<bd){bd=d;best={t:'pt',v:q.p};}}
  if(!best) for(const q of projectedPois){const d=Math.hypot(q.x-x,q.y-y);if(d<10&&d<bd){bd=d;best={t:'poi',v:q.o};}}
  if(!best) for(const q of projectedYagi){const d=Math.hypot(q.x-x,q.y0-y);if(d<Math.max(8,zoom*3)&&d<bd){bd=d;best={t:'yagi',v:q.y};}}
  if(!best){hideTip();return;}
  canvas.style.cursor=best.t==='pt'?'pointer':'default';
  const v=best.v;let html='';
  if(best.t==='pt'){const L=LEVELS[levelOf(v)];html=`<div class="tip-k" style="color:${L.color}">● ${L.name}</div><b>${escapeHTML(label(v))}</b><span>${escapeHTML(v.ma_vi_tri||'')} · ${escapeHTML(v.trang_thai||'')}</span><span>${(v.nearBuildings||[]).length} công trình trong ${IMPACT_RADIUS} m${v.yagiNear?` · ${v.yagiNear} vết trượt Yagi trong 300 m`:''}</span><em>Bấm để xem chi tiết</em>`;}
  else if(best.t==='poi'){const st=POI_STYLE[v.group];html=`<div class="tip-k" style="color:${st.c}">● ${st.n}</div><b>${escapeHTML(v.name||POI_KIND[v.kind]||v.kind)}</b><span>${escapeHTML(POI_KIND[v.kind]||v.kind)}</span>`;}
  else {html=`<div class="tip-k" style="color:#ff8a5c">● Vết trượt sau bão Yagi</div><b>${Math.round(v.area).toLocaleString('vi-VN')} m²</b><span>Phát sinh ${escapeHTML(v.day||'—')} · độ dốc ${v.slope??'—'}°</span><span>Mưa lớn nhất: ${v.r24} mm/24h · ${v.r72} mm/72h</span><span>Độ tin cậy nhận dạng: ${escapeHTML(v.conf||'—')}</span>`;}
  showTip(html,x,y);
});
// ---- fly to a point (zoom only; keeps the model centred on it) ----
let flight=0;
function flyTo(p,target=Math.max(zoom,3.2)){
  if(!p.base||!fit) return;cancelAnimationFrame(flight);
  const w=canvas.clientWidth,h=canvas.clientHeight,ca=Math.cos(angle),sa=Math.sin(angle);
  const X=p.base[0]*ca-p.base[2]*sa,Z=p.base[0]*sa+p.base[2]*ca,Y=Z*Math.sin(tilt)-p.base[1]*Math.cos(tilt);
  const z0=zoom,px0=panX,py0=panY,t0=performance.now(),dur=750;
  const s1=baseScale(w,h)*target, tx=-(X-fit.cx)*s1, ty=-18-(Y-fit.cy)*s1+h*.06;
  const step=now=>{const k=Math.min(1,(now-t0)/dur),e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
    zoom=z0+(target-z0)*e;panX=px0+(tx-px0)*e;panY=py0+(ty-py0)*e;clampPan();$('zoom-level').textContent=zoom.toFixed(1)+'×';render();
    if(k<1)flight=requestAnimationFrame(step);};
  flight=requestAnimationFrame(step);
}
// ---- base mode + legends ----
function setMode(mode){
  for(const b of document.querySelectorAll('#base-mode button')){const on=b.dataset.mode===mode;b.classList.toggle('on',on);b.setAttribute('aria-checked',String(on));}
  terrainRenderer&&terrainRenderer.setOptions({mode});
  const ml=$('mode-legend'),sl=$('scale-label');
  if(mode==='slope'&&terrainRenderer){const names=['< 8°','8–15°','15–25°','25–35°','> 35°'];
    ml.innerHTML='<div class="ml-title">ĐỘ DỐC ĐỊA HÌNH</div>'+terrainRenderer.SLOPE_CLASSES.map((c,i)=>`<span><i style="background:rgb(${c[1].join(',')})"></i>${names[i]}</span>`).join('');ml.hidden=false;sl.hidden=true;}
  else if(mode==='geology'&&terrainRenderer){const groups=[...new Set((layers.geology||[]).map(g=>g.group))];
    ml.innerHTML='<div class="ml-title">NHÓM ĐÁ (BẢN ĐỒ 1:200.000)</div>'+groups.map(g=>`<span><i style="background:${terrainRenderer.GEO_COLORS[g]||'#bbb'}"></i>${escapeHTML(g)}</span>`).join('');ml.hidden=false;sl.hidden=true;}
  else {ml.hidden=true;sl.hidden=false;}
}
document.getElementById('base-mode').addEventListener('click',e=>{const b=e.target.closest('button[data-mode]');if(b)setMode(b.dataset.mode);});
function syncOverlays(){terrainRenderer&&terrainRenderer.setOptions({water:$('layer-water').checked,yagi:$('layer-yagi').checked,faults:$('layer-faults').checked});
  $('lg-yagi').hidden=!$('layer-yagi').checked;$('lg-fault').hidden=!$('layer-faults').checked;$('lg-poi').hidden=!$('layer-places').checked;schedule();}
for(const id of ['layer-water','layer-yagi','layer-faults','layer-places']) $(id).addEventListener('change',syncOverlays);
$('layer-toggle').addEventListener('click',()=>{const p=$('layer-panel'),c=p.classList.toggle('collapsed');$('layer-toggle').setAttribute('aria-expanded',String(!c));});
document.addEventListener('keydown',e=>{if(e.target.closest('input,select,textarea'))return;
  if(e.key==='+'||e.key==='=')changeZoom(1.35);else if(e.key==='-'||e.key==='_')changeZoom(1/1.35);else if(e.key==='0')$('reset-view').click();
  else if(e.key==='Escape'&&$('details').classList.contains('open'))$('close-details').click();});
