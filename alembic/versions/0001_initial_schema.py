"""Initial IntelliLead AI multi-tenant schema.

Revision ID: 0001_initial
"""
from alembic import op
from app.database.registry import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "organization_members", "api_keys", "organization_companies", "crawl_jobs",
    "icp_profiles", "campaigns", "campaign_companies", "lead_scores",
    "review_tasks", "research_reports", "exports", "audit_logs",
)


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        for table in TENANT_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'''CREATE POLICY tenant_isolation ON "{table}"
                USING (organization_id::text = current_setting('app.current_organization_id', true))
                WITH CHECK (organization_id::text = current_setting('app.current_organization_id', true))'''
            )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TENANT_TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    Base.metadata.drop_all(bind=bind)
