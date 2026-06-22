"""
Category API routes for CRUD operations.
"""

from fastapi import APIRouter, HTTPException, status

from models.category import CategoryCreate, CategoryResponse, CategoryUpdate
from services.category_service import get_category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories():
    """Get all categories"""
    service = get_category_service()
    categories = service.get_all_categories()
    return categories


@router.get("/with-challenges", response_model=list[CategoryResponse])
async def list_categories_with_challenges():
    """Get categories that have at least one challenge"""
    service = get_category_service()
    categories = service.get_categories_with_challenges()
    return categories


@router.get("/by-parent/{parent_category}", response_model=list[CategoryResponse])
async def get_child_categories(parent_category: str):
    """Get all child categories for a given parent category"""
    service = get_category_service()
    categories = service.get_child_categories(parent_category)
    return categories


@router.get("/parent-categories", response_model=list[CategoryResponse])
async def get_parent_categories():
    """Get all parent categories (categories with null parent_category)"""
    service = get_category_service()
    categories = service.get_parent_categories()
    return categories


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: int):
    """Get a category by ID"""
    service = get_category_service()
    category = service.get_category_by_id(category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with ID {category_id} not found"
        )
    return category


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(category: CategoryCreate):
    """Create a new category"""
    service = get_category_service()
    try:
        category_data = category.model_dump(exclude_unset=True)
        created = service.create_category(category_data)
        return created
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create category: {str(e)}"
        )


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(category_id: int, category: CategoryUpdate):
    """Update an existing category"""
    service = get_category_service()
    try:
        category_data = category.model_dump(exclude_unset=True)
        if not category_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update"
            )

        updated = service.update_category(category_id, category_data)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID {category_id} not found"
            )
        return updated
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update category: {str(e)}"
        )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int):
    """Delete a category by ID"""
    service = get_category_service()
    deleted = service.delete_category(category_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with ID {category_id} not found"
        )
    return None