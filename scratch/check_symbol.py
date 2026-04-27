import sys
import os
sys.path.append(os.path.abspath('openapi_pb2'))
from openapi_pb2 import OpenApiModelMessages_pb2 as model
deal = model.ProtoOADeal()
print("Has closePositionDetail?", deal.HasField("closePositionDetail"))
