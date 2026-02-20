from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import ClientComplianceProfile


class ClientComplianceProfilesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, org_id: str, client_id: str) -> Optional[ClientComplianceProfile]:
        stmt = select(ClientComplianceProfile).where(
            ClientComplianceProfile.org_id == org_id,
            ClientComplianceProfile.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        ruleset_version: str,
        business_models: list[str],
        legal_business_name: str | None,
        operating_entity_name: str | None,
        company_address_text: str | None,
        business_license_identifier: str | None,
        support_email: str | None,
        support_phone: str | None,
        support_hours_text: str | None,
        response_time_commitment: str | None,
        privacy_policy_url: str | None,
        terms_of_service_url: str | None,
        returns_refunds_policy_url: str | None,
        shipping_policy_url: str | None,
        contact_support_url: str | None,
        company_information_url: str | None,
        subscription_terms_and_cancellation_url: str | None,
        metadata_json: dict[str, Any],
    ) -> ClientComplianceProfile:
        record = self.get(org_id=org_id, client_id=client_id)
        if record is None:
            record = ClientComplianceProfile(
                org_id=org_id,
                client_id=client_id,
                ruleset_version=ruleset_version,
                business_models=business_models,
                legal_business_name=legal_business_name,
                operating_entity_name=operating_entity_name,
                company_address_text=company_address_text,
                business_license_identifier=business_license_identifier,
                support_email=support_email,
                support_phone=support_phone,
                support_hours_text=support_hours_text,
                response_time_commitment=response_time_commitment,
                privacy_policy_url=privacy_policy_url,
                terms_of_service_url=terms_of_service_url,
                returns_refunds_policy_url=returns_refunds_policy_url,
                shipping_policy_url=shipping_policy_url,
                contact_support_url=contact_support_url,
                company_information_url=company_information_url,
                subscription_terms_and_cancellation_url=subscription_terms_and_cancellation_url,
                metadata_json=metadata_json,
            )
            self.session.add(record)
            self.session.commit()
            self.session.refresh(record)
            return record

        record.ruleset_version = ruleset_version
        record.business_models = business_models
        record.legal_business_name = legal_business_name
        record.operating_entity_name = operating_entity_name
        record.company_address_text = company_address_text
        record.business_license_identifier = business_license_identifier
        record.support_email = support_email
        record.support_phone = support_phone
        record.support_hours_text = support_hours_text
        record.response_time_commitment = response_time_commitment
        record.privacy_policy_url = privacy_policy_url
        record.terms_of_service_url = terms_of_service_url
        record.returns_refunds_policy_url = returns_refunds_policy_url
        record.shipping_policy_url = shipping_policy_url
        record.contact_support_url = contact_support_url
        record.company_information_url = company_information_url
        record.subscription_terms_and_cancellation_url = subscription_terms_and_cancellation_url
        record.metadata_json = metadata_json
        record.updated_at = func.now()

        self.session.commit()
        self.session.refresh(record)
        return record
