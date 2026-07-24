import copy, hashlib, json, unittest
from datetime import date
from decimal import Decimal
from app.csvio import CsvFormatError, ImportProfile, parse_amount_str, parse_bank_csv, parse_date_str, parse_invoice_csv
from app.evidence import build_bundle, bundle_json, validate_bundle
from app.matcher import BankTxn, Invoice, reconcile
from app.report import exceptions_csv, html_report, safe_cell

class TestCsvAndEvidence(unittest.TestCase):
    def test_profile_date_is_strict(self):
        self.assertEqual(parse_date_str("31/01/2026","DMY"),date(2026,1,31))
        with self.assertRaises(CsvFormatError): parse_date_str("31/01/2026","MDY")
    def test_ambiguous_date_requires_profile(self):
        self.assertEqual(parse_date_str("01/02/2026","DMY"),date(2026,2,1))
        self.assertEqual(parse_date_str("01/02/2026","MDY"),date(2026,1,2))
    def test_precision_rejected(self):
        with self.assertRaises(CsvFormatError): parse_amount_str("1.001",2)
    def test_malformed_amount_rejected(self):
        for value in ["NaN","Infinity","1-2","1.234,56"]:
            with self.subTest(value=value), self.assertRaises(CsvFormatError): parse_amount_str(value)
    def test_source_ids_are_content_stable(self):
        text="date,description,amount\n2026-01-01,ACME,10.00\n"
        a=parse_bank_csv(text); b=parse_bank_csv(text)
        self.assertEqual(a[0].id,b[0].id); self.assertTrue(a[0].id.startswith("B-"))
    def test_duplicate_invoice_numbers_rejected_by_reconcile(self):
        text="invoice no,customer,date,amount\nINV-1,A,2026-01-01,1.00\nINV1,A,2026-01-02,2.00\n"
        with self.assertRaises(ValueError): reconcile([],parse_invoice_csv(text))
    def test_formula_cells_neutralized(self):
        for value in ["=1+1","+cmd","-cmd","@sum","\tbad","\nbad"]:
            self.assertTrue(safe_cell(value).startswith("'"))
    def _bundle(self):
        txn=BankTxn("t",date(2026,1,2),"PAY INV1",Decimal("10.00"))
        inv=Invoice("i","INV-1","Acme",date(2026,1,1),Decimal("10.00"))
        result=reconcile([txn],[inv])
        return build_bundle(result,input_hashes={"bank_csv":"a"*64,"invoice_csv":"b"*64},import_profile=ImportProfile().to_dict())
    def test_bundle_validates(self): self.assertEqual(validate_bundle(self._bundle()),[])
    def test_bundle_tamper_detected(self):
        bundle=self._bundle(); bundle["matches"][0]["txn"]["amount"]="11.00"
        errors=validate_bundle(bundle)
        self.assertIn("bundle_sha256 mismatch",errors)
        self.assertTrue(any("residual mismatch" in e for e in errors))
    def test_bundle_is_byte_deterministic(self):
        self.assertEqual(bundle_json(self._bundle()),bundle_json(self._bundle()))
    def test_html_escapes_input(self):
        txn=BankTxn("t",date(2026,1,2),"<script>alert(1)</script>",Decimal("1.00"))
        result=reconcile([txn],[])
        page=html_report(result,"<img src=x onerror=1>")
        self.assertNotIn("<script>",page); self.assertNotIn("<img src=x",page)

if __name__=="__main__": unittest.main()
