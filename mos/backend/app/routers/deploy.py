from __future__ import annotations

from ipaddress import ip_address
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.auth.dependencies import AuthContext, get_current_user
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


class WorkloadDomainsResponse(BaseModel):
    workload_name: str
    plan_path: str
    workload_found: bool
    server_names: list[str]
    https: Optional[bool] = None


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
    _auth: AuthContext = Depends(get_current_user),
):
    _require_internal_proxy(request)
    try:
        return deploy_service.patch_workload_in_plan(
            workload_patch=workload,
            plan_path=plan_path,
            instance_name=instance_name,
            create_if_missing=create_if_missing,
            in_place=in_place,
        )
    except deploy_service.DeployError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/plans/workloads/domains", response_model=WorkloadDomainsResponse)
async def get_workload_domains(
    request: Request,
    workload_name: str = Query(..., description="Workload name to locate inside the deploy plan"),
    plan_path: Optional[str] = Query(default=None),
    instance_name: Optional[str] = Query(default=None),
    _auth: AuthContext = Depends(get_current_user),
):
    _require_internal_proxy(request)
    try:
        result = deploy_service.get_workload_domains_from_plan(
            workload_name=workload_name,
            plan_path=plan_path,
            instance_name=instance_name,
        )
        return {
            "workload_name": workload_name,
            **result,
        }
    except deploy_service.DeployError as exc:
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
        return await deploy_service.apply_plan(plan_path=(payload.plan_path if payload else None))
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
