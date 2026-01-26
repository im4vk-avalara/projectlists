"""
Reflexion Adapter

Implements the Reflexion pattern where the agent can reflect on its
actions and improve through self-evaluation.

Paper Reference: Section 3.2, Figure 9
External Reference: "Reflexion: Language Agents with Verbal Reinforcement Learning"
"""

import logging
from typing import Any, Dict, List, Optional

from aios.adapters.base import (
    BaseAdapter,
    AdapterConfig,
    AgentStep,
    AgentResult,
)
from aios.adapters.react import ReActAdapter

logger = logging.getLogger(__name__)


REFLEXION_SYSTEM_PROMPT = """You are a helpful AI assistant that learns from experience.

You will be given a task and should try to solve it. After each attempt,
you will reflect on what went well and what could be improved.

{react_instructions}

After completing your attempt, you will receive feedback and can try again
with improved strategy based on your reflection.
"""


REFLECTION_PROMPT = """Based on your previous attempt at the task, please reflect:

Task: {task}

Your previous attempt:
{attempt_summary}

Result: {result}
{error_info}

Please analyze:
1. What went well in your approach?
2. What mistakes did you make?
3. How would you approach this differently next time?

Reflection:"""


class ReflexionAdapter(BaseAdapter):
    """
    Reflexion framework adapter.
    
    The Reflexion pattern adds self-reflection to the reasoning process:
    1. Attempt the task (using ReAct-style reasoning)
    2. Evaluate the result
    3. Reflect on what could be improved
    4. Retry with improved strategy
    
    Paper Reference: Section 3.2, Figure 9
    
    Example:
        adapter = ReflexionAdapter(kernel, max_retries=3)
        result = await adapter.run("Solve this complex problem...")
    """
    
    def __init__(
        self,
        kernel,
        agent_id: Optional[str] = None,
        config: Optional[AdapterConfig] = None,
        max_retries: int = 3,
        reflection_enabled: bool = True,
    ):
        super().__init__(kernel, agent_id, config)
        
        self.max_retries = max_retries
        self.reflection_enabled = reflection_enabled
        
        # Use ReAct as the base reasoning engine
        self._react = ReActAdapter(kernel, agent_id, config)
        
        # Track reflections
        self._reflections: List[str] = []
        self._attempts: List[AgentResult] = []
    
    async def run(self, task: str, **kwargs) -> AgentResult:
        """
        Execute the Reflexion agent on a task.
        
        Args:
            task: The user's task/query
            **kwargs: Additional arguments
            
        Returns:
            AgentResult with final answer and all attempts
        """
        self._reset()
        self._reflections = []
        self._attempts = []
        
        # Initial context
        context = ""
        
        for attempt_num in range(self.max_retries):
            logger.info(f"Reflexion attempt {attempt_num + 1}/{self.max_retries}")
            
            # Build enhanced task with reflections
            enhanced_task = self._build_enhanced_task(task, context)
            
            # Run ReAct attempt
            result = await self._react.run(enhanced_task, **kwargs)
            self._attempts.append(result)
            
            # Copy steps to our trace
            for step in result.steps:
                step.step_number = len(self._steps) + 1
                self._add_step(step)
            
            self._total_tokens += result.total_tokens
            
            # Check if successful
            if result.success:
                # Verify the result (could add external validation here)
                is_valid = await self._validate_result(task, result)
                
                if is_valid:
                    return self._create_result(
                        success=True,
                        output=result.output,
                    )
            
            # Generate reflection if not the last attempt
            if self.reflection_enabled and attempt_num < self.max_retries - 1:
                reflection = await self._generate_reflection(task, result)
                self._reflections.append(reflection)
                context = self._build_reflection_context()
                
                # Save reflection to memory
                await self.save_memory(
                    f"reflection_{attempt_num}",
                    {"reflection": reflection, "attempt": result.to_dict()},
                )
        
        # Return best attempt
        best_attempt = self._select_best_attempt()
        return self._create_result(
            success=best_attempt.success if best_attempt else False,
            output=best_attempt.output if best_attempt else "",
            error=f"Failed after {self.max_retries} attempts",
        )
    
    def _build_enhanced_task(self, original_task: str, context: str) -> str:
        """Build enhanced task with reflection context."""
        if not context:
            return original_task
        
        return f"""Task: {original_task}

Previous attempts and reflections:
{context}

Please try again, taking into account the lessons learned from previous attempts."""
    
    def _build_reflection_context(self) -> str:
        """Build context from all reflections."""
        if not self._reflections:
            return ""
        
        context_parts = []
        for i, reflection in enumerate(self._reflections):
            context_parts.append(f"Attempt {i + 1} reflection:\n{reflection}")
        
        return "\n\n".join(context_parts)
    
    async def _generate_reflection(self, task: str, result: AgentResult) -> str:
        """Generate a reflection on the attempt."""
        # Summarize the attempt
        attempt_summary = self._summarize_attempt(result)
        
        # Build reflection prompt
        error_info = f"\nError: {result.error}" if result.error else ""
        prompt = REFLECTION_PROMPT.format(
            task=task,
            attempt_summary=attempt_summary,
            result="Success" if result.success else "Failed",
            error_info=error_info,
        )
        
        # Get reflection from LLM
        response = await self.chat([
            {"role": "user", "content": prompt}
        ])
        
        return response["content"]
    
    def _summarize_attempt(self, result: AgentResult) -> str:
        """Summarize an attempt for reflection."""
        if not result.steps:
            return "No steps taken."
        
        summary_parts = []
        for step in result.steps[:5]:  # Limit to first 5 steps
            summary_parts.append(
                f"Step {step.step_number}: {step.action}"
                + (f" -> {step.observation[:100]}..." if step.observation else "")
            )
        
        if len(result.steps) > 5:
            summary_parts.append(f"... and {len(result.steps) - 5} more steps")
        
        if result.output:
            summary_parts.append(f"Output: {result.output[:200]}...")
        
        return "\n".join(summary_parts)
    
    async def _validate_result(self, task: str, result: AgentResult) -> bool:
        """Validate that the result actually solves the task."""
        # Simple validation - could be enhanced with external checks
        if not result.success:
            return False
        
        if not result.output or result.output.strip() == "":
            return False
        
        return True
    
    def _select_best_attempt(self) -> Optional[AgentResult]:
        """Select the best attempt from all tries."""
        if not self._attempts:
            return None
        
        # Prefer successful attempts
        successful = [a for a in self._attempts if a.success]
        if successful:
            # Return the one with most steps (likely most thorough)
            return max(successful, key=lambda a: len(a.steps))
        
        # Return the one with most progress
        return max(self._attempts, key=lambda a: len(a.steps))
    
    def _reset(self) -> None:
        """Reset execution state."""
        super()._reset()
        self._react._reset()

