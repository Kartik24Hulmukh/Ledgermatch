"""Build a deterministic LedgerMatch source archive."""
from __future__ import annotations
import argparse, hashlib, json, stat, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PREFIX="LedgerMatch-0.4.0"
EXCLUDED_DIRS={".git","dist","__pycache__",".venv","venv"}
EXCLUDED_PREFIXES=("out_",)
EXCLUDED_SUFFIXES=(".pyc",".pyo",".DS_Store")

def included(path:Path)->bool:
    rel=path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS or part.startswith(EXCLUDED_PREFIXES) for part in rel.parts): return False
    if path.name=="RELEASE_MANIFEST.json": return False
    if path.name.endswith(EXCLUDED_SUFFIXES): return False
    return path.is_file()

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def build(output:Path):
    files=sorted((p for p in ROOT.rglob("*") if included(p)),key=lambda p:p.relative_to(ROOT).as_posix())
    manifest={"schema_version":"1.0","release":"0.4.0","files":[{"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":digest(p)} for p in files]}
    manifest_path=ROOT/"RELEASE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    archive_files=files+[manifest_path]
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        for path in sorted(archive_files,key=lambda p:p.relative_to(ROOT).as_posix()):
            arc=f"{PREFIX}/{path.relative_to(ROOT).as_posix()}"
            info=zipfile.ZipInfo(arc,(2020,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3; info.external_attr=(stat.S_IFREG|0o644)<<16
            zf.writestr(info,path.read_bytes())
    return {"filename":output.name,"file_count":len(archive_files),"bytes":output.stat().st_size,"sha256":digest(output),"zip_integrity":"PASS" if zipfile.ZipFile(output).testzip() is None else "FAIL"}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args()
    print(json.dumps(build(args.output),sort_keys=True))
if __name__=="__main__": main()
