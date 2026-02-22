from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.config import settings


class NamecheapDnsError(RuntimeError):
    """Raised when Namecheap DNS operations fail."""


# Common multi-part public suffixes for Namecheap domains.
# For unknown suffixes, parsing falls back to last-two-label split.
_MULTI_PART_TLDS = {
    "ac.uk",
    "co.jp",
    "co.nz",
    "co.uk",
    "com.au",
    "com.br",
    "com.mx",
    "gov.uk",
    "net.au",
    "org.au",
    "org.uk",
}

_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _iter_children_by_name(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first_child_by_name(element: ET.Element, name: str) -> ET.Element | None:
    children = _iter_children_by_name(element, name)
    return children[0] if children else None


def _read_required_setting(name: str) -> str:
    raw = getattr(settings, name, None)
    value = str(raw or "").strip()
    if not value:
        raise NamecheapDnsError(f"Namecheap DNS provisioning requires {name}.")
    return value


def _split_hostname_for_namecheap(hostname: str) -> tuple[str, str, str, str]:
    value = (hostname or "").strip().lower()
    if not value:
        raise NamecheapDnsError("Hostname is required for Namecheap DNS provisioning.")
    if "://" in value or "/" in value or "?" in value or "#" in value:
        raise NamecheapDnsError(
            f"Hostname '{hostname}' is invalid. Use a bare domain (for example: shop.example.com)."
        )

    labels = value.split(".")
    if len(labels) < 2:
        raise NamecheapDnsError(
            f"Hostname '{hostname}' is invalid. Expected a fully-qualified domain."
        )
    for label in labels:
        if not _LABEL_RE.match(label):
            raise NamecheapDnsError(f"Hostname '{hostname}' contains an invalid label '{label}'.")

    sld: str
    tld: str
    host_labels: list[str]

    if len(labels) >= 3 and ".".join(labels[-2:]) in _MULTI_PART_TLDS:
        sld = labels[-3]
        tld = ".".join(labels[-2:])
        host_labels = labels[:-3]
    else:
        sld = labels[-2]
        tld = labels[-1]
        host_labels = labels[:-2]

    host = ".".join(host_labels) if host_labels else "@"
    apex_domain = f"{sld}.{tld}"
    return sld, tld, host, apex_domain


def _normalize_cname_target(target_hostname: str) -> str:
    value = (target_hostname or "").strip().lower().rstrip(".")
    if not value:
        raise NamecheapDnsError("Bunny DNS target hostname is required for Namecheap CNAME provisioning.")
    if "://" in value or "/" in value or "?" in value or "#" in value:
        raise NamecheapDnsError(
            f"Bunny DNS target hostname '{target_hostname}' must be a hostname, not a URL."
        )
    labels = value.split(".")
    if len(labels) < 2:
        raise NamecheapDnsError(
            f"Bunny DNS target hostname '{target_hostname}' is invalid."
        )
    for label in labels:
        if not _LABEL_RE.match(label):
            raise NamecheapDnsError(
                f"Bunny DNS target hostname '{target_hostname}' contains an invalid label '{label}'."
            )
    return value


def _namecheap_request(*, command: str, params: dict[str, str]) -> ET.Element:
    api_user = _read_required_setting("NAMECHEAP_API_USER")
    api_key = _read_required_setting("NAMECHEAP_API_KEY")
    username = _read_required_setting("NAMECHEAP_USERNAME")
    client_ip = _read_required_setting("NAMECHEAP_CLIENT_IP")
    base_url = _read_required_setting("NAMECHEAP_API_BASE_URL")

    request_params = {
        "ApiUser": api_user,
        "ApiKey": api_key,
        "UserName": username,
        "ClientIp": client_ip,
        "Command": command,
        **params,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(base_url, data=request_params)
    except httpx.HTTPError as exc:
        raise NamecheapDnsError(f"Namecheap API request failed ({command}): {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip() or "<empty response body>"
        raise NamecheapDnsError(
            f"Namecheap API request failed ({command}) with status {response.status_code}: {detail}"
        )

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        raise NamecheapDnsError(
            f"Namecheap API request returned invalid XML ({command})."
        ) from exc

    if _local_name(root.tag) != "ApiResponse":
        raise NamecheapDnsError(
            f"Namecheap API response root is invalid for command '{command}'."
        )

    status = str(root.attrib.get("Status") or "").strip().upper()
    if status != "OK":
        errors = _first_child_by_name(root, "Errors")
        messages: list[str] = []
        if errors is not None:
            for item in _iter_children_by_name(errors, "Error"):
                text = (item.text or "").strip()
                if text:
                    messages.append(text)
        detail = "; ".join(messages) if messages else response.text.strip() or "Unknown Namecheap API error."
        raise NamecheapDnsError(
            f"Namecheap API request failed ({command}): {detail}"
        )

    return root


def _extract_get_hosts_result(*, root: ET.Element) -> ET.Element:
    command_response = _first_child_by_name(root, "CommandResponse")
    if command_response is None:
        raise NamecheapDnsError("Namecheap getHosts response is missing CommandResponse.")

    result = _first_child_by_name(command_response, "DomainDNSGetHostsResult")
    if result is None:
        raise NamecheapDnsError("Namecheap getHosts response is missing DomainDNSGetHostsResult.")

    is_using_our_dns = str(result.attrib.get("IsUsingOurDNS") or "").strip().lower()
    if is_using_our_dns not in {"true", "yes", "1"}:
        raise NamecheapDnsError(
            "Namecheap domain is not using Namecheap BasicDNS/PremiumDNS. "
            "Switch the domain DNS provider to Namecheap before provisioning records."
        )
    return result


def _extract_set_hosts_result(*, root: ET.Element) -> ET.Element:
    command_response = _first_child_by_name(root, "CommandResponse")
    if command_response is None:
        raise NamecheapDnsError("Namecheap setHosts response is missing CommandResponse.")

    result = _first_child_by_name(command_response, "DomainDNSSetHostsResult")
    if result is None:
        raise NamecheapDnsError("Namecheap setHosts response is missing DomainDNSSetHostsResult.")

    updated = str(result.attrib.get("IsSuccess") or "").strip().lower()
    if updated not in {"true", "yes", "1"}:
        raise NamecheapDnsError("Namecheap setHosts reported failure.")
    return result


def _parse_host_records(*, get_hosts_result: ET.Element) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for host in _iter_children_by_name(get_hosts_result, "host"):
        name = str(host.attrib.get("Name") or "").strip()
        record_type = str(host.attrib.get("Type") or "").strip().upper()
        address = str(host.attrib.get("Address") or "").strip()
        if not name or not record_type or not address:
            raise NamecheapDnsError(
                "Namecheap getHosts returned an invalid record (missing Name/Type/Address)."
            )
        record: dict[str, str] = {
            "Name": name,
            "Type": record_type,
            "Address": address,
        }
        ttl = str(host.attrib.get("TTL") or "").strip()
        if ttl:
            record["TTL"] = ttl
        mx_pref = str(host.attrib.get("MXPref") or "").strip()
        if mx_pref:
            record["MXPref"] = mx_pref
        records.append(record)
    return records


def _set_hosts(*, sld: str, tld: str, records: list[dict[str, str]]) -> None:
    if not records:
        raise NamecheapDnsError("Namecheap setHosts requires at least one DNS record.")

    params: dict[str, str] = {
        "SLD": sld,
        "TLD": tld,
    }
    for idx, record in enumerate(records, start=1):
        name = str(record.get("Name") or "").strip()
        record_type = str(record.get("Type") or "").strip().upper()
        address = str(record.get("Address") or "").strip()
        if not name or not record_type or not address:
            raise NamecheapDnsError(
                f"Invalid DNS record at index {idx}: Name/Type/Address are required."
            )
        params[f"HostName{idx}"] = name
        params[f"RecordType{idx}"] = record_type
        params[f"Address{idx}"] = address

        ttl = str(record.get("TTL") or "").strip()
        if ttl:
            params[f"TTL{idx}"] = ttl
        mx_pref = str(record.get("MXPref") or "").strip()
        if mx_pref:
            params[f"MXPref{idx}"] = mx_pref

    root = _namecheap_request(command="namecheap.domains.dns.setHosts", params=params)
    _extract_set_hosts_result(root=root)


def upsert_cname_record(*, hostname: str, target_hostname: str) -> dict[str, Any]:
    sld, tld, host, apex_domain = _split_hostname_for_namecheap(hostname)
    normalized_target = _normalize_cname_target(target_hostname)

    get_root = _namecheap_request(
        command="namecheap.domains.dns.getHosts",
        params={
            "SLD": sld,
            "TLD": tld,
        },
    )
    get_result = _extract_get_hosts_result(root=get_root)
    existing_records = _parse_host_records(get_hosts_result=get_result)

    conflicts = [
        record
        for record in existing_records
        if str(record.get("Name") or "").strip().lower() == host.lower()
        and str(record.get("Type") or "").strip().upper() != "CNAME"
    ]
    if conflicts:
        conflict_types = sorted({str(item.get("Type") or "").upper() for item in conflicts})
        host_label = apex_domain if host == "@" else f"{host}.{apex_domain}"
        raise NamecheapDnsError(
            f"Cannot provision CNAME for '{host_label}' because non-CNAME records already exist "
            f"for that host ({', '.join(conflict_types)})."
        )

    retained_records = [
        record
        for record in existing_records
        if str(record.get("Name") or "").strip().lower() != host.lower()
    ]
    retained_records.append(
        {
            "Name": host,
            "Type": "CNAME",
            "Address": normalized_target,
            "TTL": "300",
        }
    )

    _set_hosts(sld=sld, tld=tld, records=retained_records)

    return {
        "provider": "namecheap",
        "recordType": "CNAME",
        "host": host,
        "domain": apex_domain,
        "fqdn": apex_domain if host == "@" else f"{host}.{apex_domain}",
        "target": normalized_target,
    }
