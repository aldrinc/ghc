from temporalio import workflow


@workflow.defn
class PlaceholderWorkflow:
    @workflow.run
    async def run(self) -> None:
        return None
