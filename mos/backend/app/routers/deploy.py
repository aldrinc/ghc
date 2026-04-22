from __future__ import annotations

from ipaddress import ip_address
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.repositories.org_deploy_domains import (
    LEGACY_DEPLOY_DOMAIN_SCOPE_ERROR,
    OrgDeployDomainsRepository,
)
from app.services import deploy as deploy_service

router = APIRouter(prefix="/deploy", tags=["deploy"])


def _is_loopback_host(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        # Starlette's TestClient uses a non-IP placeholder hostname.
        return host in {"testclient", "localhost"}


def _require_internal_proxy(request: Request) -> None:
    """
    Block direct hits to the backend port when the API is intended to be accessed
    only via the MOS reverse proxy.
    """
    client = request.client
    if client is None or not _is_loopback_host(client.host):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available via the MOS reverse proxy.",
        )


class PlanUpdate(BaseModel):
    content: str = Field(..., description="Full JSON content of the plan")
    path: Optional[str] = Field(None, description="Optional plan path (inside DEPLOY_ROOT_DIR)")


class ApplyPayload(BaseModel):
    plan_path: Optional[str] = Field(None, description="Optional plan file path (inside DEPLOY_ROOT_DIR)")
    workload_names: Optional[list[str]] = Field(
        None,
        description="Optional workload names to scope artifact materialization and apply/deploy steps.",
    )


class WorkloadDomainsResponse(BaseModel):
    workload_name: str
    plan_path: str
    workload_found: bool
    server_names: list[str]
    workspace_id: str
    workspace_server_names: list[str]
    workspace_scope_error: Optional[str] = None
    https: Optional[bool] = None


def _normalize_server_names(values: Any) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workload service_config.server_names must be a list.",
        )
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workload service_config.server_names entries must be strings.",
            )
        hostname = raw.strip().lower()
        if not hostname or hostname in seen:
            continue
        seen.add(hostname)
        normalized.append(hostname)
    return normalized


def _extract_workspace_server_names(workload: dict[str, Any]) -> list[str] | None:
    if "workspace_server_names" in workload:
        return _normalize_server_names(workload.get("workspace_server_names"))
    service_config = workload.get("service_config")
    if isinstance(service_config, dict) and "server_names" in service_config:
        return _normalize_server_names(service_config.get("server_names"))
    return None


@router.get("/plans/latest")
async def latest_plan(
    request: Request,
    _auth: AuthContext = Depends(get_current_user),
):
    _require_internal_proxy(request)
    try:
        return deploy_service.get_latest_plan()
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/plans")
async def save_plan(
    request: Request,
    body: PlanUpdate,
    _auth: AuthContext = Depends(get_current_user),
):
    _require_internal_proxy(request)
    try:
        return deploy_service.save_plan(content=body.content, path=body.path)
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/plans/workloads")
async def patch_workload(
    request: Request,
    workload: dict[str, Any] = Body(..., description="Workload object (patch). Must include at least a 'name'."),
    plan_path: Optional[str] = Query(default=None),
    instance_name: Optional[str] = Query(default=None),
    create_if_missing: bool = Query(default=False),
    in_place: bool = Query(default=False),
    configure_bunny_pull_zone: bool = Query(default=False),
    bunny_pull_zone_origin_ip: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_internal_proxy(request)
    try:
        workspace_server_names = _extract_workspace_server_names(workload)
        workload_for_plan = dict(workload)
        if workspace_server_names is not None:
            workload_for_plan["workspace_server_names"] = workspace_server_names
        if configure_bunny_pull_zone:
            service_config = workload_for_plan.get("service_config")
            if service_config is None:
                service_config = {}
            if not isinstance(service_config, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workload service_config must be an object.",
                )
            normalized_service_config = dict(service_config)
            # Keep deploy plan port-based: domains are managed separately for Bunny/Namecheap.
            normalized_service_config["server_names"] = []
            normalized_service_config["https"] = False
            workload_for_plan["service_config"] = normalized_service_config

        result = deploy_service.patch_workload_in_plan(
            org_id=auth.org_id,
            workload_patch=workload_for_plan,
            plan_path=plan_path,
            instance_name=instance_name,
            create_if_missing=create_if_missing,
            in_place=in_place,
        )
        workload_name = str(workload_for_plan.get("name") or "").strip()
        if not workload_name:
            raise deploy_service.DeployError("Workload patch must include a non-empty 'name' field.")
        workspace_id = deploy_service.get_workload_workspace_id_from_plan(
            workload_name=workload_name,
            plan_path=result.get("updated_plan_path"),
            instance_name=instance_name,
        )
        if configure_bunny_pull_zone:
            result["cdn"] = deploy_service.configure_bunny_pull_zone_for_workload(
                client_id=workspace_id,
                workload_name=workload_name,
                plan_path=result.get("updated_plan_path"),
                instance_name=instance_name,
                requested_origin_ip=bunny_pull_zone_origin_ip,
                server_names=(workspace_server_names or []),
            )

        return result
    except (deploy_service.DeployError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/plans/workloads/domains", response_model=WorkloadDomainsResponse)
async def get_workload_domains(
    request: Request,
    workload_name: str = Query(..., description="Workload name to locate inside the deploy plan"),
    plan_path: Optional[str] = Query(default=None),
    instance_name: Optional[str] = Query(default=None),
    workspace_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _require_internal_proxy(request)
    try:
        result = deploy_service.get_workload_domains_from_plan(
            workload_name=workload_name,
            plan_path=plan_path,
            instance_name=instance_name,
        )
        resolved_workspace_id = (
            deploy_service.get_workload_workspace_id_from_plan(
                workload_name=workload_name,
                plan_path=result.get("plan_path"),
                instance_name=instance_name,
            )
            if result.get("workload_found")
            else None
        )
        requested_workspace_id = str(workspace_id or "").strip() or None
        if requested_workspace_id and resolved_workspace_id and requested_workspace_id != resolved_workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Requested workspace_id '{requested_workspace_id}' does not match workload "
                    f"workspace '{resolved_workspace_id}'."
                ),
            )
        effective_workspace_id = requested_workspace_id or resolved_workspace_id
        if not effective_workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_id is required when the workload is not yet present in the plan.",
            )
        workspace_scope_error = None
        workspace_server_names_value = result.get("workspace_server_names")
        if workspace_server_names_value is None:
            if result.get("workload_found"):
                repo = OrgDeployDomainsRepository(session)
                workspace_server_names = repo.list_hostnames(
                    org_id=auth.org_id,
                    client_id=effective_workspace_id,
                    strict=False,
                )
                if not workspace_server_names and repo.has_legacy_unscoped_hostnames(org_id=auth.org_id):
                    workspace_scope_error = LEGACY_DEPLOY_DOMAIN_SCOPE_ERROR
            else:
                workspace_server_names = []
        else:
            workspace_server_names = _normalize_server_names(workspace_server_names_value)
        return {
            "workload_name": workload_name,
            "workspace_id": effective_workspace_id,
            "workspace_server_names": workspace_server_names,
            "workspace_scope_error": workspace_scope_error,
            **result,
        }
    except (deploy_service.DeployError, ValueError) as exc:
        message = str(exc)
        code = status.HTTP_404_NOT_FOUND if "No plan found" in message else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=message) from exc


@router.post("/plans/apply")
async def apply_plan(
    request: Request,
    payload: Optional[ApplyPayload] = None,
    _auth: AuthContext = Depends(get_current_user),
):
    _require_internal_proxy(request)
    try:
        return await deploy_service.apply_plan(
            plan_path=(payload.plan_path if payload else None),
            workload_names=(payload.workload_names if payload else None),
        )
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/apply")
async def apply_latest_plan_alias(
    request: Request,
    payload: Optional[ApplyPayload] = None,
    _auth: AuthContext = Depends(get_current_user),
):
    """
    Backwards-compatible alias for /deploy/plans/apply.
    """
    return await apply_plan(request=request, payload=payload, _auth=_auth)


@router.post("/plans/apply-async")
async def apply_plan_async(
    request: Request,
    payload: Optional[ApplyPayload] = None,
    _auth: AuthContext = Depends(get_current_user),
):
    _require_internal_proxy(request)
    try:
        job = deploy_service.start_apply_plan_job(
            plan_path=(payload.plan_path if payload else None),
            workload_names=(payload.workload_names if payload else None),
        )
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "jobId": job["id"],
        "status": job["status"],
        "planPath": job["plan_path"],
        "statusPath": f"/deploy/plans/apply-jobs/{job['id']}",
        "workloadNames": job.get("workload_names", []),
    }


@router.post("/apply-async")
async def apply_latest_plan_async_alias(
    request: Request,
    payload: Optional[ApplyPayload] = None,
    _auth: AuthContext = Depends(get_current_user),
):
    return await apply_plan_async(request=request, payload=payload, _auth=_auth)


@router.get("/plans/apply-jobs/{job_id}")
async def get_apply_plan_job(
    request: Request,
    job_id: str,
    _auth: AuthContext = Depends(get_current_user),
):
    _require_internal_proxy(request)
    try:
        return deploy_service.get_apply_plan_job(job_id=job_id)
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/apply-jobs/{job_id}")
async def get_apply_plan_job_alias(
    request: Request,
    job_id: str,
    _auth: AuthContext = Depends(get_current_user),
):
    return await get_apply_plan_job(request=request, job_id=job_id, _auth=_auth)
