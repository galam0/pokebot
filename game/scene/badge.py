"""배지 그림과 배지 케이스 (game/scene 패키지)"""

from .. import adventure as A
from .. import hoenn as HO
from .. import johto as J
from .. import kanto as K

from .base import (_panel)

# ---------- 모험: 필드 화면 ----------
BADGE_RGB = [(168, 168, 176), (88, 152, 240), (240, 160, 48), (120, 200, 96), (240, 120, 176), (232, 196, 64),
             (224, 72, 48), (72, 168, 104)]


def _badge(d, x, y, i: int, got: bool, palette=None):
    """배지 한 개 (13x13). 없으면 빈 자리"""
    if not got:
        d.ellipse((x + 1, y + 1, x + 11, y + 11), outline=(150, 150, 160))
        return
    col = (palette or BADGE_RGB)[i]
    dark = tuple(max(0, c - 90) for c in col)
    light = tuple(min(255, c + 80) for c in col)
    cx, cy = x + 6, y + 6
    shape = [
        [(cx - 3, y), (cx + 3, y), (x + 12, cy - 3), (x + 12, cy + 3), (cx + 3, y + 12), (cx - 3, y + 12),
         (x, cy + 3), (x, cy - 3)],                                                    # 회색: 팔각형 바위
        [(cx, y), (x + 11, cy + 2), (cx + 3, y + 12), (cx - 3, y + 12), (x + 1, cy + 2)],   # 블루: 물방울
        [(cx, y), (cx + 2, cy - 2), (x + 12, cy), (cx + 2, cy + 2), (cx, y + 12), (cx - 2, cy + 2), (x, cy),
         (cx - 2, cy - 2)],                                                            # 오렌지: 별
        [(cx, y), (x + 12, cy), (cx, y + 12), (x, cy)],                                # 무지개: 마름모
        [(cx, y + 3), (cx + 3, y), (x + 12, y + 3), (x + 12, cy), (cx, y + 12), (x, cy), (x, y + 3), (cx - 3, y)],   # 핑크: 하트
        None,                                                                          # 골드: 고리
        [(cx, y), (x + 11, y + 12), (x + 1, y + 12)],                                  # 진홍: 불꽃
        [(x + 1, y + 11), (x + 2, y + 3), (x + 11, y + 1), (x + 10, y + 9)],           # 그린: 잎
    ][i]
    if shape is None:
        d.ellipse((x, y, x + 12, y + 12), fill=col, outline=dark)
        d.ellipse((x + 4, y + 4, x + 8, y + 8), fill=dark)
    else:
        d.polygon(shape, fill=col, outline=dark)
    d.point((cx - 2, cy - 2), fill=light)
    d.point((cx - 1, cy - 3), fill=light)


def _badge_case(d, x, y, run: dict):
    """지금 있는 지방의 배지 8개"""
    mod = {"kanto": None, "johto": J, "hoenn": HO}[A.region_of(run["loc"])]
    order, palette = (mod.GYM_ORDER, mod.BADGE_RGB) if mod else (K.GYM_ORDER, BADGE_RGB)
    _panel(d, (x, y, x + 8 * 16 + 6, y + 18), fill=(56, 48, 72), edge=(24, 20, 32))
    for i, g in enumerate(order):
        _badge(d, x + 4 + i * 16, y + 3, i, g in run["badges"], palette)
