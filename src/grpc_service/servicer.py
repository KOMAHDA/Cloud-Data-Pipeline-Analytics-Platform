import json
import logging
import grpc

from src.grpc_generated import analytics_pb2, analytics_pb2_grpc
from src.grpc_service.handlers import HANDLERS, run_handler

logger = logging.getLogger("grpc_analytics")


class AnalyticsServicer(analytics_pb2_grpc.AnalyticsServiceServicer):
    def ExecutePipeline(self, request, context):
        logger.info(
            "[gRPC] ExecutePipeline received: job_id=%s, dataset='%s' (%s rows), steps=%s",
            request.job_id,
            request.dataset_name,
            request.row_count,
            len(request.steps),
        )

        if not request.steps:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Pipeline must contain at least one step")
            return analytics_pb2.ExecutePipelineResponse(
                job_id=request.job_id,
                status="FAILED",
                error_message="Pipeline must contain at least one step",
            )

        exec_context = {
            "dataset_id": request.dataset_id,
            "file_path": request.file_path,
            "rows": request.row_count,
        }
        sorted_steps = sorted(request.steps, key=lambda s: s.step_order)
        step_results = []
        summary_metrics = {}

        for step in sorted_steps:
            try:
                params = json.loads(step.params_json) if step.params_json else {}
            except json.JSONDecodeError as exc:
                msg = f"Invalid JSON params at step {step.step_order}: {exc}"
                logger.error("[gRPC] %s", msg)
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(msg)
                return analytics_pb2.ExecutePipelineResponse(
                    job_id=request.job_id,
                    status="FAILED",
                    completed_steps=len(step_results),
                    error_message=msg,
                    step_results=step_results,
                )

            logger.info(
                "[gRPC] Job #%s -> Step %s: algorithm=%s, handler=%s",
                request.job_id,
                step.step_order,
                step.algorithm_code,
                step.grpc_handler,
            )
            metrics, duration_ms = run_handler(step.grpc_handler, exec_context, params)
            summary_metrics[f"step_{step.step_order}_{step.algorithm_code}"] = metrics

            step_results.append(
                analytics_pb2.StepExecutionResult(
                    step_order=step.step_order,
                    algorithm_code=step.algorithm_code,
                    status="COMPLETED",
                    duration_ms=duration_ms,
                    metrics_json=json.dumps(metrics, ensure_ascii=False),
                )
            )

        final_result = {
            "dataset_id": request.dataset_id,
            "initial_rows": request.row_count,
            "final_rows": exec_context["rows"],
            "steps_summary": summary_metrics,
        }
        logger.info("[gRPC] Job #%s finished: COMPLETED (final_rows=%s)", request.job_id, exec_context["rows"])

        return analytics_pb2.ExecutePipelineResponse(
            job_id=request.job_id,
            status="COMPLETED",
            completed_steps=len(step_results),
            result_json=json.dumps(final_result, ensure_ascii=False),
            step_results=step_results,
        )

    def ValidatePipeline(self, request, context):
        logger.info("[gRPC] ValidatePipeline received: steps=%s", len(request.steps))
        errors = []
        if not request.steps:
            errors.append("Pipeline has no steps")

        seen_orders = set()
        for step in request.steps:
            if step.step_order in seen_orders:
                errors.append(f"Duplicate step_order: {step.step_order}")
            seen_orders.add(step.step_order)

            if step.params_json:
                try:
                    json.loads(step.params_json)
                except json.JSONDecodeError:
                    errors.append(f"Invalid params_json at step {step.step_order}")

        return analytics_pb2.ValidatePipelineResponse(
            is_valid=len(errors) == 0,
            errors=errors,
            supported_handlers=sorted(HANDLERS.keys()),
        )