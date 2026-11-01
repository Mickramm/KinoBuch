// Kinobuch Service Worker – macht die App offline nutzbar.
// Bei einem Update der App diese Versionsnummer erhöhen:
const CACHE='kinobuch-1.1';
const CORE=['./','./index.html','./manifest.webmanifest','./icon-192.png','./icon-512.png','./apple-touch-icon.png'];
const fresh=u=>new Request(u,{cache:'reload'});
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(async c=>{
  await c.addAll(CORE.map(fresh));
  try{await c.add(fresh('./filmdb.json'))}catch(_){}   // Film-Datenbank ist optional
}).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const r=e.request;if(r.method!=='GET')return;
  const url=new URL(r.url);
  const font=url.hostname==='fonts.googleapis.com'||url.hostname==='fonts.gstatic.com';
  if(url.origin!==location.origin&&!font)return;
  // Sofort aus dem Cache antworten und im Hintergrund aktualisieren.
  // So kommt eine neue Film-Datenbank automatisch beim übernächsten Start an.
  e.respondWith(caches.open(CACHE).then(async c=>{
    const hit=await c.match(r,{ignoreSearch:url.origin===location.origin});
    const net=fetch(r).then(res=>{if(res&&(res.ok||res.type==='opaque'))c.put(r,res.clone());return res}).catch(()=>hit);
    if(hit){e.waitUntil(net.catch(()=>{}));return hit}
    return net;
  }));
});
