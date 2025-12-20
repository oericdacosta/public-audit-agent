import os
import sys
from src.agents.analyst import AnalystAgent
from src.execution.sandbox import DockerSandbox

def test_docker_flow():
    print("--- Starting Docker Verification ---")
    
    # 1. Check Environment
    print(f"DOCKER_NETWORK_NAME: {os.environ.get('DOCKER_NETWORK_NAME')}")
    print(f"MCP_HOST: {os.environ.get('MCP_HOST')}")
    
    # 2. Define Code to Run
    # Simple code that tests DB connection via shim
    code = """
print("Hello from Sandbox!")
tables = list_tables()
print(f"Tables found: {tables}")
"""
    
    # 3. Execute in Sandbox
    try:
        sandbox = DockerSandbox()
        print("Spawning Sandbox container...")
        result = sandbox.execute(code)
        
        print("\n--- Execution Result ---")
        print(result)
        print("------------------------")
        
        if "Tables found" in result:
            print("SUCCESS: Sandbox communicated with MCP Server!")
        else:
            print("FAILURE: Did not receive expected output.")
            sys.exit(1)
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    test_docker_flow()
