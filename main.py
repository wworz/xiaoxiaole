#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开心消消乐兑换码监控通知
自动监控官方及第三方渠道，发现新兑换码后推送通知
"""

import os
import re
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

# ==========================================
# 基础配置
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.yaml"
CONFIG_EXAMPLE_FILE = BASE_DIR / "config.example.yaml"
SOURCES_FILE = BASE_DIR / "sources.yaml"
SEEN_CODES_FILE = BASE_DIR / "seen_codes.json"
PUSH_LOG_FILE = BASE_DIR / "push_log.json"
PENDING_FILE = BASE_DIR / "pending_push.json"

# 北京时间（Actions 运行环境为 UTC，统一按北京时间记录和判断）
BJ_TZ = timezone(timedelta(hours=8))


def now_bj():
    """返回当前北京时间"""
    return datetime.now(BJ_TZ)


def bj_str():
    """返回当前北京时间字符串，格式 YYYY-MM-DD HH:MM:SS"""
    return now_bj().strftime("%Y-%m-%d %H:%M:%S")

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("xxl_monitor")


# ==========================================
# 配置加载
# ==========================================

def load_config():
    """加载配置文件，优先使用 config.yaml，不存在则使用示例配置"""
    config_path = CONFIG_FILE if CONFIG_FILE.exists() else CONFIG_EXAMPLE_FILE
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info(f"已加载配置文件: {config_path.name}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return {}


def load_sources():
    """加载监控源配置"""
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        sources = data.get("sources", [])
        # 只保留启用的源
        enabled_sources = [s for s in sources if s.get("enabled", False)]
        logger.info(f"已加载 {len(enabled_sources)} 个启用的监控源（共 {len(sources)} 个）")
        return enabled_sources
    except Exception as e:
        logger.error(f"加载监控源配置失败: {e}")
        return []


# ==========================================
# 兑换码解析（含时效与署名过滤）
# ==========================================

# 上下文中出现距今天数超过该值的日期时，视为旧内容（兑换码通常有时效）
STALE_DATE_MAX_AGE_DAYS = 14
# "X月X日"无年份时，若按今年算在未来超过该天数，则按去年重新解释（跨年旧文场景）
STALE_DATE_FUTURE_TOLERANCE_DAYS = 45
# 时效检查的上下文窗口：码前后各取这么多字符找日期
STALE_CONTEXT_WINDOW = 50


def _is_stale_content(context, now=None, max_age_days=STALE_DATE_MAX_AGE_DAYS):
    """
    检查上下文中是否包含过期日期（如旧文章中的"9月7日"）
    返回 True 表示内容疑似旧闻，其中的兑换码应丢弃

    支持的日期格式：
    - 带年份：2024年9月7日 / 2024-09-07 / 2024.9.7 / 2024/9/7
    - 仅年份：2024年（非当年直接视为过期）
    - 月日：9月7日（默认当年；若按今年算远在未来，按去年重新解释，处理跨年旧文）
    """
    if not context:
        return False
    if now is None:
        now = now_bj()
    # 统一用无时区的 datetime 比较，避免 offset-naive/aware 相减报错
    now_naive = now.replace(tzinfo=None)

    # 带年份的完整日期
    full_date_pattern = r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*[日号]?"
    for m in re.finditer(full_date_pattern, context):
        try:
            date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue  # 非法日期（如2月30日），跳过
        if (now_naive - date).days > max_age_days:
            return True

    # 仅年份：非当年的年份视为过期
    for m in re.finditer(r"(20\d{2})\s*年", context):
        if int(m.group(1)) != now_naive.year:
            return True

    # 月日格式（无年份，需跨年推断）
    for m in re.finditer(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", context):
        month, day = int(m.group(1)), int(m.group(2))
        try:
            date_this_year = datetime(now_naive.year, month, day)
        except ValueError:
            continue
        future_days = (date_this_year - now_naive).days
        if future_days > STALE_DATE_FUTURE_TOLERANCE_DAYS:
            # 按今年算太遥远 -> 很可能是去年的旧文（如1月看到"12月20日"）
            try:
                date_last_year = datetime(now_naive.year - 1, month, day)
            except ValueError:
                continue
            if (now_naive - date_last_year).days > max_age_days:
                return True
        elif (now_naive - date_this_year).days > max_age_days:
            return True

    return False


def _is_image_attribution(text, start, end):
    """
    判断匹配到的串是否是图片版权署名（如 "© Twenty47studio/Getty Images"）
    图片说明文字中的摄影师/机构名常被误判为兑换码
    """
    ctx_before = text[max(0, start - 15):start]
    ctx_after = text[end:min(len(text), end + 20)]
    combined = (ctx_before + ctx_after).upper()

    # 前文含版权符号 ©（"© 作者/机构"署名格式）
    if "©" in ctx_before:
        return True

    # 紧邻 Getty 图片机构署名，如 "Twenty47studio/Getty Images"
    if "GETTY" in combined:
        return True

    # 前文是图片来源标注，如 "图片来源：XXX"
    if "图片来源" in ctx_before:
        return True

    return False


def parse_codes_from_text(text, parser_config=None):
    """
    从文本中解析兑换码
    返回列表：[{"code": "XXX", "raw_text": "原文片段"}, ...]
    """
    if not text:
        return []

    if parser_config is None:
        parser_config = {}

    min_len = parser_config.get("min_length", 6)
    max_len = parser_config.get("max_length", 20)
    keywords = parser_config.get("keywords", ["兑换码", "礼包码", "CDK", "福利码", "口令", "激活码"])
    filter_words = [w.upper() for w in parser_config.get("filter_words", [])]

    results = []
    seen_in_this_text = set()

    # ---- 策略一：关键词附近匹配（优先，准确率高）----
    keyword_pattern = (
        r"(?i)(?:" + "|".join(re.escape(k) for k in keywords) + r")"
        r"[：:\s]*"
        r"([A-Z0-9]{" + str(min_len) + r"," + str(max_len) + r"})"
    )
    for match in re.finditer(keyword_pattern, text):
        code = match.group(1).upper()
        if _is_valid_code(code, filter_words, min_len, max_len) and code not in seen_in_this_text:
            code_start, code_end = match.start(1), match.end(1)
            # 上下文含过期日期 -> 旧闻中的码，跳过
            ctx = text[max(0, code_start - STALE_CONTEXT_WINDOW):min(len(text), code_end + STALE_CONTEXT_WINDOW)]
            if _is_stale_content(ctx):
                logger.debug(f"  [过滤] {code}: 上下文含过期日期，跳过")
                continue
            # 疑似图片版权署名 -> 跳过
            if _is_image_attribution(text, code_start, code_end):
                logger.debug(f"  [过滤] {code}: 疑似图片版权署名，跳过")
                continue
            # 获取关键词前后的上下文作为 raw_text
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            raw_text = text[start:end].strip()
            results.append({"code": code, "raw_text": raw_text})
            seen_in_this_text.add(code)

    # ---- 策略二：全文扫描独立码（补充召回，更严格）----
    # 全文扫描的码要求更长（至少 8 位），减少误报
    scan_min_len = max(min_len, 8)
    code_pattern = r"(?<![A-Z0-9])([A-Z0-9]{" + str(scan_min_len) + r"," + str(max_len) + r"})(?![A-Z0-9])"
    for match in re.finditer(code_pattern, text.upper()):
        code = match.group(1)
        if (
            _is_valid_code(code, filter_words, scan_min_len, max_len)
            and not _is_likely_official_number(text, match.start(), match.end())
            and not _is_image_attribution(text, match.start(), match.end())
            and code not in seen_in_this_text
        ):
            # 上下文含过期日期 -> 旧闻中的码，跳过
            ctx = text[max(0, match.start() - STALE_CONTEXT_WINDOW):min(len(text), match.end() + STALE_CONTEXT_WINDOW)]
            if _is_stale_content(ctx):
                logger.debug(f"  [过滤] {code}: 上下文含过期日期，跳过")
                continue
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            raw_text = text[start:end].strip()
            results.append({"code": code, "raw_text": raw_text})
            seen_in_this_text.add(code)

    return results


def _is_likely_official_number(text, start, end):
    """
    判断匹配到的串是否是备案号/证件号/文号等官方编号（而非兑换码）
    通过检查前后文的中文关键字来判断
    """
    # 获取码前后各 3 个字符的上下文
    ctx_before = text[max(0, start - 3):start]
    ctx_after = text[end:min(len(text), end + 3)]

    # 前面有这些字 -> 很可能是官方编号
    prefix_indicators = [
        "字", "第", "备", "证", "许", "准", "批", "号", "文", "网",
        "游", "版", "出", "发", "管", "监", "审", "核", "验", "登",
        "注", "册", "编", "序", "代", "编",
    ]

    # 后面有这些字 -> 很可能是官方编号
    suffix_indicators = [
        "号", "字", "证", "书", "件", "批", "准", "许", "备",
    ]

    for indicator in prefix_indicators:
        if ctx_before.endswith(indicator):
            return True

    for indicator in suffix_indicators:
        if ctx_after.startswith(indicator):
            return True

    # 检查"XX字XXX号"这种典型文号格式
    # 在更大范围内查找
    wide_before = text[max(0, start - 10):start]
    wide_after = text[end:min(len(text), end + 5)]

    # 前面有"字"且后面有"号" → 文号格式
    if "字" in wide_before and wide_after.startswith("号"):
        return True

    # 前面有"第"且后面有"号" → 第XXX号格式
    if "第" in wide_before and wide_after.startswith("号"):
        return True

    # 含 ICP 备案号特征
    if "ICP" in text[max(0, start - 5):end].upper():
        return True

    return False


def _is_valid_code(code, filter_words, min_len, max_len):
    """判断一个字符串是否是有效兑换码"""
    code_upper = code.upper()

    # 长度检查
    if len(code_upper) < min_len or len(code_upper) > max_len:
        return False

    # 必须同时包含字母和数字（纯数字或纯字母的不太可能是兑换码）
    has_letter = bool(re.search(r"[A-Z]", code_upper))
    has_digit = bool(re.search(r"[0-9]", code_upper))
    if not (has_letter and has_digit):
        return False

    # 过滤无意义词
    if code_upper in filter_words:
        return False

    # 过滤常见备案号/证件号前缀模式
    # 如: ICP 开头的
    if code_upper.startswith("ICP"):
        return False

    # 纯数字+单字母组合且字母在末尾的（如 123456A）疑似证件号
    if re.match(r"^\d+[A-Z]$", code_upper) and len(code_upper) >= 7:
        return False

    return True


# ==========================================
# 网页抓取
# ==========================================

def fetch_html(url, config=None):
    """抓取网页内容，返回 HTML 文本，失败返回 None"""
    if config is None:
        config = {}

    timeout = config.get("request_timeout", 15)
    user_agent = config.get(
        "user_agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()

        # 处理编码
        if response.encoding is None or response.encoding.lower() == "iso-8859-1":
            # 尝试从 content-type 或 html 中检测
            response.encoding = response.apparent_encoding or "utf-8"

        return response.text
    except requests.exceptions.Timeout:
        logger.warning(f"请求超时: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"请求失败 [{url}]: {e}")
        return None
    except Exception as e:
        logger.warning(f"抓取异常 [{url}]: {e}")
        return None


def fetch_rss(url, config=None):
    """抓取 RSS 内容，返回合并后的文本"""
    html = fetch_html(url, config)
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        # RSS 通常是 item 节点，提取 title 和 description
        items = soup.find_all("item")
        if not items:
            # 也可能是 atom 格式的 entry
            items = soup.find_all("entry")

        texts = []
        for item in items:
            title = item.find("title")
            desc = item.find("description")
            if not desc:
                desc = item.find("summary")
            if not desc:
                desc = item.find("content")

            if title:
                texts.append(title.get_text())
            if desc:
                texts.append(desc.get_text())

        return "\n".join(texts) if texts else None
    except Exception as e:
        logger.warning(f"RSS 解析失败 [{url}]: {e}")
        return None


def extract_text_from_html(html, selector=None):
    """从 HTML 中提取纯文本"""
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")

        # 移除 script、style、nav、footer 等无关元素
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "canvas"]):
            tag.decompose()

        if selector:
            target = soup.select_one(selector)
            if target:
                return target.get_text(separator="\n", strip=True)

        # 默认提取 body 文本
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n", strip=True)

        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        logger.warning(f"HTML 文本提取失败: {e}")
        return ""


# ==========================================
# 去重与状态存储
# ==========================================

def load_seen_codes():
    """加载已发现的兑换码"""
    if not SEEN_CODES_FILE.exists():
        return []

    try:
        with open(SEEN_CODES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.error(f"读取 seen_codes.json 失败: {e}")
        return []


def save_seen_codes(codes_list):
    """保存已发现的兑换码"""
    try:
        with open(SEEN_CODES_FILE, "w", encoding="utf-8") as f:
            json.dump(codes_list, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存 {len(codes_list)} 条兑换码记录到 {SEEN_CODES_FILE.name}")
        return True
    except Exception as e:
        logger.error(f"保存 seen_codes.json 失败: {e}")
        return False


def get_seen_code_set(seen_list):
    """从列表中提取已见过的码集合（用于快速查找）"""
    return {item["code"].upper() for item in seen_list if isinstance(item, dict) and "code" in item}


# ==========================================
# 推送日志与待发队列
# ==========================================

PUSH_LOG_KEEP = 100  # push_log.json 最多保留的记录条数


def load_push_log():
    """加载推送日志"""
    if not PUSH_LOG_FILE.exists():
        return []
    try:
        with open(PUSH_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"读取 push_log.json 失败: {e}")
        return []


def append_push_log(entry_type, success, detail, codes=None):
    """
    追加一条推送日志
    entry_type: new_codes(新码推送) / anomaly(异常提醒) / daily_report(每日报告)
    """
    log = load_push_log()
    log.append({
        "time": bj_str(),
        "type": entry_type,
        "success": bool(success),
        "detail": str(detail)[:200],
        "codes": codes or [],
    })
    # 只保留最近 N 条，避免文件无限增长
    log = log[-PUSH_LOG_KEEP:]
    try:
        with open(PUSH_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存 push_log.json 失败: {e}")


def load_pending_codes():
    """加载待发队列（此前推送失败暂存的兑换码）"""
    if not PENDING_FILE.exists():
        return []
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"读取 pending_push.json 失败: {e}")
        return []


def save_pending_codes(codes_list):
    """保存待发队列"""
    try:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(codes_list, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存 pending_push.json 失败: {e}")
        return False


def merge_codes(pending_codes, new_codes):
    """合并待发队列与新发现的码，按码值去重（待发队列的记录优先保留）"""
    merged = []
    codes_seen = set()
    for item in list(pending_codes) + list(new_codes):
        code = item["code"].upper()
        if code not in codes_seen:
            merged.append(item)
            codes_seen.add(code)
    return merged


# ==========================================
# 推送通知
# ==========================================

def get_push_config(config):
    """从配置和环境变量中获取推送密钥"""
    push_config = config.get("push", {}) if isinstance(config, dict) else {}

    return {
        "serverchan_key": os.environ.get("SERVERCHAN_KEY") or push_config.get("serverchan_key", ""),
        "bark_key": os.environ.get("BARK_KEY") or push_config.get("bark_key", ""),
        "bark_url": push_config.get("bark_url", "https://api.day.app"),
        "pushplus_token": os.environ.get("PUSHPLUS_TOKEN") or push_config.get("pushplus_token", ""),
    }


def push_notification(title, content, push_config):
    """
    推送通知，尝试所有可用渠道
    返回: (bool 是否成功, str 结果信息)
    """
    results = []
    any_success = False

    # Server酱
    if push_config.get("serverchan_key"):
        ok, msg = push_serverchan(title, content, push_config["serverchan_key"])
        results.append(f"Server酱: {'成功' if ok else '失败 - ' + msg}")
        if ok:
            any_success = True

    # Bark
    if push_config.get("bark_key"):
        ok, msg = push_bark(title, content, push_config["bark_key"], push_config.get("bark_url", "https://api.day.app"))
        results.append(f"Bark: {'成功' if ok else '失败 - ' + msg}")
        if ok:
            any_success = True

    # PushPlus
    if push_config.get("pushplus_token"):
        ok, msg = push_pushplus(title, content, push_config["pushplus_token"])
        results.append(f"PushPlus: {'成功' if ok else '失败 - ' + msg}")
        if ok:
            any_success = True

    if not results:
        return False, "未配置任何推送渠道"

    return any_success, "; ".join(results)


def push_serverchan(title, content, key):
    """Server酱推送"""
    try:
        url = f"https://sctapi.ftqq.com/{key}.send"
        data = {
            "title": title[:32],  # Server酱标题限制32字
            "desp": content,
        }
        response = requests.post(url, data=data, timeout=10)
        result = response.json()
        if result.get("code") == 0:
            logger.info("Server酱推送成功")
            return True, "ok"
        else:
            logger.warning(f"Server酱推送失败: {result.get('message', result)}")
            return False, result.get("message", str(result))
    except Exception as e:
        logger.warning(f"Server酱推送异常: {e}")
        return False, str(e)


def push_bark(title, content, key, base_url="https://api.day.app"):
    """Bark 推送"""
    try:
        url = f"{base_url.rstrip('/')}/{key}/{title}/{content}"
        response = requests.get(url, timeout=10)
        result = response.json()
        if result.get("code") == 200:
            logger.info("Bark 推送成功")
            return True, "ok"
        else:
            logger.warning(f"Bark 推送失败: {result.get('message', result)}")
            return False, result.get("message", str(result))
    except Exception as e:
        logger.warning(f"Bark 推送异常: {e}")
        return False, str(e)


def push_pushplus(title, content, token):
    """PushPlus 推送"""
    try:
        url = "https://www.pushplus.plus/send"
        data = {
            "token": token,
            "title": title,
            "content": content.replace("\n", "<br>"),
            "template": "html",
        }
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        if result.get("code") == 200:
            logger.info("PushPlus 推送成功")
            return True, "ok"
        else:
            logger.warning(f"PushPlus 推送失败: {result.get('msg', result)}")
            return False, result.get("msg", str(result))
    except Exception as e:
        logger.warning(f"PushPlus 推送异常: {e}")
        return False, str(e)


# ==========================================
# 核心业务逻辑
# ==========================================

def run_monitor(config, sources, dry_run=False):
    """
    执行一次完整的监控流程
    返回: 新发现的兑换码列表
    """
    logger.info("=" * 50)
    logger.info("开始执行兑换码监控检查")
    logger.info("=" * 50)

    parser_config = config.get("parser", {}) if isinstance(config, dict) else {}

    # 加载已发现的码
    seen_list = load_seen_codes()
    seen_set = get_seen_code_set(seen_list)
    logger.info(f"已记录兑换码: {len(seen_set)} 个")

    # 本轮新发现的码
    new_codes = []
    new_codes_set = set()
    failed_sources = []

    for source in sources:
        name = source.get("name", "未知来源")
        url = source.get("url", "")
        source_type = source.get("type", "html")
        selector = source.get("selector", "")

        logger.info(f"\n--- 正在检查: {name} ---")

        # 抓取内容
        if source_type == "rss":
            content_text = fetch_rss(url, config)
        else:
            html = fetch_html(url, config)
            if html:
                content_text = extract_text_from_html(html, selector)
            else:
                content_text = None

        if content_text is None:
            logger.warning(f"抓取失败: {name}")
            failed_sources.append(name)
            continue

        # 解析兑换码
        found_codes = parse_codes_from_text(content_text, parser_config)
        logger.info(f"解析到 {len(found_codes)} 个可能的兑换码")

        # 去重
        for item in found_codes:
            code = item["code"].upper()
            if code not in seen_set and code not in new_codes_set:
                new_code_entry = {
                    "code": code,
                    "source": name,
                    "first_seen": bj_str(),
                    "url": url,
                    "raw_text": item["raw_text"][:200],  # 限制长度
                }
                new_codes.append(new_code_entry)
                new_codes_set.add(code)
                logger.info(f"  [新码] {code} - 来源: {name}")

    # 汇总结果
    logger.info("\n" + "=" * 50)
    logger.info(f"检查完成: 共发现 {len(new_codes)} 个新兑换码")

    if failed_sources:
        logger.warning(f"有 {len(failed_sources)} 个源抓取失败: {', '.join(failed_sources)}")

    # Dry-run 模式：不推送、不保存
    if dry_run:
        logger.info("Dry-run 模式：不推送通知，不更新状态文件")
        for code_info in new_codes:
            logger.info(f"  {code_info['code']} | {code_info['source']} | {code_info['url']}")
        pending = load_pending_codes()
        if pending:
            logger.info(f"另有 {len(pending)} 个此前推送失败暂存的码，正式运行时会一并推送")
        return new_codes, failed_sources

    # 推送通知
    push_cfg = get_push_config(config)
    push_configured = any([push_cfg.get("serverchan_key"), push_cfg.get("bark_key"), push_cfg.get("pushplus_token")])

    pending_codes = load_pending_codes()

    if new_codes or pending_codes:
        # 合并本轮新码与待发队列（此前因额度用完等原因没发出去的）
        to_push = merge_codes(pending_codes, new_codes)
        if pending_codes:
            logger.info(f"待发队列中有 {len(pending_codes)} 个码，与新码合并后共 {len(to_push)} 个待推送")

        if push_configured:
            title, content = build_push_message(to_push)
            ok, msg = push_notification(title, content, push_cfg)
            logger.info(f"推送结果: {msg}")
            append_push_log("new_codes", ok, msg, [c["code"] for c in to_push])

            if ok:
                if pending_codes:
                    logger.info("推送成功，已清空待发队列")
                    save_pending_codes([])
            else:
                # 推送失败（如免费额度用完），暂存起来，下次运行时自动重试（额度次日重置后即可发出）
                save_pending_codes(to_push)
                logger.warning(f"推送失败，{len(to_push)} 个码已暂存到待发队列，将在下次运行时重试")
        else:
            logger.warning("未配置任何推送渠道，跳过推送")

        # 更新状态文件（无论推送成败都记录到 seen，避免重复识别；没发出去的码保留在待发队列中）
        if new_codes:
            seen_list.extend(new_codes)
            save_seen_codes(seen_list)
    elif failed_sources and push_configured:
        # 全部失败时推送异常提醒
        if len(failed_sources) == len(sources):
            title = "⚠️ 开心消消乐兑换码监控异常"
            content = (
                f"所有监控源均抓取失败，请检查网络或页面是否改版。\n\n"
                f"失败源数量: {len(failed_sources)}/{len(sources)}\n"
                f"失败源: {', '.join(failed_sources)}\n\n"
                f"检查时间: {bj_str()}"
            )
            ok, msg = push_notification(title, content, push_cfg)
            logger.info(f"异常推送结果: {msg}")
            append_push_log("anomaly", ok, msg)

    return new_codes, failed_sources


def build_push_message(new_codes):
    """构建推送消息内容"""
    count = len(new_codes)

    title = f"🎮 开心消消乐新兑换码 x{count}"

    lines = [
        f"发现 **{count}** 个新兑换码，请尽快兑换！\n",
        "---",
    ]

    for i, code_info in enumerate(new_codes, 1):
        lines.append(f"**{i}. {code_info['code']}**")
        lines.append(f"- 来源: {code_info['source']}")
        lines.append(f"- 发现时间: {code_info['first_seen']}")
        lines.append(f"- 原文链接: {code_info['url']}")
        if code_info.get("raw_text"):
            lines.append(f"- 原文片段: {code_info['raw_text']}")
        lines.append("")

    lines.append("---")
    lines.append("⏰ 请尽快使用兑换码，通常有有效期限制。")

    content = "\n".join(lines)

    return title, content


def test_push(config):
    """测试推送功能"""
    push_cfg = get_push_config(config)

    title = "🧪 开心消消乐兑换码监控 - 测试消息"
    content = (
        "这是一条测试消息。\n\n"
        "如果您收到了这条消息，说明推送配置已正确设置。\n\n"
        f"测试时间: {bj_str()}\n\n"
        "---\n"
        "开心消消乐兑换码监控项目"
    )

    ok, msg = push_notification(title, content, push_cfg)
    logger.info(f"测试推送结果: {msg}")
    return ok


def run_daily_report(config):
    """
    每日报告（由 Actions 在北京时间 23:30 触发）：
    - 当天已有成功推送（新码/异常提醒/补发）→ 用户已知监控在运行，不再发日报，省额度
    - 当天没有成功推送，但有暂存的待发码（免费额度用完）→ 不发日报，待发码次日额度重置后自动补发
    - 当天没有任何成功推送、也没有待发码 → 说明没抓到新码，发一条"今日无新码"日报
    """
    logger.info("=" * 50)
    logger.info("执行每日报告检查")
    logger.info("=" * 50)

    today = bj_str()[:10]
    push_log = load_push_log()
    pending_codes = load_pending_codes()

    # 统计当天（北京时间）成功的推送记录
    today_success = [
        e for e in push_log
        if e.get("success") and str(e.get("time", "")).startswith(today)
    ]

    if today_success:
        logger.info(f"今天已有 {len(today_success)} 次成功推送，无需发送日报")
        return

    if pending_codes:
        logger.info(
            f"存在 {len(pending_codes)} 个暂存待发的兑换码（推送免费额度可能已用完），"
            "跳过日报，待发码将在额度重置后自动补发"
        )
        return

    # 今天没有成功推送、也没有待发码 → 说明没抓到新码，发送日报
    push_cfg = get_push_config(config)
    push_configured = any([push_cfg.get("serverchan_key"), push_cfg.get("bark_key"), push_cfg.get("pushplus_token")])
    if not push_configured:
        logger.warning("未配置任何推送渠道，跳过日报")
        return

    title = "📊 开心消消乐监控日报"
    content = (
        f"今天（{today}）没有发现新兑换码，监控运行正常。\n\n"
        f"程序仍在持续监控中，一有新码会立刻推送。\n\n"
        f"报告时间: {bj_str()}\n\n"
        "---\n"
        "开心消消乐兑换码监控项目"
    )
    ok, msg = push_notification(title, content, push_cfg)
    logger.info(f"日报推送结果: {msg}")
    append_push_log("daily_report", ok, msg)


# ==========================================
# 命令行入口
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="开心消消乐兑换码监控通知")
    parser.add_argument("--dry-run", action="store_true", help="抓取并打印识别结果，不推送，不更新状态")
    parser.add_argument("--test-push", action="store_true", help="发送一条测试通知，验证推送配置")
    parser.add_argument("--daily-report", action="store_true", help="每日报告模式：当天没有推送时发送一条日报，不执行抓取")
    args = parser.parse_args()

    # 加载配置
    config = load_config()

    # 设置日志级别
    log_level = config.get("log_level", "INFO")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 测试推送模式
    if args.test_push:
        logger.info("执行推送测试...")
        test_push(config)
        return

    # 每日报告模式（不需要监控源）
    if args.daily_report:
        run_daily_report(config)
        return

    # 加载监控源
    sources = load_sources()
    if not sources:
        logger.error("没有可用的监控源，请检查 sources.yaml 配置")
        sys.exit(1)

    # 执行监控
    new_codes, failed_sources = run_monitor(config, sources, dry_run=args.dry_run)

    # 输出摘要
    if args.dry_run:
        print(f"\n=== Dry-run 结果 ===")
        print(f"新兑换码: {len(new_codes)} 个")
        for code_info in new_codes:
            print(f"  {code_info['code']} | {code_info['source']}")
        if failed_sources:
            print(f"失败源: {len(failed_sources)} 个")
            for s in failed_sources:
                print(f"  - {s}")


if __name__ == "__main__":
    main()
