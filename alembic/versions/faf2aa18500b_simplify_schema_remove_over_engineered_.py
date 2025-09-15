"""Simplify schema remove over-engineered components

Revision ID: faf2aa18500b
Revises: 5eb60f8328a8
Create Date: 2025-09-10 00:14:21.297888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'faf2aa18500b'
down_revision: Union[str, None] = '5eb60f8328a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop over-engineered tables if they exist
    try:
        op.drop_table('system_compliance')
    except:
        pass
    try:
        op.drop_table('ai_systems')
    except:
        pass
    try:
        op.drop_table('oauth_accounts')
    except:
        pass
    
    # Simplify compliance_tasks table - remove unnecessary columns
    op.drop_column('compliance_tasks', 'estimated_hours')
    op.drop_column('compliance_tasks', 'actual_hours')
    op.drop_column('compliance_tasks', 'completion_percentage')
    op.drop_column('compliance_tasks', 'task_metadata')
    
    # Add fields for automatic task generation from compliance gaps
    op.add_column('compliance_tasks', sa.Column('source_type', sa.String(50), nullable=True))  # 'gap_analysis', 'manual'
    op.add_column('compliance_tasks', sa.Column('source_id', sa.UUID(), nullable=True))  # Reference to gap/requirement
    op.add_column('compliance_tasks', sa.Column('requirement_id', sa.String(255), nullable=True))  # Specific requirement ID
    
    # Simplify documents table - remove unnecessary metadata
    op.drop_column('documents', 'file_size')
    op.drop_column('documents', 'mime_type')
    op.drop_column('documents', 'file_metadata')
    
    # Note: Using string columns for simplicity instead of enums
    
    # Add core compliance engine fields to organization_jurisdictions
    # This will track the 3-tier compliance status per requirement
    op.create_table('compliance_requirements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('jurisdiction_id', sa.UUID(), nullable=False),
        sa.Column('requirement_id', sa.String(100), nullable=False),  # e.g., 'AI_ACT_5.1'
        sa.Column('category', sa.String(255), nullable=False),  # e.g., 'Transparency', 'Risk Management'
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('criticality', sa.String(20), nullable=False),  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['jurisdiction_id'], ['jurisdictions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jurisdiction_id', 'requirement_id')
    )
    
    # Track compliance status for each requirement per organization
    op.create_table('compliance_assessments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('requirement_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),  # 'COMPLIANT', 'PARTIAL', 'NON_COMPLIANT', 'NOT_ASSESSED'
        sa.Column('evidence_type', sa.String(50), nullable=True),  # 'document' or 'form_response'
        sa.Column('evidence_id', sa.UUID(), nullable=True),  # Reference to document or form response
        sa.Column('explanation', sa.Text(), nullable=True),  # AI-generated explanation
        sa.Column('gap_description', sa.Text(), nullable=True),  # What's missing for compliance
        sa.Column('assessed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_id'], ['compliance_requirements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Simplify document_analyses - focus on core analysis
    op.add_column('document_analyses', sa.Column('jurisdiction_id', sa.UUID(), nullable=True))
    op.create_foreign_key(None, 'document_analyses', 'jurisdictions', ['jurisdiction_id'], ['id'])


def downgrade() -> None:
    # Reverse the changes
    op.drop_constraint(None, 'document_analyses', type_='foreignkey')
    op.drop_column('document_analyses', 'jurisdiction_id')
    
    op.drop_table('compliance_assessments')
    op.drop_table('compliance_requirements')
    
    op.execute("DROP TYPE IF EXISTS compliancestatusnew CASCADE")
    op.execute("DROP TYPE IF EXISTS criticality CASCADE")
    
    # Restore document columns
    op.add_column('documents', sa.Column('file_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('documents', sa.Column('mime_type', sa.String(100), nullable=True))
    op.add_column('documents', sa.Column('file_size', sa.Integer(), nullable=True))
    
    # Restore task columns
    op.drop_column('compliance_tasks', 'requirement_id')
    op.drop_column('compliance_tasks', 'source_id')
    op.drop_column('compliance_tasks', 'source_type')
    op.add_column('compliance_tasks', sa.Column('task_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('compliance_tasks', sa.Column('completion_percentage', sa.Float(), nullable=True))
    op.add_column('compliance_tasks', sa.Column('actual_hours', sa.Float(), nullable=True))
    op.add_column('compliance_tasks', sa.Column('estimated_hours', sa.Float(), nullable=True))
    
    # Restore tables
    op.create_table('oauth_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('oauth_name', sa.String(100), nullable=False),
        sa.Column('oauth_id', sa.String(255), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('ai_systems',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('system_type', sa.String(100), nullable=True),
        sa.Column('risk_level', sa.Enum('MINIMAL', 'LIMITED', 'HIGH', 'UNACCEPTABLE', name='airisklevel'), nullable=True),
        sa.Column('is_high_risk', sa.Boolean(), nullable=True),
        sa.Column('deployment_date', sa.DateTime(), nullable=True),
        sa.Column('last_assessment', sa.DateTime(), nullable=True),
        sa.Column('system_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('system_compliance',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('system_id', sa.UUID(), nullable=False),
        sa.Column('jurisdiction_id', sa.UUID(), nullable=False),
        sa.Column('compliance_score', sa.Float(), nullable=True),
        sa.Column('last_assessment', sa.DateTime(), nullable=True),
        sa.Column('assessment_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('gaps_identified', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('remediation_plan', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['jurisdiction_id'], ['jurisdictions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['system_id'], ['ai_systems.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
