"""Standalone Reconciliation Evidence Bundle validator."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from .evidence import validate_bundle

def main(argv=None):
    parser=argparse.ArgumentParser(prog="ledgermatch-validate")
    parser.add_argument("evidence",type=Path); parser.add_argument("--checksum",type=Path)
    args=parser.parse_args(argv)
    try: raw=args.evidence.read_bytes(); bundle=json.loads(raw)
    except (OSError,json.JSONDecodeError) as exc:
        print(f"INVALID: unreadable evidence: {type(exc).__name__}",file=sys.stderr); return 2
    if args.checksum:
        try: expected=args.checksum.read_text(encoding="utf-8").split()[0]
        except (OSError,IndexError) as exc:
            print(f"INVALID: unreadable checksum: {type(exc).__name__}",file=sys.stderr); return 2
        actual=hashlib.sha256(raw).hexdigest()
        if actual!=expected:
            print("INVALID: evidence file checksum mismatch",file=sys.stderr); return 3
    errors=validate_bundle(bundle)
    if errors:
        for error in errors: print("INVALID: "+error,file=sys.stderr)
        return 4
    print("VALID run_id="+str(bundle.get("run_id",""))); return 0
if __name__=="__main__": sys.exit(main())
