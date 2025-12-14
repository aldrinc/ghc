from temporalio import activity


@activity.defn
def noop_activity() -> str:
    return "ok"
