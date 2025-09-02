from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.api.deps import get_current_user, get_current_verified_user, get_user_organization
from app.models.user import User
from app.models.organization import Organization
from app.models.compliance import ComplianceTask, TaskStatus, TaskPriority
from app.models.jurisdiction import Jurisdiction
from app.services.seed_data import database_seeder
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    jurisdiction_id: Optional[UUID] = Query(None),
    assigned_to: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """List all compliance tasks for organization with optional filters"""
    
    # Ensure sample data exists
    result = await db.execute(select(ComplianceTask).where(
        ComplianceTask.organization_id == organization.id
    ))
    if not result.first():
        await database_seeder.create_sample_compliance_tasks(db, organization.id)
        await db.commit()
    
    # Build query with filters
    query = select(ComplianceTask).options(
        selectinload(ComplianceTask.jurisdiction),
        selectinload(ComplianceTask.assignee)
    ).where(
        ComplianceTask.organization_id == organization.id
    )
    
    if status:
        try:
            status_enum = TaskStatus(status)
            query = query.where(ComplianceTask.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if priority:
        try:
            priority_enum = TaskPriority(priority)
            query = query.where(ComplianceTask.priority == priority_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")
    
    if jurisdiction_id:
        query = query.where(ComplianceTask.jurisdiction_id == jurisdiction_id)
    
    if assigned_to:
        query = query.where(ComplianceTask.assignee_id == assigned_to)
    
    # Order by priority and due date
    query = query.order_by(
        ComplianceTask.priority.asc(),
        ComplianceTask.due_date.asc(),
        ComplianceTask.created_at.desc()
    )
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    tasks_data = []
    for task in tasks:
        task_data = {
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority.value,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "estimated_hours": task.estimated_hours,
            "actual_hours": task.actual_hours,
            "completion_percentage": task.completion_percentage,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "jurisdiction": {
                "id": str(task.jurisdiction.id),
                "name": task.jurisdiction.name,
                "regulation_type": task.jurisdiction.regulation_type.value
            } if task.jurisdiction else None,
            "assigned_user": {
                "id": str(task.assignee.id),
                "email": task.assignee.email,
                "full_name": task.assignee.full_name
            } if task.assignee else None
        }
        tasks_data.append(task_data)
    
    return {
        "tasks": tasks_data,
        "total": len(tasks_data),
        "filters": {
            "status": status,
            "priority": priority,
            "jurisdiction_id": str(jurisdiction_id) if jurisdiction_id else None,
            "assigned_to": str(assigned_to) if assigned_to else None
        }
    }


@router.post("/")
async def create_task(
    task_data: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Create a new compliance task"""
    
    # Validate required fields
    required_fields = ["title", "description", "jurisdiction_id", "priority", "due_date"]
    for field in required_fields:
        if field not in task_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    # Validate jurisdiction exists
    jurisdiction_result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == task_data["jurisdiction_id"])
    )
    jurisdiction = jurisdiction_result.scalar_one_or_none()
    if not jurisdiction:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    
    # Parse due date
    try:
        due_date = datetime.fromisoformat(task_data["due_date"].replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid due_date format")
    
    # Create task
    task = ComplianceTask(
        organization_id=organization.id,
        jurisdiction_id=task_data["jurisdiction_id"],
        title=task_data["title"],
        description=task_data["description"],
        priority=TaskPriority(task_data["priority"]),
        status=TaskStatus(task_data.get("status", "todo")),
        due_date=due_date,
        estimated_hours=task_data.get("estimated_hours"),
        assignee_id=task_data.get("assigned_to"),
        created_at=datetime.utcnow()
    )
    
    db.add(task)
    await db.flush()
    await db.refresh(task)
    await db.commit()
    
    return {
        "id": str(task.id),
        "message": "Task created successfully"
    }


@router.get("/{task_id}")
async def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get task details by ID"""
    
    result = await db.execute(
        select(ComplianceTask).options(
            selectinload(ComplianceTask.jurisdiction),
            selectinload(ComplianceTask.assignee),
        ).where(
            and_(
                ComplianceTask.id == task_id,
                ComplianceTask.organization_id == organization.id
            )
        )
    )
    
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "estimated_hours": task.estimated_hours,
        "actual_hours": task.actual_hours,
        "completion_percentage": task.completion_percentage,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "jurisdiction": {
            "id": str(task.jurisdiction.id),
            "name": task.jurisdiction.name,
            "code": task.jurisdiction.code,
            "description": task.jurisdiction.description
        } if task.jurisdiction else None,
        "assigned_user": {
            "id": str(task.assignee.id),
            "email": task.assignee.email,
            "full_name": task.assignee.full_name
        } if task.assignee else None,
        "created_by": None
    }


@router.put("/{task_id}")
async def update_task(
    task_id: UUID,
    task_data: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing task"""
    
    # Get task
    result = await db.execute(
        select(ComplianceTask).where(
            and_(
                ComplianceTask.id == task_id,
                ComplianceTask.organization_id == organization.id
            )
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update fields
    update_fields = {}
    
    if "title" in task_data:
        update_fields["title"] = task_data["title"]
    
    if "description" in task_data:
        update_fields["description"] = task_data["description"]
    
    if "status" in task_data:
        try:
            update_fields["status"] = TaskStatus(task_data["status"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {task_data['status']}")
    
    if "priority" in task_data:
        try:
            update_fields["priority"] = TaskPriority(task_data["priority"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {task_data['priority']}")
    
    if "due_date" in task_data:
        try:
            update_fields["due_date"] = datetime.fromisoformat(task_data["due_date"].replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid due_date format")
    
    if "estimated_hours" in task_data:
        update_fields["estimated_hours"] = task_data["estimated_hours"]
    
    if "actual_hours" in task_data:
        update_fields["actual_hours"] = task_data["actual_hours"]
    
    if "completion_percentage" in task_data:
        percentage = task_data["completion_percentage"]
        if not 0 <= percentage <= 100:
            raise HTTPException(status_code=400, detail="Completion percentage must be between 0 and 100")
        update_fields["completion_percentage"] = percentage
    
    if "assigned_to" in task_data:
        update_fields["assignee_id"] = task_data["assigned_to"]
    
    if update_fields:
        update_fields["updated_at"] = datetime.utcnow()
        
        await db.execute(
            update(ComplianceTask).where(
                ComplianceTask.id == task_id
            ).values(**update_fields)
        )
        await db.commit()
    
    return {"message": "Task updated successfully"}


@router.delete("/{task_id}")
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Delete a task"""
    
    result = await db.execute(
        select(ComplianceTask).where(
            and_(
                ComplianceTask.id == task_id,
                ComplianceTask.organization_id == organization.id
            )
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    await db.delete(task)
    await db.commit()
    
    return {"message": "Task deleted successfully"}


@router.get("/stats/summary")
async def get_task_stats(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get task statistics for organization"""
    
    # Get task counts by status
    status_result = await db.execute(
        select(
            ComplianceTask.status,
            func.count(ComplianceTask.id).label("count")
        ).where(
            ComplianceTask.organization_id == organization.id
        ).group_by(ComplianceTask.status)
    )
    
    status_stats = {}
    total_tasks = 0
    for status, count in status_result:
        status_stats[status.value] = count
        total_tasks += count
    
    # Get priority breakdown
    priority_result = await db.execute(
        select(
            ComplianceTask.priority,
            func.count(ComplianceTask.id).label("count")
        ).where(
            ComplianceTask.organization_id == organization.id
        ).group_by(ComplianceTask.priority)
    )
    
    priority_stats = {}
    for priority, count in priority_result:
        priority_stats[priority.value] = count
    
    # Get overdue tasks
    overdue_result = await db.execute(
        select(func.count(ComplianceTask.id)).where(
            and_(
                ComplianceTask.organization_id == organization.id,
                ComplianceTask.due_date < datetime.utcnow(),
                ComplianceTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
            )
        )
    )
    overdue_count = overdue_result.scalar() or 0
    
    # Get completion rate
    completed_result = await db.execute(
        select(func.count(ComplianceTask.id)).where(
            and_(
                ComplianceTask.organization_id == organization.id,
                ComplianceTask.status == TaskStatus.COMPLETED
            )
        )
    )
    completed_count = completed_result.scalar() or 0
    completion_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0
    
    return {
        "total_tasks": total_tasks,
        "status_breakdown": status_stats,
        "priority_breakdown": priority_stats,
        "overdue_tasks": overdue_count,
        "completion_rate": round(completion_rate, 1)
    }


@router.post("/{task_id}/assign")
async def assign_task(
    task_id: UUID,
    assignment_data: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Assign task to a user"""
    
    if "user_id" not in assignment_data:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    # Get task
    task_result = await db.execute(
        select(ComplianceTask).where(
            and_(
                ComplianceTask.id == task_id,
                ComplianceTask.organization_id == organization.id
            )
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Verify user exists and belongs to organization
    user_result = await db.execute(
        select(User).where(User.id == assignment_data["user_id"])
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update task assignment
    await db.execute(
        update(ComplianceTask).where(
            ComplianceTask.id == task_id
        ).values(
            assignee_id=assignment_data["user_id"],
            updated_at=datetime.utcnow()
        )
    )
    await db.commit()
    
    return {"message": f"Task assigned to {user.full_name or user.email}"}


@router.get("/assignment-suggestions")
async def get_assignment_suggestions(
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get suggestions for task assignments based on team members' roles and workload"""
    
    try:
        from app.services.task_assignment_service import get_task_assignment_service
        
        assignment_service = await get_task_assignment_service(db)
        suggestions = await assignment_service.get_assignment_suggestions(
            str(organization.id), 
            limit=10
        )
        
        return {
            "suggestions": suggestions,
            "total_members": len(suggestions)
        }
    except Exception as e:
        logger.error(f"Error getting assignment suggestions: {str(e)}")
        return {
            "suggestions": [],
            "total_members": 0,
            "error": "Failed to get assignment suggestions"
        }


@router.post("/suggest-assignee")
async def suggest_task_assignee(
    task_data: dict,
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_user_organization),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-powered suggestion for the best assignee for a specific task"""
    
    try:
        from app.services.task_assignment_service import get_task_assignment_service
        
        assignment_service = await get_task_assignment_service(db)
        
        # Extract task details from request
        task_title = task_data.get("title", "")
        task_description = task_data.get("description", "")
        jurisdiction_id = task_data.get("jurisdiction_id")
        task_type = task_data.get("task_type")
        
        suggested_user, reason = await assignment_service.suggest_assignee(
            str(organization.id),
            task_title,
            task_description,
            jurisdiction_id,
            task_type
        )
        
        if suggested_user:
            return {
                "suggested_assignee": {
                    "user_id": str(suggested_user.id),
                    "name": suggested_user.full_name or suggested_user.email,
                    "email": suggested_user.email
                },
                "reason": reason,
                "confidence": "high"
            }
        else:
            return {
                "suggested_assignee": None,
                "reason": reason,
                "confidence": "low"
            }
            
    except Exception as e:
        logger.error(f"Error suggesting assignee: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to suggest assignee"
        )