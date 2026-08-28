"""通知渠道配置归一化和自动化结果筛选测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.core.constants import NotificationChannelType
from app.exceptions import BadRequestException
from app.services.notification_channel_service import NotificationChannelService


def test_webhook_config_rejects_unknown_fields() -> None:
    """Webhook 公开配置只接受超时，防止前端把密钥误存到 JSON。"""
    with pytest.raises(BadRequestException, match="未知字段"):
        NotificationChannelService._normalize_config(  # noqa: SLF001
            NotificationChannelType.WEBHOOK,
            {"timeoutSeconds": 10, "token": "must-not-be-stored-here"},
        )


def test_smtp_config_normalizes_recipients() -> None:
    """邮件收件人需要清理空白，并保留发送所需的结构化字段。"""
    config = NotificationChannelService._normalize_config(  # noqa: SLF001
        NotificationChannelType.SMTP,
        {
            "host": " smtp.example.com ",
            "fromEmail": " qa@example.com ",
            "recipients": [" owner@example.com ", ""],
            "security": "starttls",
            "timeoutSeconds": 12,
        },
    )

    assert config["host"] == "smtp.example.com"
    assert config["recipients"] == ["owner@example.com"]
    assert config["security"] == "STARTTLS"


async def test_automation_result_only_sends_to_matching_channels() -> None:
    """通过结果重要度为 60，只发送给允许全部结果的启用渠道。"""
    now = datetime.now(UTC)
    all_results_channel = SimpleNamespace(
        id=1,
        channel_type="WEBHOOK",
        config={"timeoutSeconds": 10},
        encrypted_secret="encrypted-one",
        enabled=True,
        importance_threshold=60,
        breaking_only=False,
    )
    failure_only_channel = SimpleNamespace(
        id=2,
        channel_type="WEBHOOK",
        config={"timeoutSeconds": 10},
        encrypted_secret="encrypted-two",
        enabled=True,
        importance_threshold=100,
        breaking_only=True,
    )
    repository = SimpleNamespace(
        list_enabled_channels=AsyncMock(
            return_value=[all_results_channel, failure_only_channel]
        )
    )
    task = SimpleNamespace(
        id=7,
        status="PASSED",
        error_message=None,
        project=SimpleNamespace(name="LBlog"),
        definition=SimpleNamespace(name="文章发布", version="1.0"),
        environment=SimpleNamespace(name="本地测试环境"),
        updated_at=now,
    )
    automation_repository = SimpleNamespace(get_task=AsyncMock(return_value=task))
    sender = SimpleNamespace(send=AsyncMock())
    service = NotificationChannelService(
        repository,  # type: ignore[arg-type]
        sender=sender,  # type: ignore[arg-type]
        automation_repository=automation_repository,  # type: ignore[arg-type]
    )

    # 测试筛选逻辑不依赖 Fernet，替换解密函数以避免引入真实密钥。
    with patch(
        "app.services.notification_channel_service.decrypt_secret",
        return_value="https://example.com/webhook",
    ):
        result = await service.send_automation_result(8, 7)

    assert result == {"eligible": 1, "sent": 1, "failed": 0}
    sender.send.assert_awaited_once()
