"""Split text into speakable chunks for sentence-by-sentence TTS streaming (es/ru/en).
Sentence ends: . ! ? … (and CJK equivalents) followed by whitespace, or a newline. Chunks shorter than MIN_CHARS are merged
with the next one (tiny inputs make the model babble and sound choppy); chunks longer than MAX_CHARS are cut at the last
comma/semicolon/colon before the limit, else at a space."""
import re

MIN_CHARS = 24
MAX_CHARS = 220
_END = re.compile(r"(?<=[.!?…。！？])[\"')\]»”]*\s+|\n+")
_SOFT = re.compile(r"(?<=[,;:—–])\s+")


def _cut_long(s):
    out = []
    while len(s) > MAX_CHARS:
        head = s[:MAX_CHARS]
        cut = max((m.end() for m in _SOFT.finditer(head)), default=0) or head.rfind(" ") + 1 or MAX_CHARS
        out.append(s[:cut].strip())
        s = s[cut:].strip()
    return out + [s] if s else out


def split_sentences(text):
    parts = [p.strip() for p in _END.split(text) if p and p.strip()]
    chunks = []
    for p in parts:
        chunks += _cut_long(p)
    merged = []
    carry = ""
    for c in chunks:
        c = f"{carry} {c}".strip() if carry else c
        if len(c) < MIN_CHARS:
            carry = c
            continue
        carry = ""
        merged.append(c)
    if carry:
        if merged and len(merged[-1]) + len(carry) <= MAX_CHARS:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)
    return merged


if __name__ == "__main__":
    cases = {
        "Listo, ya lo mandé.": 1,
        "Terminé de renderizar el video. Lo subí a la carpeta compartida. Avisame si querés que lo revise.": 3,
        "Sí. No. Tal vez. Bueno, ahora te explico todo el asunto con calma.": 1,
        "Я закончил рендер видео. Загрузил его в общую папку! Скажи, если хочешь, чтобы я проверил?": 3,
        "Versión 3.5 lista. El precio es $4.50 por mes.": 1,
        ("palabra, " * 60).strip(", "): 3,
        "": 0,
    }
    for text, n in cases.items():
        got = split_sentences(text)
        assert all(len(c) <= MAX_CHARS for c in got), got
        assert "".join(got).replace(" ", "").replace(",", "") .startswith(text.replace(" ", "").replace(",", "")[:5]), got
        print(len(got), "==" if len(got) == n else "!= (wanted %d)" % n, [c[:30] for c in got])
