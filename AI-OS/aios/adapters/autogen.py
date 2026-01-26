"""
AutoGen Compatibility Adapter

Provides a compatibility layer for Microsoft AutoGen-style multi-agent
conversations to run through AIOS.

Paper Reference: Section 3.2, Figure 9
External Reference: Microsoft AutoGen framework
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from aios.adapters.base import (
    BaseAdapter,
    AdapterConfig,
    AgentStep,
    AgentResult,
)

logger = logging.getLogger(__name__)


@dataclass
class AutoGenAgentConfig:
    """Configuration for an AutoGen-style agent."""
    name: str
    system_message: str = ""
    human_input_mode: str = "NEVER"  # NEVER, ALWAYS, TERMINATE
    max_consecutive_auto_reply: int = 10
    is_termination_msg: Optional[Callable[[str], bool]] = None
    llm_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationMessage:
    """A message in the multi-agent conversation."""
    sender: str
    receiver: str
    content: str
    role: str = "assistant"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "content": self.content,
            "role": self.role,
        }


class AutoGenAgent:
    """
    An AutoGen-compatible agent that uses AIOS.
    
    This is a simplified implementation that captures the core
    AutoGen patterns while routing all LLM calls through AIOS.
    """
    
    def __init__(
        self,
        config: AutoGenAgentConfig,
        adapter: "AutoGenAdapter",
    ):
        self.config = config
        self.adapter = adapter
        self.name = config.name
        self._message_history: List[ConversationMessage] = []
    
    async def generate_reply(
        self,
        messages: List[ConversationMessage],
        sender: Optional["AutoGenAgent"] = None,
    ) -> str:
        """Generate a reply to the conversation."""
        # Build messages for LLM
        llm_messages = []
        
        # Add system message
        if self.config.system_message:
            llm_messages.append({
                "role": "system",
                "content": self.config.system_message,
            })
        
        # Add conversation history
        for msg in messages:
            role = "user" if msg.sender != self.name else "assistant"
            llm_messages.append({
                "role": role,
                "content": f"[{msg.sender}]: {msg.content}",
            })
        
        # Get response through AIOS
        response = await self.adapter.chat(llm_messages)
        
        return response["content"]
    
    def receive(self, message: ConversationMessage) -> None:
        """Receive a message."""
        self._message_history.append(message)
    
    def is_termination_msg(self, content: str) -> bool:
        """Check if this is a termination message."""
        if self.config.is_termination_msg:
            return self.config.is_termination_msg(content)
        
        # Default: check for common termination signals
        content_lower = content.lower()
        return any(term in content_lower for term in [
            "terminate",
            "task completed",
            "goodbye",
            "done",
        ])


class AutoGenAdapter(BaseAdapter):
    """
    AutoGen multi-agent conversation adapter.
    
    Allows AutoGen-style multi-agent conversations where multiple
    agents take turns speaking, with all LLM calls routed through AIOS.
    
    Paper Reference: Section 3.2, Figure 9
    
    Example:
        adapter = AutoGenAdapter(kernel)
        
        # Create agents
        assistant = adapter.create_agent(
            name="assistant",
            system_message="You are a helpful assistant.",
        )
        user_proxy = adapter.create_agent(
            name="user_proxy",
            human_input_mode="NEVER",
        )
        
        # Start conversation
        result = await adapter.initiate_chat(
            sender=user_proxy,
            receiver=assistant,
            message="Help me plan a project",
        )
    """
    
    def __init__(
        self,
        kernel,
        agent_id: Optional[str] = None,
        config: Optional[AdapterConfig] = None,
    ):
        super().__init__(kernel, agent_id, config)
        
        self._agents: Dict[str, AutoGenAgent] = {}
        self._conversation: List[ConversationMessage] = []
    
    def create_agent(
        self,
        name: str,
        system_message: str = "",
        human_input_mode: str = "NEVER",
        max_consecutive_auto_reply: int = 10,
        is_termination_msg: Optional[Callable[[str], bool]] = None,
        **kwargs,
    ) -> AutoGenAgent:
        """
        Create an AutoGen-style agent.
        
        Args:
            name: Agent name
            system_message: System prompt for the agent
            human_input_mode: When to request human input
            max_consecutive_auto_reply: Max auto-replies
            is_termination_msg: Function to detect termination
            
        Returns:
            AutoGenAgent instance
        """
        config = AutoGenAgentConfig(
            name=name,
            system_message=system_message,
            human_input_mode=human_input_mode,
            max_consecutive_auto_reply=max_consecutive_auto_reply,
            is_termination_msg=is_termination_msg,
            llm_config=kwargs.get("llm_config", {}),
        )
        
        agent = AutoGenAgent(config, self)
        self._agents[name] = agent
        
        return agent
    
    async def initiate_chat(
        self,
        sender: AutoGenAgent,
        receiver: AutoGenAgent,
        message: str,
        max_turns: Optional[int] = None,
    ) -> AgentResult:
        """
        Initiate a multi-agent conversation.
        
        Args:
            sender: Agent sending the initial message
            receiver: Agent receiving the initial message
            message: Initial message
            max_turns: Maximum conversation turns
            
        Returns:
            AgentResult with conversation history
        """
        self._reset()
        self._conversation = []
        
        max_turns = max_turns or self.config.max_iterations
        
        # Initial message
        initial_msg = ConversationMessage(
            sender=sender.name,
            receiver=receiver.name,
            content=message,
            role="user",
        )
        self._conversation.append(initial_msg)
        receiver.receive(initial_msg)
        
        # Track current speaker
        current_sender = receiver
        current_receiver = sender
        
        try:
            for turn in range(max_turns):
                # Generate reply
                reply = await current_sender.generate_reply(
                    self._conversation,
                    sender=current_receiver,
                )
                
                # Create message
                msg = ConversationMessage(
                    sender=current_sender.name,
                    receiver=current_receiver.name,
                    content=reply,
                )
                self._conversation.append(msg)
                current_receiver.receive(msg)
                
                # Create step
                step = AgentStep(
                    step_number=turn + 1,
                    action=f"{current_sender.name} -> {current_receiver.name}",
                    observation=reply[:200] + "..." if len(reply) > 200 else reply,
                )
                self._add_step(step)
                
                # Check for termination
                if current_sender.is_termination_msg(reply):
                    step.is_final = True
                    return self._create_result(
                        success=True,
                        output=self._format_conversation(),
                    )
                
                # Swap speakers
                current_sender, current_receiver = current_receiver, current_sender
            
            # Max turns reached
            return self._create_result(
                success=True,
                output=self._format_conversation(),
            )
            
        except Exception as e:
            logger.exception(f"AutoGen conversation failed: {e}")
            return self._create_result(
                success=False,
                output=self._format_conversation(),
                error=str(e),
            )
    
    async def run(self, task: str, **kwargs) -> AgentResult:
        """
        Run a simple two-agent conversation.
        
        Creates a user proxy and assistant agent automatically.
        """
        # Create default agents
        user_proxy = self.create_agent(
            name="user_proxy",
            system_message="You are a user proxy. Convey user requests clearly.",
        )
        
        assistant = self.create_agent(
            name="assistant",
            system_message=(
                "You are a helpful AI assistant. "
                "When you have completed the task, say 'TERMINATE'."
            ),
            is_termination_msg=lambda x: "terminate" in x.lower(),
        )
        
        return await self.initiate_chat(
            sender=user_proxy,
            receiver=assistant,
            message=task,
        )
    
    def _format_conversation(self) -> str:
        """Format the conversation as a string."""
        lines = []
        for msg in self._conversation:
            lines.append(f"[{msg.sender}]: {msg.content}")
        return "\n\n".join(lines)
    
    def _reset(self) -> None:
        """Reset execution state."""
        super()._reset()
        self._conversation = []
        for agent in self._agents.values():
            agent._message_history = []

