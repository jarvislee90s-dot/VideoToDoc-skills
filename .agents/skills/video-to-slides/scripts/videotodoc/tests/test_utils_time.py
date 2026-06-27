from videotodoc.utils import seconds_to_ms, ms_to_seconds


def test_seconds_to_ms_positive():
    assert seconds_to_ms(1.5) == 1500


def test_seconds_to_ms_zero():
    assert seconds_to_ms(0.0) == 0


def test_seconds_to_ms_negative_clamped():
    assert seconds_to_ms(-1.5) == 0


def test_ms_to_seconds():
    assert ms_to_seconds(1500) == 1.5


def test_transcript_from_dict_accepts_seconds():
    """transcript_from_dict 应兼容秒格式 JSON"""
    from videotodoc.asr import transcript_from_dict
    data = {"segments": [{"start": 1.5, "end": 3.2, "text": "hello"}]}
    t = transcript_from_dict(data)
    assert t.segments[0].start_ms == 1500
    assert t.segments[0].end_ms == 3200


def test_transcript_from_dict_accepts_ms():
    """transcript_from_dict 应接受毫秒格式 JSON（原有功能）"""
    from videotodoc.asr import transcript_from_dict
    data = {"segments": [{"start_ms": 1500, "end_ms": 3200, "text": "hello"}]}
    t = transcript_from_dict(data)
    assert t.segments[0].start_ms == 1500
    assert t.segments[0].end_ms == 3200


def test_transcript_from_dict_words_accept_seconds():
    """transcript_from_dict 中 words 也应兼容秒格式"""
    from videotodoc.asr import transcript_from_dict
    data = {
        "segments": [{
            "start": 0.0,
            "end": 2.5,
            "text": "hello world",
            "words": [
                {"start": 0.0, "end": 1.0, "word": "hello"},
                {"start": 1.0, "end": 2.5, "word": "world"},
            ],
        }]
    }
    t = transcript_from_dict(data)
    assert t.segments[0].words[0].start_ms == 0
    assert t.segments[0].words[0].end_ms == 1000
    assert t.segments[0].words[1].start_ms == 1000
    assert t.segments[0].words[1].end_ms == 2500
