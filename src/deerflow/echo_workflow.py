from temporalio import workflow, activity
from datetime import timedelta

@activity.defn
async def echo_activity(message: str) -> str:
    print(f"[DeerFlow Activity] Echoing: {message}")
    return f"Echo: {message}"

@workflow.defn
class EchoWorkflow:
    @workflow.run
    async def run(self, message: str) -> str:
        # 调用 echo activity
        result = await workflow.execute_activity(
            echo_activity,
            message,
            start_to_close_timeout=timedelta(seconds=10)
        )
        return result