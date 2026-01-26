"""
Problem Parser - Extracts structured information from Codeforces problem statements.
Uses LLM for intelligent parsing when regex patterns aren't sufficient.
"""

import re
import json
from typing import Optional, List, Tuple
from .models import (
    ProblemSpec, Constraints, TestCase, InputFormat, 
    OutputFormat, EdgeCase, Difficulty
)
from ..llm.client import LLMClient


class ProblemParser:
    """
    Parses Codeforces problem statements into structured ProblemSpec.
    Combines regex-based extraction with LLM-assisted parsing.
    """
    
    EXTRACTION_PROMPT = '''Analyze this Codeforces problem and extract structured information.

PROBLEM STATEMENT:
{statement}

Extract the following as JSON:
{{
    "title": "problem title",
    "time_limit_seconds": <float>,
    "memory_limit_mb": <int>,
    "constraints": {{
        "n_min": <int or null>,
        "n_max": <int or null>,
        "value_min": <int or null>,
        "value_max": <int or null>,
        "sum_constraint": "<string description or null>",
        "additional": {{<any other constraints as key-value>}}
    }},
    "input_format": {{
        "description": "<description>",
        "has_multiple_test_cases": <bool>,
        "first_line_format": "<e.g. 'n m' or 't'>",
        "variables": ["list", "of", "variable", "names"]
    }},
    "output_format": {{
        "description": "<description>",
        "per_test_case": <bool>,
        "format_notes": "<any special notes like modulo, YES/NO, etc.>"
    }},
    "edge_cases": [
        {{
            "description": "<what edge case>",
            "why_tricky": "<why it might cause bugs>"
        }}
    ],
    "difficulty_estimate": "easy|medium|hard|expert"
}}

Be precise with constraint values. Parse scientific notation (e.g., 10^9 = 1000000000).
Identify at least 3 potential edge cases based on the constraints and problem nature.'''

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize parser.
        
        Args:
            llm_client: LLM client for intelligent parsing. Creates default if None.
        """
        self.llm = llm_client or LLMClient()
    
    def parse(self, statement: str, problem_id: Optional[str] = None) -> ProblemSpec:
        """
        Parse a problem statement into structured ProblemSpec.
        
        Args:
            statement: The raw problem statement text.
            problem_id: Optional problem ID (e.g., "1850E").
            
        Returns:
            Parsed ProblemSpec with all extracted information.
        """
        spec = ProblemSpec(
            problem_id=problem_id,
            statement=statement
        )
        
        # Step 1: Extract sample test cases using regex (reliable)
        spec.sample_tests = self._extract_samples(statement)
        if spec.sample_tests:
            spec.mark_done("samples_parsed")
        
        # Step 2: Use LLM for intelligent extraction
        extracted = self._llm_extract(statement)
        if extracted:
            self._apply_extraction(spec, extracted)
        
        return spec
    
    def _extract_samples(self, statement: str) -> List[TestCase]:
        """Extract sample test cases from statement using regex patterns."""
        samples = []
        
        # Common patterns for input/output sections
        # Pattern 1: "Input\n...\nOutput\n..."
        # Pattern 2: "Example\nInput\n...\nOutput\n..."
        
        # Try to find input-output pairs
        # Look for "Input" followed by content, then "Output" followed by content
        
        # Split by common section markers
        sections = re.split(
            r'\n(?=(?:Input|Output|Example|Sample)(?:\s+\d+)?:?\s*\n)',
            statement,
            flags=re.IGNORECASE
        )
        
        current_input = None
        
        for section in sections:
            section = section.strip()
            
            # Check if this is an input section
            if re.match(r'^(?:Input|Sample\s+Input)(?:\s+\d+)?:?\s*\n', section, re.IGNORECASE):
                # Extract the content after the header
                lines = section.split('\n', 1)
                if len(lines) > 1:
                    current_input = lines[1].strip()
            
            # Check if this is an output section
            elif re.match(r'^(?:Output|Sample\s+Output)(?:\s+\d+)?:?\s*\n', section, re.IGNORECASE):
                if current_input:
                    lines = section.split('\n', 1)
                    if len(lines) > 1:
                        output = lines[1].strip()
                        samples.append(TestCase(
                            input=current_input,
                            expected_output=output,
                            is_sample=True
                        ))
                        current_input = None
        
        # Fallback: Try to parse Example section directly
        if not samples:
            samples = self._extract_samples_from_example_block(statement)
        
        return samples
    
    def _extract_samples_from_example_block(self, statement: str) -> List[TestCase]:
        """Fallback extraction from Example blocks."""
        samples = []
        
        # Look for patterns like:
        # Example
        # input
        # 5
        # 1 2 3 4 5
        # output
        # 15
        
        example_match = re.search(
            r'Example[s]?\s*\n(.*?)(?=\n(?:Note|Hint|$)|\Z)',
            statement,
            re.IGNORECASE | re.DOTALL
        )
        
        if example_match:
            example_block = example_match.group(1)
            
            # Split into input/output pairs
            parts = re.split(r'\n(?:input|output)\s*\n', example_block, flags=re.IGNORECASE)
            
            # Parts should alternate: content, input_content, output_content, input_content, ...
            i = 1  # Skip first part (might be empty or header)
            while i + 1 < len(parts):
                inp = parts[i].strip()
                out = parts[i + 1].strip()
                if inp and out:
                    samples.append(TestCase(
                        input=inp,
                        expected_output=out,
                        is_sample=True
                    ))
                i += 2
        
        return samples
    
    def _llm_extract(self, statement: str) -> Optional[dict]:
        """Use LLM to extract structured information."""
        try:
            prompt = self.EXTRACTION_PROMPT.format(statement=statement)
            response = self.llm.complete_json(prompt)
            
            # Clean response (remove markdown if present)
            response = response.strip()
            if response.startswith("```"):
                response = re.sub(r'^```(?:json)?\n?', '', response)
                response = re.sub(r'\n?```$', '', response)
            
            return json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            print(f"LLM extraction failed: {e}")
            return None
    
    def _apply_extraction(self, spec: ProblemSpec, data: dict) -> None:
        """Apply LLM-extracted data to ProblemSpec."""
        
        # Title
        spec.title = data.get("title", spec.title)
        
        # Constraints
        if "constraints" in data:
            c = data["constraints"]
            spec.constraints = Constraints(
                n_min=c.get("n_min"),
                n_max=c.get("n_max"),
                value_min=c.get("value_min"),
                value_max=c.get("value_max"),
                time_limit_seconds=data.get("time_limit_seconds", 1.0),
                memory_limit_mb=data.get("memory_limit_mb", 256),
                sum_constraint=c.get("sum_constraint"),
                additional=c.get("additional", {})
            )
            spec.mark_done("constraints_extracted")
        
        # Input format
        if "input_format" in data:
            inf = data["input_format"]
            spec.input_format = InputFormat(
                description=inf.get("description", ""),
                has_multiple_test_cases=inf.get("has_multiple_test_cases", False),
                first_line_format=inf.get("first_line_format"),
                variables=inf.get("variables", [])
            )
            spec.mark_done("input_format_understood")
        
        # Output format
        if "output_format" in data:
            outf = data["output_format"]
            spec.output_format = OutputFormat(
                description=outf.get("description", ""),
                per_test_case=outf.get("per_test_case", True),
                format_notes=outf.get("format_notes")
            )
            spec.mark_done("output_format_understood")
        
        # Edge cases
        if "edge_cases" in data:
            for ec in data["edge_cases"]:
                spec.edge_cases.append(EdgeCase(
                    description=ec.get("description", ""),
                    why_tricky=ec.get("why_tricky")
                ))
            if spec.edge_cases:
                spec.mark_done("edge_cases_identified")
        
        # Difficulty
        diff_map = {
            "easy": Difficulty.EASY,
            "medium": Difficulty.MEDIUM,
            "hard": Difficulty.HARD,
            "expert": Difficulty.EXPERT
        }
        spec.difficulty = diff_map.get(
            data.get("difficulty_estimate", "").lower(),
            Difficulty.UNKNOWN
        )
    
    def parse_test_cases_manual(self, inputs: List[str], outputs: List[str]) -> List[TestCase]:
        """
        Create test cases from manually provided inputs and outputs.
        
        Args:
            inputs: List of input strings.
            outputs: List of expected output strings.
            
        Returns:
            List of TestCase objects.
        """
        if len(inputs) != len(outputs):
            raise ValueError("Number of inputs must match number of outputs")
        
        return [
            TestCase(input=inp.strip(), expected_output=out.strip(), is_sample=True)
            for inp, out in zip(inputs, outputs)
        ]

