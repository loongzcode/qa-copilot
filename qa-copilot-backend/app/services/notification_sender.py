"""受控通知发送适配器；业务层不直接调用 HTTP 或 SMTP 客户端。"""

from __future__ import annotations

import asyncio
import smtplib
import socket
from dataclasses import dataclass
from email.message import EmailMessage
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.constants import NotificationChannelType
from app.models import NotificationChannel


class NotificationDeliveryError(RuntimeError):
    """通知服务返回失败、地址越界或配置无法使用。"""


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    """不同渠道共同使用的通知正文。"""

    title: str
    content: str
    level: str
    details: dict[str, str]


class NotificationSender:
    """根据渠道类型选择固定发送实现，不执行数据库中的任意代码。"""

    async def send(
        self,
        channel: NotificationChannel,
        secret: str,
        message: NotificationMessage,
    ) -> None:
        """校验渠道类型并把消息发送到对应外部服务。"""
        channel_type = NotificationChannelType(channel.channel_type)
        if channel_type == NotificationChannelType.SMTP:
            await self._send_smtp(channel.config, secret, message)
            return
        await self._send_webhook(channel_type, channel.config, secret, message)

    async def _send_webhook(
        self,
        channel_type: NotificationChannelType,
        config: dict,
        endpoint: str,
        message: NotificationMessage,
    ) -> None:
        """发送通用 Webhook、企业微信或钉钉机器人消息。"""
        await self._validate_network_target(endpoint)
        timeout_seconds = int(config.get("timeoutSeconds", 10))
        if channel_type == NotificationChannelType.WECHAT_WORK_BOT:
            payload = {
                "msgtype": "markdown",
                "markdown": {"content": self._markdown_content(message)},
            }
        elif channel_type == NotificationChannelType.DINGTALK_BOT:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": message.title,
                    "text": self._markdown_content(message),
                },
            }
        else:
            payload = {
                "title": message.title,
                "content": message.content,
                "level": message.level,
                "details": message.details,
            }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        ) as client:
            response = await client.post(endpoint, json=payload)
        if response.is_redirect:
            raise NotificationDeliveryError("通知地址返回重定向，已拒绝跟随")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NotificationDeliveryError(
                f"通知服务返回 HTTP {response.status_code}"
            ) from exc

        if channel_type in {
            NotificationChannelType.WECHAT_WORK_BOT,
            NotificationChannelType.DINGTALK_BOT,
        }:
            try:
                result = response.json()
            except ValueError as exc:
                raise NotificationDeliveryError("机器人通知返回内容不是 JSON") from exc
            error_code = result.get("errcode")
            if error_code not in (None, 0):
                raise NotificationDeliveryError(
                    f"机器人通知返回失败码 {error_code}"
                )

    async def _send_smtp(
        self,
        config: dict,
        password: str,
        message: NotificationMessage,
    ) -> None:
        """在线程中发送邮件，避免同步 smtplib 阻塞异步 Worker 事件循环。"""
        host = str(config["host"])
        await self._validate_hostname(host)
        await asyncio.to_thread(self._send_smtp_sync, config, password, message)

    @staticmethod
    def _send_smtp_sync(
        config: dict,
        password: str,
        message: NotificationMessage,
    ) -> None:
        """使用 SMTP、STARTTLS 或 SMTP_SSL 发送一封纯文本邮件。"""
        host = str(config["host"])
        port = int(config["port"])
        security = str(config.get("security", "STARTTLS"))
        username = str(config.get("username", ""))
        sender = str(config["fromEmail"])
        recipients = [str(item) for item in config["recipients"]]

        mail = EmailMessage()
        mail["Subject"] = f"{config.get('subjectPrefix', '[QA Copilot]')} {message.title}".strip()
        mail["From"] = sender
        mail["To"] = ", ".join(recipients)
        mail.set_content(NotificationSender._plain_content(message))

        timeout = int(config.get("timeoutSeconds", 10))
        if security == "SSL":
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as client:
                if username:
                    client.login(username, password)
                client.send_message(mail)
            return

        with smtplib.SMTP(host, port, timeout=timeout) as client:
            if security == "STARTTLS":
                client.starttls()
            if username:
                client.login(username, password)
            client.send_message(mail)

    @staticmethod
    def _plain_content(message: NotificationMessage) -> str:
        """把结构化消息转换成邮件和通用文本正文。"""
        detail_lines = [f"{key}：{value}" for key, value in message.details.items()]
        return "\n".join([message.content, "", *detail_lines]).strip()

    @staticmethod
    def _markdown_content(message: NotificationMessage) -> str:
        """把结构化消息转换成机器人支持的 Markdown 文本。"""
        detail_lines = [f"> **{key}**：{value}" for key, value in message.details.items()]
        return "\n\n".join([f"### {message.title}", message.content, *detail_lines])

    async def _validate_network_target(self, endpoint: str) -> None:
        """发送前检查协议、凭据和域名解析，降低服务端请求伪造风险。"""
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise NotificationDeliveryError("Webhook 地址必须是完整 HTTP(S) 地址")
        if parsed.username is not None or parsed.password is not None:
            raise NotificationDeliveryError("Webhook 地址不能包含用户名或密码")
        if parsed.scheme == "http" and not settings.debug:
            raise NotificationDeliveryError("非调试环境的 Webhook 必须使用 HTTPS")
        await self._validate_hostname(parsed.hostname)

    async def _validate_hostname(self, hostname: str) -> None:
        """解析目标所有 IP，拒绝未授权的回环、私网和保留地址。"""
        try:
            address_infos = await asyncio.get_running_loop().getaddrinfo(
                hostname,
                None,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise NotificationDeliveryError("通知服务域名无法解析") from exc

        allowed_private_networks = [
            ip_network(item, strict=False)
            for item in settings.notification_allowed_private_networks
        ]
        addresses = {
            ip_address(item[4][0].split("%", 1)[0]) for item in address_infos
        }
        for address in addresses:
            if address.is_global:
                continue
            if address.is_loopback and (
                settings.debug or settings.notification_allow_loopback
            ):
                continue
            if any(address in network for network in allowed_private_networks):
                continue
            raise NotificationDeliveryError("通知服务地址超出平台允许访问的网络范围")

