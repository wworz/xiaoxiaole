# 开心消消乐兑换码监控通知

自动监控开心消消乐官方及第三方渠道，发现新兑换码后通过手机推送通知，第一时间获取福利！

## ✨ 功能特性

- 🔍 **多渠道监控**：官方网站、微博、攻略站（18183/九游/4399）等多个来源
- 🎯 **智能识别**：自动识别兑换码/礼包码/CDK/福利码等，准确率高
- 🔄 **自动去重**：使用 `seen_codes.json` 记录已发现的码，只推送新码
- 📱 **多种推送**：支持 Server酱（微信）、Bark（iOS）、PushPlus（微信）
- ⏰ **定时检查**：GitHub Actions 每 30 分钟自动运行一次
- 🛡️ **异常容错**：单个渠道失败不影响整体，全部失败时推送异常提醒
- 🔒 **合规监控**：只抓取公开信息，不破解、不登录私人账号

## 📁 项目结构

```
.
├── main.py                    # 主程序入口
├── requirements.txt           # Python 依赖
├── config.example.yaml        # 配置文件示例
├── sources.yaml               # 监控源配置
├── seen_codes.json            # 已发现兑换码记录
├── README.md                  # 项目说明
├── tests/
│   └── test_parser.py         # 单元测试
└── .github/
    └── workflows/
        └── check.yml          # GitHub Actions 工作流
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip

### 本地运行

1. **克隆或下载项目**

   ```bash
   git clone <你的仓库地址>
   cd xxl-code-monitor
   ```

2. **安装依赖**

   ```bash
   pip install -r requirements.txt
   ```

3. **配置推送（可选，本地测试可跳过）**

   复制配置文件示例：

   ```bash
   cp config.example.yaml config.yaml
   ```

   编辑 `config.yaml` 填入推送密钥，或直接使用环境变量：

   ```bash
   export SERVERCHAN_KEY="你的Server酱Key"
   ```

4. **运行测试**

   ```bash
   # 单元测试
   python -m pytest tests/ -v

   # Dry-run 模式（抓取并打印，不推送、不更新状态）
   python main.py --dry-run

   # 测试推送（验证推送配置是否正确）
   python main.py --test-push
   ```

5. **正常运行**

   ```bash
   python main.py
   ```

## ☁️ GitHub Actions 部署

### 1. 上传代码到 GitHub

将项目推送到你的 GitHub 仓库。

### 2. 配置 Secrets

在仓库的 `Settings → Secrets and variables → Actions → New repository secret` 中添加：

| Secret 名称 | 说明 | 是否必需 |
|------------|------|---------|
| `SERVERCHAN_KEY` | Server酱 SendKey | 推荐 |
| `BARK_KEY` | Bark 推送 Key | 可选 |
| `PUSHPLUS_TOKEN` | PushPlus Token | 可选 |

> 至少配置一个推送渠道才能收到通知。

### 3. 启用工作流

推送代码后，GitHub Actions 会自动识别 `.github/workflows/check.yml`。

- 到 `Actions` 页面确认工作流已启用
- 可以点击 `Run workflow` 手动触发一次测试

### 4. 工作流说明

- **定时触发**：每 30 分钟（UTC 时间 `*/30 * * * *`）
- **手动触发**：在 Actions 页面点击 `Run workflow`
- **自动提交**：每次运行后自动提交 `seen_codes.json`（带 `[skip ci]` 避免循环触发）

## 📱 推送渠道配置

### Server酱（推荐，微信推送）

1. 访问 [Server酱官网](https://sct.ftqq.com/)
2. 用微信扫码登录
3. 复制 `SendKey`
4. 设置环境变量或写入配置：
   ```bash
   export SERVERCHAN_KEY="SCTxxxxx"
   ```

### Bark（iOS 用户）

1. App Store 搜索 "Bark" 下载安装
2. 打开 App 复制你的设备 Key
3. 设置环境变量：
   ```bash
   export BARK_KEY="你的Key"
   ```

### PushPlus

1. 访问 [PushPlus官网](https://www.pushplus.plus/)
2. 微信扫码登录
3. 在「发送消息」页面获取 Token
4. 设置环境变量：
   ```bash
   export PUSHPLUS_TOKEN="你的Token"
   ```

## ⚙️ 配置说明

### 修改检查频率

编辑 `.github/workflows/check.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '*/30 * * * *'  # 每 30 分钟
```

> 注意：GitHub Actions 使用 UTC 时间。

### 增删监控源

编辑 `sources.yaml`，每个源的配置项：

| 字段 | 说明 | 示例 |
|------|------|------|
| `name` | 源名称 | "开心消消乐官网" |
| `url` | 监控地址 | "https://..." |
| `type` | 类型：html / rss | "html" |
| `selector` | CSS 选择器（可选） | ".news-list" |
| `enabled` | 是否启用 | true / false |
| `note` | 备注说明 | "备用源" |

新增一个源：

```yaml
- name: "你的自定义源名称"
  url: "https://example.com/xxx"
  type: "html"
  enabled: true
  selector: ""
```

### 兑换码识别规则

配置文件中 `parser` 部分可调：

- `min_length` / `max_length`：码长度范围
- `keywords`：关键词列表（匹配这些词附近的码）
- `filter_words`：需要过滤的无意义词

## 🧪 命令行参数

```bash
# 正常运行（抓取、去重、推送、更新状态）
python main.py

# Dry-run 模式：只抓取和打印，不推送、不更新 seen_codes.json
python main.py --dry-run

# 测试推送：发一条测试通知，验证推送配置
python main.py --test-push
```

## 📊 seen_codes.json 说明

存储已发现的兑换码记录，每条记录包含：

```json
{
  "code": "ABC123DEF",
  "source": "开心消消乐官网",
  "first_seen": "2024-01-01 12:00:00",
  "url": "https://...",
  "raw_text": "原文片段..."
}
```

GitHub Actions 会在每次运行后自动提交更新此文件。

## ❓ 常见问题

### Q: 为什么收不到推送？

1. 检查 Secrets 是否正确配置
2. 运行 `python main.py --test-push` 测试推送
3. 查看 GitHub Actions 运行日志排查错误

### Q: 识别不出兑换码怎么办？

1. 先使用 `--dry-run` 模式查看是否抓到了页面内容
2. 检查页面是否有反爬机制（可尝试调整 User-Agent）
3. 可能是页面改版，需要更新 CSS 选择器或更换监控源

### Q: 可以监控更多渠道吗？

可以，编辑 `sources.yaml` 添加新的源即可。支持 HTML 网页和 RSS 两种类型。

### Q: 推送频率可以调整吗？

可以，修改 `.github/workflows/check.yml` 中的 cron 表达式。注意 GitHub Actions 免费版有运行时间限制。

### Q: 怎么重置已发现的兑换码？

清空 `seen_codes.json` 内容，改为 `[]` 即可。注意这会导致所有码都被当作新码重新推送。

### Q: 单个渠道失败会影响其他渠道吗？

不会。每个渠道独立处理，单个失败只记录日志，不影响其他渠道的正常监控。如果所有渠道都失败，会推送"监控异常"提醒。

## 📋 用户需要手动完成的步骤

- [ ] 1. 注册 Server酱 / Bark / PushPlus 账号，获取推送密钥
- [ ] 2. 将项目推送到自己的 GitHub 仓库
- [ ] 3. 在 GitHub 仓库 Settings 中配置 Secrets（`SERVERCHAN_KEY` 等）
- [ ] 4. 确认 GitHub Actions 已启用并可正常运行
- [ ] 5. （可选）根据需要修改 `sources.yaml` 中的监控源
- [ ] 6. （可选）调整检查频率（修改 `check.yml` 中的 cron 表达式）

## 📝 免责声明

本项目仅用于学习交流，监控内容均为互联网公开信息。请遵守相关网站的使用条款和 robots.txt 协议，合理设置检查频率，避免对目标网站造成压力。

## 📄 License

MIT License
