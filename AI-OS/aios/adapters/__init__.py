"""
AIOS Agent Framework Adapters

Provides compatibility layers for popular agent frameworks to use AIOS
as their backend infrastructure.

Paper Reference: Section 3.2, Figure 9
Spec Reference: Architecture.md (Agent Framework Adapters)

Supported Frameworks:
- ReAct: Reasoning + Acting pattern
- Reflexion: Self-reflection and refinement
- AutoGen: Multi-agent conversation
- Open-Interpreter: Code execution agent
- MetaGPT: Software development agents

Usage:
    from aios.adapters import ReActAdapter
    
    adapter = ReActAdapter(kernel)
    result = await adapter.run("Plan a trip to Paris")
"""

from aios.adapters.base import BaseAdapter, AdapterConfig
from aios.adapters.react import ReActAdapter
from aios.adapters.reflexion import ReflexionAdapter
from aios.adapters.autogen import AutoGenAdapter
from aios.adapters.interpreter import InterpreterAdapter

__all__ = [
    "BaseAdapter",
    "AdapterConfig",
    "ReActAdapter",
    "ReflexionAdapter",
    "AutoGenAdapter",
    "InterpreterAdapter",
]

