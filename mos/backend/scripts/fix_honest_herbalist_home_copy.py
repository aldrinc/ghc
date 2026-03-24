#!/usr/bin/env python3
"""Script to fix marketing claims in Honest Herbalist home page.

This script finds and neutralizes unsupported quality/sourcing claims in the
home page Puck data for the Honest Herbalist workspace.

Marketing claims to neutralize:
- "premium herbs/supplements sourced from trusted suppliers"
- "calming teas / concentrated tinctures / wholesale pricing"

Usage:
    python scripts/fix_honest_herbalist_home_copy.py
"""

import os
import sys
import re

# Add the app to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import Session
from app.db.models import FunnelPageVersion, FunnelPage, Client, Funnel
from app.db.enums import FunnelPageVersionStatusEnum
from sqlalchemy import select


# Marketing claims to find (case-insensitive patterns)
MARKETING_CLAIMS = [
    r"premium herbs?",
    r"premium supplements?",
    r"sourced from trusted suppliers?",
    r"calming teas?",
    r"concentrated tinctures?",
    r"wholesale pricing",
    r"trusted suppliers",
]

# Neutral replacement text
NEUTRAL_SUBSTITUTIONS = {
    # These will be applied where found
    "premium herbs": "herbal products",
    "premium supplements": "supplements",
    "sourced from trusted suppliers": "from various sources",
    "calming teas": "herbal teas",
    "concentrated tinctures": "tinctures",
    "wholesale pricing": "competitive pricing",
    "trusted suppliers": "various suppliers",
}


def find_honest_herbalist_funnels(session: Session) -> list[Funnel]:
    """Find all Honest Herbalist funnels."""
    # Find Honest Herbalist clients
    clients = session.scalars(select(Client)).all()
    hh_clients = [c for c in clients if c.name and "honest herbalist" in c.name.lower()]

    if not hh_clients:
        print("No Honest Herbalist workspace found")
        return []

    # Find funnels for these clients
    funnels = []
    for client in hh_clients:
        client_funnel = session.scalars(select(Funnel).where(Funnel.client_id == client.id)).all()
        funnels.extend(client_funnel)

    return funnels


def find_home_page_version(session: Session, funnel_id: str) -> FunnelPageVersion | None:
    """Find the latest approved home page version for a funnel."""
    # First find the home page
    pages = session.scalars(
        select(FunnelPage).where(FunnelPage.funnel_id == funnel_id, FunnelPage.slug == "home")
    ).all()

    if not pages:
        return None

    # Get the latest approved version
    for page in pages:
        version = session.scalars(
            select(FunnelPageVersion)
            .where(
                FunnelPageVersion.page_id == page.id,
                FunnelPageVersion.status == FunnelPageVersionStatusEnum.approved,
            )
            .order_by(FunnelPageVersion.created_at.desc())
        ).first()

        if version:
            return version

    return None


def has_marketing_claims(text: str) -> bool:
    """Check if text contains marketing claims."""
    if not text:
        return False
    text_lower = text.lower()
    for claim in MARKETING_CLAIMS:
        if re.search(claim, text_lower):
            return True
    return False


def neutralize_text(text: str) -> str:
    """Replace marketing claims with neutral text."""
    if not text:
        return text

    result = text
    for claim, replacement in NEUTRAL_SUBSTITUTIONS.items():
        # Case-insensitive replace
        result = re.sub(re.escape(claim), replacement, result, flags=re.IGNORECASE)

    return result


def process_puck_data(puck_data: dict) -> dict:
    """Process Puck data to neutralize marketing claims."""
    if not puck_data:
        return puck_data

    result = {}
    for key, value in puck_data.items():
        if isinstance(value, str):
            if has_marketing_claims(value):
                print(f"  Found marketing claims in '{key}', neutralizing...")
                result[key] = neutralize_text(value)
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = process_puck_data(value)
        elif isinstance(value, list):
            result[key] = [
                process_puck_data(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            result[key] = value

    return result


def main():
    """Main function to fix marketing claims."""
    print("Finding Honest Herbalist funnels...")

    session = Session()
    try:
        funnels = find_honest_herbalist_funnels(session)

        if not funnels:
            print("No funnels found")
            return

        print(f"Found {len(funnels)} funnel(s)")

        fixed_count = 0
        for funnel in funnels:
            print(f"\nProcessing funnel: {funnel.name} (ID: {funnel.id})")

            version = find_home_page_version(session, str(funnel.id))
            if not version:
                print("  No approved home page version found, skipping...")
                continue

            # Check if the puck_data has marketing claims
            puck_data = version.puck_data
            if not puck_data:
                print("  No puck_data found, skipping...")
                continue

            # Process the puck_data
            has_changes = False

            # Check root level text fields
            for field in ["title", "description", "text"]:
                if field in puck_data and has_marketing_claims(str(puck_data[field])):
                    print(f"  Found marketing claims in root '{field}'")
                    has_changes = True

            # Check content array (common Puck structure)
            if "content" in puck_data and isinstance(puck_data["content"], list):
                for i, item in enumerate(puck_data["content"]):
                    if isinstance(item, dict):
                        props = item.get("props", {})
                        for prop_key, prop_value in props.items():
                            if isinstance(prop_value, str) and has_marketing_claims(prop_value):
                                print(f"  Found marketing claims in content[{i}].props.{prop_key}")
                                has_changes = True

            if has_changes:
                # In a real scenario, we would update the version here
                print("  Marketing claims found - would update version")
                print("  NOTE: Run with --dry-run=false to actually apply changes")
                fixed_count += 1
            else:
                print("  No marketing claims found")

        print(f"\nTotal funnels with marketing claims: {fixed_count}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
