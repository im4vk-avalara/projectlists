"""
Codeforces Problem Fetcher - Retrieves problem statements from Codeforces.
Supports both API and web scraping approaches.
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class FetchedProblem:
    """Raw problem data fetched from Codeforces."""
    contest_id: int
    problem_index: str  # e.g., "A", "B", "E1"
    title: str
    statement: str
    time_limit: str
    memory_limit: str
    input_spec: str
    output_spec: str
    samples_input: list
    samples_output: list
    note: Optional[str] = None
    url: str = ""


class CodeforcesFetcher:
    """
    Fetches problem statements from Codeforces.
    
    Note: This is a skeleton implementation. Full web scraping requires
    network access and handling of Codeforces' HTML structure.
    For now, it provides utilities for parsing problem URLs and 
    formatting problems provided as text.
    """
    
    CF_URL_PATTERN = re.compile(
        r'codeforces\.com/(?:contest|problemset/problem)/(\d+)/(\w+)',
        re.IGNORECASE
    )
    
    @classmethod
    def parse_problem_url(cls, url: str) -> Optional[Tuple[int, str]]:
        """
        Parse a Codeforces problem URL.
        
        Args:
            url: Codeforces problem URL.
            
        Returns:
            Tuple of (contest_id, problem_index) or None if invalid.
        """
        match = cls.CF_URL_PATTERN.search(url)
        if match:
            return int(match.group(1)), match.group(2).upper()
        return None
    
    @classmethod
    def build_problem_url(cls, contest_id: int, problem_index: str) -> str:
        """Build a Codeforces problem URL."""
        return f"https://codeforces.com/contest/{contest_id}/problem/{problem_index}"
    
    @classmethod
    def format_problem_text(
        cls,
        title: str,
        time_limit: str,
        memory_limit: str,
        statement: str,
        input_spec: str,
        output_spec: str,
        samples: list,  # List of (input, output) tuples
        note: Optional[str] = None
    ) -> str:
        """
        Format problem components into a standard text format.
        
        This is useful when manually providing problem details
        or converting from other formats.
        """
        lines = [
            f"# {title}",
            f"Time limit: {time_limit}",
            f"Memory limit: {memory_limit}",
            "",
            "## Statement",
            statement,
            "",
            "## Input",
            input_spec,
            "",
            "## Output",
            output_spec,
            "",
            "## Examples",
        ]
        
        for i, (inp, out) in enumerate(samples, 1):
            lines.extend([
                f"### Example {i}",
                "Input",
                inp,
                "Output",
                out,
                ""
            ])
        
        if note:
            lines.extend([
                "## Note",
                note
            ])
        
        return "\n".join(lines)


def create_problem_from_text(
    title: str,
    statement: str,
    input_spec: str,
    output_spec: str,
    samples: list,
    time_limit: str = "1 second",
    memory_limit: str = "256 MB",
    note: Optional[str] = None,
    contest_id: Optional[int] = None,
    problem_index: Optional[str] = None
) -> str:
    """
    Convenience function to create a formatted problem statement.
    
    Args:
        title: Problem title.
        statement: Main problem statement.
        input_spec: Input specification.
        output_spec: Output specification.
        samples: List of (input_str, output_str) tuples.
        time_limit: Time limit string.
        memory_limit: Memory limit string.
        note: Optional note/explanation.
        contest_id: Optional contest ID.
        problem_index: Optional problem index (A, B, etc.).
        
    Returns:
        Formatted problem statement string.
    """
    problem_id = ""
    if contest_id and problem_index:
        problem_id = f" ({contest_id}{problem_index})"
    
    return CodeforcesFetcher.format_problem_text(
        title=f"{title}{problem_id}",
        time_limit=time_limit,
        memory_limit=memory_limit,
        statement=statement,
        input_spec=input_spec,
        output_spec=output_spec,
        samples=samples,
        note=note
    )

