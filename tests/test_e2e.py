import csv, json, subprocess, sys, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from app.evidence import validate_bundle
ROOT=Path(__file__).resolve().parents[1]

class TestE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls): subprocess.run([sys.executable,str(ROOT/"demo_data"/"generate_demo.py")],check=True,cwd=ROOT)
    def run_cli(self,out):
        return subprocess.run([sys.executable,"-m","app.cli","--bank","demo_data/bank_statement.csv","--invoices","demo_data/invoices.csv","--out",str(out)],cwd=ROOT,capture_output=True,text=True)
    def test_cli_and_evidence(self):
        out=ROOT/"out_test"; r=self.run_cli(out); self.assertEqual(r.returncode,0,r.stderr)
        expected=["matches.csv","exceptions.csv","unpaid_invoices.csv","payments_import.csv","report.html","profile.json","evidence.json","evidence.sha256"]
        for name in expected:self.assertTrue((out/name).exists(),name)
        bundle=json.loads((out/"evidence.json").read_text()); self.assertEqual(validate_bundle(bundle),[])
        self.assertGreater(bundle["summary"]["deposits_processed"],200)
        self.assertIn("Reconciliation evidence report",(out/"report.html").read_text())
    def test_cli_evidence_is_deterministic(self):
        a=ROOT/"out_det_a"; b=ROOT/"out_det_b"
        self.assertEqual(self.run_cli(a).returncode,0); self.assertEqual(self.run_cli(b).returncode,0)
        self.assertEqual((a/"evidence.json").read_bytes(),(b/"evidence.json").read_bytes())
    def test_server_security_and_shutdown(self):
        from app.server import Handler
        Handler._hits.clear(); srv=ThreadingHTTPServer(("127.0.0.1",0),Handler); srv.daemon_threads=True
        port=srv.server_address[1]; thread=threading.Thread(target=srv.serve_forever); thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/",timeout=10) as resp:
                self.assertEqual(resp.headers["Cache-Control"],"no-store")
                self.assertIn("default-src 'none'",resp.headers["Content-Security-Policy"])
            req=urllib.request.Request(f"http://127.0.0.1:{port}/",headers={"Host":"evil.example"})
            with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(req,timeout=10)
            self.assertEqual(ctx.exception.code,403)
            bank=(ROOT/"demo_data"/"bank_statement.csv").read_bytes(); invs=(ROOT/"demo_data"/"invoices.csv").read_bytes(); boundary="----lmtest"
            def part(name,filename,content):
                h=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'+(f'; filename="{filename}"' if filename else '')+'\r\nContent-Type: text/csv\r\n\r\n'
                return h.encode()+content+b"\r\n"
            body=part("bank","b.csv",bank)+part("invoices","i.csv",invs)+part("currency",None,b"USD")+part("date_format",None,b"YMD")+f"--{boundary}--\r\n".encode()
            req=urllib.request.Request(f"http://127.0.0.1:{port}/reconcile",data=body,headers={"Content-Type":f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req,timeout=120) as resp:
                page=resp.read().decode(); self.assertIn("Reconciliation evidence report",page)
                for download in ["unpaid_invoices.csv","profile.json","evidence.json","evidence.sha256"]: self.assertIn(download,page)
        finally:
            srv.shutdown(); srv.server_close(); thread.join(10)
        self.assertFalse(thread.is_alive())

if __name__=="__main__": unittest.main()
