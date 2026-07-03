import sys
import os

# 将 src/common 加入模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'common'))

from concurrent import futures
import grpc
import meta_orchestrator_pb2 as mo_pb2
import meta_orchestrator_pb2_grpc as mo_grpc

# proto 生成的代码在 src/common 目录，需要先确保路径
import sys
sys.path.insert(0, '../common')

import meta_orchestrator_pb2 as mo_pb2
import meta_orchestrator_pb2_grpc as mo_grpc

class MetaOrchestratorServicer(mo_grpc.MetaOrchestratorServicer):
    def RouteIntent(self, request, context):
        # 一期存根：返回固定路由结果
        return mo_pb2.RouteIntentResponse(
            workflow_id="echo_workflow",
            priority=5,
            persona_config='{"style": "concise", "extensions": {}}'
        )

    def QueryPriority(self, request, context):
        return mo_pb2.QueryPriorityResponse(priority_level=5)

    def InjectPersona(self, request, context):
        return mo_pb2.InjectPersonaResponse(
            persona_config='{"style": "concise", "extensions": {}}'
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