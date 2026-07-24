import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from app.matcher import BankTxn, Invoice, reconcile, subset_candidates, subset_sum

D=date(2026,1,1)
def inv(i,no,cust,amt,currency="USD",status="open",d=D): return Invoice(i,no,cust,d,Decimal(amt),status,currency)
def txn(i,desc,amt,currency="USD",d=date(2026,1,20)): return BankTxn(i,d,desc,Decimal(amt),currency)

class TestMatcher(unittest.TestCase):
    def test_reference_match(self):
        r=reconcile([txn("t","PAY INV1001","12.00")],[inv("i","INV-1001","Acme","12.00")])
        self.assertEqual(r.matches[0].evidence_class,"DIRECT_REFERENCE")
        self.assertEqual(r.matches[0].solver_status,"exact_unique")
    def test_unique_customer_subset(self):
        invoices=[inv("1","A1","Acme","10.00"),inv("2","A2","Acme","20.00"),inv("3","A3","Acme","9.00")]
        r=reconcile([txn("t","ACME BULK","30.00")],invoices)
        self.assertEqual(r.matches[0].match_type,"lump-sum")
        self.assertEqual({i.invoice_no for i in r.matches[0].invoices},{"A1","A2"})
    def test_equal_customer_amount_is_ambiguous(self):
        invoices=[inv("1","A1","Acme","10.00"),inv("2","A2","Acme","10.00")]
        r=reconcile([txn("t","ACME","10.00")],invoices)
        self.assertFalse(r.matches); self.assertEqual(r.unmatched[0].reason,"AMBIGUOUS_AMOUNT")
        self.assertEqual(len(r.unmatched[0].alternatives),2)
    def test_multiple_subsets_are_ambiguous(self):
        invoices=[inv("1","A1","Acme","10.00"),inv("2","A2","Acme","20.00"),inv("3","A3","Acme","12.00"),inv("4","A4","Acme","18.00")]
        r=reconcile([txn("t","ACME BULK","30.00")],invoices)
        self.assertFalse(r.matches); self.assertEqual(r.unmatched[0].reason,"AMBIGUOUS_COMBINATION")
        self.assertGreaterEqual(len(r.unmatched[0].alternatives),2)
    def test_tolerance_never_auto_accepts_residual(self):
        r=reconcile([txn("t","PAY INV1 LESS FEE","9.50")],[inv("1","INV-1","Acme","10.00")],Decimal("1.00"))
        self.assertFalse(r.matches); self.assertIn(r.unmatched[0].reason,{"PARTIAL_PAYMENT","RESIDUAL_REVIEW"})
    def test_amount_only_unique(self):
        r=reconcile([txn("t","COUNTER DEPOSIT","10.00")],[inv("1","A1","Acme","10.00")])
        self.assertEqual(r.matches[0].evidence_class,"AMOUNT_ONLY")
    def test_global_ambiguous_amount(self):
        invoices=[inv("1","A1","Acme","10.00"),inv("2","B1","Beta","10.00")]
        r=reconcile([txn("t","COUNTER DEPOSIT","10.00")],invoices)
        self.assertEqual(r.unmatched[0].reason,"AMBIGUOUS_AMOUNT")
    def test_partial_payment_flagged(self):
        r=reconcile([txn("t","ACME INV1","5.00")],[inv("1","INV-1","Acme","10.00")])
        self.assertEqual(r.unmatched[0].reason,"PARTIAL_PAYMENT")
    def test_no_candidate(self):
        r=reconcile([txn("t","BANK INTEREST","5.00")],[inv("1","A1","Acme","10.00")])
        self.assertEqual(r.unmatched[0].reason,"NO_CANDIDATE")
    def test_withdrawal_partition(self):
        r=reconcile([txn("t","FEE","-5.00")],[inv("1","A1","Acme","10.00")])
        self.assertEqual(r.deposits_processed,0); self.assertEqual(r.skipped_non_deposits,1)
    def test_paid_invoice_excluded(self):
        r=reconcile([txn("t","PAY INV1","10.00")],[inv("1","INV-1","Acme","10.00",status="paid")])
        self.assertFalse(r.matches)
    def test_invoice_not_reused(self):
        invoices=[inv("1","INV-1","Acme","10.00")]
        r=reconcile([txn("t1","PAY INV1","10.00"),txn("t2","ACME","10.00",d=date(2026,1,21))],invoices)
        self.assertEqual(len(r.matches),1); self.assertEqual(len(r.unmatched),1)
    def test_duplicate_invoice_number_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate invoice numbers"):
            reconcile([], [inv("1","INV-1","A","1.00"),inv("2","INV1","A","2.00")])
    def test_mixed_currency_rejected(self):
        with self.assertRaisesRegex(ValueError,"mixed currencies"):
            reconcile([txn("t","x","1.00","EUR")],[inv("1","I1","A","1.00","USD")])
    def test_subset_candidates_detect_ambiguity(self):
        invoices=[inv("1","A","X","10.00"),inv("2","B","X","20.00"),inv("3","C","X","12.00"),inv("4","D","X","18.00")]
        candidates,status=subset_candidates(invoices,3000)
        self.assertEqual(status,"exact_ambiguous"); self.assertGreaterEqual(len(candidates),2)
    def test_subset_limit_is_explicit(self):
        candidates,status=subset_candidates([inv(str(i),f"I{i}","X","1.00") for i in range(31)],200)
        self.assertEqual(candidates,[]); self.assertEqual(status,"limit_exceeded")
    def test_excess_precision_rejected_by_matcher(self):
        with self.assertRaisesRegex(ValueError,"more than two"):
            subset_sum([inv("1","I1","X","1.001")],100)
    def test_deterministic_under_invoice_reordering(self):
        invoices=[inv("1","A1","Acme","10.00"),inv("2","A2","Acme","20.00"),inv("3","A3","Acme","9.00")]
        a=reconcile([txn("t","ACME BULK","30.00")],invoices)
        b=reconcile([txn("t","ACME BULK","30.00")],list(reversed(invoices)))
        self.assertEqual([i.id for i in a.matches[0].invoices],[i.id for i in b.matches[0].invoices])

if __name__=="__main__": unittest.main()
