import sys
import numpy as np
import warnings
import time
import signal
from functools import lru_cache
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from sympy import (Symbol, S, sympify, oo, zoo, nan, lambdify, Abs, floor, ceiling,
                   limit, simplify, diff, solveset, Piecewise, sign, Max, Min, exp, log,
                   re, im, Interval as SympyInterval, Rational, Pow, Integer,
                   tan, cot, sec, csc)
from sympy.calculus.util import continuous_domain, function_range, minimum, maximum, AccumBounds
from sympy.sets import Interval, Union, FiniteSet, EmptySet, Reals, Integers
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
import colorama
from colorama import Fore, Style

# Try imports
try:
    from scipy.optimize import minimize_scalar, minimize
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Try to import Rust acceleration module
try:
    import fast_math_rs
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

colorama.init(autoreset=True)
warnings.filterwarnings('ignore')

# =============================================================================
# DEBUG AND CONFIGURATION
# =============================================================================

# Set to True to see which engine (SymPy/Rust) is handling each step
DEBUG_ENGINE = True

def debug_print(msg, color=Fore.MAGENTA):
    """Print debug message if DEBUG_ENGINE is enabled"""
    if DEBUG_ENGINE:
        print(f"{color}{Style.DIM}[DEBUG] {msg}{Style.RESET_ALL}")

# =============================================================================
# TIMING AND TIMEOUT UTILITIES
# =============================================================================

# Timeout for symbolic computations (seconds) - reduced for faster fallback
SYMBOLIC_TIMEOUT = 1.0

class SymbolicTimeoutError(Exception):
    """Custom timeout exception for symbolic computations"""
    pass

def run_with_timeout(func, timeout_seconds, default=None):
    """
    Run a function with a timeout. Windows-compatible using time-based checking.
    NOTE: This doesn't truly interrupt the function, but allows the caller to 
    proceed if the function takes too long. The function continues in background.
    Returns (result, timed_out) tuple.
    """
    import threading
    
    result_container = {'result': default, 'exception': None, 'done': False}
    
    def wrapper():
        try:
            result_container['result'] = func()
        except Exception as e:
            result_container['exception'] = e
        finally:
            result_container['done'] = True
    
    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    if not result_container['done']:
        debug_print(f"TIMEOUT after {timeout_seconds}s - switching to numerical fallback", Fore.YELLOW)
        return default, True
    
    if result_container['exception'] is not None:
        return default, False
    
    return result_container['result'], False

class Timer:
    """Context manager for timing code blocks"""
    def __init__(self, name=""):
        self.name = name
        self.elapsed = 0.0
    
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.start
        return False

class TimingStats:
    """Accumulate timing statistics for the solve function"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.parsing_time = 0.0
        self.domain_time = 0.0
        self.symbolic_range_time = 0.0
        self.numerical_range_time = 0.0
        self.total_time = 0.0
    
    def __str__(self):
        return (f"Timing: parse={self.parsing_time*1000:.2f}ms, "
                f"domain={self.domain_time*1000:.2f}ms, "
                f"sym_range={self.symbolic_range_time*1000:.2f}ms, "
                f"num_range={self.numerical_range_time*1000:.2f}ms, "
                f"total={self.total_time*1000:.2f}ms")

def _rationalize_float_exponents(expr):
    """Convert float exponents close to simple fractions into exact Rationals.
    e.g. x**0.333333 -> x**(1/3), x**0.2 -> x**(1/5)"""
    replacements = {}
    for sub in expr.atoms(Pow):
        e = sub.exp
        if e.is_Float or (e.is_Number and not isinstance(e, (Integer, Rational))):
            r = _float_to_odd_rational(e)
            if r is not None:
                replacements[sub] = Pow(sub.base, r)
            else:
                # Also try even denominators for completeness: 1/2, 1/4, 3/4, etc.
                for q in [2, 4, 6, 8]:
                    for p in range(1, 2 * q):
                        target = p / q
                        if abs(float(e) - target) < 1e-6:
                            replacements[sub] = Pow(sub.base, Rational(p, q))
                            break
                        if abs(float(e) + target) < 1e-6:
                            replacements[sub] = Pow(sub.base, Rational(-p, q))
                            break
                    else:
                        continue
                    break
    for old, new in replacements.items():
        expr = expr.subs(old, new)
    return expr

def get_sympified_expr(user_input):
    transformations = (standard_transformations + (implicit_multiplication_application,))
    expr = parse_expr(user_input, transformations=transformations)
    # Rationalize float exponents so SymPy handles them symbolically
    expr = _rationalize_float_exponents(expr)
    return expr

# =============================================================================
# HELPER FUNCTIONS FOR EDGE CASE DETECTION
# =============================================================================

PERIODIC_UNBOUNDED_FUNCS = {tan, cot, sec, csc}

# Functions that are unbounded AND have full range (-oo, oo) with no gaps
PERIODIC_FULL_RANGE_FUNCS = {tan, cot}

# Functions that are unbounded but have gaps (|f(x)| >= 1 always)
PERIODIC_GAPPED_FUNCS = {sec, csc}

from sympy import sin as sym_sin, cos as sym_cos

def _has_reciprocal_trig(f, var):
    """Detect patterns like 1/sin(x), 1/cos(x), a/sin(x), etc.
    These have range (-oo,-1]U[1,oo) or similar gapped ranges."""
    from sympy import fraction
    numer, denom_expr = fraction(f)
    # Check if denominator contains sin or cos (but not wrapped in other trig)
    if denom_expr.has(sym_sin) or denom_expr.has(sym_cos):
        return True
    # Also catch sec/csc directly
    if f.has(sec) or f.has(csc):
        return True
    return False

def is_periodically_unbounded(f):
    """Detect functions known to have periodic vertical asymptotes (tan, cot, sec, csc)."""
    for func_class in PERIODIC_UNBOUNDED_FUNCS:
        if f.has(func_class):
            return True
    return False

def is_periodically_unbounded_no_gap(f):
    """Detect if function is periodically unbounded WITH full range (-oo, oo) — no gaps.
    Returns True for tan(x), cot(x) and similar. Returns False for sec(x), csc(x), 1/sin(x)."""
    if _has_reciprocal_trig(f, None):
        return False  # reciprocal trig has gaps
    for func_class in PERIODIC_FULL_RANGE_FUNCS:
        if f.has(func_class):
            return True
    return False

def has_integer_valued_output(f):
    """Check if f always produces integer values (floor, ceiling)."""
    return f.has(floor) or f.has(ceiling)

def _float_to_odd_rational(exp_val):
    """Try to convert a float exponent to p/q Rational with odd q.
    Returns Rational if match found, else None."""
    # Common fractional powers with odd denominators: 1/3, 2/3, 1/5, 2/5, 3/5, 4/5, 1/7, etc.
    for q in [3, 5, 7, 9, 11]:
        for p in range(1, 2 * q):
            target = p / q
            if abs(float(exp_val) - target) < 1e-6:
                return Rational(p, q)
            if abs(float(exp_val) + target) < 1e-6:  # negative exponents
                return Rational(-p, q)
    return None

def has_real_odd_root(expr, var):
    """Detect x**(p/q) where q is odd — these are real-valued for all real x.
    Handles both Rational and float exponents close to simple fractions."""
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
    """Rewrite fractional powers with odd denominators for real evaluation with negative inputs.
    Handles both Rational and float exponents close to simple fractions."""
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
                    if p % 2 == 1:  # odd numerator: sign matters
                        replacements[sub] = sign(sub.base) * Abs(sub.base)**rat_exp
                    else:  # even numerator: always positive
                        replacements[sub] = Abs(sub.base)**rat_exp
    for old, new in replacements.items():
        expr = expr.subs(old, new)
    return expr

def point_in_domain_fast(pt, gen_min, gen_max, f_num):
    """Fast numeric domain check — avoids expensive SymPy symbolic evaluation."""
    if not (gen_min <= pt <= gen_max):
        return False
    try:
        val = f_num(pt)
        return np.isfinite(val) and np.isreal(val)
    except:
        return False

def make_safe_f_num_vectorized(f, x):
    """Returns a function that handles both scalar and numpy array inputs natively.
    Uses true numpy C-level vectorization instead of Python-level np.vectorize."""
    # Rewrite odd roots for real evaluation
    f_rewritten = rewrite_real_roots(f, x) if has_real_odd_root(f, x) else f
    
    modules = [
        {
            'Heaviside': lambda x: np.heaviside(x, 0.5),
            'Max': np.maximum,
            'Min': np.minimum,
        },
        'numpy'
    ]
    f_num_raw = lambdify(x, f_rewritten, modules=modules)
    
    def safe_f(x_input):
        if np.isscalar(x_input):
            try:
                result = f_num_raw(x_input)
                if isinstance(result, complex):
                    return result.real if abs(result.imag) < 1e-10 else np.nan
                result = float(result)
                return result if np.isfinite(result) else np.nan
            except:
                return np.nan
        
        # Array path — true C-level numpy execution
        x_arr = np.asarray(x_input, dtype=float)
        try:
            result = f_num_raw(x_arr)
            if np.isscalar(result):
                result = np.full_like(x_arr, result, dtype=float)
            result = np.asarray(result, dtype=complex if np.iscomplexobj(result) else float)
            if np.iscomplexobj(result):
                valid = np.abs(np.imag(result)) < 1e-10
                return np.where(valid, np.real(result), np.nan)
            return np.where(np.isfinite(result), result, np.nan)
        except Exception:
            return np.full_like(x_arr, np.nan, dtype=float)
    
    return safe_f

def get_symbolic_limits(f, x, domain):
    """
    Use SymPy's limit function to find behavior at domain boundaries.
    Returns (limit_at_left, limit_at_right)
    """
    left_limit = None
    right_limit = None
    
    try:
        # Handle Union of intervals
        if isinstance(domain, Union):
            # Get the overall bounds
            all_infs = []
            all_sups = []
            for arg in domain.args:
                if hasattr(arg, 'inf'):
                    all_infs.append(arg.inf)
                if hasattr(arg, 'sup'):
                    all_sups.append(arg.sup)
            left_bound = min(all_infs) if all_infs else -oo
            right_bound = max(all_sups) if all_sups else oo
        elif hasattr(domain, 'inf'):
            left_bound = domain.inf
            right_bound = domain.sup if hasattr(domain, 'sup') else oo
        else:
            left_bound = -oo
            right_bound = oo
        
        # Calculate limits at boundaries
        if left_bound in [-oo, oo]:
            try:
                left_limit = limit(f, x, left_bound)
                if left_limit in [zoo, nan]:
                    left_limit = None
            except:
                pass
        else:
            try:
                left_limit = limit(f, x, left_bound, '+')
                if left_limit in [zoo, nan]:
                    left_limit = None
            except:
                pass
                
        if right_bound in [oo, -oo]:
            try:
                right_limit = limit(f, x, right_bound)
                if right_limit in [zoo, nan]:
                    right_limit = None
            except:
                pass
        else:
            try:
                right_limit = limit(f, x, right_bound, '-')
                if right_limit in [zoo, nan]:
                    right_limit = None
            except:
                pass
                
    except Exception as e:
        pass
        
    return left_limit, right_limit

def find_critical_points_numerical(f, x, domain, f_num):
    """
    Find critical points (where derivative = 0 or undefined) numerically.
    OPTIMIZED: Reduced samples from 10000 to 2000, vectorized operations.
    """
    critical_values = []
    
    try:
        # Get derivative
        df = diff(f, x)
        df_num = lambdify(x, df, modules=['numpy'])
        
        # Get domain bounds
        if hasattr(domain, 'inf') and domain.inf.is_finite:
            x_min = float(domain.inf) + 1e-6
        else:
            x_min = -100.0  # Reduced from -1000
            
        if hasattr(domain, 'sup') and domain.sup.is_finite:
            x_max = float(domain.sup) - 1e-6
        else:
            x_max = 100.0  # Reduced from 1000
        
        # OPTIMIZED: Reduced from 10000 to 2000 samples
        x_samples = np.linspace(x_min, x_max, 2000)
        
        try:
            dy = df_num(x_samples)
            # Vectorized sign change detection
            if isinstance(dy, np.ndarray) and dy.size > 1:
                signs = np.sign(dy)
                sign_changes = np.where(np.diff(signs) != 0)[0]
                
                # Batch evaluate function at critical points
                if len(sign_changes) > 0:
                    x_crits = x_samples[sign_changes]
                    y_crits = np.array([f_num(xc) for xc in x_crits])
                    valid_mask = np.isfinite(y_crits)
                    critical_values.extend(y_crits[valid_mask].tolist())
        except:
            pass
            
    except:
        pass
        
    return critical_values

def analyze_function_behavior(f, x, domain):
    """
    Analyze function to determine if it's unbounded in either direction.
    Uses symbolic limits when possible.
    IMPROVED: Better detection of oscillating functions with growing amplitude.
    """
    has_inf_pos = False
    has_inf_neg = False
    left_lim = None
    right_lim = None
    
    # Rewrite odd roots to real form before computing limits.
    # SymPy treats (-1)**(1/3) as complex, but we want the real cube root.
    # This ensures limit(x**(1/3), x, -oo) returns -oo instead of oo*(-1)**(1/3).
    f_for_limits = rewrite_real_roots(f, x) if has_real_odd_root(f, x) else f
    
    # Always try to check limits at +oo and -oo for unbounded behavior
    # regardless of what the domain says
    try:
        lim_pos_inf = limit(f_for_limits, x, oo)
        # Check for simple infinity
        if lim_pos_inf == oo:
            has_inf_pos = True
            right_lim = oo
        elif lim_pos_inf == -oo:
            has_inf_neg = True
            right_lim = -oo
        # Check for AccumBounds (oscillating functions)
        elif isinstance(lim_pos_inf, AccumBounds):
            if lim_pos_inf.max == oo: has_inf_pos = True
            if lim_pos_inf.min == -oo: has_inf_neg = True
        # Check for expressions like oo*sign(...)
        elif lim_pos_inf.has(oo) and (lim_pos_inf.has(AccumBounds) or lim_pos_inf.has(sign)):
             # Conservatively assume unbounded if it involves infinity
             has_inf_pos = True
             has_inf_neg = True
        elif lim_pos_inf not in [zoo, nan]:
            right_lim = lim_pos_inf
    except:
        pass
    
    try:
        lim_neg_inf = limit(f_for_limits, x, -oo)
        if lim_neg_inf == oo:
            has_inf_pos = True
            left_lim = oo
        elif lim_neg_inf == -oo:
            has_inf_neg = True
            left_lim = -oo
        elif isinstance(lim_neg_inf, AccumBounds):
            if lim_neg_inf.max == oo: has_inf_pos = True
            if lim_neg_inf.min == -oo: has_inf_neg = True
        elif lim_neg_inf.has(oo) and (lim_neg_inf.has(AccumBounds) or lim_neg_inf.has(sign)):
             has_inf_pos = True
             has_inf_neg = True
        elif lim_neg_inf not in [zoo, nan]:
            left_lim = lim_neg_inf
    except:
        pass
    
    # For functions with Abs, check x -> oo and x -> -oo specifically
    if f_for_limits.has(Abs):
        try:
            # abs(x) -> oo as x -> +oo
            lp = limit(f_for_limits, x, oo)
            if lp == oo:
                has_inf_pos = True
            # abs(x) -> oo as x -> -oo
            ln = limit(f_for_limits, x, -oo)
            if ln == oo:
                has_inf_pos = True
        except:
            pass
        
    # Also check limits at internal singularities
    # For functions like 1/x, we need to check limits approaching singularities
    try:
        from sympy import denom
        d = denom(f_for_limits)
        if d != 1:
            sing_points = solveset(d, x, S.Reals)
            if isinstance(sing_points, FiniteSet):
                for pt in sing_points:
                    try:
                        lim_left = limit(f_for_limits, x, pt, '-')
                        lim_right = limit(f_for_limits, x, pt, '+')
                        if lim_left == oo or lim_right == oo:
                            has_inf_pos = True
                        if lim_left == -oo or lim_right == -oo:
                            has_inf_neg = True
                    except:
                        pass
    except:
        pass
    
    return has_inf_neg, has_inf_pos, left_lim, right_lim

def detect_unbounded_oscillation(f_num, gen_min, gen_max):
    """
    Numerically detect if a function has unbounded oscillation.
    For functions like exp(-x)*sin(x), the amplitude grows as x -> -oo.
    Returns (has_inf_neg, has_inf_pos) tuple.
    OPTIMIZED: Uses vectorized evaluation and respects domain bounds.
    """
    has_inf_neg = False
    has_inf_pos = False
    
    # Suppress warnings during numerical probing
    with np.errstate(all='ignore'):
        # Check behavior at increasingly extreme negative values
        # exp(-x)*sin(x) grows unbounded as x -> -infinity
        # Only check if gen_min allows negative values
        if gen_min < 0:
            try:
                neg_extremes = []
                for i in range(1, 6):  # Reduced from 8 to 6 iterations
                    x_val = -10**i
                    if x_val >= gen_min:  # Respect domain bounds
                        try:
                            y = f_num(x_val)
                            if np.isfinite(y) and np.isreal(y):
                                neg_extremes.append(abs(float(np.real(y))))
                        except:
                            pass
                
                # If absolute values are growing rapidly, it's unbounded
                if len(neg_extremes) >= 3:
                    ratios = [neg_extremes[i+1] / neg_extremes[i] if neg_extremes[i] > 1e-10 else 0 
                              for i in range(len(neg_extremes)-1)]
                    if any(r > 10 for r in ratios):
                        has_inf_neg = True
                        has_inf_pos = True
                        debug_print(f"Detected unbounded oscillation (neg direction): ratios={ratios[:3]}", Fore.YELLOW)
            except:
                pass
        
        # Check behavior at increasingly extreme positive values
        try:
            pos_extremes = []
            for i in range(1, 6):  # Reduced from 8 to 6 iterations
                x_val = 10**i
                if x_val <= gen_max:  # Respect domain bounds
                    try:
                        y = f_num(x_val)
                        if np.isfinite(y) and np.isreal(y):
                            pos_extremes.append(abs(float(np.real(y))))
                    except:
                        pass
            
            if len(pos_extremes) >= 3:
                ratios = [pos_extremes[i+1] / pos_extremes[i] if pos_extremes[i] > 1e-10 else 0 
                          for i in range(len(pos_extremes)-1)]
                if any(r > 10 for r in ratios):
                    has_inf_neg = True
                    has_inf_pos = True
                    debug_print(f"Detected unbounded oscillation (pos direction): ratios={ratios[:3]}", Fore.YELLOW)
        except:
            pass
        
        # Also check for oscillation with growing amplitude by sampling densely
        # OPTIMIZED: Only do this if domain extends to negative infinity and use vectorized eval
        if gen_min < -10:
            try:
                # Sample at large negative x values to detect growing oscillation
                # Use smaller sample size and vectorized evaluation
                sample_min = max(gen_min, -500)
                sample_max = min(-10, gen_max)
                if sample_min < sample_max:
                    x_samples = np.linspace(sample_min, sample_max, 100)  # Reduced from 500 to 100
                    # True numpy vectorized evaluation (not np.vectorize)
                    try:
                        y_samples = f_num(x_samples)
                        if np.isscalar(y_samples):
                            y_samples = np.full_like(x_samples, y_samples)
                        y_samples = np.asarray(y_samples, dtype=float)
                    except:
                        y_samples = np.array([f_num(xi) for xi in x_samples], dtype=float)
                    valid = np.isfinite(y_samples)
                    if np.sum(valid) > 20:  # Reduced threshold from 100 to 20
                        y_valid = y_samples[valid]
                        max_abs = np.max(np.abs(y_valid))
                        if max_abs > 1e10:
                            has_inf_neg = True
                            has_inf_pos = True
                            debug_print(f"Large values detected at negative x: max_abs={max_abs:.2e}", Fore.YELLOW)
            except:
                pass
    
    return has_inf_neg, has_inf_pos

def snap_to_clean_value(val, tolerance=1e-6):
    """
    Snap numerical values to nearby mathematically significant values.
    This cleans up results like 0.000001 -> 0, 0.999999 -> 1, etc.
    """
    if not np.isfinite(val):
        return val
    
    # Common clean values to snap to
    clean_values = [
        0, 1, -1, 2, -2, 0.5, -0.5,
        np.pi, -np.pi, np.pi/2, -np.pi/2, np.pi/4, -np.pi/4,
        np.e, -np.e, 1/np.e, -1/np.e,
        np.sqrt(2), -np.sqrt(2), np.sqrt(2)/2, -np.sqrt(2)/2,
        np.sqrt(3), -np.sqrt(3), np.sqrt(3)/2, -np.sqrt(3)/2,
        1/3, -1/3, 2/3, -2/3,
        1/4, -1/4, 3/4, -3/4,
    ]
    
    for clean in clean_values:
        if abs(val - clean) < tolerance:
            return clean
    
    # Also check for values that are essentially 0 but from different sources
    if abs(val) < tolerance:
        return 0.0
    
    return val


def detect_range_gaps(y_values_sorted, all_y_sorted=None, min_gap_fraction=0.15):
    """
    Find significant gaps in observed y-values.
    
    Args:
        y_values_sorted: Pre-processed (e.g. clipped) sorted y-values for gap candidate detection.
        all_y_sorted: Full (unclipped) sorted y-values for verification. If None, uses y_values_sorted.
        min_gap_fraction: Minimum gap size as fraction of total range.
    
    Uses a two-pass approach:
    1. First pass: find candidate gaps using adaptive threshold on clipped data
    2. Second pass: verify each gap against the FULL dataset — a true gap must
       have zero samples in the full dataset inside it.
    Returns list of (gap_start, gap_end) tuples.
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
    
    # Statistical threshold: gap must be significantly larger than typical spacing
    median_diff = np.median(diffs)
    # A true gap should be at least 10x the median spacing AND at least 0.3 absolute
    stat_threshold = max(median_diff * 10.0, 0.3)
    
    # Also require minimum fraction of total range
    abs_threshold = min_gap_fraction * total_range
    
    # Use the larger of stat_threshold and a capped version of abs_threshold.
    # The cap at 2.0 ensures narrow but real gaps (like (-1,1) in 1/sin(x)) 
    # aren't missed when total_range is large.
    threshold = max(stat_threshold, min(abs_threshold, 2.0))
    
    gaps = []
    for i in range(len(diffs)):
        if diffs[i] > threshold:
            gaps.append((y_values_sorted[i], y_values_sorted[i + 1]))
    
    # Merge nearby gaps (artifacts from sparse sampling within a single true gap)
    if len(gaps) > 1:
        merged = [gaps[0]]
        for gs, ge in gaps[1:]:
            prev_gs, prev_ge = merged[-1]
            if gs - prev_ge < median_diff * 5:
                merged[-1] = (prev_gs, ge)
            else:
                merged.append((gs, ge))
        gaps = merged
    
    # Verify gaps against the FULL (unclipped) dataset.
    # A true mathematical gap (like (-1,1) in csc(x)) will have ZERO samples
    # even in the full dataset. Sampling artifacts (gaps between branches due to
    # finite grid) will have samples from other branches filling them in.
    verified = []
    for gs, ge in gaps:
        # Count samples strictly inside the gap in the FULL dataset
        inside = np.searchsorted(all_y_sorted, ge, 'left') - np.searchsorted(all_y_sorted, gs, 'right')
        gap_width = ge - gs
        # True gap: zero or at most 1 sample (numerical noise) in the full dataset
        if inside <= 1 and gap_width > median_diff * 5:
            verified.append((gs, ge))
    
    return verified

def smart_numerical_range(f, x, domain_sympy, behavior_info=None):
    """
    Improved numerical range finder with proper infinity handling.
    OPTIMIZED: Uses Rust acceleration when available.
    
    behavior_info: optional (has_inf_neg, has_inf_pos, left_lim, right_lim) tuple
                   from Strategy C, to avoid recomputing expensive symbolic limits.
    """
    if not SCIPY_AVAILABLE:
        return f"{Fore.YELLOW}Scipy missing.", "N/A"

    try:
        # Create safe numerical function with true vectorization (BUG-06 fix)
        f_num = make_safe_f_num_vectorized(f, x)
        
        debug_print("Numerical range computation starting...", Fore.CYAN)

        # --- STEP 0: DETECT PERIODICALLY UNBOUNDED FUNCTIONS (EDGE-08) ---
        # Only return (-oo, oo) immediately for tan/cot (which truly cover all reals).
        # For sec/csc/1/sin/1/cos, fall through to gap detection.
        if is_periodically_unbounded_no_gap(f):
            debug_print("Detected periodically unbounded function with full range (tan/cot)", Fore.YELLOW)
            return "Interval(-oo, oo)", "Exact (periodic unbounded)"

        # --- STEP 1: USE PRE-COMPUTED BEHAVIOR OR LIGHTWEIGHT FALLBACK ---
        # Avoid calling analyze_function_behavior again — it was already
        # attempted (with timeout) in Strategy C. Recomputing here without
        # a timeout was the single biggest cause of the performance regression.
        if behavior_info is not None:
            has_inf_neg, has_inf_pos, left_lim, right_lim = behavior_info
        else:
            # Lightweight fallback: only check periodically unbounded funcs,
            # skip expensive symbolic limits
            has_inf_neg, has_inf_pos = False, False
            left_lim, right_lim = None, None
        
        # --- STEP 2: DETERMINE SEARCH BOUNDS (moved before oscillation detection) ---
        gen_min, gen_max = -100.0, 100.0  # Default bounds
        domain_is_bounded_left = False
        domain_is_bounded_right = False
        
        # Check if domain has hard boundaries
        # FIX: Use overall domain .inf/.sup instead of collecting internal
        # boundaries from sub-intervals. The old approach produced degenerate
        # ranges for domains like Union((-∞,0),(0,∞)) where both internal
        # boundaries are 0, yielding gen_min > gen_max.
        try:
            if hasattr(domain_sympy, 'inf') and domain_sympy.inf.is_finite:
                gen_min = float(domain_sympy.inf) + 1e-8
                domain_is_bounded_left = True
            if hasattr(domain_sympy, 'sup') and domain_sympy.sup.is_finite:
                gen_max = float(domain_sympy.sup) - 1e-8
                domain_is_bounded_right = True
        except:
            pass
        
        # --- STEP 2.5: NUMERICAL UNBOUNDED OSCILLATION DETECTION ---
        # Skip if we already know it's unbounded from symbolic analysis
        if not (has_inf_neg and has_inf_pos):
            osc_neg, osc_pos = detect_unbounded_oscillation(f_num, gen_min, gen_max)
            if osc_neg:
                has_inf_neg = True
                debug_print("Numerical analysis detected unbounded negative values", Fore.YELLOW)
            if osc_pos:
                has_inf_pos = True
                debug_print("Numerical analysis detected unbounded positive values", Fore.YELLOW)
        
        # --- STEP 3: ADDITIONAL EXTREME VALUE CHECKS ---
        # Skip if already fully unbounded
        if not (has_inf_neg and has_inf_pos):
            if not domain_is_bounded_right:
                try:
                    test_vals = []
                    for i in range(2, 6):
                        v = f_num(10**i)
                        if np.isfinite(v) and np.isreal(v):
                            test_vals.append(float(v))
                    if len(test_vals) >= 2:
                        if all(test_vals[i] > test_vals[i-1] for i in range(1, len(test_vals))):
                            if test_vals[-1] > 1e10:
                                has_inf_pos = True
                        if all(test_vals[i] < test_vals[i-1] for i in range(1, len(test_vals))):
                            if test_vals[-1] < -1e10:
                                has_inf_neg = True
                except:
                    pass
                    
            if not domain_is_bounded_left:
                try:
                    test_vals = []
                    for i in range(2, 6):
                        v = f_num(-10**i)
                        if np.isfinite(v) and np.isreal(v):
                            test_vals.append(float(v))
                    if len(test_vals) >= 2:
                        if all(test_vals[i] > test_vals[i-1] for i in range(1, len(test_vals))):
                            if test_vals[-1] > 1e10:
                                has_inf_pos = True
                        if all(test_vals[i] < test_vals[i-1] for i in range(1, len(test_vals))):
                            if test_vals[-1] < -1e10:
                                has_inf_neg = True
                except:
                    pass

        # --- EARLY EXIT: Fully unbounded in both directions ---
        # Only skip grid search if the function definitely has no gaps.
        # Functions like 1/sin(x), sec(x) are unbounded but have gaps.
        might_have_gaps = _has_reciprocal_trig(f, x) or f.has(sec) or f.has(csc)
        if has_inf_neg and has_inf_pos and not might_have_gaps:
            debug_print("Fully unbounded (no gaps expected) — skipping grid search", Fore.GREEN)
            return "Interval(-oo, oo)", "Hybrid Analysis"
        
        # --- EARLY EXIT: Reciprocal trig with known gap structure ---
        # For 1/sin(x), 1/cos(x), sec(x), csc(x) etc. that are unbounded
        # in both directions: sample one period densely to find the gap.
        # This is far more accurate than trying to detect gaps from sparse
        # multi-period grid sampling.
        if might_have_gaps and has_inf_neg and has_inf_pos:
            try:
                # Sample one period very densely near origin
                # For 1/sin(x), one period is (0, pi); for 1/cos(x), (-pi/2, pi/2)
                # Use a small interval avoiding exact asymptotes
                dense_x = np.linspace(0.001, np.pi - 0.001, 5000)
                dense_y = f_num(dense_x)
                if np.isscalar(dense_y):
                    dense_y = np.full_like(dense_x, dense_y, dtype=float)
                dense_y = np.asarray(dense_y, dtype=float)
                dense_mask = np.isfinite(dense_y)
                dense_y_valid = dense_y[dense_mask]
                
                if len(dense_y_valid) > 100:
                    y_min_branch = np.min(dense_y_valid)
                    y_max_branch = np.max(dense_y_valid)
                    
                    # Snap to clean values
                    y_min_branch = snap_to_clean_value(y_min_branch)
                    y_max_branch = snap_to_clean_value(y_max_branch)
                    
                    # Determine the gap structure:
                    # If all values in this branch are positive (like sin on (0,pi)),
                    # the gap is between -y_max_branch and y_min_branch
                    # Need to also check the negative branch
                    dense_x_neg = np.linspace(-np.pi + 0.001, -0.001, 5000)
                    dense_y_neg = f_num(dense_x_neg)
                    if np.isscalar(dense_y_neg):
                        dense_y_neg = np.full_like(dense_x_neg, dense_y_neg, dtype=float)
                    dense_y_neg = np.asarray(dense_y_neg, dtype=float)
                    neg_mask = np.isfinite(dense_y_neg)
                    dense_y_neg_valid = dense_y_neg[neg_mask]
                    
                    if len(dense_y_neg_valid) > 100:
                        all_branch_y = np.concatenate([dense_y_valid, dense_y_neg_valid])
                        pos_vals = all_branch_y[all_branch_y > 0]
                        neg_vals = all_branch_y[all_branch_y < 0]
                        
                        has_gap = len(pos_vals) > 0 and len(neg_vals) > 0
                        if has_gap:
                            # Gap is between max of negatives and min of positives
                            gap_upper = snap_to_clean_value(np.min(pos_vals))
                            gap_lower = snap_to_clean_value(np.max(neg_vals))
                            
                            # Verify gap: no values exist between gap_lower and gap_upper
                            in_gap = all_branch_y[(all_branch_y > gap_lower) & (all_branch_y < gap_upper)]
                            if len(in_gap) == 0 and gap_upper - gap_lower > 0.1:
                                def fmt_v(val):
                                    if abs(val) < 1e-9: return "0"
                                    return f"{val:.6f}".rstrip('0').rstrip('.')
                                
                                debug_print(f"Reciprocal trig gap detected: ({fmt_v(gap_lower)}, {fmt_v(gap_upper)})", Fore.CYAN)
                                result = f"Union(Interval(-oo, {fmt_v(gap_lower)}), Interval({fmt_v(gap_upper)}, oo))"
                                return result, "Hybrid Analysis (gap detected)"
            except Exception as e:
                debug_print(f"Reciprocal trig fast path failed: {e}", Fore.YELLOW)

        # --- STEP 3: GRID SEARCH FOR LOCAL EXTREMA ---
        # OPTIMIZED: Use Rust acceleration when available
        all_y_values = []
        
        # Use Rust module if available for faster grid generation
        if RUST_AVAILABLE:
            try:
                X_grid = np.array(fast_math_rs.generate_multi_scale_grid(
                    gen_min, gen_max, [10.0, 100.0], 800
                ))
            except:
                X_grid = None
        else:
            X_grid = None
        
        # Fallback to Python implementation
        if X_grid is None or len(X_grid) == 0:
            # For Union domains, we need to sample from each interval
            def get_sample_points(domain, scales):
                """Generate sample points respecting domain structure. OPTIMIZED."""
                points = []
                
                if isinstance(domain, Union):
                    for interval in domain.args:
                        if hasattr(interval, 'inf') and hasattr(interval, 'sup'):
                            low = float(interval.inf) if interval.inf.is_finite else -100
                            high = float(interval.sup) if interval.sup.is_finite else 100
                            # Add buffer to avoid exact boundary
                            low = low + 1e-8 if interval.inf.is_finite else low
                            high = high - 1e-8 if interval.sup.is_finite else high
                            if low < high:
                                # OPTIMIZED: Reduced from 2000 to 500 per interval
                                points.extend(np.linspace(max(low, -100), min(high, 100), 500).tolist())
                else:
                    for scale in scales:
                        search_min = max(gen_min, -scale)
                        search_max = min(gen_max, scale)
                        if search_min < search_max:
                            # OPTIMIZED: Reduced from 2000 to 800 per scale
                            points.extend(np.linspace(search_min, search_max, 800).tolist())
                
                return np.array(sorted(set(points)))
            
            X_grid = get_sample_points(domain_sympy, [10, 100])
        
        if len(X_grid) > 0:
            try:
                # True numpy vectorized evaluation (BUG-06 fix)
                Y_grid = f_num(X_grid)
                if np.isscalar(Y_grid):
                    Y_grid = np.full_like(X_grid, Y_grid, dtype=float)
                Y_grid = np.asarray(Y_grid, dtype=float)
                mask = np.isfinite(Y_grid)
                if np.any(mask):
                    all_y_values.extend(Y_grid[mask].tolist())
                
                # RUST-04: Use adaptive_grid to densify near critical regions
                if RUST_AVAILABLE and np.any(mask):
                    try:
                        # Use derivative sign changes to find critical x-values
                        df = diff(f, x)
                        df_num = lambdify(x, df, modules=['numpy'])
                        df_vals = df_num(X_grid)
                        if np.isscalar(df_vals):
                            df_vals = np.full_like(X_grid, df_vals)
                        df_vals = np.asarray(df_vals, dtype=float)
                        sign_change_idxs = fast_math_rs.find_sign_changes(df_vals)
                        if len(sign_change_idxs) > 0:
                            critical_xs = X_grid[np.array(sign_change_idxs)].tolist()
                            # Generate denser grid near critical points
                            X_dense = np.array(fast_math_rs.adaptive_grid(
                                float(gen_min), float(gen_max), 0, critical_xs, 0.1
                            ))
                            if len(X_dense) > 0:
                                Y_dense = f_num(X_dense)
                                if np.isscalar(Y_dense):
                                    Y_dense = np.full_like(X_dense, Y_dense, dtype=float)
                                Y_dense = np.asarray(Y_dense, dtype=float)
                                dense_mask = np.isfinite(Y_dense)
                                if np.any(dense_mask):
                                    all_y_values.extend(Y_dense[dense_mask].tolist())
                                    debug_print(f"Adaptive grid added {np.sum(dense_mask)} points near {len(critical_xs)} critical regions", Fore.CYAN)
                    except:
                        pass
            except:
                pass
        
        # Also sample near boundaries and near important points
        special_points = [0.001, 0.01, 0.1, 0.5, 1, 2, 5, 10, 100, 
                         -0.001, -0.01, -0.1, -0.5, -1, -2, -5, -10, -100]
        
        # For functions like sin(x)/x, also sample very close to excluded points
        # to capture behavior at removable discontinuities
        if isinstance(domain_sympy, Union):
            # Find gaps in domain (excluded points)
            for i, interval in enumerate(domain_sympy.args[:-1]):
                if hasattr(interval, 'sup'):
                    gap_point = float(interval.sup)
                    # Sample approaching the gap from both sides
                    for eps in [1e-3, 1e-5, 1e-7]:
                        special_points.extend([gap_point - eps, gap_point + eps])
        
        for pt in special_points:
            # Fast numeric domain check (BUG-09: avoids expensive SymPy .contains())
            if not point_in_domain_fast(pt, gen_min, gen_max, f_num):
                continue
            try:
                val = f_num(pt)
                if np.isfinite(val) and np.isreal(val):
                    all_y_values.append(float(val))
            except:
                pass
        
        if not all_y_values:
            return "Numerical Eval Failed (All Complex/NaN)", "Error"

        rough_min = min(all_y_values)
        rough_max = max(all_y_values)
        
        # --- STEP 4: FIND CRITICAL POINTS ---
        critical_vals = find_critical_points_numerical(f, x, domain_sympy, f_num)
        for cv in critical_vals:
            if np.isfinite(cv) and np.isreal(cv):
                all_y_values.append(float(cv))
        
        # --- STEP 5: REFINE WITH OPTIMIZATION ---
        refined_min = rough_min
        refined_max = rough_max
        
        # Use scipy minimize_scalar (C-level Brent's method, no GIL overhead)
        # NOTE: Removed Rust brent_minimize from hot path (BUG-07 fix).
        # Rust Brent calls back to Python 100x per optimization (GIL round-trip
        # each time), making it SLOWER than scipy's pure-C implementation.
        try:
            bounds_lo = max(gen_min, -100)
            bounds_hi = min(gen_max, 100)
            
            # Safe scalar evaluation wrapper
            def safe_f_opt(x_val):
                try:
                    val = f_num(float(x_val))
                    if np.isfinite(val):
                        return float(val)
                    return 1e100
                except:
                    return 1e100
            
            # Find minimum using minimize_scalar (fast, C-level Brent's method)
            try:
                result_min = minimize_scalar(
                    safe_f_opt,
                    bounds=(bounds_lo, bounds_hi),
                    method='bounded',
                    options={'maxiter': 200, 'xatol': 1e-7}
                )
                if result_min.success and np.isfinite(result_min.fun):
                    refined_min = min(refined_min, result_min.fun)
            except:
                pass
            
            # Find maximum (minimize negative)
            try:
                result_max = minimize_scalar(
                    lambda x_val: -safe_f_opt(x_val),
                    bounds=(bounds_lo, bounds_hi),
                    method='bounded',
                    options={'maxiter': 200, 'xatol': 1e-7}
                )
                if result_max.success and np.isfinite(result_max.fun):
                    refined_max = max(refined_max, -result_max.fun)
            except:
                pass
                
        except:
            pass
        
        # Update with all found values
        if all_y_values:
            refined_min = min(refined_min, min(all_y_values))
            refined_max = max(refined_max, max(all_y_values))

        # --- STEP 6: APPLY INFINITY BOUNDS ---
        final_min = refined_min if not has_inf_neg else -np.inf
        final_max = refined_max if not has_inf_pos else np.inf

        # --- STEP 7: SNAP TO CLEAN VALUES ---
        # Clean up values like 0.000001 -> 0, 0.999999 -> 1, etc.
        final_min = snap_to_clean_value(final_min)
        final_max = snap_to_clean_value(final_max)

        # --- FORMATTING ---
        def fmt(val):
            if np.isinf(val): return "oo" if val > 0 else "-oo"
            if abs(val) < 1e-9: return "0"
            if abs(val) > 1e10: return f"{val:.2e}"
            return f"{val:.6f}".rstrip('0').rstrip('.')

        # --- STEP 8: DETECT RANGE GAPS (FEAT-03 / EDGE-02) ---
        # For functions like 1/sin(x), detect that (-1, 1) is not in the range.
        # Allow gap detection even for doubly-unbounded functions if they might
        # have gaps (e.g., csc(x), sec(x), 1/sin(x), 1/cos(x)).
        both_inf = np.isinf(final_min) and np.isinf(final_max)
        run_gap_detection = all_y_values and len(all_y_values) > 100
        if run_gap_detection and (not both_inf or might_have_gaps):
            y_arr = np.array(all_y_values)
            
            # For gap detection, clip extreme outliers that create artificial gaps.
            # Use the central 98% of the data (by value) to avoid extreme tails
            # from singularities or large-x behavior dominating gap detection.
            finite_y = y_arr[np.isfinite(y_arr)]
            if len(finite_y) > 200:
                p1, p99 = np.percentile(finite_y, [1, 99])
                # Expand the range a bit so we don't miss real gaps near extremes
                iqr_range = p99 - p1
                clip_lo = p1 - 0.5 * iqr_range
                clip_hi = p99 + 0.5 * iqr_range
                clipped_y = finite_y[(finite_y >= clip_lo) & (finite_y <= clip_hi)]
            else:
                clipped_y = finite_y
            
            if len(clipped_y) > 200:
                sorted_y = np.sort(clipped_y)
                # Pass full sorted dataset for gap verification
                all_y_sorted = np.sort(finite_y)
                gaps = detect_range_gaps(sorted_y, all_y_sorted=all_y_sorted)
                if gaps:
                    debug_print(f"Detected {len(gaps)} gap(s) in range", Fore.CYAN)
                    # Build union of intervals
                    pieces = []
                    left = final_min
                    for gap_start, gap_end in gaps:
                        gs = snap_to_clean_value(gap_start)
                        ge = snap_to_clean_value(gap_end)
                        if gs > left:
                            pieces.append((left, gs))
                        left = ge
                    if left < final_max:
                        pieces.append((left, final_max))
                    
                    if len(pieces) > 1:
                        parts = []
                        for lo, hi in pieces:
                            lo_inf = np.isinf(lo) and lo < 0
                            hi_inf = np.isinf(hi) and hi > 0
                            lo_s = "-oo" if lo_inf else fmt(lo)
                            hi_s = "oo" if hi_inf else fmt(hi)
                            parts.append(f"Interval({lo_s}, {hi_s})")
                        return "Union(" + ", ".join(parts) + ")", "Hybrid Analysis (gap detected)"

        return f"Interval[{fmt(final_min)}, {fmt(final_max)}]", "Hybrid Analysis"

    except Exception as e:
        return f"Numerical Error: {e}", "Error"

def solve(func_str, show_timing=True):
    """Solve domain and range for a function with optional timing display."""
    stats = TimingStats()
    total_start = time.perf_counter()
    
    x = Symbol("x", real=True)
    print(f"{Fore.CYAN}{Style.BRIGHT}Input: {func_str}")

    # PARSING
    with Timer("parsing") as t:
        try:
            f_raw = get_sympified_expr(func_str)
            # Replace any parsed 'x' symbol with our real-valued x
            # This is important for SymPy to properly compute ranges
            x_parsed = [s for s in f_raw.free_symbols if str(s) == 'x']
            if x_parsed:
                f = f_raw.subs(x_parsed[0], x)
            else:
                f = f_raw
        except Exception as e:
            print(f"{Fore.RED}[FAIL] Parsing Error: {e}"); return None
    stats.parsing_time = t.elapsed

    if f in [zoo, oo, -oo, nan]:
        print(f"{Fore.RED}[FAIL] Infinite/Undefined Expression"); print("-" * 40); return None

    # EDGE-05: Detect constant functions (cheap check first, no expensive simplify)
    if f.is_number:
        domain = S.Reals
        print(f"{Fore.GREEN}Domain: Reals")
        print(f"{Fore.GREEN}Range:  {FiniteSet(f)}  (constant function)")
        print(f"{Style.DIM}Method: Exact (constant)")
        stats.total_time = time.perf_counter() - total_start
        if show_timing:
            print(f"{Fore.BLUE}{Style.DIM}{stats}")
        print("-" * 40)
        return stats
    # For trig identities like sin²+cos², check free_symbols after trigsimp (fast)
    if f.free_symbols:
        try:
            from sympy import trigsimp
            f_ts = trigsimp(f)
            if f_ts.is_number:
                domain = S.Reals
                print(f"{Fore.GREEN}Domain: Reals")
                print(f"{Fore.GREEN}Range:  {FiniteSet(f_ts)}  (constant function)")
                print(f"{Style.DIM}Method: Simplification (constant)")
                stats.total_time = time.perf_counter() - total_start
                if show_timing:
                    print(f"{Fore.BLUE}{Style.DIM}{stats}")
                print("-" * 40)
                return stats
        except:
            pass

    # 1. DOMAIN (with timeout guard — BUG-03 fix)
    with Timer("domain") as t:
        domain_result, domain_timed_out = run_with_timeout(
            lambda: continuous_domain(f, x, S.Reals),
            timeout_seconds=3.0,
            default=S.Reals
        )
        if domain_timed_out:
            domain = S.Reals
            print(f"{Fore.YELLOW}Domain: Assumed Reals (timeout)")
        elif domain_result is not None:
            domain = domain_result
            print(f"{Fore.GREEN}Domain: {domain}")
        else:
            domain = S.Reals
            print(f"{Fore.YELLOW}Domain: Assumed Reals (Calc failed)")
    stats.domain_time = t.elapsed

    # 2. RANGE STRATEGY
    range_res = None
    method = ""
    any_symbolic_timed_out = False  # Track for debug message only
    behavior_info = None  # Track Strategy C result for numerical fallback
    
    # EDGE-01: Detect integer-valued functions (floor, ceiling)
    if has_integer_valued_output(f):
        range_res = S.Integers
        method = "Exact (integer-valued function)"
        debug_print("Detected integer-valued function (floor/ceiling)", Fore.GREEN)
    
    def is_valid_range(result):
        """Check if the result is a valid range (Interval, Union, or numeric FiniteSet)"""
        if result is None:
            return False
        if result == EmptySet:
            return False
        if isinstance(result, FiniteSet):
            if len(result) == 1 and result.args[0] == f:
                return False
            # Accept FiniteSet if ALL elements are actual numbers (EDGE-05 fix)
            if all(arg.is_number for arg in result.args):
                return True
            if all(not arg.is_number for arg in result.args):
                return False
        return True

    # Symbolic range computation with timing AND TIMEOUT
    # Use a SHARED budget to prevent cascade timeouts (BUG-01 fix + performance)
    SYMBOLIC_TOTAL_BUDGET = 3.0  # Total seconds for all symbolic strategies combined
    
    with Timer("symbolic_range") as t:
        if range_res is None:
            budget_start = time.perf_counter()
            
            def remaining_budget():
                return SYMBOLIC_TOTAL_BUDGET - (time.perf_counter() - budget_start)
            
            # Strategy A: Pure Calculus (SymPy function_range)
            def try_function_range():
                return function_range(f, x, domain)
            
            timeout_a = min(SYMBOLIC_TIMEOUT, remaining_budget())
            if timeout_a > 0.1:
                debug_print(f"Attempting SymPy function_range (timeout={timeout_a:.1f}s)...", Fore.BLUE)
                result, timed_out = run_with_timeout(try_function_range, timeout_a)
                
                if timed_out:
                    any_symbolic_timed_out = True
                    debug_print("SymPy function_range TIMED OUT", Fore.YELLOW)
                elif result is not None and is_valid_range(result):
                    range_res = result
                    method = "Exact (function_range)"
                    debug_print(f"SymPy function_range SUCCESS: {result}", Fore.GREEN)

            # Strategy B: Symbolic Min/Max — runs independently of A (BUG-01 fix)
            if range_res is None and remaining_budget() > 0.2:
                def try_min_max():
                    search_dom = domain if domain.is_subset(S.Reals) else S.Reals
                    mn = minimum(f, x, search_dom)
                    mx = maximum(f, x, search_dom)
                    return mn, mx
                
                timeout_b = min(SYMBOLIC_TIMEOUT, remaining_budget())
                debug_print(f"Attempting SymPy min/max (timeout={timeout_b:.1f}s)...", Fore.BLUE)
                result, timed_out = run_with_timeout(try_min_max, timeout_b)
                
                if timed_out:
                    any_symbolic_timed_out = True
                    debug_print("SymPy min/max TIMED OUT", Fore.YELLOW)
                elif result is not None:
                    mn, mx = result
                    # Validate the results are actual numbers or infinity
                    mn_valid = mn is not None and (mn.is_number or mn in [oo, -oo])
                    mx_valid = mx is not None and (mx.is_number or mx in [oo, -oo])
                    
                    if mn_valid and mx_valid:
                        # Check if they are actual numbers or infinity
                        if mn == -oo and mx == oo:
                            range_res = Interval(-oo, oo)
                        elif mn == -oo:
                            range_res = Interval(-oo, mx)
                        elif mx == oo:
                            range_res = Interval(mn, oo)
                        else:
                            range_res = Interval(mn, mx)
                        method = "Exact (min/max)"
                        debug_print(f"SymPy min/max SUCCESS: [{mn}, {mx}]", Fore.GREEN)

            # Strategy C: Try symbolic limits — runs independently of A and B (BUG-01 fix)
            if range_res is None and remaining_budget() > 0.2:
                def try_limit_analysis():
                    return analyze_function_behavior(f, x, domain)
                
                timeout_c = min(SYMBOLIC_TIMEOUT, remaining_budget())
                debug_print(f"Attempting SymPy limit analysis (timeout={timeout_c:.1f}s)...", Fore.BLUE)
                result, timed_out = run_with_timeout(try_limit_analysis, timeout_c)
                
                if timed_out:
                    any_symbolic_timed_out = True
                    debug_print("SymPy limit analysis TIMED OUT", Fore.YELLOW)
                elif result is not None:
                    has_neg_inf, has_pos_inf, left_lim, right_lim = result
                    # Always save behavior_info for numerical fallback
                    behavior_info = result
                    
                    # If we can determine the limits symbolically
                    if has_neg_inf and has_pos_inf:
                        # Check if the function might have gaps (e.g., 1/sin(x), sec(x))
                        # If so, defer to numerical with gap detection
                        if _has_reciprocal_trig(f, x) or f.has(sec) or f.has(csc):
                            debug_print("Limit analysis: unbounded both ways but might have gaps, deferring to numerical", Fore.CYAN)
                        else:
                            range_res = Interval(-oo, oo)
                            method = "Exact (limit analysis)"
                            debug_print("Limit analysis: unbounded in both directions", Fore.GREEN)
                    elif has_neg_inf or has_pos_inf:
                        # One-sided unbounded: let numerical fallback handle the
                        # bounded side. The old code called maximum()/minimum()
                        # here WITHOUT timeout, which could hang indefinitely.
                        debug_print(f"Limit analysis: unbounded ({'neg' if has_neg_inf else 'pos'}), deferring to numerical", Fore.CYAN)
    stats.symbolic_range_time = t.elapsed

    # Strategy D: Smart Numerical with Scipy/Rust (with timing)
    # This is the fallback when symbolic methods fail or timeout
    with Timer("numerical_range") as t:
        if range_res is None:
            if any_symbolic_timed_out:
                debug_print("Using RUST/Numerical fallback due to symbolic timeout", Fore.CYAN)
            else:
                debug_print("Using RUST/Numerical fallback (symbolic methods returned no result)", Fore.CYAN)
            range_res, method = smart_numerical_range(f, x, domain, behavior_info=behavior_info)
            if RUST_AVAILABLE:
                method = method + " [Rust]"
    stats.numerical_range_time = t.elapsed

    # Colorize Output based on method
    if "Error" in str(range_res): 
        col = Fore.RED
    elif "Exact" in method:
        col = Fore.GREEN
    elif "Hybrid" in method:
        col = Fore.CYAN
    else: 
        col = Fore.YELLOW

    print(f"{col}Range:  {range_res}")
    print(f"{Style.DIM}Method: {method}")
    
    # Calculate and display timing
    stats.total_time = time.perf_counter() - total_start
    if show_timing:
        print(f"{Fore.BLUE}{Style.DIM}{stats}")
    print("-" * 40)
    
    return stats

def main():
    print(f"{Fore.MAGENTA}=== ROBUST SOLVER v3 (with Timing) ===")
    print(f"{Fore.MAGENTA}Rust Acceleration: {'ENABLED' if RUST_AVAILABLE else 'DISABLED'}")
    print(f"{Fore.MAGENTA}SciPy Available: {'YES' if SCIPY_AVAILABLE else 'NO'}\n")
    
    all_stats = []
    
    print(f"{Fore.WHITE}--- Standard Tests ---")
    tests = [
        "abs(x)",         # Range: [0, oo)
        "sin(x)/x",       # Range: approximately [-0.217, 1]
        "x**x",           # Range: [e^(-1/e), oo) ≈ [0.6922, oo)
        "1/x",            # Range: (-oo, 0) ∪ (0, ∞)
        "floor(x)",       # Range: Integers
        "x**2",           # Range: [0, oo)
        "sin(x)",         # Range: [-1, 1]
        "exp(x)",         # Range: (0, oo)
        "log(x)",         # Range: (-oo, oo)
        "x**3",           # Range: (-oo, oo)
        "1/(1+x**2)",     # Range: (0, 1]
    ]
    for t in tests: 
        stats = solve(t)
        if stats:
            all_stats.append(stats)
        
    print(f"\n{Fore.WHITE}--- Hard/Complex Tests ---")
    hard_tests = [
        "x * sin(x)",           # Oscillates with growing amplitude -> (-oo, oo)
        "exp(-x**2)",           # Bell curve -> (0, 1]
        "(x**2 - 1)/(x**2 + 1)",# Horizontal Asymptote at 1, min at -1 -> [-1, 1)
        "sqrt(16 - x**2)",      # Semicircle radius 4 -> [0, 4]
        "abs(sin(x))",          # Folded sine -> [0, 1]
        "x + sin(x)",           # Growing oscillation -> (-oo, oo)
        "tan(x)",               # Periodic vertical asymptotes -> (-oo, oo)
        "log(abs(x))",          # Log of magnitude -> (-oo, oo)
        "1/sin(x)",             # Cosecant -> (-oo, -1] U [1, oo)
        "exp(sin(x))",          # Composition -> [1/e, e] ≈ [0.367, 2.718]
    ]
    for t in hard_tests:
        stats = solve(t)
        if stats:
            all_stats.append(stats)
    
    print(f"\n{Fore.WHITE}--- Extreme/Challenging Tests ---")
    extreme_tests = [
        # Inverse trig functions
        "atan(x)",           # Domain: Reals, Range: (-π/2, π/2)
        "asin(x)",           # Domain: [-1, 1], Range: [-π/2, π/2]
        "acos(x)",           # Domain: [-1, 1], Range: [0, π]
        
        # Hyperbolic functions  
        "sinh(x)",           # Domain: Reals, Range: (-∞, ∞)
        "cosh(x)",           # Domain: Reals, Range: [1, ∞)
        "tanh(x)",           # Domain: Reals, Range: (-1, 1)
        
        # Complex compositions
        "sin(x**2)",         # Domain: Reals, Range: [-1, 1]
        "exp(-abs(x))",      # Domain: Reals, Range: (0, 1]
        "x/(1+x**2)",        # Domain: Reals, Range: [-0.5, 0.5]
        "x**2/(1+x**4)",     # Domain: Reals, Range: [0, 0.5]
        "sin(x)*cos(x)",     # Domain: Reals, Range: [-0.5, 0.5] (= sin(2x)/2)
        
        # Rational functions
        "(x-1)/(x+1)",       # Domain: Reals\{-1}, Range: (-∞,1)∪(1,∞)
        "x/(x**2-1)",        # Domain: Reals\{-1,1}, Range: (-∞, ∞)
        "(x**2+1)/(x**2-1)", # Domain: Reals\{-1,1}, Range: (-∞,-1)∪(1,∞)
        
        # Powers and roots
        "x**(1/3)",          # Cube root: Domain: Reals, Range: Reals (Python supports)
        "abs(x)**(1/2)",     # Domain: Reals, Range: [0, ∞)
        "x**4 - x**2",       # Domain: Reals, Range: [-0.25, ∞)
        
        # Exponential variations
        "exp(1/x)",          # Domain: Reals\{0}, Range: (0, ∞)
        "exp(-1/x**2)",      # Domain: Reals\{0}, Range: (0, 1]
        "x*exp(-x**2)",      # Domain: Reals, Range: [-0.429, 0.429] approx
        
        # Logarithmic
        "log(x**2+1)",       # Domain: Reals, Range: [0, ∞)
        "log(1+x**2)/x**2",  # Domain: Reals\{0}, Range: (0, 1]
        
        # Mixed trig
        "sin(x) + cos(x)",   # Domain: Reals, Range: [-√2, √2]
        "sin(x)**2",         # Domain: Reals, Range: [0, 1]
        "sin(x)**2 + cos(x)**2",  # Domain: Reals, Range: {1} (constant!)
        
        # Oscillating with decay/growth
        "sin(x)/x**2",       # Domain: Reals\{0}, Range: (-oo, oo) (diverges at x=0)
        "exp(-x)*sin(x)",    # Domain: Reals, Range: bounded
    ]
    for t in extreme_tests:
        stats = solve(t)
        if stats:
            all_stats.append(stats)
    
    # Print summary statistics
    if all_stats:
        total_time = sum(s.total_time for s in all_stats)
        avg_time = total_time / len(all_stats)
        max_time = max(s.total_time for s in all_stats)
        min_time = min(s.total_time for s in all_stats)
        
        print(f"\n{Fore.MAGENTA}{'='*50}")
        print(f"{Fore.MAGENTA}TIMING SUMMARY ({len(all_stats)} functions)")
        print(f"{Fore.MAGENTA}{'='*50}")
        print(f"{Fore.WHITE}Total time:   {total_time*1000:.2f}ms")
        print(f"{Fore.WHITE}Average time: {avg_time*1000:.2f}ms per function")
        print(f"{Fore.WHITE}Fastest:      {min_time*1000:.2f}ms")
        print(f"{Fore.WHITE}Slowest:      {max_time*1000:.2f}ms")
        
        # Breakdown by category
        total_parse = sum(s.parsing_time for s in all_stats)
        total_domain = sum(s.domain_time for s in all_stats)
        total_sym_range = sum(s.symbolic_range_time for s in all_stats)
        total_num_range = sum(s.numerical_range_time for s in all_stats)
        
        print(f"\n{Fore.CYAN}Time breakdown:")
        print(f"  Parsing:          {total_parse*1000:>8.2f}ms ({100*total_parse/total_time:>5.1f}%)")
        print(f"  Domain calc:      {total_domain*1000:>8.2f}ms ({100*total_domain/total_time:>5.1f}%)")
        print(f"  Symbolic range:   {total_sym_range*1000:>8.2f}ms ({100*total_sym_range/total_time:>5.1f}%)")
        print(f"  Numerical range:  {total_num_range*1000:>8.2f}ms ({100*total_num_range/total_time:>5.1f}%)")
    
    # while True:
    #     u = input("Enter function: ")
    #     solve(u)

if __name__ == "__main__":
    main()