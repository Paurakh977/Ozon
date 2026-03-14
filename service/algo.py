import sys
import numpy as np
import warnings
import time
import queue
from functools import lru_cache
from contextlib import contextmanager
from sympy import (Symbol, S, sympify, oo, zoo, nan, lambdify, Abs, floor, ceiling,
                   limit, simplify, diff, solveset, Piecewise, sign, Max, Min, exp, log,
                   re, im, Interval as SympyInterval, Rational, Pow, Integer,
                   tan, cot, sec, csc)
from sympy.calculus.util import continuous_domain, function_range, minimum, maximum, AccumBounds
from sympy.sets import Interval, Union, FiniteSet, EmptySet, Reals, Integers
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
import colorama
from colorama import Fore, Style

try:
    from scipy.optimize import minimize_scalar
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    minimize_scalar = None

try:
    import fast_math_rs
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    fast_math_rs = None

colorama.init(autoreset=True)
warnings.filterwarnings('ignore')

# =============================================================================
# DEBUG AND CONFIGURATION
# =============================================================================

DEBUG_ENGINE = True

def debug_print(msg, color=Fore.MAGENTA):
    if DEBUG_ENGINE:
        print(f"{color}{Style.DIM}[DEBUG] {msg}{Style.RESET_ALL}")

# =============================================================================
# TIMEOUT UTILITIES  (BUG-02 fix: real process kill, no ghost threads)
# =============================================================================

SYMBOLIC_TIMEOUT = 1.0

# Import worker_loop from the standalone module (no circular import)
from worker_process import worker_loop


class SympyWorker:
    """Persistent subprocess for SymPy work.  Killed and restarted on timeout."""

    def __init__(self):
        import multiprocessing
        self.q_in  = multiprocessing.Queue()
        self.q_out = multiprocessing.Queue()
        self.p = multiprocessing.Process(
            target=worker_loop,
            args=(self.q_in, self.q_out),
            daemon=True,
        )
        self.p.start()


_sympy_worker: "SympyWorker | None" = None


def get_worker() -> SympyWorker:
    global _sympy_worker
    if _sympy_worker is None:
        _sympy_worker = SympyWorker()
    return _sympy_worker


def run_with_timeout(task_type, args, timeout_seconds, default=None):
    """
    Submit a task to the persistent SymPy worker.
    Returns (result, timed_out).
    On timeout the hung process is KILLED (not just abandoned) so it
    never becomes a CPU-hogging ghost thread.
    """
    worker = get_worker()

    # Drain any stale results from a previously cancelled task
    while not worker.q_out.empty():
        try:
            worker.q_out.get_nowait()
        except queue.Empty:
            break

    worker.q_in.put((task_type, args))

    try:
        status, value = worker.q_out.get(timeout=timeout_seconds)
        if status == 'err':
            return default, False
        return value, False
    except queue.Empty:
        # True timeout — kill the process so it can't keep running
        worker.p.terminate()
        worker.p.join()
        debug_print(f"TIMEOUT after {timeout_seconds}s — worker process killed and restarted", Fore.YELLOW)
        global _sympy_worker
        _sympy_worker = SympyWorker()
        return default, True


# =============================================================================
# TIMING
# =============================================================================

class Timer:
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
    def __init__(self):
        self.reset()

    def reset(self):
        self.parsing_time       = 0.0
        self.domain_time        = 0.0
        self.symbolic_range_time = 0.0
        self.numerical_range_time = 0.0
        self.total_time         = 0.0

    def __str__(self):
        return (f"Timing: parse={self.parsing_time*1000:.2f}ms, "
                f"domain={self.domain_time*1000:.2f}ms, "
                f"sym_range={self.symbolic_range_time*1000:.2f}ms, "
                f"num_range={self.numerical_range_time*1000:.2f}ms, "
                f"total={self.total_time*1000:.2f}ms")


# =============================================================================
# EXPRESSION HELPERS
# =============================================================================

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
    This lets SymPy recognise cube roots etc. symbolically.
    """
    replacements = {}
    for sub in expr.atoms(Pow):
        e = sub.exp
        if e.is_Float or (e.is_Number and not isinstance(e, (Integer, Rational))):
            # Try odd denominators first (1/3, 2/3, 1/5 …)
            r = _float_to_odd_rational(e)
            if r is not None:
                replacements[sub] = Pow(sub.base, r)
            else:
                # Fall back to even denominators (1/2, 1/4, 3/4 …)
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


def get_sympified_expr(user_input):
    transformations = (standard_transformations + (implicit_multiplication_application,))
    expr = parse_expr(user_input, transformations=transformations)
    expr = _rationalize_float_exponents(expr)
    return expr


# =============================================================================
# EDGE-CASE DETECTION HELPERS
# =============================================================================

PERIODIC_UNBOUNDED_FUNCS  = {tan, cot, sec, csc}
PERIODIC_FULL_RANGE_FUNCS = {tan, cot}      # range = (-oo, oo), no gaps
PERIODIC_GAPPED_FUNCS     = {sec, csc}      # |f| >= 1 always

from sympy import sin as sym_sin, cos as sym_cos


@lru_cache(maxsize=128)
def _has_reciprocal_trig(f, var):
    """Detect 1/sin(x), 1/cos(x), a/sin(x), sec(x), csc(x) etc."""
    from sympy import fraction
    _, denom_expr = fraction(f)
    if denom_expr.has(sym_sin) or denom_expr.has(sym_cos):
        return True
    if f.has(sec) or f.has(csc):
        return True
    return False


def is_periodically_unbounded(f):
    return any(f.has(fc) for fc in PERIODIC_UNBOUNDED_FUNCS)


def is_periodically_unbounded_no_gap(f):
    """True for tan/cot (full range), False for sec/csc/1/sin (gapped)."""
    if _has_reciprocal_trig(f, None):
        return False
    return any(f.has(fc) for fc in PERIODIC_FULL_RANGE_FUNCS)


def has_integer_valued_output(f):
    return f.has(floor) or f.has(ceiling)


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
    Uses true C-level numpy vectorisation (not np.vectorize).
    BUG-06 fix.
    """
    f_rewritten = rewrite_real_roots(f, x) if has_real_odd_root(f, x) else f

    modules = [
        {
            'Heaviside': lambda t: np.heaviside(t, 0.5),
            'Max': np.maximum,
            'Min': np.minimum,
        },
        'numpy',
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
            result = np.asarray(result,
                                dtype=complex if np.iscomplexobj(result) else float)
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
    """
    Determine unbounded behaviour using symbolic limits.
    This copy lives in algo.py for reference and direct testing.
    The worker subprocess uses its own copy in worker_process.py
    (to avoid circular imports on Windows spawn).
    """
    has_inf_pos = False
    has_inf_neg = False
    left_lim  = None
    right_lim = None

    f_for_limits = rewrite_real_roots(f, x) if has_real_odd_root(f, x) else f

    try:
        lp = limit(f_for_limits, x, oo)
        if   lp == oo:  has_inf_pos = True;  right_lim = oo
        elif lp == -oo: has_inf_neg = True;  right_lim = -oo
        elif isinstance(lp, AccumBounds):
            if lp.max == oo:  has_inf_pos = True
            if lp.min == -oo: has_inf_neg = True
        elif lp.has(oo) and (lp.has(AccumBounds) or lp.has(sign)):
            has_inf_pos = True; has_inf_neg = True
        elif lp not in [zoo, nan]:
            right_lim = lp
    except Exception:
        pass

    try:
        ln = limit(f_for_limits, x, -oo)
        if   ln == oo:  has_inf_pos = True;  left_lim = oo
        elif ln == -oo: has_inf_neg = True;  left_lim = -oo
        elif isinstance(ln, AccumBounds):
            if ln.max == oo:  has_inf_pos = True
            if ln.min == -oo: has_inf_neg = True
        elif ln.has(oo) and (ln.has(AccumBounds) or ln.has(sign)):
            has_inf_pos = True; has_inf_neg = True
        elif ln not in [zoo, nan]:
            left_lim = ln
    except Exception:
        pass

    if f_for_limits.has(Abs):
        try:
            if limit(f_for_limits, x, oo)  == oo: has_inf_pos = True
            if limit(f_for_limits, x, -oo) == oo: has_inf_pos = True
        except Exception:
            pass

    try:
        from sympy import denom as sympy_denom
        d = sympy_denom(f_for_limits)
        if d != 1:
            sing_pts = solveset(d, x, S.Reals)
            if isinstance(sing_pts, FiniteSet):
                for pt in sing_pts:
                    try:
                        ll = limit(f_for_limits, x, pt, '-')
                        lr = limit(f_for_limits, x, pt, '+')
                        if ll == oo  or lr == oo:  has_inf_pos = True
                        if ll == -oo or lr == -oo: has_inf_neg = True
                    except Exception:
                        pass
    except Exception:
        pass

    return has_inf_neg, has_inf_pos, left_lim, right_lim


# =============================================================================
# NUMERICAL HELPERS
# =============================================================================

def find_critical_points_numerical(f, x, domain, f_num):
    """Find critical points numerically. Returns list of y-values at crits."""
    critical_values = []
    try:
        df = diff(f, x)
        df_num = lambdify(x, df, modules=['numpy'])

        x_min = float(domain.inf) + 1e-6 if (hasattr(domain, 'inf') and domain.inf.is_finite) else -100.0
        x_max = float(domain.sup) - 1e-6 if (hasattr(domain, 'sup') and domain.sup.is_finite) else 100.0

        x_samples = np.linspace(x_min, x_max, 2000)
        dy = df_num(x_samples)
        if isinstance(dy, np.ndarray) and dy.size > 1:
            signs = np.sign(dy)
            idx   = np.where(np.diff(signs) != 0)[0]
            if len(idx):
                y_crits = np.array([f_num(x_samples[i]) for i in idx])
                critical_values.extend(y_crits[np.isfinite(y_crits)].tolist())
    except Exception:
        pass
    return critical_values


def detect_unbounded_oscillation(f_num, gen_min, gen_max):
    """
    Numerically detect unbounded oscillation (e.g. exp(-x)*sin(x) as x→-∞).
    Returns (has_inf_neg, has_inf_pos).
    """
    has_inf_neg = has_inf_pos = False

    with np.errstate(all='ignore'):
        if gen_min < 0:
            try:
                neg_extremes = []
                for i in range(1, 6):
                    xv = -10 ** i
                    if xv >= gen_min:
                        y = f_num(xv)
                        if np.isfinite(y) and np.isreal(y):
                            neg_extremes.append(abs(float(np.real(y))))
                if len(neg_extremes) >= 3:
                    ratios = [neg_extremes[i+1] / neg_extremes[i]
                              if neg_extremes[i] > 1e-10 else 0
                              for i in range(len(neg_extremes) - 1)]
                    if any(r > 10 for r in ratios):
                        has_inf_neg = has_inf_pos = True
                        debug_print(f"Unbounded oscillation (neg dir): ratios={ratios[:3]}", Fore.YELLOW)
            except Exception:
                pass

        try:
            pos_extremes = []
            for i in range(1, 6):
                xv = 10 ** i
                if xv <= gen_max:
                    y = f_num(xv)
                    if np.isfinite(y) and np.isreal(y):
                        pos_extremes.append(abs(float(np.real(y))))
            if len(pos_extremes) >= 3:
                ratios = [pos_extremes[i+1] / pos_extremes[i]
                          if pos_extremes[i] > 1e-10 else 0
                          for i in range(len(pos_extremes) - 1)]
                if any(r > 10 for r in ratios):
                    has_inf_neg = has_inf_pos = True
                    debug_print(f"Unbounded oscillation (pos dir): ratios={ratios[:3]}", Fore.YELLOW)
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
                        debug_print("Large values at negative x detected", Fore.YELLOW)
            except Exception:
                pass

    return has_inf_neg, has_inf_pos


def snap_to_clean_value(val, tolerance=None):
    """Snap numerical value to nearby mathematically significant constant."""
    if not np.isfinite(val):
        return val

    # Scale-adaptive tolerance (FEAT-04 fix)
    if tolerance is None:
        magnitude = max(abs(val), 1e-10)
        tolerance = magnitude * 1e-6

    clean_values = [
        0, 1, -1, 2, -2, 0.5, -0.5,
        np.pi, -np.pi, np.pi/2, -np.pi/2, np.pi/4, -np.pi/4,
        np.pi/3, -np.pi/3, np.pi/6, -np.pi/6,
        np.e, -np.e, 1/np.e, -1/np.e,
        np.sqrt(2), -np.sqrt(2), np.sqrt(2)/2, -np.sqrt(2)/2,
        np.sqrt(3), -np.sqrt(3), np.sqrt(3)/2, -np.sqrt(3)/2,
        1/3, -1/3, 2/3, -2/3,
        1/4, -1/4, 3/4, -3/4,
    ]
    for clean in clean_values:
        if abs(val - clean) < tolerance:
            return clean
    if abs(val) < tolerance:
        return 0.0
    return val


def detect_range_gaps(y_values_sorted, all_y_sorted=None, min_gap_fraction=0.15):
    """
    Find significant gaps in observed y-values using a two-pass approach.

    Pass 1: find candidate gaps in the clipped/processed data.
    Pass 2: verify each gap against the FULL dataset — a true mathematical
            gap has ZERO samples inside it even in the full data.

    Conservative thresholds (restored from original audit baseline):
      - stat_threshold = max(10 × median_spacing, 0.3)
      - abs_threshold capped at 2.0 so narrow gaps (like (-1,1) in csc)
        are not missed when total_range is large.
    """
    n = len(y_values_sorted)
    if n < 200:           # need enough samples for reliable statistics
        return []

    total_range = y_values_sorted[-1] - y_values_sorted[0]
    if total_range < 1e-10:
        return []

    if all_y_sorted is None:
        all_y_sorted = y_values_sorted

    diffs = np.diff(y_values_sorted)
    median_diff = np.median(diffs)

    # A real gap must be ≥10× typical spacing AND ≥0.3 absolute
    stat_threshold = max(median_diff * 10.0, 0.3)
    abs_threshold  = min_gap_fraction * total_range
    # Cap abs_threshold at 2.0 so narrow gaps survive when total_range is huge
    threshold = max(stat_threshold, min(abs_threshold, 2.0))

    gaps = []
    for i in range(len(diffs)):
        if diffs[i] > threshold:
            gaps.append((y_values_sorted[i], y_values_sorted[i + 1]))

    # Merge adjacent gaps that are artefacts of sparse sampling
    if len(gaps) > 1:
        merged = [gaps[0]]
        for gs, ge in gaps[1:]:
            prev_gs, prev_ge = merged[-1]
            if gs - prev_ge < median_diff * 5:
                merged[-1] = (prev_gs, ge)
            else:
                merged.append((gs, ge))
        gaps = merged

    # Verify: a true gap must have ≤1 sample inside it in the FULL dataset
    verified = []
    for gs, ge in gaps:
        inside = (np.searchsorted(all_y_sorted, ge, 'left')
                  - np.searchsorted(all_y_sorted, gs, 'right'))
        if inside <= 1 and (ge - gs) > median_diff * 5:
            verified.append((gs, ge))

    return verified


# =============================================================================
# MAIN NUMERICAL RANGE FINDER
# =============================================================================

def smart_numerical_range(f, x, domain_sympy, behavior_info=None):
    """
    Hybrid numerical range finder.
    behavior_info: (has_inf_neg, has_inf_pos, left_lim, right_lim) from
                   Strategy C, passed in to avoid recomputation.
    """
    if not SCIPY_AVAILABLE:
        return f"{Fore.YELLOW}SciPy missing.", "N/A"

    try:
        f_num = make_safe_f_num_vectorized(f, x)
        debug_print("Numerical range computation starting...", Fore.CYAN)

        # --- STEP 0: PERIODIC FULL-RANGE SHORTCUT (tan, cot) ---
        if is_periodically_unbounded_no_gap(f):
            debug_print("Detected tan/cot — full range with no gaps", Fore.YELLOW)
            return "Interval(-oo, oo)", "Exact (periodic unbounded)"

        # --- STEP 1: REUSE PRE-COMPUTED BEHAVIOUR INFO ---
        if behavior_info is not None:
            has_inf_neg, has_inf_pos, left_lim, right_lim, sing_limits = behavior_info
        else:
            has_inf_neg = has_inf_pos = False
            left_lim = right_lim = None
            sing_limits = []

        # --- STEP 2: DOMAIN BOUNDS ---
        gen_min, gen_max = -100.0, 100.0
        domain_is_bounded_left = domain_is_bounded_right = False

        try:
            if hasattr(domain_sympy, 'inf') and domain_sympy.inf.is_finite:
                gen_min = float(domain_sympy.inf) + 1e-8
                domain_is_bounded_left = True
            if hasattr(domain_sympy, 'sup') and domain_sympy.sup.is_finite:
                gen_max = float(domain_sympy.sup) - 1e-8
                domain_is_bounded_right = True
        except Exception:
            pass

        # --- STEP 2.5: OSCILLATION DETECTION ---
        if not (has_inf_neg and has_inf_pos):
            osc_neg, osc_pos = detect_unbounded_oscillation(f_num, gen_min, gen_max)
            if osc_neg: has_inf_neg = True
            if osc_pos: has_inf_pos = True

        # --- STEP 3: MONOTONE EXTREME-VALUE CHECKS ---
        if not (has_inf_neg and has_inf_pos):
            for sign_dir, bounded in [(1, domain_is_bounded_right),
                                      (-1, domain_is_bounded_left)]:
                if bounded:
                    continue
                try:
                    test_vals = []
                    for i in range(2, 6):
                        v = f_num(sign_dir * 10**i)
                        if np.isfinite(v) and np.isreal(v):
                            test_vals.append(float(v))
                    if len(test_vals) >= 2:
                        if all(test_vals[k] > test_vals[k-1] for k in range(1, len(test_vals))):
                            if test_vals[-1] > 1e10:  has_inf_pos = True
                        if all(test_vals[k] < test_vals[k-1] for k in range(1, len(test_vals))):
                            if test_vals[-1] < -1e10: has_inf_neg = True
                except Exception:
                    pass

        # Compute once — used in multiple early-exit guards below
        might_have_gaps = _has_reciprocal_trig(f, x) or f.has(sec) or f.has(csc)

        # --- EARLY EXIT: fully unbounded, no gaps ---
        if has_inf_neg and has_inf_pos and not might_have_gaps:
            debug_print("Fully unbounded, no gaps — skipping grid search", Fore.GREEN)
            return "Interval(-oo, oo)", "Hybrid Analysis"

        # --- EARLY EXIT: reciprocal-trig gap structure ---
        # NEW-03 fix: only enter this path when we KNOW it's doubly unbounded.
        if might_have_gaps and not (has_inf_neg and has_inf_pos):
            for pt in [0, np.pi, np.pi/2, 2*np.pi]:
                try:
                    for eps in [1e-5, 1e-7]:
                        for p in [pt + eps, pt - eps]:
                            v = f_num(p)
                            if np.isfinite(v):
                                if v > 1e4: has_inf_pos = True
                                if v < -1e4: has_inf_neg = True
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
                        dense_y_neg = np.full_like(dense_x_neg, dense_y_neg, dtype=float)
                    dense_y_neg = np.asarray(dense_y_neg, dtype=float)
                    dense_y_neg_valid = dense_y_neg[np.isfinite(dense_y_neg)]

                    if len(dense_y_neg_valid) > 100:
                        all_branch = np.concatenate([dense_y_valid, dense_y_neg_valid])
                        pos_vals = all_branch[all_branch > 0]
                        neg_vals = all_branch[all_branch < 0]

                        if len(pos_vals) > 0 and len(neg_vals) > 0:
                            gap_upper = snap_to_clean_value(np.min(pos_vals))
                            gap_lower = snap_to_clean_value(np.max(neg_vals))
                            in_gap = all_branch[(all_branch > gap_lower)
                                               & (all_branch < gap_upper)]
                            if len(in_gap) == 0 and gap_upper - gap_lower > 0.1:
                                def fv(v):
                                    return "0" if abs(v) < 1e-9 else f"{v:.6f}".rstrip('0').rstrip('.')
                                debug_print(f"Reciprocal trig gap: ({fv(gap_lower)}, {fv(gap_upper)})", Fore.CYAN)
                                result = (f"Union(Interval(-oo, {fv(gap_lower)}), "
                                          f"Interval({fv(gap_upper)}, oo))")
                                return result, "Hybrid Analysis (gap detected)"
            except Exception as exc:
                debug_print(f"Reciprocal trig fast path failed: {exc}", Fore.YELLOW)

        # --- STEP 4: GRID SEARCH ---
        all_y_values = []
        limit_vals = set()
        
        def add_limit(val, is_neg_inf=False, is_pos_inf=False):
            try:
                if is_neg_inf and domain_is_bounded_left: return
                if is_pos_inf and domain_is_bounded_right: return
                
                if val is not None and getattr(val, 'is_real', False) and getattr(val, 'is_number', False):
                    fval = float(val)
                    all_y_values.append(fval)
                    limit_vals.add(snap_to_clean_value(fval))
            except Exception:
                pass
                
        add_limit(left_lim, is_neg_inf=True)
        add_limit(right_lim, is_pos_inf=True)
        for sl in sing_limits:
            add_limit(sl)

        sampled_y_values = []

        # NEW-01 fix: correct Rust API call — (gen_min, gen_max, scales_list, samples_per_scale)
        X_grid = None
        if RUST_AVAILABLE:
            try:
                X_grid = np.array(fast_math_rs.generate_multi_scale_grid(
                    float(gen_min), float(gen_max), [10.0, 100.0], 800
                ))
            except Exception:
                X_grid = None

        if X_grid is None or len(X_grid) == 0:
            def get_sample_points(domain, scales):
                points = []
                if isinstance(domain, Union):
                    for interval in domain.args:
                        i_inf = getattr(interval, 'inf', None)
                        i_sup = getattr(interval, 'sup', None)
                        if i_inf is not None and i_sup is not None:
                            low  = float(i_inf) + 1e-8 if getattr(i_inf, 'is_finite', False) else -100.0
                            high = float(i_sup) - 1e-8 if getattr(i_sup, 'is_finite', False) else 100.0
                            if low < high:
                                points.extend(
                                    np.linspace(max(low, -100), min(high, 100), 500).tolist())
                else:
                    for scale in scales:
                        s_min = max(gen_min, -scale)
                        s_max = min(gen_max,  scale)
                        if s_min < s_max:
                            points.extend(np.linspace(s_min, s_max, 800).tolist())
                return np.array(sorted(set(points)))

            X_grid = get_sample_points(domain_sympy, [10, 100])

        if len(X_grid) > 0:
            try:
                Y_grid = f_num(X_grid)
                if np.isscalar(Y_grid):
                    Y_grid = np.full_like(X_grid, Y_grid, dtype=float)
                Y_grid = np.asarray(Y_grid, dtype=float)
                mask = np.isfinite(Y_grid)
                if np.any(mask):
                    sampled_y_values.extend(Y_grid[mask].tolist()); all_y_values.extend(Y_grid[mask].tolist())

                # Adaptive densification near critical regions (RUST-04)
                if RUST_AVAILABLE and np.any(mask):
                    try:
                        df_sym = diff(f, x)
                        df_num = lambdify(x, df_sym, modules=['numpy'])
                        df_vals = df_num(X_grid)
                        if np.isscalar(df_vals):
                            df_vals = np.full_like(X_grid, df_vals)
                        df_vals = np.asarray(df_vals, dtype=float)

                        find_sc = getattr(fast_math_rs, 'find_sign_changes', None)
                        adap_g  = getattr(fast_math_rs, 'adaptive_grid', None)
                        if find_sc and adap_g:
                            sign_change_idxs = find_sc(df_vals)
                            if len(sign_change_idxs) > 0:
                                critical_xs = X_grid[np.array(sign_change_idxs)].tolist()
                                X_dense = np.array(adap_g(
                                    float(gen_min), float(gen_max), 0, critical_xs, 0.1
                                ))
                                if len(X_dense) > 0:
                                    Y_dense = f_num(X_dense)
                                    if np.isscalar(Y_dense):
                                        Y_dense = np.full_like(X_dense, Y_dense, dtype=float)
                                    Y_dense = np.asarray(Y_dense, dtype=float)
                                    dm = np.isfinite(Y_dense)
                                    if np.any(dm):
                                        sampled_y_values.extend(Y_dense[dm].tolist()); all_y_values.extend(Y_dense[dm].tolist())
                                        debug_print(
                                            f"Adaptive grid: {np.sum(dm)} pts near "
                                            f"{len(critical_xs)} critical regions", Fore.CYAN)
                    except Exception:
                        pass
            except Exception:
                pass

        # Special points (boundaries, origin vicinity, removable discontinuities)
        special_points = [0.001, 0.01, 0.1, 0.5, 1, 2, 5, 10, 100,
                          -0.001, -0.01, -0.1, -0.5, -1, -2, -5, -10, -100]
        if isinstance(domain_sympy, Union):
            for interval in domain_sympy.args[:-1]:
                sup = getattr(interval, 'sup', None)
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
                    sampled_y_values.append(float(val)); all_y_values.append(float(val))
            except Exception:
                pass

        if not all_y_values:
            return "Numerical Eval Failed (All Complex/NaN)", "Error"

        # --- STEP 5: CRITICAL POINTS ---
        for cv in find_critical_points_numerical(f, x, domain_sympy, f_num):
            if np.isfinite(cv) and np.isreal(cv):
                sampled_y_values.append(float(cv)); all_y_values.append(float(cv))

        # --- STEP 6: SCIPY OPTIMISATION ---
        refined_min = min(all_y_values)
        refined_max = max(all_y_values)

        if minimize_scalar is not None:
            bounds_lo = max(gen_min, -100)
            bounds_hi = min(gen_max,  100)

            def safe_f_opt(xv):
                try:
                    v = f_num(float(xv))
                    return float(v) if np.isfinite(v) else 1e100
                except Exception:
                    return 1e100

            try:
                r = minimize_scalar(safe_f_opt, bounds=(bounds_lo, bounds_hi),
                                    method='bounded',
                                    options={'maxiter': 200, 'xatol': 1e-7})
                if r.success and np.isfinite(r.fun):
                    refined_min = min(refined_min, r.fun)
                    sampled_y_values.append(float(r.fun))
                    all_y_values.append(float(r.fun))
            except Exception:
                pass

            try:
                r = minimize_scalar(lambda xv: -safe_f_opt(xv),
                                    bounds=(bounds_lo, bounds_hi),
                                    method='bounded',
                                    options={'maxiter': 200, 'xatol': 1e-7})
                if r.success and np.isfinite(r.fun):
                    refined_max = max(refined_max, -r.fun)
                    sampled_y_values.append(float(-r.fun))
                    all_y_values.append(float(-r.fun))
            except Exception:
                pass

        # Merge all collected values
        refined_min = min(refined_min, min(all_y_values))
        refined_max = max(refined_max, max(all_y_values))

        # --- STEP 7: APPLY INFINITY FLAGS ---
        # NEW-05 fix: do NOT auto-promote large-but-finite values to infinity.
        # Only use the flags set by explicit symbolic/numerical unbounded analysis.
        final_min = -np.inf if has_inf_neg else refined_min
        final_max =  np.inf if has_inf_pos else refined_max

        final_min = snap_to_clean_value(final_min)
        final_max = snap_to_clean_value(final_max)

        def fmt(v):
            if np.isinf(v):    return "oo" if v > 0 else "-oo"
            if abs(v) < 1e-9:  return "0"
            if abs(v) > 1e10:  return f"{v:.2e}"
            return f"{v:.6f}".rstrip('0').rstrip('.')

        # --- STEP 8: GAP DETECTION ---
        both_inf = np.isinf(final_min) and np.isinf(final_max)
        if all_y_values and len(all_y_values) > 100 and (not both_inf or might_have_gaps):
            y_arr = np.array(all_y_values)

            if might_have_gaps:
                finite_y = y_arr[np.isfinite(y_arr) & (np.abs(y_arr) < 100)]
            else:
                finite_y = y_arr[np.isfinite(y_arr)]
                if len(finite_y) > 200:
                    p1, p99 = np.percentile(finite_y, [1, 99])
                    iqr = p99 - p1
                    finite_y = finite_y[(finite_y >= p1 - 0.5*iqr) &
                                        (finite_y <= p99 + 0.5*iqr)]

            if len(finite_y) > 200:
                sorted_y    = np.sort(finite_y)
                all_y_sorted = np.sort(y_arr[np.isfinite(y_arr)])
                gaps = detect_range_gaps(sorted_y, all_y_sorted=all_y_sorted)
                if gaps:
                    debug_print(f"Detected {len(gaps)} gap(s) in range", Fore.CYAN)
                    pieces, left = [], final_min
                    for gs, ge in gaps:
                        gs = snap_to_clean_value(gs)
                        ge = snap_to_clean_value(ge)
                        if gs > left:
                            pieces.append((left, gs))
                        left = ge
                    if left < final_max:
                        pieces.append((left, final_max))
                    if len(pieces) > 1:
                        parts = []
                        for lo, hi in pieces:
                            lo_s = "-oo" if (np.isinf(lo) and lo < 0) else fmt(lo)
                            hi_s = "oo"  if (np.isinf(hi) and hi > 0) else fmt(hi)
                            parts.append(f"Interval({lo_s}, {hi_s})")
                        return "Union(" + ", ".join(parts) + ")", "Hybrid Analysis (gap detected)"

        # --- STEP 9: OPEN/CLOSED ENDPOINT DETECTION (EDGE-06) ---
        def check_openness(val, is_min):
            if np.isinf(val):
                return True
            try:
                result, timed_out = run_with_timeout(
                    'solveset_empty', (f, x, val, domain_sympy), timeout_seconds=1.0
                )
                if not timed_out:
                    if result is True: return True
                    if result is False: return False
            except Exception:
                pass
            
            # Fallback numerical check for asymptote vs attained
            try:
                if len(sampled_y_values) > 0:
                    if is_min:
                        actual_min = min(sampled_y_values)
                        if actual_min > val + 1e-11:

                            return True
                    else:
                        actual_max = max(sampled_y_values)
                        if actual_max < val - 1e-11:
                            return True
            except Exception:
                pass
            
            if snap_to_clean_value(val) in limit_vals:
                return True
                
            return False

        left_open  = check_openness(final_min, True)
        right_open = check_openness(final_max, False)

        if   left_open and right_open: interval_str = f"Interval.open({fmt(final_min)}, {fmt(final_max)})"
        elif left_open:                interval_str = f"Interval.Lopen({fmt(final_min)}, {fmt(final_max)})"
        elif right_open:               interval_str = f"Interval.Ropen({fmt(final_min)}, {fmt(final_max)})"
        else:                          interval_str = f"Interval({fmt(final_min)}, {fmt(final_max)})"

        return interval_str, "Hybrid Analysis"

    except Exception as e:
        return f"Numerical Error: {e}", "Error"


# =============================================================================
# MAIN SOLVER
# =============================================================================

def solve(func_str, show_timing=True):
    stats = TimingStats()
    total_start = time.perf_counter()

    x = Symbol("x", real=True)
    print(f"{Fore.CYAN}{Style.BRIGHT}Input: {func_str}")

    # --- PARSING ---
    with Timer("parsing") as t:
        try:
            f_raw = get_sympified_expr(func_str)
            x_parsed = [s for s in f_raw.free_symbols if str(s) == 'x']
            f = f_raw.subs(x_parsed[0], x) if x_parsed else f_raw
        except Exception as e:
            print(f"{Fore.RED}[FAIL] Parsing Error: {e}")
            return None
    stats.parsing_time = t.elapsed

    if f in [zoo, oo, -oo, nan]:
        print(f"{Fore.RED}[FAIL] Infinite/Undefined Expression")
        print("-" * 40)
        return None

    # --- CONSTANT FUNCTION DETECTION (EDGE-05) ---
    if f.is_number:
        print(f"{Fore.GREEN}Domain: Reals")
        print(f"{Fore.GREEN}Range:  {FiniteSet(f)}  (constant function)")
        print(f"{Style.DIM}Method: Exact (constant)")
        stats.total_time = time.perf_counter() - total_start
        if show_timing: print(f"{Fore.BLUE}{Style.DIM}{stats}")
        print("-" * 40)
        return stats

    if f.free_symbols:
        try:
            from sympy import trigsimp
            f_ts = trigsimp(f)
            if f_ts.is_number:
                print(f"{Fore.GREEN}Domain: Reals")
                print(f"{Fore.GREEN}Range:  {FiniteSet(f_ts)}  (constant function)")
                print(f"{Style.DIM}Method: Simplification (constant)")
                stats.total_time = time.perf_counter() - total_start
                if show_timing: print(f"{Fore.BLUE}{Style.DIM}{stats}")
                print("-" * 40)
                return stats
        except Exception:
            pass

    # --- DOMAIN (BUG-03: timeout-guarded) ---
    with Timer("domain") as t:
        domain_result, domain_timed_out = run_with_timeout(
            'domain', (f, x, S.Reals), timeout_seconds=3.0, default=S.Reals
        )
        if domain_timed_out:
            domain = S.Reals
            print(f"{Fore.YELLOW}Domain: Assumed Reals (timeout)")
        elif domain_result is not None:
            domain = domain_result
            print(f"{Fore.GREEN}Domain: {domain}")
        else:
            domain = S.Reals
            print(f"{Fore.YELLOW}Domain: Assumed Reals (calc failed)")
    stats.domain_time = t.elapsed

    # --- RANGE ---
    range_res     = None
    method        = ""
    behavior_info = None
    any_timed_out = False

    # EDGE-01: integer-valued (floor/ceiling)
    if has_integer_valued_output(f):
        range_res = S.Integers
        method    = "Exact (integer-valued function)"
        debug_print("Detected integer-valued function (floor/ceiling)", Fore.GREEN)

    def is_valid_range(result):
        if result is None or result == EmptySet:
            return False
        if isinstance(result, FiniteSet):
            if len(result) == 1 and result.args[0] == f:
                return False
            return all(arg.is_number for arg in result.args)
        return True

    SYMBOLIC_TOTAL_BUDGET = 3.0

    with Timer("symbolic_range") as t:
        if range_res is None:
            budget_start = time.perf_counter()
            remaining    = lambda: SYMBOLIC_TOTAL_BUDGET - (time.perf_counter() - budget_start)

            # Strategy A: function_range
            ta = min(SYMBOLIC_TIMEOUT, remaining())
            if ta > 0.1:
                debug_print(f"Strategy A: function_range (budget={ta:.1f}s)", Fore.BLUE)
                result, timed_out = run_with_timeout('range', (f, x, domain), ta)
                if timed_out:
                    any_timed_out = True
                    debug_print("Strategy A TIMED OUT", Fore.YELLOW)
                elif result is not None and is_valid_range(result):
                    range_res = result
                    method    = "Exact (function_range)"
                    debug_print(f"Strategy A SUCCESS: {result}", Fore.GREEN)

            # Strategy B: symbolic min/max — INDEPENDENT of A (BUG-01 fix)
            if range_res is None and remaining() > 0.2:
                tb = min(SYMBOLIC_TIMEOUT, remaining())
                debug_print(f"Strategy B: min/max (budget={tb:.1f}s)", Fore.BLUE)
                result, timed_out = run_with_timeout('min_max', (f, x, domain), tb)
                if timed_out:
                    any_timed_out = True
                    debug_print("Strategy B TIMED OUT", Fore.YELLOW)
                elif result is not None:
                    mn, mx = result
                    mn_ok = mn is not None and (mn.is_number or mn in [oo, -oo])
                    mx_ok = mx is not None and (mx.is_number or mx in [oo, -oo])
                    if mn_ok and mx_ok:
                        if   mn == -oo and mx == oo: range_res = Interval(-oo, oo)
                        elif mn == -oo:               range_res = Interval(-oo, mx)
                        elif mx == oo:                range_res = Interval(mn, oo)
                        else:                         range_res = Interval(mn, mx)
                        method = "Exact (min/max)"
                        debug_print(f"Strategy B SUCCESS: [{mn}, {mx}]", Fore.GREEN)

            # Strategy C: limit analysis — INDEPENDENT of A and B (BUG-01 fix)
            if range_res is None and remaining() > 0.2:
                tc = min(SYMBOLIC_TIMEOUT, remaining())
                debug_print(f"Strategy C: limit analysis (budget={tc:.1f}s)", Fore.BLUE)
                result, timed_out = run_with_timeout('limit', (f, x, domain), tc)
                if timed_out:
                    any_timed_out = True
                    debug_print("Strategy C TIMED OUT", Fore.YELLOW)
                elif result is not None:
                    has_neg_inf, has_pos_inf, left_lim, right_lim, sing_limits = result
                    behavior_info = result
                    if has_neg_inf and has_pos_inf:
                        if _has_reciprocal_trig(f, x) or f.has(sec) or f.has(csc):
                            debug_print("Strategy C: doubly unbounded but gapped — deferring to numerical", Fore.CYAN)
                        else:
                            range_res = Interval(-oo, oo)
                            method    = "Exact (limit analysis)"
                            debug_print("Strategy C: unbounded in both directions", Fore.GREEN)
                    elif has_neg_inf or has_pos_inf:
                        debug_print(f"Strategy C: one-sided unbounded — deferring to numerical", Fore.CYAN)
    stats.symbolic_range_time = t.elapsed

    # Strategy D: numerical fallback
    with Timer("numerical_range") as t:
        if range_res is None:
            debug_print("Strategy D: numerical fallback" +
                        (" (after timeout)" if any_timed_out else ""), Fore.CYAN)
            range_res, method = smart_numerical_range(
                f, x, domain, behavior_info=behavior_info
            )
            if RUST_AVAILABLE:
                method += " [Rust]"
    stats.numerical_range_time = t.elapsed

    # --- OUTPUT ---
    if range_res is not None and isinstance(range_res, (Interval, Union)):
        def check_bound_attained(val):
            try:
                res, to = run_with_timeout('solveset_empty', (f, x, val, domain), 0.5)
                if not to:
                    if res is False: return True
                    if res is True: return False
            except Exception:
                pass
            return None

        def fix_interval(interv):
            if not isinstance(interv, Interval): return interv
            lo = interv.left_open
            ro = interv.right_open
            
            if lo and interv.start.is_finite:
                if check_bound_attained(interv.start) is True: lo = False
            elif not lo and interv.start.is_finite:
                if check_bound_attained(interv.start) is False: lo = True
                
            if ro and interv.end.is_finite:
                if check_bound_attained(interv.end) is True: ro = False
            elif not ro and interv.end.is_finite:
                if check_bound_attained(interv.end) is False: ro = True
                
            return Interval(interv.start, interv.end, lo, ro)

        if isinstance(range_res, Interval):
            range_res = fix_interval(range_res)
        elif isinstance(range_res, Union):
            range_res = Union(*[fix_interval(arg) for arg in range_res.args])

    if   "Error"  in str(range_res): col = Fore.RED
    elif "Exact"  in method:         col = Fore.GREEN
    elif "Hybrid" in method:         col = Fore.CYAN
    else:                            col = Fore.YELLOW

    print(f"{col}Range:  {range_res}")
    print(f"{Style.DIM}Method: {method}")

    stats.total_time = time.perf_counter() - total_start
    if show_timing:
        print(f"{Fore.BLUE}{Style.DIM}{stats}")
    print("-" * 40)

    return stats


# =============================================================================
# TEST SUITE
# =============================================================================

def main():
    print(f"{Fore.MAGENTA}=== ROBUST SOLVER v4 ===")
    print(f"{Fore.MAGENTA}Rust: {'ENABLED' if RUST_AVAILABLE else 'DISABLED'}   "
          f"SciPy: {'YES' if SCIPY_AVAILABLE else 'NO'}\n")

    all_stats = []

    print(f"{Fore.WHITE}--- Standard Tests ---")
    for fn in [
        "abs(x)",         # [0, oo)
        "sin(x)/x",       # approx [-0.217, 1]
        "x**x",           # [e^(-1/e), oo)
        "1/x",            # (-oo,0)U(0,oo)
        "floor(x)",       # Integers
        "x**2",           # [0, oo)
        "sin(x)",         # [-1, 1]
        "exp(x)",         # (0, oo)
        "log(x)",         # (-oo, oo)
        "x**3",           # (-oo, oo)
        "1/(1+x**2)",     # (0, 1]
    ]:
        s = solve(fn)
        if s: all_stats.append(s)

    print(f"\n{Fore.WHITE}--- Hard/Complex Tests ---")
    for fn in [
        "x * sin(x)",
        "exp(-x**2)",
        "(x**2 - 1)/(x**2 + 1)",
        "sqrt(16 - x**2)",
        "abs(sin(x))",
        "x + sin(x)",
        "tan(x)",
        "log(abs(x))",
        "1/sin(x)",
        "exp(sin(x))",
    ]:
        s = solve(fn)
        if s: all_stats.append(s)

    print(f"\n{Fore.WHITE}--- Extreme/Challenging Tests ---")
    for fn in [
        "atan(x)", "asin(x)", "acos(x)",
        "sinh(x)", "cosh(x)", "tanh(x)",
        "sin(x**2)", "exp(-abs(x))", "x/(1+x**2)", "x**2/(1+x**4)",
        "sin(x)*cos(x)",
        "(x-1)/(x+1)", "x/(x**2-1)", "(x**2+1)/(x**2-1)",
        "x**(1/3)", "abs(x)**(1/2)", "x**4 - x**2",
        "exp(1/x)", "exp(-1/x**2)", "x*exp(-x**2)",
        "log(x**2+1)", "log(1+x**2)/x**2",
        "sin(x) + cos(x)", "sin(x)**2", "sin(x)**2 + cos(x)**2",
        "sin(x)/x**2", "exp(-x)*sin(x)",
    ]:
        s = solve(fn)
        if s: all_stats.append(s)

    if all_stats:
        total   = sum(s.total_time for s in all_stats)
        avg     = total / len(all_stats)
        fastest = min(s.total_time for s in all_stats)
        slowest = max(s.total_time for s in all_stats)

        p_parse  = sum(s.parsing_time        for s in all_stats)
        p_domain = sum(s.domain_time         for s in all_stats)
        p_sym    = sum(s.symbolic_range_time  for s in all_stats)
        p_num    = sum(s.numerical_range_time for s in all_stats)

        print(f"\n{Fore.MAGENTA}{'='*50}")
        print(f"{Fore.MAGENTA}TIMING SUMMARY ({len(all_stats)} functions)")
        print(f"{Fore.MAGENTA}{'='*50}")
        print(f"{Fore.WHITE}Total:   {total*1000:.1f}ms   "
              f"Avg: {avg*1000:.1f}ms   "
              f"Min: {fastest*1000:.1f}ms   "
              f"Max: {slowest*1000:.1f}ms")
        print(f"\n{Fore.CYAN}Breakdown:")
        for label, t in [("Parsing",         p_parse),
                          ("Domain",          p_domain),
                          ("Symbolic range",  p_sym),
                          ("Numerical range", p_num)]:
            print(f"  {label:<20} {t*1000:>8.1f}ms  ({100*t/total:>5.1f}%)")


if __name__ == "__main__":
    # Required on Windows: multiprocessing needs this guard in the main module
    import multiprocessing
    multiprocessing.freeze_support()
    main()