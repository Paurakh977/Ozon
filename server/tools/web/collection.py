from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams
from mcp import StdioServerParameters
import os, json
from dotenv import load_dotenv
from environment import WEB_SEARCH_API_KEY

load_dotenv()


DEFAULT_PARAMS = json.dumps(
    {
        # docs for tewaking prams for better results with the tavily web search tool
        # https://docs.tavily.com/documentation/api-reference/endpoint/search
        # https://docs.tavily.com/documentation/best-practices/best-practices-search#search-depth
        "max_results": 3,
        "search_depth": "basic",  # basic and ultra-fast also an option
        "include_raw_content": False,
        "include_favicon": False,
        "include_images": False,
        "include_answer": True,
        # "exclude_domains":True,
        "auto_parameters": False,
        "exact_match": True,
    }
)


web_search_mcp_tools = [
    McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=[
                    "-y",
                    "tavily-mcp@latest",
                ],
                env={
                    "TAVILY_API_KEY": WEB_SEARCH_API_KEY,
                    "DEFAULT_PARAMETERS": DEFAULT_PARAMS,
                },
            ),
            timeout=30,
        ),
    )
]
