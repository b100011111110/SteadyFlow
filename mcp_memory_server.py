import os
from typing import List, Dict
from mcp.server.fastmcp import FastMCP
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Create an MCP server for memory and text splitting
mcp = FastMCP("SteadyFlow Memory")

# Temporary storage for chunks
# In a real app, this might be a vector DB or a local file
storage: Dict[str, List[str]] = {}

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=100,
    separators=["\n\n", "\n", " ", ""]
)

@mcp.tool()
async def store_long_text(key: str, text: str) -> str:
    """Split a long text into chunks and store it for later retrieval."""
    chunks = splitter.split_text(text)
    storage[key] = chunks
    return f"Stored {len(chunks)} chunks under key '{key}'."

@mcp.tool()
async def retrieve_info(key: str, chunk_index: int = 0) -> str:
    """Retrieve a specific chunk of information by key and index."""
    if key not in storage:
        return f"Error: Key '{key}' not found."
    
    chunks = storage[key]
    if chunk_index < 0 or chunk_index >= len(chunks):
        return f"Error: Index {chunk_index} out of range (0-{len(chunks)-1})."
    
    return f"Chunk {chunk_index+1}/{len(chunks)} for '{key}':\n\n{chunks[chunk_index]}"

@mcp.tool()
async def search_memory(query: str) -> str:
    """Search through all stored information for a keyword."""
    results = []
    for key, chunks in storage.items():
        for i, chunk in enumerate(chunks):
            if query.lower() in chunk.lower():
                results.append(f"Key: {key}, Chunk: {i}")
    
    if not results:
        return f"No results found for '{query}'."
    
    return "Search Results:\n" + "\n".join(results[:10])

if __name__ == "__main__":
    mcp.run()
