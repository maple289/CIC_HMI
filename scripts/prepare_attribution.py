"""Regenerate encoded attribution from readable development-only source."""
from pathlib import Path
import base64,hashlib,json,zlib
info={
'application':'PREVEX HMI',
 'tagline':'Industrial Analyzer Monitoring & Control',
 'developer_label':'Developed by:',
 'developer':'Alexander Alexeev, C.E.T.',
 'qualification':'Certified Engineering Technologist',
 'version':'Software Version: 1.0',
 'copyright':'© 2026 Alexander Alexeev. All rights reserved.',
}
raw=json.dumps(info,ensure_ascii=False,separators=(',',':')).encode('utf-8')
packed=base64.b85encode(zlib.compress(raw,9)).decode('ascii')
module='''"""Encoded attribution. Encoding deters casual editing; it is not encryption."""
import base64
import hashlib
import hmac
import json
import zlib

_PACKED = %r
_DIGEST = %r


def developer_information():
    try:
        raw=zlib.decompress(base64.b85decode(_PACKED))
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),_DIGEST):
            raise ValueError('Attribution digest mismatch')
        info=json.loads(raw)
        if not isinstance(info,dict) or len(info)!=7 or any(not isinstance(v,str) for v in info.values()):
            raise ValueError('Invalid attribution content')
        return info
    except (ValueError,TypeError,zlib.error,UnicodeError,KeyError) as error:
        raise ValueError('Protected attribution could not be verified') from error
''' % (packed,hashlib.sha256(raw).hexdigest())
(Path(__file__).resolve().parents[1]/'src/prevex_hmi/security/attribution.py').write_text(module,encoding='utf-8')
