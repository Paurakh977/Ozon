"use server";

import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import path from 'path';

const PROTO_PATH = path.resolve(process.cwd(), 'proto/calculator.proto');

const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: globalThis.String,
  enums: globalThis.String,
  defaults: true,
  oneofs: true
});

const calculatorProto = grpc.loadPackageDefinition(packageDefinition).calculator as any;

// Use a singleton to avoid reconnecting constantly in dev
let client: any = null;

function getClient() {
  if (!client) {
    const grpcUrl = process.env.GRPC_SERVER_URL || 'localhost:50051';
    console.log(`[gRPC Client] Connecting to gRPC server at: ${grpcUrl}`);
    client = new calculatorProto.CalculatorService(
      grpcUrl,
      grpc.credentials.createInsecure()
    );
  }
  return client;
}

export async function analyzeFunction(expression: string) {
  const rpcClient = getClient();
  
  return new Promise((resolve, reject) => {
    rpcClient.AnalyzeFunction({ expression }, (error: any, response: any) => {
      if (error) {
        console.error("gRPC Error:", error);
        resolve({ has_error: true, error_message: error.message });
      } else {
        // Parse the JSON strings returned from the gRPC server
        resolve({
          domain_range: response.domain_range ? JSON.parse(response.domain_range) : null,
          function_analysis: response.function_analysis ? JSON.parse(response.function_analysis) : null,
          sequence_series: response.sequence_series ? JSON.parse(response.sequence_series) : null,
          has_error: response.has_error,
          error_message: response.error_message,
        });
      }
    });
  });
}
