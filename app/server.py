"""Loopback-only, in-memory LedgerMatch web review UI."""
from __future__ import annotations
import argparse, base64, email, email.policy, hashlib, html, json, logging, os, time
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import report
from .csvio import CsvFormatError, ImportProfile, parse_bank_csv, parse_invoice_csv
from .evidence import build_bundle, bundle_json, validate_bundle
from .matcher import reconcile

MAX_UPLOAD_MB=int(os.environ.get("LEDGERMATCH_MAX_UPLOAD_MB","10")); RATE_LIMIT=int(os.environ.get("LEDGERMATCH_RATE_LIMIT","30"))
ALLOWED_HOSTS={"127.0.0.1","localhost","[::1]"}; log=logging.getLogger("ledgermatch")
INDEX="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>LedgerMatch local review</title></head><body><main><h1>LedgerMatch</h1><p>Local, review-first reconciliation. Ambiguous combinations remain exceptions.</p><form action='/reconcile' method='post' enctype='multipart/form-data'><label>Bank CSV <input type='file' name='bank' accept='.csv,text/csv' required></label><br><label>Invoice CSV <input type='file' name='invoices' accept='.csv,text/csv' required></label><br><label>Currency <input name='currency' value='USD' maxlength='3'></label><br><label>Date format <select name='date_format'><option>YMD</option><option>DMY</option><option>MDY</option></select></label><br><label>Fee tolerance <input name='fee_tolerance' value='0'></label><br><label>Firm <input name='firm' maxlength='80'></label><br><button>Reconcile locally</button></form><p>Files are held in memory for this request and are not sent to an AI provider.</p></main></body></html>"""

def parse_multipart(content_type,body):
    raw=b"Content-Type: "+content_type.encode("latin-1","replace")+b"\r\nMIME-Version: 1.0\r\n\r\n"+body
    msg=email.message_from_bytes(raw,policy=email.policy.default); out={}
    if msg.is_multipart():
        for part in msg.iter_parts():
            name=part.get_param("name",header="content-disposition")
            if name: out[str(name)]=part.get_payload(decode=True) or b""
    return out

def error_page(message): return "<!doctype html><title>Error</title><h1>Request rejected</h1><p>"+html.escape(message)+"</p>"
def data_uri(text,mime): return f"data:{mime};base64,"+base64.b64encode(text.encode()).decode()
def result_page(result,firm,evidence_text,profile_text):
    evidence_digest=hashlib.sha256(evidence_text.encode()).hexdigest()+"  evidence.json\n"
    files=[("matches.csv",report.matches_csv(result),"text/csv"),("exceptions.csv",report.exceptions_csv(result),"text/csv"),("unpaid_invoices.csv",report.unpaid_csv(result),"text/csv"),("payments_import.csv",report.payments_import_csv(result),"text/csv"),("profile.json",profile_text,"application/json"),("evidence.json",evidence_text,"application/json"),("evidence.sha256",evidence_digest,"text/plain")]
    links=" ".join(f'<a download="{name}" href="{data_uri(text,mime)}">{name}</a>' for name,text,mime in files)
    return report.html_report(result,firm).replace("<body>","<body><nav>Download: "+links+"</nav>",1)

class Handler(BaseHTTPRequestHandler):
    server_version="LedgerMatch/0.4"; _hits=defaultdict(deque)
    def _valid_origin(self):
        host_header=self.headers.get("Host","").lower(); host=host_header
        if host_header.startswith("["): host=host_header.split("]",1)[0]+"]"
        elif ":" in host_header: host=host_header.rsplit(":",1)[0]
        if host not in ALLOWED_HOSTS: return False
        origin=self.headers.get("Origin")
        return not origin or any(origin==f"http://{h}" or origin.startswith(f"http://{h}:") for h in ALLOWED_HOSTS)
    def _rate_ok(self):
        q=self._hits[self.client_address[0]]; now=time.time()
        while q and now-q[0]>60:q.popleft()
        if len(q)>=RATE_LIMIT:return False
        q.append(now);return True
    def _send(self,code,body,ctype="text/html; charset=utf-8"):
        data=body.encode() if isinstance(body,str) else body; self.send_response(code)
        for k,v in {"Content-Type":ctype,"Content-Length":str(len(data)),"X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","Cache-Control":"no-store","Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'","X-Frame-Options":"DENY"}.items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if not self._valid_origin(): return self._send(403,error_page("Host not allowed"))
        if self.path=="/health": return self._send(200,json.dumps({"status":"ok"}),"application/json")
        if self.path in ("/","/index.html"): return self._send(200,INDEX)
        self._send(404,error_page("Not found"))
    def do_POST(self):
        if not self._valid_origin(): return self._send(403,error_page("Host or Origin not allowed"))
        if self.path!="/reconcile": return self._send(404,error_page("Not found"))
        if not self._rate_ok(): return self._send(429,error_page("Rate limit exceeded"))
        try:length=int(self.headers.get("Content-Length") or 0)
        except ValueError:length=0
        if length<=0:return self._send(411,error_page("Empty request"))
        if length>MAX_UPLOAD_MB*1024*1024:return self._send(413,error_page("Upload too large"))
        ctype=self.headers.get("Content-Type","")
        if "multipart/form-data" not in ctype:return self._send(400,error_page("Expected multipart form data"))
        self.connection.settimeout(30); body=self.rfile.read(length)
        try:
            fields=parse_multipart(ctype,body); bank=fields.get("bank"); invoices=fields.get("invoices")
            if not bank or not invoices: raise CsvFormatError("Both CSV files are required")
            bank_text=bank.decode("utf-8-sig"); invoice_text=invoices.decode("utf-8-sig")
            fee_raw=(fields.get("fee_tolerance") or b"0").decode().strip() or "0"; fee=Decimal(fee_raw)
            if fee<0 or fee>1000: raise CsvFormatError("Fee tolerance out of range")
            currency=(fields.get("currency") or b"USD").decode().strip().upper(); date_format=(fields.get("date_format") or b"YMD").decode().strip().upper()
            if len(currency)!=3 or not currency.isalpha(): raise CsvFormatError("Currency must be a three-letter code")
            profile=ImportProfile(currency,date_format,2)
            result=reconcile(parse_bank_csv(bank_text,profile),parse_invoice_csv(invoice_text,profile),fee,currency)
            profile_record={**profile.to_dict(),"fee_tolerance":str(fee)}; profile_text=json.dumps(profile_record,sort_keys=True,indent=2)+"\n"
            bundle=build_bundle(result,input_hashes={"bank_csv":hashlib.sha256(bank_text.encode()).hexdigest(),"invoice_csv":hashlib.sha256(invoice_text.encode()).hexdigest()},import_profile=profile.to_dict(),config={"fee_tolerance":str(fee)})
            errors=validate_bundle(bundle)
            if errors: raise RuntimeError("internal evidence validation failed")
            evidence_text=bundle_json(bundle); firm=(fields.get("firm") or b"").decode("utf-8","replace")[:80]
        except (CsvFormatError,InvalidOperation,UnicodeDecodeError,ValueError):
            log.warning("invalid reconciliation request from %s",self.client_address[0]); return self._send(400,error_page("Input validation failed; review the CSV format and import profile."))
        except Exception:
            log.exception("reconciliation failed"); return self._send(500,error_page("Unexpected local processing error"))
        self._send(200,result_page(result,firm,evidence_text,profile_text))
    def log_message(self,fmt,*args): log.info("%s %s",self.client_address[0],fmt%args)

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8080);p.add_argument("--host",default="127.0.0.1");p.add_argument("--unsafe-bind",action="store_true");args=p.parse_args(argv)
    if args.host not in {"127.0.0.1","localhost","::1"} and not args.unsafe_bind: raise SystemExit("Refusing non-loopback bind without --unsafe-bind")
    logging.basicConfig(level=logging.INFO); srv=ThreadingHTTPServer((args.host,args.port),Handler); srv.daemon_threads=True
    try:srv.serve_forever()
    except KeyboardInterrupt:pass
    finally:srv.shutdown();srv.server_close()
if __name__=="__main__":main()
