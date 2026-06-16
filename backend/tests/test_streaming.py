from app.llm.streaming import EmotionParser, SentenceSplitter


def _parse_all(parser: EmotionParser, text: str, chunk: int = 1):
    """逐 chunk 喂入,聚合输出。"""
    emotion = None
    out = ""
    for i in range(0, len(text), chunk):
        emo, clean = parser.feed(text[i : i + chunk])
        if emo:
            emotion = emo
        out += clean
    out += parser.flush()
    return emotion, out


def test_emotion_parser_extracts_tag():
    emotion, text = _parse_all(EmotionParser(), "[emotion:happy] 你好")
    assert emotion == "happy"
    assert text == "你好"


def test_emotion_parser_no_tag():
    emotion, text = _parse_all(EmotionParser(), "直接说话不带标签")
    assert emotion is None
    assert text == "直接说话不带标签"


def test_emotion_parser_invalid_tag_falls_back():
    emotion, text = _parse_all(EmotionParser(), "[emotion:bogus] hi")
    assert emotion == "neutral"
    assert text == "hi"


def test_emotion_parser_char_by_char():
    # 确保逐字喂入也能正确识别(WS 真实场景)
    emotion, text = _parse_all(EmotionParser(), "[emotion:sad] 唔…", chunk=1)
    assert emotion == "sad"
    assert text == "唔…"


def test_sentence_splitter_basic():
    sp = SentenceSplitter()
    out = sp.feed("第一句。第二句!剩下")
    assert out == ["第一句。", "第二句!"]
    assert sp.flush() == "剩下"


def test_sentence_splitter_incremental():
    sp = SentenceSplitter()
    collected = []
    for ch in "你好。再见!":
        collected += sp.feed(ch)
    assert collected == ["你好。", "再见!"]
    assert sp.flush() == ""
