
"""create initial training management schema

Revision ID: 4c5a99157b0e
Revises:
Create Date: 2026-11-02 23:38:53.858003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4c5a99157b0e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'skills',
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('skill_name', sa.String(150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('skill_id'),
        sa.UniqueConstraint('skill_name')
    )
    op.create_index(
        op.f('ix_skills_skill_id'),
        'skills',
        ['skill_id'],
        unique=False
    )

    op.create_table(
        'courses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.String(100), nullable=False),
        sa.Column('course_title', sa.String(200), nullable=False),
        sa.Column('course_description', sa.Text(), nullable=False),
        sa.Column('course_category', sa.String(100), nullable=False),
        sa.Column('course_duration_hours', sa.Float(), nullable=False),
        sa.Column('course_provider', sa.String(150), nullable=True),
        sa.Column('delivery_mode', sa.String(30), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('target_job_levels', sa.String(300), nullable=True),
        sa.Column('prerequisites', sa.Text(), nullable=True),
        sa.Column('has_assessment', sa.Boolean(), nullable=False),
        sa.Column('provides_certificate', sa.Boolean(), nullable=False),
        sa.Column('assessment_type', sa.String(50), nullable=False),
        sa.Column('course_cost', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id',
            'course_id',
            name='uq_company_course'
        )
    )
    op.create_index(
        op.f('ix_courses_company_id'),
        'courses',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_courses_id'),
        'courses',
        ['id'],
        unique=False
    )

    op.create_table(
        'course_sessions',
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('session_name', sa.String(150), nullable=True),
        sa.Column('start_datetime', sa.DateTime(), nullable=False),
        sa.Column('end_datetime', sa.DateTime(), nullable=False),
        sa.Column('registration_deadline', sa.DateTime(), nullable=False),
        sa.Column('session_status', sa.String(30), nullable=False),
        sa.Column('trainer_name', sa.String(150), nullable=True),
        sa.Column('location_type', sa.String(30), nullable=False),
        sa.Column('location_details', sa.Text(), nullable=True),
        sa.Column('max_participants', sa.Integer(), nullable=True),
        sa.Column('completion_status', sa.String(30), nullable=True),
        sa.Column('completion_date', sa.DateTime(), nullable=True),
        sa.Column('completion_notes', sa.Text(), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['cancelled_by'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['course_id'], ['courses.id']
        ),
        sa.PrimaryKeyConstraint('session_id')
    )
    op.create_index(
        op.f('ix_course_sessions_company_id'),
        'course_sessions',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_course_sessions_course_id'),
        'course_sessions',
        ['course_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_course_sessions_session_id'),
        'course_sessions',
        ['session_id'],
        unique=False
    )

    op.create_table(
        'course_skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('proficiency_level', sa.Integer(), nullable=True),
        sa.Column('approval_status', sa.String(30), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['approved_by'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['course_id'], ['courses.id']
        ),
        sa.ForeignKeyConstraint(
            ['skill_id'], ['skills.skill_id']
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id',
            'course_id',
            'skill_id',
            name='uq_company_course_skill'
        )
    )
    op.create_index(
        op.f('ix_course_skills_company_id'),
        'course_skills',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_course_skills_course_id'),
        'course_skills',
        ['course_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_course_skills_id'),
        'course_skills',
        ['id'],
        unique=False
    )
    op.create_index(
        op.f('ix_course_skills_skill_id'),
        'course_skills',
        ['skill_id'],
        unique=False
    )

    op.create_table(
        'job_skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('job_title', sa.String(150), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('required_proficiency', sa.Integer(), nullable=False),
        sa.Column('importance', sa.String(30), nullable=False),
        sa.Column('approval_status', sa.String(30), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['approved_by'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['skill_id'], ['skills.skill_id']
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id',
            'job_title',
            'skill_id',
            name='uq_company_job_skill'
        )
    )
    op.create_index(
        op.f('ix_job_skills_company_id'),
        'job_skills',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_job_skills_id'),
        'job_skills',
        ['id'],
        unique=False
    )

    op.create_table(
        'skill_assessments',
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('proficiency_level', sa.Integer(), nullable=False),
        sa.Column('assessment_source', sa.String(50), nullable=False),
        sa.Column('assessment_score', sa.Float(), nullable=True),
        sa.Column('evidence_quality', sa.String(30), nullable=False),
        sa.Column('assessment_date', sa.Date(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('assessor_comments', sa.Text(), nullable=True),
        sa.Column('evidence_status', sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['skill_id'], ['skills.skill_id']
        ),
        sa.PrimaryKeyConstraint('assessment_id')
    )
    op.create_index(
        op.f('ix_skill_assessments_assessment_id'),
        'skill_assessments',
        ['assessment_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_skill_assessments_company_id'),
        'skill_assessments',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_skill_assessments_employee_id'),
        'skill_assessments',
        ['employee_id'],
        unique=False
    )

    op.create_table(
        'training_plans',
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('plan_status', sa.String(30), nullable=False),
        sa.Column('plan_start_date', sa.Date(), nullable=True),
        sa.Column('target_completion_date', sa.Date(), nullable=True),
        sa.Column('actual_completion_date', sa.Date(), nullable=True),
        sa.Column('estimated_total_hours', sa.Numeric(8, 2), nullable=True),
        sa.Column('actual_total_hours', sa.Numeric(8, 2), nullable=True),
        sa.Column('estimated_total_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('actual_total_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('approval_status', sa.String(30), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approval_date', sa.DateTime(), nullable=True),
        sa.Column('approval_comments', sa.String(500), nullable=True),
        sa.Column('last_reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('plan_review_notes', sa.String(1000), nullable=True),
        sa.ForeignKeyConstraint(
            ['approved_by'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id']
        ),
        sa.PrimaryKeyConstraint('plan_id')
    )
    op.create_index(
        op.f('ix_training_plans_company_id'),
        'training_plans',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_training_plans_employee_id'),
        'training_plans',
        ['employee_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_training_plans_plan_id'),
        'training_plans',
        ['plan_id'],
        unique=False
    )

    op.create_table(
        'enrollments',
        sa.Column('enrollment_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('approval_status', sa.String(30), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approval_date', sa.DateTime(), nullable=True),
        sa.Column('approval_comments', sa.String(500), nullable=True),
        sa.Column('progress_percentage', sa.Integer(), nullable=False),
        sa.Column('expected_completion_date', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('withdrawn_at', sa.DateTime(), nullable=True),
        sa.Column('withdrawal_reason', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('status_updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['approved_by'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['course_id'], ['courses.id']
        ),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['session_id'], ['course_sessions.session_id']
        ),
        sa.ForeignKeyConstraint(
            ['status_updated_by'], ['employees.id']
        ),
        sa.PrimaryKeyConstraint('enrollment_id')
    )
    op.create_index(
        op.f('ix_enrollments_company_id'),
        'enrollments',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_enrollments_employee_id'),
        'enrollments',
        ['employee_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_enrollments_enrollment_id'),
        'enrollments',
        ['enrollment_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_enrollments_session_id'),
        'enrollments',
        ['session_id'],
        unique=False
    )

    op.create_table(
        'plan_courses',
        sa.Column('plan_course_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('priority', sa.String(30), nullable=False),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.Column('recommendation_reason', sa.Text(), nullable=True),
        sa.Column('expected_outcome', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ['course_id'], ['courses.id']
        ),
        sa.ForeignKeyConstraint(
            ['plan_id'], ['training_plans.plan_id']
        ),
        sa.PrimaryKeyConstraint('plan_course_id'),
        sa.UniqueConstraint(
            'plan_id',
            'course_id',
            name='uq_plan_course'
        )
    )
    op.create_index(
        op.f('ix_plan_courses_plan_course_id'),
        'plan_courses',
        ['plan_course_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_plan_courses_plan_id'),
        'plan_courses',
        ['plan_id'],
        unique=False
    )

    op.create_table(
        'session_attendance',
        sa.Column('attendance_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('attendance_status', sa.String(30), nullable=False),
        sa.Column('check_in_time', sa.DateTime(), nullable=True),
        sa.Column('check_out_time', sa.DateTime(), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=True),
        sa.Column('attendance_notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['recorded_by'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['session_id'], ['course_sessions.session_id']
        ),
        sa.PrimaryKeyConstraint('attendance_id'),
        sa.UniqueConstraint(
            'session_id',
            'employee_id',
            name='uq_session_employee_attendance'
        )
    )
    op.create_index(
        op.f('ix_session_attendance_attendance_id'),
        'session_attendance',
        ['attendance_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_session_attendance_company_id'),
        'session_attendance',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_session_attendance_employee_id'),
        'session_attendance',
        ['employee_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_session_attendance_session_id'),
        'session_attendance',
        ['session_id'],
        unique=False
    )

    op.create_table(
        'session_feedback',
        sa.Column('feedback_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('training_rating', sa.Integer(), nullable=False),
        sa.Column('trainer_rating', sa.Integer(), nullable=True),
        sa.Column('content_relevance_rating', sa.Integer(), nullable=True),
        sa.Column('feedback_comments', sa.Text(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['employee_id'], ['employees.id']
        ),
        sa.ForeignKeyConstraint(
            ['session_id'], ['course_sessions.session_id']
        ),
        sa.PrimaryKeyConstraint('feedback_id'),
        sa.UniqueConstraint(
            'session_id',
            'employee_id',
            name='uq_session_employee_feedback'
        )
    )
    op.create_index(
        op.f('ix_session_feedback_company_id'),
        'session_feedback',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_session_feedback_employee_id'),
        'session_feedback',
        ['employee_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_session_feedback_feedback_id'),
        'session_feedback',
        ['feedback_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_session_feedback_session_id'),
        'session_feedback',
        ['session_id'],
        unique=False
    )

    op.create_table(
        'enrollment_assessments',
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('enrollment_id', sa.Integer(), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('assessment_score', sa.Float(), nullable=True),
        sa.Column('assessment_result', sa.String(30), nullable=False),
        sa.Column('assessed_at', sa.DateTime(), nullable=False),
        sa.Column('assessor_comments', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.company_id']
        ),
        sa.ForeignKeyConstraint(
            ['enrollment_id'], ['enrollments.enrollment_id']
        ),
        sa.PrimaryKeyConstraint('assessment_id')
    )
    op.create_index(
        op.f('ix_enrollment_assessments_assessment_id'),
        'enrollment_assessments',
        ['assessment_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_enrollment_assessments_company_id'),
        'enrollment_assessments',
        ['company_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_enrollment_assessments_enrollment_id'),
        'enrollment_assessments',
        ['enrollment_id'],
        unique=False
    )

    op.add_column(
        'employees',
        sa.Column('manager_internal_id', sa.Integer(), nullable=True)
    )

    op.create_unique_constraint(
        'uq_company_employee',
        'employees',
        ['company_id', 'employee_id']
    )

    op.create_unique_constraint(
        'uq_company_employee_email',
        'employees',
        ['company_id', 'email']
    )

    op.create_foreign_key(
        'fk_employees_manager_internal_id',
        'employees',
        'employees',
        ['manager_internal_id'],
        ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        'fk_employees_manager_internal_id',
        'employees',
        type_='foreignkey'
    )

    op.drop_constraint(
        'uq_company_employee_email',
        'employees',
        type_='unique'
    )

    op.drop_constraint(
        'uq_company_employee',
        'employees',
        type_='unique'
    )

    op.drop_column('employees', 'manager_internal_id')

    op.drop_index(
        op.f('ix_enrollment_assessments_enrollment_id'),
        table_name='enrollment_assessments'
    )
    op.drop_index(
        op.f('ix_enrollment_assessments_company_id'),
        table_name='enrollment_assessments'
    )
    op.drop_index(
        op.f('ix_enrollment_assessments_assessment_id'),
        table_name='enrollment_assessments'
    )
    op.drop_table('enrollment_assessments')

    op.drop_index(
        op.f('ix_session_feedback_session_id'),
        table_name='session_feedback'
    )
    op.drop_index(
        op.f('ix_session_feedback_feedback_id'),
        table_name='session_feedback'
    )
    op.drop_index(
        op.f('ix_session_feedback_employee_id'),
        table_name='session_feedback'
    )
    op.drop_index(
        op.f('ix_session_feedback_company_id'),
        table_name='session_feedback'
    )
    op.drop_table('session_feedback')

    op.drop_index(
        op.f('ix_session_attendance_session_id'),
        table_name='session_attendance'
    )
    op.drop_index(
        op.f('ix_session_attendance_employee_id'),
        table_name='session_attendance'
    )
    op.drop_index(
        op.f('ix_session_attendance_company_id'),
        table_name='session_attendance'
    )
    op.drop_index(
        op.f('ix_session_attendance_attendance_id'),
        table_name='session_attendance'
    )
    op.drop_table('session_attendance')

    op.drop_index(
        op.f('ix_plan_courses_plan_id'),
        table_name='plan_courses'
    )
    op.drop_index(
        op.f('ix_plan_courses_plan_course_id'),
        table_name='plan_courses'
    )
    op.drop_table('plan_courses')

    op.drop_index(
        op.f('ix_enrollments_session_id'),
        table_name='enrollments'
    )
    op.drop_index(
        op.f('ix_enrollments_enrollment_id'),
        table_name='enrollments'
    )
    op.drop_index(
        op.f('ix_enrollments_employee_id'),
        table_name='enrollments'
    )
    op.drop_index(
        op.f('ix_enrollments_company_id'),
        table_name='enrollments'
    )
    op.drop_table('enrollments')

    op.drop_index(
        op.f('ix_training_plans_plan_id'),
        table_name='training_plans'
    )
    op.drop_index(
        op.f('ix_training_plans_employee_id'),
        table_name='training_plans'
    )
    op.drop_index(
        op.f('ix_training_plans_company_id'),
        table_name='training_plans'
    )
    op.drop_table('training_plans')

    op.drop_index(
        op.f('ix_skill_assessments_employee_id'),
        table_name='skill_assessments'
    )
    op.drop_index(
        op.f('ix_skill_assessments_company_id'),
        table_name='skill_assessments'
    )
    op.drop_index(
        op.f('ix_skill_assessments_assessment_id'),
        table_name='skill_assessments'
    )
    op.drop_table('skill_assessments')

    op.drop_index(
        op.f('ix_job_skills_id'),
        table_name='job_skills'
    )
    op.drop_index(
        op.f('ix_job_skills_company_id'),
        table_name='job_skills'
    )
    op.drop_table('job_skills')

    op.drop_index(
        op.f('ix_course_skills_skill_id'),
        table_name='course_skills'
    )
    op.drop_index(
        op.f('ix_course_skills_id'),
        table_name='course_skills'
    )
    op.drop_index(
        op.f('ix_course_skills_course_id'),
        table_name='course_skills'
    )
    op.drop_index(
        op.f('ix_course_skills_company_id'),
        table_name='course_skills'
    )
    op.drop_table('course_skills')

    op.drop_index(
        op.f('ix_course_sessions_session_id'),
        table_name='course_sessions'
    )
    op.drop_index(
        op.f('ix_course_sessions_course_id'),
        table_name='course_sessions'
    )
    op.drop_index(
        op.f('ix_course_sessions_company_id'),
        table_name='course_sessions'
    )
    op.drop_table('course_sessions')

    op.drop_index(
        op.f('ix_courses_id'),
        table_name='courses'
    )
    op.drop_index(
        op.f('ix_courses_company_id'),
        table_name='courses'
    )
    op.drop_table('courses')

    op.drop_index(
        op.f('ix_skills_skill_id'),
        table_name='skills'
    )
    op.drop_table('skills')
