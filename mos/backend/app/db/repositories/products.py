from __future__ import annotations

from uuid import UUID, uuid4
from typing import Any, Optional

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductOffer, ProductOfferBonus, ProductVariant

_SHORT_ID_LENGTH = 8
_MAX_SHORT_ID_GENERATION_ATTEMPTS = 32


class ProductsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _short_id_token(value: UUID | str) -> str:
        normalized = str(value).strip().lower()
        return normalized.split("-", 1)[0][:_SHORT_ID_LENGTH]

    def _short_id_exists(self, *, short_id: str) -> bool:
        stmt = (
            select(Product.id)
            .where(func.left(cast(Product.id, String), _SHORT_ID_LENGTH) == short_id)
            .limit(1)
        )
        return self.session.execute(stmt).first() is not None

    def _generate_unique_short_id_product_uuid(self) -> UUID:
        for _ in range(_MAX_SHORT_ID_GENERATION_ATTEMPTS):
            candidate = uuid4()
            if not self._short_id_exists(short_id=self._short_id_token(candidate)):
                return candidate
        raise ValueError(
            "Unable to allocate a unique 8-character product id prefix after "
            f"{_MAX_SHORT_ID_GENERATION_ATTEMPTS} attempts."
        )

    def list(self, *, org_id: str, client_id: str) -> list[Product]:
        stmt = select(Product).where(Product.org_id == org_id, Product.client_id == client_id)
        return list(self.session.scalars(stmt).all())

    def get(self, *, org_id: str, product_id: str) -> Optional[Product]:
        stmt = select(Product).where(Product.org_id == org_id, Product.id == product_id)
        return self.session.scalars(stmt).first()

    def create(self, *, org_id: str, client_id: str, **fields: Any) -> Product:
        payload = dict(fields)
        provided_id = payload.get("id")
        if provided_id is not None:
            try:
                normalized_id = UUID(str(provided_id))
            except ValueError as exc:
                raise ValueError("Product id must be a valid UUID.") from exc
            short_id = self._short_id_token(normalized_id)
            if self._short_id_exists(short_id=short_id):
                raise ValueError(
                    f"Product id prefix '{short_id}' already exists. Use a different id."
                )
            payload["id"] = normalized_id
        else:
            payload["id"] = self._generate_unique_short_id_product_uuid()

        product = Product(org_id=org_id, client_id=client_id, **payload)
        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)
        return product

    def update(self, *, org_id: str, product_id: str, **fields: Any) -> Optional[Product]:
        product = self.get(org_id=org_id, product_id=product_id)
        if not product:
            return None
        for key, value in fields.items():
            setattr(product, key, value)
        self.session.commit()
        self.session.refresh(product)
        return product


class ProductOffersRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_product(self, *, product_id: str) -> list[ProductOffer]:
        stmt = select(ProductOffer).where(ProductOffer.product_id == product_id)
        return list(self.session.scalars(stmt).all())

    def get(self, *, offer_id: str) -> Optional[ProductOffer]:
        stmt = select(ProductOffer).where(ProductOffer.id == offer_id)
        return self.session.scalars(stmt).first()

    def create(self, *, org_id: str, client_id: str, product_id: str, **fields: Any) -> ProductOffer:
        offer = ProductOffer(org_id=org_id, client_id=client_id, product_id=product_id, **fields)
        self.session.add(offer)
        self.session.commit()
        self.session.refresh(offer)
        return offer

    def update(self, *, offer_id: str, **fields: Any) -> Optional[ProductOffer]:
        offer = self.get(offer_id=offer_id)
        if not offer:
            return None
        for key, value in fields.items():
            setattr(offer, key, value)
        self.session.commit()
        self.session.refresh(offer)
        return offer


class ProductOfferBonusesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_offer(self, *, offer_id: str) -> list[ProductOfferBonus]:
        stmt = (
            select(ProductOfferBonus)
            .where(ProductOfferBonus.offer_id == offer_id)
            .order_by(ProductOfferBonus.position.asc(), ProductOfferBonus.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        offer_id: str,
        bonus_product_id: str,
        position: int,
    ) -> ProductOfferBonus:
        link = ProductOfferBonus(
            org_id=org_id,
            client_id=client_id,
            offer_id=offer_id,
            bonus_product_id=bonus_product_id,
            position=position,
        )
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link

    def delete_by_offer_and_bonus_product(
        self, *, offer_id: str, bonus_product_id: str
    ) -> bool:
        stmt = select(ProductOfferBonus).where(
            ProductOfferBonus.offer_id == offer_id,
            ProductOfferBonus.bonus_product_id == bonus_product_id,
        )
        link = self.session.scalars(stmt).first()
        if not link:
            return False
        self.session.delete(link)
        self.session.commit()
        return True


class ProductVariantsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_product(self, *, product_id: str) -> list[ProductVariant]:
        stmt = select(ProductVariant).where(ProductVariant.product_id == product_id)
        return list(self.session.scalars(stmt).all())

    def get(self, *, variant_id: str) -> Optional[ProductVariant]:
        stmt = select(ProductVariant).where(ProductVariant.id == variant_id)
        return self.session.scalars(stmt).first()

    def create(self, *, product_id: str, **fields: Any) -> ProductVariant:
        variant = ProductVariant(product_id=product_id, **fields)
        self.session.add(variant)
        self.session.commit()
        self.session.refresh(variant)
        return variant

    def update(self, *, variant_id: str, **fields: Any) -> Optional[ProductVariant]:
        variant = self.get(variant_id=variant_id)
        if not variant:
            return None
        for key, value in fields.items():
            setattr(variant, key, value)
        self.session.commit()
        self.session.refresh(variant)
        return variant
