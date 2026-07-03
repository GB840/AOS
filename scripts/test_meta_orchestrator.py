import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'common'))

import grpc
import meta_orchestrator_pb2 as mo_pb2
import meta_orchestrator_pb2_grpc as mo_grpc