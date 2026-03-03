import os
from litellm import completion
import dotenv

dotenv.load_dotenv()
api_key = os.environ["INCEPTION_API_KEY"]

response = completion(
    model="openai/mercury-2",
    messages=[{"role": "user", "content": "What is a diffusion model?"}],
    api_key=api_key,
    api_base="https://api.inceptionlabs.ai/v1",
    max_tokens=1000,
    stream=True, # Streaming MUST be true to use the diffusing effect
    extra_body={
        "diffusing": True # Pass the custom diffusing parameter here
    }
)

# Since stream=True, the response is now a generator. 
# You need to iterate over it to print the diffusing chunks as they arrive.
for chunk in response:
    # Extract the delta content and print it to the console immediately
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)