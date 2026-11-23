'use strict';
// WebGL "sa bàn" renderer: terrain surface + soil side walls + base plate + soft shadow, depth fog.
// The satellite image is requested at runtime; it is not redistributed with the app.
window.createTerrainRenderer = function (canvas, terrain, world, onChange, layers) {
  const status = document.getElementById('imagery-status');
  const gl = canvas.getContext('webgl', {alpha: true, antialias: true, preserveDrawingBuffer: true});
  if (!gl) { status.textContent = 'Trình duyệt không hỗ trợ WebGL; đang dùng bản đồ địa hình.'; return null; }
  function shader(type, source) {
    const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(s));
    return s;
  }
  const program=gl.createProgram();
  gl.attachShader(program,shader(gl.VERTEX_SHADER,`
    attribute vec3 position; attribute vec2 uv; attribute float light; attribute float kind;
    uniform float angle; uniform float tilt; uniform vec2 resolution; uniform vec2 pan; uniform float scale;
    varying vec2 texCoord; varying float shade; varying float vKind; varying float vY; varying float vDepth;
    void main(){
      float ca=cos(angle),sa=sin(angle);
      float x=position.x*ca-position.z*sa, z=position.x*sa+position.z*ca;
      float px=resolution.x*.5+pan.x+x*scale;
      float py=resolution.y*.54+pan.y+(z*sin(tilt)-position.y*cos(tilt))*scale;
      float depth=z*cos(tilt)+position.y*sin(tilt);
      gl_Position=vec4(px/resolution.x*2.0-1.0,1.0-py/resolution.y*2.0,-depth*.5,1.0);
      texCoord=uv; shade=light; vKind=kind; vY=position.y; vDepth=depth;
    }`));
  gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`
    precision mediump float;
    uniform sampler2D imagery; uniform vec3 fogColor; uniform float fogAmount;
    varying vec2 texCoord; varying float shade; varying float vKind; varying float vY; varying float vDepth;
    void main(){
      if(vKind>2.5){ // soft drop shadow under the board
        float a=smoothstep(1.0,0.35,length(texCoord))*0.55;
        gl_FragColor=vec4(0.0,0.0,0.0,a); return;
      }
      vec3 c;
      if(vKind<0.5){
        c=texture2D(imagery,texCoord).rgb*shade;
      } else if(vKind<1.5){
        // soil wall: horizontal strata, darker with depth, dark topsoil + grass lip near the surface
        float fromTop=texCoord.x-vY;
        float b=fract(vY*70.0+0.15*sin(vY*900.0));
        vec3 s=mix(vec3(.55,.40,.26),vec3(.44,.31,.20),smoothstep(.45,.55,b));
        s=mix(s,vec3(.63,.50,.33),smoothstep(.80,.86,b)*(1.0-smoothstep(.93,.99,b))*.7);
        s*=mix(.55,1.0,clamp((vY+.035)/.12,0.0,1.0));
        s=mix(vec3(.24,.18,.12),s,smoothstep(.002,.006,fromTop));
        s=mix(vec3(.22,.38,.20),s,smoothstep(.0,.0018,fromTop));
        c=s*shade;
      } else {
        // base board: dark slate with a lighter bevel band near the edge (texCoord = distance to edge)
        vec3 board=vec3(.115,.165,.145);
        board=mix(vec3(.30,.36,.31),board,smoothstep(.0,.008,texCoord.x));
        c=board*shade;
      }
      float f=clamp((0.15-vDepth)/0.8,0.0,1.0)*fogAmount;
      c=mix(c,fogColor,f);
      gl_FragColor=vec4(c,1.0);
    }
  `));
  gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));

  const W=terrain.width, H=terrain.height, hs=terrain.heights;
  const valid=(x,y)=>x>=0&&y>=0&&x<W&&y<H&&hs[y][x]!=null;
  const cellValid=(x,y)=>valid(x,y)&&valid(x+1,y)&&valid(x,y+1)&&valid(x+1,y+1);
  const EXAG=.00065, BASE=-.035, PLATE=.016, MARGIN=.045, ZS=.78;

  // Box-blurred height for a cheap ambient-occlusion term (valleys darker, ridges lighter).
  function blur(src,r){
    const out=[];for(let y=0;y<H;y++){out.push(new Array(W).fill(null));for(let x=0;x<W;x++){if(src[y][x]==null)continue;let s=0,n=0;for(let dy=-r;dy<=r;dy++){const row=src[y+dy];if(!row)continue;for(let dx=-r;dx<=r;dx++){const v=row[x+dx];if(v!=null){s+=v;n++;}}}out[y][x]=s/n;}}
    return out;
  }
  const near=blur(hs,2), far=blur(hs,6);
  function lighting(x,y){
    const c=hs[y][x], v=(xx,yy)=>hs[yy]?.[xx] ?? c;
    const dx=((v(x+1,y)-v(x-1,y))*EXAG)/(2/(W-1));
    const dz=((v(x,y+1)-v(x,y-1))*EXAG)/(2*ZS/(H-1));
    const len=Math.hypot(dx,1,dz), nx=-dx/len, ny=1/len, nz=-dz/len;
    const key=Math.max(0,nx*-.55+ny*.70+nz*-.45);      // warm key light from NW
    const fill=Math.max(0,nx*.45+ny*.80+nz*.40)*.35;    // soft fill from SE
    const sky=.35+.25*ny;
    const ao=Math.max(-1,Math.min(1,((c-near[y][x])*.6+(c-far[y][x])*.4)/14));
    return Math.max(.38,Math.min(1.35,(sky+key*.72+fill)*(1+ao*.22)));
  }
  const data=[];
  const push=(p,u,v,l,k)=>data.push(p[0],p[1],p[2],u,v,l,k);
  const gx=x=>terrain.west+(terrain.east-terrain.west)*x/(W-1), gy=y=>terrain.north-(terrain.north-terrain.south)*y/(H-1);
  const P=(x,y)=>world(gx(x),gy(y),hs[y][x]);

  // 3) terrain surface (kind 0)
  for(let y=0;y<H-1;y++) for(let x=0;x<W-1;x++){
    if(!cellValid(x,y)) continue;
    const v=(xx,yy)=>push(P(xx,yy),xx/(W-1),yy/(H-1),lighting(xx,yy),0);
    v(x,y);v(x+1,y);v(x,y+1);v(x+1,y);v(x+1,y+1);v(x,y+1);
  }
  // 4) soil walls along the outline (kind 1). texCoord.x carries the surface height at that column.
  const wall=(ax,ay,bx,by,l)=>{
    const a=P(ax,ay), b=P(bx,by), ab=[a[0],BASE,a[2]], bb=[b[0],BASE,b[2]];
    push(a,a[1],0,l,1);push(b,b[1],0,l,1);push(ab,a[1],0,l,1);
    push(b,b[1],0,l,1);push(bb,b[1],0,l,1);push(ab,a[1],0,l,1);
  };
  for(let y=0;y<H-1;y++) for(let x=0;x<W-1;x++){
    if(!cellValid(x,y)) continue;
    if(!cellValid(x,y-1)) wall(x,y,x+1,y,.80);        // north face
    if(!cellValid(x,y+1)) wall(x,y+1,x+1,y+1,.86);    // south face
    if(!cellValid(x-1,y)) wall(x,y,x,y+1,.82);        // west face
    if(!cellValid(x+1,y)) wall(x+1,y,x+1,y+1,.84);    // east face
  }
  const vertexCount=data.length/7;
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);
  gl.useProgram(program);
  for(const [name,size,offset] of [['position',3,0],['uv',2,12],['light',1,20],['kind',1,24]]) {const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,28,offset);}
  const U={};for(const n of ['angle','tilt','resolution','pan','scale','imagery','fogColor','fogAmount']) U[n]=gl.getUniformLocation(program,n);

  // ---- surface texture: base (satellite or elevation palette) + rivers painted on top ----
  function makeTexture() {
    const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    return t;
  }
  const TW=2048, TH=Math.round(2048*(H-1)/(W-1));
  const palette=document.createElement('canvas');palette.width=W;palette.height=H;
  {
    const pc=palette.getContext('2d'), im=pc.createImageData(W,H);
    const stops=[[38,84,58],[64,118,66],[112,148,78],[168,164,104],[206,186,138],[226,214,180]];
    for(let y=0;y<H;y++) for(let x=0;x<W;x++){
      const h=hs[y][x] ?? terrain.minHeight, t=Math.max(0,Math.min(.9999,(h-terrain.minHeight)/(terrain.maxHeight-terrain.minHeight)));
      const f=Math.pow(t,.85)*(stops.length-1), i=Math.floor(f), a=f-i, o=(y*W+x)*4;
      for(let c=0;c<3;c++) im.data[o+c]=Math.round(stops[i][c]*(1-a)+stops[i+1][c]*a);
      im.data[o+3]=255;
    }
    pc.putImageData(im,0,0);
  }
  const tx=lon=>(lon-terrain.west)/(terrain.east-terrain.west)*TW, ty=lat=>(terrain.north-lat)/(terrain.north-terrain.south)*TH;
  // Slope (degrees) per DEM cell, from real ground spacing.
  const mx=(terrain.east-terrain.west)/(W-1)*111320*Math.cos((terrain.north+terrain.south)/2*Math.PI/180), my=(terrain.north-terrain.south)/(H-1)*110540;
  const slopeAt=(x,y)=>{const c=hs[y][x];if(c==null)return null;const v=(xx,yy)=>hs[yy]?.[xx]??c;
    const gx=(v(x+1,y)-v(x-1,y))/(2*mx), gy=(v(x,y+1)-v(x,y-1))/(2*my);return Math.atan(Math.hypot(gx,gy))*180/Math.PI;};
  const SLOPE_CLASSES=[[8,[96,170,92]],[15,[176,200,96]],[25,[240,206,92]],[35,[236,138,58]],[90,[206,62,50]]];
  const slopeCanvas=document.createElement('canvas');slopeCanvas.width=W;slopeCanvas.height=H;
  {
    const pc=slopeCanvas.getContext('2d'), im=pc.createImageData(W,H);
    for(let y=0;y<H;y++) for(let x=0;x<W;x++){const sl=slopeAt(x,y)??0, o=(y*W+x)*4, c=SLOPE_CLASSES.find(k=>sl<k[0])[1];im.data[o]=c[0];im.data[o+1]=c[1];im.data[o+2]=c[2];im.data[o+3]=255;}
    pc.putImageData(im,0,0);
  }
  const GEO_COLORS={'Trầm tích bở rời Đệ Tứ':'#e8d9a0','Đá trầm tích lục nguyên':'#c9a27a','Đá carbonat':'#7fb2d6','Đá biến chất':'#c48fb8','Đá magma xâm nhập':'#d9665a'};
  const ringPath=(c,rings)=>{c.beginPath();for(const r of rings){r.forEach((p,i)=>{const X=tx(p[0]),Y=ty(p[1]);i?c.lineTo(X,Y):c.moveTo(X,Y);});c.closePath();}};
  function paintGeology(c){
    for(const g of layers.geology||[]){ringPath(c,g.rings);c.fillStyle=GEO_COLORS[g.group]||'#bbb';c.fill('evenodd');}
    c.save();c.globalAlpha=.55;c.lineWidth=2;c.strokeStyle='#3c3326';for(const g of layers.geology||[]){ringPath(c,g.rings);c.stroke();}c.restore();
  }
  function paintWater(c){
    c.save();c.lineJoin='round';c.lineCap='round';
    c.shadowColor='rgba(110,205,230,.85)';c.shadowBlur=10;
    for(const w of layers.water||[]){
      c.beginPath();
      for(const ring of [w.coords,...(w.holes||[])]){let first=true;for(const p of ring){if(!p)continue;const X=tx(p[0]),Y=ty(p[1]);first?c.moveTo(X,Y):c.lineTo(X,Y);first=false;}c.closePath();}
      c.fillStyle='#2b86ad';c.fill('evenodd');c.lineWidth=2.5;c.strokeStyle='#8fe1f2';c.stroke();
    }
    for(const w of layers.waterways||[]){
      const river=w.kind==='river';
      c.beginPath();let on=false;for(const p of w.coords){if(!p){on=false;continue;}const X=tx(p[0]),Y=ty(p[1]);on?c.lineTo(X,Y):c.moveTo(X,Y);on=true;}
      c.lineWidth=river?9:4;c.strokeStyle='#2b86ad';c.stroke();
      c.shadowBlur=0;c.lineWidth=river?3:1.4;c.strokeStyle=river?'#3d9fc6':'#9fe6f5';c.stroke();c.shadowBlur=10;
    }
    c.restore();
  }
  function paintYagi(c){
    c.save();c.lineJoin='round';
    for(const y of layers.yagi||[]){ringPath(c,y.rings);c.fillStyle='rgba(122,52,30,.92)';c.fill('evenodd');}
    c.shadowColor='rgba(255,120,70,.9)';c.shadowBlur=6;c.lineWidth=2;c.strokeStyle='#ff8a5c';
    for(const y of layers.yagi||[]){ringPath(c,y.rings);c.stroke();}
    c.restore();
  }
  function paintFaults(c){
    c.save();c.lineCap='round';
    for(const f of layers.faults||[]){
      const deep=/sâu/.test(f.kind||'');
      c.beginPath();f.coords.forEach((p,i)=>{const X=tx(p[0]),Y=ty(p[1]);i?c.lineTo(X,Y):c.moveTo(X,Y);});
      c.setLineDash([]);c.lineWidth=7;c.strokeStyle='rgba(40,10,40,.45)';c.stroke();
      c.setLineDash(deep?[18,12]:[]);c.lineWidth=3.2;c.strokeStyle=deep?'#d58cff':'#f05bd2';c.stroke();
    }
    c.restore();
  }
  const comp=document.createElement('canvas');comp.width=TW;comp.height=TH;const cc=comp.getContext('2d');
  const texture=makeTexture();
  const opts={mode:'satellite',water:true,yagi:false,faults:false};
  let ready=false, failed=false;
  const img=new Image(); img.crossOrigin='anonymous';
  function compose(){
    cc.clearRect(0,0,TW,TH);cc.imageSmoothingEnabled=true;cc.imageSmoothingQuality='high';
    const base=opts.mode==='satellite'&&ready?img:opts.mode==='slope'?slopeCanvas:palette;
    cc.drawImage(base,0,0,TW,TH);
    if(opts.mode==='geology'){cc.save();cc.globalAlpha=.88;paintGeology(cc);cc.restore();}
    if(opts.mode==='slope'){cc.save();cc.globalAlpha=.25;cc.drawImage(palette,0,0,TW,TH);cc.restore();}
    if(opts.water) paintWater(cc);
    if(opts.yagi) paintYagi(cc);
    if(opts.faults) paintFaults(cc);
    gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,comp);
  }
  try{compose();}catch(e){console.error(e);}
  img.onload=()=>{ready=true;try {compose();status.textContent='Ảnh vệ tinh trực tuyến · Esri';onChange();} catch(e){ready=false;compose();status.textContent='Không thể sử dụng ảnh; đang dùng bản đồ địa hình.';console.error(e);}};
  img.onerror=()=>{failed=true;status.textContent='Không tải được ảnh vệ tinh — đang hiển thị nền độ cao.';onChange();};
  const params=new URLSearchParams({bbox:[terrain.west,terrain.south,terrain.east,terrain.north].join(','),bboxSR:'4326',imageSR:'4326',size:'4096,'+Math.round(4096*(terrain.north-terrain.south)/(terrain.east-terrain.west)),format:'jpg',f:'image'});
  setTimeout(()=>{if(!ready&&!failed) status.textContent='Đang chờ ảnh vệ tinh; kiểm tra Internet nếu tải quá lâu.';},15000);
  img.src='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?'+params;

  return {
    slopeAt, SLOPE_CLASSES, GEO_COLORS,
    setOptions(o){ Object.assign(opts,o); compose(); onChange(); },
    render(angle,tilt,scale,panX,panY,enabled){
      const w=canvas.clientWidth,h=canvas.clientHeight,dpr=Math.min(window.devicePixelRatio||1,2);
      if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
      gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
      gl.useProgram(program);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);
      gl.uniform2f(U.pan,panX,panY);gl.uniform1i(U.imagery,0);gl.uniform1f(U.angle,angle);gl.uniform1f(U.tilt,tilt);
      gl.uniform1f(U.scale,scale);gl.uniform2f(U.resolution,w,h);
      gl.uniform3f(U.fogColor,.075,.145,.12);gl.uniform1f(U.fogAmount,.42);
      gl.drawArrays(gl.TRIANGLES,0,vertexCount);
      return true;
    }
  };
};
