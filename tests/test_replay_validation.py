import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class TestReplayValidation(unittest.TestCase):
    def command(self,out,*extra):
        return [sys.executable,"-m","app.cli","--bank","demo_data/bank_statement.csv","--invoices","demo_data/invoices.csv","--out",str(out),*extra]
    def test_profile_replays_identical_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/"a"; b=Path(td)/"b"
            one=subprocess.run(self.command(a,"--currency","USD","--date-format","YMD","--precision","2","--fee-tolerance","0"),cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(one.returncode,0,one.stderr)
            two=subprocess.run(self.command(b,"--profile",str(a/"profile.json")),cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(two.returncode,0,two.stderr)
            self.assertEqual((a/"evidence.json").read_bytes(),(b/"evidence.json").read_bytes())
    def test_validator_checks_bundle_and_file_checksum(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"out"; subprocess.run(self.command(out),cwd=ROOT,check=True,capture_output=True)
            valid=subprocess.run([sys.executable,"-m","app.validate",str(out/"evidence.json"),"--checksum",str(out/"evidence.sha256")],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(valid.returncode,0,valid.stderr); self.assertIn("VALID run_id=",valid.stdout)
            bundle=json.loads((out/"evidence.json").read_text()); bundle["currency"]="EUR"; (out/"tampered.json").write_text(json.dumps(bundle))
            invalid=subprocess.run([sys.executable,"-m","app.validate",str(out/"tampered.json")],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(invalid.returncode,0); self.assertIn("bundle_sha256 mismatch",invalid.stderr)
    def test_profile_rejects_unknown_fields(self):
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td)/"bad.json"; bad.write_text('{"currency":"USD","silent_accept":true}')
            run=subprocess.run(self.command(Path(td)/"out","--profile",str(bad)),cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(run.returncode,2); self.assertIn("unknown profile fields",run.stderr)

if __name__=="__main__": unittest.main()
