"""
Self-Correcting Codeforces Tutor - Main Orchestrator.

Implements the complete self-correcting loop:
Understand → Retrieve → Solve → Implement → Verify → Repair (repeat until verified)
"""

from typing import Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from .config import config
from .llm.client import LLMClient
from .parser.parser import ProblemParser
from .parser.models import ProblemSpec, TestCase
from .retriever.retriever import Retriever, RetrievalResult
from .solver.solver import Solver
from .solver.models import Solution, SolutionStatus, FailureReport
from .verifier.verifier import Verifier, VerificationResult
from .verifier.metamorphic import MetamorphicRelation


class TutorPhase(Enum):
    """Phases of the tutoring process."""
    UNDERSTAND = "understand"
    RETRIEVE = "retrieve"
    SOLVE = "solve"
    VERIFY = "verify"
    REPAIR = "repair"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class TutorSession:
    """Complete tutoring session state."""
    # Problem
    problem: Optional[ProblemSpec] = None
    
    # Retrieved knowledge
    retrieval: Optional[RetrievalResult] = None
    
    # Solution attempts
    solution: Optional[Solution] = None
    solution_history: List[Solution] = field(default_factory=list)
    
    # Verification
    verification: Optional[VerificationResult] = None
    
    # Progress
    current_phase: TutorPhase = TutorPhase.UNDERSTAND
    repair_count: int = 0
    max_repairs: int = 5
    
    # Logs
    logs: List[str] = field(default_factory=list)
    
    def log(self, message: str) -> None:
        """Add a log message."""
        self.logs.append(message)
        print(f"[{self.current_phase.value.upper()}] {message}")
    
    @property
    def is_complete(self) -> bool:
        return self.current_phase == TutorPhase.COMPLETE
    
    @property
    def is_failed(self) -> bool:
        return self.current_phase == TutorPhase.FAILED


@dataclass
class TutorOutput:
    """Final output of the tutor."""
    success: bool
    
    # Solution details
    approach_summary: str = ""
    complexity: str = ""
    code: str = ""
    
    # Verification summary
    samples_passed: int = 0
    samples_total: int = 0
    stress_tests_run: int = 0
    stress_passed: bool = False
    
    # Metadata
    techniques_used: List[str] = field(default_factory=list)
    repair_attempts: int = 0
    assumptions: List[str] = field(default_factory=list)
    checklist: dict = field(default_factory=dict)
    
    def __str__(self) -> str:
        """Format complete output."""
        lines = [
            "=" * 60,
            "SELF-CORRECTING CODEFORCES TUTOR - OUTPUT",
            "=" * 60,
            "",
        ]
        
        if not self.success:
            lines.append("❌ FAILED TO PRODUCE VERIFIED SOLUTION")
            lines.append("")
        else:
            lines.append("✅ VERIFIED SOLUTION PRODUCED")
            lines.append("")
        
        # Approach
        lines.extend([
            "📋 SOLUTION OUTLINE",
            "-" * 40,
            self.approach_summary,
            "",
            f"⏱️  Complexity: Time {self.complexity}",
            f"🔧 Techniques: {', '.join(self.techniques_used) or 'N/A'}",
            "",
        ])
        
        # Code
        lines.extend([
            "💻 FINAL CODE",
            "-" * 40,
            "```python",
            self.code,
            "```",
            "",
        ])
        
        # Verification summary
        lines.extend([
            "✔️  VERIFICATION SUMMARY",
            "-" * 40,
            f"Sample tests: {self.samples_passed}/{self.samples_total} passed",
            f"Stress tests: {self.stress_tests_run} run, {'PASSED' if self.stress_passed else 'SKIPPED/FAILED'}",
            f"Repair attempts: {self.repair_attempts}",
            "",
        ])
        
        # Assumptions
        if self.assumptions:
            lines.append("⚠️  ASSUMPTIONS")
            lines.append("-" * 40)
            for a in self.assumptions:
                lines.append(f"  • {a}")
            lines.append("")
        
        # Checklist
        lines.extend([
            "📝 CHECKLIST",
            "-" * 40,
        ])
        for item, done in self.checklist.items():
            status = "✓" if done else "✗"
            lines.append(f"  [{status}] {item.replace('_', ' ').title()}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


class Tutor:
    """
    Self-Correcting Codeforces Tutor.
    
    Implements the complete tutoring loop:
    1. UNDERSTAND: Parse problem, extract constraints, edge cases
    2. RETRIEVE: Find relevant techniques, pitfalls, templates
    3. SOLVE: Generate approach and code
    4. VERIFY: Run samples, stress tests, metamorphic tests
    5. REPAIR: If failed, analyze failure and fix (repeat until verified or max attempts)
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_repair_attempts: Optional[int] = None
    ):
        """
        Initialize tutor.
        
        Args:
            llm_client: LLM client for all AI operations.
            max_repair_attempts: Maximum repair attempts before giving up.
        """
        self.llm = llm_client or LLMClient()
        self.max_repairs = max_repair_attempts or config.execution.max_repair_iterations
        
        # Initialize components
        self.parser = ProblemParser(llm_client=self.llm)
        self.retriever = Retriever(llm_client=self.llm)
        self.solver = Solver(llm_client=self.llm, retriever=self.retriever)
        self.verifier = Verifier()
    
    def solve(
        self,
        problem_statement: str,
        samples: Optional[List[tuple]] = None,
        problem_id: Optional[str] = None,
        oracle_code: Optional[str] = None,
        metamorphic_relations: Optional[List[MetamorphicRelation]] = None,
        verbose: bool = True
    ) -> TutorOutput:
        """
        Solve a Codeforces problem with self-correction.
        
        Args:
            problem_statement: The complete problem statement text.
            samples: Optional list of (input, output) sample tuples.
            problem_id: Optional problem ID (e.g., "1850E").
            oracle_code: Optional brute-force oracle for stress testing.
            metamorphic_relations: Optional metamorphic relations to test.
            verbose: Whether to print progress.
            
        Returns:
            TutorOutput with solution and verification summary.
        """
        session = TutorSession(max_repairs=self.max_repairs)
        
        # Phase 1: UNDERSTAND
        session.current_phase = TutorPhase.UNDERSTAND
        session.log("Parsing problem statement...")
        session.problem = self._understand(problem_statement, samples, problem_id)
        session.log(f"Extracted {len(session.problem.sample_tests)} samples, "
                   f"{len(session.problem.edge_cases)} edge cases")
        
        # Phase 2: RETRIEVE
        session.current_phase = TutorPhase.RETRIEVE
        session.log("Retrieving relevant techniques...")
        session.retrieval = self._retrieve(session.problem)
        techniques = [t.name for t in session.retrieval.techniques]
        session.log(f"Detected techniques: {', '.join(techniques) or 'None'}")
        
        # Phase 3: SOLVE
        session.current_phase = TutorPhase.SOLVE
        session.log("Generating solution...")
        session.solution = self._solve(session.problem)
        session.solution_history.append(session.solution)
        session.log(f"Generated approach: {session.solution.approach.summary if session.solution.approach else 'N/A'}")
        
        # Phase 4 & 5: VERIFY + REPAIR loop
        while session.repair_count <= session.max_repairs:
            session.current_phase = TutorPhase.VERIFY
            session.log(f"Verifying solution (attempt {session.repair_count + 1})...")
            
            session.verification = self._verify(
                session.solution,
                session.problem,
                oracle_code,
                metamorphic_relations
            )
            
            if session.verification.all_passed:
                session.current_phase = TutorPhase.COMPLETE
                session.log("✓ All verification passed!")
                break
            
            # Verification failed - attempt repair
            if session.repair_count >= session.max_repairs:
                session.current_phase = TutorPhase.FAILED
                session.log(f"✗ Max repair attempts ({session.max_repairs}) reached")
                break
            
            session.current_phase = TutorPhase.REPAIR
            session.repair_count += 1
            session.log(f"Verification failed, attempting repair #{session.repair_count}...")
            
            if session.verification.failure_report:
                session.solution = self._repair(
                    session.problem,
                    session.solution,
                    session.verification.failure_report
                )
                session.solution_history.append(session.solution)
                session.log(f"Applied fix: {session.solution.repair_history[-1]['fix'] if session.solution.repair_history else 'N/A'}")
            else:
                session.log("No failure report available, cannot repair")
                session.current_phase = TutorPhase.FAILED
                break
        
        return self._create_output(session)
    
    def solve_with_samples(
        self,
        problem_statement: str,
        sample_inputs: List[str],
        sample_outputs: List[str],
        problem_id: Optional[str] = None,
        oracle_code: Optional[str] = None
    ) -> TutorOutput:
        """
        Solve a problem with explicitly provided samples.
        
        Args:
            problem_statement: Problem statement text.
            sample_inputs: List of sample input strings.
            sample_outputs: List of expected output strings.
            problem_id: Optional problem ID.
            oracle_code: Optional brute-force oracle.
            
        Returns:
            TutorOutput.
        """
        samples = list(zip(sample_inputs, sample_outputs))
        return self.solve(
            problem_statement=problem_statement,
            samples=samples,
            problem_id=problem_id,
            oracle_code=oracle_code
        )
    
    def _understand(
        self,
        statement: str,
        samples: Optional[List[tuple]],
        problem_id: Optional[str]
    ) -> ProblemSpec:
        """Parse and understand the problem."""
        problem = self.parser.parse(statement, problem_id)
        
        # If explicit samples provided, use them instead of parsed ones
        if samples:
            problem.sample_tests = []  # Clear parsed samples
            for inp, out in samples:
                problem.sample_tests.append(TestCase(
                    input=inp.strip(),
                    expected_output=out.strip(),
                    is_sample=True
                ))
            problem.mark_done("samples_parsed")
        
        return problem
    
    def _retrieve(self, problem: ProblemSpec) -> RetrievalResult:
        """Retrieve relevant techniques and templates."""
        return self.retriever.retrieve_for_problem(problem)
    
    def _solve(self, problem: ProblemSpec) -> Solution:
        """Generate solution."""
        return self.solver.solve(problem)
    
    def _verify(
        self,
        solution: Solution,
        problem: ProblemSpec,
        oracle_code: Optional[str],
        metamorphic_relations: Optional[List[MetamorphicRelation]]
    ) -> VerificationResult:
        """Verify solution."""
        return self.verifier.verify(
            solution=solution,
            problem=problem,
            oracle_code=oracle_code,
            metamorphic_relations=metamorphic_relations
        )
    
    def _repair(
        self,
        problem: ProblemSpec,
        solution: Solution,
        failure: FailureReport
    ) -> Solution:
        """Repair failing solution."""
        return self.solver.repair(problem, solution, failure)
    
    def _create_output(self, session: TutorSession) -> TutorOutput:
        """Create final output from session."""
        output = TutorOutput(success=session.is_complete)
        
        if session.solution:
            if session.solution.approach:
                output.approach_summary = session.solution.approach.summary
                output.techniques_used = session.solution.approach.techniques_used
            if session.solution.complexity:
                output.complexity = f"{session.solution.complexity.time}, Space {session.solution.complexity.space}"
            output.code = session.solution.code
            output.repair_attempts = session.solution.repair_attempts
        
        if session.verification:
            output.samples_passed = sum(1 for r in session.verification.sample_results if r.passed)
            output.samples_total = len(session.verification.sample_results)
            if session.verification.stress_result:
                output.stress_tests_run = session.verification.stress_result.tests_run
                output.stress_passed = session.verification.stress_result.passed
            output.assumptions = session.verification.assumptions
        
        if session.problem:
            output.checklist = session.problem.checklist.copy()
        
        return output

