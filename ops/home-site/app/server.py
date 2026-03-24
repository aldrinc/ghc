#!/usr/bin/env python3
from __future__ import annotations

import html
import os
import sqlite3
import sys
import urllib.parse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from typing import Final


BRAND_NAME: Final = "mOS"
OPERATOR_NAME: Final = "Moshq"
SUPPORT_EMAIL: Final = "support@moshq.app"
BUSINESS_ADDRESS_LINES: Final = (
    "8 The Green, STE A<br/>"
    "Dover, DE 19901<br/>"
    "United States"
)
EFFECTIVE_DATE: Final = "March 19, 2026"
REQUEST_TYPES: Final = {
    "delete": "Delete my data",
    "access": "Request access to my data",
    "correction": "Correct my data",
    "support": "General privacy or support request",
}

DEFAULT_APP_ROOT = Path(__file__).resolve().parent
APP_ROOT = Path(os.getenv("HOME_SITE_ROOT", str(DEFAULT_APP_ROOT)))
DATA_DIR = Path(os.getenv("HOME_SITE_DATA_DIR", str(APP_ROOT / "data")))
DB_PATH = Path(os.getenv("HOME_SITE_DB_PATH", str(DATA_DIR / "requests.sqlite3")))
STATIC_CSS_PATH = APP_ROOT / "site.css"
HOST = os.getenv("HOME_SITE_BIND", "127.0.0.1")
PORT = int(os.getenv("HOME_SITE_PORT", "8015"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deletion_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                confirmation_code TEXT NOT NULL UNIQUE,
                request_type TEXT NOT NULL,
                requester_name TEXT NOT NULL,
                requester_email TEXT,
                account_reference TEXT NOT NULL,
                details TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def fetch_request(confirmation_code: str) -> sqlite3.Row | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT confirmation_code, request_type, requester_name, requester_email,
                   account_reference, details, status, created_at, updated_at
            FROM deletion_requests
            WHERE confirmation_code = ?
            """,
            (confirmation_code,),
        ).fetchone()


def create_request(
    *,
    request_type: str,
    requester_name: str,
    requester_email: str | None,
    account_reference: str,
    details: str | None,
) -> str:
    code = token_urlsafe(9).replace("-", "").replace("_", "")[:12].upper()
    now = utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO deletion_requests (
                confirmation_code,
                request_type,
                requester_name,
                requester_email,
                account_reference,
                details,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'received', ?, ?)
            """,
            (
                code,
                request_type,
                requester_name,
                requester_email,
                account_reference,
                details,
                now,
                now,
            ),
        )
        conn.commit()
    return code


def safe(value: str | None) -> str:
    return html.escape(value or "", quote=True)


@dataclass(frozen=True)
class NavItem:
    href: str
    label: str


NAV_ITEMS: Final = (
    NavItem("/privacy", "Privacy"),
    NavItem("/terms", "Terms"),
    NavItem("/data", "Data Requests"),
)


class HomeSiteHandler(BaseHTTPRequestHandler):
    server_version = "HomeSiteHTTP/1.0"

    def do_GET(self) -> None:  # noqa: N802
        self.handle_read_request(include_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self.handle_read_request(include_body=False)

    def handle_read_request(self, *, include_body: bool) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self.redirect("/privacy")
            return
        if path == "/health":
            self.respond_text(
                "ok",
                status=HTTPStatus.OK,
                content_type="text/plain; charset=utf-8",
                include_body=include_body,
            )
            return
        if path == "/static/site.css":
            self.respond_file(STATIC_CSS_PATH, "text/css; charset=utf-8", include_body=include_body)
            return
        if path == "/privacy":
            self.respond_html(self.page_privacy(), include_body=include_body)
            return
        if path == "/terms":
            self.respond_html(self.page_terms(), include_body=include_body)
            return
        if path == "/data":
            code = (query.get("code") or [""])[0].strip()
            if code:
                row = fetch_request(code)
                self.respond_html(self.page_data(row=row, submitted_code=code), include_body=include_body)
                return
            self.respond_html(self.page_data(), include_body=include_body)
            return

        self.respond_html(self.page_not_found(), status=HTTPStatus.NOT_FOUND, include_body=include_body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/data/request":
            self.respond_html(self.page_not_found(), status=HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        fields = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)

        request_type = (fields.get("request_type") or ["delete"])[0].strip().lower()
        requester_name = (fields.get("requester_name") or [""])[0].strip()
        requester_email = (fields.get("requester_email") or [""])[0].strip()
        account_reference = (fields.get("account_reference") or [""])[0].strip()
        details = (fields.get("details") or [""])[0].strip()

        errors: list[str] = []
        if request_type not in REQUEST_TYPES:
            errors.append("Choose a valid request type.")
        if not requester_name:
            errors.append("Your name is required.")
        if not account_reference:
            errors.append("Provide at least one account, workspace, or Meta identifier so we can locate the data.")

        if errors:
            self.respond_html(
                self.page_data(
                    errors=errors,
                    form_values={
                        "request_type": request_type,
                        "requester_name": requester_name,
                        "requester_email": requester_email,
                        "account_reference": account_reference,
                        "details": details,
                    },
                ),
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        confirmation_code = create_request(
            request_type=request_type,
            requester_name=requester_name,
            requester_email=requester_email or None,
            account_reference=account_reference,
            details=details or None,
        )
        self.redirect(f"/data?code={urllib.parse.quote(confirmation_code)}", status=HTTPStatus.SEE_OTHER)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), format % args)
        )

    def page_privacy(self) -> str:
        content = f"""
        <section class="hero">
          <p class="eyebrow">Public Policy Page</p>
          <h1>Privacy Policy</h1>
          <p class="lead">
            This Privacy Policy applies to <strong>{safe(BRAND_NAME)}</strong>, the legal
            information site available at <strong>home.moshq.app</strong>, and the related
            Meta ad account integration workflows operated by <strong>{safe(OPERATOR_NAME)}</strong>.
          </p>
          <p class="meta">Effective date: {safe(EFFECTIVE_DATE)}</p>
        </section>

        <section>
          <h2>Who This Policy Covers</h2>
          <p>
            This policy is intended for people who use or interact with the Meta integration
            features provided through the mOS platform, including authorized business users who
            connect Meta ad accounts, Pages, Instagram actors, pixels, data sets, verified domains,
            and related campaign configuration data.
          </p>
        </section>

        <section>
          <h2>Data We Process</h2>
          <ul class="checklist">
            <li>Connection and account metadata such as ad account IDs and names, business manager IDs and names, Page IDs and names, Instagram actor IDs, pixel IDs, data set IDs, verified domains, and configuration status information.</li>
            <li>Credentials and secrets submitted by authorized users to operate a requested Meta connection, including access tokens. Where stored by the app, those credentials are stored in encrypted form.</li>
            <li>Creative, publishing, and operational data such as campaign names, creative text, destination URLs, asset references, upload identifiers, and publish or validation logs.</li>
            <li>Support and privacy-request information submitted through this site, including your name, optional email address, identifiers you provide, and request details.</li>
            <li>Technical information created as part of operating the site and service, such as timestamps, request logs, and basic security records.</li>
          </ul>
        </section>

        <section>
          <h2>How We Use Data</h2>
          <ul class="checklist">
            <li>To configure, validate, and operate Meta ad account integrations requested by authorized users.</li>
            <li>To create, publish, review, or manage campaign, creative, and tracking configurations.</li>
            <li>To troubleshoot issues, maintain service security, and keep audit records tied to integration changes.</li>
            <li>To respond to deletion, access, correction, or support requests submitted by users.</li>
            <li>To comply with applicable law, Meta Platform Terms, and Meta Developer Policies.</li>
          </ul>
        </section>

        <section>
          <h2>How Data May Be Shared</h2>
          <p>
            We may share data with Meta and its Graph API only to the extent required to operate
            the integration you requested. We may also share data with infrastructure and service
            providers that help us host or secure the service, and where required by law or to
            protect the rights, safety, or integrity of the service and its users.
          </p>
          <p>
            We do not sell Meta Platform Data.
          </p>
        </section>

        <section>
          <h2>Retention</h2>
          <p>
            We retain integration data for as long as it is reasonably necessary to operate the
            requested service, keep required security or audit records, resolve disputes, or comply
            with law. When a connection, workspace, or applicable account is removed, or when a
            valid deletion request is received, we will review and delete relevant data as soon as
            reasonably possible unless a longer retention period is legally required.
          </p>
        </section>

        <section>
          <h2>Your Choices and Deletion Rights</h2>
          <p>
            You can request access to, correction of, or deletion of data associated with the app
            by using the <a href="/data">Data Requests</a> page or by emailing
            <a href="mailto:{safe(SUPPORT_EMAIL)}">{safe(SUPPORT_EMAIL)}</a>.
          </p>
          <p>
            If the request relates to a Meta app removal flow, you can also remove the app from
            Facebook's Apps and Websites settings and then use the request process on this site to
            give us the identifiers we need to locate the relevant data.
          </p>
        </section>

        <section>
          <h2>Security</h2>
          <p>
            We use administrative and technical controls designed to limit access to integration
            data and request records. No internet-connected service can be guaranteed perfectly
            secure, but we take reasonable steps to protect the data we process.
          </p>
        </section>

        <section>
          <h2>Updates</h2>
          <p>
            We may update this policy from time to time. When we do, we will update the effective
            date on this page and publish the revised version at the same URL.
          </p>
        </section>

        <section>
          <h2>Contact</h2>
          <p>
            Email: <a href="mailto:{safe(SUPPORT_EMAIL)}">{safe(SUPPORT_EMAIL)}</a><br/>
            Mailing address:<br/>{BUSINESS_ADDRESS_LINES}
          </p>
        </section>
        """
        return self.layout(title="Privacy Policy", content=content, active="/privacy")

    def page_terms(self) -> str:
        content = f"""
        <section class="hero">
          <p class="eyebrow">Public Policy Page</p>
          <h1>Terms of Service</h1>
          <p class="lead">
            These Terms govern your use of this site and the related Meta integration features
            published under the <strong>{safe(BRAND_NAME)}</strong> brand.
          </p>
          <p class="meta">Effective date: {safe(EFFECTIVE_DATE)}</p>
        </section>

        <section>
          <h2>Operator</h2>
          <p>
            This site is operated by <strong>{safe(OPERATOR_NAME)}</strong> from:<br/>
            {BUSINESS_ADDRESS_LINES}
          </p>
        </section>

        <section>
          <h2>Service Scope</h2>
          <p>
            The site at <strong>home.moshq.app</strong> publishes legal and privacy information for
            the mOS Meta integration workflows and provides a public way to submit deletion and
            support requests connected to that integration.
          </p>
        </section>

        <section>
          <h2>Authorized Use</h2>
          <ul class="checklist">
            <li>You must provide accurate information when submitting a request.</li>
            <li>You must only submit requests for data you are authorized to access or control.</li>
            <li>You must not misuse this site to send spam, malicious content, or false reports.</li>
          </ul>
        </section>

        <section>
          <h2>Third-Party Platforms</h2>
          <p>
            If you use Meta or related third-party platforms through mOS, your use of those
            platforms is also governed by the applicable third-party terms and policies. These
            Terms do not replace or override Meta's terms.
          </p>
        </section>

        <section>
          <h2>Availability and Changes</h2>
          <p>
            We may update, suspend, or discontinue this site or any related workflow at any time.
            We may also update these Terms by posting a revised version at this URL.
          </p>
        </section>

        <section>
          <h2>Disclaimer</h2>
          <p>
            This site is provided on an “as is” and “as available” basis. To the maximum extent
            permitted by law, we disclaim warranties of merchantability, fitness for a particular
            purpose, and non-infringement.
          </p>
        </section>

        <section>
          <h2>Limitation of Liability</h2>
          <p>
            To the maximum extent permitted by law, {safe(OPERATOR_NAME)} will not be liable for
            indirect, incidental, special, consequential, or punitive damages arising out of or
            related to your use of this site.
          </p>
        </section>

        <section>
          <h2>Privacy</h2>
          <p>
            Your use of this site is also subject to the <a href="/privacy">Privacy Policy</a>.
            If you need to request deletion of data or track a privacy request, use the
            <a href="/data">Data Requests</a> page.
          </p>
        </section>

        <section>
          <h2>Contact</h2>
          <p>
            Email: <a href="mailto:{safe(SUPPORT_EMAIL)}">{safe(SUPPORT_EMAIL)}</a><br/>
            Mailing address:<br/>{BUSINESS_ADDRESS_LINES}
          </p>
        </section>
        """
        return self.layout(title="Terms of Service", content=content, active="/terms")

    def page_data(
        self,
        *,
        errors: list[str] | None = None,
        form_values: dict[str, str] | None = None,
        row: sqlite3.Row | None = None,
        submitted_code: str | None = None,
    ) -> str:
        values = form_values or {}
        selected_type = values.get("request_type") or "delete"
        option_markup = "".join(
            f'<option value="{safe(key)}"{" selected" if key == selected_type else ""}>{safe(label)}</option>'
            for key, label in REQUEST_TYPES.items()
        )
        alert = ""
        if errors:
            items = "".join(f"<li>{safe(message)}</li>" for message in errors)
            alert = f'<div class="alert error"><strong>Fix the following:</strong><ul>{items}</ul></div>'
        if submitted_code and row is None:
            alert = (
                f'<div class="alert error"><strong>Request not found.</strong> '
                f'No request was found for confirmation code <code>{safe(submitted_code)}</code>.</div>'
            )

        status_markup = ""
        if row is not None:
            request_type_label = REQUEST_TYPES.get(str(row["request_type"]), str(row["request_type"]))
            status_markup = f"""
            <section class="status-card">
              <p class="eyebrow">Request Status</p>
              <h2>Confirmation code {safe(str(row["confirmation_code"]))}</h2>
              <div class="status-grid">
                <div>
                  <span class="label">Status</span>
                  <strong>{safe(str(row["status"]).capitalize())}</strong>
                </div>
                <div>
                  <span class="label">Request type</span>
                  <strong>{safe(request_type_label)}</strong>
                </div>
                <div>
                  <span class="label">Submitted</span>
                  <strong>{safe(str(row["created_at"]))}</strong>
                </div>
                <div>
                  <span class="label">Reference</span>
                  <strong>{safe(str(row["account_reference"]))}</strong>
                </div>
              </div>
              <p>
                Your request has been received and logged. If we need more information, we may
                contact you using the email address you submitted, or you can follow up at
                <a href="mailto:{safe(SUPPORT_EMAIL)}">{safe(SUPPORT_EMAIL)}</a> and include your
                confirmation code.
              </p>
            </section>
            """

        content = f"""
        <section class="hero">
          <p class="eyebrow">Public Policy Page</p>
          <h1>User Data Deletion and Support Requests</h1>
          <p class="lead">
            This page provides the public deletion and privacy-request flow for the mOS Meta
            integration. You can use it to request deletion, access, correction, or general support.
          </p>
          <p class="meta">Support email: <a href="mailto:{safe(SUPPORT_EMAIL)}">{safe(SUPPORT_EMAIL)}</a></p>
        </section>

        <section>
          <h2>How to Request Deletion</h2>
          <ol class="steps">
            <li>If your request is tied to a Meta or Facebook app connection, remove the app or disconnect the relevant access in Meta/Facebook settings if applicable.</li>
            <li>Submit the request form below with enough information for us to identify the affected workspace, ad account, Page, Instagram actor, or other related record.</li>
            <li>Keep the confirmation code we generate for you. That code lets you check the status of the request on this page.</li>
          </ol>
        </section>

        {status_markup}
        {alert}

        <section>
          <h2>Submit a Request</h2>
          <form class="request-form" method="post" action="/data/request">
            <label>
              <span>Request type</span>
              <select name="request_type">
                {option_markup}
              </select>
            </label>
            <label>
              <span>Your name</span>
              <input type="text" name="requester_name" value="{safe(values.get('requester_name'))}" required />
            </label>
            <label>
              <span>Email address (optional)</span>
              <input type="email" name="requester_email" value="{safe(values.get('requester_email'))}" />
            </label>
            <label>
              <span>Account or workspace reference</span>
              <input
                type="text"
                name="account_reference"
                value="{safe(values.get('account_reference'))}"
                placeholder="Meta user ID, ad account ID, Page ID, workspace name, or similar"
                required
              />
            </label>
            <label>
              <span>Additional details (optional)</span>
              <textarea name="details" rows="5" placeholder="Add any extra context that will help locate the data.">{safe(values.get('details'))}</textarea>
            </label>
            <button type="submit">Create request</button>
          </form>
        </section>

        <section>
          <h2>Alternative Contact Method</h2>
          <p>
            If you prefer not to use the form, email
            <a href="mailto:{safe(SUPPORT_EMAIL)}">{safe(SUPPORT_EMAIL)}</a> and include the
            relevant Meta or workspace identifiers. Our mailing address is:<br/>{BUSINESS_ADDRESS_LINES}
          </p>
        </section>
        """
        return self.layout(title="User Data Deletion", content=content, active="/data")

    def page_not_found(self) -> str:
        content = """
        <section class="hero">
          <p class="eyebrow">404</p>
          <h1>Page Not Found</h1>
          <p class="lead">The policy page you requested does not exist.</p>
        </section>
        """
        return self.layout(title="Not Found", content=content, active="")

    def layout(self, *, title: str, content: str, active: str) -> str:
        nav_markup = "".join(
            (
                f'<a href="{safe(item.href)}"'
                f' class="nav-link{" active" if item.href == active else ""}">{safe(item.label)}</a>'
            )
            for item in NAV_ITEMS
        )
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe(title)} | {safe(BRAND_NAME)}</title>
    <meta
      name="description"
      content="Public privacy, terms, and data deletion information for the mOS Meta integration."
    />
    <link rel="stylesheet" href="/static/site.css" />
  </head>
  <body>
    <div class="background-grid" aria-hidden="true"></div>
    <header class="site-header">
      <a class="brand" href="/privacy">
        <span class="brand-mark">M</span>
        <span class="brand-copy">
          <strong>{safe(BRAND_NAME)}</strong>
          <small>Meta Integration Policy Center</small>
        </span>
      </a>
      <nav class="site-nav" aria-label="Primary">
        {nav_markup}
      </nav>
    </header>
    <main class="page-shell">
      {content}
    </main>
    <footer class="site-footer">
      <p>
        <strong>{safe(OPERATOR_NAME)}</strong><br/>
        <a href="mailto:{safe(SUPPORT_EMAIL)}">{safe(SUPPORT_EMAIL)}</a><br/>
        {BUSINESS_ADDRESS_LINES}
      </p>
    </footer>
  </body>
</html>
"""

    def redirect(self, location: str, status: HTTPStatus = HTTPStatus.FOUND) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.end_headers()

    def respond_html(
        self,
        content: str,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        include_body: bool = True,
    ) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def respond_text(
        self,
        content: str,
        *,
        status: HTTPStatus,
        content_type: str,
        include_body: bool = True,
    ) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def respond_file(self, path: Path, content_type: str, *, include_body: bool = True) -> None:
        if not path.exists():
            self.respond_html(self.page_not_found(), status=HTTPStatus.NOT_FOUND, include_body=include_body)
            return
        with closing(path.open("rb")) as handle:
            body = handle.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if include_body:
            self.wfile.write(body)


def main() -> None:
    ensure_database()
    server = ThreadingHTTPServer((HOST, PORT), HomeSiteHandler)
    print(f"home-site listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
