#!/bin/bash
# Golden tests - compare output against expected results

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SEED="python3 src/seed_compiler.py"
TESTS_DIR="tests/golden"
BUILD_DIR="build/test"

mkdir -p "$BUILD_DIR"
mkdir -p "$TESTS_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

passed=0
failed=0

echo "Running golden tests..."
echo ""

# Create expected outputs if they don't exist
create_golden() {
    local name=$1
    local source=$2
    local expected=$3
    
    if [ ! -f "$TESTS_DIR/${name}.expected" ]; then
        echo "$expected" > "$TESTS_DIR/${name}.expected"
    fi
    if [ ! -f "$TESTS_DIR/${name}.toy" ]; then
        echo "$source" > "$TESTS_DIR/${name}.toy"
    fi
}

# Create some basic golden tests
create_golden "hello" '
fn main() {
    print("Hello");
}
' 'Hello'

create_golden "arithmetic" '
fn main() {
    let x = 10 + 20;
    print(x);
}
' '30'

create_golden "factorial" '
fn factorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}
fn main() {
    print(factorial(5));
}
' '120'

create_golden "comparison" '
fn main() {
    if (5 < 10) {
        print(1);
    } else {
        print(0);
    }
}
' '1'

create_golden "while_loop" '
fn main() {
    let i = 0;
    let sum = 0;
    while (i < 5) {
        sum = sum + i;
        i = i + 1;
    }
    print(sum);
}
' '10'

# Run tests
for toyfile in "$TESTS_DIR"/*.toy; do
    if [ ! -f "$toyfile" ]; then
        continue
    fi
    
    name=$(basename "$toyfile" .toy)
    expected_file="$TESTS_DIR/${name}.expected"
    
    if [ ! -f "$expected_file" ]; then
        echo "  SKIP: $name (no expected file)"
        continue
    fi
    
    # Compile and run
    exe="$BUILD_DIR/$name"
    if $SEED "$toyfile" --compile -o "$exe" 2>/dev/null; then
        actual=$("$exe" 2>&1)
        expected=$(cat "$expected_file")
        
        if [ "$actual" = "$expected" ]; then
            echo -e "  ${GREEN}PASS${NC}: $name"
            ((passed++))
        else
            echo -e "  ${RED}FAIL${NC}: $name"
            echo "    Expected: $expected"
            echo "    Actual:   $actual"
            ((failed++))
        fi
    else
        echo -e "  ${RED}FAIL${NC}: $name (compilation failed)"
        ((failed++))
    fi
done

echo ""
echo "Results: $passed passed, $failed failed"

# Exit with error if any tests failed
[ $failed -eq 0 ]
