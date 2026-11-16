"""Rebuild deterministic vector branding and multi-resolution PNG-backed ICO."""
from pathlib import Path
import math,struct,sys
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
root=Path(__file__).resolve().parents[1];assets=root/'src/prevex_hmi/assets'

def arc(start,end,color):
    def point(a):return (128+94*math.cos(math.radians(a)),128+94*math.sin(math.radians(a)))
    x,y=point(start);u,v=point(end)
    return f'<path d="M{x:.3f} {y:.3f} A94 94 0 0 1 {u:.3f} {v:.3f}" fill="none" stroke="{color}" stroke-width="22"/>'
svg='<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect x="2" y="2" width="252" height="252" rx="52" fill="#0D1828" stroke="#718399" stroke-width="4"/>'
svg+=arc(135,267,'#34BA98')+arc(271,321,'#E9B84F')+arc(325,405,'#E36C71')
svg+='<path d="M118 136 L192 66 L138 145 Z" fill="#F2F5F8"/><circle cx="128" cy="137" r="12" fill="#F2F5F8"/>'
# Letter paths avoid font/renderer variation and keep HMI bold at small sizes.
svg+='<path d="M63 154 V197 H74 V180 H89 V197 H100 V154 H89 V170 H74 V154 Z M108 197 V154 H120 L132 175 L144 154 H156 V197 H145 V174 L132 193 L119 174 V197 Z M167 154 H199 V164 H189 V187 H199 V197 H167 V187 H177 V164 H167 Z" fill="#F2F5F8"/></svg>'
assets.mkdir(parents=True,exist_ok=True);(assets/'prevex-hmi.svg').write_text(svg,encoding='utf-8')
renderer=QSvgRenderer(svg.encode());images=[]
for size in (16,24,32,48,64,128,256):
    # Supersample even the 16px variant for legible strokes.
    img=QImage(size*4,size*4,QImage.Format_ARGB32);img.fill(Qt.transparent)
    painter=QPainter(img);renderer.render(painter);painter.end();img=img.scaled(size,size,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.WriteOnly);img.save(buffer,'PNG');images.append((size,bytes(data)))
    if size==256:img.save(str(assets/'prevex-hmi.png'))
offset=6+16*len(images);entries=[];payload=[]
for size,data in images:
    entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset));payload.append(data);offset+=len(data)
(assets/'prevex-hmi.ico').write_bytes(struct.pack('<HHH',0,1,len(images))+b''.join(entries)+b''.join(payload))
print('Created SVG, PNG and 7-resolution ICO (16–256px)')
