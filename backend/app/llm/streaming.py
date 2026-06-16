"""流式文本处理:情绪标签解析 + 句子切分。

两者都是增量的(喂 token、吐结果),用于 LLM 逐字输出场景:
- EmotionParser:从回复开头剥离 [emotion:xxx],其余文本透传。
- SentenceSplitter:按句末标点累积切句,供 TTS 边说边播(阶段 2)。
"""

from __future__ import annotations

import re

from app.llm.prompts import EMOTIONS

_EMOTION_RE = re.compile(r"^\s*\[emotion:([a-z_]+)\]\s*")
# 句末边界:中英文标点 + 换行
_SENTENCE_END = set("。!?！？\n.;；")


class EmotionParser:
    """增量剥离开头的 [emotion:xxx] 标签。

    用法:对每个 token 调 feed(),返回 (emotion_or_none, clean_text)。
    emotion 只会在标签被完整识别的那一次返回一次。
    """

    def __init__(self) -> None:
        self._buf = ""
        self._done = False  # 是否已过了"开头检测"阶段
        self._strip_leading = False  # 标签后续空白需吃掉(空白可能晚于 ] 到达)

    def feed(self, text: str) -> tuple[str | None, str]:
        if self._done:
            if self._strip_leading:
                text = text.lstrip()
                if text:
                    self._strip_leading = False
            return None, text

        self._buf += text

        m = _EMOTION_RE.match(self._buf)
        if m:
            emotion = m.group(1)
            rest = self._buf[m.end():]
            self._done = True
            self._buf = ""
            if emotion not in EMOTIONS:
                emotion = "neutral"
            # rest 为空时,标签后的空白可能还没到,标记下一轮 lstrip
            self._strip_leading = rest == ""
            return emotion, rest

        # 还没匹配到完整标签:可能正在传 "[emo..." 这种前缀,先 hold 住
        if self._looks_like_partial_tag(self._buf):
            return None, ""

        # 确定开头不是情绪标签,把缓冲一次性放出
        self._done = True
        out = self._buf
        self._buf = ""
        return None, out

    def flush(self) -> str:
        """流结束时取出残留缓冲(开头疑似标签但最终没成立的情况)。"""
        out = self._buf
        self._buf = ""
        self._done = True
        return out

    @staticmethod
    def _looks_like_partial_tag(buf: str) -> bool:
        # 仅当 buffer 是 "[emotion:..." 的前缀时才继续等待
        prefix = "[emotion:"
        stripped = buf.lstrip()
        if not stripped:
            return True
        if stripped.startswith(prefix):
            return "]" not in stripped  # 还没闭合
        # 是否是 "[", "[e", "[emo" 这种更短的前缀
        return prefix.startswith(stripped) or stripped.startswith("[") and len(stripped) < len(prefix)


class SentenceSplitter:
    """增量累积文本,在句末标点处吐出完整句子。"""

    def __init__(self, min_len: int = 2) -> None:
        self._buf = ""
        self._min_len = min_len

    def feed(self, text: str) -> list[str]:
        self._buf += text
        out: list[str] = []
        start = 0
        for i, ch in enumerate(self._buf):
            if ch in _SENTENCE_END:
                sentence = self._buf[start : i + 1].strip()
                if len(sentence) >= self._min_len:
                    out.append(sentence)
                    start = i + 1
        self._buf = self._buf[start:]
        return out

    def flush(self) -> str:
        out = self._buf.strip()
        self._buf = ""
        return out
