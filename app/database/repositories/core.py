from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (Company, CompanyDomain, CrawlJob, Organization, OrganizationCompany,
                      OrganizationMember, User)


class OrganizationRepository:
    def __init__(self, session: AsyncSession): self.session = session

    async def create(self, *, name: str, slug: str) -> Organization:
        obj = Organization(name=name, slug=slug)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def add_member(self, organization_id: UUID, user_id: UUID, role: str = "member") -> OrganizationMember:
        obj = OrganizationMember(organization_id=organization_id, user_id=user_id, role=role)
        self.session.add(obj)
        await self.session.flush()
        return obj


class UserRepository:
    def __init__(self, session: AsyncSession): self.session = session

    async def create(self, *, email: str, full_name: str, password_hash: str | None = None) -> User:
        obj = User(email=email.strip().lower(), full_name=full_name, password_hash=password_hash)
        self.session.add(obj)
        await self.session.flush()
        return obj


class CompanyRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session, self.organization_id = session, organization_id

    async def create_or_get(self, *, name: str, domain: str, added_by_user_id: UUID | None = None) -> Company:
        normalized = name.strip().casefold()
        result = await self.session.execute(select(Company).join(CompanyDomain).where(CompanyDomain.domain == domain.lower()))
        company = result.scalar_one_or_none()
        if company is None:
            company = Company(name=name.strip(), normalized_name=normalized)
            self.session.add(company)
            await self.session.flush()
            self.session.add(CompanyDomain(company_id=company.id, domain=domain.lower(), is_primary=True))
            await self.session.flush()
        link = await self.session.execute(select(OrganizationCompany).where(
            OrganizationCompany.organization_id == self.organization_id,
            OrganizationCompany.company_id == company.id))
        if link.scalar_one_or_none() is None:
            self.session.add(OrganizationCompany(organization_id=self.organization_id, company_id=company.id,
                                                 added_by_user_id=added_by_user_id))
            await self.session.flush()
        return company

    async def get(self, company_id: UUID) -> Company | None:
        result = await self.session.execute(select(Company).join(OrganizationCompany).where(
            Company.id == company_id, OrganizationCompany.organization_id == self.organization_id))
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100, offset: int = 0) -> list[Company]:
        result = await self.session.execute(select(Company).join(OrganizationCompany).where(
            OrganizationCompany.organization_id == self.organization_id).order_by(Company.name).limit(limit).offset(offset))
        return list(result.scalars().unique())


class CrawlJobRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session, self.organization_id = session, organization_id

    async def create(self, company_id: UUID, submitted_by_user_id: UUID | None = None, input_metadata=None) -> CrawlJob:
        # Confirm the company belongs to this organization before creating a tenant job.
        membership = await self.session.execute(select(OrganizationCompany.id).where(
            OrganizationCompany.organization_id == self.organization_id,
            OrganizationCompany.company_id == company_id))
        if membership.scalar_one_or_none() is None:
            raise LookupError("Company is not available in this organization")
        job = CrawlJob(organization_id=self.organization_id, company_id=company_id,
                       submitted_by_user_id=submitted_by_user_id, input_metadata=input_metadata or {})
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: UUID) -> CrawlJob | None:
        result = await self.session.execute(select(CrawlJob).where(
            CrawlJob.id == job_id, CrawlJob.organization_id == self.organization_id))
        return result.scalar_one_or_none()


class ICPRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session, self.organization_id = session, organization_id

    async def create(self, *, name: str, criteria: dict, is_default: bool = False):
        from ..models import ICPProfile
        obj = ICPProfile(organization_id=self.organization_id, name=name, criteria=criteria, is_default=is_default)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get(self, profile_id: UUID):
        from ..models import ICPProfile
        result = await self.session.execute(select(ICPProfile).where(
            ICPProfile.id == profile_id, ICPProfile.organization_id == self.organization_id))
        return result.scalar_one_or_none()


class CampaignRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session, self.organization_id = session, organization_id

    async def create(self, *, name: str, icp_profile_id: UUID | None = None, description: str | None = None):
        from ..models import Campaign, ICPProfile
        if icp_profile_id is not None:
            profile = await self.session.execute(select(ICPProfile.id).where(
                ICPProfile.id == icp_profile_id, ICPProfile.organization_id == self.organization_id))
            if profile.scalar_one_or_none() is None:
                raise LookupError("ICP profile is not available in this organization")
        obj = Campaign(organization_id=self.organization_id, name=name,
                       icp_profile_id=icp_profile_id, description=description)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get(self, campaign_id: UUID):
        from ..models import Campaign
        result = await self.session.execute(select(Campaign).where(
            Campaign.id == campaign_id, Campaign.organization_id == self.organization_id))
        return result.scalar_one_or_none()


class LeadScoreRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session, self.organization_id = session, organization_id

    async def create(self, *, campaign_id: UUID, company_id: UUID, score: float,
                     band: str, score_version: str, coverage: float | None = None, explanation=None):
        from ..models import Campaign, LeadScore
        campaign = await self.session.execute(select(Campaign.id).where(
            Campaign.id == campaign_id, Campaign.organization_id == self.organization_id))
        if campaign.scalar_one_or_none() is None:
            raise LookupError("Campaign is not available in this organization")
        membership = await self.session.execute(select(OrganizationCompany.id).where(
            OrganizationCompany.organization_id == self.organization_id,
            OrganizationCompany.company_id == company_id))
        if membership.scalar_one_or_none() is None:
            raise LookupError("Company is not available in this organization")
        obj = LeadScore(organization_id=self.organization_id, campaign_id=campaign_id,
                        company_id=company_id, score=score, band=band, score_version=score_version,
                        coverage=coverage, explanation=explanation or {})
        self.session.add(obj)
        await self.session.flush()
        return obj


class ReviewRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session, self.organization_id = session, organization_id

    async def create(self, *, entity_type: str, entity_id: UUID, assigned_to_user_id: UUID | None = None):
        from ..models import ReviewTask
        obj = ReviewTask(organization_id=self.organization_id, entity_type=entity_type,
                         entity_id=entity_id, assigned_to_user_id=assigned_to_user_id)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get(self, task_id: UUID):
        from ..models import ReviewTask
        result = await self.session.execute(select(ReviewTask).where(
            ReviewTask.id == task_id, ReviewTask.organization_id == self.organization_id))
        return result.scalar_one_or_none()
