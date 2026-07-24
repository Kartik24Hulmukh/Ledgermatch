"""Deterministic Reconciliation Evidence Bundle generation and validation."""
from __future__ import annotations
import hashlib, json, re
from decimal import Decimal, InvalidOperation

SCHEMA_VERSION="1.1"
ENGINE_VERSION="0.4.0"
TOP_LEVEL={"schema_version","engine_version","currency","input_hashes","import_profile","config","matches","exceptions","unpaid_invoices","summary","replay","run_id","bundle_sha256"}
HEX64=re.compile(r"^[a-f0-9]{64}$")

def canonical_json(value)->str:
    """Stable internal JSON encoding. This is not claimed as RFC 8785."""
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def sha256_text(text:str)->str: return hashlib.sha256(text.encode("utf-8")).hexdigest()
def _invoice(inv): return {"id":inv.id,"invoice_no":inv.invoice_no,"customer":inv.customer,"date":inv.date.isoformat(),"amount":str(inv.amount),"currency":inv.currency}
def _txn(txn): return {"id":txn.id,"date":txn.date.isoformat(),"description":txn.description,"amount":str(txn.amount),"currency":txn.currency}

def build_bundle(result,*,input_hashes:dict[str,str],import_profile:dict,config:dict|None=None)->dict:
    config=config or {}; matches=[]
    for m in result.matches:
        matches.append({"txn":_txn(m.txn),"invoices":[_invoice(i) for i in m.invoices],"match_type":m.match_type,"evidence_class":m.evidence_class,"solver_status":m.solver_status,"residual":str(m.residual),"alternatives":m.alternatives,"explanation":m.explanation,"decision":"accepted_by_rule"})
    exceptions=[{"txn":_txn(u.txn),"reason":u.reason,"guidance":u.suggestions,"solver_status":u.solver_status,"alternatives":u.alternatives,"decision":"pending_human_review"} for u in result.unmatched]
    body={"schema_version":SCHEMA_VERSION,"engine_version":ENGINE_VERSION,"currency":result.currency,"input_hashes":dict(sorted(input_hashes.items())),"import_profile":import_profile,"config":config,"matches":matches,"exceptions":exceptions,"unpaid_invoices":[_invoice(i) for i in result.unpaid_invoices],"summary":{"deposits_processed":result.deposits_processed,"accepted_matches":len(matches),"exceptions":len(exceptions),"matched_invoice_count":result.matched_invoice_count,"skipped_non_deposits":result.skipped_non_deposits},"replay":"python3 -m app.cli --profile profile.json --bank BANK.csv --invoices INVOICES.csv --out OUT"}
    material={"input_hashes":body["input_hashes"],"import_profile":import_profile,"config":config,"engine_version":ENGINE_VERSION}
    body["run_id"]=sha256_text(canonical_json(material)); body["bundle_sha256"]=sha256_text(canonical_json(body)); return body

def bundle_json(bundle:dict)->str: return json.dumps(bundle,sort_keys=True,indent=2,ensure_ascii=False)+"\n"

def _decimal(value,label,errors):
    try: return Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError): errors.append(f"invalid decimal for {label}"); return Decimal("0")

def validate_bundle(bundle:dict)->list[str]:
    errors=[]
    if not isinstance(bundle,dict): return ["bundle must be an object"]
    missing=TOP_LEVEL-set(bundle); unknown=set(bundle)-TOP_LEVEL
    if missing: errors.append("missing top-level fields: "+", ".join(sorted(missing)))
    if unknown: errors.append("unknown top-level fields: "+", ".join(sorted(unknown)))
    if bundle.get("schema_version")!=SCHEMA_VERSION: errors.append("unsupported schema_version")
    if bundle.get("engine_version")!=ENGINE_VERSION: errors.append("unsupported engine_version")
    currency=bundle.get("currency")
    if not isinstance(currency,str) or len(currency)!=3 or not currency.isalpha() or currency!=currency.upper(): errors.append("invalid bundle currency")
    hashes=bundle.get("input_hashes",{})
    if not isinstance(hashes,dict) or not {"bank_csv","invoice_csv"}.issubset(hashes): errors.append("missing input hashes")
    elif any(not isinstance(value,str) or not HEX64.fullmatch(value) for value in hashes.values()): errors.append("invalid input hash")
    supplied=bundle.get("bundle_sha256"); unsigned=dict(bundle); unsigned.pop("bundle_sha256",None)
    if supplied!=sha256_text(canonical_json(unsigned)): errors.append("bundle_sha256 mismatch")
    material={"input_hashes":hashes,"import_profile":bundle.get("import_profile"),"config":bundle.get("config"),"engine_version":bundle.get("engine_version")}
    if bundle.get("run_id")!=sha256_text(canonical_json(material)): errors.append("run_id mismatch")
    used=set(); txn_ids=set()
    matches=bundle.get("matches",[]); exceptions=bundle.get("exceptions",[]); unpaid=bundle.get("unpaid_invoices",[])
    if not isinstance(matches,list): errors.append("matches must be an array"); matches=[]
    if not isinstance(exceptions,list): errors.append("exceptions must be an array"); exceptions=[]
    if not isinstance(unpaid,list): errors.append("unpaid_invoices must be an array"); unpaid=[]
    for match in matches:
        if not isinstance(match,dict): errors.append("invalid match object"); continue
        txn=match.get("txn",{}); tid=txn.get("id")
        if not tid or tid in txn_ids: errors.append("missing or duplicate matched transaction ID")
        if tid: txn_ids.add(tid)
        if txn.get("currency")!=currency: errors.append(f"transaction currency mismatch for {tid}")
        total=Decimal("0")
        for inv in match.get("invoices",[]):
            iid=inv.get("id")
            if not iid or iid in used: errors.append("invoice reused or missing invoice ID")
            if iid: used.add(iid)
            if inv.get("currency")!=currency: errors.append(f"invoice currency mismatch for {iid}")
            total+=_decimal(inv.get("amount"),f"invoice {iid}",errors)
        residual=_decimal(txn.get("amount"),f"transaction {tid}",errors)-total
        claimed=_decimal(match.get("residual"),f"residual {tid}",errors)
        if residual!=claimed: errors.append(f"residual mismatch for transaction {tid}")
        if residual!=0: errors.append(f"accepted match has non-zero residual for transaction {tid}")
        if match.get("solver_status")!="exact_unique": errors.append(f"accepted match lacks exact_unique status for transaction {tid}")
        if match.get("decision")!="accepted_by_rule": errors.append(f"invalid accepted decision for transaction {tid}")
        if match.get("evidence_class") not in {"DIRECT_REFERENCE","CORROBORATED","AMOUNT_ONLY"}: errors.append(f"invalid evidence class for transaction {tid}")
    for item in exceptions:
        if not isinstance(item,dict): errors.append("invalid exception object"); continue
        txn=item.get("txn",{}); tid=txn.get("id")
        if not tid or tid in txn_ids: errors.append("missing or duplicate exception transaction ID")
        if tid: txn_ids.add(tid)
        if txn.get("currency")!=currency: errors.append(f"exception currency mismatch for {tid}")
        if item.get("decision")!="pending_human_review": errors.append(f"invalid exception decision for transaction {tid}")
    unpaid_ids=set()
    for inv in unpaid:
        iid=inv.get("id") if isinstance(inv,dict) else None
        if not iid or iid in unpaid_ids: errors.append("duplicate or missing unpaid invoice ID")
        if iid in used: errors.append(f"matched invoice appears unpaid: {iid}")
        if iid: unpaid_ids.add(iid)
        if isinstance(inv,dict) and inv.get("currency")!=currency: errors.append(f"unpaid invoice currency mismatch for {iid}")
    summary=bundle.get("summary",{})
    if not isinstance(summary,dict): errors.append("summary must be an object"); summary={}
    if summary.get("deposits_processed")!=len(txn_ids): errors.append("deposit partition count mismatch")
    if summary.get("accepted_matches")!=len(matches): errors.append("accepted match count mismatch")
    if summary.get("exceptions")!=len(exceptions): errors.append("exception count mismatch")
    if summary.get("matched_invoice_count")!=len(used): errors.append("matched invoice count mismatch")
    return errors
