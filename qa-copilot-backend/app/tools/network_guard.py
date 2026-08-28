"""后台工具访问外部主机前的服务端请求伪造防护。"""

import asyncio
import socket
from ipaddress import ip_address, ip_network

from app.core.config import settings
from app.exceptions import BadRequestException


async def validate_tool_hostname(hostname: str, port: int) -> None:
    """解析主机全部地址，只允许公网或运维显式放行的内网/回环地址。"""
    try:
        address_infos = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise BadRequestException("外部连接主机无法解析") from exc
    allowed_networks = [ip_network(value, strict=False) for value in settings.tool_allowed_private_networks]
    addresses = {ip_address(item[4][0].split("%", 1)[0]) for item in address_infos}
    if not addresses:
        raise BadRequestException("外部连接主机没有可用地址")
    for address in addresses:
        if address.is_loopback and settings.tool_allow_loopback:
            continue
        if any(address in network for network in allowed_networks):
            continue
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            raise BadRequestException("外部连接解析到未授权的内网或特殊地址")
