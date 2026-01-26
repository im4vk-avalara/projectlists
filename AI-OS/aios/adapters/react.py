"""
ReAct (Reasoning + Acting) Adapter

Implements the ReAct pattern where the agent alternates between
reasoning (thought) and acting (tool use) steps.

Paper Reference: Section 3.2, Figure 9
External Reference: "ReAct: Synergizing Reasoning and Acting in Language Models"
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from aios.adapters.base import (
    BaseAdapter,
    AdapterConfig,
    AgentStep,
    AgentResult,
)

logger = logging.getLogger(__name__)


REACT_SYSTEM_PROMPT = """You are a helpful AI assistant that can use tools to accomplish tasks.

You MUST follow this format for each step:

Thought: [Your reasoning about what to do next]
Action: [The action/tool to use]
Action Input: [The input for the action, as valid JSON]

When you have the final answer:

Thought: [Your final reasoning]
Action: Final Answer
Action Input: [Your final response to the user]

Available tools:
{tools}

Important:
- Always think before acting
- Use tools when needed
- Provide clear, helpful final answers
"""


class ReActAdapter(BaseAdapter):
    """
    ReAct (Reasoning + Acting) framework adapter.
    
    The ReAct pattern has the agent:
    1. Think about the current state
    2. Decide on an action
    3. Execute the action
    4. Observe the result
    5. Repeat until done
    
    Paper Reference: Section 3.2, Figure 9
    
    Example:
        adapter = ReActAdapter(kernel)
        result = await adapter.run("What is 25 * 4?")
        print(result.output)  # "100"
    """
    
    def __init__(
        self,
        kernel,
        agent_id: Optional[str] = None,
        config: Optional[AdapterConfig] = None,
    ):
        super().__init__(kernel, agent_id, config)
        
        # ReAct-specific patterns
        self._thought_pattern = re.compile(r"Thought:\s*(.+?)(?=Action:|$)", re.DOTALL)
        self._action_pattern = re.compile(r"Action:\s*(.+?)(?=Action Input:|$)", re.DOTALL)
        self._action_input_pattern = re.compile(r"Action Input:\s*(.+?)(?=Thought:|Observation:|$)", re.DOTALL)
    
    async def run(self, task: str, **kwargs) -> AgentResult:
        """
        Execute the ReAct agent on a task.
        
        Args:
            task: The user's task/query
            **kwargs: Additional arguments
            
        Returns:
            AgentResult with final answer and execution trace
        """
        self._reset()
        
        # Build system prompt with tools
        tools = await self._get_tool_descriptions()
        system_prompt = self.config.system_prompt or REACT_SYSTEM_PROMPT.format(tools=tools)
        
        # Initialize conversation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        
        # Save task to memory
        await self.save_memory("current_task", task)
        
        try:
            for iteration in range(self.config.max_iterations):
                # Get LLM response
                response = await self.chat(messages)
                content = response["content"]
                
                # Parse the response
                thought, action, action_input = self._parse_response(content)
                
                # Create step
                step = AgentStep(
                    step_number=iteration + 1,
                    thought=thought,
                    action=action,
                    action_input=action_input,
                )
                
                # Check if final answer
                if action.lower() == "final answer":
                    step.is_final = True
                    step.observation = str(action_input)
                    self._add_step(step)
                    
                    # Save result to memory
                    await self.save_memory("last_result", action_input)
                    
                    return self._create_result(
                        success=True,
                        output=str(action_input),
                    )
                
                # Execute action
                try:
                    observation = await self._execute_action(action, action_input)
                    step.observation = str(observation)
                except Exception as e:
                    step.observation = f"Error: {e}"
                    step.error = str(e)
                    
                    if self.config.stop_on_error:
                        self._add_step(step)
                        return self._create_result(
                            success=False,
                            output="",
                            error=str(e),
                        )
                
                self._add_step(step)
                
                # Add to conversation
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Observation: {step.observation}"})
            
            # Max iterations reached
            return self._create_result(
                success=False,
                output="",
                error=f"Max iterations ({self.config.max_iterations}) reached",
            )
            
        except Exception as e:
            logger.exception(f"ReAct execution failed: {e}")
            return self._create_result(
                success=False,
                output="",
                error=str(e),
            )
    
    def _parse_response(self, content: str) -> tuple:
        """Parse LLM response into thought, action, action_input."""
        thought = ""
        action = ""
        action_input = ""
        
        # Extract thought
        thought_match = self._thought_pattern.search(content)
        if thought_match:
            thought = thought_match.group(1).strip()
        
        # Extract action
        action_match = self._action_pattern.search(content)
        if action_match:
            action = action_match.group(1).strip()
        
        # Extract action input
        input_match = self._action_input_pattern.search(content)
        if input_match:
            action_input_raw = input_match.group(1).strip()
            
            # Try to parse as JSON
            try:
                action_input = json.loads(action_input_raw)
            except json.JSONDecodeError:
                action_input = action_input_raw
        
        return thought, action, action_input
    
    async def _execute_action(self, action: str, action_input: Any) -> Any:
        """Execute an action/tool."""
        action = action.strip().lower()
        
        # Map common action names to tools
        tool_name = action.replace(" ", "_")
        
        # Prepare parameters
        if isinstance(action_input, dict):
            params = action_input
        elif isinstance(action_input, str):
            # Try to parse as JSON
            try:
                params = json.loads(action_input)
            except json.JSONDecodeError:
                # Use as single parameter
                params = {"input": action_input}
        else:
            params = {"input": str(action_input)}
        
        # Call tool through AIOS
        try:
            result = await self.call_tool(tool_name, params)
            return result
        except Exception as e:
            # Try alternative tool names
            logger.debug(f"Tool '{tool_name}' failed, trying alternatives: {e}")
            raise
    
    async def _get_tool_descriptions(self) -> str:
        """Get formatted tool descriptions."""
        tools = await self.get_available_tools()
        
        if not tools:
            return "No tools available."
        
        descriptions = []
        for tool in tools:
            if isinstance(tool, dict):
                name = tool.get("name", tool.get("function", {}).get("name", "unknown"))
                desc = tool.get("description", tool.get("function", {}).get("description", ""))
                descriptions.append(f"- {name}: {desc}")
        
        return "\n".join(descriptions)

