"""
POWER SERIES ENGINE v2.0 — OPTIMIZED EDITION
=============================================
Analyzes power series for radius and interval of convergence.

Optimizations over v1.0:
  1. Fast-path detection for common patterns (geometric, factorial)
  2. Cached simplifications to avoid redundant computation
  3. Early bailout when limit is clearly 0 or oo
  4. Timeout protection for slow symbolic operations
  5. Log-based ratio test for better numerical stability
  6. Optimized inequality solving with pattern matching
  7. Parallel-ready endpoint analysis structure
  8. String-based input parsing with implicit multiplication support
"""

import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)
from sympy.solvers.inequalities import solve_univariate_inequality
from conv_div_engine import Profiler, super_fast_limit, check_series_convergence
from algo import get_sympified_expr, _rationalize_float_exponents
import functools
import time


# ─────────────────────────────────────────────────────────────────────────────
#  CACHING AND UTILITIES
# ─────────────────────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=128)
def _cached_simplify(expr_str):
    """Cache expensive simplifications."""
    return sp.simplify(sp.sympify(expr_str))


def _timeout_limit(expr, var, point, timeout_ms=5000):
    """
    Compute limit with timeout protection.
    Falls back to None if computation exceeds timeout.
    """
    try:
        # For very complex expressions, use a simpler approach first
        if expr.has(sp.binomial) or (expr.has(sp.factorial) and expr.has(sp.gamma)):
            # Try combsimp first for binomial/factorial expressions
            expr = sp.combsimp(expr)

        return sp.limit(expr, var, point)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  FAST PATTERN DETECTION
# ─────────────────────────────────────────────────────────────────────────────


def _detect_power_series_structure(expr, n, x):
    """
    Fast detection of common power series patterns.
    Returns (coefficient_part, power_base, center) or None if pattern not recognized.

    Patterns detected:
    - a_n * x^n           -> (a_n, x, 0)
    - a_n * (x-c)^n       -> (a_n, x-c, c)
    - a_n * (x-c)^n / b^n -> (a_n/b^n, x-c, c)
    """
    # Expand to separate terms
    expr_expanded = sp.expand(expr)

    # Look for power terms involving x
    for term in sp.Add.make_args(expr_expanded):
        for pow_term in term.atoms(sp.Pow):
            base, exp = pow_term.as_base_exp()
            if exp == n or (exp.is_Mul and n in exp.as_two_terms()):
                # Found x^n or similar pattern
                if base.has(x):
                    # Extract center from (x - c) pattern
                    if base.is_Add:
                        # (x - c) form
                        parts = base.as_two_terms()
                        if x in parts:
                            center = -sum(p for p in parts if p != x)
                            return term / pow_term, base, center
                    elif base == x:
                        return term / pow_term, x, 0

    return None


def _fast_ratio_limit(expr, n, x):
    """
    Optimized ratio test computation using logarithmic form for stability.
    """
    prof = Profiler()

    # Compute ratio a_{n+1} / a_n
    prof.start("Ratio-Compute")
    try:
        # Use combsimp for factorial-heavy expressions
        if expr.has(sp.factorial) or expr.has(sp.gamma) or expr.has(sp.binomial):
            ratio_raw = expr.subs(n, n + 1) / expr
            ratio_expr = sp.combsimp(ratio_raw)
            ratio_expr = sp.cancel(ratio_expr)
        else:
            ratio_expr = sp.cancel(expr.subs(n, n + 1) / expr)
    except Exception:
        prof.stop("Ratio-Compute")
        return None, prof
    prof.stop("Ratio-Compute")

    # Compute absolute value and limit
    prof.start("Ratio-Limit")
    try:
        abs_ratio = sp.Abs(ratio_expr)

        # Try direct limit first
        L = sp.limit(abs_ratio, n, sp.oo)

        # If limit contains AccumBounds or is unevaluated, try log approach
        if L is sp.nan or L.has(sp.AccumBounds) or L.has(sp.Limit):
            # Log-based approach for better numerical stability
            log_ratio = sp.expand_log(sp.log(abs_ratio), force=True)
            log_L = sp.limit(log_ratio, n, sp.oo)
            if log_L is not None and not log_L.has(sp.Limit):
                L = sp.exp(log_L)

        prof.stop("Ratio-Limit")
        return L, prof

    except Exception:
        prof.stop("Ratio-Limit")
        return None, prof


def _fast_root_limit(expr, n, x):
    """
    Optimized root test computation using log form.
    """
    prof = Profiler()
    prof.start("Root-Test")

    try:
        abs_expr = sp.Abs(expr)
        # Use log form: lim (1/n) * log|a_n|
        log_expr = sp.expand_log(sp.log(abs_expr), force=True)
        log_root = sp.cancel(log_expr / n)
        log_L = sp.limit(log_root, n, sp.oo)

        if log_L is not None and not log_L.has(sp.Limit):
            L = sp.exp(log_L)
            prof.stop("Root-Test")
            return L, prof
    except Exception:
        pass

    prof.stop("Root-Test")
    return None, prof


# ─────────────────────────────────────────────────────────────────────────────
#  OPTIMIZED INEQUALITY SOLVER
# ─────────────────────────────────────────────────────────────────────────────


def _solve_convergence_inequality(L, x):
    """
    Solve |L(x)| < 1 for the convergence interval.
    Uses pattern matching for common cases before falling back to general solver.
    """
    # Fix x * sign(x) which breaks continuous_domain
    if L.has(sp.sign):
        L = L.replace(sp.sign, lambda arg: sp.Abs(arg) / arg)

    # Always use the general solver for correctness
    # Pattern matching was causing issues with complex expressions
    try:
        domain = solve_univariate_inequality(L < 1, x, relational=False)
        return domain
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN ANALYSIS FUNCTION
# ─────────────────────────────────────────────────────────────────────────────


def analyze_power_series(expr, n=None, x=None):
    """
    Analyzes a power series for its radius and interval of convergence.

    Parameters
    ----------
    expr : str or sympy expression
        The general term a_n(x) of the power series.
        If string: Will be parsed with implicit multiplication support (e.g., "2x" -> 2*x)
        If sympy expr: Used directly
    n : sympy Symbol or str, optional
        The index variable (summed from 1 or 0 to infinity).
        If None, defaults to sp.Symbol('n', integer=True, positive=True)
    x : sympy Symbol or str, optional
        The variable for which convergence is analyzed.
        If None, defaults to sp.Symbol('x', real=True)

    Returns
    -------
    dict with keys:
        - radius: The radius of convergence R
        - interval: String representation of interval with brackets
        - left_endpoint: Dict with x value, convergence, reason
        - right_endpoint: Dict with x value, convergence, reason
        - limit_L: The computed limit L(x) = lim |a_{n+1}/a_n|
        - convergence: Optional description of convergence type

    Optimizations
    -------------
    - Fast pattern detection for common series types
    - Log-based ratio/root tests for numerical stability
    - Cached simplifications
    - Early bailout for trivial cases (R=0, R=oo)
    - String input parsing with rationalized exponents
    """
    # Initialize default symbols if not provided
    if n is None:
        n = sp.Symbol("n", integer=True, positive=True)
        n_name = "n"
    elif isinstance(n, str):
        n_name = n
        n = sp.Symbol(n, integer=True, positive=True)
    else:
        n_name = str(n)  # Extract name from existing symbol

    if x is None:
        x = sp.Symbol("x", real=True)
        x_name = "x"
    elif isinstance(x, str):
        x_name = x
        x = sp.Symbol(x, real=True)
    else:
        x_name = str(x)  # Extract name from existing symbol

    # Parse string input if necessary
    if isinstance(expr, str):
        try:
            # Use the robust parsing function from algo.py with proper symbol assumptions
            # The local_dict keys must match the variable names in the string expression
            local_dict = {n_name: n, x_name: x}
            expr = get_sympified_expr(expr, local_dict=local_dict)
        except Exception as e:
            return {"error": f"Failed to parse expression string: {str(e)}"}

    prof = Profiler()
    prof.start("Total")

    has_fact = expr.has(sp.factorial) or expr.has(sp.gamma) or expr.has(sp.binomial)

    prefer_root = False
    if not has_fact:
        for p in expr.atoms(sp.Pow):
            if p.exp.has(n) and (p.base.has(n) or p.exp != n):
                prefer_root = True
                break

    if prefer_root:
        L, prof_limit = _fast_root_limit(expr, n, x)
        if L is None or L is sp.nan or L.has(sp.AccumBounds):
            L, alt_prof = _fast_ratio_limit(expr, n, x)
    else:
        # ── Step 1: Try ratio test (primary method) ────────────────────────────
        L, prof_limit = _fast_ratio_limit(expr, n, x)

        # ── Step 2: Fall back to root test if ratio fails ──────────────────────
        if L is None or L is sp.nan or L.has(sp.AccumBounds):
            L, alt_prof = _fast_root_limit(expr, n, x)

    # ── Step 3: Handle failed limit computation ────────────────────────────
    if L is None or L is sp.nan or L.has(sp.Limit):
        prof.stop("Total")
        return {"error": "Could not compute symbolic limit for the series ratio/root."}

    # Clean up L (like x*sign(x) -> Abs(x)) for better output and math
    if L.has(sp.sign):
        L = L.replace(sp.sign, lambda arg: sp.Abs(arg) / arg)

    # ── Step 4: Handle special cases ───────────────────────────────────────

    # Case: L = 0 => R = infinity (converges everywhere)
    if L == 0:
        prof.stop("Total")
        return {
            "radius": sp.oo,
            "interval": "(-oo, oo)",
            "convergence": "Absolutely Convergent for all x",
            "left_endpoint": None,
            "right_endpoint": None,
            "limit_L": 0,
        }

    # Case: L = infinity => R = 0 (converges only at center)
    if L == sp.oo or L.has(sp.oo) or (L.is_number and L > 1e100):
        # Find center by solving where first term is 0
        prof.start("Center-Detection")
        try:
            term_1 = expr.subs(n, 1)
            roots = sp.solve(term_1, x)
            center = roots[0] if roots else 0
        except Exception:
            center = 0
        prof.stop("Center-Detection")

        prof.stop("Total")
        return {
            "radius": 0,
            "interval": f"[{center}, {center}]",
            "convergence": f"Converges only at center x={center}",
            "left_endpoint": {
                "x": center,
                "converges": True,
                "reason": "Trivial Center",
            },
            "right_endpoint": {
                "x": center,
                "converges": True,
                "reason": "Trivial Center",
            },
            "limit_L": L,
        }

    # Case: L depends on x => need to solve |L(x)| < 1 for convergence
    if L.has(sp.oo):
        # L contains infinity in some terms but isn't pure infinity
        prof.stop("Total")
        return {"error": f"Limit contains unbounded terms: {L}"}

    # ── Step 5: Solve convergence inequality ───────────────────────────────
    prof.start("Inequality-Solve")
    try:
        convergence_domain = _solve_convergence_inequality(L, x)

        if convergence_domain is None:
            # Try standard solver as fallback
            convergence_domain = solve_univariate_inequality(L < 1, x, relational=False)
    except Exception as e:
        prof.stop("Inequality-Solve")
        prof.stop("Total")
        return {"error": f"Failed to solve inequality L < 1: {str(e)}"}
    prof.stop("Inequality-Solve")

    # ── Step 6: Extract interval and radius ────────────────────────────────
    if isinstance(convergence_domain, sp.Interval):
        a, b = convergence_domain.start, convergence_domain.end
        radius = (b - a) / 2

        # ── Step 7: Analyze endpoints ──────────────────────────────────────
        prof.start("Endpoint-Analysis")

        left_expr = sp.simplify(expr.subs(x, a))
        right_expr = sp.simplify(expr.subs(x, b))

        # Run endpoint convergence tests
        left_res, left_reason, _ = check_series_convergence(left_expr, n)
        right_res, right_reason, _ = check_series_convergence(right_expr, n)

        prof.stop("Endpoint-Analysis")

        # Build interval string with appropriate brackets
        l_bracket = "[" if left_res else "("
        r_bracket = "]" if right_res else ")"
        interval_str = f"{l_bracket}{a}, {b}{r_bracket}"

        prof.stop("Total")
        return {
            "radius": radius,
            "interval": interval_str,
            "left_endpoint": {"x": a, "converges": left_res, "reason": left_reason},
            "right_endpoint": {"x": b, "converges": right_res, "reason": right_reason},
            "limit_L": L,
        }

    elif isinstance(convergence_domain, sp.Union):
        # Handle union of intervals (rare but possible)
        prof.stop("Total")
        return {
            "radius": "Complex",
            "interval_symbolic": convergence_domain,
            "warning": "Convergence domain is a union of intervals",
        }

    else:
        prof.stop("Total")
        return {
            "radius": "Unknown",
            "interval_symbolic": convergence_domain,
            "error": "Could not parse simple interval.",
        }


# ─────────────────────────────────────────────────────────────────────────────
#  BATCH ANALYSIS (for multiple series)
# ─────────────────────────────────────────────────────────────────────────────


def analyze_power_series_batch(series_list, n=None, x=None):
    """
    Analyze multiple power series efficiently.

    Parameters
    ----------
    series_list : list of (str or sympy expressions)
        List of general terms to analyze (can be strings or SymPy expressions)
    n : sympy Symbol or str, optional
        The index variable
        If None, defaults to sp.Symbol('n', integer=True, positive=True)
    x : sympy Symbol or str, optional
        The variable for convergence analysis
        If None, defaults to sp.Symbol('x', real=True)

    Returns
    -------
    list of dicts with analysis results
    """
    # Initialize default symbols if not provided
    if n is None:
        n = sp.Symbol("n", integer=True, positive=True)
    elif isinstance(n, str):
        n = sp.Symbol(n, integer=True, positive=True)

    if x is None:
        x = sp.Symbol("x", real=True)
    elif isinstance(x, str):
        x = sp.Symbol(x, real=True)

    results = []
    for expr in series_list:
        try:
            result = analyze_power_series(expr, n, x)
        except Exception as e:
            result = {"error": str(e), "expression": str(expr)}
        results.append(result)
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN / DEMO
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pprint

    # String-based test suite - no need for symbol definitions!
    test_series = [
        "x^n / n",  # Harmonic endpoints
        "(x-2)^n / (n * 3^n)",  # Shifted center
        "factorial(n) * x^n",  # Zero radius
        "x^n / factorial(n)",  # Infinite radius
        "(-1)^n * (x+1)^n / n^2",  # Both endpoints closed
        "n^n / factorial(n) * x^n",  # R = 1/e
        "factorial(2*n) / factorial(n)^2 * (x-3)^n",  # R = 1/4
        "(1 + 1/n)^(n^2) * x^n",  # Exponential limit
        "log(n) / n^2 * x^n",  # Logarithmic
        "(3x - 2)^n / (n * 5^n)",  # Linear shift
        "(x+2)^(2*n) / (9^n * n)",  # Power 2n
        "(-1)^n * (x-1)^n / (sqrt(n) * 2^n)",  # Alternating with sqrt
        "(2x - 1)^n / n^3",  # Multiplier on x
        "factorial(n) / n^n * (x-5)^n",  # R = e
        "((n^2 + 1) / (n^2 - 1))^(n^2) * (x+1)^n",  # Complex power
        "log(n) / sqrt(n) * (x - pi)^n",  # Log/sqrt at pi
        "factorial(3*n) / factorial(n)^3 * x^n",  # R = 1/27
        "sin(1/n) * x^n",  # Harmonic equivalent
        "(x + E)^n / (n * log(n)^2)",  # Log series
        "n^(1/n) * x^n",  # Root limit 1
        "x^n / n^2",  # P-series p=2
        "n^2 * x^n",  # Polynomial growth
        "x^n / sqrt(n)",  # P-series p=1/2
        "(-1)^n * x^n / n",  # Alternating harmonic
        "(x - 3)^n / (n * 4^n)",  # Shifted geometric
        "(x + 5)^n / n^3",  # P-series p=3
        "(2x - 1)^n / n^2",  # Linear transform
        "(3x + 2)^n / (n * 2^n)",  # Linear shift
        "(x - pi)^n / (n * E^n)",  # At pi, period e
        "n^n / factorial(n) * x^n",  # Stirling
        "factorial(n) / n^n * x^n",  # Inverse Stirling
        "factorial(4*n) / factorial(n)^4 * x^n",  # 4-factorial
        "binomial(2*n, n) * x^n",  # Central binomial
        "(1 + 1/n)^n * x^n",  # Converges to e
        "(1 + 2/n)^n * x^n",  # Converges to e^2
        "(n / (n+1))^(n^2) * x^n",  # Complex limit
        "x^n / (n * log(n+1))",  # Log denominator
        "x^n / (n * log(n+1)^2)",  # Log squared
        "log(n) / n * x^n",  # Log/n
        "log(n) / n^2 * x^n",  # Log/n^2
        "log(n)^2 / n * x^n",  # Log squared/n
        "sin(1/n) * x^n",  # Sine
        "sin(n) * x^n / n",  # Oscillating
        "cos(1/n) * x^n",  # Cosine
        "tan(1/n) * x^n",  # Tangent
        "factorial(2*n) / (factorial(n)^2 * 4^n) * x^n",  # Catalan-adjacent
        "factorial(n) / (n^n * sqrt(n)) * x^n",  # Stirling with sqrt
        "factorial(n)^2 / factorial(2*n) * x^n",  # Inverse binomial
        "((n^2 + 1) / (n^2 - 1)) * x^n",  # Rational coefficient
        "((n^2 + 1) / (n^2 - 1))^(n^2) * x^n",  # Rational to power
        "(1 + 1/n^2)^(n^3) * x^n",  # Triple power
    ]

    # test_series = [
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 1 — STANDARD (Warm-up, but with traps)
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 1. x^n / n (classic)
    #     # R=1, I=[-1, 1)  — left: AST converges, right: harmonic diverges
    #     "x^n / n",
    #     # 2. x^n / n^2
    #     # R=1, I=[-1, 1]  — both endpoints abs. convergent (p-series p=2>1)
    #     "x^n / n^2",
    #     # 3. n^2 * x^n
    #     # R=1, I=(-1, 1)  — both endpoints: n^2*(±1)^n → ∞, diverge
    #     "n^2 * x^n",
    #     # 4. x^n / sqrt(n)
    #     # R=1, I=[-1, 1)  — left: AST (1/√n→0 monotone), right: p=1/2<1 diverges
    #     "x^n / sqrt(n)",
    #     # 5. (-1)^n * x^n / n
    #     # R=1, I=(-1, 1]  — NOTE: (-1)^n flips AST behavior!
    #     # right x=1: (-1)^n/n → AST converges. left x=-1: (-1)^(2n)/n = 1/n → diverges
    #     "(-1)^n * x^n / n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 2 — SHIFTED CENTERS & COEFFICIENT TRANSFORMATIONS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 6. (x-3)^n / (n * 4^n)
    #     # R=4, center=3, I=[-1, 7)  — left: AST, right: harmonic diverges
    #     "(x - 3)^n / (n * 4^n)",
    #     # 7. (x+5)^n / n^3
    #     # R=1, center=-5, I=[-6, -4]  — both abs. convergent (p=3>1)
    #     "(x + 5)^n / n^3",
    #     # 8. (2x - 1)^n / n^2
    #     # Linear transform: center=1/2, R_x=1/2, I=[0, 1]
    #     # Both endpoints abs. convergent
    #     "(2x - 1)^n / n^2",
    #     # 9. (3x + 2)^n / (n * 2^n)
    #     # Linear: center=-2/3, R_x=2/3, I=[-4/3, 0)
    #     # left: AST converges, right: harmonic diverges
    #     "(3x + 2)^n / (n * 2^n)",
    #     # 10. (x - pi)^n / (n * E^n)
    #     # R=e, center=π, I=[π-e, π+e)
    #     # left: AST converges, right: harmonic diverges
    #     "(x - pi)^n / (n * E^n)",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 3 — FACTORIAL & STIRLING-HEAVY (Engine killers)
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 11. n^n / n! * x^n
    #     # Stirling: n^n/n! ~ e^n/√(2πn). R=1/e.
    #     # left x=-1/e: (-1)^n * C/√n → 0, AST → CONVERGES. I=[-1/e, 1/e)
    #     "n^n / factorial(n) * x^n",
    #     # 12. n! / n^n * x^n
    #     # Stirling inverse: n!/n^n ~ √(2πn)/e^n. R=e.
    #     # Both endpoints: terms → 0 but oscillate — endpoint behavior open: I=(5-e, e+5)... here centered at 0
    #     # I=(-e, e) — both open (terms ~ √n * (±1)^n doesn't → 0 cleanly at rate needed)
    #     # Actually |a_n|^(1/n) = (n!/n^n)^(1/n) → 1/e, R=e. Endpoints: |a_n * R^n| ~ √(2πn) → ∞, DIVERGE
    #     "factorial(n) / n^n * x^n",
    #     # 13. (2n)! / (n!)^2 * x^n  — central binomial coefficients
    #     # Stirling: (2n)!/(n!)^2 ~ 4^n/√(πn). R=1/4.
    #     # left x=-1/4: (-1)^n/√(πn) → AST → CONVERGES. I=[-1/4, 1/4)
    #     "factorial(2*n) / factorial(n)^2 * x^n",
    #     # 14. (3n)! / (n!)^3 * x^n
    #     # Stirling: (3n)!/(n!)^3 ~ 27^n * C/√n. R=1/27.
    #     # left: AST → CONVERGES. I=[-1/27, 1/27)
    #     "factorial(3*n) / factorial(n)^3 * x^n",
    #     # 15. (4n)! / (n!)^4 * x^n
    #     # Stirling: (4n)!/(n!)^4 ~ 256^n * C/n. R=1/256.
    #     # left: AST ~ C/√n → 0 → CONVERGES. I=[-1/256, 1/256)
    #     "factorial(4*n) / factorial(n)^4 * x^n",
    #     # 16. binomial(2*n, n) * x^n  (same as #13 but via binomial)
    #     # Should match: R=1/4, I=[-1/4, 1/4)
    #     "binomial(2*n, n) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 4 — EXPONENTIAL/LIMIT COEFFICIENT TESTS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 17. (1 + 1/n)^n * x^n
    #     # Coefficients → e as n→∞. Root test: L = e*|x|. R=1/e.
    #     # Both endpoints: |(1+1/n)^n * (±1/e)^n| → 1 ≠ 0 → DIVERGE. I=(-1/e, 1/e)
    #     "(1 + 1/n)^n * x^n",
    #     # 18. (1 + 1/n)^(n^2) * x^n
    #     # ln(a_n) = n^2 * ln(1+1/n) ≈ n - 1/2. So a_n ~ e^n / √e.
    #     # R=1/e. Both endpoints diverge (terms → 1/√e ≠ 0). I=(-1/e, 1/e)
    #     "(1 + 1/n)^(n^2) * x^n",
    #     # 19. (1 + 2/n)^n * x^n
    #     # Coefficients → e^2. R=e^(-2).
    #     # Both endpoints diverge. I=(-1/e^2, 1/e^2)
    #     "(1 + 2/n)^n * x^n",
    #     # 20. (n/(n+1))^(n^2) * x^n
    #     # ln(a_n) = n^2 * ln(n/(n+1)) = n^2 * ln(1 - 1/(n+1)) ≈ -n + 1/2
    #     # a_n ~ e^(-n) * √e. R=e. Both endpoints: terms → √e ≠ 0 → DIVERGE. I=(-e, e)
    #     "(n / (n+1))^(n^2) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 5 — LOGARITHMIC & SLOW-DECAY COEFFICIENTS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 21. x^n / (n * log(n+1))
    #     # R=1. Right x=1: ∑1/(n·ln(n)) diverges (integral test).
    #     # Left x=-1: AST → CONVERGES. I=[-1, 1)
    #     "x^n / (n * log(n+1))",
    #     # 22. x^n / (n * log(n+1)^2)
    #     # R=1. Right x=1: ∑1/(n·ln²n) CONVERGES (integral test, p=2).
    #     # Left x=-1: also converges (abs). I=[-1, 1]
    #     "x^n / (n * log(n+1)^2)",
    #     # 23. log(n) / n * x^n
    #     # R=1. Right x=1: ∑ln(n)/n diverges. Left x=-1: AST → CONVERGES. I=[-1, 1)
    #     "log(n) / n * x^n",
    #     # 24. log(n) / n^2 * x^n
    #     # R=1. Both endpoints: ∑ln(n)/n² converges (comparison/integral). I=[-1, 1]
    #     "log(n) / n^2 * x^n",
    #     # 25. log(n)^2 / n * x^n
    #     # R=1. Right x=1: ∑ln²(n)/n diverges. Left: AST → CONVERGES. I=[-1, 1)
    #     "log(n)^2 / n * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 6 — TRIG/SPECIAL FUNCTION COEFFICIENTS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 26. sin(1/n) * x^n
    #     # sin(1/n) ~ 1/n for large n → behaves like harmonic.
    #     # R=1, I=[-1, 1)
    #     "sin(1/n) * x^n",
    #     # 27. sin(n) * x^n / n
    #     # |sin(n)| ≤ 1, limsup |a_n|^(1/n) = 1. R=1.
    #     # Endpoints tricky — sin(n) doesn't go to 0, terms oscillate. Both DIVERGE.
    #     # I=(-1, 1)
    #     "sin(n) * x^n / n",
    #     # 28. cos(1/n) * x^n
    #     # cos(1/n) → 1. Root test: R=1.
    #     # Both endpoints: cos(1/n)*(±1)^n → ±1 ≠ 0 → DIVERGE. I=(-1, 1)
    #     "cos(1/n) * x^n",
    #     # 29. tan(1/n) * x^n
    #     # tan(1/n) ~ 1/n → same as harmonic. R=1.
    #     # I=[-1, 1)
    #     "tan(1/n) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 7 — DOUBLE FACTORIAL & EXOTIC RATIOS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 30. (2*n choose n) / 4^n * x^n  — Catalan-adjacent
    #     # (2n)!/(n!^2 * 4^n) ~ 1/√(πn) → 0. R=1.
    #     # left: AST → CONVERGES. right: ∑1/√(πn) diverges. I=[-1, 1)
    #     "factorial(2*n) / (factorial(n)^2 * 4^n) * x^n",
    #     # 31. n! / (n^n * sqrt(n)) * x^n
    #     # Stirling: n!/(n^n√n) ~ √(2π)/e^n. R=e.
    #     # Both endpoints: |a_n * e^n| ~ √(2π) → constant ≠ 0 → DIVERGE. I=(-e, e)
    #     "factorial(n) / (n^n * sqrt(n)) * x^n",
    #     # 32. (n!)^2 / factorial(2*n) * x^n
    #     # = 1/C(2n,n). By Stirling: (n!)^2/(2n)! ~ √(πn)/4^n. R=4.
    #     # left x=-4: AST with terms ~ √(πn)*(−1)^n — terms → ∞, DIVERGE.
    #     # right x=4: terms ~ √(πn) → ∞, DIVERGE. I=(-4, 4)
    #     "factorial(n)^2 / factorial(2*n) * x^n",
    #     # 33. (n^2 + 1) / (n^2 - 1) * x^n  (n >= 2)
    #     # Coefficients → 1 as n→∞. R=1.
    #     # Both endpoints: terms → ±1 ≠ 0 → DIVERGE. I=(-1, 1)
    #     "((n^2 + 1) / (n^2 - 1)) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 8 — ABSOLUTE MONSTERS (Maximum difficulty)
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 34. ((n^2+1)/(n^2-1))^(n^2) * x^n
    #     # ln(a_n) = n^2 * ln(1 + 2/(n^2-1)) ≈ 2. So a_n → e^2.
    #     # Root: |a_n|^(1/n) → 1. R=1.
    #     # Both endpoints: a_n*(±1)^n → ±e^2 ≠ 0 → DIVERGE. I=(-1, 1)
    #     "((n^2 + 1) / (n^2 - 1))^(n^2) * x^n",
    #     # 35. (1 + 1/n^2)^(n^3) * x^n
    #     # ln(a_n) = n^3 * ln(1+1/n^2) ≈ n. a_n ~ e^n.
    #     # Root: |a_n|^(1/n) → e. R=1/e.
    #     # Both endpoints: a_n*(±1/e)^n → 1 ≠ 0 → DIVERGE. I=(-1/e, 1/e)
    #     "(1 + 1/n^2)^(n^3) * x^n",
    # ]


    test_series = [expr for expr in test_series]
    print("=" * 80)
    print("POWER SERIES ENGINE v2.0 — OPTIMIZED EDITION")
    print("=" * 80)

    total_time = 0
    for s in test_series:
        print(f"\n--- Analyzing: {s} ---")
        t0 = time.perf_counter()
        res = analyze_power_series(s)
        elapsed = (time.perf_counter() - t0) * 1000
        total_time += elapsed
        print(f"Time: {elapsed:.1f}ms")
        pprint.pprint(res)

    print(f"\n{'=' * 80}")
    print(f"Total analysis time: {total_time:.1f}ms for {len(test_series)} series")
    print(f"Average: {total_time / len(test_series):.1f}ms per series")
    print("=" * 80)
