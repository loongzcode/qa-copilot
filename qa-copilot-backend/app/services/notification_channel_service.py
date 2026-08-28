"""通知渠道管理、测试和自动化结果发送业务。"""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.constants import AutomationExecutionStatus, NotificationChannelType
from app.core.security import decrypt_secret, encrypt_secret
from app.exceptions import BadRequestException, ConflictException, ExternalServiceException, NotFoundException
from app.models import NotificationChannel
from app.repositories.automation_execution_tasks_repository import AutomationExecutionTasksRepository
from app.repositories.notification_channel_repository import NotificationChannelRepository
from app.schemas.dto.notification_channels import NotificationChannelCreateDTO, NotificationChannelUpdateDTO
from app.schemas.vo.notification_channels import NotificationChannelTestResultVO, NotificationChannelVO
from app.services.notification_sender import NotificationMessage, NotificationSender

logger = logging.getLogger(__name__)


class NotificationChannelService:
    """维护加密通知渠道，并向启用渠道分发自动化执行结果。"""

    def __init__(
        self,
        repository: NotificationChannelRepository,
        *,
        sender: NotificationSender | None = None,
        automation_repository: AutomationExecutionTasksRepository | None = None,
    ) -> None:
        self.repository = repository
        self.sender = sender or NotificationSender()
        self.automation_repository = automation_repository

    @staticmethod
    def _to_vo(channel: NotificationChannel) -> NotificationChannelVO:
        """把实体转换成不包含密钥正文的前端视图。"""
        return NotificationChannelVO(
            id=channel.id,
            name=channel.name,
            channel_type=NotificationChannelType(channel.channel_type),
            config=channel.config,
            secret_configured=bool(channel.encrypted_secret),
            enabled=channel.enabled,
            importance_threshold=channel.importance_threshold,
            breaking_only=channel.breaking_only,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
        )

    async def list_channels(self) -> list[NotificationChannelVO]:
        """返回全部通知渠道的脱敏配置。"""
        return [self._to_vo(item) for item in await self.repository.list_channels()]

    async def create_channel(
        self,
        payload: NotificationChannelCreateDTO,
    ) -> NotificationChannelVO:
        """校验类型配置并加密密钥后创建通知渠道。"""
        config = self._normalize_config(payload.channel_type, payload.config)
        channel = NotificationChannel(
            name=payload.name,
            channel_type=payload.channel_type.value,
            config=config,
            encrypted_secret=encrypt_secret(payload.secret.strip()),
            enabled=payload.enabled,
            importance_threshold=payload.importance_threshold,
            breaking_only=payload.breaking_only,
        )
        self.repository.add(channel)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("通知渠道名称已存在") from exc
        return self._to_vo(channel)

    async def update_channel(
        self,
        channel_id: int,
        payload: NotificationChannelUpdateDTO,
    ) -> NotificationChannelVO:
        """部分更新渠道；未提交新 secret 时保留数据库原密文。"""
        channel = await self.repository.get_channel(channel_id)
        if channel is None:
            raise NotFoundException("通知渠道不存在")
        changes = payload.model_dump(exclude_unset=True)
        secret = changes.pop("secret", None)
        target_type = NotificationChannelType(
            changes.get("channel_type", channel.channel_type)
        )
        if "channel_type" in changes:
            changes["channel_type"] = target_type.value
            if target_type.value != channel.channel_type and secret is None:
                raise BadRequestException("修改渠道类型时必须重新填写密钥或 Webhook 地址")
        if "config" in changes:
            changes["config"] = self._normalize_config(
                target_type,
                dict(changes["config"]),
            )
        for key, value in changes.items():
            setattr(channel, key, value)
        if secret is not None:
            channel.encrypted_secret = encrypt_secret(secret.strip())
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("通知渠道名称已存在或配置不合法") from exc
        return self._to_vo(channel)

    async def delete_channel(self, channel_id: int) -> None:
        """删除通知渠道；发送中的 Worker 已持有实体快照，不会返回密钥。"""
        channel = await self.repository.get_channel(channel_id)
        if channel is None:
            raise NotFoundException("通知渠道不存在")
        await self.repository.delete(channel)
        await self.repository.commit()

    async def test_channel(self, channel_id: int) -> NotificationChannelTestResultVO:
        """使用真实配置发送一条测试消息，并返回外部服务耗时。"""
        channel = await self.repository.get_channel(channel_id)
        if channel is None:
            raise NotFoundException("通知渠道不存在")
        started = monotonic()
        try:
            await self.sender.send(
                channel,
                decrypt_secret(channel.encrypted_secret),
                NotificationMessage(
                    title="通知渠道连接测试",
                    content="QA Copilot 已成功调用该通知渠道。",
                    level="INFO",
                    details={"渠道": channel.name},
                ),
            )
        except Exception as exc:
            raise ExternalServiceException(
                f"通知渠道测试失败：{type(exc).__name__}"
            ) from exc
        return NotificationChannelTestResultVO(
            success=True,
            message="测试通知发送成功",
            latency_ms=max(0, round((monotonic() - started) * 1000)),
        )

    async def send_automation_result(self, project_id: int, task_id: int) -> dict[str, int]:
        """读取自动化终态并向满足阈值的启用渠道发送摘要。"""
        if self.automation_repository is None:
            raise RuntimeError("自动化通知服务缺少任务 Repository")
        task = await self.automation_repository.get_task(project_id, task_id)
        if task is None:
            raise NotFoundException("自动化执行任务不存在")
        terminal_status = AutomationExecutionStatus(task.status)
        if terminal_status not in {
            AutomationExecutionStatus.PASSED,
            AutomationExecutionStatus.FAILED,
            AutomationExecutionStatus.TIMED_OUT,
            AutomationExecutionStatus.CANCELLED,
        }:
            raise ConflictException("自动化执行任务尚未结束")

        breaking = terminal_status in {
            AutomationExecutionStatus.FAILED,
            AutomationExecutionStatus.TIMED_OUT,
        }
        importance = 100 if breaking else 80 if terminal_status == AutomationExecutionStatus.CANCELLED else 60
        channels = [
            channel
            for channel in await self.repository.list_enabled_channels()
            if channel.importance_threshold <= importance
            and (not channel.breaking_only or breaking)
        ]
        if not channels:
            return {"eligible": 0, "sent": 0, "failed": 0}

        message = NotificationMessage(
            title=f"自动化执行{self._status_label(terminal_status)}",
            content=(
                "接口自动化任务已执行完成。"
                if not task.error_message
                else f"接口自动化任务结束：{task.error_message}"
            ),
            level="ERROR" if breaking else "INFO",
            details={
                "项目": task.project.name,
                "自动化定义": f"{task.definition.name} V{task.definition.version}",
                "测试环境": task.environment.name,
                "执行状态": self._status_label(terminal_status),
                "任务编号": str(task.id),
            },
        )

        async def send_one(channel: NotificationChannel) -> bool:
            try:
                await self.sender.send(
                    channel,
                    decrypt_secret(channel.encrypted_secret),
                    message,
                )
                return True
            except Exception:
                logger.exception(
                    "自动化结果通知发送失败：task_id=%s channel_id=%s",
                    task.id,
                    channel.id,
                )
                return False

        results = await asyncio.gather(*(send_one(channel) for channel in channels))
        sent = sum(results)
        return {"eligible": len(channels), "sent": sent, "failed": len(channels) - sent}

    @staticmethod
    def _status_label(status: AutomationExecutionStatus) -> str:
        """把自动化状态转换成通知中可读的中文。"""
        return {
            AutomationExecutionStatus.PASSED: "通过",
            AutomationExecutionStatus.FAILED: "失败",
            AutomationExecutionStatus.TIMED_OUT: "超时",
            AutomationExecutionStatus.CANCELLED: "已取消",
        }[status]

    @staticmethod
    def _normalize_config(
        channel_type: NotificationChannelType,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """按渠道类型白名单化公开配置，拒绝任意未知字段。"""
        timeout = int(config.get("timeoutSeconds", 10))
        if not 1 <= timeout <= 60:
            raise BadRequestException("通知超时时间必须在 1 到 60 秒之间")
        if channel_type != NotificationChannelType.SMTP:
            unknown = set(config) - {"timeoutSeconds"}
            if unknown:
                raise BadRequestException(f"Webhook 配置包含未知字段：{', '.join(sorted(unknown))}")
            return {"timeoutSeconds": timeout}

        allowed = {
            "host",
            "port",
            "security",
            "username",
            "fromEmail",
            "recipients",
            "subjectPrefix",
            "timeoutSeconds",
        }
        unknown = set(config) - allowed
        if unknown:
            raise BadRequestException(f"SMTP 配置包含未知字段：{', '.join(sorted(unknown))}")
        host = str(config.get("host", "")).strip()
        username = str(config.get("username", "")).strip()
        from_email = str(config.get("fromEmail", "")).strip()
        recipients = [str(item).strip() for item in config.get("recipients", []) if str(item).strip()]
        security = str(config.get("security", "STARTTLS")).upper()
        port = int(config.get("port", 465 if security == "SSL" else 587))
        if not host or not from_email or not recipients:
            raise BadRequestException("SMTP 必须填写服务器、发件人和至少一个收件人")
        if not 1 <= port <= 65535 or security not in {"NONE", "STARTTLS", "SSL"}:
            raise BadRequestException("SMTP 端口或安全方式不合法")
        if "@" not in from_email or any("@" not in item for item in recipients):
            raise BadRequestException("SMTP 发件人或收件人邮箱格式不正确")
        return {
            "host": host,
            "port": port,
            "security": security,
            "username": username,
            "fromEmail": from_email,
            "recipients": recipients,
            "subjectPrefix": str(config.get("subjectPrefix", "[QA Copilot]"))[:100],
            "timeoutSeconds": timeout,
        }
