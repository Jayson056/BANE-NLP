from mcp_tool import mcp_tool  
  
@mcp_tool(name="custom.hello_world", description="Test tool.")  
def hello_world(name: str = "User"):  
 return f"Hello, {name}!" 
