'use strict';
const $ = id => document.getElementById(id);
const canvas = $('map'), ctx = canvas.getContext('2d');
let terrain, terrainRenderer = null, layers = {}, points = [], visible = [], selected = null, projectedPoints = [], frame = 0;
let angle = -.45, tilt = .83, zoom = 1, panX = 0, panY = 0, panMode = false, dragging = false, moved = false, lastX = 0, lastY = 0, startX = 0, startY = 0, dragPan = false;
const colors = { 'Nguy cơ': '#d48152', 'Đã xảy ra': '#bb5343' };
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label = p => p.ten_diem || p.thon_ban || p.ma_vi_tri || 'Chưa có tên';
function schedule() { if (!frame) frame = requestAnimationFrame(() => { frame = 0; render(); }); }
function resize() { const r = canvas.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2); canvas.width = Math.round(r.width*dpr); canvas.height = Math.round(r.height*dpr); ctx.setTransform(dpr,0,0,dpr,0,0); schedule(); }
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
  const scale=Math.min(w*.77,h*.88)*zoom;
  return {x:w/2+panX+x1*scale,y:h*.54+panY+(z1*Math.sin(tilt)-y*Math.cos(tilt))*scale,depth:z1*Math.cos(tilt)+y*Math.sin(tilt)};
}
function render() {
  if (!terrain) return;
  const w=canvas.clientWidth,h=canvas.clientHeight;ctx.clearRect(0,0,w,h);
  const useImagery=terrainRenderer && terrainRenderer.render(angle,tilt,zoom,panX,panY,$('layer-imagery').checked);
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
  if($('layer-water').checked){
    for(const p of layers.water) polygon(p.vertices,'#397b80');
    for(const p of layers.waterways) pathLine(p.vertices,'#58a0a0',1.4);
  }
  if($('layer-roads').checked){
    for(const p of layers.roads){const major=['primary','secondary','trunk','motorway'].includes(p.kind);pathLine(p.vertices,major?'#dfc989':'#b3b99c',major?1.5:0.65);}
  }
  if($('layer-buildings').checked){
    const buildings=layers.buildings.map(p=>({p,q:project(p.vertices[0],w,h)})).filter(({q})=>q.x>=-50&&q.x<=w+50&&q.y>=-50&&q.y<=h+50).sort((a,b)=>a.q.depth-b.q.depth);
    for(const {p} of buildings){
      const base=p.vertices, roof=base.map(v=>[v[0],v[1]+.0018,v[2]]);
      for(let i=0;i<base.length-1;i++) polygon([base[i],base[i+1],roof[i+1],roof[i]],'#8d9a80');
      polygon(roof,'#d8d5b8');
    }
  }
  projectedPoints=[];
  for (const p of ($('layer-points').checked ? visible : [])) {
    if(p.mapHeight == null) continue;
    const q=project(world(p.lon_wgs84,p.lat_wgs84,p.mapHeight),w,h), isSelected=selected===p;
    if(q.x < -20 || q.x > w+20 || q.y < -20 || q.y > h+20) continue;
    projectedPoints.push({p,x:q.x,y:q.y-10});
    ctx.strokeStyle=isSelected?'#e4c84e':(colors[p.trang_thai]||'#888');ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(q.x,q.y);ctx.lineTo(q.x,q.y-10);ctx.stroke();
    ctx.fillStyle=isSelected?'#e3bf3f':(colors[p.trang_thai]||'#888');ctx.strokeStyle='#faf9e9';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(q.x,q.y-10,isSelected?6:4,0,Math.PI*2);ctx.fill();ctx.stroke();
  }
}
function updateList() {
 const query=$('search').value.trim().toLocaleLowerCase('vi'), status=$('status').value;
 visible=points.filter(p=>(!status||p.trang_thai===status)&&[p.ten_diem,p.thon_ban,p.xa_cu,p.ma_vi_tri].some(v=>String(v||'').toLocaleLowerCase('vi').includes(query)));
 $('visible-count').textContent=visible.length;
 $('point-list').innerHTML=visible.length ? visible.map((p,i)=>`<button class="point-item ${p===selected?'active':''}" data-index="${points.indexOf(p)}"><span class="point-index">${String(i+1).padStart(2,'0')}</span><span class="point-info"><strong>${escapeHTML(label(p))}</strong><small>${escapeHTML(p.ma_vi_tri||'—')} · ${escapeHTML(p.trang_thai||'Chưa rõ')}</small></span><span class="point-arrow">↗</span></button>`).join('') : '<div class="empty">Không tìm thấy vị trí phù hợp.</div>';
 schedule();
}
function row(name,value) {return value===null||value===undefined||value===''?'':`<div class="detail-row"><span>${name}</span><strong>${escapeHTML(value)}</strong></div>`;}
function selectPoint(p) {
 selected=p;$('details').classList.add('open');
 $('detail-content').innerHTML=`<div class="detail-kicker">● ${escapeHTML(p.trang_thai||'CHƯA RÕ')}</div><h3>${escapeHTML(label(p))}</h3>`+
 row('MÃ VỊ TRÍ',p.ma_vi_tri)+row('ĐỊA DANH CŨ',p.xa_cu)+row('NHÓM VỊ TRÍ',p.nhom_vi_tri)+row('TỌA ĐỘ WGS84',`${p.lat_wgs84}, ${p.lon_wgs84}`)+row('ĐỘ CAO',p.cao_do_m!=null?`${p.cao_do_m} m`:null)+row('ĐỘ DỐC',p.do_doc_do!=null?`${p.do_doc_do}°`:null)+row('MƯA TRUNG BÌNH NĂM',p.mua_tb_nam_mm!=null?`${p.mua_tb_nam_mm} mm`:null)+row('NGUỒN DỮ LIỆU',p.nguon)+row('ĐỘ TIN CẬY VỊ TRÍ',p.do_tin_cay_vi_tri)+row('THỜI GIAN XẢY RA',p.thoi_gian_xay_ra)+row('KIỂU TRƯỢT',p.kieu_truot)+row('NGUY CƠ TRƯỢT TIẾP',p.nguy_co_truot_tiep)+row('THIỆT HẠI',p.thiet_hai)+row('MÔ TẢ',p.mo_ta)+ (p.co_cap_trung_can_ra_soat ? row('LƯU Ý','Có cặp trùng cần rà soát') : '');
 updateList();
}
$('point-list').addEventListener('click',e=>{const button=e.target.closest('[data-index]');if(button)selectPoint(points[Number(button.dataset.index)]);});
$('close-details').onclick=()=>{selected=null;$('details').classList.remove('open');updateList();};
$('search').addEventListener('input',updateList);$('status').addEventListener('change',updateList);
$('reset-filter').onclick=()=>{$('search').value='';$('status').value='';updateList();};
const MIN_ZOOM=.55, MAX_ZOOM=16;
function changeZoom(factor,x=canvas.clientWidth/2,y=canvas.clientHeight*.54) {
  const next=Math.max(MIN_ZOOM,Math.min(MAX_ZOOM,zoom*factor)), ratio=next/zoom;
  panX=x-canvas.clientWidth/2-(x-canvas.clientWidth/2-panX)*ratio;
  panY=y-canvas.clientHeight*.54-(y-canvas.clientHeight*.54-panY)*ratio;
  zoom=next;$('zoom-level').textContent=zoom.toFixed(1)+'×';schedule();
}
$('zoom-in').onclick=()=>changeZoom(1.35);
$('zoom-out').onclick=()=>changeZoom(1/1.35);
$('reset-view').onclick=()=>{angle=-.45;tilt=.83;zoom=1;panX=panY=0;$('zoom-level').textContent='1.0×';schedule();};
$('pan-mode').onclick=()=>{panMode=!panMode;$('pan-mode').setAttribute('aria-pressed',String(panMode));$('pan-mode').classList.toggle('active',panMode);};
canvas.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('pointerdown',e=>{if(e.button!==0&&e.button!==2)return;dragging=true;moved=false;dragPan=panMode||e.shiftKey||e.button===2;lastX=startX=e.clientX;lastY=startY=e.clientY;canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(!dragging)return;const dx=e.clientX-lastX,dy=e.clientY-lastY;if(Math.hypot(e.clientX-startX,e.clientY-startY)>3)moved=true;if(dragPan){panX+=dx;panY+=dy;}else{angle+=dx*.008;tilt=Math.max(.25,Math.min(1.38,tilt+dy*.006));}lastX=e.clientX;lastY=e.clientY;schedule();});
canvas.addEventListener('pointerup',e=>{if(!dragging)return;dragging=false;if(!moved&&e.button===0&&!dragPan){const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;let closest=null,dist=14;for(const q of projectedPoints){const d=Math.hypot(q.x-x,q.y-y);if(d<dist){dist=d;closest=q.p;}}if(closest)selectPoint(closest);}});
canvas.addEventListener('pointercancel',()=>dragging=false);
canvas.addEventListener('wheel',e=>{e.preventDefault();const rect=canvas.getBoundingClientRect();changeZoom(Math.exp(-e.deltaY*.001),e.clientX-rect.left,e.clientY-rect.top);},{passive:false});
window.addEventListener('resize',resize);
for(const id of ['layer-imagery','layer-roads','layer-buildings','layer-water','layer-points']) $(id).addEventListener('change',schedule);
fetch('/assets/data.json').then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}).then(data=>{
 terrain=data.terrain;layers=data.layers;points=data.points;const vals=terrain.heights.flat().filter(v=>v!=null);terrain.minHeight=Math.min(...vals);terrain.maxHeight=Math.max(...vals);
 $('elevation-min').textContent=Math.round(terrain.minHeight)+' m';$('elevation-max').textContent=Math.round(terrain.maxHeight)+' m';
 for(const layer of Object.values(layers)) for(const item of layer) item.vertices=item.coords.map(p=>p?world(p[0],p[1],p[2]):null);
 terrain.worldGrid=terrain.heights.map((row,y)=>row.map((height,x)=>height==null?null:world(terrain.west+(terrain.east-terrain.west)*x/(terrain.width-1),terrain.north-(terrain.north-terrain.south)*y/(terrain.height-1),height)));
 try { terrainRenderer=window.createTerrainRenderer($('terrain-gl'),terrain,world,schedule); } catch (e) { $('imagery-status').textContent='Không thể khởi tạo ảnh vệ tinh; đang dùng bản đồ địa hình.'; console.error(e); }
 points.forEach(p=>{p.mapHeight=terrainHeight(p.lon_wgs84,p.lat_wgs84);});
 $('total').textContent=points.length;$('risk-total').textContent=points.filter(p=>p.trang_thai==='Nguy cơ').length;$('occurred-total').textContent=points.filter(p=>p.trang_thai==='Đã xảy ra').length;
 $('loading').hidden=true;updateList();resize();
}).catch(err=>{$('loading').textContent='Không thể tải dữ liệu. Vui lòng kiểm tra máy chủ và tải lại trang.';console.error(err);});
