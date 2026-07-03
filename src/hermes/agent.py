import sys, os, grpc, json, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))

import meta_orchestrator_pb2 as mo_pb2
import meta_orchestrator_pb2_grpc as mo_grpc

class HermesAgent:
    def __init__(self):
        self.channel = grpc.insecure_channel('localhost:50051')
        self.stub = mo_grpc.MetaOrchestratorStub(self.channel)

    def process_input(self, user_input: str, user_id: str, project_id: str):
        trace_id = str(uuid.uuid4())
        # 1. 调用元调度路由层
        route_resp = self.stub.RouteIntent(mo_pb2.RouteIntentRequest(
            intent=user_input,
            user_id=user_id,
            project_id=project_id,
            trace_id=trace_id
        ))
        print(f"[Hermes] Routed to workflow: {route_resp.workflow_id}, priority: {route_resp.priority}")
        # 2. 下一步是将工作流 ID 发送给 DeerFlow（稍后实现）
        return route_resp.workflow_id

if __name__ == '__main__':
    agent = HermesAgent()
    agent.process_input("测试消息", "user_001", "project_demo")
    print("[Hermes] Agent test complete.")