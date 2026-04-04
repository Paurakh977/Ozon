import multiprocessing
import queue
import signal
import sys
import threading
import time
from contextlib import contextmanager

import sympy as sp
from sympy.calculus.util import continuous_domain, periodicity, AccumBounds
from sympy.calculus.singularities import singularities
from engines import get_sympified_expr


# ─────────────────────────────────────────────────────────────
# Timeout Handler
# ─────────────────────────────────────────────────────────────

class TimeoutException(Exception):
    """Raised when an operation times out."""
    pass


def run_with_timeout(func, args=(), kwargs=None, timeout_seconds=10.0, default=None):
    """
    Run a function with timeout using threading (works on Windows).
    
    Returns: (result, timed_out: bool)
    """
    if kwargs is None:
        kwargs = {}
    
    result = [default]  # Use list to allow modification in nested function
    exception = [None]
    
    def wrapper():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    if thread.is_alive():
        # Timeout occurred - thread is still running
        # Note: We can't kill threads in Python, but since it's daemon it will die with the program
        return default, True
    
    if exception[0] is not None:
        # Function raised an exception
        return default, False
    
    return result[0], False


class FunctionAnalysisEngine:
    """
    Robust math engine to analyze real functions.
    Extracts: Domain, Intercepts, Extrema, Inflection Points,
    Asymptotes (V/H/O), Parity, Periodicity, and Monotonicity.

    Fixes over v1:
    - Pre-cancel rational expressions (performance: 12s → <1s for removable-hole rationals)
    - Domain computed from original; simplified expression used for everything else
    - _domain_extends_to() gates H/oblique asymptote direction checks
    - VA filter: only check limits from sides that are actually within the domain
    - AccumBounds fully suppressed in oblique and horizontal asymptote output
    - _safe_eval() strips negligible imaginary parts (fixes x^(1/3) monotonicity)
    - get_parity() numerical fallback (fixes ln(x+sqrt(x^2+1)) = arcsinh(x))
    - get_periodicity() tries trigsimp / expand_trig / rewrite fallbacks (fixes sin^2(x))

    """

    def __init__(self, debug=False):
        self.debug = debug
        self.x = sp.Symbol("x", real=True)


    # ─────────────────────────────────────────────────────────────
    # Pre-processing
    # ─────────────────────────────────────────────────────────────

    def _preprocess_expr(self, expr):
        """
        Cancel rational expressions to avoid redundant symbolic work.
        E.g. (x^3-x)/(x^2-1) → x   (holes handled via separately-stored domain)
        Also tries powsimp for expressions like x^(2/3) * x^(1/3) etc.
        """
        # First convert odd fractional powers to real_root for proper real analysis
        expr = self._convert_to_real_roots(expr)

        try:
            cancelled = sp.cancel(expr)
            if cancelled != expr:
                return cancelled
        except Exception:
            pass
        try:
            simplified = sp.powsimp(expr, force=True)
            if simplified != expr:
                return simplified
        except Exception:
            pass
        return expr

    def _convert_to_real_roots(self, expr):
        """
        Convert x^(1/n) for odd n to real_root(x, n) for proper real analysis.
        This ensures cube roots, fifth roots, etc. give real values for negative x.
        E.g., x^(1/3) → real_root(x, 3) so that (-8)^(1/3) = -2, not complex.
        """
        try:
            # Find all Pow atoms that are fractional with x as base
            for atom in expr.atoms(sp.Pow):
                base, exp = atom.as_base_exp()
                if base == self.x or (base.has(self.x) and base.is_polynomial(self.x)):
                    # Check if exponent is 1/n for odd n
                    if isinstance(exp, sp.Rational) and exp.p == 1 and exp.q % 2 == 1:
                        n = exp.q
                        real_root_expr = sp.real_root(base, n)
                        expr = expr.subs(atom, real_root_expr)
                    # Also handle m/n where n is odd (e.g., x^(2/3) = (x^(1/3))^2)
                    elif isinstance(exp, sp.Rational) and exp.q % 2 == 1 and exp.q > 1:
                        n = exp.q
                        m = exp.p
                        # x^(m/n) = real_root(x, n)^m for odd n
                        real_root_expr = sp.real_root(base, n) ** m
                        expr = expr.subs(atom, real_root_expr)
        except Exception:
            pass
        return expr

    # ─────────────────────────────────────────────────────────────
    # Safe evaluation helpers
    # ─────────────────────────────────────────────────────────────

    def _safe_eval(self, expr, x_val):
        """
        Evaluate expr at x_val, returning a Python float.
        Strips negligible imaginary parts — critical for x^(1/3), x^(2/3), etc.
        Returns None if the value is truly complex or evaluation fails.
        """
        try:
            val = expr.subs(self.x, x_val).evalf()
            if val.is_real:
                return float(val)
            c = complex(val)
            if abs(c.imag) < 1e-8 * (abs(c.real) + 1):
                return c.real
            return None
        except Exception:
            return None

    def _has_infinite_oscillation(self, expr):
        """
        Detect if an expression has INFINITE oscillation in a bounded region.
        This is different from oscillation that extends to infinity.

        Examples:
        - sin(1/x), x^2*sin(1/x): TRUE infinite oscillation near x=0
          (infinitely many critical points in any neighborhood of 0)
        - sin(x)/x, x*sin(x): FALSE - oscillation extends to infinity
          but has countable, well-spaced critical points (at roughly nπ)

        The key distinction: if trig argument contains 1/x or similar,
        we have true infinite oscillation. If trig argument is just x,
        the oscillation is "regular" and numerically tractable.
        """
        # Check for trig functions
        trig_funcs = [sp.sin, sp.cos, sp.tan, sp.cot, sp.sec, sp.csc]
        has_trig = expr.has(*trig_funcs)
        if not has_trig:
            return False

        # Check if any trig function has 1/x or x in denominator as argument
        # This indicates infinite oscillation near x=0
        for trig in trig_funcs:
            for atom in expr.atoms(trig):
                arg = atom.args[0]
                # Check if argument has x in denominator (e.g., 1/x, 2/x, 1/(x^2))
                if arg.has(self.x):
                    # Rewrite as fraction and check if x is in denominator
                    try:
                        numer, denom = arg.as_numer_denom()
                        if denom.has(self.x):
                            # Trig of 1/x form - true infinite oscillation
                            return True
                    except:
                        pass

        # For trig(x) forms like sin(x)/x, x*sin(x), the oscillation is
        # "regular" - well-spaced critical points, numerically tractable
        return False

    def _oscillates_at_infinity(self, expr):
        """
        Detect if an expression oscillates as x → ±∞.
        This is different from _has_infinite_oscillation which detects
        infinite oscillation in a bounded region near a point.

        Examples returning True:
        - sin(x), cos(x): pure periodic oscillation
        - x*sin(x), sin(x)/x: non-periodic but still oscillates at infinity
        - x + sin(x): oscillates superimposed on linear growth

        Examples returning False:
        - sin(1/x): oscillates near 0, not at infinity (approaches 0 as x→∞)
        - e^x, x^2, ln(x): no oscillation

        Used for monotonicity: we cannot claim monotonicity extends to ±∞
        for functions that oscillate at infinity.
        """
        trig_funcs = [sp.sin, sp.cos, sp.tan, sp.cot, sp.sec, sp.csc]
        has_trig = expr.has(*trig_funcs)
        if not has_trig:
            return False

        # Check trig arguments - if any trig has argument that grows with x,
        # the function oscillates at infinity
        for trig in trig_funcs:
            for atom in expr.atoms(trig):
                arg = atom.args[0]
                if arg.has(self.x):
                    try:
                        # Check if argument grows as x → ∞
                        # For sin(x), arg = x → grows
                        # For sin(1/x), arg = 1/x → shrinks
                        numer, denom = arg.as_numer_denom()
                        if denom.has(self.x):
                            # Argument like 1/x, 1/x^2 → shrinks, not oscillating at infinity
                            continue
                        else:
                            # Argument like x, 2x, x+1 → grows, oscillates at infinity
                            return True
                    except:
                        # If we can't determine, assume it oscillates
                        return True

        return False

    def _roots_are_incomplete(self, root_set):
        """Check if root finding returned incomplete results (ConditionSet)."""
        if isinstance(root_set, sp.ConditionSet):
            return True
        if isinstance(root_set, (sp.Union, sp.Intersection, sp.Complement)):
            return any(self._roots_are_incomplete(arg) for arg in root_set.args)
        return False

    # ─────────────────────────────────────────────────────────────
    # Domain helpers
    # ─────────────────────────────────────────────────────────────

    def _domain_extends_to(self, domain, direction):
        """
        Check whether the domain has pieces extending to +∞ or -∞.
        Used to skip asymptote checks in directions outside the domain.
        """
        if domain == sp.Reals:
            return True
        if isinstance(domain, sp.Interval):
            return domain.end == sp.oo if direction == sp.oo else domain.start == -sp.oo
        if isinstance(domain, sp.Union):
            return any(self._domain_extends_to(arg, direction) for arg in domain.args)
        if isinstance(domain, sp.Complement):
            return self._domain_extends_to(domain.args[0], direction)
        return False

    def _in_domain(self, point, domain):
        try:
            if isinstance(point, (int, float)):
                point_val = float(point)
                if isinstance(domain, sp.Complement):
                    if not self._in_domain(point_val, domain.args[0]):
                        return False
                    return not self._point_in_set(point_val, domain.args[1])
                elif isinstance(domain, sp.Union):
                    return any(self._in_domain(point_val, arg) for arg in domain.args)
                elif isinstance(domain, sp.Interval):
                    lo = (
                        float(domain.start) if domain.start != -sp.oo else -float("inf")
                    )
                    hi = float(domain.end) if domain.end != sp.oo else float("inf")
                    if domain.left_open:
                        if point_val <= lo:
                            return False
                    else:
                        if point_val < lo:
                            return False
                    if domain.right_open:
                        if point_val >= hi:
                            return False
                    else:
                        if point_val > hi:
                            return False
                    return True
                elif domain == sp.Reals:
                    return True
            result = domain.contains(point)
            if result is True or result == sp.true:
                return True
            if result is False or result == sp.false:
                return False
            simplified = sp.simplify(result)
            if simplified is True or simplified == sp.true:
                return True
            if simplified is False or simplified == sp.false:
                return False
            return domain == sp.Reals
        except Exception:
            return False

    def _point_in_set(self, point_val, s):
        try:
            if isinstance(s, sp.FiniteSet):
                return any(abs(float(pt.evalf()) - point_val) < 1e-9 for pt in s)
            elif isinstance(s, sp.ImageSet):
                lam = s.lamda if hasattr(s, "lamda") else s.args[0]
                var = (
                    lam.variables[0]
                    if hasattr(lam, "variables")
                    else list(lam.free_symbols)[0]
                )
                sample_expr = lam.expr if hasattr(lam, "expr") else lam
                for i in range(-10, 11):
                    try:
                        val = float(sample_expr.subs(var, i).evalf())
                        if abs(val - point_val) < 1e-9:
                            return True
                    except:
                        pass
                return False
            elif isinstance(s, sp.Union):
                return any(self._point_in_set(point_val, arg) for arg in s.args)
            elif isinstance(s, sp.Interval):
                lo = float(s.start) if s.start != -sp.oo else -float("inf")
                hi = float(s.end) if s.end != sp.oo else float("inf")
                in_l = point_val > lo if s.left_open else point_val >= lo
                in_r = point_val < hi if s.right_open else point_val <= hi
                return in_l and in_r
        except:
            pass
        return False

    # ─────────────────────────────────────────────────────────────
    # Root/candidate extraction helpers
    # ─────────────────────────────────────────────────────────────

    def _extract_real_roots(self, point_set, test_pts_set):
        """Recursively parse all roots from complex SymPy Sets."""

        def extract(s):
            if isinstance(s, sp.FiniteSet):
                for p in s:
                    if getattr(p, "is_real", True):
                        test_pts_set.add(p)
            elif isinstance(s, sp.ImageSet):
                lam = s.lamda if hasattr(s, "lamda") else s.args[0]
                var = (
                    lam.variables[0]
                    if hasattr(lam, "variables")
                    else list(lam.free_symbols)[0]
                )
                for i in range(-5, 6):
                    try:
                        val = (
                            lam.expr.subs(var, i)
                            if hasattr(lam, "expr")
                            else lam.subs(var, i)
                        )
                        if getattr(val, "is_real", True):
                            test_pts_set.add(val)
                    except:
                        pass
            elif isinstance(s, sp.Interval):
                if s.start != -sp.oo:
                    test_pts_set.add(s.start)
                if s.end != sp.oo:
                    test_pts_set.add(s.end)
            elif isinstance(s, (sp.Union, sp.Intersection, sp.Complement)):
                for arg in s.args:
                    extract(arg)
            elif isinstance(s, sp.ConditionSet):
                expr_cond = (
                    s.condition.lhs - s.condition.rhs
                    if isinstance(s.condition, sp.Eq)
                    else s.condition
                )
                found_approx = set()
                for guess in [i / 2.0 for i in range(-20, 21)]:
                    try:
                        root = sp.nsolve(expr_cond, self.x, guess)
                        if getattr(root, "is_real", True):
                            val = float(root)
                            if abs(val) < 1e-3:
                                val = 0.0
                            r_val = round(val, 3)
                            if r_val not in found_approx:
                                found_approx.add(r_val)
                                test_pts_set.add(sp.sympify(val))
                    except:
                        pass

        extract(point_set)

    def _extract_real_roots_bounded(self, point_set, test_pts_set, lower, upper):
        """Recursively parse roots from SymPy Sets, bounded to [lower, upper]."""

        def extract(s):
            if isinstance(s, sp.FiniteSet):
                for p in s:
                    try:
                        p_val = float(p.evalf())
                        if getattr(p, "is_real", True) and lower <= p_val <= upper:
                            test_pts_set.add(p)
                    except:
                        pass
            elif isinstance(s, sp.ImageSet):
                lam = s.lamda if hasattr(s, "lamda") else s.args[0]
                var = (
                    lam.variables[0]
                    if hasattr(lam, "variables")
                    else list(lam.free_symbols)[0]
                )
                for i in range(-20, 21):
                    try:
                        val = (
                            lam.expr.subs(var, i)
                            if hasattr(lam, "expr")
                            else lam.subs(var, i)
                        )
                        v = float(val.evalf())
                        if getattr(val, "is_real", True) and lower <= v <= upper:
                            test_pts_set.add(val)
                    except:
                        pass
            elif isinstance(s, sp.Interval):
                try:
                    if s.start != -sp.oo and float(s.start.evalf()) >= lower:
                        test_pts_set.add(s.start)
                    if s.end != sp.oo and float(s.end.evalf()) <= upper:
                        test_pts_set.add(s.end)
                except:
                    pass
            elif isinstance(s, (sp.Union, sp.Intersection, sp.Complement)):
                for arg in s.args:
                    extract(arg)
            elif isinstance(s, sp.ConditionSet):
                expr_cond = (
                    s.condition.lhs - s.condition.rhs
                    if isinstance(s.condition, sp.Eq)
                    else s.condition
                )
                found_approx = set()
                for guess in [i / 2.0 for i in range(-20, 21)]:
                    if lower <= guess <= upper:
                        try:
                            root = sp.nsolve(expr_cond, self.x, guess)
                            if getattr(root, "is_real", True):
                                val = float(root)
                                if lower <= val <= upper:
                                    if abs(val) < 1e-3:
                                        val = 0.0
                                    r_val = round(val, 3)
                                    if r_val not in found_approx:
                                        found_approx.add(r_val)
                                        test_pts_set.add(sp.sympify(val))
                        except:
                            pass

        extract(point_set)

    # ─────────────────────────────────────────────────────────────
    # Analysis methods
    # ─────────────────────────────────────────────────────────────

    def safe_solveset(self, expr, domain=sp.Reals):
        try:
            return sp.solveset(expr, self.x, domain=domain)
        except Exception as e:
            return sp.EmptySet

    def get_domain(self, expr):
        try:
            return continuous_domain(expr, self.x, sp.Reals)
        except Exception as e:
            return sp.Reals

    def get_intercepts(self, expr, domain):
        intercepts = {"x": [], "y": None}

        # Y-intercept: only if 0 is genuinely in the domain
        try:
            if self._in_domain(0, domain):
                y_val = expr.subs(self.x, 0)
                if y_val.is_real and not y_val.has(sp.nan, sp.zoo, sp.I):
                    intercepts["y"] = sp.simplify(y_val)
        except Exception:
            pass

        # X-intercepts
        try:
            x_sols = self.safe_solveset(expr)
            if isinstance(x_sols, sp.FiniteSet):
                valid = []
                for sol in x_sols:
                    try:
                        if sol.is_real and self._in_domain(sol, domain):
                            valid.append(sp.simplify(sol))
                    except:
                        pass
                intercepts["x"] = valid
            elif isinstance(x_sols, sp.EmptySet.__class__) or x_sols == sp.EmptySet:
                intercepts["x"] = []
            elif isinstance(x_sols, sp.ConditionSet):
                # Try to resolve ConditionSet numerically
                resolved = self._resolve_conditionset_intercepts(expr, x_sols, domain)
                if resolved is not None:
                    intercepts["x"] = resolved
                else:
                    # Check if expression is always positive or negative in domain
                    sign_check = self._check_always_positive_or_negative(expr, domain)
                    if sign_check == "positive" or sign_check == "negative":
                        # No real intercepts possible
                        intercepts["x"] = []
                    else:
                        # Can't resolve - return the ConditionSet
                        clean_sols = sp.Intersection(x_sols, domain)
                        intercepts["x"] = clean_sols
            else:
                clean_sols = sp.Intersection(x_sols, domain)
                intercepts["x"] = clean_sols
        except Exception:
            pass
        return intercepts

    def _resolve_conditionset_intercepts(self, expr, cond_set, domain):
        """
        Try to resolve a ConditionSet for x-intercepts numerically.
        Returns a list of found roots, or None if can't resolve.
        """
        try:
            # FIRST: Check if function is always positive or negative
            # This prevents false positives like x^(1/x) which never crosses zero
            sign_check = self._check_always_positive_or_negative(expr, domain)
            if sign_check == "positive" or sign_check == "negative":
                return []  # No intercepts possible

            # Check for infinite oscillation patterns (like sin(1/x), x^2*sin(1/x))
            # These have infinitely many zeros - don't try to enumerate them
            if self._has_infinite_oscillation(expr):
                return None  # Let caller handle as ConditionSet

            # Extract the equation from ConditionSet
            if hasattr(cond_set, "condition"):
                cond = cond_set.condition
                if isinstance(cond, sp.Eq):
                    eq_expr = cond.lhs - cond.rhs
                else:
                    eq_expr = cond
            else:
                eq_expr = expr

            # Try numerical solving at various points
            found_roots = []
            guesses = [0] + [i * 0.5 for i in range(-20, 21) if i != 0]

            for guess in guesses:
                if not self._in_domain(guess, domain):
                    continue
                try:
                    root = sp.nsolve(eq_expr, self.x, guess, prec=15)
                    if getattr(root, "is_real", True):
                        root_val = float(root)
                        if self._in_domain(root_val, domain):
                            # STRICTER check: verify this is actually a root
                            check_val = self._safe_eval(expr, root_val)
                            if check_val is not None and abs(check_val) < 1e-10:
                                # Also verify nearby values have opposite signs (true zero crossing)
                                eps = 1e-6
                                left_val = (
                                    self._safe_eval(expr, root_val - eps)
                                    if self._in_domain(root_val - eps, domain)
                                    else None
                                )
                                right_val = (
                                    self._safe_eval(expr, root_val + eps)
                                    if self._in_domain(root_val + eps, domain)
                                    else None
                                )

                                is_real_zero = False
                                if left_val is not None and right_val is not None:
                                    # BUG 5 FIX: Stricter check for flat zeros (e.g., floor(x))
                                    if left_val * right_val < 0:
                                        is_real_zero = True  # genuine sign change
                                    elif abs(left_val) < 1e-8 and abs(right_val) < 1e-8:
                                        # Both sides zero — could be flat zero (floor) or isolated zero
                                        # Check a WIDER neighborhood: if f is also zero far away, it's flat
                                        wide_eps = 0.3
                                        far_left = self._safe_eval(
                                            expr, root_val - wide_eps
                                        )
                                        far_right = self._safe_eval(
                                            expr, root_val + wide_eps
                                        )
                                        if (
                                            far_left is not None
                                            and abs(far_left) < 1e-8
                                            and self._in_domain(
                                                root_val - wide_eps, domain
                                            )
                                        ):
                                            is_real_zero = False  # flat zero — skip it
                                        elif (
                                            far_right is not None
                                            and abs(far_right) < 1e-8
                                            and self._in_domain(
                                                root_val + wide_eps, domain
                                            )
                                        ):
                                            is_real_zero = False  # flat zero — skip it
                                        else:
                                            is_real_zero = (
                                                True  # isolated zero at cusp/endpoint
                                            )
                                    elif (
                                        left_val * right_val <= 0
                                    ):  # covers == 0 case with sign change
                                        is_real_zero = True
                                elif left_val is not None and abs(left_val) < 1e-8:
                                    is_real_zero = True
                                elif right_val is not None and abs(right_val) < 1e-8:
                                    is_real_zero = True
                                elif abs(check_val) < 1e-12:
                                    # Very close to zero - trust it
                                    is_real_zero = True

                                if is_real_zero:
                                    # Snap very small values to 0 more aggressively
                                    if abs(root_val) < 1e-3:
                                        root_val = 0.0
                                    # Check for duplicates with proper tolerance
                                    is_dup = any(
                                        abs(root_val - existing) < 0.01
                                        for existing in found_roots
                                    )
                                    if not is_dup:
                                        found_roots.append(root_val)
                except:
                    pass

            if found_roots:
                # Remove duplicates more aggressively and sort
                unique_roots = []
                for r in sorted(found_roots):
                    if not unique_roots or abs(r - unique_roots[-1]) > 0.01:
                        unique_roots.append(r)
                # Clean up symbolic representation
                result = []
                for r in unique_roots:
                    if r == 0.0:
                        result.append(sp.Integer(0))
                    else:
                        result.append(sp.sympify(r))
                return result
            return None
        except:
            return None

    def _check_always_positive_or_negative(self, expr, domain):
        """
        Check if expression is always positive or always negative in domain.
        Returns 'positive', 'negative', or None if can't determine.
        """
        try:
            # Sample several points in the domain
            test_points = []

            # Generate test points based on domain
            if domain == sp.Reals:
                test_points = [0.1, 0.5, 1, 2, 5, 10, -0.1, -1, -5]
            elif isinstance(domain, sp.Interval):
                lo = float(domain.start) if domain.start != -sp.oo else -100
                hi = float(domain.end) if domain.end != sp.oo else 100
                # Sample within interval
                for i in range(10):
                    t = lo + (hi - lo) * (i + 1) / 11
                    if self._in_domain(t, domain):
                        test_points.append(t)
            else:
                # For Union/Complement, sample common points
                test_points = [0.01, 0.1, 0.5, 1, 2, 5, 10]
                test_points = [p for p in test_points if self._in_domain(p, domain)]

            if not test_points:
                return None

            signs = []
            for pt in test_points:
                if not self._in_domain(pt, domain):
                    continue
                val = self._safe_eval(expr, pt)
                if val is None:
                    continue
                if val > 0:
                    signs.append(1)
                elif val < 0:
                    signs.append(-1)
                else:
                    # Found a zero - not always positive/negative
                    return None

            if not signs:
                return None
            if all(s > 0 for s in signs):
                return "positive"
            if all(s < 0 for s in signs):
                return "negative"
            return None
        except:
            return None

    def get_extrema(self, expr, domain):
        extrema = {"minima": [], "maxima": []}
        try:
            f_prime = sp.diff(expr, self.x)
            roots = self.safe_solveset(f_prime)

            # Guard against infinite oscillation cases like x^2 * sin(1/x)
            # where the derivative has infinitely many roots that can't be solved.
            # We cannot reliably find extrema in such cases.
            if self._roots_are_incomplete(roots) and self._has_infinite_oscillation(
                expr
            ):
                return extrema

            try:
                domain_f_prime = continuous_domain(f_prime, self.x, sp.Reals)
            except Exception:
                try:
                    sings = singularities(f_prime, self.x)
                    domain_f_prime = sp.Complement(domain, sings)
                except:
                    domain_f_prime = domain

            crit_undef = sp.Complement(sp.Reals, domain_f_prime)

            cands = set()
            self._extract_real_roots(roots, cands)
            self._extract_real_roots(crit_undef, cands)

            # Domain boundary endpoints are extrema candidates
            def extract_boundaries(s):
                if isinstance(s, sp.Interval):
                    if s.start != -sp.oo:
                        cands.add(s.start)
                    if s.end != sp.oo:
                        cands.add(s.end)
                elif isinstance(s, sp.Union):
                    for arg in s.args:
                        extract_boundaries(arg)

            extract_boundaries(domain)

            unique_pts = []
            for p in cands:
                try:
                    if self._in_domain(p, domain):
                        p_val = float(p.evalf())
                        if not any(
                            abs(p_val - float(up.evalf())) < 1e-5 for up in unique_pts
                        ):
                            unique_pts.append(p)
                except:
                    pass
            unique_pts.sort(key=lambda p: float(p.evalf()))

            for cp in unique_pts:
                cp_val = float(cp.evalf())
                eps = 1e-5
                left_in = self._in_domain(cp_val - eps, domain)
                right_in = self._in_domain(cp_val + eps, domain)

                try:
                    # Use _safe_eval to handle complex-valued derivatives (e.g. x^(1/3))
                    left_val = (
                        self._safe_eval(f_prime, cp_val - eps) if left_in else None
                    )
                    right_val = (
                        self._safe_eval(f_prime, cp_val + eps) if right_in else None
                    )
                    y_val = sp.simplify(expr.subs(self.x, cp))

                    # FIX: If derivative is undefined on one side but the function IS defined
                    # (cusp points like x=0 for x^(1/3)), this is NOT necessarily an extremum.
                    # Only count as extremum if there's a genuine sign change.

                    if left_val is not None and right_val is not None:
                        # Both sides defined - check for sign change
                        if left_val < -1e-7 and right_val > 1e-7:
                            extrema["minima"].append((sp.simplify(cp), y_val))
                        elif left_val > 1e-7 and right_val < -1e-7:
                            extrema["maxima"].append((sp.simplify(cp), y_val))
                        # If both same sign: not an extremum (cusp or inflection)
                    elif left_val is None and right_val is not None:
                        # Left endpoint OR cusp where left derivative is complex/undefined
                        # For true endpoint: check if domain actually ends here
                        is_true_endpoint = not self._in_domain(
                            cp_val - 10 * eps, domain
                        )
                        if is_true_endpoint:
                            if right_val > 1e-7:
                                extrema["minima"].append((sp.simplify(cp), y_val))
                            elif right_val < -1e-7:
                                extrema["maxima"].append((sp.simplify(cp), y_val))
                        # If NOT a true endpoint but derivative undefined (cusp), skip
                    elif left_val is not None and right_val is None:
                        # Right endpoint OR cusp where right derivative is complex/undefined
                        is_true_endpoint = not self._in_domain(
                            cp_val + 10 * eps, domain
                        )
                        if is_true_endpoint:
                            if left_val > 1e-7:
                                extrema["maxima"].append((sp.simplify(cp), y_val))
                            elif left_val < -1e-7:
                                extrema["minima"].append((sp.simplify(cp), y_val))
                        # If NOT a true endpoint but derivative undefined (cusp), skip
                except:
                    pass
        except Exception as e:
            raise e
        return extrema

    def get_inflection_points(self, expr, domain):
        inflections = []
        try:
            f_prime = sp.diff(expr, self.x)
            f_dp = sp.diff(f_prime, self.x)
            roots = self.safe_solveset(f_dp)

            try:
                domain_f_dp = continuous_domain(f_dp, self.x, sp.Reals)
            except Exception:
                try:
                    sings = singularities(f_dp, self.x)
                    domain_f_dp = sp.Complement(domain, sings)
                except:
                    domain_f_dp = domain

            undef = sp.Complement(sp.Reals, domain_f_dp)
            cands = set()
            self._extract_real_roots(roots, cands)
            self._extract_real_roots(undef, cands)

            unique_pts = []
            for p in cands:
                try:
                    if self._in_domain(p, domain):
                        p_val = float(p.evalf())
                        if not any(
                            abs(p_val - float(up.evalf())) < 1e-5 for up in unique_pts
                        ):
                            unique_pts.append(p)
                except:
                    pass
            unique_pts.sort(key=lambda p: float(p.evalf()))

            for cp in unique_pts:
                cp_val = float(cp.evalf())
                eps = 1e-5
                try:
                    if not (
                        self._in_domain(cp_val - eps, domain)
                        and self._in_domain(cp_val + eps, domain)
                    ):
                        continue  # Endpoints cannot be inflection points

                    lv = self._safe_eval(f_dp, cp_val - eps)
                    rv = self._safe_eval(f_dp, cp_val + eps)
                    if lv is None or rv is None:
                        continue

                    lv_sign = 1 if lv > 0 else (-1 if lv < 0 else 0)
                    rv_sign = 1 if rv > 0 else (-1 if rv < 0 else 0)
                    if lv_sign != 0 and rv_sign != 0 and lv_sign != rv_sign:
                        y_val = sp.simplify(expr.subs(self.x, cp))
                        inflections.append((sp.simplify(cp), y_val))
                except:
                    pass
        except Exception as e:
            raise e
        return inflections

    def get_asymptotes(self, expr, domain):
        asymptotes = {"vertical": [], "horizontal": [], "oblique": []}

        # ── Horizontal asymptotes ──────────────────────────────────
        # FIX: only check directions the domain actually extends to
        for d in [sp.oo, -sp.oo]:
            if not self._domain_extends_to(domain, d):
                continue
            try:
                L = sp.limit(expr, self.x, d)
                if isinstance(L, AccumBounds):
                    continue  # Oscillating — no HA in this direction
                if L.is_real and not L.is_infinite and not L.has(sp.zoo, sp.nan):
                    val = sp.simplify(L)
                    if val not in asymptotes["horizontal"]:
                        asymptotes["horizontal"].append(val)
            except:
                pass

        # ── Oblique asymptotes ────────────────────────────────────
        # FIX: skip AccumBounds at every step; only check valid directions
        for d in [sp.oo, -sp.oo]:
            if not self._domain_extends_to(domain, d):
                continue
            try:
                m = sp.limit(expr / self.x, self.x, d)
                if isinstance(m, AccumBounds):
                    continue
                if (
                    m.is_real
                    and not m.is_infinite
                    and m != 0
                    and not m.has(sp.zoo, sp.nan)
                ):
                    c = sp.limit(expr - m * self.x, self.x, d)
                    if isinstance(c, AccumBounds):
                        continue  # FIX: oscillation ⇒ no oblique asymptote
                    if c.is_real and not c.is_infinite and not c.has(sp.zoo, sp.nan):
                        line = sp.simplify(m * self.x + c)
                        # FIX: Check if the function IS the line (not just approaching it)
                        # For Abs(x), the function equals x for x>0 and -x for x<0
                        # These are NOT asymptotes - the function coincides with them
                        diff = sp.simplify(expr - line)
                        # Guard against piecewise functions like abs(x) that equal
                        # the asymptotic line in one direction but are NOT polynomials.
                        # For rational functions that simplify to a line (like (x^2-4)/(x-2) → x+2),
                        # the simplified expr is a polynomial, so we SHOULD report the asymptote.
                        # "A line is its own oblique asymptote" - per mathematical convention.
                        try:
                            # ONLY apply numerical check for non-polynomial expressions.
                            # Polynomials (including those from cancelled rational functions)
                            # should always report their asymptotic line.
                            is_polynomial = expr.is_polynomial(self.x)
                            if is_polynomial is not True:  # None or False
                                # Non-polynomial case: check if it numerically equals line at test point
                                # This catches abs(x)-like piecewise functions
                                test_val = 1e6 if d == sp.oo else -1e6
                                diff_at_test = self._safe_eval(diff, test_val)
                                if (
                                    diff_at_test is not None
                                    and abs(diff_at_test) < 1e-6
                                ):
                                    # The function equals the line at this test point,
                                    # but it's not a polynomial - likely piecewise (like abs)
                                    continue
                        except:
                            pass
                        if line not in asymptotes["oblique"]:
                            asymptotes["oblique"].append(line)
            except:
                pass

        # ── Vertical asymptotes ───────────────────────────────────
        try:
            excluded = sp.Complement(sp.Reals, domain)

            def check_va_at_point(pt, check_left=True, check_right=True):
                """
                Return True only when a genuine VA exists at pt.
                KEY FIX: we only probe limits from sides that are actually
                inside the domain — this prevents spurious VAs like x=0 for
                ln(ln(x)) whose domain is (1, ∞).
                """
                if pt.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I):
                    return False
                try:
                    pt_f = float(pt.evalf())
                    if abs(pt_f) > 1e10:
                        return False
                    eps = 1e-7
                    dom_left = self._in_domain(pt_f - eps, domain)
                    dom_right = self._in_domain(pt_f + eps, domain)
                    # If NEITHER side is in the domain, this point is irrelevant
                    if not dom_left and not dom_right:
                        return False
                    eff_left = check_left and dom_left
                    eff_right = check_right and dom_right
                    if eff_right:
                        lim_r = sp.limit(expr, self.x, pt, dir="+")
                        if getattr(lim_r, "is_infinite", False) or lim_r.has(sp.zoo):
                            return True
                    if eff_left:
                        lim_l = sp.limit(expr, self.x, pt, dir="-")
                        if getattr(lim_l, "is_infinite", False) or lim_l.has(sp.zoo):
                            return True
                except:
                    pass
                return False

            vas = []

            def process_excluded(s):
                if isinstance(s, sp.FiniteSet):
                    for pt in s:
                        if check_va_at_point(pt):
                            vas.append(pt)
                elif isinstance(s, sp.ImageSet):
                    lam = s.lamda if hasattr(s, "lamda") else s.args[0]
                    var = (
                        lam.variables[0]
                        if hasattr(lam, "variables")
                        else list(lam.free_symbols)[0]
                    )
                    sample_expr = lam.expr if hasattr(lam, "expr") else lam
                    for n_val in [0, 1]:
                        sample_pt = sample_expr.subs(var, n_val)
                        if check_va_at_point(sample_pt):
                            vas.append(s)
                            break
                elif isinstance(s, sp.Union):
                    for arg in s.args:
                        process_excluded(arg)
                elif isinstance(s, sp.Complement):
                    process_excluded(s.args[1])

            process_excluded(excluded)

            def extract_boundary_asymptotes(dom):
                if isinstance(dom, sp.Interval):
                    if dom.start != -sp.oo and dom.start.is_finite:
                        if dom.left_open and check_va_at_point(
                            dom.start, check_left=False
                        ):
                            if dom.start not in vas:
                                vas.append(dom.start)
                    if dom.end != sp.oo and dom.end.is_finite:
                        if dom.right_open and check_va_at_point(
                            dom.end, check_right=False
                        ):
                            if dom.end not in vas:
                                vas.append(dom.end)
                elif isinstance(dom, sp.Union):
                    for arg in dom.args:
                        extract_boundary_asymptotes(arg)
                elif isinstance(dom, sp.Complement):
                    extract_boundary_asymptotes(dom.args[0])

            extract_boundary_asymptotes(domain)

            # Fallback: SymPy singularities detection
            try:
                sings = singularities(expr, self.x)

                def _add_sing_set(s_set):
                    if isinstance(s_set, sp.FiniteSet):
                        for pt in s_set:
                            if pt.is_real and pt not in vas and check_va_at_point(pt):
                                vas.append(pt)
                    elif isinstance(s_set, sp.ImageSet):
                        if s_set not in vas:
                            lam = (
                                s_set.lamda
                                if hasattr(s_set, "lamda")
                                else s_set.args[0]
                            )
                            var = (
                                lam.variables[0]
                                if hasattr(lam, "variables")
                                else list(lam.free_symbols)[0]
                            )
                            sp_expr = lam.expr if hasattr(lam, "expr") else lam
                            if check_va_at_point(sp_expr.subs(var, 0)):
                                vas.append(s_set)
                    elif isinstance(s_set, sp.Union):
                        for arg in s_set.args:
                            _add_sing_set(arg)

                _add_sing_set(sings)
            except Exception:
                pass

            # Deduplicate ImageSets by value-sampling
            def imageset_equivalent(s1, s2):
                if not (isinstance(s1, sp.ImageSet) and isinstance(s2, sp.ImageSet)):
                    return False
                try:
                    lam1 = s1.lamda if hasattr(s1, "lamda") else s1.args[0]
                    lam2 = s2.lamda if hasattr(s2, "lamda") else s2.args[0]
                    e1 = lam1.expr if hasattr(lam1, "expr") else lam1
                    e2 = lam2.expr if hasattr(lam2, "expr") else lam2
                    v1 = (
                        lam1.variables[0]
                        if hasattr(lam1, "variables")
                        else list(lam1.free_symbols)[0]
                    )
                    v2 = (
                        lam2.variables[0]
                        if hasattr(lam2, "variables")
                        else list(lam2.free_symbols)[0]
                    )
                    vals1 = {float(e1.subs(v1, i).evalf()) for i in range(-3, 4)}
                    vals2 = {float(e2.subs(v2, i).evalf()) for i in range(-3, 4)}
                    return any(abs(a - b) < 1e-6 for a in vals1 for b in vals2)
                except:
                    return False

            unique_vas = []
            for v in vas:
                if not any(
                    imageset_equivalent(v, uv)
                    if isinstance(v, sp.ImageSet)
                    else v == uv
                    for uv in unique_vas
                ):
                    unique_vas.append(v)

            for v in unique_vas:
                if v not in asymptotes["vertical"]:
                    asymptotes["vertical"].append(v)
        except Exception as e:
            raise e
        return asymptotes

    def get_parity(self, expr):
        """
        Check parity symbolically (multiple simplification strategies),
        then fall back to numerical sampling — fixes ln(x+sqrt(x^2+1)) = arcsinh(x).
        """
        try:
            f_neg = sp.simplify(expr.subs(self.x, -self.x))
            f_pos = sp.simplify(expr)
            if f_neg == f_pos:
                return "Even"
            if f_neg == -f_pos:
                return "Odd"

            # Try after trig simplification
            fn_t = sp.trigsimp(f_neg)
            fp_t = sp.trigsimp(f_pos)
            if fn_t == fp_t:
                return "Even"
            if fn_t == -fp_t:
                return "Odd"

            # Try expand
            if sp.expand(f_neg - f_pos) == 0:
                return "Even"
            if sp.expand(f_neg + f_pos) == 0:
                return "Odd"

            # Symbolic equality test (slower but correct for rewritten forms)
            if expr.equals(expr.subs(self.x, -self.x)):
                return "Even"
            if expr.equals(-expr.subs(self.x, -self.x)):
                return "Odd"

            # Numerical fallback — multiple irrational test points
            test_pts = [0.3, 0.7, 1.2, 1.7, 2.3, 3.1, 5.7]
            is_even, is_odd, n_valid = True, True, 0
            for pt in test_pts:
                try:
                    pv = complex(expr.subs(self.x, pt).evalf())
                    nv = complex(expr.subs(self.x, -pt).evalf())
                    if abs(pv.imag) > 1e-9 or abs(nv.imag) > 1e-9:
                        is_even = is_odd = False
                        break
                    n_valid += 1
                    if abs(pv.real - nv.real) > 1e-6:
                        is_even = False
                    if abs(pv.real + nv.real) > 1e-6:
                        is_odd = False
                except:
                    pass
            if n_valid >= 4:
                if is_even:
                    return "Even"
                if is_odd:
                    return "Odd"
        except Exception:
            pass
        return "Neither even nor odd"

    def get_periodicity(self, expr):
        """
        Try several simplification strategies before giving up.
        Also find the FUNDAMENTAL period by testing divisors.
        E.g., sin(x)^2 has fundamental period π, not 2π.
        """
        strategies = [
            lambda e: e,
            lambda e: sp.trigsimp(e),
            lambda e: sp.expand_trig(sp.expand(e)),
            lambda e: e.rewrite(sp.cos),
            lambda e: e.rewrite(sp.sin),
        ]
        candidate = None
        for strat in strategies:
            try:
                p = periodicity(strat(expr), self.x)
                if p is not None:
                    candidate = p
                    break
            except Exception:
                pass

        if candidate is None:
            return None

        # Try to find the fundamental period by testing divisors
        # Common divisors to try: p/2, p/3, p/4, p/6
        fundamental = candidate
        for divisor in [2, 3, 4, 6]:
            try:
                test_period = candidate / divisor
                # Check if this is also a period: f(x + test_period) = f(x)
                diff = sp.simplify(expr.subs(self.x, self.x + test_period) - expr)
                if diff == 0:
                    # Verify it's actually a valid period (not zero or negative)
                    if test_period.is_positive:
                        fundamental = test_period
                        # Don't break - keep looking for smaller periods
            except Exception:
                pass

        return fundamental

    def get_monotonicity(self, expr, domain, period=None):
        intervals = {"increasing": [], "decreasing": []}
        try:
            f_prime = sp.diff(expr, self.x)
            if sp.simplify(f_prime) == 0:
                return intervals

            roots = self.safe_solveset(f_prime)
            try:
                domain_f_prime = continuous_domain(f_prime, self.x, sp.Reals)
            except Exception:
                try:
                    sings = singularities(f_prime, self.x)
                    domain_f_prime = sp.Complement(domain, sings)
                except:
                    domain_f_prime = domain

            breaks_set = set()

            # KEY FIX: Detect if we have incomplete root finding (ConditionSet)
            # combined with infinite oscillation. In such cases, we CANNOT
            # claim monotonicity extends to infinity.
            has_incomplete_roots = self._roots_are_incomplete(roots)
            has_oscillation = self._has_infinite_oscillation(expr)
            suppress_infinity = has_incomplete_roots and has_oscillation

            # CRITICAL: For infinitely oscillating functions, return empty intervals
            # immediately. Building intervals from partial nsolve results is meaningless
            # since there are infinitely many critical points we cannot enumerate.
            if suppress_infinity:
                return intervals

            if period is not None:
                try:
                    period_val = float(period.evalf())
                    sample_range = max(2 * period_val, 10)
                    disc_f = sp.Complement(sp.Reals, domain)
                    disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                    self._extract_real_roots_bounded(
                        roots, breaks_set, -sample_range, sample_range
                    )
                    self._extract_real_roots_bounded(
                        disc_f, breaks_set, -sample_range, sample_range
                    )
                    self._extract_real_roots_bounded(
                        disc_fp, breaks_set, -sample_range, sample_range
                    )
                except:
                    disc_f = sp.Complement(sp.Reals, domain)
                    disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                    self._extract_real_roots(roots, breaks_set)
                    self._extract_real_roots(disc_f, breaks_set)
                    self._extract_real_roots(disc_fp, breaks_set)
            else:
                disc_f = sp.Complement(sp.Reals, domain)
                disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                self._extract_real_roots(roots, breaks_set)
                self._extract_real_roots(disc_f, breaks_set)
                self._extract_real_roots(disc_fp, breaks_set)

            sorted_breaks = []
            for bp in breaks_set:
                try:
                    sorted_breaks.append((float(bp.evalf()), bp))
                except:
                    pass
            sorted_breaks.sort()

            unique_breaks = []
            if sorted_breaks:
                unique_breaks.append(sorted_breaks[0])
                for i in range(1, len(sorted_breaks)):
                    if abs(sorted_breaks[i][0] - unique_breaks[-1][0]) > 1e-5:
                        unique_breaks.append(sorted_breaks[i])

            # Build boundary values for interval analysis
            # For periodic functions OR oscillating functions, don't extend to infinity
            # because we can't claim monotonicity extends unboundedly
            oscillates_at_inf = self._oscillates_at_infinity(expr)

            # BUG 1 FIX: If derivative never changes sign, function is globally monotone
            # → bypass the oscillation guard entirely (e.g., x - sin(x) has f'(x) = 1 - cos(x) >= 0)
            if oscillates_at_inf:
                test_pts = [i * 0.7 for i in range(-15, 16) if i != 0]
                fp_vals = [
                    self._safe_eval(f_prime, t)
                    for t in test_pts
                    if self._in_domain(t, domain)
                ]
                fp_vals = [v for v in fp_vals if v is not None]
                if fp_vals and all(v >= -1e-9 for v in fp_vals):
                    oscillates_at_inf = (
                        False  # always non-negative → globally increasing
                    )
                elif fp_vals and all(v <= 1e-9 for v in fp_vals):
                    oscillates_at_inf = (
                        False  # always non-positive → globally decreasing
                    )

            if (period is not None and unique_breaks) or oscillates_at_inf:
                b_vals = [b[1] for b in unique_breaks]
                if not b_vals:
                    # No critical points found - for oscillating functions, return empty
                    if oscillates_at_inf:
                        return intervals
            else:
                b_vals = [-sp.oo] + [b[1] for b in unique_breaks] + [sp.oo]

            for i in range(len(b_vals) - 1):
                start, end = b_vals[i], b_vals[i + 1]

                if start == -sp.oo and end == sp.oo:
                    test_pt = 0
                elif start == -sp.oo:
                    test_pt = float(end.evalf()) - 1
                elif end == sp.oo:
                    test_pt = float(start.evalf()) + 1
                else:
                    test_pt = (float(start.evalf()) + float(end.evalf())) / 2

                try:
                    if self._in_domain(test_pt, domain):
                        # FIX: use _safe_eval to handle complex-valued f' (e.g. cube roots)
                        val = self._safe_eval(f_prime, test_pt)
                        if val is None:
                            continue

                        if abs(val) < 1e-7:
                            subbed = sp.simplify(f_prime.subs(self.x, test_pt))
                            if subbed == 0:
                                val = 0
                            elif subbed > 0:
                                val = 1
                            elif subbed < 0:
                                val = -1

                        if val > 1e-12:
                            intervals["increasing"].append((start, end))
                        elif val < -1e-12:
                            intervals["decreasing"].append((start, end))
                except:
                    pass

            # FIX: Consolidate adjacent intervals that share a boundary point in the domain
            intervals = self._consolidate_monotonicity(intervals, domain)

        except Exception as e:
            raise e
        return intervals

    def _consolidate_monotonicity(self, intervals, domain):
        """
        Consolidate adjacent monotonicity intervals that share a boundary point
        which exists in the domain.
        """

        def merge_intervals(ivs):
            if not ivs:
                return []

            # Sort intervals by starting point to be safe
            sorted_ivs = []
            for i in ivs:
                try:
                    start_val = float("-inf") if i[0] == -sp.oo else float(i[0].evalf())
                    sorted_ivs.append((start_val, i))
                except:
                    sorted_ivs.append((0, i))
            sorted_ivs.sort(key=lambda x: x[0])

            merged = [sorted_ivs[0][1]]
            for _, current in sorted_ivs[1:]:
                prev = merged[-1]
                # If they share a boundary (within tolerance) AND that bound is in the domain
                try:
                    p_end = float(prev[1].evalf()) if prev[1] != sp.oo else float("inf")
                    c_start = (
                        float(current[0].evalf())
                        if current[0] != -sp.oo
                        else float("-inf")
                    )

                    if abs(p_end - c_start) < 1e-5:
                        bound_pt = float(prev[1].evalf())
                        if self._in_domain(bound_pt, domain):
                            # Merge them
                            merged[-1] = (prev[0], current[1])
                            continue
                except:
                    # symbolic match fallback
                    if prev[1] == current[0] and self._in_domain(prev[1], domain):
                        merged[-1] = (prev[0], current[1])
                        continue

                merged.append(current)
            return merged

        intervals["increasing"] = merge_intervals(intervals["increasing"])
        intervals["decreasing"] = merge_intervals(intervals["decreasing"])
        return intervals

    # ─────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────

    def analyze(self, func_string):
        """
        Analyze a mathematical function with timeout protection.
        Returns analysis dict or None if parsing/timeout fails.
        """

        real_x = sp.Symbol("x", real=True)
        self.x = real_x

        # We only need to provide engine-specific variable symbols now!
        # get_sympified_expr in algo.py automatically handles e, ln, arctan, etc.
        local_dict = {"x": real_x}

        try:
            # get_sympified_expr handles implicit mult, '^' via convert_xor, float rationalization
            expr = get_sympified_expr(func_string, local_dict=local_dict)
            
            # Validate expression
            if expr is None or expr in [sp.zoo, sp.oo, -sp.oo, sp.nan]:
                if self.debug:
                    print(f"Invalid expression: {func_string}")
                return None
                
        except Exception as e:
            if self.debug:
                print(f"Failed to parse expression '{func_string}': {e}")
            return None

        # ── KEY: domain from original; simplified expr for everything else ──
        # This fixes the 12-second performance bug for cancellable rationals
        # while keeping correct domain holes.
        original_expr = expr
        
        try:
            domain = self.get_domain(original_expr)
        except Exception as e:
            if self.debug:
                print(f"Domain computation failed: {e}")
            domain = sp.Reals
            
        try:
            expr = self._preprocess_expr(original_expr)  # e.g. (x³-x)/(x²-1) → x
        except Exception as e:
            if self.debug:
                print(f"Preprocessing failed: {e}")
            expr = original_expr

        # Use timeout wrappers for expensive operations
        # Set generous timeouts to handle complex expressions, but prevent infinite hangs
        timeout = 5.0  # 5 seconds per operation
        
        def safe_call(func, *args, default=None, name="operation"):
            """Wrapper to call function with timeout and error handling."""
            result, timed_out = run_with_timeout(func, args=args, timeout_seconds=timeout, default=default)
            if timed_out and self.debug:
                print(f"{name} timed out after {timeout}s")
            return result

        intercepts = safe_call(self.get_intercepts, expr, domain, 
                              default={"x": [], "y": None}, name="Intercepts")
        extrema = safe_call(self.get_extrema, expr, domain,
                           default={"minima": [], "maxima": []}, name="Extrema")
        inflections = safe_call(self.get_inflection_points, expr, domain,
                               default=[], name="Inflection Points")
        asymptotes = safe_call(self.get_asymptotes, expr, domain,
                              default={"vertical": [], "horizontal": [], "oblique": []},
                              name="Asymptotes")
        parity = safe_call(self.get_parity, expr,
                          default="Neither even nor odd", name="Parity")
        period = safe_call(self.get_periodicity, expr,
                          default=None, name="Periodicity")
        monotonicity = safe_call(self.get_monotonicity, expr, domain, period,
                                default={"increasing": [], "decreasing": []},
                                name="Monotonicity")

        results = {
            "Function": str(original_expr),
            "Domain": domain,
            "Intercepts": intercepts,
            "Extrema": extrema,
            "Inflection Points": inflections,
            "Asymptotes": asymptotes,
            "Parity": parity,
            "Periodicity": period,
            "Monotonicity": monotonicity,
        }

        from engines.domain_range.domain_range_engine import format_math_set, round_sympy_expr

        formatted_intercepts = {
            "x": format_math_set(round_sympy_expr(intercepts.get("x", []))),
            "y": format_math_set(round_sympy_expr(intercepts.get("y")))
        }

        formatted_extrema = {
            "minima": format_math_set(round_sympy_expr(extrema.get("minima", []))),
            "maxima": format_math_set(round_sympy_expr(extrema.get("maxima", [])))
        }

        formatted_inflections = format_math_set(round_sympy_expr(inflections))

        formatted_asymptotes = {
            "vertical": format_math_set(round_sympy_expr(asymptotes.get("vertical", []))),
            "horizontal": format_math_set(round_sympy_expr(asymptotes.get("horizontal", []))),
            "oblique": format_math_set(round_sympy_expr(asymptotes.get("oblique", [])))
        }

        formatted_monotonicity = {
            "increasing": format_math_set(round_sympy_expr(monotonicity.get("increasing", []))),
            "decreasing": format_math_set(round_sympy_expr(monotonicity.get("decreasing", [])))
        }

        formatted_results = {
            "Function": str(original_expr),
            "Domain": format_math_set(round_sympy_expr(domain)),
            "Intercepts": formatted_intercepts,
            "Extrema": formatted_extrema,
            "Inflection Points": formatted_inflections,
            "Asymptotes": formatted_asymptotes,
            "Parity": parity,
            "Periodicity": format_math_set(round_sympy_expr(period)) if period is not None else "None",
            "Monotonicity": formatted_monotonicity,
        }
        return formatted_results

    
