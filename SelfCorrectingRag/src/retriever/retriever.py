"""
Retriever - Semantic search for techniques, pitfalls, and templates.
Uses LLM for intelligent matching based on problem description.
"""

import json
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .knowledge_base import KnowledgeBase, Technique, Pitfall, Template
from ..llm.client import LLMClient
from ..parser.models import ProblemSpec


@dataclass
class RetrievalResult:
    """Result of a retrieval query."""
    techniques: List[Technique]
    pitfalls: List[Pitfall]
    templates: List[Template]
    reasoning: str
    confidence: float  # 0-1


class Retriever:
    """
    Semantic retriever for competitive programming knowledge.
    Uses LLM to match problems to techniques based on patterns.
    """
    
    TECHNIQUE_DETECTION_PROMPT = '''Analyze this competitive programming problem and identify the most likely techniques needed to solve it.

PROBLEM:
{problem_summary}

CONSTRAINTS:
- N range: {n_range}
- Value range: {value_range}
- Time limit: {time_limit}s

AVAILABLE TECHNIQUES:
{techniques_list}

Respond with JSON:
{{
    "primary_technique": "<technique_id>",
    "secondary_techniques": ["<technique_id>", ...],
    "reasoning": "<brief explanation of why these techniques apply>",
    "confidence": <0.0 to 1.0>,
    "keywords": ["keyword1", "keyword2", ...]
}}

Consider:
1. Time complexity constraints (what's feasible in {time_limit}s for N={n_max}?)
2. Problem patterns (sorting? searching? optimization?)
3. Data structure needs (range queries? dynamic connectivity?)
'''

    FAILURE_RETRIEVAL_PROMPT = '''A solution attempt failed. Analyze the failure and suggest relevant pitfalls/fixes.

PROBLEM SUMMARY:
{problem_summary}

TECHNIQUE USED:
{technique}

FAILURE REPORT:
- Input: {failing_input}
- Expected: {expected}
- Got: {actual}
- Hypothesis: {hypothesis}

KNOWN PITFALLS:
{pitfalls_list}

Respond with JSON:
{{
    "likely_pitfalls": ["<pitfall_id>", ...],
    "reasoning": "<why these pitfalls might apply>",
    "additional_checks": ["<what to verify>", ...]
}}
'''

    def __init__(
        self, 
        llm_client: Optional[LLMClient] = None,
        knowledge_base: Optional[KnowledgeBase] = None
    ):
        """
        Initialize retriever.
        
        Args:
            llm_client: LLM client for semantic matching.
            knowledge_base: Knowledge base instance.
        """
        self.llm = llm_client or LLMClient()
        self.kb = knowledge_base or KnowledgeBase()
    
    def retrieve_for_problem(
        self, 
        problem: ProblemSpec,
        top_k: int = 3
    ) -> RetrievalResult:
        """
        Retrieve relevant techniques, pitfalls, and templates for a problem.
        
        Args:
            problem: Parsed problem specification.
            top_k: Maximum number of techniques to return.
            
        Returns:
            RetrievalResult with matched resources.
        """
        # Build prompt with problem info
        techniques_list = self._format_techniques_list()
        
        prompt = self.TECHNIQUE_DETECTION_PROMPT.format(
            problem_summary=problem.statement[:2000],  # Truncate if needed
            n_range=f"[{problem.constraints.n_min}, {problem.constraints.n_max}]",
            value_range=f"[{problem.constraints.value_min}, {problem.constraints.value_max}]",
            time_limit=problem.constraints.time_limit_seconds,
            n_max=problem.constraints.n_max or "unknown",
            techniques_list=techniques_list
        )
        
        # Get LLM response
        try:
            response = self.llm.complete_json(prompt)
            data = self._parse_json_response(response)
        except Exception as e:
            # Fallback to keyword-based search
            print(f"LLM retrieval failed: {e}, falling back to keywords")
            return self._keyword_fallback(problem)
        
        # Collect techniques
        techniques = []
        primary = data.get("primary_technique")
        if primary and primary in self.kb.techniques:
            techniques.append(self.kb.techniques[primary])
        
        for tech_id in data.get("secondary_techniques", [])[:top_k-1]:
            if tech_id in self.kb.techniques and tech_id != primary:
                techniques.append(self.kb.techniques[tech_id])
        
        # Collect pitfalls for detected techniques
        pitfalls = []
        for tech in techniques:
            pitfalls.extend(self.kb.get_pitfalls_for_technique(tech.id))
        
        # Always include general pitfalls
        general_pitfalls = [p for p in self.kb.pitfalls.values() if p.technique == 'general']
        pitfalls = list({p.id: p for p in pitfalls + general_pitfalls}.values())
        
        # Collect templates
        templates = []
        for tech in techniques:
            template = self.kb.get_template_for_technique(tech.id)
            if template:
                templates.append(template)
        
        # Update problem with detected techniques
        problem.detected_techniques = [t.id for t in techniques]
        if techniques:
            problem.mark_done("technique_identified")
        
        return RetrievalResult(
            techniques=techniques,
            pitfalls=pitfalls,
            templates=templates,
            reasoning=data.get("reasoning", ""),
            confidence=data.get("confidence", 0.5)
        )
    
    def retrieve_for_failure(
        self,
        problem: ProblemSpec,
        technique: str,
        failing_input: str,
        expected: str,
        actual: str,
        hypothesis: str = ""
    ) -> List[Pitfall]:
        """
        Retrieve relevant pitfalls based on a test failure.
        
        Args:
            problem: Problem specification.
            technique: Technique that was used.
            failing_input: The input that failed.
            expected: Expected output.
            actual: Actual output.
            hypothesis: Optional hypothesis about the bug.
            
        Returns:
            List of potentially relevant pitfalls.
        """
        pitfalls_list = self._format_pitfalls_list(technique)
        
        prompt = self.FAILURE_RETRIEVAL_PROMPT.format(
            problem_summary=problem.statement[:1000],
            technique=technique,
            failing_input=failing_input[:500],
            expected=expected[:200],
            actual=actual[:200],
            hypothesis=hypothesis or "Unknown",
            pitfalls_list=pitfalls_list
        )
        
        try:
            response = self.llm.complete_json(prompt)
            data = self._parse_json_response(response)
        except Exception:
            # Return all pitfalls for the technique
            return self.kb.get_pitfalls_for_technique(technique)
        
        # Collect matching pitfalls
        pitfalls = []
        for pit_id in data.get("likely_pitfalls", []):
            if pit_id in self.kb.pitfalls:
                pitfalls.append(self.kb.pitfalls[pit_id])
        
        return pitfalls if pitfalls else self.kb.get_pitfalls_for_technique(technique)
    
    def get_template(self, technique: str) -> Optional[str]:
        """Get code template for a technique."""
        template = self.kb.get_template_for_technique(technique)
        return template.content if template else None
    
    def _format_techniques_list(self) -> str:
        """Format techniques list for prompt."""
        lines = []
        for tech_id, tech in self.kb.techniques.items():
            lines.append(
                f"- {tech_id}: {tech.name} ({tech.category}) - {tech.description}"
            )
        return "\n".join(lines)
    
    def _format_pitfalls_list(self, technique: str) -> str:
        """Format pitfalls list for prompt."""
        pitfalls = self.kb.get_pitfalls_for_technique(technique)
        lines = []
        for pit in pitfalls:
            lines.append(f"- {pit.id}: {pit.name} - {pit.description}")
        return "\n".join(lines)
    
    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response, handling markdown."""
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r'^```(?:json)?\n?', '', response)
            response = re.sub(r'\n?```$', '', response)
        return json.loads(response)
    
    def _keyword_fallback(self, problem: ProblemSpec) -> RetrievalResult:
        """Fallback keyword-based retrieval."""
        # Extract keywords from problem
        text = problem.statement.lower()
        keywords = []
        
        keyword_patterns = [
            ('shortest', ['bfs', 'dijkstra']),
            ('path', ['bfs', 'dfs', 'dijkstra']),
            ('minimum', ['dp_linear', 'greedy_interval', 'binary_search']),
            ('maximum', ['dp_linear', 'greedy_interval', 'binary_search']),
            ('count', ['dp_linear', 'modular_arithmetic']),
            ('sum', ['dp_knapsack', 'segment_tree', 'fenwick_tree']),
            ('range', ['segment_tree', 'fenwick_tree']),
            ('connected', ['union_find', 'bfs', 'dfs']),
            ('tree', ['dfs', 'segment_tree']),
            ('graph', ['bfs', 'dfs', 'dijkstra']),
            ('sorted', ['binary_search', 'two_pointers']),
            ('binary', ['binary_search']),
            ('subset', ['dp_bitmask', 'dp_knapsack']),
            ('permutation', ['dp_bitmask']),
            ('string', ['string_hashing', 'kmp']),
            ('pattern', ['kmp', 'string_hashing']),
            ('gcd', ['gcd_lcm']),
            ('prime', ['prime_sieve']),
            ('modulo', ['modular_arithmetic']),
        ]
        
        matched_techniques = set()
        for keyword, techs in keyword_patterns:
            if keyword in text:
                matched_techniques.update(techs)
        
        techniques = [
            self.kb.techniques[t] 
            for t in matched_techniques 
            if t in self.kb.techniques
        ][:3]
        
        pitfalls = []
        for tech in techniques:
            pitfalls.extend(self.kb.get_pitfalls_for_technique(tech.id))
        
        templates = []
        for tech in techniques:
            template = self.kb.get_template_for_technique(tech.id)
            if template:
                templates.append(template)
        
        return RetrievalResult(
            techniques=techniques,
            pitfalls=list({p.id: p for p in pitfalls}.values()),
            templates=templates,
            reasoning="Keyword-based matching (LLM fallback)",
            confidence=0.3
        )

