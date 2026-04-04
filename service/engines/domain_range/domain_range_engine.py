import multiprocessing
import queue
import time
import traceback
import warnings
from contextlib import contextmanager
from functools import lru_cache

import colorama
import fast_math_rs
import numpy as np
from colorama import Fore, Style
from scipy.optimize import minimize, minimize_scalar

import sympy as sp
from sympy import (
    Float,
    Abs,
    Add,
    E,
    Integer,
    Max,
    Min,
    Mul,
    Piecewise,
    Pow,
    Rational,
    S,
    Symbol,
    ceiling,
    cot,
    csc,
    diff,
    exp,
    floor,
    fraction,
    gcd,
    im,
    lambdify,
    lcm,
    limit,
    log,
    nan,
    nsimplify,
    oo,
    pi,
    re,
    sec,
    sign,
    simplify,
    solveset,
    sympify,
    tan,
    trigsimp,
    zoo,
)

from sympy import Rational as Rat
from sympy import cos as sym_cos
from sympy import denom as sympy_denom
from sympy import sin as sym_sin

from sympy.calculus.util import (
    AccumBounds,
    continuous_domain,
    function_range,
    maximum,
    minimum,
)
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)
from sympy.sets import (
    Complement,
    EmptySet,
    FiniteSet,
    ImageSet,
    Integers,
    Interval,
    Reals,
    Union,
)

from .worker_process import worker_loop

RUST_AVAILABLE = True
SCIPY_AVAILABLE = True
DEBUG_ENGINE = True
minimize_scalar = None


colorama.init(autoreset=True)
warnings.filterwarnings("ignore")


def debugger(msg, color=Fore.MAGENTA):
    if DEBUG_ENGINE:
        print(f"{color}{Style.DIM}[DEBUG] {msg}{Style.RESET_ALL}")


SYMBOLIC_TIMEOUT = 1.0


class SympyWorker:
    """Persistent subprocess for SymPy work. Killed and restarted on timeout."""

    def __init__(self):
        self.q_in = multiprocessing.Queue()
        self.q_out = multiprocessing.Queue()
        self.p = multiprocessing.Process(
            target=worker_loop,
            args=(self.q_in, self.q_out),
            daemon=True,
        )
        self.p.start()


import threading

_thread_local = threading.local()


def get_worker() -> SympyWorker:
    if not hasattr(_thread_local, "worker") or getattr(_thread_local, "worker") is None:
        _thread_local.worker = SympyWorker()
    return _thread_local.worker


def run_with_timeout(task_type, args, timeout_seconds, default=None):
    """
    Submit a task to the persistent SymPy worker.
    Returns (result, timed_out).
    On timeout the hung process is KILLED so it never becomes a ghost thread.
    """
    worker = get_worker()

    while not worker.q_out.empty():
        try:
            worker.q_out.get_nowait()
        except queue.Empty:
            break

    worker.q_in.put((task_type, args))

    try:
        status, value = worker.q_out.get(timeout=timeout_seconds)
        if status == "err":
            return default, False
        return value, False
    except queue.Empty:
        worker.p.terminate()
        worker.p.join()
        debugger(
            f"TIMEOUT after {timeout_seconds}s — worker process killed and restarted",
            Fore.YELLOW,
        )
        _thread_local.worker = SympyWorker()
        return default, True


# EXPRESSION HELPERS


def _float_to_odd_rational(exp_val):
    """Convert a float exponent to p/q Rational with odd q, or None."""
    for q in [3, 5, 7, 9, 11]:
        for p in range(1, 2 * q):
            target = p / q
            if abs(float(exp_val) - target) < 1e-6:
                return Rational(p, q)
            if abs(float(exp_val) + target) < 1e-6:
                return Rational(-p, q)
    return None


def _rationalize_float_exponents(expr):
    """
    Convert float exponents close to simple fractions into exact Rationals.
    Handles both odd denominators (1/3, 2/3, 1/5 …) and even (1/2, 3/4 …).
    """
    replacements = {}
    for sub in expr.atoms(Pow):
        e = sub.exp
        if e.is_Float or (e.is_Number and not isinstance(e, (Integer, Rational))):
            r = _float_to_odd_rational(e)
            if r is not None:
                replacements[sub] = Pow(sub.base, r)
            else:
                matched = False
                for q in [2, 4, 6, 8]:
                    for p in range(1, 2 * q):
                        if abs(float(e) - p / q) < 1e-6:
                            replacements[sub] = Pow(sub.base, Rational(p, q))
                            matched = True
                            break
                        if abs(float(e) + p / q) < 1e-6:
                            replacements[sub] = Pow(sub.base, Rational(-p, q))
                            matched = True
                            break
                    if matched:
                        break
    for old, new in replacements.items():
        expr = expr.subs(old, new)
    return expr


def get_sympified_expr(user_input, local_dict=None):
    """
    Parse a string input into a SymPy expression with proper transformations.

    Parameters
    ----------
    user_input : str
        Mathematical expression as a string
    local_dict : dict, optional
        Dictionary mapping variable names to SymPy symbols with specific assumptions.
        Example: {'n': Symbol('n', integer=True, positive=True), 'x': Symbol('x', real=True)}
        If None, symbols are created with default assumptions.

    Returns
    -------
    sympy expression
        Parsed and rationalized expression with proper symbol assumptions
    """

    # ── Universal base dictionary for robust math parsing ──
    # This prevents fragmentation and ensures all engines map 'arctan', 'e', 'ln', etc. correctly.
    base_dict = {
        # Constants
        "e": E,
        "E": sp.E,
        "pi": sp.pi,
        "π": sp.pi,  # Unicode pi symbol support
        # Inverse Trig (human 'arc' prefix -> SymPy 'a' prefix)
        "arctan": sp.atan,
        "arcsin": sp.asin,
        "arccos": sp.acos,
        "arccot": sp.acot,
        "arcsec": sp.asec,
        "arccsc": sp.acsc,
        # Inverse Hyperbolic (human 'arc' prefix -> SymPy 'a' prefix)
        "arctanh": sp.atanh,
        "arcsinh": sp.asinh,
        "arccosh": sp.acosh,
        "arccoth": sp.acoth,
        "arcsech": sp.asech,
        "arccsch": sp.acsch,
        # Logarithms
        "ln": sp.log,
        "log": sp.log,
        # Absolute value and rounding
        "abs": sp.Abs,
        "Abs": sp.Abs,
        "floor": sp.floor,
        "ceil": sp.ceiling,
        "ceiling": sp.ceiling,
        # Miscellaneous wrappers/aliases
        "sgn": sp.sign,
        "sign": sp.sign,
    }

    # Merge the universal base functions with any custom logic/symbols provided (like x, n, a)
    final_dict = base_dict.copy()
    if local_dict:
        final_dict.update(local_dict)

    transformations = standard_transformations + (
        implicit_multiplication_application,
        convert_xor,
    )
    expr = parse_expr(
        user_input, transformations=transformations, local_dict=final_dict
    )
    expr = _rationalize_float_exponents(expr)
    return expr


# =============================================================================
# EDGE-CASE DETECTION HELPERS
# =============================================================================

PERIODIC_UNBOUNDED_FUNCS = {tan, cot, sec, csc}
PERIODIC_FULL_RANGE_FUNCS = {tan, cot}
PERIODIC_GAPPED_FUNCS = {sec, csc}

# Bounded inverse trig functions and their ranges
BOUNDED_INVERSE_TRIG = {
    sp.atan: (Interval.open(-pi / 2, pi / 2)),  # (-π/2, π/2)
    sp.asin: (Interval(-pi / 2, pi / 2)),  # [-π/2, π/2]
    sp.acos: (Interval(0, pi)),  # [0, π]
    sp.acot: (Interval.open(0, pi)),  # (0, π)
    sp.asec: (
        Union(Interval.Ropen(0, pi / 2), Interval.Lopen(pi / 2, pi))
    ),  # [0,π/2) ∪ (π/2,π]
    sp.acsc: (
        Union(Interval.Ropen(-pi / 2, 0), Interval.Lopen(0, pi / 2))
    ),  # [-π/2,0) ∪ (0,π/2]
}


def get_outermost_function(f):
    """
    Get the outermost function of an expression.
    For atan(2x/(1-x^2)), returns atan.
    """
    if hasattr(f, "func") and f.func is not None:
        return f.func
    return None


def is_bounded_inverse_trig(f, x):
    """
    Detect if the outermost function is a bounded inverse trig function.
    Returns (is_bounded, range_interval) or (False, None).

    Critical: atan(...), asin(...), acos(...) are ALWAYS bounded
    regardless of what's inside the argument.
    """
    outer_func = get_outermost_function(f)
    if outer_func in BOUNDED_INVERSE_TRIG:
        return True, BOUNDED_INVERSE_TRIG[outer_func]
    return False, None


def is_domain_bounded(domain):
    """
    Check if domain is a bounded (finite) set.
    Returns (is_bounded, lower, upper) or (False, None, None).
    """
    try:
        if isinstance(domain, Interval):
            if domain.start.is_finite and domain.end.is_finite:
                return True, float(domain.start.evalf()), float(domain.end.evalf())
        elif isinstance(domain, FiniteSet):
            vals = [float(v.evalf()) for v in domain]
            return True, min(vals), max(vals)
        elif isinstance(domain, Union):
            # All components must be bounded
            all_bounded = True
            lower = float("inf")
            upper = float("-inf")
            for comp in domain.args:
                if isinstance(comp, Interval):
                    if comp.start.is_finite and comp.end.is_finite:
                        lower = min(lower, float(comp.start.evalf()))
                        upper = max(upper, float(comp.end.evalf()))
                    else:
                        all_bounded = False
                        break
                elif isinstance(comp, FiniteSet):
                    for v in comp:
                        fv = float(v.evalf())
                        lower = min(lower, fv)
                        upper = max(upper, fv)
                else:
                    all_bounded = False
                    break
            if all_bounded and lower != float("inf"):
                return True, lower, upper
    except Exception:
        pass
    return False, None, None


def is_bounded_trig_squared(f, x):
    """
    Detect if f(x) = (trig(g(x)))^2 where trig is sin or cos.
    These are bounded to [0, 1], not [0, oo).
    """
    if f.func is Pow and f.exp == 2:
        base = f.base
        # sin(...)^2 or cos(...)^2
        if base.func in (sym_sin, sym_cos):
            return True
        # More complex: sin(...)^2 + cos(...)^2 etc. would need more checks
    return False


def is_squared_expression(f, x):
    """
    Detect if f(x) is a squared expression: (g(x))^2 or Abs(g(x))^2.
    Returns True if the entire expression is provably non-negative.
    """
    # Direct (expr)**2
    if f.func is Pow and f.exp == 2:
        return True

    # Abs(expr)**2
    if f.func is Pow and f.exp == 2 and f.base.func is Abs:
        return True

    # More general: any even power of a real expression
    if f.func is Pow:
        if f.exp.is_integer and f.exp.is_even and f.exp > 0:
            # Base must be real-valued for this to guarantee non-negative
            return True

    # Abs(anything)
    if f.func is Abs:
        return True

    # Check for products of squared terms: (g(x))^2 * (h(x))^2
    if f.func is Mul:
        # All factors must be squared or positive
        all_nonneg = True
        for factor in f.args:
            if not is_squared_expression(factor, x):
                if not (factor.is_positive or (factor.is_number and float(factor) > 0)):
                    all_nonneg = False
                    break
        if all_nonneg:
            return True

    return False


def is_abs_or_abs_like(f, x):
    """
    Detect if f involves Abs in a way that makes it unbounded as x→±∞.
    E.g., abs(x), abs(x - 3), |x| + 1/|x|
    """
    if f.has(Abs):
        # Check if any Abs term has a linear-in-x argument
        for sub in f.atoms(Abs):
            arg = sub.args[0]
            if arg.has(x):
                # Check if the argument is linear or polynomial in x
                coeff = arg.as_poly(x) if arg.is_polynomial(x) else None
                if coeff is not None and coeff.degree() >= 1:
                    return True
    return False


def detect_bounded_exponential(f, x, domain):
    """
    Detect functions like x^(1-x), x^(-x), x^(1/x) that have bounded range.
    These are of the form x^g(x) where the exponential behavior is self-limiting.

    IMPORTANT: Must check ALL parts of the domain, not just positive values.
    For example, (1+1/x)^x is bounded on x>0 but unbounded on x<-1.

    Returns (is_bounded, lower_bound, upper_bound) or (False, None, None).
    """
    if f.func is not Pow:
        return False, None, None

    base, exp_val = f.args

    # Must be x^g(x) form where base involves x and exponent involves x
    if not (base.has(x) and exp_val.has(x)):
        return False, None, None

    # Special cases we can recognize:
    # x^(1-x) on (0, ∞): max at x=1, value=1, goes to 0 at both ends
    # x^(-x) on (0, ∞): max at x=1/e, value=e^(1/e), goes to 1 at 0+, goes to 0 at ∞
    # x^(1/x) on (0, ∞): max at x=e, value=e^(1/e)
    # BUT: (1+1/x)^x on (-∞,-1)∪(0,∞) is unbounded on the (-∞,-1) branch!

    try:
        f_num = make_safe_f_num_vectorized(f, x)

        # Build test points from ALL parts of the domain
        all_test_pts = []

        # Helper to extract intervals from domain
        def get_intervals(dom):
            if hasattr(dom, "args") and dom.func.__name__ == "Union":
                intervals = []
                for part in dom.args:
                    intervals.extend(get_intervals(part))
                return intervals
            elif isinstance(dom, Interval):
                return [dom]
            else:
                return []

        intervals = get_intervals(domain)

        # If no structured intervals found, fall back to positive sampling only
        # (for simple domains like (0, ∞))
        if not intervals:
            # Default to positive sampling
            all_test_pts = np.concatenate(
                [
                    np.linspace(0.001, 0.1, 20),
                    np.linspace(0.1, 1, 50),
                    np.linspace(1, 10, 50),
                    np.linspace(10, 100, 30),
                    np.array([0.0001, 0.00001]),
                ]
            )
        else:
            for intv in intervals:
                lo = float(intv.start) if intv.start != -oo else -1e6
                hi = float(intv.end) if intv.end != oo else 1e6

                # Skip tiny intervals
                if hi - lo < 1e-6:
                    continue

                # Add buffer from boundaries for open intervals
                eps = min(0.001, (hi - lo) * 0.01)
                if intv.left_open:
                    lo = lo + eps
                if intv.right_open:
                    hi = hi - eps

                # Sample this interval
                if lo > 0:
                    # Positive interval
                    pts = np.concatenate(
                        [
                            np.linspace(lo, min(lo * 10, hi), 30),
                            np.linspace(max(lo, 0.1), min(hi, 100), 50),
                        ]
                    )
                elif hi < 0:
                    # Negative interval - CRITICAL for (1+1/x)^x type functions
                    pts = np.linspace(lo, hi, 80)
                    # Add points near the boundary (e.g., near -1 for (1+1/x)^x)
                    if hi > -2:
                        # Dense sampling near upper boundary
                        pts = np.concatenate(
                            [pts, np.linspace(max(lo, hi - 1), hi - 0.001, 50)]
                        )
                else:
                    # Interval crossing zero
                    pts = np.concatenate(
                        [
                            np.linspace(lo, -0.001, 40) if lo < 0 else np.array([]),
                            np.linspace(0.001, hi, 40) if hi > 0 else np.array([]),
                        ]
                    )

                all_test_pts.append(pts)

            all_test_pts = (
                np.concatenate(all_test_pts) if all_test_pts else np.array([])
            )

        if len(all_test_pts) < 20:
            return False, None, None

        vals = f_num(all_test_pts)
        valid = np.isfinite(vals) & np.isreal(vals)

        if np.sum(valid) < 20:
            return False, None, None

        valid_vals = vals[valid].astype(float)

        # Check for unbounded behavior - if ANY values are very large, NOT bounded
        if np.any(np.abs(valid_vals) > 1e6):
            return False, None, None

        # Check if all values are in a reasonable bounded range
        if np.all(valid_vals > -1e-10) and np.all(valid_vals < 1e10):
            # Check limits at boundaries of each interval
            has_unbounded_limit = False

            for intv in intervals if intervals else []:
                # Check behavior near boundaries
                if intv.end != oo and intv.right_open:
                    # Check limit as x approaches upper bound from left
                    test_near_hi = float(intv.end) - 0.0001
                    try:
                        val_hi = f_num(test_near_hi)
                        if np.isfinite(val_hi) and abs(val_hi) > 100:
                            has_unbounded_limit = True
                            break
                    except:
                        pass

                if intv.start != -oo and intv.left_open:
                    # Check limit as x approaches lower bound from right
                    test_near_lo = float(intv.start) + 0.0001
                    try:
                        val_lo = f_num(test_near_lo)
                        if np.isfinite(val_lo) and abs(val_lo) > 100:
                            has_unbounded_limit = True
                            break
                    except:
                        pass

            if has_unbounded_limit:
                return False, None, None

            # Additional check: sample VERY close to singular boundaries
            # For (1+1/x)^x, as x → -1+, value → ∞
            for intv in intervals if intervals else []:
                if intv.end != oo and intv.right_open:
                    for delta in [0.01, 0.001, 0.0001]:
                        test_pt = float(intv.end) - delta
                        try:
                            v = f_num(test_pt)
                            if np.isfinite(v) and abs(v) > 50:
                                return False, None, None
                        except:
                            pass

            max_val = np.max(valid_vals)
            min_val = max(0, np.min(valid_vals))  # These are typically positive

            # Verify the bounds are tight by finding the actual maximum
            from scipy.optimize import minimize_scalar

            try:
                # Find maximum in positive region
                neg_f = lambda xv: -f_num(float(xv)) if f_num(float(xv)) > 0 else 1e10
                res = minimize_scalar(neg_f, bounds=(0.1, 10), method="bounded")
                if res.success:
                    max_val = max(max_val, -res.fun)
            except:
                pass

            # Snap to clean values
            max_val = snap_to_clean_value(max_val)
            min_val = snap_to_clean_value(min_val)

            if min_val >= 0 and max_val <= 10:  # Reasonable bounded range
                return True, min_val, max_val

    except Exception:
        pass

    return False, None, None


@lru_cache(maxsize=128)
def _has_reciprocal_trig(f, var):
    """Detect 1/sin(x), 1/cos(x), a/sin(x), sec(x), csc(x) etc."""
    _, denom_expr = fraction(f)
    if denom_expr.has(sym_sin) or denom_expr.has(sym_cos):
        return True
    if f.has(sec) or f.has(csc):
        return True
    return False


def is_periodically_unbounded(f):
    return any(f.has(fc) for fc in PERIODIC_UNBOUNDED_FUNCS)


def is_periodically_unbounded_no_gap(f):
    if _has_reciprocal_trig(f, None):
        return False
    return any(f.has(fc) for fc in PERIODIC_FULL_RANGE_FUNCS)


# =============================================================================
# INTEGER-VALUED OUTPUT DETECTION  (FIX-01)
# =============================================================================


def _is_term_integer_valued(term):
    """
    Return True if an expression is guaranteed integer-valued.
    Handles: integers, floor(expr), ceiling(expr), n*floor(expr), combinations.
    """
    # Plain integer constant
    if getattr(term, "is_integer", False) and term.is_number:
        return True

    # Direct floor / ceiling call
    if term.func in (floor, ceiling):
        return True

    # Product of integer-valued terms
    if term.func is Mul:
        return all(_is_term_integer_valued(a) for a in term.args)

    # Sum of integer-valued terms
    if term.func is Add:
        return all(_is_term_integer_valued(a) for a in term.args)

    return False


def has_integer_valued_output(f):
    """
    Robustly determine whether the ENTIRE expression is integer-valued.
    """
    return _is_term_integer_valued(f)


# =============================================================================
# PERIODIC DOMAIN DETECTION & EXPANSION  (FIX-02)
# =============================================================================

# Known fundamental periods for SymPy trig functions
_TRIG_PERIODS = {
    sym_sin: 2 * pi,
    sym_cos: 2 * pi,
    tan: pi,
    cot: pi,
    sec: 2 * pi,
    csc: 2 * pi,
}


def _fundamental_period(f, x):
    """
    Attempt to determine the fundamental period of f(x).

    Strategy
    --------
    1. Walk all trig sub-expressions and collect their periods scaled by the
       inner linear coefficient.  e.g. sin(3x) has period 2π/3.
    2. Return the LCM of all found periods (as a SymPy expression).
    3. If nothing is found, return None.
    """

    candidate_periods = []

    for func_cls, base_period in _TRIG_PERIODS.items():
        for sub in f.atoms(func_cls):
            arg = sub.args[0]
            # Only handle linear arguments a*x + b
            coeff = arg.coeff(x)
            if coeff != 0 and coeff.is_real:
                try:
                    period = base_period / abs(coeff)
                    candidate_periods.append(period)
                except Exception:
                    pass

    if not candidate_periods:
        return None

    # LCM of symbolic periods: for simple rationals this works cleanly
    result = candidate_periods[0]
    for p in candidate_periods[1:]:
        try:
            # lcm(a/b, c/d) = lcm(a,c)/gcd(b,d)
            result = (result * p) / gcd(result, p)
        except Exception:
            # Fallback: take the maximum — still better than nothing
            result = Max(result, p)

    return result


def _get_trig_functions_in_expr(f):
    """Return the set of trig function classes present in f."""
    found = set()
    for func_cls in _TRIG_PERIODS:
        if f.has(func_cls):
            found.add(func_cls)
    return found


def _domain_is_strict_subset_of_period(domain, period_float, tolerance=1e-6):
    """
    Return True when `domain` is a single finite interval whose width is
    strictly less than one full period.  That is the hallmark of SymPy
    having returned only the principal-period component.
    """
    if not isinstance(domain, Interval):
        return False
    if not (domain.start.is_finite and domain.end.is_finite):
        return False
    width = float((domain.end - domain.start).evalf())
    return width < period_float - tolerance


def expand_periodic_domain(f, x, domain):
    """
    Post-process a domain returned by SymPy's continuous_domain() to handle
    cases where SymPy only found one period of a genuinely periodic domain.

    Examples that trigger this:
        sqrt(sin(x))       → SymPy gives [0, π]   → should be ⋃ₙ [2nπ, (2n+1)π]
        sqrt(cos(x))       → SymPy gives [-π/2, π/2]  → periodic union
        log(sin(x))        → SymPy gives (0, π)    → periodic union
        sqrt(sin(x)+cos(x))→ SymPy gives one interval → periodic union
        1/(sin(x)+2)       → domain is all reals   → no expansion needed

    Returns
    -------
    (expanded_domain, was_expanded: bool)

    The expansion covers ±NUM_PERIODS periods so the union is finite but
    large enough for any practical display / downstream computation.
    """
    NUM_PERIODS = 12  # ±12 periods — display ~24 intervals

    # ── Guard 1: must have at least one trig function ──────────────────────
    trig_funcs_present = _get_trig_functions_in_expr(f)
    if not trig_funcs_present:
        return domain, False

    # ── Guard 2: period must be determinable ───────────────────────────────
    period_sym = _fundamental_period(f, x)
    if period_sym is None:
        return domain, False

    try:
        period_float = float(period_sym.evalf())
    except Exception:
        return domain, False

    if period_float <= 0 or period_float > 1e6:
        return domain, False

    # ── Guard 3: domain must look like a truncated single period ───────────
    if isinstance(domain, Complement):
        base = domain.args[0]
        if isinstance(base, Interval):
            component_list = [base]
        elif isinstance(base, Union) and all(
            isinstance(a, Interval) for a in base.args
        ):
            component_list = list(base.args)
        else:
            return domain, False
    elif isinstance(domain, Interval):
        component_list = [domain]
    elif isinstance(domain, Union) and all(
        isinstance(a, Interval) for a in domain.args
    ):
        component_list = list(domain.args)
    else:
        return domain, False

    # Compute the span from the leftmost start to rightmost end
    try:
        span_start = min(float(c.start.evalf()) for c in component_list)
        span_end = max(float(c.end.evalf()) for c in component_list)
    except Exception:
        return domain, False

    span_width = span_end - span_start

    # If the span already covers a full period or more, trust SymPy
    if span_width >= period_float - 1e-6:
        return domain, False

    # ── Guard 4: numerical verification ───────────────────────────────────
    # Confirm that f is actually defined one period later at a representative
    # interior point of the domain.
    try:
        f_num = make_safe_f_num_vectorized(f, x)

        # Pick a point well inside the first-period component
        test_pt_base = span_start + span_width * 0.5
        test_pt_next = test_pt_base + period_float

        val_base = f_num(test_pt_base)
        val_next = f_num(test_pt_next)

        base_ok = bool(np.isfinite(val_base) and np.isreal(val_base))
        next_ok = bool(np.isfinite(val_next) and np.isreal(val_next))

        if not (base_ok and next_ok):
            debugger(
                f"Periodic expansion aborted: base_ok={base_ok}, next_ok={next_ok}",
                Fore.YELLOW,
            )
            return domain, False

        # Also verify a point BETWEEN periods is invalid (true gap)
        gap_pt = span_end + period_float * 0.25
        val_gap = f_num(gap_pt)
        gap_is_invalid = (not np.isfinite(val_gap)) or (not np.isreal(val_gap))

        if not gap_is_invalid:
            # The function is valid between periods → domain is all (or almost all)
            # reals and SymPy already returned something reasonable.
            return domain, False

    except Exception as exc:
        debugger(f"Periodic expansion numerical check failed: {exc}", Fore.YELLOW)
        return domain, False

    # ── Build the periodic union ───────────────────────────────────────────
    try:
        all_intervals = []
        for k in range(-NUM_PERIODS, NUM_PERIODS + 1):
            shift = k * period_sym
            for comp in component_list:
                new_start = comp.start + shift
                new_end = comp.end + shift
                all_intervals.append(
                    Interval(new_start, new_end, comp.left_open, comp.right_open)
                )

        expanded = Union(*all_intervals)
        debugger(
            f"Periodic domain expanded: {len(component_list)} component(s) × "
            f"{2 * NUM_PERIODS + 1} periods (period={period_float:.4f})",
            Fore.GREEN,
        )
        return expanded, True

    except Exception as exc:
        debugger(f"Periodic expansion union build failed: {exc}", Fore.YELLOW)
        return domain, False


def _format_periodic_union(obj, fmt_val_fn, fmt_interval_fn):
    """
    Detect a uniformly-periodic Union and format it as  ⋃_{n∈ℤ} [a+nT, b+nT]
    instead of listing dozens of identical-looking intervals.

    Returns a formatted string if periodic, else None.
    """
    if not isinstance(obj, Union):
        return None

    parts = [a for a in obj.args if isinstance(a, Interval)]
    if len(parts) < 5:
        return None

    # Sort by start point
    try:
        parts_sorted = sorted(parts, key=lambda iv: float(iv.start.evalf()))
    except Exception:
        return None

    # Check equal spacing (period)
    try:
        spacings = [
            float((parts_sorted[i + 1].start - parts_sorted[i].start).evalf())
            for i in range(len(parts_sorted) - 1)
        ]
        lengths = [float((p.end - p.start).evalf()) for p in parts_sorted]
        tol = 1e-6
        if (
            max(abs(s - spacings[0]) for s in spacings) > tol
            or max(abs(l - lengths[0]) for l in lengths) > tol
        ):
            return None
    except Exception:
        return None

    # Pick the anchor interval closest to x=0
    anchor = min(parts_sorted, key=lambda iv: abs(float(iv.start.evalf())))

    lb = "(" if anchor.left_open else "["
    rb = ")" if anchor.right_open else "]"

    try:
        a_str = fmt_val_fn(anchor.start)
        b_str = fmt_val_fn(anchor.end)
        T_str = fmt_val_fn(parts_sorted[1].start - parts_sorted[0].start)
        return f"U_{{n in Z}} {lb}{a_str} + {T_str}*n, {b_str} + {T_str}*n{rb}"
    except Exception:
        return None


def has_real_odd_root(expr, var):
    """x**(p/q) with odd q — real for all real x."""
    for sub in expr.atoms(Pow):
        if sub.base.has(var):
            if isinstance(sub.exp, Rational):
                if sub.exp.q % 2 == 1 and sub.exp.q > 1:
                    return True
            elif sub.exp.is_Float or sub.exp.is_Number:
                r = _float_to_odd_rational(sub.exp)
                if r is not None and r.q % 2 == 1 and r.q > 1:
                    return True
    return False


def rewrite_real_roots(expr, var):
    """Rewrite x**(p/q) (odd q) so numpy evaluates it correctly for x < 0."""
    replacements = {}
    for sub in expr.atoms(Pow):
        if sub.base.has(var):
            rat_exp = None
            if isinstance(sub.exp, Rational):
                rat_exp = sub.exp
            elif sub.exp.is_Float or sub.exp.is_Number:
                rat_exp = _float_to_odd_rational(sub.exp)
            if rat_exp is not None:
                p, q = rat_exp.p, rat_exp.q
                if q % 2 == 1 and q > 1:
                    if p % 2 == 1:
                        replacements[sub] = sign(sub.base) * Abs(sub.base) ** rat_exp
                    else:
                        replacements[sub] = Abs(sub.base) ** rat_exp
    for old, new in replacements.items():
        expr = expr.subs(old, new)
    return expr


def point_in_domain_fast(pt, gen_min, gen_max, f_num):
    """Fast numeric domain check — avoids SymPy .contains() in hot loops."""
    if not (gen_min <= pt <= gen_max):
        return False
    try:
        val = f_num(pt)
        return bool(np.isfinite(val) and np.isreal(val))
    except Exception:
        return False


# =============================================================================
# VECTORISED NUMERICAL EVALUATION
# =============================================================================


def make_safe_f_num_vectorized(f, x):
    """
    Returns a callable that accepts both scalars and numpy arrays.
    Uses true C-level numpy vectorisation.
    """
    f_rewritten = rewrite_real_roots(f, x) if has_real_odd_root(f, x) else f

    modules = [
        {
            "Heaviside": lambda t: np.heaviside(t, 0.5),
            "Max": np.maximum,
            "Min": np.minimum,
        },
        "numpy",
    ]
    f_raw = lambdify(x, f_rewritten, modules=modules)

    def safe_f(x_input):
        if np.isscalar(x_input):
            try:
                result = f_raw(x_input)
                if isinstance(result, complex):
                    return result.real if abs(result.imag) < 1e-10 else np.nan
                result = float(result)
                return result if np.isfinite(result) else np.nan
            except Exception:
                return np.nan

        x_arr = np.asarray(x_input, dtype=float)
        try:
            result = f_raw(x_arr)
            if np.isscalar(result):
                result = np.full_like(x_arr, result, dtype=float)
            result = np.asarray(
                result, dtype=complex if np.iscomplexobj(result) else float
            )
            if np.iscomplexobj(result):
                valid = np.abs(np.imag(result)) < 1e-10
                return np.where(valid, np.real(result), np.nan)
            return np.where(np.isfinite(result), result, np.nan)
        except Exception:
            return np.full_like(x_arr, np.nan, dtype=float)

    return safe_f


# =============================================================================
# SYMBOLIC LIMIT / BEHAVIOUR ANALYSIS
# =============================================================================


def analyze_function_behavior(f, x, domain):
    has_inf_pos = False
    has_inf_neg = False
    left_lim = None
    right_lim = None

    f_for_limits = rewrite_real_roots(f, x) if has_real_odd_root(f, x) else f

    try:
        lp = limit(f_for_limits, x, oo)
        if lp == oo:
            has_inf_pos = True
            right_lim = oo
        elif lp == -oo:
            has_inf_neg = True
            right_lim = -oo
        elif isinstance(lp, AccumBounds):
            if lp.max == oo:
                has_inf_pos = True
            if lp.min == -oo:
                has_inf_neg = True
        elif lp.has(oo) and (lp.has(AccumBounds) or lp.has(sign)):
            has_inf_pos = True
            has_inf_neg = True
        elif lp not in [zoo, nan] and not lp.has(oo):
            right_lim = lp
    except Exception:
        pass

    try:
        ln = limit(f_for_limits, x, -oo)
        if ln == oo:
            has_inf_pos = True
            left_lim = oo
        elif ln == -oo:
            has_inf_neg = True
            left_lim = -oo
        elif isinstance(ln, AccumBounds):
            if ln.max == oo:
                has_inf_pos = True
            if ln.min == -oo:
                has_inf_neg = True
        elif ln.has(oo) and (ln.has(AccumBounds) or ln.has(sign)):
            has_inf_pos = True
            has_inf_neg = True
        elif ln not in [zoo, nan] and not ln.has(oo):
            left_lim = ln
    except Exception:
        pass

    if f_for_limits.has(Abs):
        try:
            if limit(f_for_limits, x, oo) == oo:
                has_inf_pos = True
            if limit(f_for_limits, x, -oo) == oo:
                has_inf_pos = True
        except Exception:
            pass

    try:
        d = sympy_denom(f_for_limits)
        if d != 1:
            sing_pts = solveset(d, x, S.Reals)
            if isinstance(sing_pts, FiniteSet):
                for pt in sing_pts:
                    try:
                        ll = limit(f_for_limits, x, pt, "-")
                        if ll == oo:
                            has_inf_pos = True
                        elif ll == -oo:
                            has_inf_neg = True
                        elif ll not in [zoo, nan] and not ll.has(oo):
                            sing_limits.append((ll, pt))

                        lr = limit(f_for_limits, x, pt, "+")
                        if lr == oo:
                            has_inf_pos = True
                        elif lr == -oo:
                            has_inf_neg = True
                        elif lr not in [zoo, nan] and not lr.has(oo):
                            sing_limits.append((lr, pt))
                    except Exception:
                        pass
    except Exception:
        pass

    return has_inf_neg, has_inf_pos, left_lim, right_lim


# =============================================================================
# NUMERICAL HELPERS
# =============================================================================


def find_critical_points_numerical(f, x, domain, f_num):
    critical_points = []
    try:
        df, timed_out = run_with_timeout("diff", (f, x), 1.0)
        if timed_out or df is None:
            return critical_points
        df_num = lambdify(x, df, modules=["numpy"])

        x_min = (
            float(domain.inf) + 1e-6
            if (hasattr(domain, "inf") and domain.inf.is_finite)
            else -100.0
        )
        x_max = (
            float(domain.sup) - 1e-6
            if (hasattr(domain, "sup") and domain.sup.is_finite)
            else 100.0
        )

        x_samples = np.linspace(x_min, x_max, 2000)
        dy = df_num(x_samples)
        if isinstance(dy, np.ndarray) and dy.size > 1:
            signs = np.sign(dy)
            idx = np.where(np.diff(signs) != 0)[0]
            if len(idx):
                for i in idx:
                    yv = f_num(x_samples[i])
                    if np.isfinite(yv) and np.isreal(yv):
                        critical_points.append((float(x_samples[i]), float(yv)))
    except Exception:
        pass
    return critical_points


def detect_unbounded_oscillation(f_num, gen_min, gen_max):
    has_inf_neg = has_inf_pos = False

    with np.errstate(all="ignore"):
        if gen_min < 0:
            try:
                neg_extremes = []
                for i in range(1, 6):
                    xv = -(10**i)
                    if xv >= gen_min:
                        y = f_num(xv)
                        if np.isfinite(y) and np.isreal(y):
                            neg_extremes.append(abs(float(np.real(y))))
                if len(neg_extremes) >= 3:
                    ratios = [
                        neg_extremes[i + 1] / neg_extremes[i]
                        if neg_extremes[i] > 1e-10
                        else 0
                        for i in range(len(neg_extremes) - 1)
                    ]
                    if any(r > 10 for r in ratios):
                        has_inf_neg = has_inf_pos = True
                        debugger(
                            f"Unbounded oscillation (neg dir): ratios={ratios[:3]}",
                            Fore.YELLOW,
                        )
            except Exception:
                pass

        try:
            pos_extremes = []
            for i in range(1, 6):
                xv = 10**i
                if xv <= gen_max:
                    y = f_num(xv)
                    if np.isfinite(y) and np.isreal(y):
                        pos_extremes.append(abs(float(np.real(y))))
            if len(pos_extremes) >= 3:
                ratios = [
                    pos_extremes[i + 1] / pos_extremes[i]
                    if pos_extremes[i] > 1e-10
                    else 0
                    for i in range(len(pos_extremes) - 1)
                ]
                if any(r > 10 for r in ratios):
                    has_inf_neg = has_inf_pos = True
                    debugger(
                        f"Unbounded oscillation (pos dir): ratios={ratios[:3]}",
                        Fore.YELLOW,
                    )
        except Exception:
            pass

        if gen_min < -10:
            try:
                sample_min = max(gen_min, -500)
                sample_max = min(-10, gen_max)
                if sample_min < sample_max:
                    xs = np.linspace(sample_min, sample_max, 100)
                    try:
                        ys = f_num(xs)
                        if np.isscalar(ys):
                            ys = np.full_like(xs, ys)
                        ys = np.asarray(ys, dtype=float)
                    except Exception:
                        ys = np.array([f_num(xi) for xi in xs], dtype=float)
                    valid = np.isfinite(ys)
                    if np.sum(valid) > 20 and np.max(np.abs(ys[valid])) > 1e10:
                        has_inf_neg = has_inf_pos = True
                        debugger("Large values at negative x detected", Fore.YELLOW)
            except Exception:
                pass

        # --- LINEAR GROWTH DETECTION (for abs(x) type functions) ---
        # Check if function values grow linearly/polynomially at extreme x
        try:
            test_large = [100, 1000, 10000, 100000]
            large_vals = []
            for xv in test_large:
                v = f_num(xv)
                if np.isfinite(v) and np.isreal(v):
                    large_vals.append((xv, float(v)))

            if len(large_vals) >= 3:
                # Check if y-values are growing (linear or faster)
                ys_large = [v[1] for v in large_vals]
                if all(ys_large[i + 1] > ys_large[i] for i in range(len(ys_large) - 1)):
                    # Check if growth is unbounded (not leveling off)
                    if ys_large[-1] > 10 * ys_large[0]:
                        has_inf_pos = True
                        debugger(
                            f"Linear/polynomial growth detected: y({test_large[-1]})={ys_large[-1]:.2e}",
                            Fore.YELLOW,
                        )

            # Same for negative x
            large_vals_neg = []
            for xv in [-100, -1000, -10000, -100000]:
                v = f_num(xv)
                if np.isfinite(v) and np.isreal(v):
                    large_vals_neg.append((xv, float(v)))

            if len(large_vals_neg) >= 3:
                ys_large_neg = [v[1] for v in large_vals_neg]
                # Check for growth in magnitude
                abs_ys = [abs(y) for y in ys_large_neg]
                if all(abs_ys[i + 1] > abs_ys[i] for i in range(len(abs_ys) - 1)):
                    if abs_ys[-1] > 10 * abs_ys[0]:
                        if ys_large_neg[-1] > 0:
                            has_inf_pos = True
                        else:
                            has_inf_neg = True
                        debugger(
                            f"Linear/polynomial growth (neg x): y({-100000})={ys_large_neg[-1]:.2e}",
                            Fore.YELLOW,
                        )
        except Exception:
            pass

    return has_inf_neg, has_inf_pos


def snap_to_clean_value(val, tolerance=None):
    """Snap numerical value to nearby mathematically significant constant."""
    if not np.isfinite(val):
        return val

    if tolerance is None:
        magnitude = max(abs(val), 1e-10)
        tolerance = magnitude * 1e-6

    clean_values = [
        0,
        1,
        -1,
        2,
        -2,
        0.5,
        -0.5,
        np.pi,
        -np.pi,
        np.pi / 2,
        -np.pi / 2,
        np.pi / 4,
        -np.pi / 4,
        np.pi / 3,
        -np.pi / 3,
        np.pi / 6,
        -np.pi / 6,
        np.e,
        -np.e,
        1 / np.e,
        -1 / np.e,
        np.sqrt(2),
        -np.sqrt(2),
        np.sqrt(2) / 2,
        -np.sqrt(2) / 2,
        np.sqrt(3),
        -np.sqrt(3),
        np.sqrt(3) / 2,
        -np.sqrt(3) / 2,
        1 / 3,
        -1 / 3,
        2 / 3,
        -2 / 3,
        1 / 4,
        -1 / 4,
        3 / 4,
        -3 / 4,
        np.exp(-1 / np.e),
        -np.exp(-1 / np.e),
    ]
    for clean in clean_values:
        if abs(val - clean) < tolerance:
            return clean

    # Relaxed snapping for exactly zero, helping open-bound limiting values
    # like log(x-floor(x)) where numerical optimizer hits e.g. -1e-6
    if abs(val) < max(tolerance, 1e-5):
        return 0.0

    return val


def detect_range_gaps(y_values_sorted, all_y_sorted=None, min_gap_fraction=0.15):
    """
    Find significant gaps in observed y-values using a two-pass approach.
    """
    n = len(y_values_sorted)
    if n < 200:
        return []

    total_range = y_values_sorted[-1] - y_values_sorted[0]
    if total_range < 1e-10:
        return []

    if all_y_sorted is None:
        all_y_sorted = y_values_sorted

    diffs = np.diff(y_values_sorted)
    median_diff = np.median(diffs)

    stat_threshold = max(median_diff * 10.0, 0.3)
    abs_threshold = min_gap_fraction * total_range
    threshold = max(stat_threshold, min(abs_threshold, 2.0))

    gaps = []
    for i in range(len(diffs)):
        if diffs[i] > threshold:
            gaps.append((y_values_sorted[i], y_values_sorted[i + 1]))

    if len(gaps) > 1:
        merged = [gaps[0]]
        for gs, ge in gaps[1:]:
            prev_gs, prev_ge = merged[-1]
            if gs - prev_ge < median_diff * 5:
                merged[-1] = (prev_gs, ge)
            else:
                merged.append((gs, ge))
        gaps = merged

    verified = []
    for gs, ge in gaps:
        inside = np.searchsorted(all_y_sorted, ge, "left") - np.searchsorted(
            all_y_sorted, gs, "right"
        )
        if inside <= 1 and (ge - gs) > median_diff * 5:
            verified.append((gs, ge))

    return verified


# =============================================================================
# MAIN NUMERICAL RANGE FINDER
# =============================================================================


def smart_numerical_range(f, x, domain_sympy, behavior_info=None):
    """
    Hybrid numerical range finder.
    behavior_info: (has_inf_neg, has_inf_pos, left_lim, right_lim, sing_limits)
    """
    if not SCIPY_AVAILABLE:
        return f"{Fore.YELLOW}SciPy missing.", "N/A"

    try:
        f_num = make_safe_f_num_vectorized(f, x)
        debugger("Numerical range computation starting...", Fore.CYAN)
        debugger("Computing X_grid", Fore.CYAN)

        # --- STEP 0.0: BOUNDED INVERSE TRIG CHECK ---
        # atan(...), asin(...), acos(...) are ALWAYS bounded regardless of argument
        is_bounded_inv_trig, inv_trig_range = is_bounded_inverse_trig(f, x)
        if is_bounded_inv_trig:
            debugger(
                f"Detected bounded inverse trig: range = {inv_trig_range}", Fore.GREEN
            )
            # Format the interval properly
            if isinstance(inv_trig_range, Interval):
                lo = inv_trig_range.start
                hi = inv_trig_range.end
                lo_open = inv_trig_range.left_open
                hi_open = inv_trig_range.right_open

                def fmt_pi(v):
                    if v == pi:
                        return "pi"
                    if v == -pi:
                        return "-pi"
                    if v == pi / 2:
                        return "pi/2"
                    if v == -pi / 2:
                        return "-pi/2"
                    return str(v)

                if lo_open and hi_open:
                    return (
                        f"Interval.open({fmt_pi(lo)}, {fmt_pi(hi)})",
                        "Exact (bounded inverse trig)",
                    )
                elif lo_open:
                    return (
                        f"Interval.Lopen({fmt_pi(lo)}, {fmt_pi(hi)})",
                        "Exact (bounded inverse trig)",
                    )
                elif hi_open:
                    return (
                        f"Interval.Ropen({fmt_pi(lo)}, {fmt_pi(hi)})",
                        "Exact (bounded inverse trig)",
                    )
                else:
                    return (
                        f"Interval({fmt_pi(lo)}, {fmt_pi(hi)})",
                        "Exact (bounded inverse trig)",
                    )
            return str(inv_trig_range), "Exact (bounded inverse trig)"

        # --- STEP 0.0b: BOUNDED DOMAIN CHECK ---
        # If domain is bounded (finite closed interval), range MUST be bounded
        # for a continuous function. This is a mathematical fact.
        domain_bounded, dom_lo, dom_hi = is_domain_bounded(domain_sympy)
        if domain_bounded:
            debugger(f"Bounded domain detected: [{dom_lo}, {dom_hi}]", Fore.CYAN)

        # --- STEP 0.1: SQUARED EXPRESSION CHECK ---
        # If f(x) = (g(x))^2 or similar, range must be [0, ∞) or [0, max]
        is_squared = is_squared_expression(f, x)
        if is_squared:
            debugger("Detected squared/abs expression: range must be >= 0", Fore.GREEN)

        # --- STEP 0: PERIODIC FULL-RANGE SHORTCUT (tan, cot) ---
        if is_periodically_unbounded_no_gap(f):
            debugger("Detected tan/cot — full range with no gaps", Fore.YELLOW)
            return "Interval(-oo, oo)", "Exact (periodic unbounded)"

        # --- STEP 0.2: BOUNDED EXPONENTIAL CHECK ---
        # Functions like x^(1-x) that are self-limiting
        is_bounded, bound_min, bound_max = detect_bounded_exponential(
            f, x, domain_sympy
        )
        if is_bounded:
            debugger(
                f"Detected bounded exponential: range [{bound_min}, {bound_max}]",
                Fore.GREEN,
            )

            def fmt(v):
                if abs(v) < 1e-9:
                    return "0"
                return f"{v:.6f}".rstrip("0").rstrip(".")

            # Check if bounds are attained
            # For x**(1-x) on [0, ∞): f(0) = 0^1 = 0 is attained!
            # We need to check if the domain includes 0 and f(0) = 0
            lo_open = True  # Default: assume 0 is approached as limit
            hi_open = False  # Usually attains maximum

            if bound_min <= 0:
                # Check if 0 is in the domain and f(0) = 0
                try:
                    # Check if domain contains 0
                    zero_in_domain = False
                    if isinstance(domain_sympy, Interval):
                        if domain_sympy.start == 0 and not domain_sympy.left_open:
                            zero_in_domain = True
                        elif domain_sympy.contains(0):
                            zero_in_domain = True
                    elif hasattr(domain_sympy, "contains"):
                        zero_in_domain = domain_sympy.contains(0) == True

                    if zero_in_domain:
                        # Check if f(0) = 0
                        f_at_zero = f_num(0.0)
                        if np.isfinite(f_at_zero) and abs(f_at_zero) < 1e-9:
                            lo_open = False  # 0 is actually attained!
                            debugger(
                                "Bounded exponential: f(0)=0 is attained, closed at 0",
                                Fore.GREEN,
                            )
                except Exception:
                    pass

            if lo_open and not hi_open:
                return (
                    f"Interval.Lopen({fmt(bound_min)}, {fmt(bound_max)})",
                    "Hybrid Analysis (bounded exponential)",
                )
            elif lo_open and hi_open:
                return (
                    f"Interval.open({fmt(bound_min)}, {fmt(bound_max)})",
                    "Hybrid Analysis (bounded exponential)",
                )
            else:
                return (
                    f"Interval({fmt(bound_min)}, {fmt(bound_max)})",
                    "Hybrid Analysis (bounded exponential)",
                )

        # --- STEP 0.3: BOUNDED TRIG SQUARED CHECK ---
        # Functions like (sin(g(x)))^2 or (cos(g(x)))^2 are bounded to [0, 1]
        if is_bounded_trig_squared(f, x):
            debugger("Detected bounded trig squared: range [0, 1]", Fore.GREEN)
            return "Interval(0, 1)", "Exact (bounded trig squared)"

        # --- STEP 1: REUSE PRE-COMPUTED BEHAVIOUR INFO ---
        if behavior_info is not None:
            has_inf_neg, has_inf_pos, left_lim, right_lim, sing_limits = behavior_info
        else:
            has_inf_neg = has_inf_pos = False
            left_lim = right_lim = None
            sing_limits = []

        # --- STEP 2: DOMAIN BOUNDS ---
        # For Union domains (e.g. periodic), use the overall numeric extremes
        # rather than just the .inf/.sup of the outer set (which may not exist).
        gen_min, gen_max = -100.0, 100.0
        domain_is_bounded_left = domain_is_bounded_right = False

        try:
            if hasattr(domain_sympy, "inf") and getattr(
                domain_sympy.inf, "is_finite", False
            ):
                gen_min = float(domain_sympy.inf) + 1e-8
                domain_is_bounded_left = True
            elif (
                hasattr(domain_sympy, "inf")
                and getattr(domain_sympy.inf, "is_finite") == False
            ):
                domain_is_bounded_left = False
            else:
                pass  # fallback

            if hasattr(domain_sympy, "sup") and getattr(
                domain_sympy.sup, "is_finite", False
            ):
                gen_max = float(domain_sympy.sup) - 1e-8
                domain_is_bounded_right = True
            elif (
                hasattr(domain_sympy, "sup")
                and getattr(domain_sympy.sup, "is_finite") == False
            ):
                domain_is_bounded_right = False
        except Exception:
            pass

        # --- STEP 2.3: NEAR-SINGULARITY LIMIT CHECK (catches log(sin(x))→-∞ or →+∞) ---
        # When the domain has open endpoints or boundary singularities, probe the
        # function value from inside the domain near those boundaries.  Useful for
        # log(g(x)) where g→0⁺ gives f→-∞, or log(1+sqrt(...)) where inner→+∞.
        try:
            boundary_pts = []
            if isinstance(domain_sympy, Union):
                for comp in domain_sympy.args:
                    if isinstance(comp, Interval):
                        if comp.start.is_finite:
                            boundary_pts.append(float(comp.start.evalf()))
                        if comp.end.is_finite:
                            boundary_pts.append(float(comp.end.evalf()))
            elif hasattr(domain_sympy, "inf") and domain_sympy.inf.is_finite:
                boundary_pts.append(float(domain_sympy.inf.evalf()))
            if hasattr(domain_sympy, "sup") and domain_sympy.sup.is_finite:
                boundary_pts.append(float(domain_sympy.sup.evalf()))

            for bp in boundary_pts:
                for eps in [1e-3, 1e-5, 1e-7]:
                    for interior_pt in [bp + eps, bp - eps]:
                        try:
                            v = f_num(interior_pt)
                            if np.isfinite(v):
                                if v < -1e4 and not has_inf_neg:
                                    has_inf_neg = True
                                    debugger(
                                        f"Near-singularity probe: f({interior_pt:.2e})={v:.2e} → -∞ inferred",
                                        Fore.YELLOW,
                                    )
                                if v > 1e4 and not has_inf_pos:
                                    has_inf_pos = True
                                    debugger(
                                        f"Near-singularity probe: f({interior_pt:.2e})={v:.2e} → +∞ inferred",
                                        Fore.YELLOW,
                                    )
                        except Exception:
                            pass
                    if has_inf_neg and has_inf_pos:
                        break
                if has_inf_neg and has_inf_pos:
                    break

            # --- LOGARITHMIC GROWTH DETECTION ---
            # For log-type functions, values may not reach 1e4 but grow monotonically
            # toward boundary. Detect consistent growth pattern.
            if not (has_inf_neg and has_inf_pos):
                for bp in boundary_pts:
                    # Check from both sides
                    for direction in [+1, -1]:  # +1 = right of bp, -1 = left of bp
                        vals = []
                        eps_vals = [1e-2, 1e-4, 1e-6, 1e-8, 1e-10]
                        for eps in eps_vals:
                            pt = bp + direction * eps
                            try:
                                v = f_num(pt)
                                if np.isfinite(v):
                                    vals.append(v)
                                else:
                                    break  # Outside domain
                            except Exception:
                                break

                        if len(vals) >= 4:
                            # Check if monotonically increasing (→ +∞) or decreasing (→ -∞)
                            diffs = [
                                vals[i + 1] - vals[i] for i in range(len(vals) - 1)
                            ]
                            if all(d > 0 for d in diffs) and vals[-1] > vals[0] + 2:
                                # Monotonically increasing, significant growth
                                has_inf_pos = True
                                debugger(
                                    f"Logarithmic growth to +∞ near x={bp} ({vals[0]:.2f}→{vals[-1]:.2f})",
                                    Fore.YELLOW,
                                )
                            elif all(d < 0 for d in diffs) and vals[-1] < vals[0] - 2:
                                # Monotonically decreasing
                                has_inf_neg = True
                                debugger(
                                    f"Logarithmic growth to -∞ near x={bp} ({vals[0]:.2f}→{vals[-1]:.2f})",
                                    Fore.YELLOW,
                                )
                    if has_inf_neg and has_inf_pos:
                        break
        except Exception:
            pass

        # --- STEP 2.4: EXTENDED DOMAIN BOUNDARY CHECK ---
        # For functions like log(1+sqrt((x-1)/(x+1))), check asymptotic behavior
        # near excluded points (e.g. x=-1 which is just outside the domain).
        # Probe OUTSIDE the domain to detect vertical asymptotes.
        if not (has_inf_neg and has_inf_pos):
            try:
                # Find domain boundaries and check just inside
                if hasattr(domain_sympy, "inf") and domain_sympy.inf.is_finite:
                    boundary = float(domain_sympy.inf.evalf())
                    # Probe just inside the domain
                    for eps in [1e-2, 1e-4, 1e-6]:
                        v = f_num(boundary + eps)
                        if np.isfinite(v):
                            if v > 1e4:
                                has_inf_pos = True
                                debugger(
                                    f"Domain boundary asymptote: +∞ near x={boundary}",
                                    Fore.YELLOW,
                                )
                            elif v < -1e4:
                                has_inf_neg = True
                                debugger(
                                    f"Domain boundary asymptote: -∞ near x={boundary}",
                                    Fore.YELLOW,
                                )
                            break

                if hasattr(domain_sympy, "sup") and domain_sympy.sup.is_finite:
                    boundary = float(domain_sympy.sup.evalf())
                    for eps in [1e-2, 1e-4, 1e-6]:
                        v = f_num(boundary - eps)
                        if np.isfinite(v):
                            if v > 1e4:
                                has_inf_pos = True
                                debugger(
                                    f"Domain boundary asymptote: +∞ near x={boundary}",
                                    Fore.YELLOW,
                                )
                            elif v < -1e4:
                                has_inf_neg = True
                                debugger(
                                    f"Domain boundary asymptote: -∞ near x={boundary}",
                                    Fore.YELLOW,
                                )
                            break
            except Exception:
                pass

        # --- PREPARE LIMIT POINTS ---
        limit_points = []

        def add_limit(val, x_source=None, is_neg_inf=False, is_pos_inf=False):
            try:
                if is_neg_inf and domain_is_bounded_left:
                    return
                if is_pos_inf and domain_is_bounded_right:
                    return
                if val is not None and (
                    isinstance(val, (int, float, complex))
                    or (
                        getattr(val, "is_real", False)
                        and getattr(val, "is_number", False)
                    )
                ):
                    fval = float(val)
                    limit_points.append((snap_to_clean_value(fval), x_source))
            except Exception:
                pass

        add_limit(left_lim, -np.inf, is_neg_inf=True)
        add_limit(right_lim, np.inf, is_pos_inf=True)
        for sl in sing_limits:
            if isinstance(sl, tuple) and len(sl) == 2:
                add_limit(sl[0], sl[1])
            else:
                add_limit(sl)

        # --- STEP 2.5: OSCILLATION DETECTION ---
        if not (has_inf_neg and has_inf_pos):
            osc_neg, osc_pos = detect_unbounded_oscillation(f_num, gen_min, gen_max)
            if osc_neg:
                has_inf_neg = True
            if osc_pos:
                has_inf_pos = True

        # --- STEP 3: MONOTONE EXTREME-VALUE CHECKS ---
        if not (has_inf_neg and has_inf_pos):
            for sign_dir, bounded in [
                (1, domain_is_bounded_right),
                (-1, domain_is_bounded_left),
            ]:
                if bounded:
                    continue
                try:
                    test_vals = []
                    for i in range(2, 6):
                        v = f_num(sign_dir * 10**i)
                        if np.isfinite(v) and np.isreal(v):
                            test_vals.append(float(v))
                    if len(test_vals) >= 2:
                        if all(
                            test_vals[k] > test_vals[k - 1]
                            for k in range(1, len(test_vals))
                        ):
                            if test_vals[-1] > 1e10:
                                has_inf_pos = True
                        if all(
                            test_vals[k] < test_vals[k - 1]
                            for k in range(1, len(test_vals))
                        ):
                            if test_vals[-1] < -1e10:
                                has_inf_neg = True
                except Exception:
                    pass

        might_have_gaps = _has_reciprocal_trig(f, x) or f.has(sec) or f.has(csc)

        if has_inf_neg and has_inf_pos and not might_have_gaps:
            debugger("Fully unbounded, no gaps — skipping grid search", Fore.GREEN)
            return "Interval(-oo, oo)", "Hybrid Analysis"

        if might_have_gaps and not (has_inf_neg and has_inf_pos):
            for pt in [0, np.pi, np.pi / 2, 2 * np.pi]:
                try:
                    for eps in [1e-5, 1e-7]:
                        for p in [pt + eps, pt - eps]:
                            v = f_num(p)
                            if np.isfinite(v):
                                if v > 1e4:
                                    has_inf_pos = True
                                if v < -1e4:
                                    has_inf_neg = True
                except Exception:
                    pass
        if might_have_gaps and has_inf_neg and has_inf_pos:
            try:
                dense_x = np.linspace(0.001, np.pi - 0.001, 5000)
                dense_y = f_num(dense_x)
                if np.isscalar(dense_y):
                    dense_y = np.full_like(dense_x, dense_y, dtype=float)
                dense_y = np.asarray(dense_y, dtype=float)
                dense_y_valid = dense_y[np.isfinite(dense_y)]

                if len(dense_y_valid) > 100:
                    dense_x_neg = np.linspace(-np.pi + 0.001, -0.001, 5000)
                    dense_y_neg = f_num(dense_x_neg)
                    if np.isscalar(dense_y_neg):
                        dense_y_neg = np.full_like(
                            dense_x_neg, dense_y_neg, dtype=float
                        )
                    dense_y_neg = np.asarray(dense_y_neg, dtype=float)
                    dense_y_neg_valid = dense_y_neg[np.isfinite(dense_y_neg)]

                    if len(dense_y_neg_valid) > 100:
                        all_branch = np.concatenate([dense_y_valid, dense_y_neg_valid])
                        pos_vals = all_branch[all_branch > 0]
                        neg_vals = all_branch[all_branch < 0]

                        if len(pos_vals) > 0 and len(neg_vals) > 0:
                            min_p = float(np.min(pos_vals))
                            max_n = float(np.max(neg_vals))
                            for lv, _ in limit_points:
                                if isinstance(lv, (float, int, np.floating)):
                                    if lv >= 0 and lv < min_p:
                                        min_p = lv
                                    if lv <= 0 and lv > max_n:
                                        max_n = lv
                            gap_upper = snap_to_clean_value(min_p)
                            gap_lower = snap_to_clean_value(max_n)
                            in_gap = all_branch[
                                (all_branch > gap_lower) & (all_branch < gap_upper)
                            ]
                            if len(in_gap) == 0 and gap_upper - gap_lower > 0.1:

                                def fv(v):
                                    return (
                                        "0"
                                        if abs(v) < 1e-9
                                        else f"{v:.6f}".rstrip("0").rstrip(".")
                                    )

                                debugger(
                                    f"Reciprocal trig gap: ({fv(gap_lower)}, {fv(gap_upper)})",
                                    Fore.CYAN,
                                )
                                result = (
                                    f"Union(Interval(-oo, {fv(gap_lower)}), "
                                    f"Interval({fv(gap_upper)}, oo))"
                                )
                                return result, "Hybrid Analysis (gap detected)"
            except Exception as exc:
                debugger(f"Reciprocal trig fast path failed: {exc}", Fore.YELLOW)

        # --- STEP 4: GRID SEARCH ---
        all_points = []

        X_grid = None
        if isinstance(domain_sympy, Union):
            pts_list = []
            components = [a for a in domain_sympy.args if isinstance(a, Interval)]
            pts_per_comp = max(50, 800 // max(1, len(components)))
            for comp in components:
                lo = (
                    float(comp.start.evalf()) + 1e-8 if comp.start.is_finite else -100.0
                )
                hi = float(comp.end.evalf()) - 1e-8 if comp.end.is_finite else 100.0
                lo = max(lo, -100.0)
                hi = min(hi, 100.0)
                if lo < hi:
                    pts_list.append(np.linspace(lo, hi, pts_per_comp))
            if pts_list:
                X_grid = np.unique(np.concatenate(pts_list))
            else:
                X_grid = np.array([])

        if X_grid is None and RUST_AVAILABLE:
            try:
                X_grid = np.array(
                    fast_math_rs.generate_multi_scale_grid(
                        float(gen_min), float(gen_max), [10.0, 100.0], 800
                    )
                )
            except Exception:
                X_grid = None

        if X_grid is None or len(X_grid) == 0:

            def get_sample_points(domain, scales):
                points = []
                if isinstance(domain, Union):
                    for interval in domain.args:
                        i_inf = getattr(interval, "inf", None)
                        i_sup = getattr(interval, "sup", None)
                        if i_inf is not None and i_sup is not None:
                            low = (
                                float(i_inf) + 1e-8
                                if getattr(i_inf, "is_finite", False)
                                else -100.0
                            )
                            high = (
                                float(i_sup) - 1e-8
                                if getattr(i_sup, "is_finite", False)
                                else 100.0
                            )
                            if low < high:
                                points.extend(
                                    np.linspace(
                                        max(low, -100), min(high, 100), 500
                                    ).tolist()
                                )
                else:
                    for scale in scales:
                        s_min = max(gen_min, -scale)
                        s_max = min(gen_max, scale)
                        if s_min < s_max:
                            points.extend(np.linspace(s_min, s_max, 800).tolist())
                return np.array(sorted(set(points)))

            X_grid = get_sample_points(domain_sympy, [10, 100])

        debugger("Computing Y_grid", Fore.CYAN)
        if len(X_grid) > 0:
            try:
                Y_grid = f_num(X_grid)
                if np.isscalar(Y_grid):
                    Y_grid = np.full_like(X_grid, Y_grid, dtype=float)
                Y_grid = np.asarray(Y_grid, dtype=float)
                mask = np.isfinite(Y_grid)
                if np.any(mask):
                    all_points.extend(list(zip(X_grid[mask], Y_grid[mask])))

                debugger("Rust adaptive grid", Fore.CYAN)
                if RUST_AVAILABLE and np.any(mask):
                    try:
                        df_sym, to_diff = run_with_timeout("diff", (f, x), 1.0)
                        if to_diff or df_sym is None:
                            raise ValueError("diff timed out")
                        df_num = lambdify(x, df_sym, modules=["numpy"])
                        df_vals = df_num(X_grid)
                        if np.isscalar(df_vals):
                            df_vals = np.full_like(X_grid, df_vals)
                        df_vals = np.asarray(df_vals, dtype=float)

                        find_sc = getattr(fast_math_rs, "find_sign_changes", None)
                        adap_g = getattr(fast_math_rs, "adaptive_grid", None)
                        if find_sc and adap_g:
                            sign_change_idxs = find_sc(df_vals)
                            if len(sign_change_idxs) > 0:
                                critical_xs = X_grid[
                                    np.array(sign_change_idxs)
                                ].tolist()
                                X_dense = np.array(
                                    adap_g(
                                        float(gen_min),
                                        float(gen_max),
                                        0,
                                        critical_xs,
                                        0.1,
                                    )
                                )
                                if len(X_dense) > 0:
                                    Y_dense = f_num(X_dense)
                                    if np.isscalar(Y_dense):
                                        Y_dense = np.full_like(
                                            X_dense, Y_dense, dtype=float
                                        )
                                    Y_dense = np.asarray(Y_dense, dtype=float)
                                    dm = np.isfinite(Y_dense)
                                    if np.any(dm):
                                        all_points.extend(
                                            list(zip(X_dense[dm], Y_dense[dm]))
                                        )
                    except Exception:
                        pass
            except Exception:
                pass

        special_points = [
            0.001,
            0.01,
            0.1,
            0.5,
            1,
            2,
            5,
            10,
            100,
            -0.001,
            -0.01,
            -0.1,
            -0.5,
            -1,
            -2,
            -5,
            -10,
            -100,
        ]

        # Add trig function critical points for floor/ceiling of trig functions
        # sin(x) peaks at π/2 + 2πn, troughs at -π/2 + 2πn
        # cos(x) peaks at 2πn, troughs at π + 2πn
        if f.has(sym_sin) or f.has(sym_cos) or f.has(floor) or f.has(ceiling):
            for n in range(-5, 6):
                # sin peaks/troughs
                special_points.append(np.pi / 2 + 2 * np.pi * n)  # sin = 1
                special_points.append(-np.pi / 2 + 2 * np.pi * n)  # sin = -1
                # cos peaks/troughs
                special_points.append(2 * np.pi * n)  # cos = 1
                special_points.append(np.pi + 2 * np.pi * n)  # cos = -1
                # sin+cos combined peaks
                special_points.append(np.pi / 4 + 2 * np.pi * n)  # sin+cos = sqrt(2)
                special_points.append(
                    -3 * np.pi / 4 + 2 * np.pi * n
                )  # sin+cos = -sqrt(2)

        # For floor/ceil, add points just before and after integers
        if f.has(floor) or f.has(ceiling):
            for i in range(-10, 11):
                special_points.append(i - 1e-9)
                special_points.append(i + 1e-9)
                special_points.append(i - 0.001)
                special_points.append(i + 0.001)

        if isinstance(domain_sympy, Union):
            for interval in domain_sympy.args[:-1]:
                sup = getattr(interval, "sup", None)
                if sup is not None:
                    gp = float(sup)
                    for eps in [1e-3, 1e-5, 1e-7]:
                        special_points.extend([gp - eps, gp + eps])

        for pt in special_points:
            if not point_in_domain_fast(pt, gen_min, gen_max, f_num):
                continue
            try:
                val = f_num(pt)
                if np.isfinite(val) and np.isreal(val):
                    all_points.append((float(pt), float(val)))
            except Exception:
                pass

        if not all_points and not limit_points:
            return "Numerical Eval Failed (All Complex/NaN)", "Error"

        # --- STEP 5: CRITICAL POINTS ---
        debugger("Finding critical points numerical", Fore.CYAN)
        for cp in find_critical_points_numerical(f, x, domain_sympy, f_num):
            if isinstance(cp, tuple) and len(cp) == 2:
                cx, cy = cp
                if np.isfinite(cy) and np.isreal(cy):
                    all_points.append((cx, cy))

        # --- STEP 6: SCIPY OPTIMISATION ---
        all_y_values = [p[1] for p in all_points]
        refined_min = min(all_y_values) if all_y_values else np.inf
        refined_max = max(all_y_values) if all_y_values else -np.inf

        for lv, _ in limit_points:
            if np.isfinite(lv):
                all_y_values.append(lv)

        debugger("Minimizing scalar", Fore.CYAN)
        if minimize_scalar is not None:
            bounds_lo = max(gen_min, -100)
            bounds_hi = min(gen_max, 100)

            def safe_f_opt(xv):
                try:
                    v = f_num(float(xv))
                    if np.isfinite(v) and np.isreal(v):
                        return float(v)
                    return np.inf
                except Exception:
                    return np.inf

            try:
                r = minimize_scalar(
                    safe_f_opt,
                    bounds=(bounds_lo, bounds_hi),
                    method="bounded",
                    options={"maxiter": 200, "xatol": 1e-7},
                )
                if r.success and np.isfinite(r.fun) and r.fun < 1e99:
                    refined_min = min(refined_min, r.fun)
                    all_points.append((r.x, float(r.fun)))
                    all_y_values.append(float(r.fun))
            except Exception:
                pass

            try:
                r = minimize_scalar(
                    lambda xv: -safe_f_opt(xv),
                    bounds=(bounds_lo, bounds_hi),
                    method="bounded",
                    options={"maxiter": 200, "xatol": 1e-7},
                )
                if r.success and np.isfinite(r.fun) and r.fun > -1e99:
                    refined_max = max(refined_max, -r.fun)
                    all_points.append((r.x, float(-r.fun)))
                    all_y_values.append(float(-r.fun))
            except Exception:
                pass

        if all_y_values:
            refined_min = min(refined_min, min(all_y_values))
            refined_max = max(refined_max, max(all_y_values))

        # --- STEP 6.5: SQUARED EXPRESSION CONSTRAINT ---
        # If f(x) = (g(x))^2 or similar, the minimum must be >= 0
        if is_squared:
            if refined_min < 0:
                refined_min = 0
            if has_inf_neg:
                has_inf_neg = False  # Can't go to -∞ if squared
                debugger(
                    "Squared expression: overriding has_inf_neg to False", Fore.GREEN
                )
            # For Abs(g(x)) or (g(x))^2, check if g(x)=0 has solutions
            # If so, the minimum is exactly 0
            if refined_min > 0 and refined_min < 0.1:
                # Small positive min - might actually be 0
                inner_expr = None
                if f.func is Abs:
                    inner_expr = f.args[0]
                elif f.func is Pow and f.exp == 2:
                    inner_expr = f.base

                if inner_expr is not None:
                    try:
                        # Try to find zeros of inner expression numerically
                        inner_num = lambdify(x, inner_expr, "numpy")
                        test_points = np.linspace(-100, 100, 10001)
                        inner_vals = inner_num(test_points)
                        if np.isscalar(inner_vals):
                            inner_vals = np.full_like(test_points, inner_vals)
                        inner_vals = np.asarray(inner_vals, dtype=float)
                        # Check for sign changes (zeros)
                        valid_mask = np.isfinite(inner_vals)
                        if np.sum(valid_mask) > 10:
                            valid_vals = inner_vals[valid_mask]
                            has_positive = np.any(valid_vals > 1e-10)
                            has_negative = np.any(valid_vals < -1e-10)
                            has_near_zero = np.any(np.abs(valid_vals) < 1e-6)
                            if (has_positive and has_negative) or has_near_zero:
                                debugger(
                                    "Abs/squared inner expr crosses zero: min = 0",
                                    Fore.GREEN,
                                )
                                refined_min = 0
                    except Exception:
                        pass

        # --- STEP 6.6: BOUNDED DOMAIN CONSTRAINT (EXTREME VALUE THEOREM) ---
        # MATHEMATICAL FACT: If domain is bounded (finite closed interval),
        # then the range of a continuous function MUST be bounded.
        # This overrides any false positives from timeout/numerical heuristics.
        if domain_bounded:
            if has_inf_neg or has_inf_pos:
                debugger(
                    f"Bounded domain [{dom_lo}, {dom_hi}] → range MUST be bounded (Extreme Value Theorem)",
                    Fore.GREEN,
                )
                has_inf_neg = False
                has_inf_pos = False

        # --- STEP 7: APPLY INFINITY FLAGS ---
        final_min = -np.inf if has_inf_neg else refined_min
        final_max = np.inf if has_inf_pos else refined_max

        final_min = snap_to_clean_value(final_min)
        final_max = snap_to_clean_value(final_max)

        # --- STEP 7.5: HORIZONTAL ASYMPTOTE GAP DETECTION ---
        # If a function approaches a finite limit at ±∞ but never attains it,
        # that value creates a gap in the range (e.g., log(1+sqrt((x-1)/(x+1))) → log(2))
        horizontal_asymptote_gaps = []

        def _get_finite_limit_value(lim):
            """Extract float value from a sympy limit if it's finite."""
            if lim is None:
                return None
            try:
                if hasattr(lim, "is_finite") and lim.is_finite:
                    return float(lim)
                elif isinstance(lim, (int, float)):
                    return float(lim)
                elif hasattr(lim, "is_number") and lim.is_number:
                    fv = float(lim)
                    if np.isfinite(fv):
                        return fv
            except Exception:
                pass
            return None

        def _detect_numerical_limit(f_num, direction, num_points=20):
            """
            Numerically detect if f(x) converges to a finite limit as x → ±∞.
            Returns the limit value if detected, None otherwise.
            """
            try:
                if direction > 0:
                    # x → +∞: test at large positive values
                    test_xs = [10**i for i in range(2, 7)]  # 100, 1000, ..., 1e6
                else:
                    # x → -∞: test at large negative values
                    test_xs = [-(10**i) for i in range(2, 7)]

                vals = []
                for tx in test_xs:
                    try:
                        v = f_num(tx)
                        if np.isfinite(v) and np.isreal(v):
                            vals.append(float(v))
                    except Exception:
                        pass

                if len(vals) >= 3:
                    # Check if values are converging (differences decreasing)
                    diffs = [abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1)]
                    if all(d < 0.1 for d in diffs[-2:]):  # Last differences small
                        # Values seem to converge - estimate the limit
                        est_limit = vals[-1]
                        # Verify it's truly converging (not just slow growth)
                        if abs(vals[-1] - vals[-2]) < 0.01:
                            return est_limit
            except Exception:
                pass
            return None

        left_lim_val = _get_finite_limit_value(left_lim)
        right_lim_val = _get_finite_limit_value(right_lim)

        # If symbolic limits failed (timeout), try numerical detection
        if left_lim_val is None and not domain_is_bounded_left:
            left_lim_val = _detect_numerical_limit(f_num, -1)
            if left_lim_val is not None:
                debugger(
                    f"Numerically detected left limit (x→-∞): {left_lim_val:.6f}",
                    Fore.CYAN,
                )

        if right_lim_val is None and not domain_is_bounded_right:
            right_lim_val = _detect_numerical_limit(f_num, 1)
            if right_lim_val is not None:
                debugger(
                    f"Numerically detected right limit (x→+∞): {right_lim_val:.6f}",
                    Fore.CYAN,
                )

        # Check if horizontal asymptotes create gaps
        for lim_val, lim_name, is_bounded in [
            (left_lim_val, "left (x→-∞)", domain_is_bounded_left),
            (right_lim_val, "right (x→+∞)", domain_is_bounded_right),
        ]:
            if lim_val is None or is_bounded:
                continue  # No asymptote or domain is bounded on this side

            # Check if this limit value is actually attained by the function
            # A horizontal asymptote means f(x) → L but f(x) ≠ L for all x
            try:
                # Verify numerically: can we get arbitrarily close to lim_val?
                # If yes, but never reach it exactly, it's an asymptote gap
                close_vals = []
                for test_x in np.linspace(-1000, 1000, 2001):
                    try:
                        v = f_num(test_x)
                        if np.isfinite(v):
                            close_vals.append((abs(v - lim_val), v, test_x))
                    except Exception:
                        pass

                if close_vals:
                    close_vals.sort(key=lambda t: t[0])
                    closest_dist, closest_val, closest_x = close_vals[0]

                    # If we actually reach the limit value (within numerical precision),
                    # then it's NOT an asymptote - it's an attained value! Skip it.
                    if closest_dist < 1e-10:
                        debugger(
                            f"Limit value {lim_val:.6f} at {lim_name} IS attained (not an asymptote)",
                            Fore.GREEN,
                        )
                        continue

                    # If we get very close but not exactly equal, it's likely an asymptote
                    if closest_dist < 0.1:
                        # Try to verify: can we find ANY x where f(x) = lim_val?
                        try:

                            def obj(xv):
                                v = f_num(float(xv))
                                return (v - lim_val) ** 2 if np.isfinite(v) else 1e9

                            best_dist = 1e9
                            for start in np.linspace(-100, 100, 21):
                                try:
                                    r = minimize(
                                        obj,
                                        start,
                                        method="Nelder-Mead",
                                        options={"maxiter": 100},
                                    )
                                    if r.success and r.fun < best_dist:
                                        best_dist = r.fun
                                except Exception:
                                    pass

                            # If we can't get closer than 1e-6 to the limit value,
                            # it's an asymptote (the value is never attained)
                            if best_dist > 1e-6:
                                horizontal_asymptote_gaps.append(lim_val)
                                debugger(
                                    f"Horizontal asymptote detected at {lim_name}: y = {lim_val:.6f} (never attained)",
                                    Fore.CYAN,
                                )
                        except Exception:
                            pass
            except Exception:
                pass

        # Also check if both limits converge to the same value (stronger evidence)
        if (
            left_lim_val is not None
            and right_lim_val is not None
            and not domain_is_bounded_left
            and not domain_is_bounded_right
        ):
            if abs(left_lim_val - right_lim_val) < 1e-8:
                # Both branches approach the same limit - definitely a horizontal asymptote
                common_lim = (left_lim_val + right_lim_val) / 2
                if common_lim not in horizontal_asymptote_gaps:
                    # Verify this value is not attained
                    try:

                        def obj(xv):
                            v = f_num(float(xv))
                            return (v - common_lim) ** 2 if np.isfinite(v) else 1e9

                        best_dist = 1e9
                        for start in np.linspace(-100, 100, 21):
                            try:
                                r = minimize(
                                    obj,
                                    start,
                                    method="Nelder-Mead",
                                    options={"maxiter": 100},
                                )
                                if r.success and r.fun < best_dist:
                                    best_dist = r.fun
                            except Exception:
                                pass

                        if best_dist > 1e-6:
                            horizontal_asymptote_gaps.append(common_lim)
                            debugger(
                                f"Common horizontal asymptote at both ±∞: y = {common_lim:.6f}",
                                Fore.CYAN,
                            )
                    except Exception:
                        pass

        # Deduplicate horizontal asymptote gaps (merge values within 1e-4 of each other)
        if len(horizontal_asymptote_gaps) > 1:
            horizontal_asymptote_gaps = sorted(horizontal_asymptote_gaps)
            deduped = [horizontal_asymptote_gaps[0]]
            for v in horizontal_asymptote_gaps[1:]:
                if abs(v - deduped[-1]) > 1e-4:
                    deduped.append(v)
                else:
                    # Average the close values
                    deduped[-1] = (deduped[-1] + v) / 2
            horizontal_asymptote_gaps = deduped

        def fmt(v):
            if np.isinf(v):
                return "oo" if v > 0 else "-oo"
            if abs(v) < 1e-9:
                return "0"
            if abs(v) > 1e10:
                return f"{v:.2e}"
            if RUST_AVAILABLE and hasattr(fast_math_rs, "format_symbolic_value"):
                v_str = fast_math_rs.format_symbolic_value(v)
                if (
                    not any(char.isdigit() for char in v_str)
                    or "E" in v_str
                    or "/" in v_str
                    or "pi" in v_str
                    or "exp" in v_str
                    or "sqrt" in v_str
                ):
                    return v_str
            if abs(v - np.exp(-1 / np.e)) < 1e-8:
                return "exp(-1/E)"
            if abs(v + np.exp(-1 / np.e)) < 1e-8:
                return "-exp(-1/E)"
            # Common mathematical constants
            if abs(v - np.log(2)) < 1e-6:
                return "log(2)"
            if abs(v - np.log(3)) < 1e-6:
                return "log(3)"
            return f"{v:.6f}".rstrip("0").rstrip(".")

        # --- STEP 8: GAP DETECTION ---
        both_inf = np.isinf(final_min) and np.isinf(final_max)
        if (
            all_y_values
            and len(all_y_values) > 100
            and (not both_inf or might_have_gaps)
        ):
            y_arr = np.array(all_y_values)

            if might_have_gaps:
                finite_y = y_arr[np.isfinite(y_arr) & (np.abs(y_arr) < 100)]
            else:
                finite_y = y_arr[np.isfinite(y_arr)]
                if len(finite_y) > 200:
                    p1, p99 = np.percentile(finite_y, [1, 99])
                    iqr = p99 - p1
                    finite_y = finite_y[
                        (finite_y >= p1 - 0.5 * iqr) & (finite_y <= p99 + 0.5 * iqr)
                    ]

            if len(finite_y) > 200:
                sorted_y = np.sort(finite_y)
                all_y_sorted = np.sort(y_arr[np.isfinite(y_arr)])
                gaps = detect_range_gaps(sorted_y, all_y_sorted=all_y_sorted)

                # VERIFY GAPS mathematically to avoid hallucinating gaps on steep curves
                verified_gaps = []
                for gs, ge in gaps:
                    mid_y = float((gs + ge) / 2)
                    verified = False
                    try:
                        res, to = run_with_timeout(
                            "solveset_empty", (f, x, mid_y, domain_sympy), 2.0
                        )
                        if not to and res is True:
                            verified = True
                    except Exception:
                        pass

                    if not verified:
                        # Fallback: Numerical verification
                        # Try to find x such that f(x) == mid_y
                        try:
                            # Objective function: (f(x) - mid_y)^2
                            def obj(xv):
                                v = f_num(xv)
                                return (v - mid_y) ** 2 if np.isfinite(v) else 1e9

                            # Try from a few starting points
                            pts = np.linspace(-10, 10, 20)
                            best_val = 1e9
                            for pt in pts:
                                r = minimize(
                                    obj,
                                    pt,
                                    method="Nelder-Mead",
                                    options={"maxiter": 50},
                                )
                                if r.success and r.fun < best_val:
                                    best_val = r.fun
                                    if best_val < 1e-4:
                                        break

                            if best_val > 1e-2:
                                # We couldn't get close to mid_y numerically, so gap is likely real!
                                verified = True
                        except Exception:
                            # If optimization fails, be conservative and assume not a gap
                            pass

                    if verified:
                        verified_gaps.append((gs, ge))

                # Add horizontal asymptote gaps (point gaps at asymptote values)
                for asym_val in horizontal_asymptote_gaps:
                    asym_val = snap_to_clean_value(asym_val)
                    # Point gap: the asymptote value itself is excluded
                    # We add a tiny gap around the point to represent exclusion
                    verified_gaps.append((asym_val, asym_val))

                if verified_gaps:
                    # Sort gaps by start value
                    verified_gaps = sorted(verified_gaps, key=lambda g: g[0])
                    debugger(
                        f"Detected {len(verified_gaps)} verified gap(s) in range",
                        Fore.CYAN,
                    )
                    pieces = []
                    left = final_min
                    for gs, ge in verified_gaps:
                        gs = snap_to_clean_value(gs)
                        ge = snap_to_clean_value(ge)
                        if gs >= left:
                            pieces.append((left, gs))
                        left = ge
                    if left <= final_max:
                        pieces.append((left, final_max))
                    if len(pieces) > 1 or (
                        len(pieces) == 1 and pieces[0][0] == pieces[0][1]
                    ):
                        parts = []
                        for i, (lo, hi) in enumerate(pieces):
                            # Skip degenerate intervals (point gaps where lo == hi)
                            if abs(lo - hi) < 1e-10:
                                continue

                            lo_s = "-oo" if (np.isinf(lo) and lo < 0) else fmt(lo)
                            hi_s = "oo" if (np.isinf(hi) and hi > 0) else fmt(hi)

                            # Determine open/closed status
                            # At gaps, intervals should be open on the gap side
                            left_open = np.isinf(lo) and lo < 0  # -oo is always open
                            right_open = np.isinf(hi) and hi > 0  # +oo is always open

                            # Check if this piece's endpoint touches a gap
                            # If hi matches a gap value, this interval should be open on the right
                            # If lo matches a gap value, this interval should be open on the left
                            if not right_open and i < len(pieces) - 1:
                                # Not the last piece - right endpoint touches next piece
                                # This must be a gap point, so make it open
                                right_open = True
                            if not left_open and i > 0:
                                # Not the first piece - left endpoint touches previous piece
                                # This must be a gap point, so make it open
                                left_open = True

                            parts.append(
                                f"Interval({lo_s}, {hi_s}, {left_open}, {right_open})"
                            )
                        debugger(
                            f"Returning gap-based range: pieces={pieces}, parts={parts}",
                            Fore.MAGENTA,
                        )
                        # Only return if we have valid parts
                        if len(parts) > 0:
                            if len(parts) == 1:
                                return parts[0], "Hybrid Analysis (gap detected)"
                            return "Union(" + ", ".join(
                                parts
                            ) + ")", "Hybrid Analysis (gap detected)"

        # Handle horizontal asymptote gaps when main gap detection didn't find/return anything
        if horizontal_asymptote_gaps:
            # Create union with point gaps for each asymptote
            verified_gaps = [
                (snap_to_clean_value(v), snap_to_clean_value(v))
                for v in horizontal_asymptote_gaps
            ]
            verified_gaps = sorted(verified_gaps, key=lambda g: g[0])

            pieces = []
            left = final_min
            for gs, ge in verified_gaps:
                if gs > left and gs <= final_max:
                    pieces.append((left, gs))
                    left = ge
            if left < final_max:
                pieces.append((left, final_max))

            if len(pieces) > 1:
                parts = []
                for lo, hi in pieces:
                    lo_s = "-oo" if (np.isinf(lo) and lo < 0) else fmt(lo)
                    hi_s = "oo" if (np.isinf(hi) and hi > 0) else fmt(hi)
                    parts.append(f"Interval({lo_s}, {hi_s})")
                return "Union(" + ", ".join(
                    parts
                ) + ")", "Hybrid Analysis (horizontal asymptote gap)"

        # --- STEP 9: OPEN/CLOSED ENDPOINT DETECTION ---
        def check_openness(val, is_min):
            if np.isinf(val):
                return True

            # Special handling for bounded trig functions: sin, cos always attain ±1
            # sin(g(x)) for continuous unbounded g(x) always attains 1 and -1
            if abs(abs(val) - 1) < 1e-9:
                # Check if this is a sin or cos based function
                if f.has(sym_sin) or f.has(sym_cos):
                    # For functions like sin(x+sin(x)), sin(x), cos(x), etc.
                    # These always attain their bounds of ±1 on unbounded domains
                    if domain_sympy == S.Reals or (
                        hasattr(domain_sympy, "inf")
                        and domain_sympy.inf == -oo
                        and hasattr(domain_sympy, "sup")
                        and domain_sympy.sup == oo
                    ):
                        debugger(
                            f"Trig function with bound {val}: assuming attained",
                            Fore.GREEN,
                        )
                        return False  # Bound IS attained, so NOT open

            try:
                result, timed_out = run_with_timeout(
                    "solveset_empty", (f, x, val, domain_sympy), timeout_seconds=2.0
                )
                if not timed_out:
                    if result is True:
                        return True
                    if result is False:
                        return False
            except Exception:
                pass

            try:
                if len(all_points) > 0:
                    all_y = [p[1] for p in all_points]
                    if is_min:
                        actual_min = min(all_y)
                        if actual_min > val + 1e-9:
                            return True
                    else:
                        actual_max = max(all_y)
                        if actual_max < val - 1e-9:
                            return True
            except Exception:
                pass

            for lv, _ in limit_points:
                if abs(lv - snap_to_clean_value(val)) < 1e-7:
                    return True

            # Default: for trig functions on unbounded domain, assume bounds are attained
            if (f.has(sym_sin) or f.has(sym_cos)) and abs(val) <= 1 + 1e-9:
                if domain_sympy == S.Reals or (
                    hasattr(domain_sympy, "inf")
                    and not getattr(domain_sympy.inf, "is_finite", True)
                ):
                    return False  # Assume attained

            return False

        left_open = check_openness(final_min, True)
        right_open = check_openness(final_max, False)

        # --- STEP 8.5: INTERIOR HOLE SPLITTING FROM LIMITS ---
        holes = []
        for lv, x_src in limit_points:
            if final_min < lv < final_max:
                verified_hole = False
                try:
                    res, to = run_with_timeout(
                        "solveset_empty", (f, x, lv, domain_sympy), 2.0
                    )
                    if not to and res is True:
                        verified_hole = True
                except Exception:
                    pass

                if (
                    not verified_hole
                    and not np.isinf(lv)
                    and not np.isnan(lv)
                    and SCIPY_AVAILABLE
                ):
                    # Fallback: Numerical verification for single-point holes
                    try:

                        def obj(xv):
                            v = f_num(xv[0])
                            return (v - lv) ** 2 if np.isfinite(v) else 1e9

                        pts = np.linspace(
                            max(-10, final_min if final_min > -1e9 else -10),
                            min(10, final_max if final_max < 1e9 else 10),
                            20,
                        )
                        hit_elsewhere = False

                        for pt in pts:
                            r = minimize(
                                obj, [pt], method="Nelder-Mead", options={"maxiter": 50}
                            )
                            if r.success and r.fun < 1e-4:
                                x_star = r.x[0]
                                if x_src is None:
                                    hit_elsewhere = True
                                    break
                                elif np.isinf(float(x_src)):
                                    if abs(x_star) < 100:  # hit at a finite point
                                        hit_elsewhere = True
                                        break
                                else:
                                    if (
                                        abs(x_star - float(x_src)) > 1e-2
                                    ):  # hit away from the limit source
                                        hit_elsewhere = True
                                        break

                        if not hit_elsewhere:
                            verified_hole = True
                    except Exception:
                        pass

                if verified_hole:
                    holes.append(float(lv))
        holes = sorted(list(set(holes)))
        if holes:
            debugger(f"Detected interior holes: {holes}", Fore.CYAN)
            intervals = []
            curr_left = final_min
            for i, hole in enumerate(holes):
                lo_s = (
                    "-oo" if (np.isinf(curr_left) and curr_left < 0) else fmt(curr_left)
                )
                hi_s = fmt(hole)
                if i == 0:
                    if left_open:
                        intervals.append(f"Interval.open({lo_s}, {hi_s})")
                    else:
                        intervals.append(f"Interval.Ropen({lo_s}, {hi_s})")
                else:
                    intervals.append(f"Interval.open({lo_s}, {hi_s})")
                curr_left = hole
            lo_s = "-oo" if (np.isinf(curr_left) and curr_left < 0) else fmt(curr_left)
            hi_s = "oo" if (np.isinf(final_max) and final_max > 0) else fmt(final_max)
            if right_open:
                intervals.append(f"Interval.open({lo_s}, {hi_s})")
            else:
                intervals.append(f"Interval.Lopen({lo_s}, {hi_s})")
            return "Union(" + ", ".join(
                intervals
            ) + ")", "Hybrid Analysis (interior hole)"

        if left_open and right_open:
            interval_str = f"Interval.open({fmt(final_min)}, {fmt(final_max)})"
        elif left_open:
            interval_str = f"Interval.Lopen({fmt(final_min)}, {fmt(final_max)})"
        elif right_open:
            interval_str = f"Interval.Ropen({fmt(final_min)}, {fmt(final_max)})"
        else:
            interval_str = f"Interval({fmt(final_min)}, {fmt(final_max)})"

        return interval_str, "Hybrid Analysis"
    except Exception as e:
        traceback.print_exc()
        return f"Numerical Error: {e}", "Error"


# =============================================================================
# FORMATTING
# =============================================================================


def format_math_set(obj):
    if isinstance(obj, str):
        if obj == "Reals":
            return "(-oo, oo)"
        elif obj == "Integers":
            return "Integers"
        try:
            obj = eval(obj, globals(), locals())
        except Exception:
            return obj

    if obj == S.Reals:
        return "(-oo, oo)"
    if obj == S.Integers:
        return "Integers"
    if obj == EmptySet:
        return "EmptySet"

    def fmt_val(val):
        if val == S.Infinity:
            return "oo"
        if val == S.NegativeInfinity:
            return "-oo"
        if getattr(val, "is_Float", False):
            s = str(val)
            if "e" not in s.lower() and "." in s:
                s = s.rstrip("0").rstrip(".")
                if not s:
                    return "0"
            return s
        return str(val)

    if isinstance(obj, FiniteSet):
        items = sorted([fmt_val(arg) for arg in obj.args])
        return "{" + ", ".join(items) + "}"

    def fmt_interval(interv):
        lo_str = fmt_val(interv.start)
        hi_str = fmt_val(interv.end)
        left_bracket = "(" if interv.left_open or lo_str == "-oo" else "["
        right_bracket = ")" if interv.right_open or hi_str == "oo" else "]"
        return f"{left_bracket}{lo_str}, {hi_str}{right_bracket}"

    if isinstance(obj, Interval):
        return fmt_interval(obj)

    if isinstance(obj, ImageSet):
        try:
            expr = obj.lamda.expr
            var = obj.lamda.variables[0]
            n_sym = Symbol("n")
            expr_n = expr.subs(var, n_sym)
            return f"{{{fmt_val(expr_n)} | n in Z}}"
        except Exception:
            return str(obj)

    if isinstance(obj, Complement):
        base, exc = obj.args
        base_str = format_math_set(base)
        exc_str = format_math_set(exc)
        if base_str == "(-oo, oo)":
            base_str = "R"
        return f"{base_str} \\ {exc_str}"

    if isinstance(obj, Union):
        # ── Attempt compact periodic representation ──────────────────────
        periodic_str = _format_periodic_union(obj, fmt_val, fmt_interval)
        if periodic_str is not None:
            return periodic_str

        parts = []
        for arg in obj.args:
            if isinstance(arg, Interval):
                parts.append(fmt_interval(arg))
            elif isinstance(arg, FiniteSet):
                items = sorted([fmt_val(x) for x in arg.args])
                parts.append("{" + ", ".join(items) + "}")
            else:
                parts.append(format_math_set(arg))
        return " U ".join(parts)

    return str(obj)


def round_sympy_expr(expr, digits=3):
    if isinstance(expr, Float):
        return Float(round(float(expr), digits), digits)

    elif isinstance(expr, Interval):
        return Interval(
            round_sympy_expr(expr.start, digits),
            round_sympy_expr(expr.end, digits),
            expr.left_open,
            expr.right_open,
        )

    elif isinstance(expr, Union):
        return Union(*[round_sympy_expr(arg, digits) for arg in expr.args])

    elif isinstance(expr, FiniteSet):
        return FiniteSet(*[round_sympy_expr(arg, digits) for arg in expr.args])

    return expr


# =============================================================================
# MAIN SOLVER
# =============================================================================


def solve(func_str):
    x = Symbol("x", real=True)

    # --- PARSING ---
    try:
        f_raw = get_sympified_expr(func_str)

        # Validate the expression before processing
        if f_raw is None or f_raw in [zoo, oo, -oo, nan]:
            debugger(f"Invalid expression after parsing: {func_str}", Fore.RED)
            return None

        # Check for empty function calls (like abs() with no args)
        # This happens when parsing invalid expressions
        if hasattr(f_raw, "atoms"):
            for atom in f_raw.atoms():
                if hasattr(atom, "func") and hasattr(atom, "args"):
                    # Check if it's a function with zero arguments when it shouldn't be
                    if (
                        atom.func in [Abs, sym_sin, sym_cos, tan, exp, log]
                        and len(atom.args) == 0
                    ):
                        debugger(
                            f"Invalid expression - empty function call: {atom.func}",
                            Fore.RED,
                        )
                        return None

        x_parsed = [s for s in f_raw.free_symbols if str(s) == "x"]
        f = f_raw.subs(x_parsed[0], x) if x_parsed else f_raw
    except Exception as e:
        debugger(f"Expression parsing failed: {e}", Fore.RED)
        return None

    if f in [zoo, oo, -oo, nan]:
        return None

    # --- CONSTANT FUNCTION DETECTION ---
    if f.is_number:
        debugger("Constant function detected", Fore.YELLOW)
        return None

    if f.free_symbols:
        try:
            f_ts = trigsimp(f)
            if f_ts.is_number:
                debugger("Expression simplifies to constant", Fore.YELLOW)
                # Return proper result for constant function
                const_val = float(f_ts.evalf())
                # Format the constant nicely
                if abs(const_val - round(const_val)) < 1e-10:
                    const_str = str(int(round(const_val)))
                elif abs(const_val - 1.5) < 1e-10:
                    const_str = "3/2"
                elif abs(const_val - 0.5) < 1e-10:
                    const_str = "1/2"
                else:
                    const_str = f"{const_val:.6f}".rstrip("0").rstrip(".")
                return {
                    "domain": "(-oo, oo)",
                    "range": f"{{{const_str}}}",
                    "range_method": "Constant (trigsimp)",
                }
        except Exception:
            pass

    # --- DOMAIN ---
    domain_result, domain_timed_out = run_with_timeout(
        "domain", (f, x, S.Reals), timeout_seconds=3.0, default=S.Reals
    )
    if domain_timed_out:
        domain = S.Reals
    elif domain_result is not None:
        domain = domain_result
    else:
        domain = S.Reals

    # ── FIX-02: Expand periodic domains truncated by SymPy ───────────────
    domain, was_periodic = expand_periodic_domain(f, x, domain)
    if was_periodic:
        debugger(
            "Periodic domain detected — expanded from single period to full ℤ-union",
            Fore.GREEN,
        )

    def refine_domain_boundaries(dom, f_num):
        if isinstance(dom, Interval):
            lo, ro = dom.left_open, dom.right_open
            if not lo and dom.start.is_finite:
                v = f_num(float(dom.start))
                if not np.isfinite(v) or not np.isreal(v):
                    lo = True
            if not ro and dom.end.is_finite:
                v = f_num(float(dom.end))
                if not np.isfinite(v) or not np.isreal(v):
                    ro = True
            return Interval(dom.start, dom.end, bool(lo), bool(ro))
        elif isinstance(dom, Union):
            return Union(*[refine_domain_boundaries(arg, f_num) for arg in dom.args])
        return dom

    try:
        f_num_dom = make_safe_f_num_vectorized(f, x)
        domain = refine_domain_boundaries(domain, f_num_dom)
    except Exception:
        pass

    # --- RANGE ---
    range_res = None
    method = ""
    behavior_info = None
    any_timed_out = False

    # ── FIX-01: Robust integer-valued detection ───────────────────────────
    if has_integer_valued_output(f):
        # Extra guard: make sure x - floor(x) style expressions are routed
        # to the full solver by verifying the function takes non-integer values.
        try:
            f_num_test = make_safe_f_num_vectorized(f, x)
            test_vals = [f_num_test(v) for v in [0.3, 0.7, 1.5, 2.8, -0.4]]
            test_vals = [v for v in test_vals if np.isfinite(v)]
            all_integer = all(abs(v - round(v)) < 1e-9 for v in test_vals)
        except Exception:
            all_integer = True  # conservative: trust structural check

        if all_integer:
            debugger("Detected integer-valued function (floor/ceiling)", Fore.GREEN)
            # ── Determine which integers are actually attained ────────────
            # Sample densely over multiple periods to collect all reachable
            # integer values; this correctly identifies e.g.:
            #   ceiling(x) - floor(x)  → {1}    (not all integers)
            #   floor(x) + 1           → ℤ      (all integers stay)
            #   2*floor(x)             → even ℤ (every even integer)
            try:
                f_num_test2 = make_safe_f_num_vectorized(f, x)
                # Sample across a wide range including many floor-transitions
                xs_probe = np.linspace(-20.5, 20.5, 4000)

                # For functions involving sin/cos, add critical points where sin/cos = ±1
                # These are the exact peaks that floor() might round differently
                if f.has(sym_sin) or f.has(sym_cos):
                    trig_critical = []
                    for n in range(-10, 11):
                        # sin(x) = 1 at π/2 + 2πn
                        trig_critical.append(np.pi / 2 + 2 * np.pi * n)
                        # sin(x) = -1 at -π/2 + 2πn (or 3π/2 + 2πn)
                        trig_critical.append(-np.pi / 2 + 2 * np.pi * n)
                        # cos(x) = 1 at 2πn
                        trig_critical.append(2 * np.pi * n)
                        # cos(x) = -1 at π + 2πn
                        trig_critical.append(np.pi + 2 * np.pi * n)
                    xs_probe = np.unique(
                        np.concatenate([xs_probe, np.array(trig_critical)])
                    )

                ys_probe = f_num_test2(xs_probe)
                if np.isscalar(ys_probe):
                    ys_probe = np.full_like(xs_probe, ys_probe)
                ys_probe = np.asarray(ys_probe, dtype=float)
                valid_mask = np.isfinite(ys_probe)
                if np.any(valid_mask):
                    raw_vals = ys_probe[valid_mask]
                    # Round to nearest integer and collect unique values
                    int_vals = set(
                        int(round(v)) for v in raw_vals if abs(v - round(v)) < 1e-6
                    )
                    if len(int_vals) == 0:
                        # Fallback: something went wrong, use S.Integers
                        range_res = S.Integers
                    elif len(int_vals) == 1:
                        # Single integer value — constant-integer function
                        only_val = next(iter(int_vals))
                        range_res = FiniteSet(Integer(only_val))
                        method = "Exact (integer-valued function)"
                        debugger(
                            f"Integer-valued function with single value: {{{only_val}}}",
                            Fore.GREEN,
                        )
                    else:
                        # Multiple values: check if they form a complete
                        # arithmetic sequence (step=k → k*Integers + offset)
                        sorted_vals = sorted(int_vals)
                        gaps = [
                            sorted_vals[i + 1] - sorted_vals[i]
                            for i in range(len(sorted_vals) - 1)
                        ]
                        min_gap = min(gaps)
                        all_same_gap = all(g == min_gap for g in gaps)

                        # Only trust this pattern if we've sampled enough
                        # integers on BOTH sides of zero
                        neg_count = sum(1 for v in sorted_vals if v < 0)
                        pos_count = sum(1 for v in sorted_vals if v >= 0)
                        good_coverage = neg_count >= 3 and pos_count >= 3

                        if good_coverage and all_same_gap and min_gap == 1:
                            # Dense, no gaps → all integers
                            range_res = S.Integers
                        elif good_coverage and all_same_gap and min_gap > 1:
                            # Subset of integers with uniform spacing
                            # e.g. 2*floor(x) → {…,-4,-2,0,2,4,…}
                            offset = sorted_vals[0] % min_gap
                            # Express as FiniteSet only if small, else Integers
                            # For display, report as multiples
                            range_res = S.Integers  # structural: still Z-like
                            # Override display method label
                            method = f"Exact (integer-valued function, step={min_gap})"
                            debugger(
                                f"Integer-valued, step={min_gap}, range≈{min_gap}·ℤ+{offset}",
                                Fore.GREEN,
                            )
                        else:
                            # Irregular or insufficient coverage
                            mn, mx = min(sorted_vals), max(sorted_vals)
                            # the grid spans [-20.5, 20.5]. If limits reach large values, they are unbounded.
                            bounded_below = mn > -350
                            bounded_above = mx < 350

                            sample_str = ", ".join(str(v) for v in sorted_vals[:4])
                            dots = ", ..." if len(sorted_vals) > 4 else ""

                            if bounded_below and not bounded_above:
                                range_res = f"Irregular integers {{{sample_str}{dots}}}"
                                method = "Exact (irregular integers, bounded below)"
                            elif bounded_above and not bounded_below:
                                range_res = (
                                    f"Irregular integers {{..., {sample_str}{dots}}}"
                                )
                                method = "Exact (irregular integers, bounded above)"
                            elif bounded_below and bounded_above:
                                range_res = f"Irregular integers {{{sample_str}{dots}}}"
                                method = "Exact (irregular integers, bounded)"
                            else:
                                range_res = "Irregular integers"
                                method = "Exact (irregular integers)"

                            debugger(f"Irregular integers detected", Fore.GREEN)

                        if (
                            hasattr(range_res, "is_Set")
                            and range_res is S.Integers
                            and not method
                        ):
                            method = "Exact (integer-valued function)"
                else:
                    range_res = S.Integers
                    method = "Exact (integer-valued function)"

            except Exception:
                range_res = S.Integers
                method = "Exact (integer-valued function)"

            if not method:
                method = "Exact (integer-valued function)"
        else:
            debugger(
                "floor/ceiling present but output is NOT integer-valued — "
                "routing to full solver",
                Fore.YELLOW,
            )

    def is_valid_range(result):
        if result is None or result == EmptySet:
            return False
        if isinstance(result, FiniteSet):
            if len(result) == 1 and result.args[0] == f:
                return False
            return all(arg.is_number for arg in result.args)
        return True

    SYMBOLIC_TOTAL_BUDGET = 3.0

    if range_res is None:
        budget_start = time.perf_counter()
        remaining = lambda: SYMBOLIC_TOTAL_BUDGET - (time.perf_counter() - budget_start)

        # Strategy A0: single-period shortcut for periodic domains
        # Handles two cases:
        #  1. Large periodic Union (e.g. sqrt(sin(x))) → pick one Interval component
        #  2. Complement domain (e.g. log(sin(x))) → extract the base Interval
        # In both cases: for a periodic function, range over one period == range over all ℝ.
        single_period_domain = None
        if isinstance(domain, Union):
            comp_list = [a for a in domain.args if isinstance(a, Interval)]
            if len(comp_list) >= 4:
                # Pick the component closest to x=0
                try:
                    single_period_domain = min(
                        comp_list,
                        key=lambda iv: min(
                            abs(float(iv.start.evalf())), abs(float(iv.end.evalf()))
                        ),
                    )
                except Exception:
                    single_period_domain = None

        # Complement domain: extract the base set if it's a finite Interval
        # e.g.  Complement(Interval.open(0, pi), {0, pi})  → Interval.open(0, pi)
        if single_period_domain is None:
            try:
                if isinstance(domain, Complement):
                    base = domain.args[0]
                    if (
                        isinstance(base, Interval)
                        and base.start.is_finite
                        and base.end.is_finite
                    ):
                        # Verify there's a trig function so this really is periodic
                        if any(
                            f.has(fc) for fc in [sym_sin, sym_cos, tan, cot, sec, csc]
                        ):
                            single_period_domain = base
            except Exception:
                pass

        if single_period_domain is not None:
            t_a0 = min(SYMBOLIC_TIMEOUT, remaining())
            if t_a0 > 0.1:
                debugger(
                    f"Strategy A0: function_range on representative interval "
                    f"[{single_period_domain.start}, {single_period_domain.end}] "
                    f"(budget={t_a0:.1f}s)",
                    Fore.BLUE,
                )
                result_a0, to_a0 = run_with_timeout(
                    "range", (f, x, single_period_domain), t_a0
                )
                if to_a0:
                    any_timed_out = True
                    debugger("Strategy A0 TIMED OUT", Fore.YELLOW)
                elif result_a0 is not None and is_valid_range(result_a0):
                    range_res = result_a0
                    method = "Exact (function_range, periodic)"
                    debugger(f"Strategy A0 SUCCESS: {result_a0}", Fore.GREEN)

        # Strategy A1: Composition decomposition
        if range_res is None and remaining() > 0.2:
            # Useful for f(x) like sin(1/x) or exp(-x**2)
            if f.count(x) == 1:
                ta1 = min(SYMBOLIC_TIMEOUT, remaining())
                if ta1 > 0.1:
                    debugger(
                        f"Strategy A1: composition decomposition (budget={ta1:.1f}s)",
                        Fore.BLUE,
                    )
                    result, timed_out = run_with_timeout(
                        "composited_range", (f, x, domain), ta1
                    )
                    if timed_out:
                        any_timed_out = True
                        debugger("Strategy A1 TIMED OUT", Fore.YELLOW)
                    elif result is not None and is_valid_range(result):
                        range_res = result
                        method = "Exact (function_range, composited)"
                        debugger(f"Strategy A1 SUCCESS: {result}", Fore.GREEN)

        # Strategy A: function_range (full domain)
        ta = min(SYMBOLIC_TIMEOUT, remaining())
        if range_res is None and ta > 0.1:
            debugger(f"Strategy A: function_range (budget={ta:.1f}s)", Fore.BLUE)
            result, timed_out = run_with_timeout("range", (f, x, domain), ta)
            if timed_out:
                any_timed_out = True
                debugger("Strategy A TIMED OUT", Fore.YELLOW)
            elif result is not None and is_valid_range(result):
                range_res = result
                method = "Exact (function_range)"
                debugger(f"Strategy A SUCCESS: {result}", Fore.GREEN)

        # Strategy B: symbolic min/max
        if range_res is None and remaining() > 0.2:
            tb = min(SYMBOLIC_TIMEOUT, remaining())
            debugger(f"Strategy B: min/max (budget={tb:.1f}s)", Fore.BLUE)
            result, timed_out = run_with_timeout("min_max", (f, x, domain), tb)
            if timed_out:
                any_timed_out = True
                debugger("Strategy B TIMED OUT", Fore.YELLOW)
            elif result is not None:
                mn, mx = result
                mn_ok = mn is not None and (mn.is_number or mn in [oo, -oo])
                mx_ok = mx is not None and (mx.is_number or mx in [oo, -oo])
                if mn_ok and mx_ok:
                    if mn == -oo and mx == oo:
                        range_res = Interval(-oo, oo)
                    elif mn == -oo:
                        range_res = Interval(-oo, mx)
                    elif mx == oo:
                        range_res = Interval(mn, oo)
                    else:
                        range_res = Interval(mn, mx)
                    method = "Exact (min/max)"
                    debugger(f"Strategy B SUCCESS: [{mn}, {mx}]", Fore.GREEN)

        # Strategy C: limit analysis
        if range_res is None and remaining() > 0.2:
            tc = min(SYMBOLIC_TIMEOUT, remaining())
            debugger(f"Strategy C: limit analysis (budget={tc:.1f}s)", Fore.BLUE)
            result, timed_out = run_with_timeout("limit", (f, x, domain), tc)
            if timed_out:
                any_timed_out = True
                debugger("Strategy C TIMED OUT", Fore.YELLOW)
            elif result is not None:
                has_neg_inf, has_pos_inf, left_lim, right_lim, sing_limits = result
                behavior_info = result

                # Check for squared expression - must be non-negative
                if is_squared_expression(f, x):
                    has_neg_inf = False  # Squared expressions can't be negative
                    debugger(
                        "Strategy C: squared expression detected, range >= 0",
                        Fore.GREEN,
                    )

                if has_neg_inf and has_pos_inf:
                    if _has_reciprocal_trig(f, x) or f.has(sec) or f.has(csc):
                        debugger(
                            "Strategy C: doubly unbounded but gapped — deferring to numerical",
                            Fore.CYAN,
                        )
                    else:
                        range_res = Interval(-oo, oo)
                        method = "Exact (limit analysis)"
                        debugger("Strategy C: unbounded in both directions", Fore.GREEN)
                elif has_neg_inf or has_pos_inf:
                    # For squared expressions, if only has_pos_inf, that's [0, oo)
                    # UNLESS it's a bounded squared expression like cos(...)^2
                    if is_squared_expression(f, x) and has_pos_inf and not has_neg_inf:
                        if is_bounded_trig_squared(f, x):
                            debugger(
                                "Strategy C: bounded trig squared — deferring to numerical",
                                Fore.CYAN,
                            )
                        else:
                            range_res = Interval(0, oo)
                            method = "Exact (limit analysis, squared)"
                            debugger(
                                "Strategy C: squared expression, range [0, oo)",
                                Fore.GREEN,
                            )
                    else:
                        debugger(
                            f"Strategy C: one-sided unbounded — deferring to numerical",
                            Fore.CYAN,
                        )

    # Strategy D: numerical fallback
    if range_res is None:
        debugger(
            "Strategy D: numerical fallback"
            + (" (after timeout)" if any_timed_out else ""),
            Fore.CYAN,
        )
        range_res_str, method = smart_numerical_range(
            f, x, domain, behavior_info=behavior_info
        )

        if RUST_AVAILABLE:
            method += " [Rust]"
        if isinstance(range_res_str, str) and "Error" not in range_res_str:
            try:
                range_res = eval(range_res_str)
            except Exception:
                range_res = range_res_str
        else:
            range_res = range_res_str

    # --- ENDPOINT OPEN/CLOSED REFINEMENT ---
    if range_res is not None and isinstance(range_res, (Interval, Union)):

        def check_bound_attained(val):
            try:
                res, to = run_with_timeout("solveset_empty", (f, x, val, domain), 2.0)
                if not to:
                    if res is False:
                        return True
                    if res is True:
                        return False
            except Exception:
                pass
            return None

        def fix_interval(interv):
            if not isinstance(interv, Interval):
                return interv
            lo = interv.left_open
            ro = interv.right_open

            if lo and interv.start.is_finite:
                if check_bound_attained(interv.start) is True:
                    lo = False
            elif not lo and interv.start.is_finite:
                if check_bound_attained(interv.start) is False:
                    lo = True

            if ro and interv.end.is_finite:
                if check_bound_attained(interv.end) is True:
                    ro = False
            elif not ro and interv.end.is_finite:
                if check_bound_attained(interv.end) is False:
                    ro = True

            return Interval(interv.start, interv.end, bool(lo), bool(ro))

        if isinstance(range_res, Interval):
            range_res = fix_interval(range_res)
        elif isinstance(range_res, Union):
            range_res = Union(*[fix_interval(arg) for arg in range_res.args])

    if "Error" in str(range_res):
        col = Fore.RED
    elif "Exact" in method:
        col = Fore.GREEN
    elif "Hybrid" in method:
        col = Fore.CYAN
    else:
        col = Fore.YELLOW

    return {
        "range": format_math_set(round_sympy_expr(range_res, 3)),
        "domain": format_math_set(domain),
        "method": method,
    }
