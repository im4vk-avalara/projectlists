"""
Tests for Agent Framework Adapters

Paper Reference: Section 3.2, Figure 9
"""

import pytest
import asyncio
import tempfile

from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
from aios.adapters.base import BaseAdapter, AdapterConfig, AgentStep, AgentResult
from aios.adapters.react import ReActAdapter
from aios.adapters.reflexion import ReflexionAdapter
from aios.adapters.autogen import AutoGenAdapter
from aios.adapters.interpreter import InterpreterAdapter


class TestBaseAdapter:
    """Tests for base adapter functionality."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                storage_root=tmpdir,
                auto_approve_confirmations=True,
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_adapter_creation(self, kernel: AIOSKernel):
        """Test creating an adapter."""
        adapter = ReActAdapter(kernel, agent_id="test-agent")
        
        assert adapter.agent_id == "test-agent"
        assert adapter.kernel == kernel
        assert adapter.client is not None
    
    @pytest.mark.asyncio
    async def test_adapter_chat(self, kernel: AIOSKernel):
        """Test chat through adapter."""
        adapter = ReActAdapter(kernel)
        
        response = await adapter.chat([
            {"role": "user", "content": "Hello!"}
        ])
        
        assert "content" in response
        assert response["content"] is not None
    
    @pytest.mark.asyncio
    async def test_adapter_memory(self, kernel: AIOSKernel):
        """Test memory operations through adapter."""
        adapter = ReActAdapter(kernel)
        
        # Save
        await adapter.save_memory("test_key", {"value": 42})
        
        # Load
        value = await adapter.load_memory("test_key")
        
        assert value == {"value": 42}
    
    @pytest.mark.asyncio
    async def test_adapter_tools(self, kernel: AIOSKernel):
        """Test getting available tools."""
        adapter = ReActAdapter(kernel)
        
        tools = await adapter.get_available_tools()
        
        # Built-in tools should be available
        tool_names = [t.get("name") or t.get("function", {}).get("name") for t in tools]
        assert "calculator" in tool_names


class TestReActAdapter:
    """Tests for ReAct adapter."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                storage_root=tmpdir,
                auto_approve_confirmations=True,
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_react_run(self, kernel: AIOSKernel):
        """Test running ReAct agent."""
        config = AdapterConfig(max_iterations=3, verbose=False)
        adapter = ReActAdapter(kernel, config=config)
        
        result = await adapter.run("What is the current time?")
        
        assert isinstance(result, AgentResult)
        assert result.iterations > 0
    
    @pytest.mark.asyncio
    async def test_react_parse_response(self, kernel: AIOSKernel):
        """Test parsing ReAct-style responses."""
        adapter = ReActAdapter(kernel)
        
        response = """Thought: I need to calculate this.
Action: calculator
Action Input: {"expression": "2+2"}"""
        
        thought, action, action_input = adapter._parse_response(response)
        
        assert "calculate" in thought.lower()
        assert action == "calculator"
        assert action_input == {"expression": "2+2"}
    
    @pytest.mark.asyncio
    async def test_react_final_answer(self, kernel: AIOSKernel):
        """Test parsing final answer."""
        adapter = ReActAdapter(kernel)
        
        response = """Thought: I have the answer now.
Action: Final Answer
Action Input: The result is 42."""
        
        thought, action, action_input = adapter._parse_response(response)
        
        assert action.lower() == "final answer"


class TestReflexionAdapter:
    """Tests for Reflexion adapter."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                storage_root=tmpdir,
                auto_approve_confirmations=True,
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_reflexion_run(self, kernel: AIOSKernel):
        """Test running Reflexion agent."""
        config = AdapterConfig(max_iterations=2, verbose=False)
        adapter = ReflexionAdapter(
            kernel,
            config=config,
            max_retries=1,
            reflection_enabled=False,  # Faster test
        )
        
        result = await adapter.run("Say hello")
        
        assert isinstance(result, AgentResult)
    
    @pytest.mark.asyncio
    async def test_reflexion_with_reflection(self, kernel: AIOSKernel):
        """Test Reflexion with reflection enabled."""
        config = AdapterConfig(max_iterations=2)
        adapter = ReflexionAdapter(
            kernel,
            config=config,
            max_retries=2,
            reflection_enabled=True,
        )
        
        # This will attempt the task and potentially reflect
        result = await adapter.run("What is 2+2?")
        
        assert isinstance(result, AgentResult)


class TestAutoGenAdapter:
    """Tests for AutoGen adapter."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                storage_root=tmpdir,
                auto_approve_confirmations=True,
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_autogen_create_agent(self, kernel: AIOSKernel):
        """Test creating AutoGen-style agents."""
        adapter = AutoGenAdapter(kernel)
        
        agent = adapter.create_agent(
            name="assistant",
            system_message="You are helpful.",
        )
        
        assert agent.name == "assistant"
        assert agent.config.system_message == "You are helpful."
    
    @pytest.mark.asyncio
    async def test_autogen_simple_run(self, kernel: AIOSKernel):
        """Test simple AutoGen run."""
        config = AdapterConfig(max_iterations=3)
        adapter = AutoGenAdapter(kernel, config=config)
        
        result = await adapter.run("Say hello and then TERMINATE")
        
        assert isinstance(result, AgentResult)
    
    @pytest.mark.asyncio
    async def test_autogen_conversation(self, kernel: AIOSKernel):
        """Test multi-agent conversation."""
        config = AdapterConfig(max_iterations=3)
        adapter = AutoGenAdapter(kernel, config=config)
        
        user = adapter.create_agent(
            name="user",
            system_message="You are a user asking questions.",
        )
        
        assistant = adapter.create_agent(
            name="assistant",
            system_message="You are helpful. Say TERMINATE when done.",
            is_termination_msg=lambda x: "terminate" in x.lower(),
        )
        
        result = await adapter.initiate_chat(
            sender=user,
            receiver=assistant,
            message="Hello! Please respond and then say TERMINATE.",
            max_turns=3,
        )
        
        assert len(adapter._conversation) >= 2


class TestInterpreterAdapter:
    """Tests for Interpreter adapter."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                storage_root=tmpdir,
                auto_approve_confirmations=True,
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_interpreter_safe_python(self, kernel: AIOSKernel):
        """Test safe Python execution."""
        adapter = InterpreterAdapter(kernel, safe_mode=True)
        
        output, error = await adapter._execute_python("print(2 + 2)")
        
        assert "4" in output
        assert error is None
    
    @pytest.mark.asyncio
    async def test_interpreter_safe_restrictions(self, kernel: AIOSKernel):
        """Test that unsafe operations are blocked."""
        adapter = InterpreterAdapter(kernel, safe_mode=True)
        
        # Importing should fail in safe mode
        output, error = await adapter._execute_python("import os")
        
        assert error is not None
    
    @pytest.mark.asyncio
    async def test_interpreter_bash(self, kernel: AIOSKernel):
        """Test bash execution."""
        adapter = InterpreterAdapter(kernel, safe_mode=True)
        
        output, error = await adapter._execute_bash("echo hello")
        
        assert "hello" in output
        assert error is None
    
    @pytest.mark.asyncio
    async def test_interpreter_bash_restrictions(self, kernel: AIOSKernel):
        """Test that disallowed commands are blocked."""
        adapter = InterpreterAdapter(kernel, safe_mode=True, allowed_commands=["echo"])
        
        output, error = await adapter._execute_bash("rm -rf /")
        
        assert error is not None
        assert "not allowed" in error
    
    @pytest.mark.asyncio
    async def test_interpreter_run(self, kernel: AIOSKernel):
        """Test running interpreter agent."""
        config = AdapterConfig(max_iterations=2)
        adapter = InterpreterAdapter(kernel, config=config, safe_mode=True)
        
        result = await adapter.run("What is 5 + 5?")
        
        assert isinstance(result, AgentResult)

