import asyncio
import json
import logging
import os
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
import grpc

import calculator_pb2
import calculator_pb2_grpc

from engines import (
    FunctionAnalysisEngine,
    solve,
    evaluate_expression,
    TangentEngine,
    _latex_tangent,
)

# --- Top-level wrapper functions for ProcessPoolExecutor ---
# Windows uses 'spawn' for multiprocessing, which requires target functions
# to be picklable and importable at the top-level.


def _run_all_engines(expr):
    """
    Run all 4 engines sequentially inside a single worker process.
    This avoids flooding the ProcessPoolExecutor queue with 20 tasks
    for 5 requests, preventing queue contention and reducing IPC overhead.
    Returns fully serialized data so we don't pass complex SymPy objects
    across the multiprocessing boundary.
    """
    import json
    from engines import (
        solve,
        FunctionAnalysisEngine,
        TangentEngine,
        evaluate_expression,
        _latex_tangent,
    )

    # Local imports of the helper functions
    from grpc_server import make_serializable, safe_json

    # 1. Domain/Range
    try:
        dr_res = solve(expr)
        dr_final = json.dumps(safe_json(dr_res)) if dr_res else "{}"
    except Exception as e:
        dr_final = json.dumps({"error": str(e)})

    # 2. Analysis & Tangent
    try:
        analysis_engine = FunctionAnalysisEngine(debug=False)
        analysis_res = analysis_engine.analyze(expr) or {}
    except Exception as e:
        analysis_res = {"error": str(e)}

    try:
        tangent_engine = TangentEngine()
        tangent_res = tangent_engine.compute(expr)
        if hasattr(tangent_res, "status") and getattr(tangent_res, "status") != "ERROR":
            try:
                analysis_res["Tangent Equation"] = _latex_tangent(tangent_res)
            except Exception:
                pass
    except Exception as e:
        pass  # Optional to add tangent errors directly to analysis

    # Serialize analysis entirely
    try:
        analysis_final = (
            json.dumps(make_serializable(analysis_res)) if analysis_res else "{}"
        )
    except Exception as e:
        analysis_final = json.dumps({"error": str(e)})

    # 3. Sequence/Series
    try:
        seq_ser_res = evaluate_expression(expr)
        seq_final = json.dumps(safe_json(seq_ser_res)) if seq_ser_res else "{}"
    except Exception as e:
        seq_final = json.dumps({"error": str(e)})

    return dr_final, analysis_final, seq_final


# Global process pool executor
_executor = None


def get_executor():
    global _executor
    if _executor is None:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        _executor = ProcessPoolExecutor(max_workers=multiprocessing.cpu_count())
    return _executor


def make_serializable(obj):
    """Flattens SymPy objects and lists/tuples into strings for the UI to display easily"""
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        if len(obj) == 0:
            return "None"
        return ", ".join(str(make_serializable(v)) for v in obj)
    elif isinstance(obj, tuple):
        return f"({', '.join(str(make_serializable(v)) for v in obj)})"
    elif obj is None:
        return "None"
    else:
        return str(obj).replace("oo", "∞")


def safe_json(obj):
    """Safely converts SymPy objects to strings while preserving JSON lists/dicts structure"""
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return [safe_json(v) for v in obj]
    elif obj is None or isinstance(obj, (int, float, bool, str)):
        return obj
    else:
        return str(obj).replace("oo", "∞")


class CalculatorService(calculator_pb2_grpc.CalculatorServiceServicer):
    def __init__(self):
        self.engine = FunctionAnalysisEngine(debug=False)
        self.tangent_engine = TangentEngine()

    async def AnalyzeFunction(self, request, context):
        expr = request.expression
        response = calculator_pb2.AnalyzeResponse()

        try:
            # Run all the underlying engine calculations concurrently by dispatching ONE task
            # per request to the ProcessPoolExecutor. This bypasses the GIL and eliminates queue starvation.
            loop = asyncio.get_running_loop()
            executor = get_executor()

            # The worker runs all engines for this specific expression, avoiding 4 IPC roundtrips
            dr_final, analysis_final, seq_final = await loop.run_in_executor(
                executor, _run_all_engines, expr
            )

            response.domain_range = dr_final
            response.function_analysis = analysis_final
            response.sequence_series = seq_final
            response.has_error = False

        except Exception as e:
            response.has_error = True
            response.error_message = str(e)

        return response


async def serve():
    # Load environment variables with fallback
    service_dir = Path(__file__).resolve().parent
    root_dir = service_dir.parent

    root_env = root_dir / ".env"
    service_env = service_dir / ".env"

    if root_env.exists():
        load_dotenv(root_env)
        logging.info("Loaded .env from root: %s", root_env)
    elif service_env.exists():
        load_dotenv(service_env)
        logging.info("Loaded .env from service: %s", service_env)
    else:
        logging.info("No .env file found. Using default/system environment variables.")

    server = grpc.aio.server()
    calculator_pb2_grpc.add_CalculatorServiceServicer_to_server(
        CalculatorService(), server
    )
    url = os.getenv("GRPC_SERVER_URL")
    if not url:
        raise RuntimeError("Missing required environment variable: GRPC_SERVER_URL")
    port = os.getenv("GRPC_SERVER_PORT")
    if not port:
        raise RuntimeError("Missing required environment variable: GRPC_SERVER_PORT")
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    logging.info(
        "Starting server on %s (loaded GRPC_SERVER_PORT=%s)", listen_addr, port
    )
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        executor = get_executor()
        if executor:
            executor.shutdown(wait=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
