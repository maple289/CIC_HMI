"""Encoded attribution. Encoding deters casual editing; it is not encryption."""
import base64
import hashlib
import hmac
import json
import zlib

_PACKED = 'c-m!-!Ab)`42EAN%)wI`Y7ZXvR@Mc3D2SHgO{P2PbRZ;aX1cnH59Dk3WX4ud@b>4=_b30G3&TLU4>b$B#@*g^+wK8w)+;x2H6+T6X0JFNOVu0*mK<n$MTNC+uA-R}TtF*aRmegSM<f|gA1UmREPVarMA%KuU&3}v!k56&&V4JyaR#mL{KgyibPSaDzuj8YYO~$xI9V?|{oY`IU?EAlR11x$<&59UzCH&<*q*HhF8$nyUWQ3?I#gpmKVUImT*1E@-UPu3E1+0VM~vRRe*s(vX#o'
_DIGEST = 'e27be38bceaec574ae9b72f2d1164b4e4fac67df5541a52d059bf771c57539d7'


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
