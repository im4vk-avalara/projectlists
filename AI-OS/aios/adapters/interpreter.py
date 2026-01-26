"""
Open Interpreter Compatibility Adapter

Provides a compatibility layer for Open Interpreter-style code
execution agents to run through AIOS.

Paper Reference: Section 3.2, Figure 9
External Reference: Open Interpreter project
"""

import asyncio
import logging
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from aios.adapters.base import (
    BaseAdapter,
    AdapterConfig,
    AgentStep,
    AgentResult,
)

logger = logging.getLogger(__name__)


INTERPRETER_SYSTEM_PROMPT = """You are a code interpreter assistant. You can write and execute code to help users.

When you need to run code, format it as:

```python
# Your code here
```

Or for shell commands:

```bash
# Your command here
```

After seeing the output, explain the results and continue if needed.

Important:
- Always explain what you're going to do before running code
- Handle errors gracefully
- Provide clear explanations of results
"""


class InterpreterAdapter(BaseAdapter):
    """
    Open Interpreter-style code execution adapter.
    
    Allows agents to write and execute code (Python, bash) to
    accomplish tasks, with all LLM calls routed through AIOS.
    
    Paper Reference: Section 3.2, Figure 9
    
    Example:
        adapter = InterpreterAdapter(kernel, safe_mode=True)
        result = await adapter.run("Calculate the first 10 fibonacci numbers")
    """
    
    # Code block patterns
    PYTHON_PATTERN = re.compile(r"```python\n(.*?)```", re.DOTALL)
    BASH_PATTERN = re.compile(r"```bash\n(.*?)```", re.DOTALL)
    
    def __init__(
        self,
        kernel,
        agent_id: Optional[str] = None,
        config: Optional[AdapterConfig] = None,
        safe_mode: bool = True,
        allowed_commands: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        super().__init__(kernel, agent_id, config)
        
        self.safe_mode = safe_mode
        self.allowed_commands = allowed_commands or ["ls", "cat", "echo", "pwd", "date"]
        self.timeout = timeout
        
        # Execution context
        self._python_globals: Dict[str, Any] = {}
        self._execution_count = 0
    
    async def run(self, task: str, **kwargs) -> AgentResult:
        """
        Execute the interpreter agent on a task.
        
        Args:
            task: The user's task/query
            **kwargs: Additional arguments
            
        Returns:
            AgentResult with output and execution trace
        """
        self._reset()
        self._python_globals = {}
        self._execution_count = 0
        
        # Build system prompt
        system_prompt = self.config.system_prompt or INTERPRETER_SYSTEM_PROMPT
        
        # Initialize conversation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        
        try:
            for iteration in range(self.config.max_iterations):
                # Get LLM response
                response = await self.chat(messages)
                content = response["content"]
                
                # Create step
                step = AgentStep(
                    step_number=iteration + 1,
                    thought=self._extract_explanation(content),
                )
                
                # Check for code blocks
                python_code = self.PYTHON_PATTERN.findall(content)
                bash_code = self.BASH_PATTERN.findall(content)
                
                if python_code:
                    step.action = "execute_python"
                    step.action_input = python_code[0]
                    
                    # Execute Python
                    output, error = await self._execute_python(python_code[0])
                    step.observation = output if output else f"Error: {error}"
                    
                    if error:
                        step.error = error
                    
                elif bash_code:
                    step.action = "execute_bash"
                    step.action_input = bash_code[0]
                    
                    # Execute bash
                    output, error = await self._execute_bash(bash_code[0])
                    step.observation = output if output else f"Error: {error}"
                    
                    if error:
                        step.error = error
                    
                else:
                    # No code, this might be the final answer
                    step.action = "respond"
                    step.observation = content
                    
                    # Check if this seems like a final answer
                    if self._is_final_answer(content):
                        step.is_final = True
                        self._add_step(step)
                        
                        return self._create_result(
                            success=True,
                            output=content,
                        )
                
                self._add_step(step)
                
                # Continue conversation with execution output
                messages.append({"role": "assistant", "content": content})
                
                if step.observation and step.action in ("execute_python", "execute_bash"):
                    messages.append({
                        "role": "user",
                        "content": f"Output:\n```\n{step.observation}\n```\n\nPlease continue or provide the final answer.",
                    })
            
            # Max iterations - return last response
            return self._create_result(
                success=True,
                output=self._steps[-1].observation if self._steps else "",
            )
            
        except Exception as e:
            logger.exception(f"Interpreter execution failed: {e}")
            return self._create_result(
                success=False,
                output="",
                error=str(e),
            )
    
    async def _execute_python(self, code: str) -> tuple:
        """Execute Python code."""
        self._execution_count += 1
        
        if self.safe_mode:
            # Restricted execution
            return await self._safe_execute_python(code)
        else:
            return await self._full_execute_python(code)
    
    async def _safe_execute_python(self, code: str) -> tuple:
        """Execute Python in restricted mode."""
        import io
        import sys
        
        # Capture output
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            # Restricted globals
            safe_globals = {
                "__builtins__": {
                    "print": print,
                    "len": len,
                    "range": range,
                    "str": str,
                    "int": int,
                    "float": float,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "sorted": sorted,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "abs": abs,
                    "round": round,
                    "pow": pow,
                    "True": True,
                    "False": False,
                    "None": None,
                },
            }
            safe_globals.update(self._python_globals)
            
            # Execute
            exec(code, safe_globals)
            
            # Update globals
            self._python_globals.update({
                k: v for k, v in safe_globals.items()
                if not k.startswith("_")
            })
            
            output = sys.stdout.getvalue()
            return output, None
            
        except Exception as e:
            return None, str(e)
            
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    async def _full_execute_python(self, code: str) -> tuple:
        """Execute Python with full access (unsafe)."""
        import io
        import sys
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            exec(code, self._python_globals)
            output = sys.stdout.getvalue()
            return output, None
        except Exception as e:
            return None, str(e)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    async def _execute_bash(self, code: str) -> tuple:
        """Execute bash command."""
        if self.safe_mode:
            # Check if command is allowed
            command = code.strip().split()[0] if code.strip() else ""
            if command not in self.allowed_commands:
                return None, f"Command '{command}' not allowed in safe mode"
        
        try:
            result = await asyncio.create_subprocess_shell(
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                result.communicate(),
                timeout=self.timeout,
            )
            
            output = stdout.decode() if stdout else ""
            error = stderr.decode() if stderr and result.returncode != 0 else None
            
            return output, error
            
        except asyncio.TimeoutError:
            return None, f"Command timed out after {self.timeout}s"
        except Exception as e:
            return None, str(e)
    
    def _extract_explanation(self, content: str) -> str:
        """Extract explanation text (non-code) from response."""
        # Remove code blocks
        text = self.PYTHON_PATTERN.sub("", content)
        text = self.BASH_PATTERN.sub("", text)
        return text.strip()[:200]
    
    def _is_final_answer(self, content: str) -> bool:
        """Check if this seems like a final answer."""
        # No code blocks and certain phrases
        has_code = bool(self.PYTHON_PATTERN.search(content) or self.BASH_PATTERN.search(content))
        
        if has_code:
            return False
        
        final_phrases = [
            "the answer is",
            "in conclusion",
            "the result is",
            "here's the answer",
            "to summarize",
            "the solution is",
        ]
        
        content_lower = content.lower()
        return any(phrase in content_lower for phrase in final_phrases)
    
    def _reset(self) -> None:
        """Reset execution state."""
        super()._reset()
        self._python_globals = {}
        self._execution_count = 0

