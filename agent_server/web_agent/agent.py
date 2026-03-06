from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams
from mcp import StdioServerParameters
import os,json
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ["INCEPTION_API_KEY"]


DEFAULT_PARAMS = json.dumps({
    # docs for tewaking prams for better results with the tavily web search tool
    # https://docs.tavily.com/documentation/api-reference/endpoint/search
    # https://docs.tavily.com/documentation/best-practices/best-practices-search#search-depth
    
    "max_results": 3,
    "search_depth": "basic",  #basic and ultra-fast also an option
    "include_raw_content": False,
    "include_favicon": False,
    "include_images": False,
    "include_answer":True,
    # "exclude_domains":True,
    "auto_parameters":False,
    "exact_match": True,
})
model = LiteLlm(
    model="openai/mercury-2",
    api_key=api_key,
    api_base="https://api.inceptionlabs.ai/v1",
    max_tokens=8000,
)

root_agent = LlmAgent(
    name="Search_and_Solve_Agent",
    model=model,
    instruction="""You are an expert mathematics tutor specializing in Calculus.
Your tools:
- A web search tool to find information on the internet.

Rules for tool usage:
- When external information is required, make exactly one tool call to the web search tool.
- Do not call the web search tool more than once for a single student query.
- If the search results are insufficient, continue using your internal knowledge; do not invoke the web search again.
- You may use other available tools when appropriate, but minimize tool calls and show full reasoning.

Your role:
- Solve student problems clearly, concisely, and step-by-step.
- Be an expert on Calculus.
- Only invoke the web search tool when absolutely necessary and only once per query.""",
    description="A concise, expert Calculus tutor that solves student problems step-by-step.",
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=[
                        "-y",
                        "tavily-mcp@latest",
                    ],
                    env={
                        "TAVILY_API_KEY": os.environ["TAVILY_API_KEY"],
                        "DEFAULT_PARAMETERS":DEFAULT_PARAMS  ,
                    }
                ),
                timeout=30,
            ),
        )
    ],
)

