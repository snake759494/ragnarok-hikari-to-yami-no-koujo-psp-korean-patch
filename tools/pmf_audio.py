"""Extract ATRAC3+ audio (private stream 0xBD) from a PSMF file into an .oma file."""
import struct,sys
def audio_es(d):
    out=bytearray(); p=0x800
    while p<len(d):
        if d[p:p+4]!=b'\x00\x00\x01\xba': p+=0x800; continue
        q=p+14
        while q<p+0x800-6 and d[q:q+3]==b'\x00\x00\x01':
            sid=d[q+3]; ln=struct.unpack('>H',d[q+4:q+6])[0]
            if sid==0xbd:
                hl=d[q+8]; pay=d[q+9+hl:q+6+ln]
                out+=pay[4:]
            q+=6+ln
        p+=0x800
    return bytes(out)
def to_oma(es):
    assert es[:2]==b'\x0f\xd0', es[:8].hex()
    b2,b3=es[2],es[3]
    fsz=(((b2&3)<<8)|b3)*8+8
    frames=bytearray(); p=0
    while p+8+fsz<=len(es):
        assert es[p:p+2]==b'\x0f\xd0'
        frames+=es[p+8:p+8+fsz]; p+=8+fsz
    h=bytearray(0x60); h[0:3]=b'EA3'; h[3]=1; h[4:6]=b'\x00\x60'; h[6:8]=b'\xff\xff'
    h[0x20]=1; h[0x21]=0; h[0x22]=b2; h[0x23]=b3
    return bytes(h)+bytes(frames)
if __name__=='__main__':
    d=open(sys.argv[1],'rb').read(); open(sys.argv[2],'wb').write(to_oma(audio_es(d)))
