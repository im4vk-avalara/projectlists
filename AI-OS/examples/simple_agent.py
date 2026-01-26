"""
Simple AIOS Agent Example

Demonstrates basic usage of the AIOS SDK.

Usage:
    # First, start the AIOS server:
    python -m aios
    
    # Then run this example:
    python examples/simple_agent.py
"""

import asyncio
import logging
from aios.sdk.client import AIOSClient
from aios.kernel.aios_kernel import AIOSKernel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_local_agent():
    """
    Run agent with local kernel (in-process).
    No server needed.
    """
    logger.info("Starting local AIOS kernel...")
    
    # Create and start kernel
    kernel = AIOSKernel()
    await kernel.start()
    
    # Create client connected to local kernel
    client = AIOSClient(kernel=kernel, agent_id="simple-agent")
    
    try:
        # Simple chat
        logger.info("Sending chat request...")
        response = await client.chat([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! What can you help me with?"},
        ])
        
        logger.info(f"Response: {response.content}")
        logger.info(f"Status: {response.status}")
        
        # Memory operations
        logger.info("\n--- Memory Operations ---")
        
        # Write to memory
        await client.memory_write("user_preference", {"theme": "dark"})
        logger.info("Wrote user_preference to memory")
        
        # Read from memory
        mem_response = await client.memory_read("user_preference")
        logger.info(f"Read user_preference: {mem_response.data}")
        
        # List keys
        await client.memory_write("another_key", "value")
        list_response = await client.memory_list()
        logger.info(f"Memory keys: {list_response.keys}")
        
        # Get kernel stats
        logger.info("\n--- Kernel Stats ---")
        stats = kernel.get_stats()
        logger.info(f"LLM Cores: {stats['llm_manager']['total_cores']}")
        logger.info(f"Scheduler: {stats['scheduler']['strategy']}")
        logger.info(f"Completed syscalls: {stats['scheduler']['completed_syscalls']}")
        
    finally:
        await client.close()
        await kernel.stop()
        logger.info("Kernel stopped")


async def run_remote_agent():
    """
    Run agent connecting to remote AIOS server.
    Requires server to be running on localhost:8000.
    """
    logger.info("Connecting to remote AIOS server...")
    
    async with AIOSClient(
        base_url="http://localhost:8000",
        agent_id="remote-agent"
    ) as client:
        # Chat
        response = await client.chat([
            {"role": "user", "content": "Hello from remote agent!"},
        ])
        
        logger.info(f"Response: {response.content}")


async def multi_turn_conversation():
    """
    Demonstrate multi-turn conversation with memory.
    """
    logger.info("Starting multi-turn conversation demo...")
    
    kernel = AIOSKernel()
    await kernel.start()
    
    client = AIOSClient(kernel=kernel, agent_id="conv-agent")
    
    try:
        conversation = []
        
        # Turn 1
        conversation.append({"role": "user", "content": "My name is Alice."})
        response = await client.chat(conversation)
        conversation.append({"role": "assistant", "content": response.content})
        logger.info(f"Turn 1 - User: My name is Alice.")
        logger.info(f"Turn 1 - Assistant: {response.content}")
        
        # Store name in memory
        await client.memory_write("user_name", "Alice")
        
        # Turn 2
        conversation.append({"role": "user", "content": "What's the weather like?"})
        response = await client.chat(conversation)
        conversation.append({"role": "assistant", "content": response.content})
        logger.info(f"Turn 2 - User: What's the weather like?")
        logger.info(f"Turn 2 - Assistant: {response.content}")
        
        # Recall from memory
        name_response = await client.memory_read("user_name")
        logger.info(f"\nRecalled from memory: user_name = {name_response.data}")
        
    finally:
        await client.close()
        await kernel.stop()


def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--remote":
        asyncio.run(run_remote_agent())
    elif len(sys.argv) > 1 and sys.argv[1] == "--conversation":
        asyncio.run(multi_turn_conversation())
    else:
        asyncio.run(run_local_agent())


if __name__ == "__main__":
    main()

