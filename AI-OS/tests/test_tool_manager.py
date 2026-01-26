"""
Tests for Tool Manager

Paper Reference: Section 3.7
"""

import pytest
import asyncio

from aios.kernel.tool_manager import (
    ToolManager,
    Tool,
    ToolParameter,
)


class TestToolParameter:
    """Tests for ToolParameter class."""
    
    def test_create_parameter(self):
        """Test creating a parameter."""
        param = ToolParameter(
            name="expression",
            type="string",
            description="Math expression",
            required=True,
        )
        
        assert param.name == "expression"
        assert param.type == "string"
        assert param.required is True
    
    def test_to_dict(self):
        """Test serialization."""
        param = ToolParameter(
            name="count",
            type="number",
            description="Count",
            required=False,
            default=10,
        )
        
        data = param.to_dict()
        
        assert data["name"] == "count"
        assert data["default"] == 10


class TestToolManager:
    """Tests for ToolManager class."""
    
    @pytest.fixture
    def tool_mgr(self) -> ToolManager:
        """Create tool manager."""
        return ToolManager(default_max_instances=2, timeout_seconds=5)
    
    @pytest.mark.asyncio
    async def test_register_tool(self, tool_mgr: ToolManager):
        """Test registering a tool."""
        async def my_tool(x: int) -> int:
            return x * 2
        
        tool = await tool_mgr.register_tool(
            name="double",
            description="Doubles a number",
            function=my_tool,
            parameters=[ToolParameter("x", "number", "Input number")],
        )
        
        assert tool.name == "double"
        assert tool_mgr.get_tool("double") is not None
    
    @pytest.mark.asyncio
    async def test_call_tool(self, tool_mgr: ToolManager):
        """Test calling a tool."""
        async def adder(a: int, b: int) -> int:
            return a + b
        
        await tool_mgr.register_tool(
            name="add",
            description="Adds two numbers",
            function=adder,
            parameters=[
                ToolParameter("a", "number", "First number"),
                ToolParameter("b", "number", "Second number"),
            ],
        )
        
        result = await tool_mgr.call("agent-1", "add", {"a": 5, "b": 3})
        
        assert result == 8
    
    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self, tool_mgr: ToolManager):
        """Test calling non-existent tool."""
        with pytest.raises(ValueError, match="not found"):
            await tool_mgr.call("agent-1", "nonexistent", {})
    
    @pytest.mark.asyncio
    async def test_parameter_validation(self, tool_mgr: ToolManager):
        """Test parameter validation."""
        async def my_tool(name: str) -> str:
            return f"Hello {name}"
        
        await tool_mgr.register_tool(
            name="greet",
            description="Greets",
            function=my_tool,
            parameters=[ToolParameter("name", "string", "Name", required=True)],
        )
        
        # Missing required parameter
        with pytest.raises(ValueError, match="validation failed"):
            await tool_mgr.call("agent-1", "greet", {})
    
    @pytest.mark.asyncio
    async def test_max_instances(self, tool_mgr: ToolManager):
        """Test max instances limit."""
        call_count = 0
        
        async def slow_tool() -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.5)
            return "done"
        
        await tool_mgr.register_tool(
            name="slow",
            description="Slow tool",
            function=slow_tool,
            max_instances=1,
        )
        
        # Start first call
        task1 = asyncio.create_task(tool_mgr.call("agent-1", "slow", {}))
        await asyncio.sleep(0.1)  # Let it start
        
        # Second call should fail
        with pytest.raises(RuntimeError, match="max instances"):
            await tool_mgr.call("agent-2", "slow", {})
        
        # Wait for first to complete
        await task1
    
    @pytest.mark.asyncio
    async def test_list_tools(self, tool_mgr: ToolManager):
        """Test listing tools."""
        async def tool1(): return 1
        async def tool2(): return 2
        
        await tool_mgr.register_tool("tool1", "Tool 1", tool1, category="cat1")
        await tool_mgr.register_tool("tool2", "Tool 2", tool2, category="cat2")
        
        all_tools = tool_mgr.list_tools()
        assert len(all_tools) == 2
        
        cat1_tools = tool_mgr.list_tools(category="cat1")
        assert len(cat1_tools) == 1
    
    @pytest.mark.asyncio
    async def test_tool_schemas(self, tool_mgr: ToolManager):
        """Test getting OpenAI-compatible schemas."""
        async def calculator(expression: str) -> str:
            return str(eval(expression))
        
        await tool_mgr.register_tool(
            name="calc",
            description="Calculator",
            function=calculator,
            parameters=[ToolParameter("expression", "string", "Math expr")],
        )
        
        schemas = tool_mgr.get_tool_schemas()
        
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "calc"
    
    @pytest.mark.asyncio
    async def test_decorator_registration(self, tool_mgr: ToolManager):
        """Test decorator-based registration."""
        @tool_mgr.register(
            name="decorated",
            description="A decorated tool",
        )
        async def my_tool() -> str:
            return "result"
        
        tool = tool_mgr.get_tool("decorated")
        assert tool is not None
        
        result = await tool_mgr.call("agent-1", "decorated", {})
        assert result == "result"
    
    @pytest.mark.asyncio
    async def test_stats(self, tool_mgr: ToolManager):
        """Test getting stats."""
        async def my_tool() -> int:
            return 42
        
        await tool_mgr.register_tool("test", "Test", my_tool)
        await tool_mgr.call("agent-1", "test", {})
        
        stats = tool_mgr.get_stats()
        
        assert stats["registered_tools"] == 1
        assert stats["total_executions"] == 1

