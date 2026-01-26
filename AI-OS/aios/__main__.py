"""
AIOS CLI Entry Point

Run the AIOS server from command line:
    python -m aios
    python -m aios --host 0.0.0.0 --port 8000
    python -m aios --config config/default.yaml
"""

import argparse
import asyncio
import logging
import os
import sys


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AIOS - LLM Agent Operating System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("AIOS_HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("AIOS_PORT", "8000")),
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.getenv("AIOS_CONFIG", "config/default.yaml"),
        help="Path to config file (default: config/default.yaml)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.getenv("AIOS_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("AIOS_RELOAD", "").lower() == "true",
        help="Enable auto-reload (development only)",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Set config path for app
    os.environ["AIOS_CONFIG"] = args.config
    
    # Run server
    import uvicorn
    
    uvicorn.run(
        "aios.server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()

