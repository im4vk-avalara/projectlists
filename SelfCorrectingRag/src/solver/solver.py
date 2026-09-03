"""
Solver - Generates solutions for competitive programming problems.
Uses LLM with retrieved techniques and templates.
"""

import re
import json
from typing import Optional, List, Tuple

from .models import Solution, Approach, Complexity, SolutionStatus, FailureReport
from ..parser.models import ProblemSpec
from ..retriever.retriever import Retriever, RetrievalResult
from ..llm.client import LLMClient


class Solver:
    """
    Generates solutions for competitive programming problems.
    Uses retrieved techniques and templates to guide code generation.
    """
    
    APPROACH_PROMPT = '''You are an expert competitive programmer. Generate a solution approach for this problem.

PROBLEM:
{problem_statement}

CONSTRAINTS:
- N: [{n_min}, {n_max}]
- Values: [{val_min}, {val_max}]
- Time limit: {time_limit}s
- Memory limit: {memory_limit}MB

DETECTED TECHNIQUES:
{techniques}

EDGE CASES TO HANDLE:
{edge_cases}

RELEVANT TEMPLATES:
{templates}

Generate a detailed approach as JSON:
{{
    "summary": "<one-line summary of approach>",
    "key_insight": "<the main idea that makes this work>",
    "steps": [
        "<step 1>",
        "<step 2>",
        ...
    ],
    "correctness_argument": "<brief proof/argument why this is correct>",
    "edge_case_handling": {{
        "<edge case 1>": "<how to handle>",
        ...
    }},
    "time_complexity": "<e.g., O(n log n)>",
    "space_complexity": "<e.g., O(n)>",
    "complexity_explanation": "<why this complexity>"
}}'''

    CODE_GENERATION_PROMPT = '''Generate a COMPLETE, SELF-CONTAINED Python solution for this competitive programming problem.

PROBLEM:
{problem_statement}

APPROACH:
{approach}

COMPLEXITY:
- Time: {time_complexity}
- Space: {space_complexity}

TEMPLATE CODE (use as reference):
```python
{template_code}
```

SAMPLE INPUT/OUTPUT:
{samples}

PITFALLS TO AVOID:
{pitfalls}

CRITICAL REQUIREMENTS:
1. Output ONLY valid Python code - NO markdown, NO explanations, NO ```python``` tags
2. The code must be COMPLETE and RUNNABLE as-is
3. Include ALL imports at the top (sys, collections, etc.)
4. Include ALL variable definitions and the main logic
5. Read input using input() or sys.stdin
6. Print output to stdout
7. Handle multiple test cases if the problem requires it
8. Handle edge cases (n=1, empty arrays, etc.)

The code should start with imports (if needed) and end with the solution logic.
DO NOT include markdown formatting. DO NOT include explanations.
Output raw Python code only:'''

    REPAIR_PROMPT = '''Fix this competitive programming solution based on the failure report.

PROBLEM SUMMARY:
{problem_summary}

CURRENT CODE:
```python
{current_code}
```

FAILURE REPORT:
- Input: {failing_input}
- Expected: {expected}
- Got: {actual}
- Error type: {error_type}
- Hypothesis: {hypothesis}

RELEVANT PITFALLS:
{pitfalls}

INSTRUCTIONS:
1. Analyze the bug carefully
2. Fix the code to handle this case
3. Return the COMPLETE fixed code (not just the changed part)
4. The fixed_code must be valid Python that runs standalone

Respond with this exact JSON format:
{{
    "bug_analysis": "<what went wrong and why>",
    "fix_description": "<brief description of the fix>",
    "fixed_code": "<COMPLETE Python code - all imports, all logic, ready to run>"
}}

IMPORTANT: The fixed_code field must contain the ENTIRE solution, not just a snippet.'''

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        retriever: Optional[Retriever] = None
    ):
        """
        Initialize solver.
        
        Args:
            llm_client: LLM client for generation.
            retriever: Retriever for techniques/templates.
        """
        self.llm = llm_client or LLMClient()
        self.retriever = retriever or Retriever(llm_client=self.llm)
    
    def solve(self, problem: ProblemSpec) -> Solution:
        """
        Generate a complete solution for a problem.
        
        Args:
            problem: Parsed problem specification.
            
        Returns:
            Generated Solution object.
        """
        solution = Solution()
        
        # Step 1: Retrieve relevant techniques and templates
        retrieval = self.retriever.retrieve_for_problem(problem)
        
        # Step 2: Generate approach
        approach, complexity = self._generate_approach(problem, retrieval)
        solution.approach = approach
        solution.complexity = complexity
        
        # Step 3: Generate code
        code = self._generate_code(problem, approach, complexity, retrieval)
        solution.code = code
        solution.status = SolutionStatus.GENERATED
        
        problem.mark_done("solution_implemented")
        
        return solution
    
    def _generate_approach(
        self, 
        problem: ProblemSpec, 
        retrieval: RetrievalResult
    ) -> Tuple[Approach, Complexity]:
        """Generate solution approach and complexity analysis."""
        
        # Format techniques info
        techniques_text = "\n".join([
            f"- {t.name}: {t.description}\n  Key insight: {t.key_insight}"
            for t in retrieval.techniques
        ]) or "No specific technique detected"
        
        # Format edge cases
        edge_cases_text = "\n".join([
            f"- {ec.description}" + (f" ({ec.why_tricky})" if ec.why_tricky else "")
            for ec in problem.edge_cases
        ]) or "None identified"
        
        # Format template references
        templates_text = "\n".join([
            f"- {t.name}: available for reference"
            for t in retrieval.templates
        ]) or "No templates"
        
        prompt = self.APPROACH_PROMPT.format(
            problem_statement=problem.statement[:3000],
            n_min=problem.constraints.n_min or 1,
            n_max=problem.constraints.n_max or "unknown",
            val_min=problem.constraints.value_min or 1,
            val_max=problem.constraints.value_max or "unknown",
            time_limit=problem.constraints.time_limit_seconds,
            memory_limit=problem.constraints.memory_limit_mb,
            techniques=techniques_text,
            edge_cases=edge_cases_text,
            templates=templates_text
        )
        
        response = self.llm.complete_json(prompt)
        data = self._parse_json(response)
        
        approach = Approach(
            summary=data.get("summary", ""),
            steps=data.get("steps", []),
            key_insight=data.get("key_insight", ""),
            correctness_argument=data.get("correctness_argument", ""),
            techniques_used=[t.id for t in retrieval.techniques],
            edge_case_handling=data.get("edge_case_handling", {})
        )
        
        # Estimate operations count
        estimated_ops = self._estimate_operations(
            data.get("time_complexity", "O(n)"),
            problem.constraints.n_max
        )
        
        complexity = Complexity(
            time=data.get("time_complexity", "O(?)"),
            space=data.get("space_complexity", "O(?)"),
            explanation=data.get("complexity_explanation", ""),
            estimated_operations=estimated_ops,
            fits_constraints=not Complexity(
                time=data.get("time_complexity", ""),
                space=data.get("space_complexity", ""),
                estimated_operations=estimated_ops
            ).will_tle(problem.constraints.time_limit_seconds)
        )
        
        return approach, complexity
    
    def _generate_code(
        self,
        problem: ProblemSpec,
        approach: Approach,
        complexity: Complexity,
        retrieval: RetrievalResult
    ) -> str:
        """Generate solution code."""
        
        # Format approach steps
        approach_text = f"""Summary: {approach.summary}
Key insight: {approach.key_insight}

Steps:
{chr(10).join(f'{i+1}. {step}' for i, step in enumerate(approach.steps))}

Correctness: {approach.correctness_argument}"""
        
        # Get template code
        template_code = ""
        if retrieval.templates:
            template_code = retrieval.templates[0].content[:2000]
        else:
            template_code = "# No specific template - use standard Python"
        
        # Format samples
        samples_text = ""
        for i, test in enumerate(problem.sample_tests[:3], 1):
            samples_text += f"\n--- Sample {i} ---\nInput:\n{test.input}\nOutput:\n{test.expected_output}\n"
        
        # Format pitfalls
        pitfalls_text = "\n".join([
            f"- {p.name}: {p.fix}"
            for p in retrieval.pitfalls[:5]
        ]) or "- Watch for edge cases"
        
        prompt = self.CODE_GENERATION_PROMPT.format(
            problem_statement=problem.statement[:2500],
            approach=approach_text,
            time_complexity=complexity.time,
            space_complexity=complexity.space,
            template_code=template_code,
            samples=samples_text,
            pitfalls=pitfalls_text
        )
        
        # Try up to 3 times to get valid code
        for attempt in range(3):
            response = self.llm.complete(prompt, temperature=0.3 + attempt * 0.1)
            code = self._extract_code(response)
            
            # Validate code completeness
            if self._is_complete_code(code):
                return code
            
            print(f"Code generation attempt {attempt + 1} produced incomplete code, retrying...")
        
        # Return whatever we got on last attempt
        return code
    
    def _is_complete_code(self, code: str) -> bool:
        """Check if generated code appears to be complete and runnable."""
        if not code or len(code) < 20:
            return False
        
        # Check for basic structure
        has_input = 'input' in code.lower() or 'stdin' in code.lower()
        has_print = 'print' in code.lower()
        
        # Check it's not just a snippet
        lines = [l for l in code.strip().split('\n') if l.strip() and not l.strip().startswith('#')]
        if len(lines) < 3:
            return False
        
        # Check for syntax errors
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError:
            return False
        
        return has_input and has_print
    
    def repair(
        self,
        problem: ProblemSpec,
        solution: Solution,
        failure: FailureReport
    ) -> Solution:
        """
        Repair a failing solution based on failure report.
        
        Args:
            problem: Problem specification.
            solution: Current failing solution.
            failure: Failure report with details.
            
        Returns:
            Updated Solution object.
        """
        # Get relevant pitfalls based on failure
        pitfalls = self.retriever.retrieve_for_failure(
            problem=problem,
            technique=solution.approach.techniques_used[0] if solution.approach and solution.approach.techniques_used else "general",
            failing_input=failure.failing_input,
            expected=failure.expected_output,
            actual=failure.actual_output,
            hypothesis=failure.root_cause_hypothesis
        )
        
        pitfalls_text = "\n".join([
            f"- {p.name}: {p.description}\n  Fix: {p.fix}"
            for p in pitfalls
        ])
        
        prompt = self.REPAIR_PROMPT.format(
            problem_summary=problem.statement[:1500],
            current_code=solution.code,
            failing_input=failure.failing_input[:500],
            expected=failure.expected_output[:300],
            actual=failure.actual_output[:300],
            error_type=failure.error_type,
            hypothesis=failure.root_cause_hypothesis or "Unknown",
            pitfalls=pitfalls_text
        )
        
        try:
            response = self.llm.complete_json(prompt)
            data = self._parse_json(response)
        except Exception as e:
            # If JSON parsing fails, try to extract code directly
            print(f"Repair JSON parsing failed: {e}, trying direct extraction")
            try:
                response = self.llm.complete(prompt, temperature=0.3)
                fixed_code = self._extract_code(response)
                if fixed_code and fixed_code != solution.code:
                    solution.code = fixed_code
                    solution.add_repair(failure.failing_input, "Auto-repair (JSON parse failed)")
                    solution.status = SolutionStatus.REPAIRED
                return solution
            except Exception:
                # Return unchanged solution if all fails
                return solution
        
        # Update solution
        fixed_code = data.get("fixed_code", solution.code)
        if fixed_code and fixed_code.startswith("```"):
            fixed_code = self._extract_code(fixed_code)
        
        if fixed_code:
            solution.code = fixed_code
        solution.add_repair(failure.failing_input, data.get("fix_description", ""))
        solution.status = SolutionStatus.REPAIRED
        
        return solution
    
    def _estimate_operations(self, complexity: str, n_max: Optional[int]) -> Optional[int]:
        """Estimate number of operations from complexity string."""
        if n_max is None:
            return None
        
        n = n_max
        complexity = complexity.lower().replace(" ", "")
        
        # Parse common complexities
        patterns = [
            (r"o\(1\)", lambda n: 1),
            (r"o\(logn\)", lambda n: max(1, n.bit_length())),
            (r"o\(n\)", lambda n: n),
            (r"o\(nlogn\)", lambda n: n * max(1, n.bit_length())),
            (r"o\(n\^2\)", lambda n: n * n),
            (r"o\(n\^3\)", lambda n: n * n * n),
            (r"o\(2\^n\)", lambda n: 2 ** min(n, 30)),
            (r"o\(n!\)", lambda n: min(10**18, 1) if n > 20 else __import__('math').factorial(n)),
        ]
        
        for pattern, calc in patterns:
            if re.match(pattern, complexity):
                return calc(n)
        
        # Default: assume O(n)
        return n
    
    def _extract_code(self, response: str) -> str:
        """Extract Python code from LLM response."""
        # Try to find code block with python tag
        code_match = re.search(r'```python\n(.*?)```', response, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        # Try generic code block
        code_match = re.search(r'```\n(.*?)```', response, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        # Try to find "fixed_code" field in JSON-like response
        fixed_code_match = re.search(r'"fixed_code"\s*:\s*"(.*?)"(?:\s*}|,\s*")', response, re.DOTALL)
        if fixed_code_match:
            code = fixed_code_match.group(1)
            # Unescape newlines and quotes
            code = code.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            return code.strip()
        
        # If no code block, try to extract valid Python code
        lines = response.strip().split('\n')
        
        # Find first line that looks like Python code
        code_start = -1
        code_indicators = ('import ', 'from ', 'def ', 'class ', 'MOD', 'n =', 't =', 
                          'n,', 't,', 'for ', 'while ', 'if ', 'try:', 'input(')
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip empty lines and obvious explanatory text
            if not stripped:
                continue
            if stripped.startswith(('Looking', 'Let', 'The ', 'This ', 'I ', 'We ', 'So ', 
                                   'For ', '1.', '2.', '3.', '-', '*', '{')):
                continue
            # Check if it looks like code
            for indicator in code_indicators:
                if stripped.startswith(indicator) or indicator in stripped:
                    code_start = i
                    break
            if code_start >= 0:
                break
        
        if code_start >= 0:
            # Extract from code_start to end, but stop at JSON or explanation
            code_lines = []
            for line in lines[code_start:]:
                # Stop if we hit JSON or explanation
                if line.strip().startswith(('{', '"bug_analysis', 'Looking', 'The issue')):
                    break
                code_lines.append(line)
            return '\n'.join(code_lines).strip()
        
        # Last resort: return the whole thing
        return response.strip()
    
    def _parse_json(self, response: str) -> dict:
        """Parse JSON from LLM response."""
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r'^```(?:json)?\n?', '', response)
            response = re.sub(r'\n?```$', '', response)
        return json.loads(response)

