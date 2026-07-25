from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    datasets: Mapped[list['Dataset']] = relationship(back_populates='owner')
    refresh_sessions: Mapped[list['RefreshSession']] = relationship(back_populates='user')


class OwnedResource:
    owner_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)


class Dataset(Base, OwnedResource):
    __tablename__ = 'datasets'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    active_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    profile: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(50))

    owner: Mapped[User] = relationship(back_populates='datasets')
    versions: Mapped[list['Version']] = relationship(back_populates='dataset', cascade='all, delete-orphan')
    chunks: Mapped[list['Chunk']] = relationship(back_populates='dataset', cascade='all, delete-orphan')
    events: Mapped[list['DatasetEvent']] = relationship(back_populates='dataset', cascade='all, delete-orphan')
    transformations: Mapped[list['Transformation']] = relationship(back_populates='dataset', cascade='all, delete-orphan')
    reports: Mapped[list['Report']] = relationship(back_populates='dataset', cascade='all, delete-orphan')


class RefreshSession(Base):
    __tablename__ = 'refresh_sessions'

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    parent_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates='refresh_sessions')


class DatasetChild(Base, OwnedResource):
    __abstract__ = True
    dataset_id: Mapped[str] = mapped_column(ForeignKey('datasets.id'), nullable=False, index=True)


class Version(DatasetChild):
    __tablename__ = 'versions'
    __table_args__ = (UniqueConstraint('dataset_id', 'number', name='uq_versions_dataset_number'),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dataset: Mapped[Dataset] = relationship(back_populates='versions')


class Chunk(DatasetChild):
    __tablename__ = 'chunks'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column('metadata', Text, nullable=False, default='{}')
    dataset: Mapped[Dataset] = relationship(back_populates='chunks')


class DatasetEvent(DatasetChild):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dataset: Mapped[Dataset] = relationship(back_populates='events')


class Transformation(DatasetChild):
    __tablename__ = 'transformations'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    preview_path: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dataset: Mapped[Dataset] = relationship(back_populates='transformations')


class Report(DatasetChild):
    __tablename__ = 'reports'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dataset: Mapped[Dataset] = relationship(back_populates='reports')


Index('ix_versions_owner_dataset', Version.owner_user_id, Version.dataset_id)
Index('ix_chunks_owner_dataset', Chunk.owner_user_id, Chunk.dataset_id)
Index('ix_events_owner_dataset', DatasetEvent.owner_user_id, DatasetEvent.dataset_id)
Index('ix_transformations_owner_dataset', Transformation.owner_user_id, Transformation.dataset_id)
Index('ix_reports_owner_dataset', Report.owner_user_id, Report.dataset_id)
