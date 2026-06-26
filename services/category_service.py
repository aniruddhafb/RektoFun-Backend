"""
Category service for database operations on categories.
"""

from datetime import datetime
from typing import Any, Optional

from supabase import Client

from config import get_supabase_client


class CategoryService:
    """Service for managing categories"""

    def __init__(self, supabase: Optional[Client] = None):
        self.supabase = supabase or get_supabase_client()

    def get_all_categories(self) -> list[dict[str, Any]]:
        """Get all categories"""
        response = self.supabase.table("category").select("*").order("created_at", desc=True).execute()
        return response.data if response.data else []

    def get_category_by_id(self, category_id: int) -> Optional[dict[str, Any]]:
        """Get a category by ID"""
        response = self.supabase.table("category").select("*").eq("id", category_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None

    def get_category_by_name(self, category_name: str) -> Optional[dict[str, Any]]:
        """Get a category by name"""
        response = self.supabase.table("category").select("*").eq("category", category_name).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None

    def create_category(self, category_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new category"""
        # Check if category already exists
        existing = self.get_category_by_name(category_data["category"])
        if existing:
            raise ValueError(f"Category '{category_data['category']}' already exists")

        response = self.supabase.table("category").insert(category_data).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        raise RuntimeError("Failed to create category")

    def update_category(self, category_id: int, category_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Update an existing category"""
        # Check if category exists
        existing = self.get_category_by_id(category_id)
        if not existing:
            return None

        # If category name is being changed, check for duplicates
        if "category" in category_data and category_data["category"] != existing["category"]:
            duplicate = self.get_category_by_name(category_data["category"])
            if duplicate:
                raise ValueError(f"Category '{category_data['category']}' already exists")

        response = (
            self.supabase.table("category")
            .update(category_data)
            .eq("id", category_id)
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None

    def delete_category(self, category_id: int) -> bool:
        """Delete a category by ID"""
        # Check if category exists
        existing = self.get_category_by_id(category_id)
        if not existing:
            return False

        response = self.supabase.table("category").delete().eq("id", category_id).execute()
        return response.data is not None and len(response.data) > 0

    def get_categories_with_challenges(self) -> list[dict[str, Any]]:
        """Get categories that have at least one challenge"""
        response = (
            self.supabase.table("category")
            .select("*")
            .gt("challenges_count", 0)
            .order("challenges_count", desc=True)
            .execute()
        )
        return response.data if response.data else []

    def get_child_categories(self, parent_category: str) -> list[dict[str, Any]]:
        """Get all child categories for a given parent category"""
        response = (
            self.supabase.table("category")
            .select("*")
            .ilike("parent_category", parent_category)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data if response.data else []

    def get_parent_categories(self) -> list[dict[str, Any]]:
        """Get all parent categories (categories with null parent_category)"""
        response = (
            self.supabase.table("category")
            .select("*")
            .is_("parent_category", None)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data if response.data else []

    def increment_challenges_count(self, category_name: str) -> Optional[dict[str, Any]]:
        """Increment the challenges count for a category"""
        existing = self.get_category_by_name(category_name)
        if not existing:
            return None

        new_count = (existing.get("challenges_count") or 0) + 1
        response = (
            self.supabase.table("category")
            .update({"challenges_count": new_count})
            .eq("category", category_name)
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None

    def decrement_challenges_count(self, category_name: str) -> Optional[dict[str, Any]]:
        """Decrement the challenges count for a category"""
        existing = self.get_category_by_name(category_name)
        if not existing:
            return None

        current_count = existing.get("challenges_count") or 0
        new_count = max(0, current_count - 1)
        response = (
            self.supabase.table("category")
            .update({"challenges_count": new_count})
            .eq("category", category_name)
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None


# Singleton instance for use across the application
_category_service: CategoryService | None = None


def get_category_service() -> CategoryService:
    """Get or create the category service singleton"""
    global _category_service
    if _category_service is None:
        _category_service = CategoryService()
    return _category_service