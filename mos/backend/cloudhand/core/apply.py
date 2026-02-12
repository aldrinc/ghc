import json
import os
import shutil
import subprocess
import hashlib
from pathlib import Path

from ..adapters.deployer import ServerDeployer
from ..models import ApplicationSourceType, ApplicationSpec, DesiredStateSpec
from ..secrets import get_or_create_project_ssh_key
from ..terraform_gen import get_generator
from .paths import cloudhand_dir, terraform_dir


_AUTO_PORT_RANGE_START = 20000
_AUTO_PORT_RANGE_END = 29999
_RESERVED_PORT_OWNERS = {
    22: "system:ssh",
    80: "system:http",
    443: "system:https",
}


def _validate_port(port: int, *, instance_name: str, workload_name: str) -> None:
    if port < 1 or port > 65535:
        raise ValueError(
            f"Invalid port {port} for workload '{workload_name}' on instance '{instance_name}'. "
            "Ports must be between 1 and 65535."
        )


def _deterministic_available_port(
    *,
    instance_name: str,
    workload_name: str,
    used_ports: dict[int, str],
) -> int:
    span = _AUTO_PORT_RANGE_END - _AUTO_PORT_RANGE_START + 1
    if span <= 0:
        raise ValueError("Invalid auto-port range configuration.")

    seed = hashlib.sha256(f"{instance_name}:{workload_name}".encode("utf-8")).hexdigest()
    offset = int(seed[:8], 16) % span

    for step in range(span):
        candidate = _AUTO_PORT_RANGE_START + ((offset + step) % span)
        if candidate not in used_ports:
            return candidate

    raise ValueError(
        f"No free ports available in range {_AUTO_PORT_RANGE_START}-{_AUTO_PORT_RANGE_END} "
        f"for workload '{workload_name}' on instance '{instance_name}'."
    )


def _set_or_validate_port_env(
    *,
    app: ApplicationSpec,
    instance_name: str,
    assigned_port: int,
) -> None:
    env_port_raw = (app.service_config.environment.get("PORT") or "").strip()
    if not env_port_raw:
        app.service_config.environment["PORT"] = str(assigned_port)
        return

    try:
        env_port = int(env_port_raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid PORT environment value '{env_port_raw}' for workload '{app.name}' "
            f"on instance '{instance_name}'."
        ) from exc

    if env_port != assigned_port:
        raise ValueError(
            f"PORT environment ({env_port}) conflicts with assigned service port ({assigned_port}) "
            f"for workload '{app.name}' on instance '{instance_name}'."
        )


def _assign_and_validate_instance_ports(*, instance_name: str, app_models: list[ApplicationSpec]) -> None:
    used_ports: dict[int, str] = dict(_RESERVED_PORT_OWNERS)

    # First pass: validate explicit ports and reserve them.
    for app in app_models:
        ports = list(app.service_config.ports)
        if not ports:
            continue

        seen_in_workload: set[int] = set()
        for port in ports:
            _validate_port(port, instance_name=instance_name, workload_name=app.name)
            if port in seen_in_workload:
                raise ValueError(
                    f"Duplicate port {port} configured multiple times for workload '{app.name}' "
                    f"on instance '{instance_name}'."
                )
            seen_in_workload.add(port)

            owner = used_ports.get(port)
            if owner and owner != app.name:
                raise ValueError(
                    f"Port conflict on instance '{instance_name}': port {port} is already reserved by '{owner}' "
                    f"and cannot be used by workload '{app.name}'."
                )
            used_ports[port] = app.name

    # Second pass: assign deterministic ports for workloads that omitted ports.
    for app in app_models:
        if app.service_config.ports:
            continue

        env_port_raw = (app.service_config.environment.get("PORT") or "").strip()
        if env_port_raw:
            try:
                env_port = int(env_port_raw)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid PORT environment value '{env_port_raw}' for workload '{app.name}' "
                    f"on instance '{instance_name}'."
                ) from exc
            _validate_port(env_port, instance_name=instance_name, workload_name=app.name)
            owner = used_ports.get(env_port)
            if owner and owner != app.name:
                raise ValueError(
                    f"Port conflict on instance '{instance_name}': port {env_port} is already reserved by '{owner}' "
                    f"and cannot be used by workload '{app.name}'."
                )
            app.service_config.ports = [env_port]
            used_ports[env_port] = app.name
            print(f"  -> Using PORT={env_port} for {app.name} on {instance_name} from environment.")
            continue

        assigned_port = _deterministic_available_port(
            instance_name=instance_name,
            workload_name=app.name,
            used_ports=used_ports,
        )
        app.service_config.ports = [assigned_port]
        used_ports[assigned_port] = app.name
        if app.source_type != ApplicationSourceType.FUNNEL_PUBLICATION:
            _set_or_validate_port_env(app=app, instance_name=instance_name, assigned_port=assigned_port)
        print(f"  -> Assigned port {assigned_port} to {app.name} on {instance_name}.")


def apply_plan(
    root: Path,
    plan_path: Path,
    auto_approve: bool = False,
    terraform_bin: str = "terraform",
    project_id: str = "default",
    workspace_id: str = "default",
) -> int:
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found at {plan_path}")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    new_spec_data = plan_data.get("new_spec")
    if not new_spec_data:
        raise ValueError("Plan does not contain 'new_spec'")

    # Validate and persist new spec
    new_spec = DesiredStateSpec.model_validate(new_spec_data)
    for inst in new_spec.instances:
        app_models = [
            app if isinstance(app, ApplicationSpec) else ApplicationSpec.model_validate(app)
            for app in inst.workloads
        ]
        _assign_and_validate_instance_ports(instance_name=inst.name, app_models=app_models)
        inst.workloads = app_models

    ch_dir = cloudhand_dir(root)
    ch_dir.mkdir(parents=True, exist_ok=True)
    spec_path = ch_dir / "spec.json"
    spec_path.write_text(new_spec.model_dump_json(indent=2), encoding="utf-8")

    # Regenerate Terraform to reflect the new spec
    generator = get_generator(new_spec.provider)
    tf_dir = terraform_dir(root)
    generator.generate(new_spec, tf_dir, project_id, workspace_id)

    # Acquire or create project SSH keypair
    print("Fetching SSH Identity...")
    priv_key, pub_key = get_or_create_project_ssh_key(project_id)

    # Run Terraform Apply
    tf_bin = shutil.which(terraform_bin)
    if not tf_bin:
        raise FileNotFoundError(f"Terraform binary '{terraform_bin}' not found in PATH")

    env = os.environ.copy()
    if "TF_VAR_hcloud_token" not in env and os.getenv("HCLOUD_TOKEN"):
        env["TF_VAR_hcloud_token"] = os.getenv("HCLOUD_TOKEN", "")
    env["TF_VAR_ssh_public_key"] = pub_key

    subprocess.run([tf_bin, "init", "-input=false", "-upgrade"], cwd=tf_dir, check=True, env=env)

    cmd = [tf_bin, "apply"]
    if auto_approve:
        cmd.append("-auto-approve")

    result = subprocess.run(cmd, cwd=tf_dir, env=env)
    if result.returncode != 0:
        return result.returncode

    # Load Terraform outputs for server IP mapping
    tf_out = subprocess.check_output([tf_bin, "output", "-json"], cwd=tf_dir, env=env)
    outputs = json.loads(tf_out)
    server_ips = outputs.get("server_ips", {}).get("value", {})

    # Deploy workloads over SSH
    print("Deploying Applications...")
    nginx_mode = os.getenv("CLOUDHAND_NGINX_MODE", "per-app").strip().lower()
    for inst in new_spec.instances:
        ip = server_ips.get(inst.name)
        if not ip or not inst.workloads:
            continue
        print(f" Configuring {inst.name} ({ip})...")
        deployer = ServerDeployer(ip, priv_key, local_root=root)

        app_models = [
            app if isinstance(app, ApplicationSpec) else ApplicationSpec.model_validate(app)
            for app in inst.workloads
        ]

        # Nginx routing modes:
        # - per-app (default): each workload gets its own nginx site (domain -> workload)
        # - combined: one nginx site proxies multiple workloads on a single host (path-based routing)
        if nginx_mode in {"combined", "single", "shared"}:
            if any(app.source_type == ApplicationSourceType.FUNNEL_PUBLICATION for app in app_models):
                raise ValueError(
                    "CLOUDHAND_NGINX_MODE=combined is not supported for workloads "
                    "with source_type='funnel_publication'. Use per-app mode."
                )
            deployed_apps = []
            for app_model in app_models:
                print(f"  -> Deploying {app_model.name} ({app_model.runtime})...")
                deployer.deploy(app_model, configure_nginx=False)
                deployed_apps.append(app_model)
            if deployed_apps:
                deployer.configure_combined_nginx(deployed_apps)
        else:
            for app_model in app_models:
                print(f"  -> Deploying {app_model.name} ({app_model.runtime})...")
                deployer.deploy(app_model, configure_nginx=True)

    return 0
