from datetime import datetime

from app.core.constants import ProjectMemberRole
from app.schemas.camel_model import CamelModel


class TestProjectMemberVO(CamelModel):
    """项目成员列表中的一条成员信息。"""

    project_id: int
    user_id: int
    username: str
    display_name: str
    member_role: ProjectMemberRole
    created_at: datetime


class TestProjectMemberOptionVO(CamelModel):
    """添加成员时供前端下拉框选择的系统用户。"""

    user_id: int
    username: str
    display_name: str
