from __future__ import annotations

import json
import os
import argparse
import shlex
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://app:app@localhost:5433/app")
os.environ.setdefault("CLERK_JWT_ISSUER", "https://clerk.local")
os.environ.setdefault("CLERK_JWKS_URL", "https://clerk.local/.well-known/jwks.json")

from app.services import deploy as deploy_service
import cloudhand.adapters.deployer as deployer_module
from cloudhand.adapters.deployer import ServerDeployer
from cloudhand.models import FunnelArtifactSourceSpec


RELEASE_ID = "candidate-local-listicle"
PRODUCT_SLUG = "local-product"
FUNNEL_SLUG = "local-listicle"
LISTICLE_SLUG = "listicle"
QUIZ_SLUG = "quiz"
SALES_SLUG = "sales-page"
LISTICLE_PAGE_ID = "page-listicle"
QUIZ_PAGE_ID = "page-quiz"
SALES_PAGE_ID = "page-sales"
PUBLICATION_ID = "publication-local"


def _html_shell(*, title: str, body: str, origin: str, page_stage: str) -> str:
    page_slug = LISTICLE_SLUG if page_stage == "pre_sales" else SALES_SLUG
    page_id = "page-listicle" if page_stage == "pre_sales" else "page-sales"
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style data-mos-render-optimization="true">
      body {{ margin: 0; }}
    </style>
    <script src="https://connect.facebook.net/en_US/fbevents.js"></script>
    <script>
      window.fbq = function() {{}};
      window.fbq("init", "pixel-local");
      window.posthog = {{}};
      window.posthog.init = function(apiKey, config, instanceName) {{
        window.posthog[instanceName] = {{
          capture: function() {{}}
        }};
      }};
      window.posthog.init("phx_local", {{
        api_host: "{origin}",
        ui_host: "{origin}",
        defaults: "2026-01-30",
        person_profiles: "identified_only"
      }}, "mosFunnel");
      function normalizePresaleSourcePageType(value) {{
        const normalized = String(value || "").trim().toLowerCase().replace(/-/g, "_");
        if (normalized === "quiz" || normalized === "quiz_funnel" || normalized === "quiz_presell") return "quiz_presell";
        if (normalized === "listical" || normalized === "listicle" || normalized === "listicle_hybrid" || normalized === "listical_presell" || normalized === "listicle_presell") return "listical_presell";
        return normalized || "";
      }}
      const query = new URLSearchParams(window.location.search);
      const sourceContext = {{}};
      if ("{page_stage}" === "pre_sales") {{
        sourceContext.source_page_type = "listical_presell";
      }}
      if ("{page_stage}" === "sales") {{
        const sourcePageType = normalizePresaleSourcePageType(query.get("source_page_type") || query.get("from"));
        if (sourcePageType) {{
          sourceContext.source_page_type = sourcePageType;
          sourceContext.from_stage = "pre_sales";
          sourceContext.to_stage = "sales";
        }}
      }}
      const bridge = {{
        session_id: query.get("session_id") || query.get("rmbc_session_id") || "local-session-1",
        visitor_id: query.get("visitor_id") || query.get("rmbc_anonymous_id") || "local-visitor-1",
        click_id: query.get("click_id") || query.get("rmbc_click_id") || "local-click-1"
      }};
      const baseProps = Object.assign({{
        product_slug: "{PRODUCT_SLUG}",
        funnel_slug: "{FUNNEL_SLUG}",
        publication_id: "publication-local",
        page_id: "{page_id}",
        page_slug: "{page_slug}",
        page_stage: "{page_stage}",
        content_category: "{'presell_page' if page_stage == 'pre_sales' else 'sales_page'}",
        session_id: bridge.session_id,
        visitor_id: bridge.visitor_id,
        click_id: bridge.click_id
      }}, sourceContext);
      function sendInternal(eventType, props) {{
        return fetch("/public/events", {{
          method: "POST",
          headers: {{ "content-type": "application/json" }},
          body: JSON.stringify({{ events: [{{ eventType, props: props || {{}} }}] }})
        }}).catch(function() {{}});
      }}
      function captureAll(eventName, props) {{
        const merged = Object.assign({{}}, baseProps, props || {{}});
        sendInternal(eventName, merged);
        window.posthog.mosFunnel.capture(eventName, merged);
        window.fbq("trackCustom", eventName, Object.assign({{}}, merged, {{
          event_source_url: window.location.href
        }}));
      }}
    </script>
  </head>
  <body>
    {body}
  </body>
</html>
"""


def _listicle_html(*, origin: str) -> str:
    return _html_shell(
        title="Local Listicle Candidate",
        origin=origin,
        page_stage="pre_sales",
        body=f"""
    <main>
      <h1>Local listicle candidate</h1>
      <a id="to-sales" href="/{PRODUCT_SLUG}/{FUNNEL_SLUG}/{SALES_SLUG}/">Continue</a>
    </main>
    <script>
      window.addEventListener("DOMContentLoaded", function() {{
        captureAll("Entered Funnel");
        captureAll("pre_sales_page_view");
        captureAll("presell_page_view");
        captureAll("EnteredPresales");
        captureAll("Entered Presales Page");
        window.fbq("track", "PageView", Object.assign({{}}, baseProps, {{ event_source_url: window.location.href }}));
        window.posthog.mosFunnel.capture("PageView", baseProps);
      }});
      document.getElementById("to-sales").addEventListener("click", function(event) {{
        event.preventDefault();
        const params = new URLSearchParams(window.location.search);
        params.set("session_id", bridge.session_id);
        params.set("visitor_id", bridge.visitor_id);
        params.set("click_id", bridge.click_id);
        params.set("source_page_type", "listical_presell");
        params.set("from_stage", "pre_sales");
        params.set("to_stage", "sales");
        const destination = "/{PRODUCT_SLUG}/{FUNNEL_SLUG}/{SALES_SLUG}/?" + params.toString();
        const clickProps = Object.assign({{}}, baseProps, {{
          destination_url: destination,
          page_id: "page-listicle",
          page_slug: "{LISTICLE_SLUG}",
          page_stage: "pre_sales",
          source_page_type: "listical_presell",
          from_stage: "pre_sales",
          to_stage: "sales"
        }});
        captureAll("pre_sales_to_sales_click", clickProps);
        captureAll("cta_click", clickProps);
        captureAll("PreSalesToSalesClick", clickProps);
        setTimeout(function() {{ window.location.href = destination; }}, 50);
      }});
    </script>
""",
    )


def _sales_html(*, origin: str) -> str:
    return _html_shell(
        title="Local Sales Candidate",
        origin=origin,
        page_stage="sales",
        body="""
    <main>
      <h1>Local sales candidate</h1>
      <button id="checkout-btn" type="button">Checkout</button>
    </main>
    <script>
      window.addEventListener("DOMContentLoaded", function() {
        captureAll("sales_page_view", { content_category: "sales_page" });
        captureAll("Entered Sales Page", { content_category: "sales_page" });
        captureAll("EnteredSales", { content_category: "sales_page" });
        captureAll("ViewContent", { content_category: "sales_page" });
        captureAll("offer_page_view", { content_category: "sales_page" });
        window.fbq("track", "PageView", Object.assign({}, baseProps, { event_source_url: window.location.href }));
        window.posthog.mosFunnel.capture("PageView", baseProps);
      });
      document.getElementById("checkout-btn").addEventListener("click", function() {
        captureAll("sales_to_checkout_click", { content_category: "sales_page" });
        captureAll("AddToCart", { content_category: "sales_page" });
        captureAll("SalesToCheckoutClick", { content_category: "sales_page" });
        captureAll("SalesToCheckoutClicked", { content_category: "sales_page" });
        fetch("/api/public/checkout", { method: "POST" }).catch(function() {});
      });
    </script>
""",
    )


def _quiz_html_document() -> str:
    return """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Local quiz candidate</title></head>
  <body>
    <main>
      <section id="quiz-lead"><h1>Local quiz candidate</h1></section>
      <section id="quiz-question"><button id="quiz-option" type="button">Option A</button></section>
      <section id="quiz-result">Your result</section>
      <section id="quiz-recommendation">Recommended bundle</section>
      <a id="to-sales" href="/local-product/local-listicle/sales-page/">Continue</a>
    </main>
    <script>
      (function() {
        function emit(eventType, props) {
          window.dispatchEvent(new CustomEvent("mos:track-event", {
            detail: { eventType: eventType, props: props || {} }
          }));
        }
        function emitQuizPathOnce() {
          if (window.sessionStorage.getItem("local_quiz_path_emitted") === "1") return;
          window.sessionStorage.setItem("local_quiz_path_emitted", "1");
          var base = {
            quiz_id: "local-quiz",
            quizId: "local-quiz",
            quiz_version: "v1",
            quizVersion: "v1",
            question_id: "q1",
            questionId: "q1",
            result_id: "result-a",
            resultId: "result-a",
            recommendation_id: "rec-a",
            recommendationId: "rec-a",
            cta_id: "to-sales",
            ctaId: "to-sales"
          };
          emit("quiz_lead_viewed", base);
          emit("quiz_question_viewed", base);
          emit("quiz_option_presented", base);
          emit("quiz_option_selected", Object.assign({}, base, { option_id: "a", optionId: "a" }));
          emit("quiz_question_submitted", base);
          emit("quiz_completed", Object.assign({}, base, { answer_path_id: "path-a", answerPathId: "path-a" }));
          emit("quiz_result_viewed", base);
          emit("quiz_recommendation_viewed", base);
          emit("quiz_cta_viewed", base);
        }
        window.addEventListener("DOMContentLoaded", function() {
          window.setTimeout(emitQuizPathOnce, 500);
        });
      })();
    </script>
  </body>
</html>
"""


def _build_imported_page(
    *,
    page_id: str,
    slug: str,
    stage: str,
    html_artifact_kind: str,
    html_document: str,
    bindings: list[dict],
    tracking: dict,
    manifest_overrides: dict | None = None,
) -> dict:
    manifest = {
        "schemaVersion": "html-deploy-v1",
        "htmlArtifactKind": html_artifact_kind,
        "pageStage": stage,
        "bindings": bindings,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    return {
        "funnelId": "funnel-local",
        "funnelSlug": FUNNEL_SLUG,
        "productSlug": PRODUCT_SLUG,
        "publicationId": PUBLICATION_ID,
        "pageId": page_id,
        "slug": slug,
        "stage": stage,
        "tracking": tracking,
        "pageMap": {
            LISTICLE_PAGE_ID: LISTICLE_SLUG,
            QUIZ_PAGE_ID: QUIZ_SLUG,
            SALES_PAGE_ID: SALES_SLUG,
        },
        "pageStageMap": {
            LISTICLE_PAGE_ID: "pre_sales",
            QUIZ_PAGE_ID: "pre_sales",
            SALES_PAGE_ID: "sales",
        },
        "puckData": {
            "root": {"props": {"title": slug}},
            "content": [
                {
                    "type": "ImportedHtmlDocument",
                    "props": {
                        "id": f"imported-{slug}",
                        "title": slug,
                        "sourceLabel": f"{slug}.html",
                        "htmlDocument": html_document,
                        "instrumentationManifest": manifest,
                    },
                }
            ],
            "zones": {},
        },
    }


def _build_local_funnel_source(
    *,
    presales_html: str,
    presales_slug: str,
    presales_page_id: str,
    presales_artifact_kind: str,
    sales_html: str,
    tracking: dict,
    presales_manifest_overrides: dict | None = None,
) -> FunnelArtifactSourceSpec:
    artifact = {
        "meta": {
            "clientId": "local-client",
            "artifactId": "local-candidate-artifact",
        },
        "products": {
            PRODUCT_SLUG: {
                "meta": {
                    "productId": "product-local",
                    "productSlug": PRODUCT_SLUG,
                },
                "funnels": {
                    FUNNEL_SLUG: {
                        "funnelId": "funnel-local",
                        "meta": {
                            "funnelSlug": FUNNEL_SLUG,
                            "funnelId": "funnel-local",
                            "publicationId": PUBLICATION_ID,
                            "entrySlug": presales_slug,
                            "pages": [
                                {"pageId": presales_page_id, "slug": presales_slug},
                                {"pageId": SALES_PAGE_ID, "slug": SALES_SLUG},
                            ],
                        },
                        "pages": {
                            presales_slug: _build_imported_page(
                                page_id=presales_page_id,
                                slug=presales_slug,
                                stage="pre_sales",
                                html_artifact_kind=presales_artifact_kind,
                                html_document=presales_html,
                                tracking=tracking,
                                manifest_overrides=presales_manifest_overrides,
                                bindings=[
                                    {
                                        "id": "to-sales",
                                        "type": "internal_navigation",
                                        "selector": "#to-sales",
                                        "event": "click",
                                        "targetPageId": SALES_PAGE_ID,
                                        "trackEventType": "pre_sales_to_sales_click",
                                    }
                                ],
                            ),
                            SALES_SLUG: _build_imported_page(
                                page_id=SALES_PAGE_ID,
                                slug=SALES_SLUG,
                                stage="sales",
                                html_artifact_kind="sales",
                                html_document=sales_html,
                                tracking=tracking,
                                bindings=[
                                    {
                                        "id": "checkout",
                                        "type": "checkout",
                                        "selector": "#checkout-btn",
                                        "event": "click",
                                        "trackEventType": "sales_to_checkout_click",
                                        "checkout": {
                                            "mode": "public_checkout",
                                            "variantResolver": {
                                                "type": "fixed",
                                                "variantId": "variant-local",
                                            },
                                        },
                                    }
                                ],
                            ),
                        },
                        "commerce": {
                            "productSlug": PRODUCT_SLUG,
                            "funnelSlug": FUNNEL_SLUG,
                            "funnelId": "funnel-local",
                            "product": {
                                "id": "product-local",
                                "variants": [
                                    {
                                        "id": "variant-local",
                                        "provider": "shopify",
                                        "price": 117,
                                        "currency": "USD",
                                        "option_values": {},
                                    }
                                ],
                                "variants_count": 1,
                            },
                        },
                    }
                },
            }
        },
    }
    return FunnelArtifactSourceSpec.model_validate(
        {
            "client_id": "local-client",
            "upstream_api_base_root": tracking["posthogApiHost"],
            "artifact_render_mode": "html_deploy",
            "artifact": artifact,
        }
    )


def _make_local_renderer_deployer() -> ServerDeployer:
    deployer = object.__new__(ServerDeployer)
    deployer.ip = "127.0.0.1"
    deployer.local_root = Path.cwd()
    deployer._remote_directory_cache = {"/"}

    def upload_file(content: str, remote_path: str) -> None:
        target = Path(remote_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")

    def upload_bytes(content: bytes, remote_path: str) -> None:
        target = Path(remote_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(content))

    def run(cmd: str, cwd: str | None = None, mask=None) -> str:
        parts = shlex.split(cmd)
        if len(parts) >= 3 and parts[0] == "mkdir" and parts[1] == "-p":
            for raw_path in parts[2:]:
                Path(raw_path).mkdir(parents=True, exist_ok=True)
        return ""

    deployer.upload_file = upload_file  # type: ignore[method-assign]
    deployer.upload_bytes = upload_bytes  # type: ignore[method-assign]
    deployer.run = run  # type: ignore[method-assign]
    deployer._path_exists = lambda path: Path(str(path)).exists()  # type: ignore[method-assign]
    deployer._enable_https = lambda server_names: None  # type: ignore[method-assign]
    deployer._measure_html_deploy_image_layouts = lambda **_: {}  # type: ignore[method-assign]
    deployer._validate_html_deploy_visual_parity = lambda **_: None  # type: ignore[method-assign]
    return deployer


def _write_candidate_site_from_html(
    root: Path,
    *,
    origin: str,
    listicle_html_path: Path,
    asset_root: Path,
    tracking: dict,
) -> None:
    candidate_root = root / "site-releases" / RELEASE_ID
    live_root = root / "site"
    live_root.mkdir(parents=True)
    (live_root / "index.html").write_text(
        "<!doctype html><html><body>old live bundle</body></html>",
        encoding="utf-8",
    )

    listicle_html = listicle_html_path.read_text(encoding="utf-8")
    sales_html = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Local sales candidate</title></head>
  <body>
    <main>
      <h1>Local sales candidate</h1>
      <button id="checkout-btn" type="button">Checkout</button>
    </main>
  </body>
</html>
"""
    source = _build_local_funnel_source(
        presales_html=listicle_html,
        presales_slug=LISTICLE_SLUG,
        presales_page_id=LISTICLE_PAGE_ID,
        presales_artifact_kind="listicle",
        sales_html=sales_html,
        tracking=tracking,
    )
    deployer = _make_local_renderer_deployer()
    original_roots = deployer_module._STANDALONE_LOCAL_IMAGE_ASSET_ROOTS
    deployer_module._STANDALONE_LOCAL_IMAGE_ASSET_ROOTS = (asset_root, *original_roots)
    try:
        deployer._write_funnel_artifact_standalone_html_routes(
            site_dir=str(candidate_root),
            source=source,
            public_server_names=["127.0.0.1"],
            mirrored_target_paths=set(),
            standalone_served_assets={},
            standalone_image_sources={},
        )
    finally:
        deployer_module._STANDALONE_LOCAL_IMAGE_ASSET_ROOTS = original_roots


def _write_quiz_candidate_site_from_fixture(
    root: Path,
    *,
    tracking: dict,
) -> None:
    candidate_root = root / "site-releases" / RELEASE_ID
    live_root = root / "site"
    live_root.mkdir(parents=True)
    (live_root / "index.html").write_text(
        "<!doctype html><html><body>old live bundle</body></html>",
        encoding="utf-8",
    )
    sales_html = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Local sales candidate</title></head>
  <body>
    <main>
      <h1>Local sales candidate</h1>
      <button id="checkout-btn" type="button">Checkout</button>
    </main>
  </body>
</html>
"""
    source = _build_local_funnel_source(
        presales_html=_quiz_html_document(),
        presales_slug=QUIZ_SLUG,
        presales_page_id=QUIZ_PAGE_ID,
        presales_artifact_kind="quiz",
        sales_html=sales_html,
        tracking=tracking,
        presales_manifest_overrides={
            "quizId": "local-quiz",
            "quizVersion": "v1",
            "quizVariant": "default",
            "quizLeads": [{"id": "quiz-lead", "selector": "#quiz-lead"}],
            "quizQuestions": [{"id": "q1", "selector": "#quiz-question", "questionIndex": 1}],
            "quizOptions": [
                {
                    "id": "a",
                    "selector": "#quiz-option",
                    "questionId": "q1",
                    "questionIndex": 1,
                    "optionId": "a",
                }
            ],
            "quizResults": [{"id": "result-a", "selector": "#quiz-result"}],
            "quizRecommendations": [{"id": "rec-a", "selector": "#quiz-recommendation"}],
            "ctas": [{"id": "to-sales", "selector": "#to-sales", "ctaPosition": 1}],
        },
    )
    deployer = _make_local_renderer_deployer()
    deployer._write_funnel_artifact_standalone_html_routes(
        site_dir=str(candidate_root),
        source=source,
        public_server_names=["127.0.0.1"],
        mirrored_target_paths=set(),
        standalone_served_assets={},
        standalone_image_sources={},
    )


def _write_candidate_site(root: Path, *, origin: str) -> None:
    candidate_root = root / "site-releases" / RELEASE_ID / PRODUCT_SLUG / FUNNEL_SLUG
    live_root = root / "site"
    (candidate_root / LISTICLE_SLUG).mkdir(parents=True)
    (candidate_root / SALES_SLUG).mkdir(parents=True)
    live_root.mkdir(parents=True)
    (live_root / "index.html").write_text(
        "<!doctype html><html><body>old live bundle</body></html>",
        encoding="utf-8",
    )
    (candidate_root / LISTICLE_SLUG / "index.html").write_text(
        _listicle_html(origin=origin),
        encoding="utf-8",
    )
    (candidate_root / SALES_SLUG / "index.html").write_text(
        _sales_html(origin=origin),
        encoding="utf-8",
    )


class CandidateHandler(BaseHTTPRequestHandler):
    root: Path

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if (
            self.path.startswith("/public/events")
            or self.path.startswith("/api/public/events")
            or self.path.startswith("/api/public/checkout")
        ):
            self._send(200, b"{}", "application/json")
            return
        self._send(404, b"not found", "text/plain")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/__mos/meta/fbevents.js":
            self._send(200, b"window.fbq=function(){};/* /__mos/meta/tr */", "application/javascript")
            return
        if parsed.path == "/__mos/meta/tr/":
            self._send(200, b"ok", "text/plain")
            return
        if parsed.path == "/static/array.js":
            self._send(200, b"window.__localPosthogAssetLoaded=true;", "application/javascript")
            return
        query = parse_qs(parsed.query)
        release_id = (query.get(deploy_service._HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM) or [""])[0]
        cookie = self.headers.get("cookie") or ""
        has_candidate_cookie = (
            f"{deploy_service._HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM}={RELEASE_ID}" in cookie
        )
        if parsed.path.startswith("/_standalone-assets/") and has_candidate_cookie:
            target = self.root / "site-releases" / RELEASE_ID / parsed.path.lstrip("/")
        elif release_id == RELEASE_ID:
            target = self.root / "site-releases" / release_id / parsed.path.lstrip("/")
        else:
            target = self.root / "site" / parsed.path.lstrip("/")
        if target.is_dir():
            target = target / "index.html"
        if target.is_file():
            content_type = "text/html; charset=utf-8"
            if parsed.path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
                content_type = "image/svg+xml" if parsed.path.lower().endswith(".svg") else "image/*"
            headers = None
            if release_id == RELEASE_ID:
                headers = {
                    "set-cookie": (
                        f"{deploy_service._HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM}={RELEASE_ID}; "
                        "Path=/; SameSite=Lax"
                    )
                }
            self._send(200, target.read_bytes(), content_type, headers=headers)
            return
        self._send(404, b"not found", "text/plain")

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a local html-deploy candidate release without promoting live."
    )
    parser.add_argument(
        "--listicle-html",
        type=Path,
        help="Optional raw listicle HTML file to render through the html-deploy-v1 bridge.",
    )
    parser.add_argument(
        "--fixture",
        choices=("listicle", "quiz"),
        default="listicle",
        help="Local generated fixture to validate when --listicle-html is not provided.",
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        help="Optional root used to resolve relative image assets from --listicle-html.",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="html-deploy-candidate-local-") as tmp_dir:
        root = Path(tmp_dir)
        server = ThreadingHTTPServer(("127.0.0.1", 0), CandidateHandler)
        CandidateHandler.root = root
        origin = f"http://127.0.0.1:{server.server_port}"
        tracking = {
            "metaPixelId": "pixel-local",
            "posthogProjectApiKey": "phx_local",
            "posthogApiHost": origin,
            "posthogUiHost": origin,
            "posthogDefaults": "2026-01-30",
            "posthogPersonProfiles": "identified_only",
        }
        start_slug = LISTICLE_SLUG
        start_page_id = LISTICLE_PAGE_ID
        start_artifact_kind = "listicle"
        if args.listicle_html:
            listicle_html_path = args.listicle_html.expanduser().resolve()
            if not listicle_html_path.is_file():
                raise SystemExit(f"listicle HTML file not found: {listicle_html_path}")
            asset_root = (
                args.asset_root.expanduser().resolve()
                if args.asset_root
                else listicle_html_path.parent
            )
            _write_candidate_site_from_html(
                root,
                origin=origin,
                listicle_html_path=listicle_html_path,
                asset_root=asset_root,
                tracking=tracking,
            )
        elif args.fixture == "quiz":
            start_slug = QUIZ_SLUG
            start_page_id = QUIZ_PAGE_ID
            start_artifact_kind = "quiz"
            _write_quiz_candidate_site_from_fixture(root, tracking=tracking)
        else:
            _write_candidate_site(root, origin=origin)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            start_url = f"{origin}/{PRODUCT_SLUG}/{FUNNEL_SLUG}/{start_slug}/"
            sales_url = f"{origin}/{PRODUCT_SLUG}/{FUNNEL_SLUG}/{SALES_SLUG}/"
            quiz_internal_events = (
                [
                    "quiz_lead_viewed",
                    "quiz_question_viewed",
                    "quiz_option_presented",
                    "quiz_option_selected",
                    "quiz_question_submitted",
                    "quiz_completed",
                    "quiz_result_viewed",
                    "quiz_recommendation_viewed",
                    "quiz_cta_viewed",
                ]
                if start_artifact_kind == "quiz"
                else []
            )
            quiz_posthog_events = (
                [
                    "QuizLeadViewed",
                    "QuizQuestionViewed",
                    "QuizOptionPresented",
                    "QuizOptionSelected",
                    "QuizQuestionSubmitted",
                    "QuizCompleted",
                    "QuizResultViewed",
                    "QuizRecommendationViewed",
                    "QuizCtaViewed",
                ]
                if start_artifact_kind == "quiz"
                else []
            )
            start_manifest = (
                {
                    "quizOptions": [{"id": "a", "selector": "#quiz-option", "questionIndex": 1}],
                }
                if start_artifact_kind == "quiz"
                else {}
            )
            validation_plan = {
                "render_mode": "html_deploy",
                "origin": origin,
                "candidate_release_id": RELEASE_ID,
                "checkout_validated": True,
                "pages_to_validate": [
                    {
                        "url": start_url,
                        "tracking": tracking,
                        "stage": "pre_sales",
                        "slug": start_slug,
                        "page_id": start_page_id,
                        "html_artifact_kind": start_artifact_kind,
                    },
                    {
                        "url": sales_url,
                        "tracking": tracking,
                        "stage": "sales",
                        "slug": SALES_SLUG,
                        "page_id": SALES_PAGE_ID,
                        "html_artifact_kind": "sales",
                    },
                ],
                "path_plans": [
                    {
                        "candidate_release_id": RELEASE_ID,
                        "start_page": {
                            "url": start_url,
                            "stage": "pre_sales",
                            "slug": start_slug,
                            "page_id": start_page_id,
                            "html_artifact_kind": start_artifact_kind,
                            "manifest": start_manifest,
                        },
                        "sales_page": {
                            "url": sales_url,
                            "stage": "sales",
                            "slug": SALES_SLUG,
                            "product_slug": PRODUCT_SLUG,
                            "funnel_slug": FUNNEL_SLUG,
                            "publication_id": "publication-local",
                            "page_id": "page-sales",
                        },
                        "pre_sales_click_selectors": ["#to-sales"],
                        "checkout_targets": [
                            {
                                "selector": "#checkout-btn",
                                "mode": "public_checkout",
                                "external_urls": [],
                            }
                        ],
                        "tracking": tracking,
                        "expected_internal_events": [
                            "pre_sales_page_view",
                            "presell_page_view",
                            *quiz_internal_events,
                            "pre_sales_to_sales_click",
                            "sales_page_view",
                            "offer_page_view",
                            "sales_to_checkout_click",
                        ],
                        "expected_meta_events": [
                            "PageView",
                            "EnteredPresales",
                            "Entered Presales Page",
                            "PreSalesToSalesClick",
                            "PageView",
                            "Entered Sales Page",
                            "EnteredSales",
                            "ViewContent",
                            "AddToCart",
                            "SalesToCheckoutClick",
                            "SalesToCheckoutClicked",
                        ],
                        "expected_posthog_events": [
                            "pre_sales_page_view",
                            "PageView",
                            "presell_page_view",
                            "EnteredPresales",
                            "Entered Presales Page",
                            *quiz_posthog_events,
                            "pre_sales_to_sales_click",
                            "cta_click",
                            "PreSalesToSalesClick",
                            "sales_page_view",
                            "PageView",
                            "Entered Sales Page",
                            "EnteredSales",
                            "ViewContent",
                            "offer_page_view",
                            "sales_to_checkout_click",
                            "AddToCart",
                            "SalesToCheckoutClick",
                            "SalesToCheckoutClicked",
                        ],
                        "required_posthog_readback_events": [],
                        "require_meta_pixel_network_validation": False,
                    }
                ],
            }
            result = deploy_service._run_funnel_tracking_post_deploy_validation_sync(
                validation_plan=validation_plan
            )
            optimization = deploy_service._run_html_deploy_optimization_validation_sync(
                validation_plan=validation_plan
            )
            lighthouse = deploy_service._run_html_deploy_lighthouse_validation_sync(
                validation_plan=validation_plan
            )
            print(
                json.dumps(
                    {
                        "origin": origin,
                        "result": result,
                        "optimization": optimization,
                        "lighthouse": lighthouse,
                    },
                    indent=2,
                )
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
