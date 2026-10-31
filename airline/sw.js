// 내용을 바꾸면 버전을 올립니다
const CACHE='airline-note-v1';
const FILES=['./','index.html','manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png','img/i-006-000.webp','img/i-010-001.webp','img/i-012-002.webp','img/i-019-003.webp','img/i-019-004.webp','img/i-020-005.webp','img/i-022-007.webp','img/i-025-008.webp','img/i-028-015.webp','img/i-035-016.webp','img/i-041-017.webp','img/i-041-018.webp','img/i-043-019.webp','img/i-044-020.webp','img/i-045-021.webp','img/i-045-022.webp','img/i-045-023.webp','img/i-047-024.webp','img/i-052-025.webp','img/i-052-026.webp','img/i-056-029.webp','img/i-056-030.webp','img/i-056-031.webp','img/i-056-032.webp','img/i-056-033.webp','img/i-056-034.webp','img/i-058-035.webp','img/i-060-036.webp','img/i-067-037.webp','img/i-070-039.webp','img/i-070-040.webp','img/i-070-041.webp','img/i-077-042.webp','img/i-083-043.webp','img/i-084-044.webp','img/i-084-045.webp','img/i-084-046.webp','img/i-091-047.webp','img/i-091-048.webp','img/i-091-049.webp','img/i-091-050.webp','img/i-091-051.webp'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith('airline-note-v')&&k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  e.respondWith(fetch(e.request).then(r=>{const cp=r.clone();caches.open(CACHE).then(c=>c.put(e.request,cp));return r;})
    .catch(()=>caches.match(e.request,{ignoreSearch:true}).then(r=>r||caches.match('index.html'))));
});
