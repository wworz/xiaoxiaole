# -*- coding: utf-8 -*-
"""
兑换码解析单元测试
运行方式: python -m pytest tests/test_parser.py 或 python -m unittest discover tests
"""

import unittest
import sys
import os
from datetime import datetime, timedelta

# 添加上级目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    parse_codes_from_text,
    _is_valid_code,
    _is_likely_official_number,
    _is_stale_content,
    _is_image_attribution,
)


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

    def test_icp_prefix_filtered(self):
        """ICP 开头的备案号应被过滤"""
        self.assertFalse(_is_valid_code("ICP140541", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("ICP2024001", self.filter_words, self.min_len, self.max_len))

    def test_id_number_like_filtered(self):
        """纯数字+末尾单字母的疑似证件号应被过滤（7位以上）"""
        self.assertFalse(_is_valid_code("1234567A", self.filter_words, self.min_len, self.max_len))
        self.assertFalse(_is_valid_code("1101011990X", self.filter_words, self.min_len, self.max_len))


class TestIsLikelyOfficialNumber(unittest.TestCase):
    """测试 _is_likely_official_number 上下文过滤函数"""

    def test_game_record_number(self):
        """游戏备案号 CSG120 后跟'号'应识别为官方编号"""
        text = "文网游备字2014M-CSG120号"
        # CSG120 在文本中的位置
        start = text.find("CSG120")
        end = start + len("CSG120")
        self.assertTrue(_is_likely_official_number(text, start, end))

    def test_icp_license(self):
        """ICP 备案号格式应识别为官方编号"""
        text = "京ICP证140541号"
        start = text.find("ICP")
        end = start + len("ICP")
        # ICP 本身会被前缀过滤，这里测试上下文
        text2 = "京ICP证140541号"
        start2 = text2.find("140541")
        end2 = start2 + len("140541")
        # 140541 是纯数字，不会被识别为码，但前后有"证"和"号"
        self.assertTrue(_is_likely_official_number(text2, start2, end2))

    def test_di_hao_format(self):
        """第XXX号格式应识别为官方编号"""
        text = "第A12345号"
        start = text.find("A12345")
        end = start + len("A12345")
        self.assertTrue(_is_likely_official_number(text, start, end))

    def test_zi_hao_format(self):
        """XX字XXX号格式应识别为官方编号"""
        text = "京政字A2024001号"
        start = text.find("A2024001")
        end = start + len("A2024001")
        self.assertTrue(_is_likely_official_number(text, start, end))

    def test_normal_code_not_official(self):
        """正常兑换码不应被识别为官方编号"""
        text = "最新兑换码：ABC123DEF 快来领取"
        start = text.find("ABC123DEF")
        end = start + len("ABC123DEF")
        self.assertFalse(_is_likely_official_number(text, start, end))

    def test_code_with_prefix_bei(self):
        """前面有'备'字的应识别为官方编号"""
        text = "备案号B2024001信息"
        start = text.find("B2024001")
        end = start + len("B2024001")
        self.assertTrue(_is_likely_official_number(text, start, end))

    def test_code_with_suffix_zheng(self):
        """后面有'证'字的应识别为官方编号"""
        text = "编号C2024001证"
        start = text.find("C2024001")
        end = start + len("C2024001")
        self.assertTrue(_is_likely_official_number(text, start, end))


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

    # ---- 误报过滤测试 ----

    def test_false_positive_game_record_number(self):
        """游戏备案号 CSG120 不应被识别为兑换码"""
        text = "文网游备字2014M-CSG120号 是本游戏的备案号"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertNotIn("CSG120", codes)

    def test_false_positive_icp_license(self):
        """ICP 备案号不应被识别为兑换码"""
        text = "京ICP证140541号 是本站的备案信息"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertNotIn("ICP140541", codes)

    def test_false_positive_di_hao(self):
        """第XXX号格式不应被识别为兑换码"""
        text = "本产品批准文号为 第A12345号"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertNotIn("A12345", codes)

    def test_false_positive_zi_hao(self):
        """XX字XXX号格式不应被识别为兑换码"""
        text = "京政字A2024001号 官方文件"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertNotIn("A2024001", codes)

    def test_false_positive_short_code_in_text(self):
        """6位的码如果没有关键词前缀，全文扫描不应匹配（全文扫描最小8位）"""
        text = "随机出现的 VIP666 没有前缀关键词"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        # VIP666 只有 6 位，全文扫描最小 8 位，且没有关键词前缀
        self.assertNotIn("VIP666", codes)

    def test_keyword_still_works_with_hao(self):
        """关键词+码+号的格式，只要码前面有关键词，仍应识别（关键词匹配优先级高）"""
        text = "兑换码：VIP666888号礼包"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        # 有关键词"兑换码"前缀，策略一匹配，仍应识别
        self.assertIn("VIP666888", codes)


class TestIsStaleContent(unittest.TestCase):
    """测试 _is_stale_content 日期时效过滤"""

    def setUp(self):
        # 固定"当前时间"为 2026-10-22，便于断言各种日期场景
        self.now = datetime(2026, 10, 22)

    def test_user_case_sep7(self):
        """用户实际案例：9月7日距今45天，应视为过期旧闻"""
        self.assertTrue(_is_stale_content("兑换码 9月7日 先说长期有效的通用码", self.now))

    def test_recent_date_not_stale(self):
        """7天前的日期在14天阈值内，不应视为过期"""
        self.assertFalse(_is_stale_content("10月15日发布的兑换码", self.now))

    def test_today_not_stale(self):
        """今天的日期不应视为过期"""
        self.assertFalse(_is_stale_content("10月22日最新兑换码", self.now))

    def test_future_date_not_stale(self):
        """未来的日期（如活动预告）不应视为过期"""
        self.assertFalse(_is_stale_content("11月15日活动开启，兑换码提前放送", self.now))

    def test_cross_year_december(self):
        """跨年场景：1月看到'12月15日'应按去年解释，距今26天 -> 过期"""
        now_jan = datetime(2027, 1, 10)
        self.assertTrue(_is_stale_content("12月15日发布的兑换码", now_jan))

    def test_cross_year_recent_not_stale(self):
        """跨年但很近：1月5日看到'12月30日'（6天前）不应视为过期"""
        now_jan = datetime(2027, 1, 5)
        self.assertFalse(_is_stale_content("12月30日发布的兑换码", now_jan))

    def test_full_date_past_year(self):
        """带年份的过去日期（2024年9月7日）应视为过期"""
        self.assertTrue(_is_stale_content("2024年9月7日 兑换码汇总", self.now))

    def test_full_date_this_year_recent(self):
        """带年份的今年近期日期不应视为过期"""
        self.assertFalse(_is_stale_content("2026年10月20日 兑换码发布", self.now))

    def test_year_only_past(self):
        """仅年份：非当年（2024年）应视为过期"""
        self.assertTrue(_is_stale_content("2024年发布的兑换码", self.now))

    def test_year_only_current(self):
        """仅年份：当年不应视为过期"""
        self.assertFalse(_is_stale_content("2026年最新兑换码", self.now))

    def test_iso_date_format(self):
        """ISO 格式日期 2026-09-07 距今45天应视为过期"""
        self.assertTrue(_is_stale_content("2026-09-07 发布兑换码", self.now))

    def test_no_date_not_stale(self):
        """没有日期的文本不受影响"""
        self.assertFalse(_is_stale_content("先说长期有效的通用码 HAPPY10000", self.now))

    def test_invalid_date_ignored(self):
        """非法日期（2月30日）应跳过，不误判"""
        self.assertFalse(_is_stale_content("2月30日兑换码", self.now))

    def test_empty_context(self):
        """空上下文不应视为过期"""
        self.assertFalse(_is_stale_content("", self.now))
        self.assertFalse(_is_stale_content(None, self.now))


class TestIsImageAttribution(unittest.TestCase):
    """测试 _is_image_attribution 图片署名过滤"""

    def _pos(self, text, code):
        """返回码在原文（大写后位置一致）中的起止位置"""
        start = text.upper().find(code.upper())
        return start, start + len(code)

    def test_user_case_getty(self):
        """用户实际案例：© Twenty47studio/Getty Images 是图片署名而非兑换码"""
        text = "纸应用 内藏山国立公园的秋景，韩国 © Twenty47studio/Getty Images 静水映斑斓"
        start, end = self._pos(text, "TWENTY47STUDIO")
        self.assertTrue(_is_image_attribution(text, start, end))

    def test_slash_getty(self):
        """XXX/Getty Images 格式应识别为署名"""
        text = "摄影师ZS123ABC/Getty Images 拍摄于景区"
        start, end = self._pos(text, "ZS123ABC")
        self.assertTrue(_is_image_attribution(text, start, end))

    def test_image_source_prefix(self):
        """'图片来源：XXX'应识别为署名"""
        text = "图片来源：PG2026PIC 仅供欣赏"
        start, end = self._pos(text, "PG2026PIC")
        self.assertTrue(_is_image_attribution(text, start, end))

    def test_copyright_symbol_before(self):
        """码前面紧邻版权符号 © 应识别为署名"""
        text = "封面图 © PHOTO2026X 作者所有"
        start, end = self._pos(text, "PHOTO2026X")
        self.assertTrue(_is_image_attribution(text, start, end))

    def test_normal_code_not_attribution(self):
        """正常兑换码上下文不应误判为署名"""
        text = "最新兑换码：ABC123DEF 快来领取"
        start, end = self._pos(text, "ABC123DEF")
        self.assertFalse(_is_image_attribution(text, start, end))


class TestRealWorldFalsePositives(unittest.TestCase):
    """
    复现用户遇到的两个误报场景，验证修复后的完整链路
    （日期动态生成，保证测试无论何时运行都稳定）
    """

    def setUp(self):
        self.parser_config = {
            "min_length": 6,
            "max_length": 20,
            "keywords": ["兑换码", "礼包码", "CDK", "福利码", "口令", "激活码"],
            "filter_words": [
                "HTTP", "HTTPS", "WWW", "COM", "CN", "NET", "ORG",
                "HTML", "PHP", "ASP", "JSP", "GIF", "PNG", "JPG",
                "HAPPY10000", "TWENTY47STUDIO",
            ],
        }

    def test_stale_date_code_filtered(self):
        """45天前日期附近的码不应被识别（用户案例：9月7日旧文中的码）"""
        d = datetime.now() - timedelta(days=45)
        text = (
            f"开心消消乐兑换码 {d.month}月{d.day}日 先说长期有效的通用码:OLDCODE99"
            "是最稳定的周年纪念码之一，输入就能领金币"
        )
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertNotIn("OLDCODE99", codes)

    def test_fresh_date_code_kept(self):
        """7天前日期附近的有效码应正常识别（不能误杀新码）"""
        d = datetime.now() - timedelta(days=7)
        text = f"{d.month}月{d.day}日发布的兑换码：FRESH12345 快来领取"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertIn("FRESH12345", codes)

    def test_getty_attribution_filtered(self):
        """Getty 图片署名不应被识别为兑换码（用户案例：TWENTY47STUDIO）"""
        text = "壁纸应用 内藏山国立公园的秋景，韩国 © Twenty47studio/Getty Images 静水映斑斓"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertNotIn("TWENTY47STUDIO", codes)

    def test_filter_words_block_known_invalid_codes(self):
        """filter_words 中用户确认无效的码（HAPPY10000）不应被识别"""
        text = "先说长期有效的通用码:HAPPY10000是最稳定的周年纪念码之一"
        result = parse_codes_from_text(text, self.parser_config)
        codes = [r["code"] for r in result]
        self.assertNotIn("HAPPY10000", codes)


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
