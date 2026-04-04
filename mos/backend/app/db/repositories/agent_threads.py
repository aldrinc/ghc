from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentThread,
    AgentTurn,
    ApprovalItem,
    RuntimeSession,
    SitePageContextBinding,
)


class AgentThreadsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_latest_for_page(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        site_id: str,
        page_id: str,
        objective_type: str,
        agent_profile: str,
    ) -> AgentThread | None:
        stmt = (
            select(AgentThread)
            .where(
                AgentThread.org_id == org_id,
                AgentThread.client_id == client_id,
                AgentThread.product_id == product_id,
                AgentThread.site_id == site_id,
                AgentThread.page_id == page_id,
                AgentThread.objective_type == objective_type,
                AgentThread.agent_profile == agent_profile,
            )
            .order_by(AgentThread.updated_at.desc(), AgentThread.created_at.desc())
        )
        return self.session.scalars(stmt).first()

    def get(self, *, thread_id: str, org_id: str | None = None) -> AgentThread | None:
        stmt = select(AgentThread).where(AgentThread.id == thread_id)
        if org_id:
            stmt = stmt.where(AgentThread.org_id == org_id)
        return self.session.scalars(stmt).first()

    def create_thread(
        self,
        *,
        thread_id: str | None = None,
        org_id: str,
        user_id: str,
        client_id: str,
        product_id: str,
        agent_profile: str,
        objective_type: str,
        bundle_key: str,
        runtime_profile_key: str | None,
        strategy_bundle_id: str | None,
        bundle_manifest: dict[str, Any],
        title: str | None = None,
        site_id: str | None = None,
        page_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> AgentThread:
        now = datetime.now(timezone.utc)
        thread = AgentThread(
            id=thread_id,
            org_id=org_id,
            user_id=user_id,
            client_id=client_id,
            product_id=product_id,
            site_id=site_id,
            page_id=page_id,
            agent_profile=agent_profile,
            objective_type=objective_type,
            title=title,
            bundle_key=bundle_key,
            runtime_profile_key=runtime_profile_key,
            strategy_bundle_id=strategy_bundle_id,
            bundle_manifest=bundle_manifest,
            metadata_json=metadata_json or {},
            created_at=now,
            updated_at=now,
        )
        self.session.add(thread)
        self.session.flush()
        self.session.refresh(thread)
        return thread

    def update_thread(self, *, thread: AgentThread) -> AgentThread:
        thread.updated_at = datetime.now(timezone.utc)
        self.session.add(thread)
        self.session.flush()
        self.session.refresh(thread)
        return thread

    def next_turn_seq(self, *, thread_id: str) -> int:
        stmt = select(func.max(AgentTurn.seq)).where(AgentTurn.thread_id == thread_id)
        current = self.session.scalar(stmt)
        return int(current or 0) + 1

    def create_turn(
        self,
        *,
        thread_id: str,
        seq: int,
        role: str,
        content: str,
        run_id: str | None = None,
        artifact_id: str | None = None,
        site_page_version_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> AgentTurn:
        turn = AgentTurn(
            thread_id=thread_id,
            seq=seq,
            role=role,
            content=content,
            run_id=run_id,
            artifact_id=artifact_id,
            site_page_version_id=site_page_version_id,
            metadata_json=metadata_json or {},
        )
        self.session.add(turn)
        self.session.flush()
        self.session.refresh(turn)
        return turn

    def list_turns(self, *, thread_id: str) -> list[AgentTurn]:
        stmt = (
            select(AgentTurn)
            .where(AgentTurn.thread_id == thread_id)
            .order_by(AgentTurn.seq.asc(), AgentTurn.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())


class RuntimeSessionsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_thread(self, *, thread_id: str) -> RuntimeSession | None:
        stmt = select(RuntimeSession).where(RuntimeSession.thread_id == thread_id)
        return self.session.scalars(stmt).first()

    def create_session(
        self,
        *,
        thread_id: str,
        org_id: str,
        client_id: str,
        product_id: str,
        agent_profile: str,
        scope_key: str,
        runtime_home: str,
        projection_hash: str,
        toolsets: list[str],
        status: str = "ready",
    ) -> RuntimeSession:
        now = datetime.now(timezone.utc)
        runtime_session = RuntimeSession(
            thread_id=thread_id,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            agent_profile=agent_profile,
            scope_key=scope_key,
            runtime_home=runtime_home,
            projection_hash=projection_hash,
            toolsets=toolsets,
            status=status,
            created_at=now,
            updated_at=now,
            last_used_at=now,
        )
        self.session.add(runtime_session)
        self.session.flush()
        self.session.refresh(runtime_session)
        return runtime_session

    def update_session(self, *, runtime_session: RuntimeSession) -> RuntimeSession:
        runtime_session.updated_at = datetime.now(timezone.utc)
        runtime_session.last_used_at = datetime.now(timezone.utc)
        self.session.add(runtime_session)
        self.session.flush()
        self.session.refresh(runtime_session)
        return runtime_session


class SitePageContextBindingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_page(self, *, page_id: str, org_id: str | None = None) -> SitePageContextBinding | None:
        stmt = select(SitePageContextBinding).where(SitePageContextBinding.page_id == page_id)
        if org_id:
            stmt = stmt.where(SitePageContextBinding.org_id == org_id)
        return self.session.scalars(stmt).first()

    def upsert_binding(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        site_id: str,
        page_id: str,
        bundle_key: str,
        strategy_bundle_id: str | None,
        runtime_profile_key: str | None,
        binding_json: dict[str, Any],
    ) -> SitePageContextBinding:
        existing = self.get_by_page(page_id=page_id, org_id=org_id)
        now = datetime.now(timezone.utc)
        if existing:
            existing.client_id = client_id
            existing.product_id = product_id
            existing.site_id = site_id
            existing.bundle_key = bundle_key
            existing.strategy_bundle_id = strategy_bundle_id
            existing.runtime_profile_key = runtime_profile_key
            existing.status = "active"
            existing.binding_json = binding_json
            existing.updated_at = now
            self.session.add(existing)
            self.session.flush()
            self.session.refresh(existing)
            return existing

        binding = SitePageContextBinding(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            site_id=site_id,
            page_id=page_id,
            bundle_key=bundle_key,
            strategy_bundle_id=strategy_bundle_id,
            runtime_profile_key=runtime_profile_key,
            binding_json=binding_json,
            created_at=now,
            updated_at=now,
        )
        self.session.add(binding)
        self.session.flush()
        self.session.refresh(binding)
        return binding


class ApprovalItemsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        org_id: str,
        thread_id: str,
        target_kind: str,
        artifact_id: str | None = None,
        site_page_version_id: str | None = None,
    ) -> ApprovalItem:
        item = ApprovalItem(
            org_id=org_id,
            thread_id=thread_id,
            target_kind=target_kind,
            artifact_id=artifact_id,
            site_page_version_id=site_page_version_id,
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def list_for_thread(self, *, thread_id: str) -> list[ApprovalItem]:
        stmt = (
            select(ApprovalItem)
            .where(ApprovalItem.thread_id == thread_id)
            .order_by(ApprovalItem.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get(self, *, approval_item_id: str, org_id: Optional[str] = None) -> ApprovalItem | None:
        stmt = select(ApprovalItem).where(ApprovalItem.id == approval_item_id)
        if org_id:
            stmt = stmt.where(ApprovalItem.org_id == org_id)
        return self.session.scalars(stmt).first()

    def update(self, *, item: ApprovalItem) -> ApprovalItem:
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item
