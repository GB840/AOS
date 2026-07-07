import sys
import os

# 将 src/common 与当前包目录加入模块搜索路径
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'common'))
sys.path.insert(0, _HERE)

from concurrent import futures
import grpc
import meta_orchestrator_pb2 as mo_pb2
import meta_orchestrator_pb2_grpc as mo_grpc

# 真实 L3.5 元调度引擎
from engine import MetaOrchestratorEngine

_engine = MetaOrchestratorEngine()


class MetaOrchestratorServicer(mo_grpc.MetaOrchestratorServicer):
    def RouteIntent(self, request, context):
        result = _engine.route_intent(
            intent=request.intent,
            user_id=request.user_id,
            project_id=request.project_id,
            trace_id=request.trace_id,
        )
        return mo_pb2.RouteIntentResponse(
            workflow_id=str(result["workflow_id"]),
            priority=int(result["priority"]),
            persona_config=str(result["persona_config"]),
        )

    def QueryPriority(self, request, context):
        return mo_pb2.QueryPriorityResponse(
            priority_level=int(_engine.query_priority(request.task_id))
        )

    def InjectPersona(self, request, context):
        return mo_pb2.InjectPersonaResponse(
            persona_config=str(_engine.inject_persona(request.user_id, request.project_id))
        )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    mo_grpc.add_MetaOrchestratorServicer_to_server(MetaOrchestratorServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("L3.5 Meta Orchestrator running on port 50051")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
