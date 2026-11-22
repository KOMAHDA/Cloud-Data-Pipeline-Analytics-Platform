import json
import grpc

from src.config import GRPC_HOST, GRPC_PORT
from src.grpc_generated import analytics_pb2, analytics_pb2_grpc


def main() -> None:
    with grpc.insecure_channel(f"{GRPC_HOST}:{GRPC_PORT}") as channel:
        stub = analytics_pb2_grpc.AnalyticsServiceStub(channel)

        steps = [
            analytics_pb2.PipelineStepInput(
                step_order=1,
                algorithm_code="clean",
                grpc_handler="clean_nulls",
                params_json=json.dumps({"drop_ratio": 0.1}),
            ),
            analytics_pb2.PipelineStepInput(
                step_order=2,
                algorithm_code="norm",
                grpc_handler="normalize",
                params_json=json.dumps({"method": "min-max"}),
            ),
        ]

        val_resp = stub.ValidatePipeline(analytics_pb2.ValidatePipelineRequest(steps=steps))
        print("ValidatePipeline:", val_resp.is_valid, list(val_resp.supported_handlers))

        exec_resp = stub.ExecutePipeline(
            analytics_pb2.ExecutePipelineRequest(
                job_id=1,
                dataset_id=10,
                dataset_name="sales_2026.csv",
                file_path="/data/sales_2026.csv",
                row_count=1000,
                steps=steps,
            )
        )
        print("ExecutePipeline:", exec_resp.status, exec_resp.result_json)


if __name__ == "__main__":
    main()