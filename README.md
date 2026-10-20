# astrbot_plugin_manual_compress

**手动上下文压缩插件** —— 一条指令把当前会话的冗长历史浓缩成 LLM 摘要，释放 token、续命长对话。

## 功能

- **手动压缩**：`/compress` 一键触发，用当前 Provider 把整个会话历史浓缩为摘要，保留关键信息；
- **状态查看**：`/compress status` 查看当前会话的消息条数与估算 token 数；
- **原生还原**：使用 AstrBot 框架原生方法还原消息，完整保留 tool_calls / tool_call_id / 多模态内容，压缩后工具调用链不断裂；
- **智能跳过**：历史过短（≤4 条）时提示无需压缩；
- **主人专属**：仅主人可用。

## 适用场景

- 长对话聊到后期响应变慢、变贵——压缩后上下文瞬间瘦身；
- 想保留对话精华又不想 `/reset` 清空重来。

## 安装

```bash
cd /path/to/AstrBot/data/plugins
git clone https://github.com/snlyj/astrbot_plugin_manual_compress.git
# 重启 AstrBot 或在 WebUI 面板热重载
```

## 配置

```bash
# MASTER_ID（必填）
export ASTRBOT_MASTER_ID="你的QQ号"
# 或编辑 main.py 第 39 行：MASTER_ID = "你的QQ号"
```

## 指令说明

| 指令 | 权限 | 说明 |
|------|------|------|
| `/compress` | 仅主人 | 立即压缩当前会话上下文为 LLM 摘要 |
| `/compress status` | 仅主人 | 查看当前会话的消息数与 token 估算，不做任何修改 |

## 参数说明（源码可调项）

| 参数 | 默认值 | 位置 | 说明 |
|------|--------|------|------|
| `MASTER_ID` | 无（必填） | 环境变量 `ASTRBOT_MASTER_ID` 或源码第 39 行 | 允许执行压缩的用户 ID |
| `len(history) <= 4` | `4` | 压缩触发下限 | 历史消息数不超过此值时拒绝压缩（太短没必要） |

## 使用示例

```
你：/compress status
🤖 📊 当前会话历史：87 条消息，约 42310 tokens。

你：/compress
🤖 ✅ 压缩完成：87 条 → 1 条摘要（约 412 tokens），节省 97%。
```

## 工作原理

1. 从会话管理器取出当前会话完整历史；
2. 用框架原生 `bind_checkpoint_messages` 还原消息对象（保留工具调用与多模态结构）；
3. 调用 `LLMSummaryCompressor` 让当前 Provider 生成摘要；
4. 摘要替换原历史写入会话。

压缩消耗一次 LLM 调用（输入=原历史，输出=摘要），约等于让模型读一遍当前对话的价格。

## 常见问题

**Q：压缩会丢什么？**
早期对话的具体措辞会丢失，摘要保留事实要点（决定、偏好、任务状态等）。刚发生的关键对话建议压缩前先让机器人记进长期记忆（配合 `astrbot_plugin_long_memory`）。

**Q：压缩失败？**
检查当前 Provider 是否可用（压缩用的就是聊天用的模型）。

## 依赖

- AstrBot v4.x+（依赖框架内置的 `LLMSummaryCompressor`）
- 无第三方 pip 依赖

## License

MIT
