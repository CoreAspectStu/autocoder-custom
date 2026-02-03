"""Initial schema - Create uat_test_features and uat_test_plan tables

Revision ID: 001
Revises:
Create Date: 2025-01-27

This migration creates the initial database schema for the UAT AutoCoder Plugin:
- uat_test_features: Stores individual test scenarios
- uat_test_plan: Stores generated test plans
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial tables."""

    # Create uat_test_features table
    op.create_table(
        'uat_test_features',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('phase', sa.String(length=50), nullable=False),
        sa.Column('journey', sa.String(length=100), nullable=False),
        sa.Column('scenario', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('test_type', sa.String(length=50), nullable=False),
        sa.Column('test_file', sa.String(length=500), nullable=True),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('expected_result', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('dependencies', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('devlayer_card_id', sa.String(length=100), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for uat_test_features
    op.create_index(op.f('ix_uat_test_features_priority'), 'uat_test_features', ['priority'])
    op.create_index(op.f('ix_uat_test_features_phase'), 'uat_test_features', ['phase'])
    op.create_index(op.f('ix_uat_test_features_journey'), 'uat_test_features', ['journey'])
    op.create_index(op.f('ix_uat_test_features_status'), 'uat_test_features', ['status'])

    # Create uat_test_plan table
    op.create_table(
        'uat_test_plan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('cycle_id', sa.String(length=100), nullable=False),
        sa.Column('total_features_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('journeys_identified', sa.JSON(), nullable=False),
        sa.Column('recommended_phases', sa.JSON(), nullable=False),
        sa.Column('test_prd', sa.Text(), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cycle_id')
    )

    # Create index for uat_test_plan
    op.create_index(op.f('ix_uat_test_plan_cycle_id'), 'uat_test_plan', ['cycle_id'], unique=True)


def downgrade() -> None:
    """Drop initial tables."""

    # Drop uat_test_plan table
    op.drop_index(op.f('ix_uat_test_plan_cycle_id'), table_name='uat_test_plan')
    op.drop_table('uat_test_plan')

    # Drop uat_test_features table
    op.drop_index(op.f('ix_uat_test_features_status'), table_name='uat_test_features')
    op.drop_index(op.f('ix_uat_test_features_journey'), table_name='uat_test_features')
    op.drop_index(op.f('ix_uat_test_features_phase'), table_name='uat_test_features')
    op.drop_index(op.f('ix_uat_test_features_priority'), table_name='uat_test_features')
    op.drop_table('uat_test_features')
