from __future__ import annotations
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
                        Numeric, String, Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from .base import Base, TimestampMixin, UUIDPrimaryKey

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Organization(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(40), default="starter", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    members: Mapped[list[OrganizationMember]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    memberships: Mapped[list[OrganizationMember]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OrganizationMember(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), default="member", nullable=False)
    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class ApiKey(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "api_keys"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Industry(UUIDPrimaryKey, Base):
    __tablename__ = "industries"
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("industries.id", ondelete="SET NULL"))


class Company(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (Index("ix_companies_normalized_name", "normalized_name"),)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    industry_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("industries.id", ondelete="SET NULL"))
    business_model: Mapped[str | None] = mapped_column(String(80))
    company_type: Mapped[str | None] = mapped_column(String(80))
    domains: Mapped[list[CompanyDomain]] = relationship(back_populates="company", cascade="all, delete-orphan")
    profile: Mapped[CompanyProfile | None] = relationship(back_populates="company", uselist=False, cascade="all, delete-orphan")


class CompanyDomain(UUIDPrimaryKey, Base):
    __tablename__ = "company_domains"
    __table_args__ = (UniqueConstraint("domain", name="uq_company_domains_domain"),)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[Company] = relationship(back_populates="domains")


class CompanyProfile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "company_profiles"
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False)
    employee_range: Mapped[str | None] = mapped_column(String(80))
    revenue_range: Mapped[str | None] = mapped_column(String(80))
    headquarters: Mapped[str | None] = mapped_column(String(180))
    country: Mapped[str | None] = mapped_column(String(100))
    founded_year: Mapped[int | None] = mapped_column(Integer)
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"))
    company: Mapped[Company] = relationship(back_populates="profile")


class CompanySocialLink(UUIDPrimaryKey, Base):
    __tablename__ = "company_social_links"
    __table_args__ = (UniqueConstraint("company_id", "platform"),)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)


class OrganizationCompany(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "organization_companies"
    __table_args__ = (UniqueConstraint("organization_id", "company_id"),)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    added_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    tags: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class Source(UUIDPrimaryKey, Base):
    __tablename__ = "sources"
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="website", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class CrawlJob(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (CheckConstraint("status IN ('queued','running','done','failed','cancelled')", name="crawl_job_status"),)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    progress_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class CompanyPage(UUIDPrimaryKey, Base):
    __tablename__ = "company_pages"
    __table_args__ = (UniqueConstraint("company_id", "url"),)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    crawl_job_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("crawl_jobs.id", ondelete="SET NULL"), index=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    page_type: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(500))
    meta_description: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Technology(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "technology_catalog"
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    vendor: Mapped[str | None] = mapped_column(String(120))
    signature_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TechnologyDetection(UUIDPrimaryKey, Base):
    __tablename__ = "technology_detections"
    __table_args__ = (UniqueConstraint("company_id", "technology_id", "page_id"), Index("ix_tech_detections_company", "company_id"))
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    technology_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("technology_catalog.id", ondelete="RESTRICT"), nullable=False)
    page_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_pages.id", ondelete="SET NULL"))
    score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    confidence_kind: Mapped[str] = mapped_column(String(24), default="heuristic", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="detected", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DetectionEvidence(UUIDPrimaryKey, Base):
    __tablename__ = "detection_evidence"
    detection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("technology_detections.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("company_pages.id", ondelete="SET NULL"))
    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    evidence_value: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GrowthSignal(UUIDPrimaryKey, Base):
    __tablename__ = "growth_signals"
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freshness_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"))


class CompanySnapshot(UUIDPrimaryKey, Base):
    __tablename__ = "company_snapshots"
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)


class ICPProfile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "icp_profiles"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Campaign(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "campaigns"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    icp_profile_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("icp_profiles.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class CampaignCompany(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "campaign_companies"
    __table_args__ = (UniqueConstraint("campaign_id", "company_id"),)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    added_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class LeadScore(UUIDPrimaryKey, Base):
    __tablename__ = "lead_scores"
    __table_args__ = (UniqueConstraint("campaign_id", "company_id", "score_version"), CheckConstraint("score >= 0 AND score <= 100", name="lead_score_range"))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    band: Mapped[str] = mapped_column(String(20), nullable=False)
    score_version: Mapped[str] = mapped_column(String(40), nullable=False)
    coverage: Mapped[float | None] = mapped_column(Numeric(5, 4))
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScoreBreakdown(UUIDPrimaryKey, Base):
    __tablename__ = "score_breakdowns"
    lead_score_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("lead_scores.id", ondelete="CASCADE"), nullable=False, index=True)
    criterion: Mapped[str] = mapped_column(String(120), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    criterion_score: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    contribution: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)


class ReviewTask(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "review_tasks"
    __table_args__ = (CheckConstraint("status IN ('pending','verified','rejected','needs_investigation','expired')", name="review_status"),)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class ReviewDecision(UUIDPrimaryKey, Base):
    __tablename__ = "review_decisions"
    review_task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("review_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    correction: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ResearchReport(UUIDPrimaryKey, Base):
    __tablename__ = "research_reports"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))


class ResearchCitation(UUIDPrimaryKey, Base):
    __tablename__ = "research_citations"
    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)


class Export(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "exports"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"))
    format: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    error_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(UUIDPrimaryKey, Base):
    __tablename__ = "audit_logs"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
