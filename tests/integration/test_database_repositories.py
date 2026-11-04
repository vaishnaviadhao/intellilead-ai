import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.repositories import CompanyRepository, CrawlJobRepository, OrganizationRepository, UserRepository


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_company_and_crawl_job_are_scoped_to_organization(session_factory):
    async with session_factory() as session:
        async with session.begin():
            orgs = OrganizationRepository(session)
            org_a = await orgs.create(name="Agency A", slug="agency-a")
            org_b = await orgs.create(name="Agency B", slug="agency-b")
            user = await UserRepository(session).create(email="owner@example.com", full_name="Owner")
            await orgs.add_member(org_a.id, user.id, "owner")
            company = await CompanyRepository(session, org_a.id).create_or_get(
                name="Example SaaS", domain="example.com", added_by_user_id=user.id)
            job = await CrawlJobRepository(session, org_a.id).create(company.id, user.id)
            assert await CompanyRepository(session, org_a.id).get(company.id) is not None
            assert await CompanyRepository(session, org_b.id).get(company.id) is None
            assert await CrawlJobRepository(session, org_a.id).get(job.id) is not None
            assert await CrawlJobRepository(session, org_b.id).get(job.id) is None


@pytest.mark.asyncio
async def test_same_domain_reuses_global_company_but_creates_tenant_link(session_factory):
    async with session_factory() as session:
        async with session.begin():
            repo = OrganizationRepository(session)
            a = await repo.create(name="Agency A", slug="agency-a")
            b = await repo.create(name="Agency B", slug="agency-b")
            company_a = await CompanyRepository(session, a.id).create_or_get(name="Example", domain="example.com")
            company_b = await CompanyRepository(session, b.id).create_or_get(name="Example SaaS", domain="example.com")
            assert company_a.id == company_b.id
            assert len(await CompanyRepository(session, a.id).list()) == 1
            assert len(await CompanyRepository(session, b.id).list()) == 1
