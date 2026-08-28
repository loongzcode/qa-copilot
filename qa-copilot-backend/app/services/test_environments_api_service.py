import asyncio
import json
import re
import socket
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from time import perf_counter
from urllib.parse import urlsplit

import httpx
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.constants import ProjectStatus, TestEnvironmentType
from app.core.security import decrypt_secret, encrypt_secret
from app.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.models import TestEnvironment, User
from app.repositories.test_environments_api_repository import TestEnvironmentsApiRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.test_environments import (
    TestEnvironmentCreateDTO,
    TestEnvironmentUpdateDTO,
    TestEnvironmentVariableDTO,
)
from app.schemas.vo.test_environments import (
    TestEnvironmentConnectionResultVO,
    TestEnvironmentVariableVO,
    TestEnvironmentVO,
)


@dataclass(frozen=True, slots=True)
class AutomationRuntimeEnvironment:
    """只在 Worker 内存中存在的自动化运行环境，真实变量不会写入任务表或日志。"""

    base_url: str
    headers: dict[str, str]
    variables: dict[str, str]


class TestEnvironmentsApiService:
    _VARIABLE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}")

    _FORBIDDEN_HEADERS = {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "proxy-authorization",
        "proxy-connection",
    }
    def __init__(self, repository: TestEnvironmentsApiRepository,
                 project_repository: TestProjectsRepository,):
        self.repository = repository
        self.project_repository = project_repository

    @staticmethod
    def _environment_read(
        environment: TestEnvironment,
    ) -> TestEnvironmentVO:
        # 数据库没有保存变量时，使用空列表。
        # encrypted_variables 保存的是：
        # 加密后的 JSON 字符串。
        #
        # 所以读取顺序是：
        # 密文 -> 解密成 JSON 字符串 -> 转成 Python 列表。
        raw_variables = TestEnvironmentsApiService._decrypt_variables(environment.encrypted_variables)

        # 保存处理后可以返回给前端的变量。
        variable_vos: list[TestEnvironmentVariableVO] = []

        for item in raw_variables:
            # 没有 secret 字段时默认按照敏感变量处理，
            # 避免因为旧数据缺少字段而泄露变量值。
            secret = item.get("secret", True)

            # 敏感变量不返回真实值，普通变量可以正常返回。
            value = "********" if secret else item.get("value", "")

            variable_vos.append(
                TestEnvironmentVariableVO(
                    key=item.get("key", ""),
                    value=value,
                    secret=secret,
                )
            )

        return TestEnvironmentVO(
            id=environment.id,
            project_id=environment.project_id,
            name=environment.name,
            environment_type=TestEnvironmentType(environment.environment_type),
            base_url=environment.base_url,
            allowed_hosts=environment.allowed_hosts,
            headers=environment.headers,
            variables=variable_vos,
            variable_count=len(variable_vos),
            enabled=environment.enabled,
            created_by=environment.created_by,
            created_by_name=(environment.creator.display_name if environment.creator else None),
            created_at=environment.created_at,
            updated_at=environment.updated_at,
        )

    @staticmethod
    def _encrypt_variables(
            variables: list[TestEnvironmentVariableDTO],
    ) -> str:
        variable_list = []
        for variable in variables:
            variable_list.append(variable.model_dump())
        variable_json = json.dumps(variable_list,ensure_ascii=False)
        return encrypt_secret(variable_json)

    @staticmethod
    def _decrypt_variables(
        encrypted_variables: str,
    ) -> list[dict]:
        # 兼容数据库中的空字符串。
        if not encrypted_variables:
            return []

        decrypted_text = decrypt_secret(encrypted_variables)
        variable_data = json.loads(decrypted_text)

        # 数据库中的变量必须是 JSON 数组。
        # 如果不是数组，说明数据已经损坏或格式不正确。
        if not isinstance(variable_data, list):
            raise ValueError("环境变量数据格式错误")

        return variable_data

    async def build_automation_runtime_environment(
        self,
        project_id: int,
        environment_id: int,
    ) -> AutomationRuntimeEnvironment:
        """读取并验证 Worker 执行 HTTP 请求需要的环境配置。

        功能：校验环境存在、启用且非生产，复用 SSRF 防护，再在内存中解密变量。
        作用：由自动化 Worker 在真正启动 Pytest 前调用，形成最后一道目标边界检查。
        为什么用它：提交任务和实际执行之间环境可能变化，不能只信任 API 提交时的
        校验；把真实变量限定在 Worker 内存中可避免明文落入任务表和 Redis。
        """
        environment = await self.repository.get_environment(project_id, environment_id)
        if environment is None:
            raise NotFoundException("测试环境不存在")
        if not environment.enabled:
            raise BadRequestException("测试环境已停用")
        if environment.environment_type == TestEnvironmentType.PRODUCTION.value:
            raise ForbiddenException("自动化执行器禁止连接生产环境")
        await self._validate_target_url(environment.base_url, environment.allowed_hosts)
        variables = {
            str(item["key"]): str(item.get("value", ""))
            for item in self._decrypt_variables(environment.encrypted_variables)
            if item.get("key")
        }
        return AutomationRuntimeEnvironment(
            base_url=environment.base_url,
            headers=self._render_headers(environment),
            variables=variables,
        )

    @staticmethod
    def _is_public_ip(value: str) -> bool:
        try:
            address = ip_address(value)
        except ValueError:
            return False

        return (
            address.is_global
            and not address.is_private
            and not address.is_loopback
            and not address.is_link_local
            and not address.is_reserved
            and not address.is_multicast
            and not address.is_unspecified
        )

    @staticmethod
    def _is_allowed_target_ip(
        value: str,
        allow_configured_private_networks: bool,
    ) -> bool:
        """判断目标 IP 是否位于平台明确允许访问的网络范围内。"""

        if TestEnvironmentsApiService._is_public_ip(value):
            return True
        if not allow_configured_private_networks:
            return False

        try:
            address = ip_address(value)
        except ValueError:
            return False

        # 回环地址只用于本地开发联调，例如访问本机启动的博客或测试服务。
        # 必须同时满足以下条件：
        # 1. 项目配置的是精确域名/IP，而不是 allowed_hosts=["*"]；
        # 2. 后端运行环境明确为 development；
        # 3. 平台运维显式开启 TEST_ENV_ALLOW_LOOPBACK。
        # 生产环境即使误配了开关，也不会访问 127.0.0.1 或 ::1。
        if address.is_loopback:
            return (
                settings.app_env.lower() == "development"
                and settings.test_env_allow_loopback
            )

        for network_value in settings.test_env_allowed_private_networks:
            network = ip_network(network_value)
            if address.version == network.version and address in network:
                return True

        return False
        

    async def list_environments(
            self,
            project_id: int,
            current_user: User,
            keyword: str,
            enabled: bool | None,
    ) -> list[TestEnvironmentVO]:
        project = await self.project_repository.get_accessible_project(project_id,current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        environments = await self.repository.list_environments(project_id,keyword,enabled)
        return [self._environment_read(environment) for environment in environments]

    

    async def create_environment(
            self,
            project_id: int,
            current_user: User,
            payload: TestEnvironmentCreateDTO,
    ) -> TestEnvironmentVO:
        project = await self.project_repository.get_accessible_project(project_id,current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不允许创建测试环境")
        if "*" in payload.allowed_hosts and not current_user.is_superuser:
            raise ForbiddenException("只有超级管理员可以允许所有公网域名")
        environment = TestEnvironment(
            project_id = project_id,
            name = payload.name,
            environment_type=payload.environment_type.value,
            base_url = payload.base_url,
            allowed_hosts = payload.allowed_hosts,
            encrypted_variables = self._encrypt_variables(payload.variables),
            headers = payload.headers,
            enabled=payload.enabled,
            created_by=current_user.id,
            creator=current_user
        )
        self.repository.add(environment)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("当前项目中已存在同名测试环境") from exc
        return self._environment_read(environment)

    async def delete_environment(
        self,
        project_id: int,
        environment_id: int,
        current_user: User,
    ) -> None:
        """删除当前用户有权管理的项目测试环境。"""

        # 第一步：根据项目 ID 和当前用户查询有权访问的项目。
        # 普通用户只能操作自己的项目，超级管理员可以操作所有项目。
        project = await self.project_repository.get_accessible_project(project_id,current_user)

        # 第二步：项目不存在或当前用户没有访问权限时抛出异常。
        # 这两种情况对外使用同一个提示，避免泄露其他用户的项目信息。
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        # 第三步：已归档项目只允许查看历史数据，不能再删除测试环境。
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不允许删除测试环境")
        # 第四步：同时使用 project_id 和 environment_id 查询环境。
        # 这样可以保证要删除的环境确实属于当前项目，避免跨项目删除。
        environment = await self.repository.get_environment(project_id,environment_id)
        # 第五步：环境不存在时抛出 NotFoundException。
        if environment is None:
            raise NotFoundException("测试环境不存在")
        # 第六步：调用 Repository 删除环境实体。
        # BaseRepository.delete() 是异步方法，这里需要使用 await。
        await self.repository.delete(environment)
        # 第七步：提交事务。提交失败时必须先 rollback，
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            # 再把数据库异常转换成前端能够理解的 ConflictException。
            raise ConflictException("删除失败") from exc

    async def update_environment(
            self,
            project_id: int,
            environment_id: int,
            current_user: User,
            payload: TestEnvironmentUpdateDTO,
    ) -> TestEnvironmentVO:
        """编辑测试环境，并安全处理前端返回的敏感变量掩码。

        这个方法中与变量有关的对象分为五类：
        1. payload.variables：前端本次提交的变量 DTO；
        2. environment.encrypted_variables：数据库中保存的整段密文；
        3. existing_variables：密文解密后的旧变量字典列表；
        4. existing_variable_map：以变量名为键建立的旧变量索引；
        5. merged_variables：合并新旧值后，最终准备重新加密的变量 DTO 列表。

        敏感变量返回前端时已经变成 ********。如果前端仍然提交 ********，
        代表用户没有修改真实值，后端必须从 existing_variable_map 中找回旧值，
        不能把星号当成真实密钥写进数据库。
        """

        # 先检查当前用户是否能够访问这个项目。
        # get_accessible_project() 同时负责项目存在性和项目数据权限判断。
        project = await self.project_repository.get_accessible_project(project_id,current_user)

        # 项目不存在和无权访问统一返回同一提示，避免泄露其他用户的项目数据。
        if project is None:
            raise NotFoundException("项目不存在或无权操作")

        # 归档项目作为历史数据保留，只允许查看，不能再修改测试环境。
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不允许更新测试环境")

        # 同时使用 project_id 和 environment_id 查询，确保环境属于当前项目，
        # 避免用户拿当前项目权限去修改其他项目中的环境。
        environment = await self.repository.get_environment(project_id,environment_id)
        if environment is None:
            raise NotFoundException("测试环境不存在")

        # 只提取前端实际传入的字段，未传字段继续使用数据库原值。
        # variables 不能直接 setattr，因为其中的敏感值可能只是 ******** 掩码，
        # 所以先排除，后面单独完成新旧变量合并。
        changes = payload.model_dump(
            exclude_unset=True,
            exclude={"variables"},
        )

        # 只有前端确实修改了 allowed_hosts 时才检查 * 的配置权限。
        # 普通用户可以编辑普通白名单，但只有超级管理员可以主动配置 *。
        if "allowed_hosts" in changes:
            new_allowed_hosts = changes["allowed_hosts"]

            if "*" in new_allowed_hosts and not current_user.is_superuser:
                raise ForbiddenException("只有超级管理员可以允许所有公网域名")

        # 更新 DTO 允许只传 base_url 或只传 allowed_hosts。
        # 因此需要把“本次新值”和“数据库旧值”组合起来，得到修改后的最终配置。
        # dict.get(字段名, 旧值) 表示：传了用新值，没传就使用旧值。
        final_base_url = changes.get(
            "base_url",
            environment.base_url,
        )
        final_allowed_hosts = changes.get(
            "allowed_hosts",
            environment.allowed_hosts,
        )

        base_host = urlsplit(final_base_url).hostname

        # 使用普通白名单时，基础地址自身的域名必须位于白名单中。
        # 配置 * 时表示允许所有公网域名，因此跳过精确域名匹配。
        if "*" not in final_allowed_hosts and base_host not in final_allowed_hosts:
            raise BadRequestException("基础地址的域名必须包含在域名白名单中")

        # name、base_url、allowed_hosts、headers、enabled 都是普通实体字段，
        # 可以通过 setattr() 根据字段名统一更新。
        for key, value in changes.items():
            setattr(environment, key, value)

        # 把数据库密文解密成旧变量列表。
        # 示例：[{"key": "api_token", "value": "真实值", "secret": True}]
        existing_variables = self._decrypt_variables(environment.encrypted_variables)

        # 将旧变量列表转换成以变量名为键的字典，方便通过变量名快速查找旧值。
        # 示例：{"api_token": {"key": "api_token", ...}}
        existing_variable_map = {}

        for item in existing_variables:
            key = item.get("key")

            if key:
                existing_variable_map[key] = item

        # None 表示前端没有提交 variables 字段，此时必须保留数据库原密文。
        # 空列表 [] 表示前端明确清空全部变量，仍然需要重新加密空数组。
        if payload.variables is not None:
            # 保存合并完成、最终准备写回数据库的变量 DTO。
            merged_variables: list[TestEnvironmentVariableDTO] = []

            for variable in payload.variables:
                # 先假设使用前端本次提交的值。
                value = variable.value

                # secret=True 且值为 ********，表示前端拿到的是掩码，
                # 用户没有填写新的真实值，需要按照变量名称找回数据库旧值。
                if variable.secret and value == "********":
                    existing_variable = existing_variable_map.get(variable.key)

                    # 旧变量中找不到同名记录，说明这是一个新敏感变量。
                    # 新变量不能只填写掩码，否则数据库中没有真实值可以保留。
                    if existing_variable is None:
                        raise BadRequestException(f"新敏感变量 {variable.key} 必须填写真实值")

                    # 用解密后的旧真实值替换前端提交的 ********。
                    value = existing_variable.get("value", "")

                # 无论是普通变量、新敏感值，还是保留了旧值的敏感变量，
                # 最终都要加入本次准备保存的变量列表。
                merged_variables.append(
                    TestEnvironmentVariableDTO(
                        key=variable.key,
                        value=value,
                        secret=variable.secret,
                    )
                )

            # 所有变量合并完成后整体序列化并加密一次，再替换实体中的旧密文。
            environment.encrypted_variables = self._encrypt_variables(merged_variables)

        # 提交普通字段和加密变量的修改。
        # 如果环境名称违反同一项目内的唯一约束，则回滚整个事务。
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("当前项目中已存在同名测试环境") from exc

        # 返回前再次转换成 VO；_environment_read() 会对敏感值重新脱敏，
        # 因此真实密钥不会通过编辑接口响应返回前端。
        return self._environment_read(environment)

    async def _validate_hostname_addresses(
        self,
        hostname: str,
        allow_configured_private_networks: bool,
    ) -> None:
        """确保域名解析出的每个 IP 都位于平台允许的网络边界内。"""

        try:
            address_infos = await asyncio.get_running_loop().getaddrinfo(
                hostname,
                None,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise BadRequestException("测试环境域名无法解析") from exc

        # getaddrinfo() 可能返回重复地址，因此使用 set 去重。
        resolved_addresses = {address_info[4][0].split("%", 1)[0] for address_info in address_infos}

        if not resolved_addresses:
            raise BadRequestException("测试环境域名没有可用的 IP 地址")

        # 不能只检查第一条解析结果。任意一个地址越过平台网络边界时，
        # 都拒绝整个请求，防止同一域名混合解析到允许地址和危险地址。
        blocked_addresses = [
            address
            for address in resolved_addresses
            if not self._is_allowed_target_ip(
                address,
                allow_configured_private_networks,
            )
        ]

        if blocked_addresses:
            raise ForbiddenException("测试环境地址超出平台允许访问的网络范围")

    async def _validate_target_url(
        self,
        target_url: str,
        allowed_hosts: list[str],
    ) -> None:
        """发送请求前重新检查协议、域名白名单和 DNS 解析结果。"""

        parsed_url = urlsplit(target_url)

        # 只允许 HTTP(S)，防止 file://、ftp://、gopher:// 等协议。
        if parsed_url.scheme not in {"http", "https"}:
            raise BadRequestException("测试环境只允许使用 HTTP 或 HTTPS 地址")

        hostname = parsed_url.hostname

        if not hostname:
            raise BadRequestException("测试环境地址缺少有效域名")

        # URL 中不能直接携带 username:password。
        # 账号、密码和 Token 必须使用加密环境变量。
        if parsed_url.username is not None or parsed_url.password is not None:
            raise BadRequestException("测试环境地址不能包含账号或密码")

        normalized_hostname = hostname.lower().rstrip(".")

        # 没有配置 * 时，目标域名必须和白名单精确匹配。
        if "*" not in allowed_hosts and normalized_hostname not in allowed_hosts:
            raise ForbiddenException("测试环境域名不在允许访问的白名单中")

        # 精确域名白名单可以访问运维配置的私网子网；* 永远只允许公网。
        # 因此项目用户不能仅通过配置 * 扩大到公司内网。
        await self._validate_hostname_addresses(
            normalized_hostname,
            allow_configured_private_networks="*" not in allowed_hosts,
        )


    def _render_headers(
        self,
        environment: TestEnvironment,
    ) -> dict[str, str]:
        """使用真实环境变量替换请求头占位符。"""

        variable_data = self._decrypt_variables(
            environment.encrypted_variables
        )

        # 建立变量名称到真实值的映射。
        variable_values = {
            item.get("key", ""): str(item.get("value", ""))
            for item in variable_data
            if item.get("key")
        }

        rendered_headers: dict[str, str] = {}

        for header_name, header_value in environment.headers.items():
            normalized_name = header_name.strip()
            lower_name = normalized_name.lower()

            # 这些请求头必须由 HTTP 客户端根据真实请求自动生成。
            if lower_name in self._FORBIDDEN_HEADERS:
                raise BadRequestException(
                    f"不允许配置请求头 {normalized_name}"
                )

            # 防止通过换行符注入额外请求头。
            if (
                "\r" in normalized_name
                or "\n" in normalized_name
                or "\r" in header_value
                or "\n" in header_value
            ):
                raise BadRequestException(
                    "请求头不能包含换行符"
                )

            def replace_variable(
                matched: re.Match[str],
            ) -> str:
                variable_key = matched.group(1)

                if variable_key not in variable_values:
                    raise BadRequestException(
                        f"请求头引用了不存在的环境变量：{variable_key}"
                    )

                return variable_values[variable_key]

            rendered_headers[normalized_name] = (
                self._VARIABLE_PATTERN.sub(
                    replace_variable,
                    header_value,
                )
            )

        return rendered_headers


    async def test_connection(
            self,
            project_id: int,
            environment_id: int,
            current_user: User,
    ) -> TestEnvironmentConnectionResultVO:
        project = await self.project_repository.get_accessible_project(project_id,current_user)

        # 项目不存在和无权访问统一返回同一提示，避免泄露其他用户的项目数据。
        if project is None:
            raise NotFoundException("项目不存在或无权操作")

        # 归档项目作为历史数据保留，只允许查看，不能再修改测试环境。
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能测试环境连接")

        environment = await self.repository.get_environment(project_id,environment_id)
        if environment is None:
            raise NotFoundException("测试环境不存在")

        await self._validate_target_url(environment.base_url,environment.allowed_hosts)
        request_headers = self._render_headers(environment)
        started_at = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    10.0,
                    connect=5.0,
                ),
                follow_redirects=False,
                trust_env=False,
            )as client:
                # 使用 stream，只读取响应头，不下载可能很大的响应体
                async with client.stream(
                    "GET",
                    environment.base_url,
                    headers=request_headers,
                )as response:
                    status_code = response.status_code
        except httpx.TimeoutException:
            latency_ms = int((perf_counter() - started_at) * 1000)
            return TestEnvironmentConnectionResultVO(
                success=False, status_code=None, latency_ms=latency_ms, message="连接超时"
            )
        except httpx.RequestError:
            latency_ms = int((perf_counter() - started_at) * 1000)

            return TestEnvironmentConnectionResultVO(
                success=False,
                status_code=None,
                latency_ms=latency_ms,
                message="无法连接测试环境",
            )
        latency_ms = int((perf_counter() - started_at) * 1000)
        if 200 <= status_code < 300:
            return TestEnvironmentConnectionResultVO(
                success=True,
                status_code=status_code,
                latency_ms=latency_ms,
                message="连接成功",
            )
        if 300 <= status_code < 400:
            return TestEnvironmentConnectionResultVO(
                success=False,
                status_code=status_code,
                latency_ms=latency_ms,
                message="目标返回重定向，系统未自动跟随",
            )
        return TestEnvironmentConnectionResultVO(
            success=False,
            status_code=status_code,
            latency_ms=latency_ms,
            message=f"目标返回 HTTP {status_code}",
        )
