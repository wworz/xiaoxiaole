# -*- coding: utf-8 -*-
"""
兑换码解析单元测试
运行方式: python -m pytest tests/test_parser.py 或 python -m unittest discover tests
"""

import unittest
import sys
import os

# 添加上级目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import parse_codes_from_text, _is_valid_code


class TestIsValidCode(unittest.TestCase):
    """测试 _is_valid_code 函数"""

    def setUp(self):
        self.filter_words = [
            "HTTP", "HTTPS", "WWW", "COM", "CN", "NET", "ORG",
            "HTML", "PHP", "ASP", "JSP",
        ]
        self.min_len = 6
        self.max_len = 20

    def test_valid_code(self):
        """有效兑换码应返回 True"""
        self.assertTrue(_is_valid_code("ABC123DEF456", self.filter_words, self.min_len, self.max_len))
        self.assertTrue(_is_valid_code("KXXL888", self.filter_words, self.min_len, self.max_len))
        self.assertTrue(_is_valid_code("VIP666", self.filter_words, self.min_len, self.max_len))
        self.assertTrue(_is_valid_code("NEWYEAR2024", self.filter_words, self.min_len, self.max_len))

    def test_pure_numbers(self):
        """纯数字不应是有效兑换码"""
        self.assertFalse(_is_valid_code("123456", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("000000", self.filter_words, self.min_len, self.max_len))

    def test_pure_letters(self):
        """纯字母不应是有效兑换码"""
        self.assertFalse(_is_valid_code("ABCDEF", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("HELLOWORLD", self.filter_words, self.min_len, self.max_len))

    def test_too_short(self):
        """太短的码应被过滤"""
        self.assertFalse(_is_valid_code("AB12", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("A1", self.filter_words, self.min_len, self.max_len))

    def test_too_long(self):
        """太长的码应被过滤"""
        long_code = "A1" * 15  # 30 个字符
        self.assertFalse(_is_valid_code(long_code, self.filter_words, self.min_len, self.max_len))

    def test_filter_words(self):
        """过滤词应被排除"""
        self.assertFalse(_is_valid_code("HTTP", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("HTTPS", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("WWW", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("HTML", self.filter_words, self.min_len, self.max_len))

    def test_case_insensitive(self):
        """大小写不敏感"""
        self.assertTrue(_is_valid_code("abc123def", self.filter_words, self.min_len, self.max_len))
        self.assertTrue(_is_valid_code("AbC123DeF", self.filter_words, self.min_len, self.max_len))


class TestParseCodesFromText(unittest.TestCase):
    """测试 parse_codes_from_text 函数"""

    def setUp(self):
        self.parser_config = {
            "min_length": 6,
            "max_length": 20,
            "keywords": ["兑换码", "礼包码", "CDK", "福利码", "口令", "激活码"],
            "filter_words": [
                "HTTP", "HTTPS", "WWW", "COM", "CN", "NET", "ORG",
                "HTML", "PHP", "ASP", "JSP", "GIF", "PNG", "JPG",
            ],
        }

    def test_keyword_match_exchange_code(self):
        """关键词'兑换码'后紧跟的码应被识别"""
        text = "最新兑换码：ABC123DEF，赶快使用！"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("ABC123DEF", codes)

    def test_keyword_match_gift_code(self):
        """关键词'礼包码'后紧跟的码应被识别"""
        text = "礼包码: VIP666888，先到先得"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("VIP666888", codes)

    def test_keyword_match_cdk(self):
        """关键词'CDK'后紧跟的码应被识别"""
        text = "CDK：KXXL2024NEW 限时领取"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("KXXL2024NEW", codes)

    def test_keyword_variations(self):
        """不同分隔符的关键词都应匹配"""
        texts = [
            "兑换码ABC123DEF",
            "兑换码:ABC123DEF",
            "兑换码：ABC123DEF",
            "兑换码 ABC123DEF",
            "兑换码  ABC123DEF",
        ]
        for text in texts:
            result = parse_codes_from_text(text, self.parser_config)
            codes = [r["code"] for r in result]
            self.assertIn("ABC123DEF", codes, f"未能从 '{text}' 中识别")

    def test_case_insensitive_keywords(self):
        """关键词大小写不敏感"""
        text = "cdk：KXXL666888"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("KXXL666888", codes)

    def test_code_unified_uppercase(self):
        """识别出的码应统一转为大写"""
        text = "兑换码：abc123def"
        result = parse_codes_from_text(text, self.parser_config)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["code"], "ABC123DEF")

    def test_multiple_codes(self):
        """识别多个兑换码"""
        text = """
        兑换码一：ABC123DEF
        兑换码二：GHI456JKL
        礼包码：VIP666888
        """
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("ABC123DEF", codes)
        self.assertIn("GHI456JKL", codes)
        self.assertIn("VIP666888", codes)
        self.assertGreaterEqual(len(result), 3)

    def test_deduplication_in_single_text(self):
        """同一段文本中重复的码应去重"""
        text = """
        兑换码：ABC123DEF
        再次提醒兑换码：ABC123DEF
        礼包码：ABC123DEF
        """
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertEqual(codes.count("ABC123DEF"), 1)

    def test_filter_html_keywords(self):
        """应过滤 HTML/HTTP 等无意义词"""
        text = "访问 https://www.example.com/abc123.html 获取兑换码"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        # HTML/HTTPS/WWW/COM 不应出现在结果中
        self.assertNotIn("HTML", codes)
        self.assertNotIn("HTTPS", codes)
        self.assertNotIn("WWW", codes)
        self.assertNotIn("COM", codes)

    def test_empty_text(self):
        """空文本应返回空列表"""
        result = parse_codes_from_text("", self.parser_config)
        self.assertEqual(result, [])

    def test_none_text(self):
        """None 文本应返回空列表"""
        result = parse_codes_from_text(None, self.parser_config)
        self.assertEqual(result, [])

    def test_raw_text_included(self):
        """结果应包含原始文本片段"""
        text = "最新活动兑换码：ABC123DEF 快来领取"
        result = parse_codes_from_text(text, self.parser_config)
        self.assertGreater(len(result), 0)
        self.assertIn("raw_text", result[0])
        self.assertTrue(len(result[0]["raw_text"]) > 0)

    def test_welfare_keyword(self):
        """福利码关键词应匹配"""
        text = "专属福利码：FULI9999 福利多多"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("FULI9999", codes)

    def test_activation_keyword(self):
        """激活码关键词应匹配"""
        text = "激活码: JIHUO888 立即激活"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("JIHUO888", codes)

    def test_command_keyword(self):
        """口令关键词应匹配"""
        text = "口令：KOULING666 神秘礼包"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("KOULING666", codes)


class TestSeenCodesLogic(unittest.TestCase):
    """测试去重逻辑（基于 seen_codes 的外部验证）"""

    def test_code_comparison_case_insensitive(self):
        """码的比较应不区分大小写"""
        from main import get_seen_code_set

        seen_list = [
            {"code": "ABC123", "source": "test", "first_seen": "2024-01-01", "url": "", "raw_text": ""},
            {"code": "def456", "source": "test", "first_seen": "2024-01-01", "url": "", "raw_text": ""},
        ]
        seen_set = get_seen_code_set(seen_list)

        # 集合中应该都是大写
        self.assertIn("ABC123", seen_set)
        self.assertIn("DEF456", seen_set)
        self.assertNotIn("def456", seen_set)

    def test_empty_seen_list(self):
        """空列表应返回空集合"""
        from main import get_seen_code_set

        self.assertEqual(get_seen_code_set([]), set())


if __name__ == "__main__":
    unittest.main()
