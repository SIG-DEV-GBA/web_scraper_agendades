"""Supabase database layer -- split from the original monolithic supabase_client.py.

Public API:
    SupabaseClient        -- facade class (keeps the same interface)
    get_supabase_client   -- singleton factory
"""

from src.core.db.client import SupabaseClient, get_supabase_client

__all__ = ["SupabaseClient", "get_supabase_client"]
