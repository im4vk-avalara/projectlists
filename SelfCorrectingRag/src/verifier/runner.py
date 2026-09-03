"""
Test Runner - Executes Python code against test inputs.
Uses subprocess with timeout for safe execution.
"""

import subprocess
import tempfile
import os
import sys
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..config import config


class ExecutionStatus(Enum):
    """Status of code execution."""
    SUCCESS = "success"
    WRONG_ANSWER = "wrong_answer"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    MEMORY_ERROR = "memory_error"
    COMPILATION_ERROR = "compilation_error"


@dataclass
class ExecutionResult:
    """Result of running code on a test case."""
    status: ExecutionStatus
    output: str
    expected: str
    runtime_ms: float
    error_message: Optional[str] = None
    
    @property
    def passed(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS
    
    def __str__(self) -> str:
        if self.passed:
            return f"✓ PASSED ({self.runtime_ms:.1f}ms)"
        return f"✗ {self.status.value}: got '{self.output[:100]}', expected '{self.expected[:100]}'"


class TestRunner:
    """
    Runs Python code against test inputs with timeout.
    Uses subprocess for isolation and safety.
    """
    
    def __init__(
        self, 
        timeout_seconds: Optional[float] = None,
        python_executable: str = sys.executable
    ):
        """
        Initialize test runner.
        
        Args:
            timeout_seconds: Timeout per test case.
            python_executable: Path to Python interpreter.
        """
        self.timeout = timeout_seconds or config.execution.timeout_seconds
        self.python = python_executable
    
    def run(
        self, 
        code: str, 
        test_input: str, 
        expected_output: str
    ) -> ExecutionResult:
        """
        Run code on a single test case.
        
        Args:
            code: Python source code.
            test_input: Input to provide via stdin.
            expected_output: Expected output to compare against.
            
        Returns:
            ExecutionResult with status and output.
        """
        import time
        
        # Create temporary file for code
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.py', 
            delete=False
        ) as f:
            f.write(code)
            code_file = f.name
        
        try:
            start_time = time.time()
            
            # Run code with subprocess
            result = subprocess.run(
                [self.python, code_file],
                input=test_input,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            runtime_ms = (time.time() - start_time) * 1000
            
            if result.returncode != 0:
                # Runtime error
                return ExecutionResult(
                    status=ExecutionStatus.RUNTIME_ERROR,
                    output=result.stdout.strip(),
                    expected=expected_output.strip(),
                    runtime_ms=runtime_ms,
                    error_message=result.stderr.strip()
                )
            
            actual_output = result.stdout.strip()
            expected_clean = expected_output.strip()
            
            # Compare outputs
            if self._outputs_match(actual_output, expected_clean):
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output=actual_output,
                    expected=expected_clean,
                    runtime_ms=runtime_ms
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.WRONG_ANSWER,
                    output=actual_output,
                    expected=expected_clean,
                    runtime_ms=runtime_ms
                )
                
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                output="",
                expected=expected_output.strip(),
                runtime_ms=self.timeout * 1000,
                error_message=f"Exceeded {self.timeout}s time limit"
            )
        except MemoryError:
            return ExecutionResult(
                status=ExecutionStatus.MEMORY_ERROR,
                output="",
                expected=expected_output.strip(),
                runtime_ms=0,
                error_message="Memory limit exceeded"
            )
        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.RUNTIME_ERROR,
                output="",
                expected=expected_output.strip(),
                runtime_ms=0,
                error_message=str(e)
            )
        finally:
            # Clean up temp file
            try:
                os.unlink(code_file)
            except:
                pass
    
    def run_multiple(
        self, 
        code: str, 
        test_cases: list
    ) -> list:
        """
        Run code on multiple test cases.
        
        Args:
            code: Python source code.
            test_cases: List of (input, expected_output) tuples or TestCase objects.
            
        Returns:
            List of ExecutionResult objects.
        """
        results = []
        for test in test_cases:
            if hasattr(test, 'input'):
                # TestCase object
                inp, exp = test.input, test.expected_output
            else:
                # Tuple
                inp, exp = test
            results.append(self.run(code, inp, exp))
        return results
    
    def _outputs_match(self, actual: str, expected: str) -> bool:
        """
        Compare outputs with some flexibility.
        Handles trailing whitespace and floating point tolerance.
        """
        # Normalize whitespace
        actual_lines = [line.strip() for line in actual.strip().split('\n')]
        expected_lines = [line.strip() for line in expected.strip().split('\n')]
        
        if len(actual_lines) != len(expected_lines):
            return False
        
        for act, exp in zip(actual_lines, expected_lines):
            if act == exp:
                continue
            
            # Try numeric comparison with tolerance
            try:
                act_nums = [float(x) for x in act.split()]
                exp_nums = [float(x) for x in exp.split()]
                if len(act_nums) != len(exp_nums):
                    return False
                for a, e in zip(act_nums, exp_nums):
                    if abs(a - e) > 1e-6 and abs(a - e) / max(abs(e), 1e-9) > 1e-6:
                        return False
            except ValueError:
                # Not numeric, must match exactly
                return False
        
        return True
    
    def check_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        Check if code has valid Python syntax.
        
        Returns:
            Tuple of (is_valid, error_message).
        """
        try:
            compile(code, '<string>', 'exec')
            return True, None
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"

