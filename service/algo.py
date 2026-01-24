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
                   re, im, Interval as SympyInterval)
from sympy.calculus.util import continuous_domain, function_range, minimum, maximum, AccumBounds
from sympy.sets import Interval, Union, FiniteSet, EmptySet, Reals
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
import colorama
from colorama import Fore, Style

# Try imports
try:
    from scipy.optimize import minimize_scalar, minimize
    from scipy.optimize import differential_evolution
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
SYMBOLIC_TIMEOUT = 2.0

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

def timed_call(func, timeout=SYMBOLIC_TIMEOUT):
    """Call a function with a soft timeout check.
    Returns (result, timed_out) tuple."""
    start = time.perf_counter()
    try:
        result = func()
        elapsed = time.perf_counter() - start
        return result, False
    except Exception as e:
        return None, False

def get_sympified_expr(user_input):
    transformations = (standard_transformations + (implicit_multiplication_application,))
    return parse_expr(user_input, transformations=transformations)

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
    
    # Always try to check limits at +oo and -oo for unbounded behavior
    # regardless of what the domain says
    try:
        lim_pos_inf = limit(f, x, oo)
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
        lim_neg_inf = limit(f, x, -oo)
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
    if f.has(Abs):
        try:
            # abs(x) -> oo as x -> +oo
            lp = limit(f, x, oo)
            if lp == oo:
                has_inf_pos = True
            # abs(x) -> oo as x -> -oo
            ln = limit(f, x, -oo)
            if ln == oo:
                has_inf_pos = True
        except:
            pass
        
    # Also check limits at internal singularities
    # For functions like 1/x, we need to check limits approaching singularities
    try:
        from sympy import denom
        d = denom(f)
        if d != 1:
            sing_points = solveset(d, x, S.Reals)
            if isinstance(sing_points, FiniteSet):
                for pt in sing_points:
                    try:
                        lim_left = limit(f, x, pt, '-')
                        lim_right = limit(f, x, pt, '+')
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
                if x_val <= gen_max or gen_max >= 100:  # Respect domain bounds
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
                    # Vectorized evaluation with numpy
                    y_samples = np.vectorize(f_num)(x_samples)
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


def smart_numerical_range(f, x, domain_sympy):
    """
    Improved numerical range finder with proper infinity handling.
    OPTIMIZED: Uses Rust acceleration when available.
    """
    if not SCIPY_AVAILABLE:
        return f"{Fore.YELLOW}Scipy missing.", "N/A"

    try:
        # Create a safe numerical function that handles complex results
        def make_safe_f_num(f, x):
            f_num_raw = lambdify(x, f, modules=['numpy'])
            def safe_f(val):
                try:
                    result = f_num_raw(val)
                    # Handle complex results - only return real part if imaginary is negligible
                    if isinstance(result, np.ndarray):
                        if np.iscomplexobj(result):
                            # Only keep values where imaginary part is negligible
                            mask = np.abs(np.imag(result)) < 1e-10
                            result = np.where(mask, np.real(result), np.nan)
                        return result
                    else:
                        if isinstance(result, complex):
                            if abs(result.imag) < 1e-10:
                                return result.real
                            return np.nan
                        return result
                except:
                    return np.nan
            return safe_f
        
        f_num = make_safe_f_num(f, x)
        
        debug_print("RUST numerical range computation starting...", Fore.CYAN)

        # --- STEP 1: ANALYZE FUNCTION BEHAVIOR SYMBOLICALLY ---
        has_inf_neg, has_inf_pos, left_lim, right_lim = analyze_function_behavior(f, x, domain_sympy)
        
        # --- STEP 2: DETERMINE SEARCH BOUNDS (moved before oscillation detection) ---
        gen_min, gen_max = -100.0, 100.0  # Default bounds
        domain_is_bounded_left = False
        domain_is_bounded_right = False
        
        # Check if domain has hard boundaries (handle Union of intervals)
        try:
            if isinstance(domain_sympy, Union):
                all_infs = []
                all_sups = []
                for arg in domain_sympy.args:
                    if hasattr(arg, 'inf') and arg.inf.is_finite:
                        all_infs.append(float(arg.inf))
                    if hasattr(arg, 'sup') and arg.sup.is_finite:
                        all_sups.append(float(arg.sup))
                if all_infs:
                    gen_min = min(all_infs) + 1e-8
                    domain_is_bounded_left = True
                if all_sups:
                    gen_max = max(all_sups) - 1e-8
                    domain_is_bounded_right = True
            else:
                if hasattr(domain_sympy, 'inf') and domain_sympy.inf.is_finite:
                    gen_min = float(domain_sympy.inf) + 1e-8
                    domain_is_bounded_left = True
                if hasattr(domain_sympy, 'sup') and domain_sympy.sup.is_finite:
                    gen_max = float(domain_sympy.sup) - 1e-8
                    domain_is_bounded_right = True
        except:
            pass
        
        # --- STEP 2.5: NUMERICAL UNBOUNDED OSCILLATION DETECTION ---
        # For functions like exp(-x)*sin(x), symbolic limits may not detect unbounded behavior
        # Now we pass the actual domain bounds to avoid sampling outside the domain
        osc_neg, osc_pos = detect_unbounded_oscillation(f_num, gen_min, gen_max)
        if osc_neg:
            has_inf_neg = True
            debug_print("Numerical analysis detected unbounded negative values", Fore.YELLOW)
        if osc_pos:
            has_inf_pos = True
            debug_print("Numerical analysis detected unbounded positive values", Fore.YELLOW)
        
        # --- STEP 3: ADDITIONAL EXTREME VALUE CHECKS ---
        # For unbounded domains, also check behavior at extreme values
        # OPTIMIZED: Reduced test range
        if not domain_is_bounded_right:
            try:
                test_vals = []
                for i in range(2, 6):  # Reduced from 2-8
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
                for i in range(2, 6):  # Reduced from 2-8
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
                # OPTIMIZED: Vectorized evaluation
                Y_grid = np.vectorize(f_num)(X_grid)
                mask = np.isfinite(Y_grid) & np.isreal(Y_grid)
                if np.any(mask):
                    all_y_values.extend(Y_grid[mask].astype(float).tolist())
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
        
        # Helper to check if a point is in the domain
        def point_in_domain(pt, dom):
            try:
                pt_sym = float(pt)
                return dom.contains(pt_sym) == True
            except:
                return False
        
        for pt in special_points:
            # Only sample points that are actually in the domain
            if not point_in_domain(pt, domain_sympy):
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
        
        # OPTIMIZED: Use Rust Brent's method if available (much faster than differential_evolution)
        if RUST_AVAILABLE:
            try:
                bounds_min = max(gen_min, -100)
                bounds_max = min(gen_max, 100)
                
                # Find minimum using Rust Brent's method
                x_min, f_min = fast_math_rs.brent_minimize(
                    f_num, bounds_min, bounds_max, 1e-6, 100
                )
                if np.isfinite(f_min):
                    refined_min = min(refined_min, f_min)
                
                # Find maximum (minimize negative)
                neg_f_num = lambda x: -f_num(x)
                x_max, neg_f_max = fast_math_rs.brent_minimize(
                    neg_f_num, bounds_min, bounds_max, 1e-6, 100
                )
                if np.isfinite(neg_f_max):
                    refined_max = max(refined_max, -neg_f_max)
            except:
                pass
        
        # Fallback to scipy optimization
        try:
            bounds = [(max(gen_min, -100), min(gen_max, 100))]
            
            # Find minimum
            def safe_f_opt(x_arr):
                try:
                    val = f_num(x_arr[0]) if hasattr(x_arr, '__len__') else f_num(x_arr)
                    if np.isfinite(val) and np.isreal(val):
                        return float(val)
                    return 1e100
                except:
                    return 1e100
            
            # Try faster minimize_scalar first
            try:
                result_scalar = minimize_scalar(
                    lambda x: safe_f_opt([x]),
                    bounds=(bounds[0][0], bounds[0][1]),
                    method='bounded',
                    options={'maxiter': 100}
                )
                if result_scalar.success and np.isfinite(result_scalar.fun):
                    refined_min = min(refined_min, result_scalar.fun)
            except:
                pass
            
            # OPTIMIZED: Reduced maxiter from 500 to 100, added workers=-1 for parallel
            result_min = differential_evolution(
                safe_f_opt, bounds, 
                maxiter=100,  # Reduced from 500
                seed=42, 
                polish=False,  # Disable polishing for speed
                tol=0.01,  # More tolerant convergence
                atol=0.01,
                updating='deferred',  # Better for parallel
                workers=1  # Use single worker to avoid overhead for simple functions
            )
            if result_min.success and np.isfinite(result_min.fun):
                refined_min = min(refined_min, result_min.fun)
            
            # Find maximum (minimize negative)
            def safe_neg_f_opt(x_arr):
                try:
                    val = f_num(x_arr[0]) if hasattr(x_arr, '__len__') else f_num(x_arr)
                    if np.isfinite(val) and np.isreal(val):
                        return -float(val)
                    return 1e100
                except:
                    return 1e100
            
            # Try faster minimize_scalar first for maximum
            try:
                result_scalar = minimize_scalar(
                    lambda x: safe_neg_f_opt([x]),
                    bounds=(bounds[0][0], bounds[0][1]),
                    method='bounded',
                    options={'maxiter': 100}
                )
                if result_scalar.success and np.isfinite(result_scalar.fun):
                    refined_max = max(refined_max, -result_scalar.fun)
            except:
                pass
            
            result_max = differential_evolution(
                safe_neg_f_opt, bounds,
                maxiter=100,  # Reduced from 500
                seed=42,
                polish=False,
                tol=0.01,
                atol=0.01,
                updating='deferred',
                workers=1
            )
            if result_max.success and np.isfinite(result_max.fun):
                refined_max = max(refined_max, -result_max.fun)
                
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

    # 1. DOMAIN
    with Timer("domain") as t:
        try:
            domain = continuous_domain(f, x, S.Reals)
            print(f"{Fore.GREEN}Domain: {domain}")
        except:
            domain = S.Reals
            print(f"{Fore.YELLOW}Domain: Assumed Reals (Calc failed)")
    stats.domain_time = t.elapsed

    # 2. RANGE STRATEGY
    range_res = None
    method = ""
    symbolic_timed_out = False
    
    def is_valid_range(result):
        """Check if the result is a valid range (Interval or Union of Intervals, not just the expression)"""
        if result is None:
            return False
        if result == EmptySet:
            return False
        # If it's a FiniteSet containing the original expression, it's not valid
        if isinstance(result, FiniteSet):
            # Check if it just contains the expression itself (failed computation)
            if len(result) == 1 and result.args[0] == f:
                return False
            # Check if it contains only symbolic expressions (not numbers)
            if all(not arg.is_number for arg in result.args):
                return False
        return True

    # Symbolic range computation with timing AND TIMEOUT
    with Timer("symbolic_range") as t:
        # Strategy A: Pure Calculus (SymPy function_range) - WITH TIMEOUT
        # This is reliable when it works, but can hang on complex functions
        def try_function_range():
            return function_range(f, x, domain)
        
        debug_print(f"Attempting SymPy function_range (timeout={SYMBOLIC_TIMEOUT}s)...", Fore.BLUE)
        result, timed_out = run_with_timeout(try_function_range, SYMBOLIC_TIMEOUT)
        
        if timed_out:
            symbolic_timed_out = True
            debug_print("SymPy function_range TIMED OUT - will use numerical fallback", Fore.YELLOW)
        elif result is not None and is_valid_range(result):
            range_res = result
            method = "Exact (function_range)"
            debug_print(f"SymPy function_range SUCCESS: {result}", Fore.GREEN)

        # Strategy B: Symbolic Min/Max (SymPy minimum/maximum) - WITH TIMEOUT
        # Good for functions like abs(x), piecewise
        if range_res is None and not symbolic_timed_out:
            def try_min_max():
                search_dom = domain if domain.is_subset(S.Reals) else S.Reals
                mn = minimum(f, x, search_dom)
                mx = maximum(f, x, search_dom)
                return mn, mx
            
            debug_print(f"Attempting SymPy min/max (timeout={SYMBOLIC_TIMEOUT}s)...", Fore.BLUE)
            result, timed_out = run_with_timeout(try_min_max, SYMBOLIC_TIMEOUT)
            
            if timed_out:
                symbolic_timed_out = True
                debug_print("SymPy min/max TIMED OUT - will use numerical fallback", Fore.YELLOW)
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

        # Strategy C: Try symbolic limits for unbounded behavior - WITH TIMEOUT
        if range_res is None and not symbolic_timed_out:
            def try_limit_analysis():
                return analyze_function_behavior(f, x, domain)
            
            debug_print(f"Attempting SymPy limit analysis (timeout={SYMBOLIC_TIMEOUT}s)...", Fore.BLUE)
            result, timed_out = run_with_timeout(try_limit_analysis, SYMBOLIC_TIMEOUT)
            
            if timed_out:
                symbolic_timed_out = True
                debug_print("SymPy limit analysis TIMED OUT - will use numerical fallback", Fore.YELLOW)
            elif result is not None:
                has_neg_inf, has_pos_inf, left_lim, right_lim = result
                
                # If we can determine the limits symbolically
                if has_neg_inf and has_pos_inf:
                    range_res = Interval(-oo, oo)
                    method = "Exact (limit analysis)"
                    debug_print("Limit analysis: unbounded in both directions", Fore.GREEN)
                elif has_neg_inf:
                    # Need to find the maximum numerically
                    try:
                        mx = maximum(f, x, domain)
                        if mx is not None and mx != oo and (mx.is_number or mx in [oo, -oo]):
                            range_res = Interval(-oo, mx)
                            method = "Hybrid (limits + max)"
                    except:
                        pass
                elif has_pos_inf:
                    # Need to find the minimum numerically
                    try:
                        mn = minimum(f, x, domain)
                        if mn is not None and mn != -oo and (mn.is_number or mn in [oo, -oo]):
                            range_res = Interval(mn, oo)
                            method = "Hybrid (limits + min)"
                    except:
                        pass
    stats.symbolic_range_time = t.elapsed

    # Strategy D: Smart Numerical with Scipy/Rust (with timing)
    # This is the fallback when symbolic methods fail or timeout
    with Timer("numerical_range") as t:
        if range_res is None:
            if symbolic_timed_out:
                debug_print("Using RUST/Numerical fallback due to symbolic timeout", Fore.CYAN)
            else:
                debug_print("Using RUST/Numerical fallback (symbolic methods returned no result)", Fore.CYAN)
            range_res, method = smart_numerical_range(f, x, domain)
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
        "sin(x)/x**2",       # Domain: Reals\{0}, Range: approximately bounded
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