"""플래티넘 신오 맵을 3D로 그린다 (pret/pokeplatinum 데이터, tools/nds3d.py).

맵 매트릭스(32x32칸 땅 조각을 이어 붙인 격자) → 땅 조각마다 지형 모델 + 건물(프롭) 모델을 놓고,
필드 카메라(거리 666.9, 59도 내려다봄, 세로 시야 반각 8.09도)로 그린다.
화면 1칸 = 16px (DS와 같은 크기), 320x192로 그린 뒤 3배로 키운다.

    python tools/sinnoh_maps.py <pokeplatinum 경로> <맵 헤더 이름> <중심 x칸> <중심 z칸> <출력.png>
"""

import json
import math
import re
import struct
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nds3d as N  # noqa: E402

CHUNK = 32          # 땅 조각 하나 = 32x32칸
TILE = 16.0         # 한 칸 = 16 (월드 단위)
CAM_DIST = 666.922119140625
CAM_PITCH = 59.051513671875
CAM_FOV = 8.0914306640625


class Platinum:
    def __init__(self, root: str):
        self.root = Path(root)
        self.field = self.root / "res/field"
        self.prop_order = [l.strip() for l in open(self.field / "props/models/map_prop_models.order")]
        self.map_order = [l.strip() for l in open(self.field / "maps/data/map_data.order")]
        self.headers = self._headers()

    def _headers(self) -> dict[str, dict]:
        s = (self.root / "include/data/map_headers.h").read_text()
        out = {}
        for m in re.finditer(r"\[(MAP_HEADER_\w+)\]\s*=\s*\{(.*?)\n    \}", s, re.S):
            body = m.group(2)
            f = dict(re.findall(r"\.(\w+)\s*=\s*([^,\n]+),", body))
            out[m.group(1)] = f
        return out

    @lru_cache(maxsize=None)
    def matrix(self, mid: str) -> dict:
        return json.load(open(self.field / f"matrices/{mid}.json"))

    @lru_cache(maxsize=None)
    def area(self, aid: str) -> dict:
        return json.load(open(self.field / f"area_data/{aid}.json"))

    @lru_cache(maxsize=64)
    def map_tex(self, name: str):
        return N.TexSet.from_file(str(self.field / f"maps/texture_sets/{name}.nsbtx"))

    @lru_cache(maxsize=64)
    def prop_tex(self, name: str):
        p = self.field / f"props/texture_sets/{name}.nsbtx"
        return N.TexSet.from_file(str(p)) if p.exists() else None

    @lru_cache(maxsize=None)
    def prop(self, mid: int):
        return N.load_models(str(self.field / "props/models" / self.prop_order[mid]))

    @lru_cache(maxsize=256)
    def land(self, map_id: str):
        """MAP_123 → (지형 모델들, 프롭 목록, 칸 속성 32x32)"""
        n = int(map_id.split("_")[1])
        b = (self.field / "maps/data" / self.map_order[n]).read_bytes()
        a, p, m, bd = struct.unpack_from("<4I", b, 0)
        attrs = np.frombuffer(b, "<u2", count=a // 2, offset=16).reshape(CHUNK, CHUNK) if a == 2048 else None
        props = [struct.unpack_from("<I3i3i3i", b, 16 + a + k * 0x30) for k in range(p // 0x30)]
        models, _ = N.load_models(b[16 + a + p: 16 + a + p + m])
        return models, props, attrs

    def cells(self, header: str) -> list[tuple[int, int]]:
        """이 맵 헤더가 차지하는 매트릭스 칸 (행, 열)"""
        mid = self.headers[header]["mapMatrixID"].strip()
        m = self.matrix(mid)
        out = []
        for r, row in enumerate(m.get("headers") or []):
            for c, h in enumerate(row):
                if h == header:
                    out.append((r, c))
        if not out:   # 실내처럼 헤더 표가 없는 매트릭스: 땅이 있는 칸 전부
            for r, row in enumerate(m["maps"]):
                for c, mp in enumerate(row):
                    if mp != "MAP_NONE":
                        out.append((r, c))
        return out

    def scene(self, header: str, rows: range, cols: range) -> N.Scene:
        """매트릭스의 (행, 열) 범위를 하나의 장면으로. 월드 좌표: 열 c, 행 r의 조각 중심 = (c*512, r*512)"""
        h = self.headers[header]
        mid = h["mapMatrixID"].strip()
        m = self.matrix(mid)
        sc = N.Scene()
        for r in rows:
            for c in cols:
                if not (0 <= r < len(m["maps"]) and 0 <= c < len(m["maps"][r])):
                    continue
                mp = m["maps"][r][c]
                if mp == "MAP_NONE":
                    continue
                hd = m["headers"][r][c] if m.get("headers") else header
                aid = self.headers.get(hd, h)["areaDataArchiveID"].strip()
                ar = self.area(aid)
                alt = m["altitudes"][r][c] if m.get("altitudes") else 0
                off = np.eye(4)
                off[:3, 3] = [c * CHUNK * TILE, alt * TILE / 2, r * CHUNK * TILE]
                models, props, _ = self.land(mp)
                mt = self.map_tex(ar["mapTextureSet"])
                for mdl in models:
                    sc.add_model(mdl, [mt], off)
                pt = self.prop_tex(ar["mapPropSet"].replace("model", "texture"))
                for pid, x, y, z, rx, ry, rz, sx, sy, sz in props:
                    if pid >= len(self.prop_order):
                        continue
                    pm, ptx = self.prop(pid)
                    M = np.diag([sx / 4096, sy / 4096, sz / 4096, 1.0])
                    M[:3, 3] = [x / 4096, y / 4096, z / 4096]
                    for mdl in pm:
                        sc.add_model(mdl, [pt, ptx], off @ M)   # 지역 프롭 텍스처가 먼저 (게임도 이걸 붙인다)
        return sc


def events(pl: Platinum, header: str) -> dict:
    name = pl.headers[header]["eventsArchiveID"].strip()
    f = pl.field / "events" / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def walkable(pl: Platinum, header: str) -> set[tuple[int, int]]:
    """이 헤더의 걸을 수 있는 칸 (매트릭스 전체 칸 좌표)"""
    m = pl.matrix(pl.headers[header]["mapMatrixID"].strip())
    out = set()
    for r, c in pl.cells(header):
        _, _, attrs = pl.land(m["maps"][r][c])
        if attrs is None:
            continue
        zs, xs = np.nonzero((attrs >> 15) == 0)
        out.update(zip((c * CHUNK + xs).tolist(), (r * CHUNK + zs).tolist()))
    return out


def auto_view(pl: Platinum, header: str, kind: str = "field") -> tuple[int, int]:
    """카메라(주인공) 칸: 마을이면 포켓몬센터 앞, 아니면 걸을 수 있는 칸들의 가운데"""
    walk = walkable(pl, header)
    if not walk:
        cells = pl.cells(header)
        r, c = cells[len(cells) // 2]
        return c * CHUNK + 16, r * CHUNK + 16
    xs = sorted(x for x, _ in walk)
    zs = sorted(z for _, z in walk)
    target = (xs[len(xs) // 2], zs[len(zs) // 2])
    ev = events(pl, header)
    pts = [(e["x"], e["z"]) for k in ("object_events", "warp_events", "bg_events") for e in ev.get(k, [])]
    if pts:   # 사람·문·표지판이 있는 곳의 가운데 (방은 조각 한쪽 구석에 있어서 걸을 수 있는 칸 가운데는 빈 곳)
        target = (sorted(x for x, _ in pts)[len(pts) // 2], sorted(z for _, z in pts)[len(pts) // 2])
    if kind == "field":
        for w in ev.get("warp_events", []):
            if "POKECENTER_1F" in w["dest_header_id"]:
                target = (w["x"], w["z"] + 3)
                break
    elif kind in ("center", "mart"):   # 카운터가 보이게 문과 카운터 사이
        doors = [(w["x"], w["z"]) for w in ev.get("warp_events", [])]
        if doors:
            dx, dz = doors[0]
            target = (dx, dz - 4)
    return min(walk, key=lambda p: (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2)


def ground_height(pl: Platinum, header: str, gx: float, gz: float) -> float:
    """(칸 좌표) 땅의 높이: 그 칸을 덮는 거의 평평한 지형 삼각형 중 가장 낮은 것 (나무 꼭대기·지붕 말고 땅)"""
    m = pl.matrix(pl.headers[header]["mapMatrixID"].strip())
    c, r = int(gx // CHUNK), int(gz // CHUNK)
    if not (0 <= r < len(m["maps"]) and 0 <= c < len(m["maps"][r])) or m["maps"][r][c] == "MAP_NONE":
        return 0.0
    alt = m["altitudes"][r][c] if m.get("altitudes") else 0
    px = (gx - c * CHUNK) * TILE - CHUNK * TILE / 2 + TILE / 2
    pz = (gz - r * CHUNK) * TILE - CHUNK * TILE / 2 + TILE / 2
    models, _, _ = pl.land(m["maps"][r][c])
    best = None
    for mdl in models:
        for _, P, _, _ in mdl.triangles():
            a, b, cc = P[:, 0], P[:, 1], P[:, 2]
            n = np.cross(b - a, cc - a)
            ln = np.linalg.norm(n, axis=1) + 1e-9
            flat = np.abs(n[:, 1]) / ln > 0.7
            # 점이 삼각형(xz 투영) 안에 있는지
            v0, v1 = (b - a)[:, [0, 2]], (cc - a)[:, [0, 2]]
            v2 = np.array([px, pz]) - a[:, [0, 2]]
            d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
            d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
            den = d00 * d11 - d01 * d01
            ok = np.abs(den) > 1e-9
            den = np.where(ok, den, 1)
            v = (d11 * d20 - d01 * d21) / den
            w = (d00 * d21 - d01 * d20) / den
            inside = ok & flat & (v >= -1e-4) & (w >= -1e-4) & (v + w <= 1 + 1e-4)
            if inside.any():
                y = (a[:, 1] + v * (b - a)[:, 1] + w * (cc - a)[:, 1])[inside]
                lo = float(y.min())
                best = lo if best is None else min(best, lo)
    return (best if best is not None else 0.0) + alt * TILE / 2


def render(pl: Platinum, header: str, cx: float, cz: float, w: int = 320, h: int = 192, scale: int = 3,
           zoom: float = 1.0, bg=(16, 24, 16)):
    """(cx, cz): 월드 칸 좌표 (매트릭스 전체 기준, 칸 단위). 그 칸이 화면 가운데."""
    tx = cx * TILE - CHUNK * TILE / 2 + TILE / 2
    tz = cz * TILE - CHUNK * TILE / 2 + TILE / 2
    # 보이는 범위의 조각만 싣는다
    span_x = w / 16 / 2 / zoom + 4
    span_z = h / 16 / 2 / zoom + 10
    c0, c1 = int((cx - span_x) // CHUNK), int((cx + span_x) // CHUNK)
    r0, r1 = int((cz - span_z) // CHUNK), int((cz + span_z) // CHUNK)
    sc = pl.scene(header, range(r0, r1 + 1), range(c0, c1 + 1))
    ang = math.radians(CAM_PITCH)
    target = np.array([tx, ground_height(pl, header, cx, cz), tz])   # 주인공이 서 있는 땅 높이를 본다
    eye = target + np.array([0.0, math.sin(ang), math.cos(ang)]) * CAM_DIST
    fov = math.degrees(math.atan(math.tan(math.radians(CAM_FOV)) * (h / 192) / zoom))
    im = sc.render(eye, target, fov, w, h, bg=bg)
    return im.resize((w * scale, h * scale), 0) if scale != 1 else im


if __name__ == "__main__":
    root, header, x, z, out = sys.argv[1:6]
    pl = Platinum(root)
    render(pl, header, float(x), float(z)).save(out)
