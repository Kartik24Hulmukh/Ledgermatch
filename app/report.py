"""Safe CSV and HTML artifacts for reconciliation review."""
from __future__ import annotations
import csv, html, io


def safe_cell(value):
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def _csv(header, rows):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([[safe_cell(v) for v in row] for row in rows])
    return buf.getvalue()


def matches_csv(result):
    return _csv(["Txn ID","Date","Description","Deposit","Currency","Invoices","Customers","Match Type","Evidence Class","Solver Status","Residual","Explanation"],
                [[m.txn.id,m.txn.date.isoformat(),m.txn.description,f"{m.txn.amount:.2f}",m.txn.currency,"|".join(i.invoice_no for i in m.invoices),"|".join(sorted({i.customer for i in m.invoices})),m.match_type,m.evidence_class,m.solver_status,f"{m.residual:.2f}",m.explanation] for m in result.matches])


def exceptions_csv(result):
    return _csv(["Txn ID","Date","Description","Deposit","Currency","Reason","Solver Status","Alternatives","Guidance"],
                [[u.txn.id,u.txn.date.isoformat(),u.txn.description,f"{u.txn.amount:.2f}",u.txn.currency,u.reason,u.solver_status,";".join("|".join(c) for c in u.alternatives),u.suggestions] for u in result.unmatched])


def unpaid_csv(result):
    return _csv(["Invoice ID","Invoice No","Customer","Date","Amount","Currency","Days Outstanding"],
                [[i.id,i.invoice_no,i.customer,i.date.isoformat(),f"{i.amount:.2f}",i.currency,(result.as_of-i.date).days if result.as_of else ""] for i in result.unpaid_invoices])


def payments_import_csv(result):
    rows=[]
    for m in result.matches:
        for i in m.invoices:
            rows.append([m.txn.id,m.txn.date.isoformat(),i.customer,i.invoice_no,f"{i.amount:.2f}",i.currency,m.txn.description,m.match_type,m.evidence_class,m.solver_status])
    return _csv(["Txn ID","Payment Date","Customer","Invoice Number","Amount Applied","Currency","Bank Description","Match Type","Evidence Class","Solver Status"],rows)


_CSS="""body{font-family:system-ui,sans-serif;margin:0;color:#0f172a;background:#f8fafc}header{background:#0f172a;color:#fff;padding:24px 32px}main{padding:24px 32px;max-width:1200px;margin:auto}.cards{display:flex;gap:12px;flex-wrap:wrap}.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px}.n{font-size:22px;font-weight:700}.l{font-size:12px;color:#64748b}table{border-collapse:collapse;width:100%;background:#fff;font-size:12px}th,td{border:1px solid #e2e8f0;padding:6px;text-align:left;vertical-align:top}th{background:#f1f5f9}footer{padding:16px 32px;color:#64748b;font-size:12px}@media(max-width:760px){main{padding:12px}table{display:block;overflow-x:auto}}"""


def html_report(result, firm_name=""):
    e=lambda value: html.escape(str(value),quote=True)
    def row(values): return "<tr>"+"".join(f"<td>{e(v)}</td>" for v in values)+"</tr>"
    match_rows="".join(row([m.txn.id,m.txn.date.isoformat(),m.txn.description,f"{m.txn.amount:.2f}",", ".join(i.invoice_no for i in m.invoices),m.evidence_class,m.solver_status,m.explanation]) for m in result.matches)
    exc_rows="".join(row([u.txn.id,u.txn.date.isoformat(),u.txn.description,f"{u.txn.amount:.2f}",u.reason,u.solver_status,"; ".join(" + ".join(c) for c in u.alternatives),u.suggestions]) for u in result.unmatched)
    firm=f"<p>Prepared by {e(firm_name)}</p>" if firm_name else ""
    return ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>LedgerMatch reconciliation evidence report</title><style>"+_CSS+"</style></head><body>"
            f"<header><h1>Reconciliation evidence report</h1><p>Currency: {e(result.currency)} · review-first output</p>{firm}</header><main>"
            f"<div class='cards'><div class='card'><div class='n'>{result.deposits_processed}</div><div class='l'>Deposits analyzed</div></div>"
            f"<div class='card'><div class='n'>{len(result.matches)}</div><div class='l'>Uniquely supported matches</div></div>"
            f"<div class='card'><div class='n'>{len(result.unmatched)}</div><div class='l'>Need review</div></div></div>"
            f"<h2>Uniquely supported matches</h2><table><tr><th>Txn ID</th><th>Date</th><th>Description</th><th>Deposit</th><th>Invoices</th><th>Evidence</th><th>Solver</th><th>Why</th></tr>{match_rows}</table>"
            f"<h2>Exceptions and ambiguity</h2><table><tr><th>Txn ID</th><th>Date</th><th>Description</th><th>Deposit</th><th>Reason</th><th>Solver</th><th>Alternatives</th><th>Guidance</th></tr>{exc_rows}</table>"
            "</main><footer>LedgerMatch proposes evidence-backed allocations. Ambiguous, residual-bearing, or amount-only combinations require human review. No report is legal, tax, or audit advice.</footer></body></html>")
