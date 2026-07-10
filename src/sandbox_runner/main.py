import os
import argparse
from sandbox_runner.server import mcp

def main():
    parser=argparse.ArgumentParser(
        prog="sandbox-runner",
        description="SandboxRunner — MCP server that executes Python and C++ code in isolated Docker containers.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport to use for MCP communication"
    )   
    args=parser.parse_args()
    mcp.run(transport=args.transport)

if __name__ == "__main__":
    main()
