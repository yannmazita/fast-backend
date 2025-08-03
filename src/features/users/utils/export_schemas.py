# src.features.users.utils.export_schemas
from src.core.schemas import Base as CoreBaseSchema
from src.features.auth.schemas import OAuthAccountRead
from src.features.users.schemas import BanRead, UserRead


class UserDataExport(CoreBaseSchema):
    profile: UserRead
    oauth_accounts: list[OAuthAccountRead]
    ban_history: list[BanRead]
