import copy, json, subprocess, sys, tempfile, unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from app.csvio import ImportProfile
from app.evidence import build_bundle, bundle_json
from app.matcher import BankTxn, Invoice, reconcile
from app.review import build_review_events, parse_review_text, review_text, verify_review_events
ROOT=Path(__file__).resolve().parents[1]

class TestReviewLedger(unittest.TestCase):
    def bundle(self,two=False):
        invoices=[Invoice("i1","INV-1","Acme",date(2026,1,1),Decimal("10.00")),Invoice("i2","INV-2","Acme",date(2026,1,1),Decimal("10.00"))]
        txns=[BankTxn("t1",date(2026,1,2),"Acme payment",Decimal("10.00"))]
        if two:
            invoices += [Invoice("i3","INV-3","Beta",date(2026,1,1),Decimal("20.00")),Invoice("i4","INV-4","Beta",date(2026,1,1),Decimal("20.00"))]
            txns += [BankTxn("t2",date(2026,1,2),"Beta payment",Decimal("20.00"))]
        result=reconcile(txns,invoices,currency="USD")
        return build_bundle(result,input_hashes={"bank_csv":"a"*64,"invoice_csv":"b"*64},import_profile=ImportProfile().to_dict())
    def document(self,two=False):
        decisions=[{"txn_id":"t1","decision":"approve_exact","invoice_ids":["i1"],"reason_code":"REMITTANCE_CONFIRMED","note":"Synthetic review"}]
        if two: decisions.append({"txn_id":"t2","decision":"defer","invoice_ids":[],"reason_code":"NEEDS_DOCUMENT","note":""})
        return {"reviewer":"Reviewer 01","recorded_at":"2026-07-24T00:00:00Z","decisions":decisions}
    def test_deterministic_valid_chain(self):
        bundle=self.bundle(True); a=build_review_events(bundle,self.document(True)); b=build_review_events(bundle,self.document(True))
        self.assertEqual(a,b); self.assertEqual(verify_review_events(a,bundle),[])
        self.assertEqual(parse_review_text(review_text(a)),a)
    def test_edit_reorder_and_delete_are_detected(self):
        bundle=self.bundle(True); events=build_review_events(bundle,self.document(True))
        edited=copy.deepcopy(events); edited[0]["note"]="changed"; self.assertTrue(verify_review_events(edited,bundle))
        reordered=list(reversed(events)); self.assertTrue(verify_review_events(reordered,bundle))
        self.assertTrue(verify_review_events(events[1:],bundle)); self.assertTrue(verify_review_events([],bundle))
    def test_nonconserving_or_duplicate_allocations_rejected(self):
        bundle=self.bundle(True); bad=self.document(True); bad["decisions"][0]["invoice_ids"]=["i3"]
        with self.assertRaisesRegex(ValueError,"conserve"): build_review_events(bundle,bad)
        duplicate=self.document(True); duplicate["decisions"][1]={"txn_id":"t2","decision":"approve_exact","invoice_ids":["i1"],"reason_code":"MANUAL","note":""}
        with self.assertRaisesRegex(ValueError,"already used"): build_review_events(bundle,duplicate)
    def test_reject_cannot_allocate_invoice(self):
        bundle=self.bundle(); doc=self.document(); doc["decisions"][0]["decision"]="reject"
        with self.assertRaisesRegex(ValueError,"must not allocate"): build_review_events(bundle,doc)
    def test_cli_create_verify_and_receipt_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); evidence=td/"evidence.json"; decisions=td/"decisions.json"; review=td/"review.ndjson"
            evidence.write_text(bundle_json(self.bundle())); decisions.write_text(json.dumps(self.document()))
            create=subprocess.run([sys.executable,"-m","app.review","create","--evidence",str(evidence),"--decisions",str(decisions),"--out",str(review)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(create.returncode,0,create.stderr); receipt=review.with_suffix(".ndjson.receipt.json")
            verify=subprocess.run([sys.executable,"-m","app.review","verify","--evidence",str(evidence),"--review",str(review),"--receipt",str(receipt)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(verify.returncode,0,verify.stderr); self.assertIn("VALID events=1",verify.stdout)
            review.write_text(review.read_text().replace("Synthetic review","Altered review"))
            invalid=subprocess.run([sys.executable,"-m","app.review","verify","--evidence",str(evidence),"--review",str(review),"--receipt",str(receipt)],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(invalid.returncode,0)

if __name__=="__main__": unittest.main()
