'use strict';
// The satellite image is requested at runtime; it is not redistributed with the app.
window.createTerrainRenderer = function (canvas, terrain, world, onChange) {
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
    attribute vec3 position; attribute vec2 uv; attribute float light;
    uniform float angle; uniform float tilt; uniform vec2 resolution; uniform vec2 pan; uniform float scale;
    varying vec2 texCoord; varying float shade;
    void main(){
      float ca=cos(angle),sa=sin(angle);
      float x=position.x*ca-position.z*sa, z=position.x*sa+position.z*ca;
      float px=resolution.x*.5+pan.x+x*scale;
      float py=resolution.y*.54+pan.y+(z*sin(tilt)-position.y*cos(tilt))*scale;
      float depth=z*cos(tilt)+position.y*sin(tilt);
      gl_Position=vec4(px/resolution.x*2.0-1.0,1.0-py/resolution.y*2.0,-depth*.5,1.0);
      texCoord=uv; shade=light;
    }`));
  gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`
    precision mediump float; uniform sampler2D imagery; varying vec2 texCoord; varying float shade;
    void main(){ vec4 c=texture2D(imagery,texCoord); gl_FragColor=vec4(c.rgb*shade,1.0); }
  `));
  gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
  const vertices=[];
  function lighting(x,y){
    const center=terrain.heights[y][x], value=(xx,yy)=>terrain.heights[yy]?.[xx] ?? center;
    const dx=((value(x+1,y)-value(x-1,y))*.00065)/(2/(terrain.width-1));
    const dz=((value(x,y+1)-value(x,y-1))*.00065)/(2*.78/(terrain.height-1));
    const length=Math.hypot(dx,1,dz), dot=(-dx*-.45+1*.84-dz*-.3)/length;
    return Math.max(.55,Math.min(1.23,.58+dot*.60));
  }
  const add=(x,y)=>{const h=terrain.heights[y][x];const lon=terrain.west+(terrain.east-terrain.west)*x/(terrain.width-1);const lat=terrain.north-(terrain.north-terrain.south)*y/(terrain.height-1);const p=world(lon,lat,h);vertices.push(...p,x/(terrain.width-1),y/(terrain.height-1),lighting(x,y));};
  for(let y=0;y<terrain.height-1;y++) for(let x=0;x<terrain.width-1;x++) {
    if(terrain.heights[y][x]==null||terrain.heights[y][x+1]==null||terrain.heights[y+1][x]==null||terrain.heights[y+1][x+1]==null) continue;
    add(x,y);add(x+1,y);add(x,y+1);add(x+1,y);add(x+1,y+1);add(x,y+1);
  }
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.STATIC_DRAW);
  gl.useProgram(program);
  for(const [name,size,offset] of [['position',3,0],['uv',2,12],['light',1,20]]) {const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,24,offset);}
  function makeTexture() {
    const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    return texture;
  }
  const fallbackTexture=makeTexture(), texture=makeTexture();
  const pixels=new Uint8Array(terrain.width*terrain.height*4);
  const stops=[[30,73,45],[42,110,55],[106,145,57],[196,147,61],[202,91,45]];
  for(let y=0;y<terrain.height;y++) for(let x=0;x<terrain.width;x++) {
    const height=terrain.heights[y][x] ?? terrain.minHeight;
    const v=Math.max(0,Math.min(.9999,(height-terrain.minHeight)/(terrain.maxHeight-terrain.minHeight)))*4;
    const i=Math.floor(v),a=v-i,index=(y*terrain.width+x)*4;
    for(let c=0;c<3;c++)pixels[index+c]=Math.round(stops[i][c]*(1-a)+stops[i+1][c]*a);
    pixels[index+3]=255;
  }
  gl.bindTexture(gl.TEXTURE_2D,fallbackTexture);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,terrain.width,terrain.height,0,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
  let ready=false, failed=false;
  const img=new Image(); img.crossOrigin='anonymous';
  img.onload=()=>{try {gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,img);ready=true;status.textContent='Ảnh vệ tinh trực tuyến · Esri';onChange();} catch(e){status.textContent='Không thể sử dụng ảnh; đang dùng bản đồ địa hình.';console.error(e);}};
  img.onerror=()=>{failed=true;status.textContent='Không tải được ảnh vệ tinh. Kiểm tra kết nối Internet.';onChange();};
  const params=new URLSearchParams({bbox:[terrain.west,terrain.south,terrain.east,terrain.north].join(','),bboxSR:'4326',imageSR:'4326',size:'4096,'+Math.round(4096*(terrain.north-terrain.south)/(terrain.east-terrain.west)),format:'jpg',f:'image'});
  setTimeout(()=>{if(!ready&&!failed) status.textContent='Đang chờ ảnh vệ tinh; kiểm tra Internet nếu tải quá lâu.';},15000);
  img.src='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?'+params;
  return {
    render(angle,tilt,zoom,panX,panY,enabled){
      const w=canvas.clientWidth,h=canvas.clientHeight,dpr=Math.min(window.devicePixelRatio||1,2);
      if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
      gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);gl.useProgram(program);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,ready&&enabled?texture:fallbackTexture);
      gl.uniform2f(gl.getUniformLocation(program,'pan'),panX,panY);gl.uniform1i(gl.getUniformLocation(program,'imagery'),0);gl.uniform1f(gl.getUniformLocation(program,'angle'),angle);gl.uniform1f(gl.getUniformLocation(program,'tilt'),tilt);gl.uniform1f(gl.getUniformLocation(program,'scale'),Math.min(w*.77,h*.88)*zoom);gl.uniform2f(gl.getUniformLocation(program,'resolution'),w,h);
      gl.drawArrays(gl.TRIANGLES,0,vertices.length/6);return true;
    }
  };
};
