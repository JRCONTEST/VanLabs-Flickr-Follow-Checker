import json, os, re, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CACHE = {}
LOCK = threading.Lock()
PATTERN = re.compile(r'^https://www\\.flickr\\.com/people/[A-Za-z0-9@._%-]+/?$')
TTL = 1800

def check(url):
    if not isinstance(url, str) or not PATTERN.fullmatch(url):
        return {'status':'unknown','code':None}
    with LOCK:
        old = CACHE.get(url)
        if old and time.time()-old[0] < TTL:
            return old[1]
    result = {'status':'unknown','code':None}
    try:
        req = Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; VanLabsStatusChecker/1.0)','Accept':'text/html'}, method='GET')
        with urlopen(req, timeout=9) as response:
            code = response.status
            body = response.read(240000).decode('utf-8', errors='replace')
            visible_410 = bool(re.search(r'(?is)(?:<h[1-6][^>]*>\s*410\s*</h[1-6]>|\b410\b.{0,120}questa non (?:è|&egrave;|&#232;) la pagina che)', body))
            result = {'status':'gone' if visible_410 or code == 410 else 'ok' if code == 200 else 'other','code':code,'reason':'page_410' if visible_410 else 'http_410' if code == 410 else 'http'}
    except HTTPError as e:
        result = {'status':'gone' if e.code == 410 else 'other','code':e.code}
    except (URLError, TimeoutError, OSError, ValueError):
        pass
    with LOCK:
        CACHE[url] = (time.time(), result)
    return result

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()
    def send_cors_headers(self):
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin','https://vanlabs-flickr-follow-checker.onrender.com')
        self.send_header('Access-Control-Allow-Methods','GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.send_header('Cache-Control','no-store')
    def do_GET(self):
        if self.path == '/health':
            self.respond({'ok':True});return
        if self.path != '/check':
            self.send_response(404);self.send_cors_headers();self.end_headers();return
        try:
            with open('profiles.json',encoding='utf-8') as f:
                urls=json.load(f)
            with ThreadPoolExecutor(max_workers=6) as pool:
                jobs={pool.submit(check,u):u for u in urls}
                results={jobs[j]:j.result() for j in as_completed(jobs)}
            self.respond({'results':results,'checked_at':int(time.time())})
        except Exception:
            self.respond({'error':'verification_unavailable'},500)
    def respond(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_cors_headers()
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),Handler).serve_forever()
