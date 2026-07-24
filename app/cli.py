"""LedgerMatch CLI."""
from __future__ import annotations
import argparse, hashlib, json, sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from . import report as report_mod
from .csvio import CsvFormatError, ImportProfile, parse_bank_csv, parse_invoice_csv
from .evidence import build_bundle, bundle_json, validate_bundle
from .matcher import reconcile

PROFILE_KEYS={"currency","date_format","precision","fee_tolerance"}
def _sha(text): return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _read_profile(path):
    if not path: return {}
    try: value=json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc: raise CsvFormatError(f"invalid profile JSON: {exc.msg}") from exc
    if not isinstance(value,dict): raise CsvFormatError("profile must be a JSON object")
    unknown=set(value)-PROFILE_KEYS
    if unknown: raise CsvFormatError("unknown profile fields: "+", ".join(sorted(unknown)))
    return value

def main(argv=None):
    p=argparse.ArgumentParser(prog="ledgermatch",description="Local, review-first deposit-to-invoice reconciliation")
    p.add_argument("--bank",required=True); p.add_argument("--invoices",required=True); p.add_argument("--out",required=True)
    p.add_argument("--profile",help="JSON import profile emitted by an earlier run")
    p.add_argument("--currency"); p.add_argument("--date-format",choices=["YMD","DMY","MDY"])
    p.add_argument("--precision",type=int,choices=[0,2]); p.add_argument("--fee-tolerance")
    p.add_argument("--firm",default=""); p.add_argument("--ai",action="store_true",help="Explicit opt-in advisory; never authoritative")
    args=p.parse_args(argv)
    try:
        saved=_read_profile(args.profile)
        currency=(args.currency or saved.get("currency") or "USD").upper()
        date_format=args.date_format or saved.get("date_format") or "YMD"
        precision=args.precision if args.precision is not None else saved.get("precision",2)
        fee=Decimal(args.fee_tolerance if args.fee_tolerance is not None else saved.get("fee_tolerance","0"))
        if fee<0: raise CsvFormatError("fee tolerance must be non-negative")
        profile=ImportProfile(currency,date_format,precision)
        bank_text=Path(args.bank).read_text(encoding="utf-8-sig")
        invoice_text=Path(args.invoices).read_text(encoding="utf-8-sig")
        txns=parse_bank_csv(bank_text,profile); invs=parse_invoice_csv(invoice_text,profile)
        result=reconcile(txns,invs,fee,currency=profile.currency)
    except (InvalidOperation,FileNotFoundError,OSError,CsvFormatError,ValueError,TypeError) as exc:
        print(f"error: {exc}",file=sys.stderr); return 2
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    profile_record={**profile.to_dict(),"fee_tolerance":str(fee)}
    artifacts={"matches.csv":report_mod.matches_csv(result),"exceptions.csv":report_mod.exceptions_csv(result),"unpaid_invoices.csv":report_mod.unpaid_csv(result),"payments_import.csv":report_mod.payments_import_csv(result),"report.html":report_mod.html_report(result,args.firm),"profile.json":json.dumps(profile_record,sort_keys=True,indent=2)+"\n"}
    for name,text in artifacts.items(): (out/name).write_text(text,encoding="utf-8")
    bundle=build_bundle(result,input_hashes={"bank_csv":_sha(bank_text),"invoice_csv":_sha(invoice_text)},import_profile=profile.to_dict(),config={"fee_tolerance":str(fee)})
    errors=validate_bundle(bundle)
    if errors:
        print("error: evidence validation failed: "+"; ".join(errors),file=sys.stderr); return 3
    evidence_text=bundle_json(bundle); (out/"evidence.json").write_text(evidence_text,encoding="utf-8")
    (out/"evidence.sha256").write_text(hashlib.sha256(evidence_text.encode()).hexdigest()+"  evidence.json\n",encoding="utf-8")
    if args.ai:
        from . import llm_assist
        if not llm_assist.enabled(): print("AI advisory skipped: LLM_API_KEY is not configured.")
        else:
            suggestions=[llm_assist.suggest(u.txn,result.unpaid_invoices) for u in result.unmatched]
            (out/"ai_suggestions.json").write_text(json.dumps(suggestions,indent=2),encoding="utf-8")
    print(f"Deposits processed: {result.deposits_processed}")
    print(f"Uniquely supported: {len(result.matches)}")
    print(f"Need human review: {len(result.unmatched)}")
    print(f"Evidence bundle: {out/'evidence.json'}")
    return 0
if __name__=="__main__": sys.exit(main())
