"""Repository for Postiz integration data access."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import (
    ClientPostizChannel,
    ClientPostizCredentials,
    ClientPostizPostingProfile,
    PostizPublication,
)


class PostizCredentialsRepository:
    """Repository for Postiz credentials."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, org_id: str, client_id: str) -> Optional[ClientPostizCredentials]:
        stmt = select(ClientPostizCredentials).where(
            ClientPostizCredentials.org_id == org_id,
            ClientPostizCredentials.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        base_url: str,
        credentials_encrypted: str,
        auth_type: str = "api_key",
    ) -> ClientPostizCredentials:
        stmt = (
            insert(ClientPostizCredentials)
            .values(
                org_id=org_id,
                client_id=client_id,
                base_url=base_url,
                auth_type=auth_type,
                credentials_encrypted=credentials_encrypted,
            )
            .on_conflict_do_update(
                index_elements=["org_id", "client_id"],
                set_={
                    "base_url": base_url,
                    "auth_type": auth_type,
                    "credentials_encrypted": credentials_encrypted,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            .returning(ClientPostizCredentials)
        )
        result = self.session.execute(stmt).scalar_one()
        self.session.flush()
        self.session.refresh(result)
        return result

    def update_validation(
        self,
        *,
        org_id: str,
        client_id: str,
        last_validated_at: datetime,
        last_validation_error: Optional[str] = None,
    ) -> Optional[ClientPostizCredentials]:
        cred = self.get(org_id=org_id, client_id=client_id)
        if cred is None:
            return None
        cred.last_validated_at = last_validated_at
        cred.last_validation_error = last_validation_error
        cred.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(cred)
        return cred

    def delete(self, org_id: str, client_id: str) -> bool:
        cred = self.get(org_id=org_id, client_id=client_id)
        if cred is None:
            return False
        self.session.delete(cred)
        self.session.flush()
        return True


class PostizChannelRepository:
    """Repository for Postiz channels."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        *,
        org_id: str,
        client_id: str,
        enabled_only: bool = False,
    ) -> List[ClientPostizChannel]:
        stmt = select(ClientPostizChannel).where(
            ClientPostizChannel.org_id == org_id,
            ClientPostizChannel.client_id == client_id,
        )
        if enabled_only:
            stmt = stmt.where(ClientPostizChannel.disabled == False)  # noqa: E712
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, channel_id: str) -> Optional[ClientPostizChannel]:
        stmt = select(ClientPostizChannel).where(
            ClientPostizChannel.id == channel_id,
            ClientPostizChannel.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def get_by_postiz_ids(
        self,
        org_id: str,
        client_id: str,
        postiz_integration_id: str,
        postiz_channel_id: str,
    ) -> Optional[ClientPostizChannel]:
        stmt = select(ClientPostizChannel).where(
            ClientPostizChannel.org_id == org_id,
            ClientPostizChannel.client_id == client_id,
            ClientPostizChannel.postiz_integration_id == postiz_integration_id,
            ClientPostizChannel.postiz_channel_id == postiz_channel_id,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        postiz_integration_id: str,
        postiz_channel_id: str,
        identifier: str,
        name: str,
        profile: str | None = None,
        picture_url: str | None = None,
        disabled: bool = False,
        is_default: bool = False,
        metadata_json: dict[str, Any] | None = None,
    ) -> ClientPostizChannel:
        stmt = (
            insert(ClientPostizChannel)
            .values(
                org_id=org_id,
                client_id=client_id,
                postiz_integration_id=postiz_integration_id,
                postiz_channel_id=postiz_channel_id,
                identifier=identifier,
                name=name,
                profile=profile,
                picture_url=picture_url,
                disabled=disabled,
                is_default=is_default,
                metadata_json=metadata_json or {},
                last_synced_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                index_elements=[
                    "org_id",
                    "client_id",
                    "postiz_integration_id",
                    "postiz_channel_id",
                ],
                set_={
                    "identifier": identifier,
                    "name": name,
                    "profile": profile,
                    "picture_url": picture_url,
                    "disabled": disabled,
                    "is_default": is_default,
                    "metadata_json": metadata_json or {},
                    "last_synced_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            .returning(ClientPostizChannel)
        )
        result = self.session.execute(stmt).scalar_one()
        self.session.flush()
        self.session.refresh(result)
        return result

    def update_last_synced(
        self,
        *,
        org_id: str,
        channel_id: str,
        last_synced_at: datetime | None = None,
    ) -> Optional[ClientPostizChannel]:
        channel = self.get(org_id=org_id, channel_id=channel_id)
        if channel is None:
            return None
        channel.last_synced_at = last_synced_at or datetime.now(timezone.utc)
        channel.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(channel)
        return channel

    def delete(self, org_id: str, channel_id: str) -> bool:
        channel = self.get(org_id=org_id, channel_id=channel_id)
        if channel is None:
            return False
        self.session.delete(channel)
        self.session.flush()
        return True

    def clear_for_client(self, *, org_id: str, client_id: str) -> int:
        """Delete all channels for a client. Returns count of deleted rows."""
        stmt = select(ClientPostizChannel).where(
            ClientPostizChannel.org_id == org_id,
            ClientPostizChannel.client_id == client_id,
        )
        channels = list(self.session.scalars(stmt).all())
        count = len(channels)
        for channel in channels:
            self.session.delete(channel)
        self.session.flush()
        return count

    def mark_missing_as_disabled(
        self,
        *,
        org_id: str,
        client_id: str,
        active_postiz_integration_ids: set[str],
    ) -> int:
        channels = self.list(org_id=org_id, client_id=client_id)
        updated = 0
        for channel in channels:
            if channel.postiz_integration_id in active_postiz_integration_ids:
                continue
            channel.disabled = True
            metadata = dict(channel.metadata_json or {})
            metadata["stale"] = True
            channel.metadata_json = metadata
            channel.updated_at = datetime.now(timezone.utc)
            updated += 1
        self.session.flush()
        return updated


class PostizPostingProfileRepository:
    """Repository for Postiz posting profiles."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        *,
        org_id: str,
        client_id: str,
    ) -> List[ClientPostizPostingProfile]:
        stmt = select(ClientPostizPostingProfile).where(
            ClientPostizPostingProfile.org_id == org_id,
            ClientPostizPostingProfile.client_id == client_id,
        )
        return list(self.session.scalars(stmt).all())

    def get(self, org_id: str, profile_id: str) -> Optional[ClientPostizPostingProfile]:
        stmt = select(ClientPostizPostingProfile).where(
            ClientPostizPostingProfile.id == profile_id,
            ClientPostizPostingProfile.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def get_default(self, org_id: str, client_id: str) -> Optional[ClientPostizPostingProfile]:
        stmt = select(ClientPostizPostingProfile).where(
            ClientPostizPostingProfile.org_id == org_id,
            ClientPostizPostingProfile.client_id == client_id,
            ClientPostizPostingProfile.is_default == True,  # noqa: E712
        )
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        name: str,
        is_default: bool = False,
        default_channel_ids: list[str] | None = None,
        timezone: str | None = None,
        short_link: bool = False,
        provider_settings_json: dict[str, Any] | None = None,
        postiz_posting_profile_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ClientPostizPostingProfile:
        # If setting as default, clear other defaults first
        if is_default:
            self._clear_defaults(org_id=org_id, client_id=client_id)

        profile = ClientPostizPostingProfile(
            org_id=org_id,
            client_id=client_id,
            name=name,
            is_default=is_default,
            default_channel_ids=default_channel_ids or [],
            timezone=timezone,
            short_link=bool(short_link),
            provider_settings_json=provider_settings_json or {},
            postiz_posting_profile_id=postiz_posting_profile_id,
            metadata_json=metadata_json or {},
        )
        self.session.add(profile)
        self.session.flush()
        self.session.refresh(profile)
        return profile

    def update(
        self,
        *,
        org_id: str,
        profile_id: str,
        **fields,
    ) -> Optional[ClientPostizPostingProfile]:
        profile = self.get(org_id=org_id, profile_id=profile_id)
        if profile is None:
            return None

        # If setting as default, clear other defaults first
        if fields.get("is_default"):
            self._clear_defaults(org_id=org_id, client_id=profile.client_id)

        for key, value in fields.items():
            setattr(profile, key, value)
        profile.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(profile)
        return profile

    def delete(self, org_id: str, profile_id: str) -> bool:
        profile = self.get(org_id=org_id, profile_id=profile_id)
        if profile is None:
            return False
        self.session.delete(profile)
        self.session.flush()
        return True

    def _clear_defaults(self, *, org_id: str, client_id: str) -> None:
        """Clear is_default on all profiles for a client."""
        stmt = (
            update(ClientPostizPostingProfile)
            .where(
                ClientPostizPostingProfile.org_id == org_id,
                ClientPostizPostingProfile.client_id == client_id,
                ClientPostizPostingProfile.is_default == True,  # noqa: E712
            )
            .values(is_default=False, updated_at=datetime.now(timezone.utc))
        )
        self.session.execute(stmt)
        self.session.flush()


class PostizPublicationRepository:
    """Repository for Postiz publications."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self,
        *,
        org_id: str,
        client_id: str,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[List[PostizPublication], int]:
        stmt = select(PostizPublication).where(
            PostizPublication.org_id == org_id,
            PostizPublication.client_id == client_id,
        )
        if status:
            stmt = stmt.where(PostizPublication.status == status)

        count_stmt = select(PostizPublication.id).where(
            PostizPublication.org_id == org_id,
            PostizPublication.client_id == client_id,
        )
        if status:
            count_stmt = count_stmt.where(PostizPublication.status == status)
        total = len(list(self.session.scalars(count_stmt).all()))

        stmt = stmt.order_by(PostizPublication.created_at.desc()).limit(limit).offset(offset)
        publications = list(self.session.scalars(stmt).all())
        return publications, total

    def get(self, org_id: str, publication_id: str) -> Optional[PostizPublication]:
        stmt = select(PostizPublication).where(
            PostizPublication.id == publication_id,
            PostizPublication.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def get_by_postiz_id(
        self, org_id: str, client_id: str, postiz_post_id: str
    ) -> Optional[PostizPublication]:
        stmt = select(PostizPublication).where(
            PostizPublication.org_id == org_id,
            PostizPublication.client_id == client_id,
            PostizPublication.postiz_post_id == postiz_post_id,
        )
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        content: str,
        post_type: str = "now",
        scheduled_for: datetime | None = None,
        target_channels_json: dict[str, Any],
        media_urls_json: list[str] | None = None,
        link_url: str | None = None,
        provider_settings_by_identifier_json: dict[str, Any] | None = None,
        request_payload_json: dict[str, Any],
        postiz_posting_profile_id: str | None = None,
    ) -> PostizPublication:
        publication = PostizPublication(
            org_id=org_id,
            client_id=client_id,
            postiz_posting_profile_id=postiz_posting_profile_id,
            content=content,
            post_type=post_type,
            scheduled_for=scheduled_for,
            target_channels_json=target_channels_json,
            media_urls_json=media_urls_json or [],
            link_url=link_url,
            provider_settings_by_identifier_json=provider_settings_by_identifier_json or {},
            request_payload_json=request_payload_json,
            status="pending",
        )
        self.session.add(publication)
        self.session.flush()
        self.session.refresh(publication)
        return publication

    def update_on_success(
        self,
        *,
        org_id: str,
        publication_id: str,
        postiz_post_id: str | None,
        postiz_post_ids_json: list[str] | None = None,
        response_payload_json: dict[str, Any] | None = None,
        status: str = "published",
        release_urls_json: list[str] | None = None,
        postiz_post_status: str | None = None,
    ) -> Optional[PostizPublication]:
        pub = self.get(org_id=org_id, publication_id=publication_id)
        if pub is None:
            return None
        pub.postiz_post_id = postiz_post_id
        if postiz_post_ids_json is not None:
            pub.postiz_post_ids_json = postiz_post_ids_json
        if response_payload_json is not None:
            pub.response_payload_json = response_payload_json
        pub.status = status
        pub.postiz_post_status = postiz_post_status
        if release_urls_json is not None:
            pub.release_urls_json = release_urls_json
        pub.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(pub)
        return pub

    def update_on_error(
        self,
        *,
        org_id: str,
        publication_id: str,
        error_payload_json: dict[str, Any],
        status: str = "failed",
    ) -> Optional[PostizPublication]:
        pub = self.get(org_id=org_id, publication_id=publication_id)
        if pub is None:
            return None
        pub.error_payload_json = error_payload_json
        pub.status = status
        pub.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(pub)
        return pub

    def update_sync(
        self,
        *,
        org_id: str,
        publication_id: str,
        postiz_post_status: str | None = None,
        release_urls_json: list[str] | None = None,
        status: str | None = None,
    ) -> Optional[PostizPublication]:
        pub = self.get(org_id=org_id, publication_id=publication_id)
        if pub is None:
            return None
        if postiz_post_status is not None:
            pub.postiz_post_status = postiz_post_status
        if release_urls_json is not None:
            pub.release_urls_json = release_urls_json
        if status is not None:
            pub.status = status
        pub.last_synced_at = datetime.now(timezone.utc)
        pub.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.refresh(pub)
        return pub

    def delete(self, org_id: str, publication_id: str) -> bool:
        pub = self.get(org_id=org_id, publication_id=publication_id)
        if pub is None:
            return False
        self.session.delete(pub)
        self.session.flush()
        return True
