from app.db.base import SessionLocal
from app.llm import LLMClient
from app.services.deep_research import DeepResearchJobService

from .types import DeepResearchJobRef, LlmGenerationResult, StepGenerationRequest


def run_llm_generation(request: StepGenerationRequest) -> LlmGenerationResult:
    llm = LLMClient(default_model=request.llm_params.model)
    raw_output = llm.generate_text(request.prompt_text, request.llm_params)
    return LlmGenerationResult(raw_output=raw_output)


def run_deep_research(request: StepGenerationRequest) -> LlmGenerationResult:
    with SessionLocal() as session:
        job_service = DeepResearchJobService(session)
        llm_output, job = job_service.run_deep_research(
            org_id=request.org_id or "",
            client_id=request.client_id or "",
            prompt=request.prompt_text,
            model=request.llm_params.model,
            prompt_sha256=request.prompt_sha256,
            use_web_search=bool(request.llm_params.use_web_search),
            max_output_tokens=request.llm_params.max_tokens,
            step_key=request.step_key,
            workflow_run_id=request.workflow_run_id,
            parent_run_id=request.parent_run_id,
            onboarding_payload_id=request.onboarding_payload_id,
            temporal_workflow_id=request.workflow_id,
            parent_workflow_id=request.parent_workflow_id,
            metadata={"title": request.title},
        )
    job_ref = None
    if job:
        status_value = getattr(job, "status", None)
        if hasattr(status_value, "value"):
            status_value = status_value.value
        job_ref = DeepResearchJobRef(
            job_id=str(getattr(job, "id", "")),
            response_id=getattr(job, "response_id", None),
            status=status_value,
        )
    return LlmGenerationResult(raw_output=llm_output, job=job_ref)
