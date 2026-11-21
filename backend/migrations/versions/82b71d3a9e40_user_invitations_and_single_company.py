"""Add user invitations and enforce one company per account.

Revision ID: 82b71d3a9e40
Revises: 71eab962f143
"""
from alembic import op
import sqlalchemy as sa

revision = "82b71d3a9e40"
down_revision = "71eab962f143"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE users, user_company_roles IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM user_company_roles GROUP BY user_id HAVING count(*) > 1)
             OR EXISTS (SELECT 1 FROM user_company_roles WHERE employee_id IS NOT NULL
                        GROUP BY employee_id HAVING count(*) > 1)
             OR EXISTS (SELECT 1 FROM users u WHERE NOT EXISTS
                        (SELECT 1 FROM user_company_roles m WHERE m.user_id = u.user_id))
             OR EXISTS (SELECT 1 FROM users GROUP BY lower(trim(email)) HAVING count(*) > 1)
          THEN RAISE EXCEPTION 'Resolve duplicate memberships, employee links, email identities, or users without a membership before upgrading.';
          END IF;
        END $$;
    """)
    op.add_column(
        "users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_index(
        "uq_users_normalized_email", "users", [sa.text("lower(trim(email))")], unique=True
    )
    op.create_unique_constraint("uq_user_single_company", "user_company_roles", ["user_id"])
    op.create_unique_constraint("uq_membership_employee", "user_company_roles", ["employee_id"])
    op.create_table(
        "user_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="RESTRICT")),
        sa.Column("department", sa.String(100)),
        sa.Column("manager_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="RESTRICT")),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_invitations_company_id", "user_invitations", ["company_id"])
    op.create_index(
        "uq_pending_invitation_company_email", "user_invitations",
        ["company_id", sa.text("lower(trim(email))")],
        unique=True, postgresql_where=sa.text("status = 'Pending'"),
    )
    op.create_table(
        "user_management_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("invitation_id", sa.Integer(), sa.ForeignKey("user_invitations.id")),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_management_audits_company_id", "user_management_audits", ["company_id"])
    op.execute("""
        CREATE FUNCTION enforce_user_has_company() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE checked_user_id integer;
        BEGIN
          IF TG_TABLE_NAME = 'users' THEN checked_user_id := NEW.user_id;
          ELSE checked_user_id := OLD.user_id;
          END IF;
          IF EXISTS (SELECT 1 FROM users WHERE user_id = checked_user_id)
             AND NOT EXISTS (SELECT 1 FROM user_company_roles WHERE user_id = checked_user_id)
          THEN RAISE EXCEPTION 'A user account must have one company membership.';
          END IF;
          RETURN NULL;
        END $$;
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER user_requires_company AFTER INSERT ON users
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION enforce_user_has_company();
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER membership_requires_user_company
        AFTER DELETE OR UPDATE OF user_id ON user_company_roles
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION enforce_user_has_company();
    """)


def downgrade():
    op.execute("DROP TRIGGER membership_requires_user_company ON user_company_roles")
    op.execute("DROP TRIGGER user_requires_company ON users")
    op.execute("DROP FUNCTION enforce_user_has_company()")
    op.drop_index("ix_user_management_audits_company_id", table_name="user_management_audits")
    op.drop_table("user_management_audits")
    op.drop_index("uq_pending_invitation_company_email", table_name="user_invitations")
    op.drop_index("ix_user_invitations_company_id", table_name="user_invitations")
    op.drop_table("user_invitations")
    op.drop_constraint("uq_membership_employee", "user_company_roles", type_="unique")
    op.drop_constraint("uq_user_single_company", "user_company_roles", type_="unique")
    op.drop_index("uq_users_normalized_email", table_name="users")
    op.drop_column("users", "auth_version")
