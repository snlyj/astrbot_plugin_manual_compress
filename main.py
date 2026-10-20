import os
import json

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.star import Context, Star, register

try:
    from astrbot.core.agent.context.compressor import LLMSummaryCompressor
    from astrbot.core.agent.message import (
        Message,
        bind_checkpoint_messages,
        dump_messages_with_checkpoints,
    )
except ImportError:  # 兼容不同版本路径
    LLMSummaryCompressor = None
    Message = None
    bind_checkpoint_messages = None
    dump_messages_with_checkpoints = None


def _load_messages(history: list) -> list:
    """用框架原生方法还原消息，完整保留 tool_calls / tool_call_id / 多模态内容。"""
    if bind_checkpoint_messages is not None:
        try:
            return bind_checkpoint_messages(
                [m for m in history if isinstance(m, dict)]
            )
        except Exception as e:  # 个别脏数据时退回逐条解析
            logger.warning(f"[manual_compress] 原生解析失败，逐条解析: {e}")
    msgs = []
    for item in history:
        try:
            if isinstance(item, dict) and not str(item.get("role", "")).startswith("_"):
                msgs.append(Message.model_validate(item))
        except Exception:
            continue
    return msgs

MASTER_ID = os.environ.get("ASTRBOT_MASTER_ID", "")


@register(
    "astrbot_plugin_manual_compress",
    "静",
    "手动触发当前会话的上下文压缩（LLM 摘要）",
    "1.2.0",
)
class ManualCompress(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("compress")
    async def compress(self, event: AstrMessageEvent, sub: str = ""):
        """手动压缩当前会话上下文：/compress 或 /compress status（仅主人可用）"""
        if event.get_sender_id() != MASTER_ID:
            event.set_result(MessageEventResult().message("不接受主人以外的命令。"))
            event.stop_event()
            return

        umo = event.unified_msg_origin
        conv_mgr = self.context.conversation_manager

        cid = await conv_mgr.get_curr_conversation_id(umo)
        if not cid:
            event.set_result(
                MessageEventResult().message("❌ 当前没有会话，请先说句话创建会话。")
            )
            return

        conv = await conv_mgr.get_conversation(umo, cid)
        if not conv:
            event.set_result(
                MessageEventResult().message("❌ 未找到会话记录。")
            )
            return

        raw = conv.history
        if isinstance(raw, str):
            try:
                history = json.loads(raw) if raw.strip() else []
            except Exception:
                history = []
        elif isinstance(raw, list):
            history = raw
        else:
            history = []
        if not history:
            event.set_result(
                MessageEventResult().message("ℹ️ 会话历史为空，无需压缩。")
            )
            return

        # 仅查看状态
        if sub == "status":
            from astrbot.core.agent.context.token_counter import (
                EstimateTokenCounter,
            )

            counter = EstimateTokenCounter()
            status_msgs = _load_messages(history)
            total = counter.count_tokens(status_msgs)
            event.set_result(
                MessageEventResult().message(
                    f"📊 当前会话历史：{len(history)} 条消息，"
                    f"约 {total} tokens。"
                )
            )
            return

        # 获取当前 Provider
        provider = await self.context.get_using_provider_async(umo)
        if not provider:
            event.set_result(
                MessageEventResult().message("❌ 未找到可用的 LLM Provider。")
            )
            return

        # 若历史过短则不压缩
        if len(history) <= 4:
            event.set_result(
                MessageEventResult().message(
                    f"ℹ️ 会话历史仅 {len(history)} 条，太短了，无需压缩。"
                )
            )
            return

        # 读取全局压缩设置里的自定义指令与保留比例
        cfg = self.context.get_config(umo=umo)
        runner_cfg = cfg.get("agent_runner", {}).get("config", {}).get(
            "compression", {}
        )
        instruction = runner_cfg.get("instruction") or None
        keep_ratio = runner_cfg.get("keep_recent_ratio", 0.15)

        if LLMSummaryCompressor is None:
            event.set_result(
                MessageEventResult().message(
                    "❌ 当前 AstrBot 版本不兼容此插件，请检查版本。"
                )
            )
            return

        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=keep_ratio,
            instruction_text=instruction,
        )

        # 将 DB 中的 dict 历史转为 Message 对象（保留工具调用结构）
        messages = _load_messages(history)

        if len(messages) < 4:
            event.set_result(
                MessageEventResult().message("ℹ️ 有效消息过少，无需压缩。")
            )
            return

        try:
            compressed = await compressor(messages)
        except Exception as e:
            logger.error(f"[manual_compress] 压缩失败: {e}", exc_info=True)
            event.set_result(
                MessageEventResult().message(f"❌ 压缩失败：{e}")
            )
            return

        if len(compressed) >= len(messages):
            event.set_result(
                MessageEventResult().message(
                    f"ℹ️ 压缩后 ({len(compressed)} 条) 并未比原来 "
                    f"({len(messages)} 条) 更精简，已保留原历史。"
                )
            )
            return

        # 写回数据库：用框架原生序列化，tool_calls 与 tool 结果成对保留
        if dump_messages_with_checkpoints is not None:
            new_history = dump_messages_with_checkpoints(compressed)
        else:
            new_history = [m.model_dump() for m in compressed]

        await conv_mgr.update_conversation(
            umo, conversation_id=cid, history=new_history
        )

        old_total = sum(len(str(m.get("content", ""))) for m in history)
        new_total = sum(len(str(m.get("content", ""))) for m in new_history)
        event.set_result(
            MessageEventResult().message(
                f"✅ 压缩完成：{len(history)} 条 → {len(new_history)} 条消息"
                f"（{old_total} → {new_total} 字符）。"
            )
        )
