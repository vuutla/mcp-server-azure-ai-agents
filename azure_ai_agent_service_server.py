"""Azure AI Agent Service MCP Server for Claude Desktop using Azure AI Search and Bing Web Grounding Tools."""

import os
import sys
import asyncio
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Import Azure AI Agent Service modules
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import AzureAISearchTool, BingGroundingTool, MessageRole
from azure.identity import DefaultAzureCredential

# Add startup message
print("Starting Azure AI Agent Service MCP Server...", file=sys.stderr)

# Load environment variables
load_dotenv()
print("Environment variables loaded", file=sys.stderr)

# Create MCP server
mcp = FastMCP(
    "azure-ai-agent", 
    description="MCP server for Azure AI Agent Service integration with AzureAISearch and Bing Web Grounding tools",
    dependencies=[
        "azure-identity",
        "python-dotenv",
        "azure-ai-projects"
    ]
)
print("MCP server instance created", file=sys.stderr)

class AzureAIAgentClient:
    """Client for Azure AI Agent Service with Azure AI Search and Bing Web Grounding tools."""
    
    def __init__(self):
        """Initialize Azure AI Agent Service client with credentials from environment variables."""
        print("Initializing Azure AI Agent client...", file=sys.stderr)
        
        # Load environment variables
        self.project_connection_string = os.getenv("PROJECT_CONNECTION_STRING")
        self.model_deployment_name = os.getenv("MODEL_DEPLOYMENT_NAME")
        self.search_connection_name = os.getenv("AI_SEARCH_CONNECTION_NAME")
        self.bing_connection_name = os.getenv("BING_CONNECTION_NAME")
        self.index_name = os.getenv("AI_SEARCH_INDEX_NAME")
        
        # Validate environment variables
        required_vars = {
            "PROJECT_CONNECTION_STRING": self.project_connection_string,
            "MODEL_DEPLOYMENT_NAME": self.model_deployment_name,
            "AI_SEARCH_CONNECTION_NAME": self.search_connection_name,
            "BING_CONNECTION_NAME": self.bing_connection_name,
            "AI_SEARCH_INDEX_NAME": self.index_name
        }
        
        missing = [k for k, v in required_vars.items() if not v]
        if missing:
            error_msg = f"Missing environment variables: {', '.join(missing)}"
            print(f"Error: {error_msg}", file=sys.stderr)
            raise ValueError(error_msg)
        
        # Initialize AIProjectClient
        try:
            self.client = AIProjectClient.from_connection_string(
                credential=DefaultAzureCredential(),
                conn_str=self.project_connection_string
            )
            print("AIProjectClient initialized successfully", file=sys.stderr)
        except Exception as e:
            print(f"Error initializing AIProjectClient: {str(e)}", file=sys.stderr)
            raise
        
        print(f"Azure AI Agent client initialized for AI Search connection: {self.search_connection_name}, Bing connection: {self.bing_connection_name}", file=sys.stderr)
    
    def search_index(self, query, top=5):
        """
        Perform a search using Azure AI Search Tool (default: best/hybrid mode).
        
        Args:
            query: The search query text
            top: Maximum number of results to return
            
        Returns:
            Formatted search results
        """
        print(f"Performing AI Search for: {query}", file=sys.stderr)
        
        try:
            # Get Azure AI Search connection
            search_connection = self.client.connections.get(connection_name=self.search_connection_name)
            if not search_connection:
                raise ValueError(f"Connection '{self.search_connection_name}' not found")
            
            # Create search tool
            search_tool = AzureAISearchTool(
                index_connection_id=search_connection.id,
                index_name=self.index_name
            )
            
            # Create agent with the search tool
            agent = self.client.agents.create_agent(
                model=self.model_deployment_name,
                name="search-agent",
                instructions=f"You are an Azure AI Search expert. Use the Azure AI Search Tool to find the most relevant information for: '{query}'. Return only the top {top} most relevant results. For each result, provide a title, content excerpt, and relevance score if available. Format your response as Markdown with each result clearly separated.",
                tools=search_tool.definitions,
                tool_resources=search_tool.resources,
                headers={"x-ms-enable-preview": "true"}
            )
            
            # Create thread for communication
            thread = self.client.agents.create_thread()
            
            # Create message to thread
            self.client.agents.create_message(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=query
            )
            
            # Process the run
            run = self.client.agents.create_and_process_run(
                thread_id=thread.id,
                agent_id=agent.id
            )
            
            if run.status == "failed":
                print(f"Run failed: {run.last_error}", file=sys.stderr)
                return f"Search failed: {run.last_error}"
            
            # Get the agent's response
            response_message = self.client.agents.list_messages(thread_id=thread.id).get_last_message_by_role(
                MessageRole.AGENT
            )
            
            result = ""
            if response_message:
                for text_message in response_message.text_messages:
                    result += text_message.text.value + "\n"
                
                # Include any citations
                for annotation in response_message.url_citation_annotations:
                    result += f"\nCitation: [{annotation.url_citation.title}]({annotation.url_citation.url})\n"
            
            # Clean up resources
            self.client.agents.delete_agent(agent.id)
            
            return result
        
        except Exception as e:
            print(f"Error during search: {str(e)}", file=sys.stderr)
            raise
    
    def web_search(self, query):
        """
        Perform a web search using Bing Web Grounding Tool.
        
        Args:
            query: The search query text
            
        Returns:
            Formatted search results from the web
        """
        print(f"Performing Bing Web search for: {query}", file=sys.stderr)
        
        try:
            # Get Bing connection
            bing_connection = self.client.connections.get(connection_name=self.bing_connection_name)
            if not bing_connection:
                raise ValueError(f"Connection '{self.bing_connection_name}' not found")
            
            # Initialize Bing Web Grounding Tool
            bing_tool = BingGroundingTool(connection_id=bing_connection.id)
            
            # Create agent with the Bing tool
            agent = self.client.agents.create_agent(
                model=self.model_deployment_name,
                name="web-search-agent",
                instructions=f"You are a helpful web search assistant. Use the Bing Web Grounding Tool to find the most current and accurate information for: '{query}'. Provide a comprehensive answer with citations to sources. Format your response as Markdown.",
                tools=bing_tool.definitions,
                headers={"x-ms-enable-preview": "true"}
            )
            
            # Create thread for communication
            thread = self.client.agents.create_thread()
            
            # Create message to thread
            self.client.agents.create_message(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=query
            )
            
            # Process the run
            run = self.client.agents.create_and_process_run(
                thread_id=thread.id,
                agent_id=agent.id
            )
            
            if run.status == "failed":
                print(f"Run failed: {run.last_error}", file=sys.stderr)
                return f"Web search failed: {run.last_error}"
            
            # Get the agent's response
            response_message = self.client.agents.list_messages(thread_id=thread.id).get_last_message_by_role(
                MessageRole.AGENT
            )
            
            result = ""
            if response_message:
                for text_message in response_message.text_messages:
                    result += text_message.text.value + "\n"
                
                # Include any citations
                for annotation in response_message.url_citation_annotations:
                    result += f"\nCitation: [{annotation.url_citation.title}]({annotation.url_citation.url})\n"
            
            # Clean up resources
            self.client.agents.delete_agent(agent.id)
            
            return result
        
        except Exception as e:
            print(f"Error during web search: {str(e)}", file=sys.stderr)
            raise

# Initialize Azure AI Agent client
try:
    print("Starting initialization of agent client...", file=sys.stderr)
    agent_client = AzureAIAgentClient()
    print("Agent client initialized successfully", file=sys.stderr)
except Exception as e:
    print(f"Error initializing agent client: {str(e)}", file=sys.stderr)
    # Don't exit - we'll handle errors in the tool functions
    agent_client = None

@mcp.tool()
def search_index(query: str, top: int = 5) -> str:
    """
    Search your Azure AI Search index using the optimal retrieval method.
    
    Args:
        query: The search query text
        top: Maximum number of results to return (default: 5)
    
    Returns:
        Formatted search results from your indexed documents
    """
    print(f"Tool called: search_index({query}, {top})", file=sys.stderr)
    if agent_client is None:
        return "Error: Azure AI Agent client is not initialized. Check server logs for details."
    
    try:
        results = agent_client.search_index(query, top)
        return f"## Azure AI Search Results\n\n{results}"
    except Exception as e:
        error_msg = f"Error performing index search: {str(e)}"
        print(error_msg, file=sys.stderr)
        return error_msg

@mcp.tool()
def web_search(query: str) -> str:
    """
    Search the web using Bing Web Grounding to find the most current information.
    
    Args:
        query: The search query text
    
    Returns:
        Formatted search results from the web with citations
    """
    print(f"Tool called: web_search({query})", file=sys.stderr)
    if agent_client is None:
        return "Error: Azure AI Agent client is not initialized. Check server logs for details."
    
    try:
        results = agent_client.web_search(query)
        return f"## Bing Web Search Results\n\n{results}"
    except Exception as e:
        error_msg = f"Error performing web search: {str(e)}"
        print(error_msg, file=sys.stderr)
        return error_msg

if __name__ == "__main__":
    # Run the server with stdio transport (default)
    print("Starting MCP server run...", file=sys.stderr)
    mcp.run()