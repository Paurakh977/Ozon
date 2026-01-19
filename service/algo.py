import sys
import numpy as np
import warnings
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

colorama.init(autoreset=True)
warnings.filterwarnings('ignore')

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
            x_min = -1000.0
            
        if hasattr(domain, 'sup') and domain.sup.is_finite:
            x_max = float(domain.sup) - 1e-6
        else:
            x_max = 1000.0
        
        # Sample for sign changes in derivative (critical points)
        x_samples = np.linspace(x_min, x_max, 10000)
        
        try:
            dy = df_num(x_samples)
            # Find where derivative changes sign
            sign_changes = np.where(np.diff(np.sign(dy)))[0]
            
            for idx in sign_changes:
                x_crit = x_samples[idx]
                try:
                    y_crit = f_num(x_crit)
                    if np.isfinite(y_crit):
                        critical_values.append(y_crit)
                except:
                    pass
        except:
            pass
            
    except:
        pass
        
    return critical_values

def analyze_function_behavior(f, x, domain):
    """
    Analyze function to determine if it's unbounded in either direction.
    Uses symbolic limits when possible.
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

def smart_numerical_range(f, x, domain_sympy):
    """
    Improved numerical range finder with proper infinity handling.
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

        # --- STEP 1: ANALYZE FUNCTION BEHAVIOR SYMBOLICALLY ---
        has_inf_neg, has_inf_pos, left_lim, right_lim = analyze_function_behavior(f, x, domain_sympy)
        
        # --- STEP 2: DETERMINE SEARCH BOUNDS ---
        gen_min, gen_max = -1000.0, 1000.0
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
        
        # For unbounded domains, also check behavior at extreme values
        if not domain_is_bounded_right:
            try:
                # Check if function grows to infinity as x -> oo
                test_vals = []
                for i in range(2, 8):
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
                for i in range(2, 8):
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
        # Use multiple scales to catch features at different ranges
        all_y_values = []
        
        # For Union domains, we need to sample from each interval
        def get_sample_points(domain, scales):
            """Generate sample points respecting domain structure."""
            points = []
            
            if isinstance(domain, Union):
                for interval in domain.args:
                    if hasattr(interval, 'inf') and hasattr(interval, 'sup'):
                        low = float(interval.inf) if interval.inf.is_finite else -1000
                        high = float(interval.sup) if interval.sup.is_finite else 1000
                        # Add buffer to avoid exact boundary
                        low = low + 1e-8 if interval.inf.is_finite else low
                        high = high - 1e-8 if interval.sup.is_finite else high
                        if low < high:
                            points.extend(np.linspace(max(low, -1000), min(high, 1000), 2000).tolist())
            else:
                for scale in scales:
                    search_min = max(gen_min, -scale)
                    search_max = min(gen_max, scale)
                    if search_min < search_max:
                        points.extend(np.linspace(search_min, search_max, 2000).tolist())
            
            return np.array(sorted(set(points)))
        
        X_grid = get_sample_points(domain_sympy, [10, 100, 1000])
        
        if len(X_grid) > 0:
            try:
                Y_grid = np.array([f_num(xi) for xi in X_grid])
                mask = np.isfinite(Y_grid) & np.isreal(Y_grid)
                if np.any(mask):
                    all_y_values.extend([float(y) for y in Y_grid[mask]])
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
        
        # Use differential evolution for global optimization
        try:
            bounds = [(max(gen_min, -100), min(gen_max, 100))]
            
            # Find minimum
            def safe_f_opt(x_arr):
                try:
                    val = f_num(x_arr[0])
                    if np.isfinite(val) and np.isreal(val):
                        return float(val)
                    return 1e100
                except:
                    return 1e100
            
            result_min = differential_evolution(safe_f_opt, bounds, maxiter=500, seed=42, polish=True)
            if result_min.success and np.isfinite(result_min.fun):
                refined_min = min(refined_min, result_min.fun)
            
            # Find maximum (minimize negative)
            def safe_neg_f_opt(x_arr):
                try:
                    val = -f_num(x_arr[0])
                    if np.isfinite(val) and np.isreal(val):
                        return float(val)
                    return 1e100
                except:
                    return 1e100
            
            result_max = differential_evolution(safe_neg_f_opt, bounds, maxiter=500, seed=42, polish=True)
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

        # --- FORMATTING ---
        def fmt(val):
            if np.isinf(val): return "oo" if val > 0 else "-oo"
            if abs(val) < 1e-9: return "0"
            if abs(val) > 1e10: return f"{val:.2e}"
            return f"{val:.6f}".rstrip('0').rstrip('.')

        return f"Interval[{fmt(final_min)}, {fmt(final_max)}]", "Hybrid Analysis"

    except Exception as e:
        return f"Numerical Error: {e}", "Error"

def solve(func_str):
    x = Symbol("x", real=True)
    print(f"{Fore.CYAN}{Style.BRIGHT}Input: {func_str}")

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
        print(f"{Fore.RED}[FAIL] Parsing Error: {e}"); return

    if f in [zoo, oo, -oo, nan]:
        print(f"{Fore.RED}[FAIL] Infinite/Undefined Expression"); print("-" * 40); return

    # 1. DOMAIN
    try:
        domain = continuous_domain(f, x, S.Reals)
        print(f"{Fore.GREEN}Domain: {domain}")
    except:
        domain = S.Reals
        print(f"{Fore.YELLOW}Domain: Assumed Reals (Calc failed)")

    # 2. RANGE STRATEGY
    range_res = None
    method = ""
    
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

    # Strategy A: Pure Calculus (SymPy function_range)
    # This is reliable when it works
    try:
        range_res = function_range(f, x, domain)
        if is_valid_range(range_res):
            method = "Exact (function_range)"
        else:
            range_res = None
    except: 
        pass

    # Strategy B: Symbolic Min/Max (SymPy minimum/maximum)
    # Good for functions like abs(x), piecewise
    if range_res is None:
        try:
            # Try to get minimum and maximum symbolically
            search_dom = domain if domain.is_subset(S.Reals) else S.Reals
            mn = minimum(f, x, search_dom)
            mx = maximum(f, x, search_dom)
            
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
        except: 
            pass

    # Strategy C: Try symbolic limits for unbounded behavior
    if range_res is None:
        try:
            # Check behavior at domain boundaries
            has_neg_inf, has_pos_inf, left_lim, right_lim = analyze_function_behavior(f, x, domain)
            
            # If we can determine the limits symbolically
            if has_neg_inf and has_pos_inf:
                range_res = Interval(-oo, oo)
                method = "Exact (limit analysis)"
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
        except:
            pass

    # Strategy D: Smart Numerical with Scipy
    if range_res is None:
        range_res, method = smart_numerical_range(f, x, domain)

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
    print("-" * 40)

def main():
    print(f"{Fore.MAGENTA}=== ROBUST SOLVER v3 ===\n")
    
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
        solve(t)
        
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
        solve(t)
    
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
        solve(t)
    
    # while True:
    #     u = input("Enter function: ")
    #     solve(u)

if __name__ == "__main__":
    main()