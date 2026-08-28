from pydantic import Field

from app.core.constants import ProjectMemberRole
from app.schemas.camel_model import CamelModel


class TestProjectMemberCreateDTO(CamelModel):
    """向项目中添加成员。"""

    user_id: int = Field(gt=0)
    member_role: ProjectMemberRole = ProjectMemberRole.MEMBER


class TestProjectMemberUpdateDTO(CamelModel):
    """修改已有项目成员的角色。"""

    member_role: ProjectMemberRole
