"""Build-only manifest tools. Keys must be supplied externally, never bundled."""
import argparse,base64,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from prevex_hmi.security.integrity import canonical,file_digest,verify_manifest


def signing_key(path):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    target=Path(path).resolve()
    if target.is_relative_to(ROOT):raise ValueError('Signing keys must be stored outside the development repository')
    password=os.environ.get('PREVEX_MANIFEST_KEY_PASSWORD')
    key=load_pem_private_key(target.read_bytes(),password.encode() if password else None)
    if not isinstance(key,Ed25519PrivateKey):raise ValueError('An Ed25519 manifest-signing key is required')
    return key


def envelope(root,paths,key=None):
    root=Path(root).resolve()
    files={Path(p).resolve().relative_to(root).as_posix():file_digest(p) for p in sorted(paths)}
    payload={'schema':1,'product':'PREVEX HMI','version':'1.0','files':files}
    return {'payload':payload,'signature':base64.b64encode(key.sign(canonical(payload))).decode() if key else ''}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['create','verify']);parser.add_argument('root',type=Path)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--signing-key',type=Path)
    parser.add_argument('--public-key',type=Path,help='Independently trusted raw32-byte Ed25519 public key; do not trust a key delivered beside a download')
    args=parser.parse_args();root=args.root.resolve();manifest=args.manifest.resolve()
    if args.operation=='create':
        key=signing_key(args.signing_key) if args.signing_key else None
        paths=[p for p in root.rglob('*') if p.is_file() and p.resolve()!=manifest]
        manifest.write_text(json.dumps(envelope(root,paths,key),indent=2),encoding='utf-8')
        print('Release manifest created'+(' and signed' if key else ' (unsigned; no publisher authenticity claim)'))
    else:
        public=base64.b64encode(args.public_key.read_bytes()).decode() if args.public_key else ''
        print(json.dumps(verify_manifest(root,json.loads(manifest.read_text(encoding='utf-8')),public)))


if __name__=='__main__':main()
