import asyncio
import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from concurrent import futures
import grpc

import calculator_pb2
import calculator_pb2_grpc

from engines import FunctionAnalysisEngine, solve, evaluate_expression, TangentEngine, _latex_tangent

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
        return str(obj).replace('oo', '∞')

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
        return str(obj).replace('oo', '∞')

class CalculatorService(calculator_pb2_grpc.CalculatorServiceServicer):
    def __init__(self):
        self.engine = FunctionAnalysisEngine(debug=False)
        self.tangent_engine = TangentEngine()

    async def AnalyzeFunction(self, request, context):
        expr = request.expression
        response = calculator_pb2.AnalyzeResponse()
        
        try:
            # Domain and Range
            try:
                dr = await asyncio.to_thread(solve, expr)
                response.domain_range = json.dumps(safe_json(dr)) if dr else "{}"
            except Exception as e:
                response.domain_range = json.dumps({"error": str(e)})

            # Function Analysis
            try:
                analysis = await asyncio.to_thread(self.engine.analyze, expr)
                
                # Also get tangent equation
                try:
                    tangent_res = await asyncio.to_thread(self.tangent_engine.compute, expr)
                    if tangent_res.status != "ERROR":
                        analysis["Tangent Equation"] = _latex_tangent(tangent_res)
                except Exception as e:
                    pass

                response.function_analysis = json.dumps(make_serializable(analysis)) if analysis else "{}"
            except Exception as e:
                response.function_analysis = json.dumps({"error": str(e)})

            # Sequence and Series
            try:
                seq_ser = await asyncio.to_thread(evaluate_expression, expr)
                response.sequence_series = json.dumps(safe_json(seq_ser)) if seq_ser else "{}"
            except Exception as e:
                response.sequence_series = json.dumps({"error": str(e)})
            
            response.has_error = False

        except Exception as e:
            response.has_error = True
            response.error_message = str(e)
            
        return response

async def serve():
    # Load environment variables with fallback
    service_dir = Path(__file__).resolve().parent
    root_dir = service_dir.parent
    
    root_env = root_dir / '.env'
    service_env = service_dir / '.env'
    
    if root_env.exists():
        load_dotenv(root_env)
        logging.info("Loaded .env from root: %s", root_env)
    elif service_env.exists():
        load_dotenv(service_env)
        logging.info("Loaded .env from service: %s", service_env)
    else:
        logging.info("No .env file found. Using default/system environment variables.")

    server = grpc.aio.server()
    calculator_pb2_grpc.add_CalculatorServiceServicer_to_server(CalculatorService(), server)
    port = os.getenv('GRPC_SERVER_PORT', '50051')
    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    logging.info("Starting server on %s (loaded GRPC_SERVER_PORT=%s)", listen_addr, port)
    await server.start()
    await server.wait_for_termination()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
