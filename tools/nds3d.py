"""닌텐도 DS 3D 모델(NSBMD)·텍스처(NSBTX)를 읽어 소프트웨어로 그린다 (플래티넘 신오 맵용).

- 텍스처: 모든 형식 (A3I5, 4/16/256색, 4x4 압축, A5I3, 다이렉트)
- 모델: 재질(텍스처·팔레트 이름, 반복/뒤집기, 알파), 노드 변환, 렌더 명령(SBC), 디스플레이 리스트(GX 명령)
- 그리기: numpy z-버퍼 래스터라이저, 원근 카메라 (DS 필드 카메라와 같은 값), 가장 가까운 텍셀 샘플링
읽는 방식은 GBATEK의 GX 명령 설명과 공개된 NSBMD 구조 문서를 따랐다.
"""

import math
import struct

import numpy as np
from PIL import Image

FX = 4096.0


# ---------------------------------------------------------------- 공통
def _dict(b: bytes, off: int) -> list[tuple[str, bytes]]:
    """NITRO 사전 (이름 → 데이터 조각)"""
    num = b[off + 1]
    p = off + 4
    sub = struct.unpack_from("<H", b, p)[0]
    p += sub + num * 4
    each = struct.unpack_from("<H", b, p)[0]
    p += 4
    data = [b[p + i * each: p + (i + 1) * each] for i in range(num)]
    p += num * each
    names = [b[p + i * 16: p + i * 16 + 16].rstrip(b"\0").decode("latin1") for i in range(num)]
    return list(zip(names, data))


def _rgb555(v: int) -> tuple[int, int, int]:
    return ((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31)


def _blocks(b: bytes) -> dict[str, int]:
    """BMD0/BTX0 파일의 블록 (이름 → 시작)"""
    n = struct.unpack_from("<H", b, 0x0E)[0]
    out = {}
    for i in range(n):
        o = struct.unpack_from("<I", b, 0x10 + i * 4)[0]
        out[b[o:o + 4].decode("latin1")] = o
    return out


# ---------------------------------------------------------------- 텍스처
class TexSet:
    """TEX0 블록: 텍스처·팔레트 이름으로 RGBA 그림을 만든다"""

    def __init__(self, b: bytes, t: int):
        self.b, self.t = b, t
        self.tex_data = t + struct.unpack_from("<I", b, t + 0x14)[0]
        self.c4_data = t + struct.unpack_from("<I", b, t + 0x24)[0]
        self.c4_idx = t + struct.unpack_from("<I", b, t + 0x28)[0]
        self.pal_data = t + struct.unpack_from("<I", b, t + 0x38)[0]
        self.tex = {}
        for name, d in _dict(b, t + struct.unpack_from("<H", b, t + 0x0E)[0]):
            off, param = struct.unpack_from("<HH", d, 0)
            self.tex[name] = (off << 3, param)
        self.pal = {}
        for name, d in _dict(b, t + struct.unpack_from("<I", b, t + 0x34)[0]):
            self.pal[name] = struct.unpack_from("<H", d, 0)[0] << 3
        self._cache = {}

    @classmethod
    def from_file(cls, path: str) -> "TexSet | None":
        b = open(path, "rb").read()
        blk = _blocks(b)
        return cls(b, blk["TEX0"]) if "TEX0" in blk else None

    def size(self, tname: str) -> tuple[int, int]:
        _, param = self.tex[tname]
        return 8 << ((param >> 4) & 7), 8 << ((param >> 7) & 7)

    def image(self, tname: str, pname: str | None) -> np.ndarray | None:
        """(h, w, 4) uint8"""
        key = (tname, pname)
        if key in self._cache:
            return self._cache[key]
        if tname not in self.tex:
            return None
        b = self.b
        off, param = self.tex[tname]
        w, h = 8 << ((param >> 4) & 7), 8 << ((param >> 7) & 7)
        fmt, transp = (param >> 10) & 7, (param >> 13) & 1
        poff = self.pal.get(pname, 0) if pname else 0
        pal_base = self.pal_data + poff

        def pal(n):
            raw = np.frombuffer(b, dtype="<u2", count=n, offset=min(pal_base, len(b) - 2 * n))
            return np.stack([(raw & 31) * 255 // 31, ((raw >> 5) & 31) * 255 // 31,
                             ((raw >> 10) & 31) * 255 // 31], -1).astype(np.uint8)

        out = np.zeros((h, w, 4), np.uint8)
        n = w * h
        base = self.tex_data + off
        if fmt in (2, 3, 4):
            bpp = {2: 2, 3: 4, 4: 8}[fmt]
            raw = np.frombuffer(b, np.uint8, count=n * bpp // 8, offset=base)
            if bpp == 8:
                idx = raw.astype(np.int32)
            else:
                per = 8 // bpp
                idx = np.stack([(raw >> (k * bpp)) & ((1 << bpp) - 1) for k in range(per)], -1).reshape(-1)
            p = pal(1 << bpp)
            out[..., :3] = p[idx].reshape(h, w, 3)
            out[..., 3] = np.where((idx == 0) & bool(transp), 0, 255).reshape(h, w)
        elif fmt in (1, 6):   # A3I5, A5I3
            raw = np.frombuffer(b, np.uint8, count=n, offset=base).astype(np.int32)
            if fmt == 1:
                idx, a = raw & 31, (raw >> 5) * 255 // 7
                p = pal(32)
            else:
                idx, a = raw & 7, (raw >> 3) * 255 // 31
                p = pal(8)
            out[..., :3] = p[idx].reshape(h, w, 3)
            out[..., 3] = a.reshape(h, w)
        elif fmt == 7:   # 다이렉트
            raw = np.frombuffer(b, "<u2", count=n, offset=base).astype(np.int32)
            out[..., 0] = ((raw & 31) * 255 // 31).reshape(h, w)
            out[..., 1] = (((raw >> 5) & 31) * 255 // 31).reshape(h, w)
            out[..., 2] = (((raw >> 10) & 31) * 255 // 31).reshape(h, w)
            out[..., 3] = np.where(raw >> 15, 255, 0).reshape(h, w)
        elif fmt == 5:   # 4x4 압축
            texels = np.frombuffer(b, "<u4", count=n // 16, offset=self.c4_data + off)
            pidx = np.frombuffer(b, "<u2", count=n // 16, offset=self.c4_idx + off // 2)
            bw = w // 4
            for k in range(n // 16):
                pi = int(pidx[k])
                mode, poff2 = pi >> 14, (pi & 0x3FFF) * 4
                cols = [_rgb555(struct.unpack_from("<H", b, pal_base + poff2 + i * 2)[0]) for i in range(4)
                        if pal_base + poff2 + i * 2 + 2 <= len(b)]
                while len(cols) < 4:
                    cols.append((0, 0, 0))
                c0, c1 = cols[0], cols[1]
                if mode == 0:
                    cs = [c0 + (255,), c1 + (255,), cols[2] + (255,), (0, 0, 0, 0)]
                elif mode == 1:
                    cs = [c0 + (255,), c1 + (255,), tuple((a + b2) // 2 for a, b2 in zip(c0, c1)) + (255,), (0, 0, 0, 0)]
                elif mode == 2:
                    cs = [c + (255,) for c in cols]
                else:
                    cs = [c0 + (255,), c1 + (255,), tuple((5 * a + 3 * b2) // 8 for a, b2 in zip(c0, c1)) + (255,),
                          tuple((3 * a + 5 * b2) // 8 for a, b2 in zip(c0, c1)) + (255,)]
                tv = int(texels[k])
                by, bx = (k // bw) * 4, (k % bw) * 4
                for yy in range(4):
                    for xx in range(4):
                        out[by + yy, bx + xx] = cs[(tv >> ((yy * 4 + xx) * 2)) & 3]
        else:
            return None
        self._cache[key] = out
        return out


# ---------------------------------------------------------------- 모델
def _mat_from_node(d: bytes, p: int):
    """노드 TRS → 4x4 (DS 행렬은 행 벡터 기준이지만 여기서는 열 벡터로 바꿔 쓴다)"""
    flag, m0 = struct.unpack_from("<Hh", d, p)
    p += 4
    t = np.zeros(3)
    r = np.eye(3)
    s = np.ones(3)
    if not flag & 1:
        t = np.array(struct.unpack_from("<3i", d, p)) / FX
        p += 12
    if not flag & 2:
        if flag & 8:   # 피벗 압축 회전
            a, bb = (v / FX for v in struct.unpack_from("<2h", d, p))
            p += 4
            sel, neg = (flag >> 4) & 15, (flag >> 8) & 15
            r = _pivot(sel, neg, a, bb)
        else:
            vals = struct.unpack_from("<8h", d, p)
            p += 16
            m = [m0 / FX] + [v / FX for v in vals]
            r = np.array(m).reshape(3, 3)
    if not flag & 4:
        s = np.array(struct.unpack_from("<3i", d, p)) / FX
        p += 24
    M = np.eye(4)
    M[:3, :3] = (r * s[:, None]).T   # 행 벡터 행렬 → 열 벡터
    M[:3, 3] = t
    return M


def _pivot(sel, neg, a, b):
    o = -1.0 if neg & 1 else 1.0
    c = -b if neg & 2 else b
    d = -a if neg & 4 else a
    m = np.zeros(9)
    piv = sel
    m[piv] = o
    rest = [i for i in range(9) if i // 3 != piv // 3 and i % 3 != piv % 3]
    m[rest[0]], m[rest[1]], m[rest[2]], m[rest[3]] = a, b, c, d
    return m.reshape(3, 3)


class Model:
    """NSBMD 안의 모델 하나: 재질·삼각형 목록"""

    def __init__(self, b: bytes, mo: int):
        self.b = b
        hd = struct.unpack_from("<5I", b, mo)
        _, sbc, mats, shps, _ = hd
        self.n_nodes, self.n_mats, self.n_shapes = b[mo + 0x17], b[mo + 0x18], b[mo + 0x19]
        self.pos_scale = struct.unpack_from("<i", b, mo + 0x1C)[0] / FX
        # 노드
        self.nodes = []
        for name, d in _dict(b, mo + 0x40):
            noff = struct.unpack_from("<I", d, 0)[0]
            self.nodes.append(_mat_from_node(b, mo + 0x40 + noff))
        # 재질
        mbase = mo + mats
        tex_off, pal_off = struct.unpack_from("<HH", b, mbase)
        self.mats = []
        for name, d in _dict(b, mbase + 4):
            p = mbase + struct.unpack_from("<I", d, 0)[0]
            polyattr = struct.unpack_from("<I", b, p + 0x0C)[0]
            teximg = struct.unpack_from("<I", b, p + 0x14)[0]
            flags = struct.unpack_from("<H", b, p + 0x1E)[0]
            w, h = struct.unpack_from("<HH", b, p + 0x20)
            dif = struct.unpack_from("<I", b, p + 0x04)[0]
            tex_scale = (1.0, 1.0)
            q = p + 0x2C
            if flags & 0x2000:   # 텍스처 행렬 (크기 조절만 반영)
                if not flags & 0x0002:
                    tex_scale = (struct.unpack_from("<i", b, q)[0] / FX, struct.unpack_from("<i", b, q + 4)[0] / FX)
            self.mats.append({"name": name, "tex": None, "pal": None, "alpha": (polyattr >> 16) & 31,
                              "cull": (polyattr >> 6) & 3, "rep": (teximg >> 16) & 3, "flip": (teximg >> 18) & 3,
                              "w": w, "h": h, "dif": _rgb555(dif & 0x7FFF), "tscale": tex_scale})
        for kind, off in (("tex", tex_off), ("pal", pal_off)):
            for name, d in _dict(b, mbase + off):
                lst, cnt = struct.unpack_from("<HB", d, 0)
                for i in range(cnt):
                    mi = b[mbase + lst + i]
                    if mi < len(self.mats):
                        self.mats[mi][kind] = name
        # 모양 (디스플레이 리스트)
        sbase = mo + shps
        self.shapes = []
        for name, d in _dict(b, sbase):
            p = sbase + struct.unpack_from("<I", d, 0)[0]
            dl_off, dl_size = struct.unpack_from("<II", b, p + 8)
            self.shapes.append(b[p + dl_off: p + dl_off + dl_size])
        self.sbc = b[mo + sbc: mo + mats]

    # ------------------------------------------------------------ 렌더 명령
    def triangles(self):
        """[(재질 번호, (N,3,3) 위치, (N,3,2) 텍스처 좌표(텍셀), (N,3,3) 정점 색)]"""
        out = []
        stack = {}
        cur_mtx = np.eye(4)
        cur_mat = 0
        s = self.sbc
        i = 0
        while i < len(s):
            op = s[i]
            cmd = op & 0x1F
            if cmd == 0x00:   # NOP
                i += 1
            elif cmd == 0x01:   # 끝
                break
            elif cmd == 0x02:   # 노드 보이기
                i += 3
            elif cmd == 0x03:   # 행렬 불러오기
                cur_mtx = stack.get(s[i + 1], np.eye(4))
                i += 2
            elif cmd == 0x04:   # 재질
                cur_mat = s[i + 1]
                i += 2
            elif cmd == 0x05:   # 모양 그리기
                si = s[i + 1]
                if si < len(self.shapes):
                    out.extend(self._run_dl(self.shapes[si], cur_mat, cur_mtx, stack))
                i += 2
            elif cmd == 0x06:   # 노드 변환
                node, parent = s[i + 1], s[i + 2]
                M = self.nodes[node] if node < len(self.nodes) else np.eye(4)
                base = stack.get(("node", parent), np.eye(4)) if parent != node else np.eye(4)
                cur_mtx = base @ M
                stack[("node", node)] = cur_mtx
                i += 4
                if op & 0x20:   # 저장
                    stack[s[i]] = cur_mtx
                    i += 1
                if op & 0x40:   # 불러오기
                    cur_mtx = stack.get(s[i], cur_mtx)
                    i += 1
            elif cmd == 0x07 or cmd == 0x08:   # 빌보드
                i += 2
            elif cmd == 0x09:   # 가중치 행렬 (맵에는 거의 없음)
                n = s[i + 2]
                i += 3 + n * 3
            elif cmd == 0x0B:   # 크기 조절 시작/끝
                i += 1
            elif cmd == 0x0C:
                i += 3
            elif cmd == 0x0D:
                i += 3
            else:
                i += 1
        return out

    def _run_dl(self, dl: bytes, mat: int, M: np.ndarray, stack: dict):
        PARAMS = {0x00: 0, 0x10: 1, 0x11: 0, 0x12: 1, 0x13: 1, 0x14: 1, 0x15: 0, 0x16: 16, 0x17: 12, 0x18: 16,
                  0x19: 12, 0x1A: 9, 0x1B: 3, 0x1C: 3, 0x20: 1, 0x21: 1, 0x22: 1, 0x23: 2, 0x24: 1, 0x25: 1,
                  0x26: 1, 0x27: 1, 0x28: 1, 0x29: 1, 0x2A: 1, 0x2B: 1, 0x30: 1, 0x31: 1, 0x32: 1, 0x33: 1,
                  0x34: 32, 0x40: 1, 0x41: 0, 0x50: 1, 0x60: 1, 0x70: 3, 0x71: 2, 0x72: 1}
        words = struct.unpack_from(f"<{len(dl) // 4}I", dl)
        k = 0
        pos = np.zeros(3)
        tc = (0.0, 0.0)
        col = (255, 255, 255)
        prim = 0
        verts = []
        tris_p, tris_t, tris_c = [], [], []
        mtx = M

        def flush():
            v = verts
            idx = []
            if prim == 0:
                idx = [(j, j + 1, j + 2) for j in range(0, len(v) - 2, 3)]
            elif prim == 1:
                for j in range(0, len(v) - 3, 4):
                    idx += [(j, j + 1, j + 2), (j, j + 2, j + 3)]
            elif prim == 2:
                for j in range(len(v) - 2):
                    idx.append((j, j + 1, j + 2) if j % 2 == 0 else (j + 1, j, j + 2))
            elif prim == 3:
                for j in range(0, len(v) - 3, 2):
                    idx += [(j, j + 1, j + 3), (j, j + 3, j + 2)]
            for a, b2, c in idx:
                tris_p.append([v[a][0], v[b2][0], v[c][0]])
                tris_t.append([v[a][1], v[b2][1], v[c][1]])
                tris_c.append([v[a][2], v[b2][2], v[c][2]])

        def emit():   # 정점은 posScale을 먼저 곱하고 노드 행렬 (노드 이동값은 이미 월드 단위)
            w = mtx @ np.array([pos[0] * self.pos_scale, pos[1] * self.pos_scale, pos[2] * self.pos_scale, 1.0])
            verts.append((w[:3], tc, col))

        while k < len(words):
            packed = words[k]
            k += 1
            ops = [(packed >> (8 * j)) & 0xFF for j in range(4)]
            for op in ops:
                n = PARAMS.get(op, 0)
                prm = words[k:k + n]
                k += n
                if op == 0x14:   # 행렬 불러오기
                    mtx = stack.get(prm[0] & 31, M)
                elif op == 0x20:
                    col = _rgb555(prm[0])
                elif op == 0x22:
                    sv, tv = prm[0] & 0xFFFF, prm[0] >> 16
                    sv = sv - 65536 if sv & 0x8000 else sv
                    tv = tv - 65536 if tv & 0x8000 else tv
                    tc = (sv / 16.0, tv / 16.0)
                elif op == 0x23:
                    x, y = prm[0] & 0xFFFF, prm[0] >> 16
                    z = prm[1] & 0xFFFF
                    pos = np.array([_s16(x), _s16(y), _s16(z)]) / FX
                    emit()
                elif op == 0x24:
                    v = prm[0]
                    pos = np.array([_s10(v & 0x3FF), _s10((v >> 10) & 0x3FF), _s10((v >> 20) & 0x3FF)]) / 64.0
                    emit()
                elif op == 0x25:
                    pos = np.array([_s16(prm[0] & 0xFFFF) / FX, _s16(prm[0] >> 16) / FX, pos[2]])
                    emit()
                elif op == 0x26:
                    pos = np.array([_s16(prm[0] & 0xFFFF) / FX, pos[1], _s16(prm[0] >> 16) / FX])
                    emit()
                elif op == 0x27:
                    pos = np.array([pos[0], _s16(prm[0] & 0xFFFF) / FX, _s16(prm[0] >> 16) / FX])
                    emit()
                elif op == 0x28:
                    v = prm[0]
                    pos = pos + np.array([_s10(v & 0x3FF), _s10((v >> 10) & 0x3FF), _s10((v >> 20) & 0x3FF)]) / FX
                    emit()
                elif op == 0x40:
                    if verts:
                        flush()
                    verts = []
                    prim = prm[0] & 3
                elif op == 0x41:
                    flush()
                    verts = []
        if verts:
            flush()
        if not tris_p:
            return []
        return [(mat, np.array(tris_p), np.array(tris_t), np.array(tris_c, np.float32))]


def _s16(v):
    return v - 65536 if v & 0x8000 else v


def _s10(v):
    return v - 1024 if v & 0x200 else v


def load_models(path_or_bytes) -> tuple[list[Model], "TexSet | None"]:
    b = open(path_or_bytes, "rb").read() if isinstance(path_or_bytes, str) else path_or_bytes
    blk = _blocks(b)
    mdl = blk["MDL0"]
    models = [Model(b, mdl + struct.unpack_from("<I", d, 0)[0]) for _, d in _dict(b, mdl + 8)]
    tex = TexSet(b, blk["TEX0"]) if "TEX0" in blk else None
    return models, tex


# ---------------------------------------------------------------- 그리기
class Scene:
    """삼각형을 모아 두었다가 카메라로 그린다"""

    def __init__(self):
        self.batches = []   # (위치 (N,3,3), 텍셀 좌표, 색, 텍스처 RGBA, 재질 정보)

    def add_model(self, model: Model, texsets: list, M: np.ndarray | None = None):
        for mi, P, T, C in model.triangles():
            mat = model.mats[mi] if mi < len(model.mats) else {"tex": None, "pal": None, "alpha": 31, "rep": 3,
                                                                "flip": 0, "w": 8, "h": 8, "dif": (255, 255, 255),
                                                                "tscale": (1, 1), "cull": 0}
            img = None
            for ts in texsets:
                if ts and mat["tex"] and mat["tex"] in ts.tex:
                    img = ts.image(mat["tex"], mat["pal"])
                    break
            if M is not None:
                Ph = np.concatenate([P, np.ones(P.shape[:2] + (1,))], -1)
                P = (Ph @ M.T)[..., :3]
            self.batches.append((P, T, C, img, mat))

    def render(self, eye: np.ndarray, target: np.ndarray, fovy_half_deg: float, w: int, h: int,
               bg=(0, 0, 0)) -> Image.Image:
        fwd = target - eye
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        f = 1.0 / math.tan(math.radians(fovy_half_deg))
        aspect = w / h
        color = np.zeros((h, w, 3), np.float32)
        color[:] = bg
        depth = np.full((h, w), np.inf, np.float32)
        trans = []   # 반투명은 나중에 (뒤에서 앞으로)
        for P, T, C, img, mat in self.batches:
            rel = P - eye
            x = rel @ right
            y = rel @ up
            z = rel @ fwd
            ok = (z > 1.0).all(1)
            sx = (x / z * f / aspect * 0.5 + 0.5) * w
            sy = (0.5 - y / z * f * 0.5) * h
            if mat["alpha"] < 31 and mat["alpha"] > 0:
                trans.append((sx, sy, z, T, C, img, mat, ok))
                continue
            if mat["alpha"] == 0:   # 안 보이는 면 (와이어프레임 모드) — 건너뜀
                continue
            self._raster(color, depth, sx, sy, z, T, C, img, mat, ok, blend=False)
        for t in trans:
            self._raster(color, depth, *t[:7], t[7], blend=True)
        return Image.fromarray(np.clip(color, 0, 255).astype(np.uint8))

    @staticmethod
    def _raster(color, depth, sx, sy, z, T, C, img, mat, ok, blend):
        h, w = depth.shape
        if img is not None:
            th, tw = img.shape[:2]
            sc = mat.get("tscale", (1, 1))
        dif = np.array(mat.get("dif", (255, 255, 255)), np.float32) / 255.0
        a_mat = mat["alpha"] / 31.0
        for n in np.nonzero(ok)[0]:
            x0, y0, x1, y1, x2, y2 = sx[n, 0], sy[n, 0], sx[n, 1], sy[n, 1], sx[n, 2], sy[n, 2]
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-9:
                continue
            minx, maxx = max(int(math.floor(min(x0, x1, x2))), 0), min(int(math.ceil(max(x0, x1, x2))), w - 1)
            miny, maxy = max(int(math.floor(min(y0, y1, y2))), 0), min(int(math.ceil(max(y0, y1, y2))), h - 1)
            if minx > maxx or miny > maxy:
                continue
            ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
            px, py = xs + 0.5, ys + 0.5
            w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
            w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not inside.any():
                continue
            iz = np.array([1 / z[n, 0], 1 / z[n, 1], 1 / z[n, 2]])
            zi = w0 * iz[0] + w1 * iz[1] + w2 * iz[2]
            zz = 1.0 / zi
            region = depth[miny:maxy + 1, minx:maxx + 1]
            vis = inside & (zz <= region + 0.05)   # 같은 깊이면 나중 것 (건물 문 프롭이 건물 안의 문을 덮게)
            if not vis.any():
                continue
            cvert = C[n] / 255.0
            vc = (w0[..., None] * cvert[0] * iz[0] + w1[..., None] * cvert[1] * iz[1]
                  + w2[..., None] * cvert[2] * iz[2]) / zi[..., None]
            if img is not None:
                u = (w0 * T[n, 0, 0] * iz[0] + w1 * T[n, 1, 0] * iz[1] + w2 * T[n, 2, 0] * iz[2]) / zi * sc[0]
                v = (w0 * T[n, 0, 1] * iz[0] + w1 * T[n, 1, 1] * iz[1] + w2 * T[n, 2, 1] * iz[2]) / zi * sc[1]
                ui = np.floor(u).astype(np.int64)
                vi = np.floor(v).astype(np.int64)
                ui = _wrap(ui, tw, mat["rep"] & 1, mat["flip"] & 1)
                vi = _wrap(vi, th, mat["rep"] & 2, mat["flip"] & 2)
                tex = img[vi, ui].astype(np.float32)
                rgb = tex[..., :3] * vc
                alpha = tex[..., 3] / 255.0
                vis &= alpha > 0.5 if not blend else alpha > 0.01
            else:
                rgb = 255.0 * vc * dif
                alpha = np.ones_like(zz)
            if not vis.any():
                continue
            creg = color[miny:maxy + 1, minx:maxx + 1]
            if blend:
                a = (alpha * a_mat)[..., None]
                creg[vis] = (creg * (1 - a) + rgb * a)[vis]
            else:
                creg[vis] = rgb[vis]
                region[vis] = zz[vis]


def _wrap(i, n, rep, flip):
    if not rep:
        return np.clip(i, 0, n - 1)
    if flip:
        m = np.mod(i, 2 * n)
        return np.where(m >= n, 2 * n - 1 - m, m)
    return np.mod(i, n)
