"""Mechanical release verifier. Exits non-zero on any failed gate."""
from __future__ import annotations
import hashlib, json, os, re, subprocess, sys, tempfile, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEXT_SUFFIXES={".py",".md",".yml",".yaml",".txt",".html",".json"}
BANNED=re.compile(r"\b(?:100x|revolutionary|game-changing|guaranteed|production-capable|everything else is done)\b",re.I)
PLACEHOLDER=re.compile(r"REPLACE|TODO|example\.org|ACCOUNT_ID")
SECRET=re.compile(r"(?:sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})")
STALE=re.compile(r"(?:^|/)(?:__pycache__|\.pytest_cache)(?:/|$)|\.(?:pyc|pyo)$|(?:^|/)\.DS_Store$")

def run(command,env=None):
    result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,env=env)
    if result.returncode:
        print(result.stdout); print(result.stderr,file=sys.stderr); raise SystemExit(result.returncode)
    return result.stdout+result.stderr

def scan():
    problems=[]
    for path in ROOT.rglob("*"):
        if not path.is_file(): continue
        rel=path.relative_to(ROOT).as_posix()
        if rel.startswith((".git/","dist/","out_")): continue
        if STALE.search(rel): problems.append(f"stale:{rel}")
        if path.suffix.lower() in TEXT_SUFFIXES and rel != "scripts/verify_release.py":
            text=path.read_text(errors="ignore")
            if BANNED.search(text): problems.append(f"banned:{rel}")
            if PLACEHOLDER.search(text): problems.append(f"placeholder:{rel}")
            if SECRET.search(text): problems.append(f"secret:{rel}")
    return problems

def main():
    problems=scan()
    if problems:
        print("\n".join(problems)); return 1
    with tempfile.TemporaryDirectory(prefix="lm-verify-") as temp:
        temp=Path(temp); env=dict(os.environ); env["PYTHONPYCACHEPREFIX"]=str(temp/"pycache"); env["PYTHONDONTWRITEBYTECODE"]="1"
        test_output=run([sys.executable,"-W","error::ResourceWarning","-m","unittest","discover","-s","tests","-v"],env)
        out=temp/"demo"
        run([sys.executable,"-m","app.cli","--bank","demo_data/bank_statement.csv","--invoices","demo_data/invoices.csv","--out",str(out),"--currency","USD","--date-format","YMD"],env)
        from app.evidence import validate_bundle
        bundle=json.loads((out/"evidence.json").read_text())
        evidence_errors=validate_bundle(bundle)
        if evidence_errors:
            print("evidence:"+";".join(evidence_errors)); return 1
        run([sys.executable,"-m","app.validate",str(out/"evidence.json"),"--checksum",str(out/"evidence.sha256")],env)
        a=temp/"a.zip"; b=temp/"b.zip"
        first=json.loads(run([sys.executable,"scripts/build_release.py","--output",str(a)],env).strip().splitlines()[-1])
        second=json.loads(run([sys.executable,"scripts/build_release.py","--output",str(b)],env).strip().splitlines()[-1])
        if a.read_bytes()!=b.read_bytes(): print("deterministic_package:FAIL"); return 1
        if zipfile.ZipFile(a).testzip() is not None: print("zip_integrity:FAIL"); return 1
        tests=re.search(r"Ran (\d+) tests",test_output)
        receipt={"tests":int(tests.group(1)) if tests else None,"warnings_as_errors":"PASS","evidence_validation":"PASS","banned_hits":0,"placeholder_hits":0,"secret_hits":0,"stale_hits":0,"deterministic_package":"PASS","zip_integrity":"PASS","package_file_count":first["file_count"],"package_bytes":first["bytes"],"package_sha256":first["sha256"]}
        print(json.dumps(receipt,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
