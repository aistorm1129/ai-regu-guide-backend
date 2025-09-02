from typing import List, Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.models.user import User
from app.models.organization import Organization, UserOrganization, UserRole
from app.models.compliance import ComplianceTask, TaskStatus
from app.models.jurisdiction import Jurisdiction
import re


class TaskAssignmentService:
    """Service for suggesting task assignments based on roles, expertise, and workload"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def suggest_assignee(
        self, 
        organization_id: str,
        task_title: str, 
        task_description: str,
        jurisdiction_id: Optional[str] = None,
        task_type: Optional[str] = None
    ) -> Tuple[Optional[User], str]:
        """
        Suggest the best assignee for a task based on multiple factors
        Returns (suggested_user, reason)
        """
        
        # Get organization members with their roles
        org_members_result = await self.db.execute(
            select(User, UserOrganization.role)
            .join(UserOrganization)
            .where(UserOrganization.organization_id == organization_id)
        )
        org_members = org_members_result.all()
        
        if not org_members:
            return None, "No organization members found"
        
        # Score each member based on various factors
        member_scores = []
        
        for user, role in org_members:
            score = await self._calculate_user_score(
                user, role, task_title, task_description, jurisdiction_id, task_type
            )
            member_scores.append((user, role, score))
        
        # Sort by score and return the best candidate
        member_scores.sort(key=lambda x: x[2], reverse=True)
        
        if member_scores:
            best_user, best_role, best_score = member_scores[0]
            reason = self._generate_assignment_reason(best_user, best_role, best_score)
            return best_user, reason
        
        return None, "No suitable assignee found"
    
    async def _calculate_user_score(
        self,
        user: User,
        role: UserRole,
        task_title: str,
        task_description: str,
        jurisdiction_id: Optional[str] = None,
        task_type: Optional[str] = None
    ) -> float:
        """Calculate a score for how well a user fits a task"""
        
        score = 0.0
        
        # Role-based scoring
        role_scores = {
            UserRole.OWNER: 0.7,  # Owners can do everything but may be busy
            UserRole.ADMIN: 0.9,  # Admins are good for most tasks
            UserRole.COMPLIANCE_OFFICER: 1.0,  # Best for compliance tasks
            UserRole.MEMBER: 0.3,   # Basic members
            UserRole.VIEWER: 0.1    # Viewers have limited access
        }
        score += role_scores.get(role, 0.3)
        
        # Keyword-based scoring based on task content
        task_content = f"{task_title} {task_description}".lower()
        
        # Compliance-specific keywords
        compliance_keywords = [
            'compliance', 'risk assessment', 'documentation', 'training',
            'monitoring', 'reporting', 'assessment', 'framework', 'standard',
            'legal', 'regulation', 'audit', 'policy', 'gdpr', 'privacy', 
            'data protection', 'contract', 'agreement', 'law'
        ]
        if role == UserRole.COMPLIANCE_OFFICER and any(keyword in task_content for keyword in compliance_keywords):
            score += 0.5
        
        # Admin gets bonus for general administrative tasks
        admin_keywords = [
            'coordination', 'management', 'planning', 'organization', 
            'oversight', 'administration', 'team', 'project'
        ]
        if role == UserRole.ADMIN and any(keyword in task_content for keyword in admin_keywords):
            score += 0.3
        
        # Workload factor (users with fewer active tasks get higher scores)
        active_tasks_result = await self.db.execute(
            select(func.count(ComplianceTask.id))
            .where(
                and_(
                    ComplianceTask.assignee_id == user.id,
                    ComplianceTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
                )
            )
        )
        active_tasks_count = active_tasks_result.scalar() or 0
        
        # Penalty for high workload
        workload_penalty = min(active_tasks_count * 0.1, 0.3)  # Max 30% penalty
        score -= workload_penalty
        
        # Bonus for jurisdiction expertise (if jurisdiction is specified)
        if jurisdiction_id:
            # Check if user has worked on tasks for this jurisdiction before
            jurisdiction_experience_result = await self.db.execute(
                select(func.count(ComplianceTask.id))
                .where(
                    and_(
                        ComplianceTask.assignee_id == user.id,
                        ComplianceTask.jurisdiction_id == jurisdiction_id,
                        ComplianceTask.status == TaskStatus.COMPLETED
                    )
                )
            )
            jurisdiction_experience = jurisdiction_experience_result.scalar() or 0
            
            if jurisdiction_experience > 0:
                score += min(jurisdiction_experience * 0.05, 0.2)  # Max 20% bonus
        
        return max(score, 0.0)  # Ensure non-negative score
    
    def _generate_assignment_reason(self, user: User, role: UserRole, score: float) -> str:
        """Generate a human-readable reason for the assignment suggestion"""
        
        reasons = []
        
        if role == UserRole.COMPLIANCE_OFFICER:
            reasons.append("Compliance Officer role")
        elif role == UserRole.ADMIN:
            reasons.append("Administrative privileges")
        elif role == UserRole.OWNER:
            reasons.append("Organization owner")
        elif role == UserRole.MEMBER:
            reasons.append("Team member")
        
        if score > 0.8:
            reasons.append("high suitability score")
        elif score > 0.6:
            reasons.append("good suitability score")
        
        if len(reasons) == 0:
            return f"Suggested based on availability"
        
        return f"Suggested based on {', '.join(reasons)}"
    
    async def get_assignment_suggestions(
        self, 
        organization_id: str,
        limit: int = 3
    ) -> List[Dict]:
        """Get a list of all members with their assignment suitability"""
        
        org_members_result = await self.db.execute(
            select(User, UserOrganization.role)
            .join(UserOrganization)
            .where(UserOrganization.organization_id == organization_id)
        )
        org_members = org_members_result.all()
        
        suggestions = []
        
        for user, role in org_members:
            # Get current workload
            active_tasks_result = await self.db.execute(
                select(func.count(ComplianceTask.id))
                .where(
                    and_(
                        ComplianceTask.assignee_id == user.id,
                        ComplianceTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
                    )
                )
            )
            active_tasks = active_tasks_result.scalar() or 0
            
            # Get completed tasks
            completed_tasks_result = await self.db.execute(
                select(func.count(ComplianceTask.id))
                .where(
                    and_(
                        ComplianceTask.assignee_id == user.id,
                        ComplianceTask.status == TaskStatus.COMPLETED
                    )
                )
            )
            completed_tasks = completed_tasks_result.scalar() or 0
            
            suggestions.append({
                "user_id": str(user.id),
                "name": user.full_name or user.email,
                "email": user.email,
                "role": role.value,
                "active_tasks": active_tasks,
                "completed_tasks": completed_tasks,
                "workload_level": "High" if active_tasks > 5 else "Medium" if active_tasks > 2 else "Low",
                "expertise_areas": self._get_user_expertise_areas(role)
            })
        
        # Sort by workload (ascending) and role priority
        role_priority = {
            UserRole.COMPLIANCE_OFFICER: 1,
            UserRole.ADMIN: 2,
            UserRole.OWNER: 3,
            UserRole.MEMBER: 4,
            UserRole.VIEWER: 5
        }
        
        suggestions.sort(key=lambda x: (x["active_tasks"], role_priority.get(UserRole(x["role"]), 10)))
        
        return suggestions[:limit]
    
    def _get_user_expertise_areas(self, role: UserRole) -> List[str]:
        """Get expertise areas based on role"""
        
        expertise_map = {
            UserRole.COMPLIANCE_OFFICER: [
                "Compliance Management", "Risk Assessment", "Audit Preparation", 
                "Regulatory Analysis", "Legal Analysis", "Policy Review",
                "Documentation", "Privacy Law"
            ],
            UserRole.ADMIN: [
                "Project Management", "Team Coordination", "Process Optimization",
                "Reporting", "General Administration", "System Management"
            ],
            UserRole.OWNER: [
                "Strategic Planning", "Business Analysis", "Stakeholder Management",
                "Decision Making", "Resource Allocation", "Leadership"
            ],
            UserRole.MEMBER: [
                "General Support", "Data Entry", "Basic Analysis", "Task Execution"
            ],
            UserRole.VIEWER: [
                "Monitoring", "Observation", "Basic Support"
            ]
        }
        
        return expertise_map.get(role, ["General Support"])


# Factory function
async def get_task_assignment_service(db: AsyncSession) -> TaskAssignmentService:
    return TaskAssignmentService(db)