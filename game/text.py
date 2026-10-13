"""한국어 조사 처리 (은(는) → 은/는 등)."""

import re

_JOSA = re.compile(r"([가-힣0-9A-Za-z])(\*\*)?(은\(는\)|이\(가\)|을\(를\)|\(으\)로)")
_DIGIT_BATCHIM = {"0": 21, "1": 8, "2": 0, "3": 16, "4": 0, "5": 0, "6": 1, "7": 8, "8": 8, "9": 0}  # 영 일 이 삼 사 오 육 칠 팔 구


def _batchim(ch: str) -> int:
    """받침 번호 (0 = 없음, 8 = ㄹ)"""
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28
    return _DIGIT_BATCHIM.get(ch, 0)


def josa(text: str) -> str:
    def repl(m):
        ch, bold, j = m.group(1), m.group(2) or "", m.group(3)
        b = _batchim(ch)
        pick = {"은(는)": "은" if b else "는", "이(가)": "이" if b else "가",
                "을(를)": "을" if b else "를", "(으)로": "으로" if b and b != 8 else "로"}[j]
        return ch + bold + pick
    return _JOSA.sub(repl, text)
