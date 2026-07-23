from functools import lru_cache
from typing import Optional

from accounts.repository import AccountRepository, SupabaseAccountRepository
from config import get_account_settings


@lru_cache(maxsize=1)
def get_account_repository() -> Optional[AccountRepository]:
    settings = get_account_settings()
    if not settings.configured:
        return None
    return SupabaseAccountRepository(settings.supabase_url, settings.supabase_service_role_key)
