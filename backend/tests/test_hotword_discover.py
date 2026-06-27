"""hotword_discover 的单元测试。"""
from backend.app.hotword_discover import _parse_llm_json


def test_parse_clean_json():
    """标准 JSON 对象。"""
    content = '{"terms": [{"word": "金蝶", "kind": "产品", "confidence": 0.9, "example": "金蝶接口报错", "is_uncertain": false}]}'
    terms = _parse_llm_json(content)
    assert len(terms) == 1
    assert terms[0]["word"] == "金蝶"
    assert terms[0]["kind"] == "产品"


def test_parse_markdown_wrapped_json():
    """markdown 代码块包裹的 JSON。"""
    content = '```json\n{"terms": [{"word": "ERP", "kind": "行业", "confidence": 0.85, "example": "ERP系统", "is_uncertain": false}]}\n```'
    terms = _parse_llm_json(content)
    assert len(terms) == 1
    assert terms[0]["word"] == "ERP"


def test_parse_empty_response():
    """空响应返回空列表。"""
    assert _parse_llm_json("") == []
    assert _parse_llm_json("无术语") == []


def test_parse_json_with_extra_text():
    """JSON 前后有解释文本。"""
    content = '好的，以下是抽取的术语：\n{"terms": [{"word": "MES", "kind": "行业", "confidence": 0.8, "example": "MES升级", "is_uncertain": false}]}\n希望有帮助'
    terms = _parse_llm_json(content)
    assert len(terms) == 1
    assert terms[0]["word"] == "MES"


def test_parse_missing_terms_key():
    """JSON 没有 terms 键（LLM 没按格式）返回空。"""
    content = '{"result": []}'
    assert _parse_llm_json(content) == []
