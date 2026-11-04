// 저장해 둔 내용을 먼저 보여주고, 서버에 새 내용이 '정상적으로' 있을 때만 몰래 갱신합니다.
// 링크(폴더)를 닫아 404가 나와도 저장본은 덮어쓰지 않습니다.
const CACHE='airline-note-v12';
const FILES=['./','index.html','manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png','img/i-006-000.webp','img/i-010-001.webp','img/i-012-002.webp','img/i-019-003.webp','img/i-019-004.webp','img/i-020-005.webp','img/i-022-007.webp','img/i-025-008.webp','img/i-028-015.webp','img/i-035-016.webp','img/i-041-017.webp','img/i-041-018.webp','img/i-043-019.webp','img/i-044-020.webp','img/i-045-021.webp','img/i-045-022.webp','img/i-045-023.webp','img/i-047-024.webp','img/i-052-025.webp','img/i-052-026.webp','img/i-056-029.webp','img/i-056-030.webp','img/i-056-031.webp','img/i-056-032.webp','img/i-056-033.webp','img/i-056-034.webp','img/i-058-035.webp','img/i-060-036.webp','img/i-067-037.webp','img/i-070-039.webp','img/i-070-040.webp','img/i-070-041.webp','img/i-077-042.webp','img/i-083-043.webp','img/i-084-044.webp','img/i-084-045.webp','img/i-084-046.webp','img/i-091-047.webp','img/i-091-048.webp','img/i-091-049.webp','img/i-091-050.webp','img/i-091-051.webp'];
// 휴대폰·CDN 캐시에 남은 예전 파일을 피하려고 주소 뒤에 버전 꼬리표를 붙여 받습니다
const bust=f=>f+(f.indexOf('?')>-1?'&':'?')+'sw='+CACHE;
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>Promise.all(FILES.map(f=>fetch(bust(f),{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(f);return c.put(f,r);})))));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith('airline-note-v')&&k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);
  if(u.origin!==location.origin)return; // 실시간 기상(aviationweather.gov) 등 외부 요청은 그대로 통과
  if(u.pathname.indexOf('/wx/')>-1){ // 기상·NOTAM 데이터는 항상 최신 우선, 실패 시 저장본
    e.respondWith(fetch(e.request,{cache:'no-store'}).then(r=>{if(r.ok){const cp=r.clone();caches.open(CACHE).then(c=>c.put(u.origin+u.pathname,cp));}return r;}).catch(()=>caches.match(u.origin+u.pathname)));
    return;
  }
  const net=fetch(u.href,{cache:'no-cache'}).then(r=>{if(r&&r.ok){const cp=r.clone();caches.open(CACHE).then(c=>c.put(e.request,cp));}return r;});
  e.respondWith(caches.match(e.request,{ignoreSearch:true}).then(hit=>{
    if(hit){e.waitUntil(net.catch(()=>{}));return hit;}
    return net.then(r=>r.ok?r:caches.match('index.html').then(i=>i||r)).catch(()=>caches.match('index.html'));
  }));
});
self.addEventListener('message',e=>{
  const port=e.ports&&e.ports[0]; if(!port)return;
  const t=e.data&&e.data.type;
  const check=()=>caches.open(CACHE).then(c=>Promise.all(FILES.map(f=>c.match(f,{ignoreSearch:true})))).then(rs=>{const n=rs.filter(Boolean).length;return {ok:n===FILES.length,count:n,total:FILES.length,version:CACHE};});
  if(t==='status'){e.waitUntil(check().then(r=>port.postMessage(r)).catch(()=>port.postMessage({ok:false})));}
  if(t==='save'){e.waitUntil(caches.open(CACHE).then(c=>Promise.all(FILES.map(f=>fetch(bust(f),{cache:'no-store'}).then(r=>{if(r.ok)return c.put(f,r);}).catch(()=>{})))).then(check).then(r=>port.postMessage(r)).catch(()=>port.postMessage({ok:false})));}
});
