"""
Category models for request/response validation and data transfer.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    """Base category model with common attributes"""
    category: str = Field(..., description="Category name")
    challenges_count: Optional[int] = Field(None, description="Number of challenges in this category")
    parent_category: Optional[str] = Field(None, description="Child category name")


class CategoryCreate(CategoryBase):
    """Model for creating a new category"""
    pass


class CategoryUpdate(BaseModel):
    """Model for updating an existing category - all fields optional"""
    category: Optional[str] = Field(None, description="Category name")
    challenges_count: Optional[int] = Field(None, description="Number of challenges in this category")
    parent_category: Optional[str] = Field(None, description="Child category name")


class CategoryResponse(CategoryBase):
    """Model for category response data"""
    id: int = Field(..., description="Unique category ID")
    created_at: datetime = Field(..., description="Category creation timestamp")

    class Config:
        from_attributes = True


class CategoryListResponse(BaseModel):
    """Model for list of categories response"""
    categories: list[CategoryResponse]
    total: int = Field(..., description="Total number of categories")