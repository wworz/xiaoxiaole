# -*- coding: utf-8 -*-
"""
每日报告与待发队列逻辑单元测试
运行方式: python -m pytest tests/test_daily_report.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# 添加上级目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class StateFileTestCase(unittest.TestCase):
    """将状态文件指向临时目录的测试基类"""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        temp_path = self._temp_dir.name
        self._orig_files = (
            main.SEEN_CODES_FILE, main.PUSH_LOG_FILE, main.PENDING_FILE,
        )
        main.PUSH_LOG_FILE = Path(temp_path) / "push_log.json"
        main.PENDING_FILE = Path(temp_path) / "pending_push.json"
        # 清理可能存在的环境变量，避免影响推送配置判断
        self._orig_env = {}
        for key in ("SERVERCHAN_KEY", "BARK_KEY", "PUSHPLUS_TOKEN"):
            self._orig_env[key] = os.environ.pop(key, None)

    def tearDown(self):
        main.SEEN_CODES_FILE, main.PUSH_LOG_FILE, main.PENDING_FILE = self._orig_files
        for key, val in self._orig_env.items():
            if val is not None:
                os.environ[key] = val
        self._temp_dir.cleanup()


class TestMergeCodes(unittest.TestCase):
    """测试 merge_codes 合并去重"""

    def test_merge_dedup(self):
        """待发队列与新码中重复的码只保留一个"""
        pending = [{"code": "ABC123", "source": "s1"}]
        new = [{"code": "abc123", "source": "s2"}, {"code": "XYZ789", "source": "s2"}]
        merged = main.merge_codes(pending, new)
        codes = [c["code"] for c in merged]
        self.assertEqual(codes, ["ABC123", "XYZ789"])
        # 重复时保留待发队列的记录
        self.assertEqual(merged[0]["source"], "s1")

    def test_merge_empty(self):
        """两个都为空时返回空列表"""
        self.assertEqual(main.merge_codes([], []), [])

    def test_merge_only_pending(self):
        """只有待发队列时原样返回"""
        pending = [{"code": "ABC123", "source": "s1"}]
        merged = main.merge_codes(pending, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["code"], "ABC123")


class TestPushLog(StateFileTestCase):
    """测试推送日志读写"""

    def test_append_and_load(self):
        log = main.load_push_log()
        self.assertEqual(log, [])
        main.append_push_log("new_codes", True, "Server酱: 成功", ["A1B2C3"])
        log = main.load_push_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["type"], "new_codes")
        self.assertTrue(log[0]["success"])
        self.assertEqual(log[0]["codes"], ["A1B2C3"])

    def test_keep_last_n(self):
        """日志只保留最近 PUSH_LOG_KEEP 条"""
        for i in range(main.PUSH_LOG_KEEP + 20):
            main.append_push_log("new_codes", True, f"ok{i}")
        log = main.load_push_log()
        self.assertEqual(len(log), main.PUSH_LOG_KEEP)
        self.assertEqual(log[-1]["detail"], f"ok{main.PUSH_LOG_KEEP + 19}")


class TestPendingCodes(StateFileTestCase):
    """测试待发队列读写"""

    def test_save_and_load(self):
        codes = [{"code": "ABC123", "source": "测试", "first_seen": "2026-10-18 12:00:00"}]
        self.assertTrue(main.save_pending_codes(codes))
        self.assertEqual(main.load_pending_codes(), codes)

    def test_clear(self):
        main.save_pending_codes([{"code": "ABC123"}])
        main.save_pending_codes([])
        self.assertEqual(main.load_pending_codes(), [])


class TestDailyReport(StateFileTestCase):
    """测试每日报告的分支判断"""

    CONFIG = {"push": {"serverchan_key": "fake_key_for_test"}}

    def test_report_sent_when_nothing_today(self):
        """当天无成功推送、无待发码 → 应发送日报并记录日志"""
        with mock.patch.object(main, "push_notification", return_value=(True, "ok")) as m:
            main.run_daily_report(self.CONFIG)
        m.assert_called_once()
        # 校验日报内容
        args, _ = m.call_args
        self.assertIn("没有发现新兑换码", args[1])
        # 日报结果写入日志
        log = main.load_push_log()
        self.assertEqual(log[-1]["type"], "daily_report")
        self.assertTrue(log[-1]["success"])

    def test_no_report_if_pushed_today(self):
        """当天已有成功推送 → 不发日报（省额度）"""
        main.append_push_log("new_codes", True, "ok", ["A1B2C3"])
        with mock.patch.object(main, "push_notification", return_value=(True, "ok")) as m:
            main.run_daily_report(self.CONFIG)
        m.assert_not_called()

    def test_no_report_if_pending_codes(self):
        """有暂存待发码（额度用完）→ 不发日报，等次日补发"""
        main.save_pending_codes([{"code": "ABC123", "source": "s"}])
        with mock.patch.object(main, "push_notification", return_value=(True, "ok")) as m:
            main.run_daily_report(self.CONFIG)
        m.assert_not_called()

    def test_failed_push_does_not_block_report(self):
        """当天的失败推送记录不算成功 → 仍应发送日报"""
        main.append_push_log("new_codes", False, "额度用完", ["A1B2C3"])
        with mock.patch.object(main, "push_notification", return_value=(True, "ok")) as m:
            main.run_daily_report(self.CONFIG)
        m.assert_called_once()

    def test_no_push_config_skip(self):
        """未配置推送渠道 → 跳过日报"""
        with mock.patch.object(main, "push_notification", return_value=(True, "ok")) as m:
            main.run_daily_report({})
        m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
