"""Comprehensive schema alignment with current models

Revision ID: schema_align_2025
Revises: ca1bec26d6cd
Create Date: 2025-01-09 02:00:00.000000

This migration completely restructures the database to match the current SQLAlchemy models.
Since there's no production data, we can drop and recreate tables as needed.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'schema_align_2025'
down_revision: Union[str, None] = 'ca1bec26d6cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop all existing tables in reverse dependency order to avoid FK constraint issues
    op.execute("DROP TABLE IF EXISTS form_responses CASCADE")
    op.execute("DROP TABLE IF EXISTS form_questions CASCADE")
    op.execute("DROP TABLE IF EXISTS compliance_reports CASCADE")
    op.execute("DROP TABLE IF EXISTS system_compliance CASCADE")
    op.execute("DROP TABLE IF EXISTS compliance_tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS ai_systems CASCADE")
    op.execute("DROP TABLE IF EXISTS document_analysis CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS organization_jurisdictions CASCADE")
    op.execute("DROP TABLE IF EXISTS user_organizations CASCADE")
    op.execute("DROP TABLE IF EXISTS jurisdictions CASCADE")
    op.execute("DROP TABLE IF EXISTS organizations CASCADE")
    op.execute("DROP TABLE IF EXISTS oauth_accounts CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    
    # Drop any existing enum types
    op.execute("DROP TYPE IF EXISTS plantype CASCADE")
    op.execute("DROP TYPE IF EXISTS questiontype CASCADE")
    op.execute("DROP TYPE IF EXISTS userrole CASCADE")
    op.execute("DROP TYPE IF EXISTS organizationsize CASCADE")
    op.execute("DROP TYPE IF EXISTS regulationtype CASCADE")
    op.execute("DROP TYPE IF EXISTS compliancestatus CASCADE")
    op.execute("DROP TYPE IF EXISTS documenttype CASCADE")
    op.execute("DROP TYPE IF EXISTS analysisstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS taskstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS taskpriority CASCADE")
    op.execute("DROP TYPE IF EXISTS reporttype CASCADE")
    op.execute("DROP TYPE IF EXISTS airisklevel CASCADE")
    
    # Create enum types for current models
    bind = op.get_bind()
    
    # Helper function to safely create enums
    def safe_create_enum(name, values):
        enum_type = sa.Enum(*values, name=name)
        try:
            enum_type.create(bind, checkfirst=True)
        except Exception:
            # Enum already exists, skip
            pass
        return enum_type
    
    plantype_enum = safe_create_enum('plantype', ['BASIC', 'PROFESSIONAL'])
    userrole_enum = safe_create_enum('userrole', ['OWNER', 'ADMIN', 'COMPLIANCE_OFFICER', 'MEMBER', 'VIEWER'])
    organizationsize_enum = safe_create_enum('organizationsize', ['SMALL', 'MEDIUM', 'LARGE', 'ENTERPRISE'])
    regulationtype_enum = safe_create_enum('regulationtype', ['EU_AI_ACT', 'US_AI_GOVERNANCE', 'ISO_42001', 'GDPR', 'CCPA', 'CUSTOM'])
    compliancestatus_enum = safe_create_enum('compliancestatus', ['NOT_STARTED', 'IN_PROGRESS', 'PARTIALLY_COMPLIANT', 'COMPLIANT', 'NON_COMPLIANT'])
    documenttype_enum = safe_create_enum('documenttype', ['POLICY', 'PROCEDURE', 'RISK_ASSESSMENT', 'AUDIT_REPORT', 'COMPLIANCE_CERTIFICATE', 'TECHNICAL_DOCUMENTATION', 'DATA_PROTECTION', 'OTHER'])
    analysisstatus_enum = safe_create_enum('analysisstatus', ['PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED'])
    taskstatus_enum = safe_create_enum('taskstatus', ['TODO', 'IN_PROGRESS', 'REVIEW', 'COMPLETED', 'BLOCKED', 'CANCELLED'])
    taskpriority_enum = safe_create_enum('taskpriority', ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
    reporttype_enum = safe_create_enum('reporttype', ['COMPLIANCE_SUMMARY', 'GAP_ANALYSIS', 'RISK_ASSESSMENT', 'AUDIT_REPORT', 'EXECUTIVE_SUMMARY', 'DETAILED_COMPLIANCE'])
    airisklevel_enum = safe_create_enum('airisklevel', ['MINIMAL', 'LIMITED', 'HIGH', 'UNACCEPTABLE'])
    questiontype_enum = safe_create_enum('questiontype', ['RADIO', 'TEXTAREA', 'SELECT', 'INPUT'])
    
    # Create users table (matching current User model)
    op.create_table('users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('plan', plantype_enum, nullable=False, server_default='BASIC'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('is_verified', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('is_superuser', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    
    # Create oauth_accounts table (matching current OAuthAccount model)
    op.create_table('oauth_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('oauth_name', sa.String(length=100), nullable=False),
        sa.Column('oauth_id', sa.String(length=255), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create organizations table (matching current Organization model)
    op.create_table('organizations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('size', organizationsize_enum, nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create user_organizations table (matching current UserOrganization model)
    op.create_table('user_organizations',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('role', userrole_enum, nullable=False, server_default='MEMBER'),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'organization_id')
    )
    
    # Create jurisdictions table (matching current Jurisdiction model)
    op.create_table('jurisdictions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('regulation_type', regulationtype_enum, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('requirements', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.Column('effective_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # Create organization_jurisdictions table (matching current OrganizationJurisdiction model)
    op.create_table('organization_jurisdictions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('jurisdiction_id', sa.UUID(), nullable=False),
        sa.Column('compliance_status', compliancestatus_enum, nullable=False, server_default='NOT_STARTED'),
        sa.Column('compliance_score', sa.Float(), nullable=True),
        sa.Column('setup_date', sa.DateTime(), nullable=True),
        sa.Column('last_assessment_date', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['jurisdiction_id'], ['jurisdictions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'jurisdiction_id')
    )
    
    # Create documents table (matching current Document model)
    op.create_table('documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('document_type', documenttype_enum, nullable=False, server_default='OTHER'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('upload_date', sa.DateTime(), nullable=True),
        sa.Column('file_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create document_analyses table (matching current DocumentAnalysis model)
    op.create_table('document_analyses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('analysis_type', sa.String(length=100), nullable=False),
        sa.Column('status', analysisstatus_enum, nullable=False, server_default='PENDING'),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('compliance_gaps', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('recommendations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('confidence_score', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create ai_systems table (matching current AISystem model)
    op.create_table('ai_systems',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('system_type', sa.String(length=100), nullable=True),
        sa.Column('risk_level', airisklevel_enum, nullable=True),
        sa.Column('is_high_risk', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('deployment_date', sa.DateTime(), nullable=True),
        sa.Column('last_assessment', sa.DateTime(), nullable=True),
        sa.Column('system_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create compliance_tasks table (matching current ComplianceTask model)
    op.create_table('compliance_tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('jurisdiction_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', taskstatus_enum, nullable=False, server_default='TODO'),
        sa.Column('priority', taskpriority_enum, nullable=False, server_default='MEDIUM'),
        sa.Column('assignee_id', sa.UUID(), nullable=True),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('completed_date', sa.DateTime(), nullable=True),
        sa.Column('estimated_hours', sa.Float(), nullable=True),
        sa.Column('actual_hours', sa.Float(), nullable=True),
        sa.Column('completion_percentage', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('task_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['jurisdiction_id'], ['jurisdictions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create system_compliance table (matching current SystemCompliance model)
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
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'jurisdiction_id')
    )
    
    # Create compliance_reports table (matching current ComplianceReport model)
    op.create_table('compliance_reports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('report_type', reporttype_enum, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('generated_date', sa.DateTime(), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create form_questions table (matching current FormQuestion model)
    op.create_table('form_questions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('category', sa.String(length=255), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('question_type', questiontype_enum, nullable=False),
        sa.Column('options', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('required', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('help_text', sa.Text(), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('jurisdictions', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create form_responses table (matching current FormResponse model)
    op.create_table('form_responses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('question_id', sa.UUID(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['form_questions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop all tables in reverse order
    op.drop_table('form_responses')
    op.drop_table('form_questions')
    op.drop_table('compliance_reports')
    op.drop_table('system_compliance')
    op.drop_table('compliance_tasks')
    op.drop_table('ai_systems')
    op.drop_table('document_analyses')
    op.drop_table('documents')
    op.drop_table('organization_jurisdictions')
    op.drop_table('user_organizations')
    op.drop_table('jurisdictions')
    op.drop_table('organizations')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('oauth_accounts')
    op.drop_table('users')
    
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS questiontype CASCADE")
    op.execute("DROP TYPE IF EXISTS airisklevel CASCADE")
    op.execute("DROP TYPE IF EXISTS reporttype CASCADE")
    op.execute("DROP TYPE IF EXISTS taskpriority CASCADE")
    op.execute("DROP TYPE IF EXISTS taskstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS analysisstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS documenttype CASCADE")
    op.execute("DROP TYPE IF EXISTS compliancestatus CASCADE")
    op.execute("DROP TYPE IF EXISTS regulationtype CASCADE")
    op.execute("DROP TYPE IF EXISTS organizationsize CASCADE")
    op.execute("DROP TYPE IF EXISTS userrole CASCADE")
    op.execute("DROP TYPE IF EXISTS plantype CASCADE")