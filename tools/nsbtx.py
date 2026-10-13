"""NDS 텍스처(NSBTX) → 그림. 하트골드 필드 그림(히비키·코토네)을 꺼낼 때 쓴다 (4·16·256색 팔레트 텍스처)."""
import struct, sys
from PIL import Image

def info_list(b, off):
    num = b[off + 1]
    p = off + 4
    sub = struct.unpack_from("<H", b, p)[0]          # 헤더 크기 (8)
    p += sub + num * 4
    each = struct.unpack_from("<H", b, p)[0]
    p += 4
    data = [b[p + i * each: p + (i + 1) * each] for i in range(num)]
    p += num * each
    names = [b[p + i * 16: p + i * 16 + 16].rstrip(b"\0").decode("latin1") for i in range(num)]
    return list(zip(names, data))

def bgr555(v):
    return ((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31)

def decode(path):
    b = open(path, "rb").read()
    assert b[:4] == b"BTX0"
    t = struct.unpack_from("<I", b, 16)[0]
    assert b[t:t + 4] == b"TEX0", b[t:t+4]
    tex_info = struct.unpack_from("<H", b, t + 0x0E)[0]
    tex_data = struct.unpack_from("<I", b, t + 0x14)[0]
    pal_info = struct.unpack_from("<I", b, t + 0x34)[0]
    pal_data = struct.unpack_from("<I", b, t + 0x38)[0]
    texs = info_list(b, t + tex_info)
    pals = info_list(b, t + pal_info)
    out = []
    for (tname, td), (pname, pd) in zip(texs, pals * len(texs)):
        off, param = struct.unpack_from("<HH", td, 0)
        off <<= 3
        w, h = 8 << ((param >> 4) & 7), 8 << ((param >> 7) & 7)
        fmt, transp = (param >> 10) & 7, (param >> 13) & 1
        poff = struct.unpack_from("<H", pd, 0)[0] << 3
        bpp = {2: 2, 3: 4, 4: 8}.get(fmt)
        if not bpp:
            print("형식", fmt, "건너뜀"); continue
        ncol = 1 << bpp
        pal = [bgr555(struct.unpack_from("<H", b, t + pal_data + poff + i * 2)[0]) for i in range(ncol)]
        im = Image.new("RGBA", (w, h))
        px = im.load()
        base = t + tex_data + off
        for i in range(w * h):
            byte = b[base + (i * bpp) // 8]
            v = (byte >> ((i * bpp) % 8)) & (ncol - 1)
            px[i % w, i // w] = (0, 0, 0, 0) if (v == 0 and transp) else pal[v] + (255,)
        out.append((tname, pname, im))
    return out

if __name__ == "__main__":
    for tname, pname, im in decode(sys.argv[1]):
        print(tname, pname, im.size)
        im.save(sys.argv[2] + f"_{tname}.png")
