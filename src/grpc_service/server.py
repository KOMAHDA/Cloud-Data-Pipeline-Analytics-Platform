from concurrent import futures
import logging
import grpc

from src.config import GRPC_HOST, GRPC_PORT
from src.grpc_generated import analytics_pb2_grpc
from src.grpc_service.servicer import AnalyticsServicer


def serve() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    analytics_pb2_grpc.add_AnalyticsServiceServicer_to_server(AnalyticsServicer(), server)

    bind_address = f"{GRPC_HOST}:{GRPC_PORT}"
    server.add_insecure_port(bind_address)
    server.start()
    logging.getLogger("grpc_analytics").info("gRPC AnalyticsService started on %s", bind_address)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()