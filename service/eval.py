import sys
from sympy import Symbol, S, sympify, oo
from sympy.calculus.util import continuous_domain, function_range
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
import colorama
from colorama import Fore, Style

# Initialize Colorama for auto-resetting colors
colorama.init(autoreset=True)

def get_sympified_expr(user_input):
    """Parses string input into SymPy expression with smart transformations."""
    transformations = (standard_transformations + (implicit_multiplication_application,))
    return parse_expr(user_input, transformations=transformations)

def test_function(func_str, description):
    """
    Tests a specific function string for Domain and Range.
    Returns: (success_bool, status_message)
    """
    x = Symbol("x")
    
    print(f"{Fore.CYAN}{Style.BRIGHT}Testing: {func_str}")
    print(f"{Fore.CYAN}Type:    {description}")

    try:
        # 1. PARSING
        f = get_sympified_expr(func_str)
    except Exception as e:
        print(f"{Fore.RED}[FAIL] Parsing Error: {e}")
        print("-" * 50)
        return False

    # 2. DOMAIN CALCULATION
    try:
        domain = continuous_domain(f, x, S.Reals)
        print(f"{Fore.GREEN}[OK]   Domain: {domain}")
    except NotImplementedError:
        print(f"{Fore.YELLOW}[WARN] Domain: SymPy method not implemented for this function.")
    except Exception as e:
        print(f"{Fore.RED}[FAIL] Domain Error: {e}")

    # 3. RANGE CALCULATION
    try:
        # Range is often harder for SymPy to calculate than Domain
        r_range = function_range(f, x, S.Reals)
        print(f"{Fore.GREEN}[OK]   Range:  {r_range}")
    except NotImplementedError:
        print(f"{Fore.YELLOW}[WARN] Range:  SymPy cannot determine range (Not Implemented).")
    except Exception as e:
        print(f"{Fore.RED}[FAIL] Range Error: {e}")

    print("-" * 50)
    return True

def run_suite():
    print(f"{Fore.MAGENTA}{Style.BRIGHT}=== SYMPY DOMAIN & RANGE STRESS TEST ===\n")

    # A list of tuples: (Function String, Description)
    test_cases = [
        # --- BASIC & POLYNOMIAL ---
        ("x", "Linear (Identity)"),
        ("1/x", "Rational (Basic Reciprocal)"),
        ("x**2", "Quadratic (Parabola)"),
        ("abs(x)", "Absolute Value"),

        # --- TRIGONOMETRIC ---
        ("sin(x)", "Sine Wave"),
        ("tan(x)", "Tangent (Vertical Asymptotes)"),
        ("sin(x)/x", "Sinc Function (Removable Discontinuity at 0)"),

        # --- HYPERBOLIC ---
        ("sinh(x)", "Hyperbolic Sine"),
        ("cosh(x)", "Hyperbolic Cosine (Hanging Chain)"),
        ("tanh(x)", "Hyperbolic Tangent (Sigmoid shape)"),

        # --- INVERSE TRIG & HYPERBOLIC ---
        ("asin(x)", "Inverse Sine (Restricted Domain)"),
        ("acos(x)", "Inverse Cosine"),
        ("acosh(x)", "Inverse Hyperbolic Cosine (Domain >= 1)"),
        ("atanh(x)", "Inverse Hyperbolic Tangent (Asymptotes at -1, 1)"),

        # --- LOGARITHMIC & EXPONENTIAL ---
        ("log(x)", "Natural Log"),
        ("exp(x)", "Exponential"),
        ("log(x**2 - 1)", "Composite Log (Two disjoint intervals)"),

        # --- RADICALS ---
        ("sqrt(x - 2)", "Square Root (Half-line)"),
        ("sqrt(4 - x**2)", "Semicircle (Finite Domain)"),

        # --- COMPLEX / TRICKY COMPOSITES ---
        ("sqrt((x-1)/(x-2))", "Rational inside Radical (Union of intervals)"),
        ("1/sin(x)", "Cosecant (Infinite Asymptotes)"),
        ("exp(-x**2)", "Gaussian (Bell Curve)"),

        # --- PATHOLOGICAL / EDGE CASES ---
        ("x**x", "X to power of X (Complex for x<0)"),
        ("floor(x)", "Floor Function (Step discontinuities)"),

        # --- ADDITIONAL HARD/COMPLEX TESTS ---
        ("x * sin(x)", "Oscillating with growing amplitude (unbounded)"),
        ("(x**2 - 1)/(x**2 + 1)", "Rational with horizontal asymptote -> [-1,1)"),
        ("sqrt(16 - x**2)", "Semicircle radius 4 -> [0, 4]"),
        ("abs(sin(x))", "Folded sine -> [0, 1]"),
        ("x + sin(x)", "Growing oscillation -> (-oo, oo)"),
        ("log(abs(x))", "Log of magnitude -> (-oo, oo)"),
        ("exp(sin(x))", "Composition -> [exp(-1), exp(1)]"),
    ]

    success_count = 0
    
    for func, desc in test_cases:
        if test_function(func, desc):
            success_count += 1
            
    print(f"{Fore.MAGENTA}Test Suite Complete.")

if __name__ == "__main__":
    run_suite()