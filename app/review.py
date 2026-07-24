"""Deterministic, tamper-evident human review ledger for reconciliation exceptions."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .evidence import canonical_json, validate_bundle

SCHEMA_VERSION="1.0"
DECISIONS={"approve_exact","reject","defer"}
REASON=re.compile(r"^[A-Z0-9_]{2,50}$")
EVENT_FIELDS={"schema_version","sequence","previous_hash","run_id","reviewer","recorded_at","txn_id","decision","invoice_ids","reason_code","note","event_hash"}

def sha256_bytes(value:bytes)->str: return hashlib.sha256(value).hexdigest()
def _event_hash(event):
    unsigned=dict(event); unsigned.pop("event_hash",None)
    return sha256_bytes(canonical_json(unsigned).encode("utf-8"))
def _timestamp(value):
    if not isinstance(value,str): raise ValueError("recorded_at must be an ISO-8601 timestamp")
    try: parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc: raise ValueError("recorded_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None: raise ValueError("recorded_at must include a timezone")
    return value

def _validate_decisions(bundle,document):
    if validate_bundle(bundle): raise ValueError("evidence bundle must validate before review")
    reviewer=document.get("reviewer")
    if not isinstance(reviewer,str) or not reviewer.strip() or len(reviewer)>120: raise ValueError("reviewer must be 1-120 characters")
    recorded_at=_timestamp(document.get("recorded_at")); decisions=document.get("decisions")
    if not isinstance(decisions,list) or not decisions: raise ValueError("decisions must be a non-empty array")
    if len(decisions)>10000: raise ValueError("too many review decisions")
    exceptions={item["txn"]["id"]:item for item in bundle["exceptions"]}
    unpaid={item["id"]:item for item in bundle["unpaid_invoices"]}
    already_used={inv["id"] for match in bundle["matches"] for inv in match["invoices"]}
    claimed=set(); seen_txns=set(); normalized=[]
    for raw in decisions:
        if not isinstance(raw,dict): raise ValueError("each decision must be an object")
        allowed={"txn_id","decision","invoice_ids","reason_code","note"}
        unknown=set(raw)-allowed
        if unknown: raise ValueError("unknown decision fields: "+", ".join(sorted(unknown)))
        txn_id=raw.get("txn_id"); decision=raw.get("decision"); invoice_ids=raw.get("invoice_ids",[])
        reason=raw.get("reason_code"); note=raw.get("note","")
        if txn_id not in exceptions: raise ValueError(f"transaction is not an exception: {txn_id}")
        if txn_id in seen_txns: raise ValueError(f"duplicate transaction decision: {txn_id}")
        seen_txns.add(txn_id)
        if decision not in DECISIONS: raise ValueError(f"invalid review decision for {txn_id}")
        if not isinstance(reason,str) or not REASON.fullmatch(reason): raise ValueError(f"invalid reason_code for {txn_id}")
        if not isinstance(note,str) or len(note)>500: raise ValueError(f"note too long or invalid for {txn_id}")
        if not isinstance(invoice_ids,list) or any(not isinstance(i,str) for i in invoice_ids): raise ValueError(f"invoice_ids must be strings for {txn_id}")
        if len(invoice_ids)!=len(set(invoice_ids)): raise ValueError(f"duplicate invoice ID for {txn_id}")
        if decision=="approve_exact":
            if not invoice_ids: raise ValueError(f"approve_exact requires invoice IDs for {txn_id}")
            selected=[]
            for iid in invoice_ids:
                if iid not in unpaid: raise ValueError(f"invoice is not unpaid evidence: {iid}")
                if iid in already_used or iid in claimed: raise ValueError(f"invoice already used in review: {iid}")
                selected.append(unpaid[iid])
            txn=exceptions[txn_id]["txn"]
            if any(inv["currency"]!=txn["currency"] for inv in selected): raise ValueError(f"currency mismatch for {txn_id}")
            try: total=sum((Decimal(inv["amount"]) for inv in selected),Decimal("0")); amount=Decimal(txn["amount"])
            except InvalidOperation as exc: raise ValueError(f"invalid amount for {txn_id}") from exc
            if total!=amount: raise ValueError(f"approve_exact does not conserve amount for {txn_id}")
            claimed.update(invoice_ids)
        elif invoice_ids:
            raise ValueError(f"{decision} must not allocate invoices for {txn_id}")
        normalized.append({"txn_id":txn_id,"decision":decision,"invoice_ids":invoice_ids,"reason_code":reason,"note":note})
    return reviewer.strip(),recorded_at,normalized

def build_review_events(bundle,document):
    reviewer,recorded_at,decisions=_validate_decisions(bundle,document); events=[]; previous="0"*64
    for sequence,decision in enumerate(decisions,1):
        event={"schema_version":SCHEMA_VERSION,"sequence":sequence,"previous_hash":previous,"run_id":bundle["run_id"],"reviewer":reviewer,"recorded_at":recorded_at,**decision}
        event["event_hash"]=_event_hash(event); events.append(event); previous=event["event_hash"]
    return events

def review_text(events): return "".join(json.dumps(event,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n" for event in events)
def parse_review_text(text):
    events=[]
    for line_no,line in enumerate(text.splitlines(),1):
        if not line.strip(): continue
        try: value=json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f"invalid review JSON on line {line_no}") from exc
        events.append(value)
    return events

def verify_review_events(events,bundle):
    errors=[]
    if not isinstance(events,list) or not events: return ["review ledger is empty"]
    previous="0"*64; decisions=[]; reviewer=None; recorded_at=None
    for expected,event in enumerate(events,1):
        if not isinstance(event,dict): errors.append(f"event {expected} is not an object"); continue
        if set(event)!=EVENT_FIELDS: errors.append(f"event {expected} fields are invalid")
        if event.get("schema_version")!=SCHEMA_VERSION: errors.append(f"event {expected} schema is unsupported")
        if event.get("sequence")!=expected: errors.append(f"event {expected} sequence mismatch")
        if event.get("previous_hash")!=previous: errors.append(f"event {expected} predecessor mismatch")
        if event.get("run_id")!=bundle.get("run_id"): errors.append(f"event {expected} run_id mismatch")
        if event.get("event_hash")!=_event_hash(event): errors.append(f"event {expected} hash mismatch")
        previous=event.get("event_hash","")
        reviewer=reviewer or event.get("reviewer"); recorded_at=recorded_at or event.get("recorded_at")
        if event.get("reviewer")!=reviewer or event.get("recorded_at")!=recorded_at: errors.append(f"event {expected} batch identity mismatch")
        decisions.append({k:event.get(k) for k in ["txn_id","decision","invoice_ids","reason_code","note"]})
    if not errors:
        try:
            rebuilt=build_review_events(bundle,{"reviewer":reviewer,"recorded_at":recorded_at,"decisions":decisions})
            if rebuilt!=events: errors.append("review ledger semantic reconstruction mismatch")
        except ValueError as exc: errors.append(str(exc))
    return errors

def build_receipt(evidence_path,review_path,events):
    review_bytes=review_path.read_bytes()
    return {"schema_version":"1.0","evidence_sha256":sha256_bytes(evidence_path.read_bytes()),"run_id":events[0]["run_id"],"event_count":len(events),"chain_head":events[-1]["event_hash"],"review_sha256":sha256_bytes(review_bytes)}
def verify_receipt(receipt,evidence_path,review_path,events):
    expected=build_receipt(evidence_path,review_path,events)
    return [] if receipt==expected else ["review receipt mismatch"]

def main(argv=None):
    parser=argparse.ArgumentParser(prog="ledgermatch-review"); sub=parser.add_subparsers(dest="command",required=True)
    create=sub.add_parser("create"); create.add_argument("--evidence",type=Path,required=True); create.add_argument("--decisions",type=Path,required=True); create.add_argument("--out",type=Path,required=True)
    verify=sub.add_parser("verify"); verify.add_argument("--evidence",type=Path,required=True); verify.add_argument("--review",type=Path,required=True); verify.add_argument("--receipt",type=Path)
    args=parser.parse_args(argv)
    try:
        evidence=json.loads(args.evidence.read_text(encoding="utf-8"))
        if args.command=="create":
            decisions=json.loads(args.decisions.read_text(encoding="utf-8")); events=build_review_events(evidence,decisions)
            args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(review_text(events),encoding="utf-8")
            receipt_path=args.out.with_suffix(args.out.suffix+".receipt.json"); receipt=build_receipt(args.evidence,args.out,events)
            receipt_path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n",encoding="utf-8")
            print(f"CREATED events={len(events)} chain_head={events[-1]['event_hash']} receipt={receipt_path}"); return 0
        events=parse_review_text(args.review.read_text(encoding="utf-8")); errors=verify_review_events(events,evidence)
        if args.receipt:
            receipt=json.loads(args.receipt.read_text(encoding="utf-8")); errors.extend(verify_receipt(receipt,args.evidence,args.review,events))
        if errors:
            for error in errors: print("INVALID: "+error,file=sys.stderr)
            return 3
        print(f"VALID events={len(events)} chain_head={events[-1]['event_hash']}"); return 0
    except (OSError,json.JSONDecodeError,ValueError) as exc:
        print(f"INVALID: {exc}",file=sys.stderr); return 2
if __name__=="__main__": sys.exit(main())
