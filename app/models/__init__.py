"""
Import every model so SQLModel.metadata picks them all up.
Alembic and the session engine rely on this single import point.
"""

from app.models.activity_log import ActivityLog  # noqa: F401
from app.models.comment import Comment  # noqa: F401
from app.models.issue import Issue, IssuePriority, IssueStatus, IssueType  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.sprint import Sprint, SprintStatus  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.watcher import Watcher  # noqa: F401
