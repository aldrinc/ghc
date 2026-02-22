import xml.etree.ElementTree as ET

import pytest

from app.services import namecheap_dns


def _build_get_hosts_response(*, host_entries: list[dict[str, str]], is_using_our_dns: str = "true") -> ET.Element:
    hosts_xml = "".join(
        f'<host Name="{entry["Name"]}" Type="{entry["Type"]}" Address="{entry["Address"]}" TTL="{entry.get("TTL", "1800")}" />'
        for entry in host_entries
    )
    xml = (
        "<ApiResponse Status=\"OK\">"
        "<CommandResponse Type=\"namecheap.domains.dns.getHosts\">"
        f"<DomainDNSGetHostsResult Domain=\"example.com\" IsUsingOurDNS=\"{is_using_our_dns}\">"
        f"{hosts_xml}"
        "</DomainDNSGetHostsResult>"
        "</CommandResponse>"
        "</ApiResponse>"
    )
    return ET.fromstring(xml)


def test_split_hostname_for_namecheap_supports_apex_and_subdomain():
    sld, tld, host, apex = namecheap_dns._split_hostname_for_namecheap("shop.example.com")
    assert sld == "example"
    assert tld == "com"
    assert host == "shop"
    assert apex == "example.com"

    sld2, tld2, host2, apex2 = namecheap_dns._split_hostname_for_namecheap("example.com")
    assert sld2 == "example"
    assert tld2 == "com"
    assert host2 == "@"
    assert apex2 == "example.com"


def test_split_hostname_for_namecheap_supports_common_multi_part_tld():
    sld, tld, host, apex = namecheap_dns._split_hostname_for_namecheap("shop.example.co.uk")
    assert sld == "example"
    assert tld == "co.uk"
    assert host == "shop"
    assert apex == "example.co.uk"


def test_upsert_cname_record_merges_records_and_replaces_existing_cname(monkeypatch):
    monkeypatch.setattr(
        namecheap_dns,
        "_namecheap_request",
        lambda *, command, params: _build_get_hosts_response(
            host_entries=[
                {"Name": "@", "Type": "A", "Address": "198.51.100.10"},
                {"Name": "shop", "Type": "CNAME", "Address": "old-target.b-cdn.net"},
            ]
        ),
    )

    captured: dict[str, object] = {}

    def _fake_set_hosts(*, sld: str, tld: str, records: list[dict[str, str]]) -> None:
        captured["sld"] = sld
        captured["tld"] = tld
        captured["records"] = records

    monkeypatch.setattr(namecheap_dns, "_set_hosts", _fake_set_hosts)

    result = namecheap_dns.upsert_cname_record(
        hostname="shop.example.com",
        target_hostname="workspace-123.b-cdn.net",
    )

    assert result == {
        "provider": "namecheap",
        "recordType": "CNAME",
        "host": "shop",
        "domain": "example.com",
        "fqdn": "shop.example.com",
        "target": "workspace-123.b-cdn.net",
    }
    assert captured["sld"] == "example"
    assert captured["tld"] == "com"
    assert captured["records"] == [
        {"Name": "@", "Type": "A", "Address": "198.51.100.10", "TTL": "1800"},
        {"Name": "shop", "Type": "CNAME", "Address": "workspace-123.b-cdn.net", "TTL": "300"},
    ]


def test_upsert_cname_record_errors_when_non_cname_conflict_exists(monkeypatch):
    monkeypatch.setattr(
        namecheap_dns,
        "_namecheap_request",
        lambda *, command, params: _build_get_hosts_response(
            host_entries=[
                {"Name": "shop", "Type": "A", "Address": "198.51.100.10"},
            ]
        ),
    )

    def _unexpected_set_hosts(*, sld: str, tld: str, records: list[dict[str, str]]) -> None:
        raise AssertionError("setHosts should not run when host has non-CNAME conflicts")

    monkeypatch.setattr(namecheap_dns, "_set_hosts", _unexpected_set_hosts)

    with pytest.raises(namecheap_dns.NamecheapDnsError, match="Cannot provision CNAME"):
        namecheap_dns.upsert_cname_record(
            hostname="shop.example.com",
            target_hostname="workspace-123.b-cdn.net",
        )


def test_extract_get_hosts_result_requires_namecheap_dns_enabled():
    root = _build_get_hosts_response(host_entries=[], is_using_our_dns="false")
    with pytest.raises(namecheap_dns.NamecheapDnsError, match="not using Namecheap"):
        namecheap_dns._extract_get_hosts_result(root=root)
