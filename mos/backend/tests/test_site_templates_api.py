from uuid import uuid4

from app.db.models import SiteImport
from app.db.repositories.sites_runtime import SitesRuntimeRepository


def _imported_page_puck_data() -> dict:
    return {
        "root": {
            "props": {
                "title": "Imported source page",
                "description": "Imported runtime source",
            }
        },
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "imported-page-1",
                    "pageName": "Imported source page",
                    "pageType": "product_detail",
                    "renderMode": "source",
                    "sharedRuntimeSource": "const ProductPurchaseSection = () => null;",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "imported-section-1",
                                "content": [
                                    {
                                        "type": "ImportedRuntimeSection",
                                        "props": {
                                            "id": "imported-runtime-1",
                                            "sectionLabel": "Imported source page",
                                            "componentName": "ProductPurchaseSection",
                                            "textOverrides": [],
                                            "imageOverrides": [],
                                            "buttonOverrides": [
                                                {
                                                    "key": "button-1",
                                                    "label": "Button 1",
                                                    "originalText": "ADD TO CART -",
                                                    "text": "ADD TO CART -",
                                                    "href": "",
                                                }
                                            ],
                                        },
                                    }
                                ],
                                "surface": "source",
                                "renderMode": "source",
                                "sectionKey": "productpurchasesection",
                                "displayName": "Imported source page",
                                "sectionType": "bundle_selector",
                                "sourceSectionId": "product-purchase-section",
                                "semanticTagsText": "bundle_selector, purchase, offers",
                            },
                        }
                    ],
                },
            }
        ],
        "zones": {},
    }


def test_create_template_from_imported_site_and_instantiate_preserves_page_content(
    api_client,
    db_session,
    seed_data,
):
    client = seed_data["client"]
    runtime_repo = SitesRuntimeRepository(db_session)

    source_site = runtime_repo.create_site(
        org_id=str(client.org_id),
        client_id=str(client.id),
        name="OMNI Creatine Gummy",
        description="Imported OMNI page",
        site_type="ecommerce",
        site_family="sales-pdp",
        commerce_provider=None,
        route_slug="omni-creatine-gummy",
        theme_binding_mode="standalone",
    )

    source_page = runtime_repo.create_page(
        site_id=str(source_site.id),
        name="OMNI Creatine Gummy",
        slug="product-detail",
        page_type="product_detail",
        page_role="product_detail",
        ordering=0,
        adapted_puck_data=_imported_page_puck_data(),
    )
    runtime_repo.create_page_version(
        page_id=str(source_page.id),
        puck_data=_imported_page_puck_data(),
        provenance={"source_type": "test"},
        status="approved",
        source_type="site_import",
        source_id="test-import",
    )
    source_site.entry_page_id = str(source_page.id)

    site_import = SiteImport(
        id=str(uuid4()),
        org_id=client.org_id,
        client_id=client.id,
        source_url="archive://omni.zip",
        source_hostname="archive",
        input_mode="archive",
        status="completed",
        title="OMNI Creatine Gummy",
        suggested_template_family="imported-template",
        resolved_site_family="imported-template",
        resolved_page_type="product_detail",
        saved_site_id=str(source_site.id),
    )
    db_session.add(site_import)
    db_session.flush()

    source_site.site_import_id = str(site_import.id)
    db_session.add(source_site)
    db_session.commit()

    create_template_response = api_client.post(
        f"/sites/{source_site.id}/create-template?clientId={client.id}",
        json={
            "name": "OMNI One Product Store",
            "description": "Workspace starter sourced from the imported Omni page",
        },
    )
    assert create_template_response.status_code == 201, create_template_response.text
    template_payload = create_template_response.json()
    assert template_payload["family"] == "imported-template"
    assert template_payload["pageCount"] == 17
    assert template_payload["commerceProvider"] == "medusa"

    instantiate_response = api_client.post(
        f"/site-templates/{template_payload['id']}/instantiate",
        json={
            "clientId": str(client.id),
            "name": "OMNI One Product Instance",
            "description": "Instantiated from saved site template",
        },
    )
    assert instantiate_response.status_code == 201, instantiate_response.text
    instantiated_site_id = instantiate_response.json()["siteId"]

    instantiated_site_response = api_client.get(
        f"/sites/{instantiated_site_id}?clientId={client.id}"
    )
    assert instantiated_site_response.status_code == 200, instantiated_site_response.text
    instantiated_site = instantiated_site_response.json()
    assert instantiated_site["siteFamily"] == "imported-template"
    assert instantiated_site["commerceProvider"] == "medusa"
    assert len(instantiated_site["pages"]) == 17
    home_page = next(page for page in instantiated_site["pages"] if page["pageType"] == "home")
    assert home_page["slug"] == "home"
    assert any(page["pageType"] == "checkout" for page in instantiated_site["pages"])
    assert any(page["pageType"] == "contact_support" for page in instantiated_site["pages"])

    page_id = home_page["id"]
    page_response = api_client.get(
        f"/sites/{instantiated_site_id}/pages/{page_id}?clientId={client.id}"
    )
    assert page_response.status_code == 200, page_response.text
    page_payload = page_response.json()
    assert page_payload["latestApproved"]["puckData"]["root"]["props"]["title"] == "Imported source page"
    assert page_payload["latestApproved"]["puckData"]["content"][0]["type"] == "ImportedPage"
    button_override = (
        page_payload["latestApproved"]["puckData"]["content"][0]["props"]["content"][0]["props"]["content"][0]["props"]["buttonOverrides"][0]
    )
    assert button_override["text"] == "BUY NOW -"
    assert button_override["action"] == "medusa_buy_now"
    assert button_override["selectionStrategy"] == "omni_selected_tier"
    assert button_override["replaceCart"] is True
