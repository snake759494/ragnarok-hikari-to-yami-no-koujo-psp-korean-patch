"""Generic GIM decoder (formats 0-5, swizzle) -> PIL RGBA, and FCHN container reader."""
import struct
from PIL import Image
import gim_tool as G
def fchn(d):
    assert d[:4]==b'FCHN'
    n=struct.unpack_from('<H',d,6)[0]
    return [struct.unpack_from('<II',d,8+8*i) for i in range(n)]  # (size, offset)
def decode(blob):
    im=G.find_chunk(blob,G.IMAGE); h=im.start+16
    _,_,fmt,order,w,hh,bpp,pa,ha=struct.unpack_from('<HHHHHHHHH',blob,h)
    pitch=(w*bpp//8+pa-1)//pa*pa; rows=(hh+ha-1)//ha*ha
    po=im.start+im.data_offset+struct.unpack_from('<I',blob,h+0x1C)[0]
    raw=blob[po:po+pitch*rows]
    px=G.unswizzle(raw,pitch,rows) if order else bytearray(raw)
    pal=None
    pc=G.find_chunk(blob,G.PALETTE)
    if pc:
        ph=pc.start+16; pfmt=struct.unpack_from('<H',blob,ph+4)[0]
        pofs=pc.start+pc.data_offset+struct.unpack_from('<I',blob,ph+0x1C)[0]
        pal=[conv(pfmt,blob,pofs+i*(4 if pfmt==3 else 2)) for i in range(256 if fmt==5 else 16)]
    out=Image.new('RGBA',(w,hh))
    P=out.load()
    for y in range(hh):
        row=y*pitch
        for x in range(w):
            if fmt==5: c=pal[px[row+x]]
            elif fmt==4:
                b=px[row+x//2]; c=pal[(b>>4) if x&1 else (b&15)]
            else: c=conv(fmt,px,row+x*(bpp//8))
            P[x,y]=c
    return out,(fmt,w,hh,bpp,pitch,rows,po,order)
def conv(fmt,b,o):
    if fmt==3: return tuple(b[o:o+4])
    v=struct.unpack_from('<H',b,o)[0]
    if fmt==0: return ((v&31)*255//31,((v>>5)&63)*255//63,((v>>11)&31)*255//31,255)
    if fmt==1: return ((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31,255 if v>>15 else 0)
    if fmt==2: return ((v&15)*17,((v>>4)&15)*17,((v>>8)&15)*17,((v>>12)&15)*17)
    raise ValueError(fmt)
