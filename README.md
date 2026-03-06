# Context Probe

## 这个工具是用来做什么的？

探测 LLM 模型的**实际可用上下文窗口大小**，区分理论规格和实际限制。

支持 Anthropic 和 OpenAI 兼容的服务商（OpenAI、DeepSeek、Kimi 等），通过真实 API 调用和二分查找，精确测量模型实际支持的最大 token 数量。

**使用场景：** 当你使用 API 代理或第三方服务时，它们宣称支持某个上下文长度，但实际可能有限制——这个工具帮你验证真实情况。

## 安装

### 一键安装（推荐）

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/hachimi02/context_probe/main/install_from_github.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/hachimi02/context_probe/main/install_from_github.bat | iex
```

安装脚本会提示选择安装位置：
1. 当前项目 (`.claude/skills/`)
2. 用户目录 (`~/.claude/skills/`)
3. 自定义路径

### 手动安装

下载以下文件到你的技能目录：
- `SKILL.md` — 技能定义
- `context_probe.py` — 主程序
- `context_config.jsonc.template` — 配置模板

或使用安装脚本：
```bash
# 下载并运行安装脚本
./install_from_github.sh

# 指定版本/分支
./install_from_github.sh dev
```

## 快速开始

```bash
# 使用配置文件（推荐）
python context_probe.py --config context_config.json

# 交互式输入（旧格式）
python context_probe.py
```

## 配置

复制 `context_config.jsonc.template` 为 `context_config.jsonc`，填入 API keys。

**配置文件查找顺序：**
1. 如果指定 `--config`，使用指定的文件
2. 否则优先使用 `context_config.jsonc`
3. 不存在则使用 `context_config.json`

**推荐使用 `.jsonc` 格式**，可以添加注释说明配置项。

### 新格式（推荐）

```json
{
  "report_file": "context_report.json",
  "providers": {
    "anthropic": {
      "type": "anthropic",
      "api_key": "sk-ant-...",
      "base_url": "",
      "headers": {},
      "models": [
        { "name": "claude-sonnet-4-6", "expected_context": 1000000 }
      ]
    },
    "deepseek": {
      "type": "openai",
      "api_key": "sk-...",
      "base_url": "https://api.deepseek.com",
      "models": [
        { "name": "deepseek-chat", "expected_context": 128000 }
      ]
    }
  }
}
```

**字段说明：**
- `type` — `"anthropic"` 或 `"openai"`（OpenAI 兼容）
- `api_key` — Provider API key
- `base_url` — API 端点（留空使用默认）
- `headers` — 可选的自定义请求头（如 Claude Code 识别头）
- `models` — 模型列表，`expected_context` 用于计算测试内容大小

**启用 Claude 1M 上下文窗口：**

根据 [Claude 官方文档](https://platform.claude.com/docs/zh-CN/build-with-claude/context-windows#1-m-token)，要使用 1M token 上下文窗口，需要添加 beta header：

```json
"headers": {
  "anthropic-beta": "context-1m-2025-08-07"
}
```

**注意：** 默认情况下 Claude Sonnet 4.6 使用 200K 上下文窗口，只有添加此 header 才能启用 1M 上下文。

### 旧格式（向后兼容）

顶层 `api_key`、`base_url`、`models` 仍然支持，会被包装为单个 Anthropic provider。

## 工作原理

### 核心发现

1. **count_tokens** — 纯计数工具，不检查上下文限制
2. **messages.create** — 实际推理接口，返回真实的上下文窗口限制
3. **代理限制** — 代理可能对不同接口设置不同的限制策略

### 测试流程

**1. 动态生成测试内容**
- 根据最大 `expected_context` 计算内容大小（`expected_context × 6 × 3.0` 字符）
- 内存中生成，无需文件系统

**2. count_tokens 验证（Anthropic）**
- 用途：验证测试内容是否足够大
- 方法：用合理大小的样本调用一次
- 输出：样本的 token 数

**3. messages.create 二分查找**
- 用途：测试实际可用的上下文窗口
- 方法：两阶段二分查找
  - **粗搜**：5000 字符阈值，快速定位
  - **精搜**：40 字符阈值，精确到约 10 tokens
- 处理：
  - 成功 → 扩大下界
  - 超限 → 缩小上界
  - 过载 → 重试 3 次
  - 代理错误 → 停止测试

**4. 生成报告**
- 终端表格：模型、测试内容验证、实际上下文窗口
- JSON 文件：详细结果和 provider 元数据

### 特殊处理

- **Prompt caching**：自动计算缓存 tokens（`cache_creation_input_tokens` + `cache_read_input_tokens`）
- **并发测试**：多个模型并发执行
- **错误分类**：区分 context/proxy/overload/unsupported/unknown

## 依赖

按需安装 SDK：

```bash
pip install anthropic   # Anthropic 模型
pip install openai      # OpenAI 兼容 providers
```

可选依赖（支持配置文件注释）：

```bash
pip install commentjson  # 支持 JSONC 格式配置文件
```

无其他第三方依赖。

## 示例结果

```
┌──────────────────────────────────────┬──────────────────────────┬───────────────────────────────────┐
│ 模型                                │ 测试内容 (count_tokens) │ 实际上下文窗口 (messages.create) │
├──────────────────────────────────────┼──────────────────────────┼───────────────────────────────────┤
│ anthropic/claude-haiku-4-5-20251001 │ 200,005 tokens (样本)   │ 216,498 tokens                   │
│ anthropic/claude-sonnet-4-6         │ 1,000,005 tokens (样本) │ 194,994 tokens                   │
└──────────────────────────────────────┴──────────────────────────┴───────────────────────────────────┘
```

**解读：**
- 测试内容足够大（样本验证通过）
- Sonnet 实际限制约 195K tokens（远低于官方 1M）
- Haiku 实际限制约 216K tokens（略高于官方 200K）

## 架构特点

- **条件 SDK 导入**：用户只需安装用到的 SDK
- **Provider 抽象**：统一的客户端工厂和调用封装
- **动态内容生成**：无需预估文件大小
- **两阶段搜索**：平衡速度和精度
