from __future__ import annotations

from enum import Enum
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class NodeType(str, Enum):
    COMPUTE_INSTANCE = "ComputeInstance"
    LOAD_BALANCER = "LoadBalancer"
    NETWORK = "Network"
    SUBNET = "Subnet"
    FIREWALL = "Firewall"
    VOLUME = "Volume"
    IP_ADDRESS = "IpAddress"
    DNS_RECORD = "DnsRecord"


class EdgeType(str, Enum):
    ATTACHED_TO = "attached_to"
    IN_NETWORK = "in_network"
    PROTECTED_BY = "protected_by"
    TARGETS = "targets"
    RESOLVES_TO = "resolves_to"


class Node(BaseModel):
    id: str
    type: NodeType
    name: Optional[str] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    provider: Optional[str] = None
    provider_native_id: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    attrs: Dict[str, str] = Field(default_factory=dict)


class Edge(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    type: EdgeType

    class Config:
        populate_by_name = True


class CloudGraph(BaseModel):
    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)


class RuntimeType(str, Enum):
    DOCKER = "docker"
    NODEJS = "nodejs"
    PYTHON = "python"
    STATIC = "static"
    GO = "go"


class ApplicationSourceType(str, Enum):
    GIT = "git"
    FUNNEL_PUBLICATION = "funnel_publication"
    FUNNEL_ARTIFACT = "funnel_artifact"


class FunnelPublicationSourceSpec(BaseModel):
    public_id: str
    upstream_base_url: str
    upstream_api_base_url: str


class FunnelArtifactSourceSpec(BaseModel):
    product_id: str
    upstream_api_base_root: str
    runtime_dist_path: str = "mos/frontend/dist"
    artifact: Dict[str, Any]


class ServiceSpec(BaseModel):
    """How to run the app in the background."""

    command: Optional[str] = None
    environment: Dict[str, str] = Field(default_factory=dict)
    environment_file: Optional[str] = None
    environment_file_upload: Optional[str] = None
    ports: List[int] = Field(default_factory=list)
    server_names: List[str] = Field(default_factory=list)
    https: bool = False


class BuildSpec(BaseModel):
    """How to build the app from source."""

    install_command: Optional[str] = None
    build_command: Optional[str] = None
    system_packages: List[str] = Field(default_factory=list)


class ApplicationSpec(BaseModel):
    name: str
    source_type: ApplicationSourceType = ApplicationSourceType.GIT
    source_ref: Optional[FunnelPublicationSourceSpec | FunnelArtifactSourceSpec] = None
    repo_url: Optional[str] = None
    branch: str = "main"
    runtime: RuntimeType
    build_config: BuildSpec
    service_config: ServiceSpec
    destination_path: str = "/opt/apps"

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_funnel_artifact_source_ref(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        source_type = str(value.get("source_type") or "").strip().lower()
        if source_type != ApplicationSourceType.FUNNEL_ARTIFACT.value:
            return value

        source_ref = value.get("source_ref")
        if not isinstance(source_ref, dict):
            return value

        normalized = dict(source_ref)

        legacy_api_base = normalized.get("upstream_api_base_url")
        if (
            "upstream_api_base_root" not in normalized
            and isinstance(legacy_api_base, str)
            and legacy_api_base.strip()
        ):
            normalized["upstream_api_base_root"] = legacy_api_base.strip()

        if "artifact" not in normalized:
            legacy_meta = normalized.get("meta")
            legacy_funnels = normalized.get("funnels")
            if isinstance(legacy_meta, dict) and isinstance(legacy_funnels, dict):
                normalized["artifact"] = {
                    "meta": legacy_meta,
                    "funnels": legacy_funnels,
                }

        product_id = normalized.get("product_id")
        if not isinstance(product_id, str) or not product_id.strip():
            inferred_product_id: Optional[str] = None

            artifact = normalized.get("artifact")
            if isinstance(artifact, dict):
                meta = artifact.get("meta")
                if isinstance(meta, dict):
                    meta_product_id = meta.get("productId") or meta.get("product_id")
                    if isinstance(meta_product_id, str) and meta_product_id.strip():
                        inferred_product_id = meta_product_id.strip()

            if not inferred_product_id:
                workload_name = str(value.get("name") or "").strip()
                match = re.match(r"^product-funnels-([0-9a-fA-F-]{36})$", workload_name)
                if match:
                    candidate = match.group(1)
                    try:
                        inferred_product_id = str(UUID(candidate))
                    except ValueError:
                        inferred_product_id = None

            if inferred_product_id:
                normalized["product_id"] = inferred_product_id

        out = dict(value)
        out["source_ref"] = normalized
        return out

    @model_validator(mode="after")
    def validate_source(self) -> "ApplicationSpec":
        if self.source_type == ApplicationSourceType.GIT:
            repo_url = (self.repo_url or "").strip()
            if not repo_url:
                raise ValueError("repo_url is required when source_type='git'.")
            command = (self.service_config.command or "").strip()
            if not command:
                raise ValueError("service_config.command is required when source_type='git'.")
            if self.source_ref is not None:
                raise ValueError("source_ref is not allowed when source_type='git'.")
            self.repo_url = repo_url
            self.service_config.command = command
            return self

        if self.source_type == ApplicationSourceType.FUNNEL_PUBLICATION:
            if self.repo_url is not None:
                raise ValueError("repo_url is not allowed when source_type='funnel_publication'.")
            if self.source_ref is None:
                raise ValueError("source_ref is required when source_type='funnel_publication'.")
            if not isinstance(self.source_ref, FunnelPublicationSourceSpec):
                raise ValueError("source_ref must be FunnelPublicationSourceSpec when source_type='funnel_publication'.")
            self.source_ref.public_id = self.source_ref.public_id.strip()
            self.source_ref.upstream_base_url = self.source_ref.upstream_base_url.strip().rstrip("/")
            self.source_ref.upstream_api_base_url = self.source_ref.upstream_api_base_url.strip().rstrip("/")
            if not self.source_ref.public_id:
                raise ValueError("source_ref.public_id must be non-empty for source_type='funnel_publication'.")
            if not self.source_ref.upstream_base_url.startswith(("http://", "https://")):
                raise ValueError("source_ref.upstream_base_url must start with http:// or https://.")
            if not self.source_ref.upstream_api_base_url.startswith(("http://", "https://")):
                raise ValueError("source_ref.upstream_api_base_url must start with http:// or https://.")
            return self

        if self.source_type == ApplicationSourceType.FUNNEL_ARTIFACT:
            if self.repo_url is not None:
                raise ValueError("repo_url is not allowed when source_type='funnel_artifact'.")
            if self.source_ref is None:
                raise ValueError("source_ref is required when source_type='funnel_artifact'.")
            if not isinstance(self.source_ref, FunnelArtifactSourceSpec):
                raise ValueError("source_ref must be FunnelArtifactSourceSpec when source_type='funnel_artifact'.")
            self.source_ref.product_id = self.source_ref.product_id.strip()
            self.source_ref.upstream_api_base_root = self.source_ref.upstream_api_base_root.strip().rstrip("/")
            self.source_ref.runtime_dist_path = self.source_ref.runtime_dist_path.strip()
            if not self.source_ref.product_id:
                raise ValueError("source_ref.product_id must be non-empty for source_type='funnel_artifact'.")
            if not self.source_ref.upstream_api_base_root.startswith(("http://", "https://")):
                raise ValueError("source_ref.upstream_api_base_root must start with http:// or https://.")
            if not self.source_ref.runtime_dist_path:
                raise ValueError("source_ref.runtime_dist_path must be non-empty for source_type='funnel_artifact'.")
            if not isinstance(self.source_ref.artifact, dict):
                raise ValueError("source_ref.artifact must be an object for source_type='funnel_artifact'.")
            if not isinstance(self.source_ref.artifact.get("meta"), dict):
                raise ValueError("source_ref.artifact.meta must be an object for source_type='funnel_artifact'.")
            if not isinstance(self.source_ref.artifact.get("funnels"), dict):
                raise ValueError("source_ref.artifact.funnels must be an object for source_type='funnel_artifact'.")
            return self

        raise ValueError(f"Unsupported source_type: {self.source_type}")


class NetworkSpec(BaseModel):
    name: str
    cidr: str


class UnattendedUpgradesPolicy(BaseModel):
    enabled: bool = True
    allowed_origins: List[str] = Field(
        default_factory=lambda: [
            "${distro_id}:${distro_codename}-security",
            "${distro_id}ESMApps:${distro_codename}-apps-security",
            "${distro_id}ESM:${distro_codename}-infra-security",
        ]
    )
    auto_reboot: bool = False
    auto_reboot_time: str = "04:00"


class MaintenancePolicy(BaseModel):
    unattended_upgrades: UnattendedUpgradesPolicy = Field(default_factory=UnattendedUpgradesPolicy)


class InstanceSpec(BaseModel):
    name: str
    size: str
    network: str
    region: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    workloads: List[ApplicationSpec] = Field(default_factory=list)
    maintenance: Optional[MaintenancePolicy] = None


class LoadBalancerPortSpec(BaseModel):
    port: int
    protocol: str


class LoadBalancerTargetSpec(BaseModel):
    type: str
    selector: str


class LoadBalancerSpec(BaseModel):
    name: str
    network: str
    ports: List[LoadBalancerPortSpec] = Field(default_factory=list)
    targets: List[LoadBalancerTargetSpec] = Field(default_factory=list)


class FirewallRuleSpec(BaseModel):
    direction: str
    protocol: str
    port: Optional[str] = None
    cidr: Optional[str] = None


class FirewallTargetSpec(BaseModel):
    type: str
    selector: str


class FirewallSpec(BaseModel):
    name: str
    rules: List[FirewallRuleSpec] = Field(default_factory=list)
    targets: List[FirewallTargetSpec] = Field(default_factory=list)


class DnsRecordSpec(BaseModel):
    zone: str
    name: str
    type: str
    target: str


class ContainerPortSpec(BaseModel):
    container_port: int
    host_port: Optional[int] = None


class ContainerVolumeSpec(BaseModel):
    host_path: str
    container_path: str


class ContainerEnvVar(BaseModel):
    name: str
    value: str


class ContainerSpec(BaseModel):
    name: str
    image: str
    host_selector: str
    ports: List[ContainerPortSpec] = Field(default_factory=list)
    env: List[ContainerEnvVar] = Field(default_factory=list)
    volumes: List[ContainerVolumeSpec] = Field(default_factory=list)
    restart_policy: str = "always"


class DesiredStateSpec(BaseModel):
    provider: str
    region: Optional[str] = None
    networks: List[NetworkSpec] = Field(default_factory=list)
    instances: List[InstanceSpec] = Field(default_factory=list)
    load_balancers: List[LoadBalancerSpec] = Field(default_factory=list)
    firewalls: List[FirewallSpec] = Field(default_factory=list)
    dns_records: List[DnsRecordSpec] = Field(default_factory=list)
    containers: List[ContainerSpec] = Field(default_factory=list)
