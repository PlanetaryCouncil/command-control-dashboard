"""Generated selfies on GitHub, revealed through the secure ultra PoW flow.

The catalog deliberately includes public original URLs: bypass is allowed.
PoW verifies the normal reveal flow, not access control over the public image.
"""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

BITS = 13
MIN_SECONDS = 1.0
TTL = 120
LIMIT = 512


def directory():
    return Path(os.environ.get("FLEET_PORTRAITS",
                Path.home() / ".local/share/command-control/portraits")).resolve()


def catalog():
    """Operator-curated GitHub originals; public URLs are intentional."""
    try:
        records = json.loads((directory() / "catalog.json").read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(records, list):
        return []
    return [{"id": r["id"], "who": str(r.get("who", "anonymous"))[:80],
             "caption": str(r.get("caption", ""))[:400], "url": r["url"]}
            for r in records if isinstance(r, dict)
            and re.fullmatch(r"[a-z0-9-]{1,64}", str(r.get("id", "")))
            and github_image_url(r.get("url"))]


def github_image_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and not url.username and not url.password
                and url.port in (None, 443)
                and (url.hostname == "raw.githubusercontent.com"
                     or (url.hostname or "").endswith(".github.io")))
    except ValueError:
        return False


class Gate:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.pending = {}
        self.lock = threading.Lock()

    def issue(self, identifier):
        now = self.clock()
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items()
                            if now - v[1] < TTL}
            if len(self.pending) >= LIMIT:
                raise OverflowError("busy; try again shortly")
            token = secrets.token_hex(32)
            self.pending[token] = (identifier, now)
        return {"challenge": token, "bits": BITS, "min_seconds": MIN_SECONDS,
                "expires_seconds": TTL, "algorithm": "SHA-256(challenge:nonce)"}

    def redeem(self, identifier, token, nonce):
        if not re.fullmatch(r"[0-9a-f]{64}", token):
            return False
        if not re.fullmatch(r"[0-9]{1,16}", nonce):
            return False
        digest = hashlib.sha256(f"{token}:{nonce}".encode()).digest()
        if int.from_bytes(digest, "big") >> (256 - BITS):
            return False
        with self.lock:
            entry = self.pending.get(token)
            if entry is None or entry[0] != identifier:
                return False
            age = self.clock() - entry[1]
            if age < MIN_SECONDS or age >= TTL:
                return False
            del self.pending[token]  # one image response; parallel replay fails
        return True


GATE = Gate()

WORKER = """
self.onmessage = async ({data:c}) => {
  try {
    const enc = new TextEncoder();
    for (let nonce=0; nonce<Number.MAX_SAFE_INTEGER; nonce++) {
      const hash = new Uint8Array(await crypto.subtle.digest('SHA-256',
        enc.encode(c.challenge + ':' + nonce)));
      const bytes=Math.floor(c.bits/8), rest=c.bits%8;
      if (hash.slice(0,bytes).every(b=>b===0) &&
          (!rest || hash[bytes] >>> (8-rest) === 0)) {
        postMessage({nonce:String(nonce)}); return;
      }
    }
    throw new Error('No solution found');
  } catch(e) { postMessage({error:e.message}); }
};
"""

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>secure ultra · Generated selfies</title><style>
:root{--mono:ui-monospace,monospace;--border:#24473c;--raised:#10221b;
--ink:#d7eee3;--muted:#7dffb0}*{box-sizing:border-box}
body{margin:0;background:#050b09;color:var(--ink);font:16px/1.6 var(--mono)}
main{max-width:960px;margin:auto;padding:28px 20px}header{display:flex;flex-wrap:wrap}
h1{font-size:28px;color:var(--muted)}a{color:var(--muted)}
article{border:1px solid var(--border);padding:24px;margin:24px 0}
button{font:inherit;background:var(--raised);color:var(--muted);border:1px solid
var(--border);padding:12px 18px;cursor:pointer}button:disabled{opacity:.6}
img{display:block;width:100%;height:auto;margin-top:20px}small{opacity:.8}
</style><style>__NAVCSS__</style><main><header>__NAV__</header>
<h1>Generated selfies</h1><p>ASCII faces stay open on the
<a href="https://planetarycouncil.github.io/selfie-gallery/">selfie wall</a>.
These illustrated portraits take a little work to reveal.</p>
<p>secure ultra</p>
<p><small>About a second of computation, depending on your device.
Originals hosted on GitHub.</small></p>
<div id="portraits" aria-live="polite">Loading portraits…</div></main>
<script>
const host=document.getElementById('portraits');
async function json(url){const r=await fetch(url,{cache:'no-store'});
 if(!r.ok)throw new Error('Request failed ('+r.status+')');return r.json();}
async function reveal(card,button,id){
 button.disabled=true;button.textContent='Working to reveal…';
 let worker, timer;
 try {
  const c=await json('/api/portraits/'+id+'/challenge');
  const started=performance.now();
  const result=await new Promise((resolve,reject)=>{
   worker=new Worker('/api/portraits/worker.js');
   timer=setTimeout(()=>reject(new Error('Work timed out; try again')),90000);
   worker.onmessage=({data})=>data.error?reject(new Error(data.error)):resolve(data);
   worker.onerror=()=>reject(new Error('Your browser could not run the work'));
   worker.postMessage(c);
  });
  await new Promise(r=>setTimeout(r,Math.max(0,c.min_seconds*1000+100-(performance.now()-started))));
  const q=new URLSearchParams({challenge:c.challenge,nonce:result.nonce});
  const response=await fetch('/api/portraits/'+id+'/image?'+q,{cache:'no-store'});
  if(!response.ok)throw new Error('Reveal failed ('+response.status+'); try again');
  const original=await response.json();
  const image=document.createElement('img');image.alt='Illustrated selfie: '+id;
  image.onerror=()=>{image.remove();
    button.hidden=false;button.textContent='Image could not load; retry';};
  image.src=original.url;card.appendChild(image);button.hidden=true;
 }catch(e){button.textContent=e.message+' — retry';}
 finally{clearTimeout(timer);if(worker)worker.terminate();button.disabled=false;}
}
json('/api/portraits').then(items=>{
 host.textContent=items.length?'':'No generated portraits yet.';
 for(const p of items){const card=document.createElement('article');
  const title=document.createElement('h2');title.textContent=p.who;card.appendChild(title);
  const caption=document.createElement('p');caption.textContent=p.caption;card.appendChild(caption);
  const button=document.createElement('button');button.textContent='Reveal portrait · ~1 second of work';
  button.onclick=()=>reveal(card,button,p.id);card.appendChild(button);
  const source=document.createElement('p'),link=document.createElement('a');
  link.href=p.url;link.textContent='Original on GitHub';source.appendChild(link);
  card.appendChild(source);host.appendChild(card);}
}).catch(e=>host.textContent=e.message);
</script></html>"""


def page(nav_html="", nav_css=""):
    return PAGE.replace("__NAV__", nav_html).replace("__NAVCSS__", nav_css).encode()


def handle(handler, path):
    """Return True for every portrait route, including malformed requests."""
    if path != "/portraits" and not (path == "/api/portraits" or
                                        path.startswith("/api/portraits/")):
        return False
    if path == "/portraits":
        import nav
        handler._send(page(nav.html(path, remote=handler._remote()), nav.CSS))
    elif path == "/api/portraits":
        handler._send(json.dumps(catalog()).encode(), "application/json")
    elif path == "/api/portraits/worker.js":
        handler._send(WORKER.encode(), "text/javascript; charset=utf-8")
    else:
        match = re.fullmatch(r"/api/portraits/([a-z0-9-]{1,64})/(challenge|image)", path)
        if not match:
            handler.send_error(404)
            return True
        identifier, action = match.groups()
        portrait = next((r for r in catalog() if r["id"] == identifier), None)
        if portrait is None:
            handler.send_error(404)
            return True
        if action == "challenge":
            if handler._flooding("portrait-challenges"):
                return True
            try:
                challenge = GATE.issue(identifier)
            except OverflowError:
                handler._send(b'{"error":"busy; retry shortly"}', "application/json", code=429)
                return True
            handler._send(json.dumps(challenge).encode(), "application/json")
        else:
            from urllib.parse import parse_qs, urlsplit
            q = parse_qs(urlsplit(handler.path).query)
            if not GATE.redeem(identifier, q.get("challenge", [""])[0],
                               q.get("nonce", [""])[0]):
                handler._send(b'{"error":"fresh proof of work required"}',
                              "application/json", code=403)
            else:
                handler._send(json.dumps({"url": portrait["url"]}).encode(),
                              "application/json")
    return True
