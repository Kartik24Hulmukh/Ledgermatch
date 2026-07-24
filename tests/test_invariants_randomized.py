import random, unittest
from datetime import date, timedelta
from decimal import Decimal
from app.matcher import BankTxn, Invoice, reconcile

class TestRandomizedInvariants(unittest.TestCase):
    def test_seeded_reference_runs_preserve_conservation_and_exclusivity(self):
        rng=random.Random(20260723)
        for case in range(80):
            base=date(2026,1,1)+timedelta(days=case%90); invoices=[]; txns=[]
            for idx in range(rng.randint(4,18)):
                amount=Decimal(rng.randint(100,500000))/100; ref=f"R{case:03d}-{idx:03d}"
                inv=Invoice(f"i-{ref}",ref,f"Customer {idx}",base,amount,"open","USD"); invoices.append(inv)
                txns.append(BankTxn(f"t-{ref}",base+timedelta(days=1),f"Transfer {ref}",amount,"USD"))
            rng.shuffle(invoices); rng.shuffle(txns); result=reconcile(txns,invoices,currency="USD")
            self.assertEqual(len(result.matches),len(txns)); self.assertEqual(len(result.unmatched),0)
            used=[]
            for match in result.matches:
                self.assertEqual(match.solver_status,"exact_unique")
                self.assertEqual(sum((i.amount for i in match.invoices),Decimal("0")),match.txn.amount)
                self.assertEqual(match.residual,Decimal("0")); used.extend(i.id for i in match.invoices)
            self.assertEqual(len(used),len(set(used)))
    def test_seeded_equal_amount_collisions_never_auto_accept(self):
        rng=random.Random(8841); base=date(2026,3,1)
        for case in range(80):
            amount=Decimal(rng.randint(100,100000))/100; customer=f"Collision {case}"
            invoices=[Invoice(f"a{case}",f"A-{case}",customer,base,amount,"open","USD"),Invoice(f"b{case}",f"B-{case}",customer,base,amount,"open","USD")]
            txn=BankTxn(f"t{case}",base+timedelta(days=1),customer,amount,"USD")
            result=reconcile([txn],invoices,currency="USD")
            self.assertEqual(len(result.matches),0); self.assertEqual(len(result.unmatched),1)
            self.assertIn(result.unmatched[0].solver_status,{"exact_ambiguous","unresolved"})

if __name__=="__main__": unittest.main()
