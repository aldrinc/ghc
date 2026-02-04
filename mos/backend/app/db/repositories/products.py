from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductOffer, ProductOfferPricePoint


class ProductsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, *, org_id: str, client_id: str) -> list[Product]:
        stmt = select(Product).where(Product.org_id == org_id, Product.client_id == client_id)
        return list(self.session.scalars(stmt).all())

    def get(self, *, org_id: str, product_id: str) -> Optional[Product]:
        stmt = select(Product).where(Product.org_id == org_id, Product.id == product_id)
        return self.session.scalars(stmt).first()

    def create(self, *, org_id: str, client_id: str, **fields: Any) -> Product:
        product = Product(org_id=org_id, client_id=client_id, **fields)
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


class ProductOfferPricePointsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_offer(self, *, offer_id: str) -> list[ProductOfferPricePoint]:
        stmt = select(ProductOfferPricePoint).where(ProductOfferPricePoint.offer_id == offer_id)
        return list(self.session.scalars(stmt).all())

    def get(self, *, price_point_id: str) -> Optional[ProductOfferPricePoint]:
        stmt = select(ProductOfferPricePoint).where(ProductOfferPricePoint.id == price_point_id)
        return self.session.scalars(stmt).first()

    def create(self, *, offer_id: str, **fields: Any) -> ProductOfferPricePoint:
        price_point = ProductOfferPricePoint(offer_id=offer_id, **fields)
        self.session.add(price_point)
        self.session.commit()
        self.session.refresh(price_point)
        return price_point

    def update(self, *, price_point_id: str, **fields: Any) -> Optional[ProductOfferPricePoint]:
        price_point = self.get(price_point_id=price_point_id)
        if not price_point:
            return None
        for key, value in fields.items():
            setattr(price_point, key, value)
        self.session.commit()
        self.session.refresh(price_point)
        return price_point
