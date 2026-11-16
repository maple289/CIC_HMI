"""Offline startup checks. Unsigned checks detect damage, not publisher identity."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
from .attribution import developer_information

# Release staging changes these constants before native compilation only.
_PROTECTED = False
_PUBLIC_KEY = ''


class IntegrityError(ValueError):
    pass


def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')


def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(root,envelope,public_key='',required=()):
    """Verify a manifest against an independently pinned key, never its own key."""
    try:
        root=Path(root).resolve();payload=envelope['payload'];files=payload['files']
        if payload.get('schema')!=1 or not isinstance(files,dict) or not files or len(files)>10000:
            raise IntegrityError('Invalid integrity manifest')
        if public_key:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.exceptions import InvalidSignature
            try:
                Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key,validate=True)).verify(base64.b64decode(envelope['signature'],validate=True),canonical(payload))
            except (InvalidSignature,ValueError,KeyError) as error:
                raise IntegrityError('Release signature does not match the trusted publisher key') from error
        elif envelope.get('signature'):
            raise IntegrityError('Signed manifest requires an independently trusted public key')
        if not set(required)<=set(files):raise IntegrityError('Required protected components are missing from manifest')
        for relative,expected in files.items():
            path=Path(relative)
            if path.is_absolute() or '..' in path.parts or ':' in relative or '\\' in relative:
                raise IntegrityError('Invalid resource path in manifest')
            target=(root/path).resolve()
            if not target.is_relative_to(root) or not target.is_file():raise IntegrityError(f'Protected component missing: {relative}')
            if not isinstance(expected,str) or not hmac.compare_digest(file_digest(target),expected):
                raise IntegrityError(f'Protected component changed: {relative}')
        return {'protected':True,'signature':'verified' if public_key else 'unsigned','files_verified':len(files)}
    except IntegrityError:raise
    except (OSError,ValueError,TypeError,KeyError,ImportError) as error:
        raise IntegrityError('Protected components could not be verified') from error


def verify_startup():
    try:developer_information()
    except ValueError as error:raise IntegrityError('Developer attribution could not be verified') from error
    if not _PROTECTED:return {'protected':False,'signature':'development','files_verified':0}
    root=Path(__file__).resolve().parents[2]
    manifest=root/'prevex_hmi/assets/integrity.json'
    required=['prevex_hmi/assets/prevex-hmi.ico','prevex_hmi/assets/fonts/PrevexUI-Regular.ttf',
              'prevex_hmi/assets/fonts/PrevexUI-SemiBold.ttf','prevex_hmi/assets/fonts/PrevexUI-Bold.ttf',
              'prevex_hmi/assets/fonts/PrevexSymbols-Regular.ttf']
    native=list(root.glob('prevex_hmi*.pyd'))
    if len(native)!=1:raise IntegrityError('Protected native application is missing or ambiguous')
    required.append(native[0].name)
    try:envelope=json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:raise IntegrityError('Protected resource manifest is missing or invalid') from error
    return verify_manifest(root,envelope,_PUBLIC_KEY,required)
