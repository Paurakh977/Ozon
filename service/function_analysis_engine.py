import sympy as sp
import time
from sympy.calculus.util import continuous_domain, periodicity, AccumBounds
from sympy.calculus.singularities import singularities

try:
    from algo import get_sympified_expr
except ImportError:
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations, implicit_multiplication_application
    )
    def get_sympified_expr(user_input):
        transformations = (standard_transformations + (implicit_multiplication_application,))
        return parse_expr(user_input, transformations=transformations)


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
    - print_report() filters AccumBounds at display level as final safety net
    """

    def __init__(self, debug=False):
        self.debug = debug
        self.x = sp.Symbol('x', real=True)

    def _log(self, msg):
        if self.debug:
            print(f"[Engine] {msg}")

    # ─────────────────────────────────────────────────────────────
    # Pre-processing
    # ─────────────────────────────────────────────────────────────

    def _preprocess_expr(self, expr):
        """
        Cancel rational expressions to avoid redundant symbolic work.
        E.g. (x^3-x)/(x^2-1) → x   (holes handled via separately-stored domain)
        Also tries powsimp for expressions like x^(2/3) * x^(1/3) etc.
        """
        try:
            cancelled = sp.cancel(expr)
            if cancelled != expr:
                self._log(f"Cancelled: {expr} → {cancelled}")
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
                    lo = float(domain.start) if domain.start != -sp.oo else -float('inf')
                    hi = float(domain.end) if domain.end != sp.oo else float('inf')
                    if domain.left_open:
                        if point_val <= lo: return False
                    else:
                        if point_val < lo: return False
                    if domain.right_open:
                        if point_val >= hi: return False
                    else:
                        if point_val > hi: return False
                    return True
                elif domain == sp.Reals:
                    return True
            result = domain.contains(point)
            if result is True or result == sp.true: return True
            if result is False or result == sp.false: return False
            simplified = sp.simplify(result)
            if simplified is True or simplified == sp.true: return True
            if simplified is False or simplified == sp.false: return False
            return domain == sp.Reals
        except Exception:
            return False

    def _point_in_set(self, point_val, s):
        try:
            if isinstance(s, sp.FiniteSet):
                return any(abs(float(pt.evalf()) - point_val) < 1e-9 for pt in s)
            elif isinstance(s, sp.ImageSet):
                lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                sample_expr = lam.expr if hasattr(lam, 'expr') else lam
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
                lo = float(s.start) if s.start != -sp.oo else -float('inf')
                hi = float(s.end) if s.end != sp.oo else float('inf')
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
                    if getattr(p, 'is_real', True):
                        test_pts_set.add(p)
            elif isinstance(s, sp.ImageSet):
                lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                for i in range(-5, 6):
                    try:
                        val = lam.expr.subs(var, i) if hasattr(lam, 'expr') else lam.subs(var, i)
                        if getattr(val, 'is_real', True):
                            test_pts_set.add(val)
                    except:
                        pass
            elif isinstance(s, sp.Interval):
                if s.start != -sp.oo: test_pts_set.add(s.start)
                if s.end != sp.oo:   test_pts_set.add(s.end)
            elif isinstance(s, (sp.Union, sp.Intersection, sp.Complement)):
                for arg in s.args: extract(arg)
            elif isinstance(s, sp.ConditionSet):
                expr_cond = (s.condition.lhs - s.condition.rhs
                             if isinstance(s.condition, sp.Eq) else s.condition)
                found_approx = set()
                for guess in [i / 2.0 for i in range(-20, 21)]:
                    try:
                        root = sp.nsolve(expr_cond, self.x, guess)
                        if getattr(root, 'is_real', True):
                            val = float(root)
                            if abs(val) < 1e-3: val = 0.0
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
                        if getattr(p, 'is_real', True) and lower <= p_val <= upper:
                            test_pts_set.add(p)
                    except:
                        pass
            elif isinstance(s, sp.ImageSet):
                lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                for i in range(-20, 21):
                    try:
                        val = lam.expr.subs(var, i) if hasattr(lam, 'expr') else lam.subs(var, i)
                        v = float(val.evalf())
                        if getattr(val, 'is_real', True) and lower <= v <= upper:
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
                for arg in s.args: extract(arg)
            elif isinstance(s, sp.ConditionSet):
                expr_cond = (s.condition.lhs - s.condition.rhs
                             if isinstance(s.condition, sp.Eq) else s.condition)
                found_approx = set()
                for guess in [i / 2.0 for i in range(-20, 21)]:
                    if lower <= guess <= upper:
                        try:
                            root = sp.nsolve(expr_cond, self.x, guess)
                            if getattr(root, 'is_real', True):
                                val = float(root)
                                if lower <= val <= upper:
                                    if abs(val) < 1e-3: val = 0.0
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
            self._log(f"Error solving {expr}: {e}")
            return sp.EmptySet

    def get_domain(self, expr):
        self._log("Calculating Domain...")
        try:
            return continuous_domain(expr, self.x, sp.Reals)
        except Exception as e:
            self._log(f"Domain calculation failed: {e}")
            return sp.Reals

    def get_intercepts(self, expr, domain):
        self._log("Calculating Intercepts...")
        intercepts = {'x': [], 'y': None}

        # Y-intercept: only if 0 is genuinely in the domain
        try:
            if self._in_domain(0, domain):
                y_val = expr.subs(self.x, 0)
                if y_val.is_real and not y_val.has(sp.nan, sp.zoo, sp.I):
                    intercepts['y'] = sp.simplify(y_val)
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
                intercepts['x'] = valid
            elif not isinstance(x_sols, sp.EmptySet.__class__):
                clean_sols = sp.Intersection(x_sols, domain)
                intercepts['x'] = clean_sols
        except Exception:
            pass
        return intercepts

    def get_extrema(self, expr, domain):
        self._log("Calculating Extrema...")
        extrema = {'minima': [], 'maxima': []}
        try:
            f_prime = sp.diff(expr, self.x)
            roots = self.safe_solveset(f_prime)
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
                    if s.start != -sp.oo: cands.add(s.start)
                    if s.end != sp.oo:   cands.add(s.end)
                elif isinstance(s, sp.Union):
                    for arg in s.args: extract_boundaries(arg)
            extract_boundaries(domain)

            unique_pts = []
            for p in cands:
                try:
                    if self._in_domain(p, domain):
                        p_val = float(p.evalf())
                        if not any(abs(p_val - float(up.evalf())) < 1e-5 for up in unique_pts):
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
                    left_val  = self._safe_eval(f_prime, cp_val - eps) if left_in  else None
                    right_val = self._safe_eval(f_prime, cp_val + eps) if right_in else None
                    y_val = sp.simplify(expr.subs(self.x, cp))

                    if left_val is not None and right_val is not None:
                        if left_val < -1e-7 and right_val > 1e-7:
                            extrema['minima'].append((sp.simplify(cp), y_val))
                        elif left_val > 1e-7 and right_val < -1e-7:
                            extrema['maxima'].append((sp.simplify(cp), y_val))
                    elif left_val is None and right_val is not None:   # Left endpoint
                        if right_val > 1e-7:
                            extrema['minima'].append((sp.simplify(cp), y_val))
                        elif right_val < -1e-7:
                            extrema['maxima'].append((sp.simplify(cp), y_val))
                    elif left_val is not None and right_val is None:   # Right endpoint
                        if left_val > 1e-7:
                            extrema['maxima'].append((sp.simplify(cp), y_val))
                        elif left_val < -1e-7:
                            extrema['minima'].append((sp.simplify(cp), y_val))
                except:
                    pass
        except Exception as e:
            self._log(f"Extrema calculation failed: {e}")
        return extrema

    def get_inflection_points(self, expr, domain):
        self._log("Calculating Inflection Points...")
        inflections = []
        try:
            f_prime = sp.diff(expr, self.x)
            f_dp    = sp.diff(f_prime, self.x)
            roots   = self.safe_solveset(f_dp)

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
                        if not any(abs(p_val - float(up.evalf())) < 1e-5 for up in unique_pts):
                            unique_pts.append(p)
                except:
                    pass
            unique_pts.sort(key=lambda p: float(p.evalf()))

            for cp in unique_pts:
                cp_val = float(cp.evalf())
                eps = 1e-5
                try:
                    if not (self._in_domain(cp_val - eps, domain) and
                            self._in_domain(cp_val + eps, domain)):
                        continue   # Endpoints cannot be inflection points

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
            self._log(f"Inflection points failed: {e}")
        return inflections

    def get_asymptotes(self, expr, domain):
        self._log("Calculating Asymptotes...")
        asymptotes = {'vertical': [], 'horizontal': [], 'oblique': []}

        # ── Horizontal asymptotes ──────────────────────────────────
        # FIX: only check directions the domain actually extends to
        for d in [sp.oo, -sp.oo]:
            if not self._domain_extends_to(domain, d):
                continue
            try:
                L = sp.limit(expr, self.x, d)
                if isinstance(L, AccumBounds):
                    continue   # Oscillating — no HA in this direction
                if L.is_real and not L.is_infinite and not L.has(sp.zoo, sp.nan):
                    val = sp.simplify(L)
                    if val not in asymptotes['horizontal']:
                        asymptotes['horizontal'].append(val)
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
                if m.is_real and not m.is_infinite and m != 0 and not m.has(sp.zoo, sp.nan):
                    c = sp.limit(expr - m * self.x, self.x, d)
                    if isinstance(c, AccumBounds):
                        continue   # FIX: oscillation ⇒ no oblique asymptote
                    if c.is_real and not c.is_infinite and not c.has(sp.zoo, sp.nan):
                        line = sp.simplify(m * self.x + c)
                        if line not in asymptotes['oblique']:
                            asymptotes['oblique'].append(line)
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
                    dom_left  = self._in_domain(pt_f - eps, domain)
                    dom_right = self._in_domain(pt_f + eps, domain)
                    # If NEITHER side is in the domain, this point is irrelevant
                    if not dom_left and not dom_right:
                        return False
                    eff_left  = check_left  and dom_left
                    eff_right = check_right and dom_right
                    if eff_right:
                        lim_r = sp.limit(expr, self.x, pt, dir='+')
                        if getattr(lim_r, 'is_infinite', False) or lim_r.has(sp.zoo):
                            return True
                    if eff_left:
                        lim_l = sp.limit(expr, self.x, pt, dir='-')
                        if getattr(lim_l, 'is_infinite', False) or lim_l.has(sp.zoo):
                            return True
                except:
                    pass
                return False

            vas = []

            def process_excluded(s):
                if isinstance(s, sp.FiniteSet):
                    for pt in s:
                        if check_va_at_point(pt): vas.append(pt)
                elif isinstance(s, sp.ImageSet):
                    lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                    var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                    sample_expr = lam.expr if hasattr(lam, 'expr') else lam
                    for n_val in [0, 1]:
                        sample_pt = sample_expr.subs(var, n_val)
                        if check_va_at_point(sample_pt):
                            vas.append(s)
                            break
                elif isinstance(s, sp.Union):
                    for arg in s.args: process_excluded(arg)
                elif isinstance(s, sp.Complement):
                    process_excluded(s.args[1])

            process_excluded(excluded)

            def extract_boundary_asymptotes(dom):
                if isinstance(dom, sp.Interval):
                    if dom.start != -sp.oo and dom.start.is_finite:
                        if dom.left_open and check_va_at_point(dom.start, check_left=False):
                            if dom.start not in vas:
                                vas.append(dom.start)
                    if dom.end != sp.oo and dom.end.is_finite:
                        if dom.right_open and check_va_at_point(dom.end, check_right=False):
                            if dom.end not in vas:
                                vas.append(dom.end)
                elif isinstance(dom, sp.Union):
                    for arg in dom.args: extract_boundary_asymptotes(arg)
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
                            lam = s_set.lamda if hasattr(s_set, 'lamda') else s_set.args[0]
                            var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                            sp_expr = lam.expr if hasattr(lam, 'expr') else lam
                            if check_va_at_point(sp_expr.subs(var, 0)):
                                vas.append(s_set)
                    elif isinstance(s_set, sp.Union):
                        for arg in s_set.args: _add_sing_set(arg)
                _add_sing_set(sings)
            except Exception:
                pass

            # Deduplicate ImageSets by value-sampling
            def imageset_equivalent(s1, s2):
                if not (isinstance(s1, sp.ImageSet) and isinstance(s2, sp.ImageSet)):
                    return False
                try:
                    lam1 = s1.lamda if hasattr(s1, 'lamda') else s1.args[0]
                    lam2 = s2.lamda if hasattr(s2, 'lamda') else s2.args[0]
                    e1   = lam1.expr if hasattr(lam1, 'expr') else lam1
                    e2   = lam2.expr if hasattr(lam2, 'expr') else lam2
                    v1   = lam1.variables[0] if hasattr(lam1, 'variables') else list(lam1.free_symbols)[0]
                    v2   = lam2.variables[0] if hasattr(lam2, 'variables') else list(lam2.free_symbols)[0]
                    vals1 = {float(e1.subs(v1, i).evalf()) for i in range(-3, 4)}
                    vals2 = {float(e2.subs(v2, i).evalf()) for i in range(-3, 4)}
                    return any(abs(a - b) < 1e-6 for a in vals1 for b in vals2)
                except:
                    return False

            unique_vas = []
            for v in vas:
                if not any(
                    imageset_equivalent(v, uv) if isinstance(v, sp.ImageSet) else v == uv
                    for uv in unique_vas
                ):
                    unique_vas.append(v)

            for v in unique_vas:
                if v not in asymptotes['vertical']:
                    asymptotes['vertical'].append(v)
        except Exception as e:
            self._log(f"Vertical asymptote failed: {e}")

        return asymptotes

    def get_parity(self, expr):
        """
        Check parity symbolically (multiple simplification strategies),
        then fall back to numerical sampling — fixes ln(x+sqrt(x^2+1)) = arcsinh(x).
        """
        self._log("Calculating Parity...")
        try:
            f_neg = sp.simplify(expr.subs(self.x, -self.x))
            f_pos = sp.simplify(expr)
            if f_neg == f_pos:  return "Even"
            if f_neg == -f_pos: return "Odd"

            # Try after trig simplification
            fn_t = sp.trigsimp(f_neg)
            fp_t = sp.trigsimp(f_pos)
            if fn_t == fp_t:  return "Even"
            if fn_t == -fp_t: return "Odd"

            # Try expand
            if sp.expand(f_neg - f_pos) == 0: return "Even"
            if sp.expand(f_neg + f_pos) == 0: return "Odd"

            # Symbolic equality test (slower but correct for rewritten forms)
            if expr.equals(expr.subs(self.x, -self.x)):  return "Even"
            if expr.equals(-expr.subs(self.x, -self.x)): return "Odd"

            # Numerical fallback — multiple irrational test points
            test_pts = [0.3, 0.7, 1.2, 1.7, 2.3, 3.1, 5.7]
            is_even, is_odd, n_valid = True, True, 0
            for pt in test_pts:
                try:
                    pv = complex(expr.subs(self.x,  pt).evalf())
                    nv = complex(expr.subs(self.x, -pt).evalf())
                    if abs(pv.imag) > 1e-9 or abs(nv.imag) > 1e-9:
                        is_even = is_odd = False
                        break
                    n_valid += 1
                    if abs(pv.real - nv.real) > 1e-6: is_even = False
                    if abs(pv.real + nv.real) > 1e-6: is_odd  = False
                except:
                    pass
            if n_valid >= 4:
                if is_even: return "Even"
                if is_odd:  return "Odd"
        except Exception:
            pass
        return "Neither even nor odd"

    def get_periodicity(self, expr):
        """
        Try several simplification strategies before giving up.
        Fixes sin(x)^2 which requires trigsimp or expand_trig to expose period π.
        """
        strategies = [
            lambda e: e,
            lambda e: sp.trigsimp(e),
            lambda e: sp.expand_trig(sp.expand(e)),
            lambda e: e.rewrite(sp.cos),
            lambda e: e.rewrite(sp.sin),
        ]
        for strat in strategies:
            try:
                p = periodicity(strat(expr), self.x)
                if p is not None:
                    return p
            except Exception:
                pass
        return None

    def get_monotonicity(self, expr, domain, period=None):
        self._log("Calculating Monotonicity...")
        intervals = {'increasing': [], 'decreasing': []}
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

            if period is not None:
                try:
                    period_val   = float(period.evalf())
                    sample_range = max(2 * period_val, 10)
                    disc_f  = sp.Complement(sp.Reals, domain)
                    disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                    self._extract_real_roots_bounded(roots,   breaks_set, -sample_range, sample_range)
                    self._extract_real_roots_bounded(disc_f,  breaks_set, -sample_range, sample_range)
                    self._extract_real_roots_bounded(disc_fp, breaks_set, -sample_range, sample_range)
                except:
                    disc_f  = sp.Complement(sp.Reals, domain)
                    disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                    self._extract_real_roots(roots,   breaks_set)
                    self._extract_real_roots(disc_f,  breaks_set)
                    self._extract_real_roots(disc_fp, breaks_set)
            else:
                disc_f  = sp.Complement(sp.Reals, domain)
                disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                self._extract_real_roots(roots,   breaks_set)
                self._extract_real_roots(disc_f,  breaks_set)
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

            if period is not None and unique_breaks:
                b_vals = [b[1] for b in unique_breaks]
            else:
                b_vals = [-sp.oo] + [b[1] for b in unique_breaks] + [sp.oo]

            for i in range(len(b_vals) - 1):
                start, end = b_vals[i], b_vals[i + 1]

                if   start == -sp.oo and end == sp.oo: test_pt = 0
                elif start == -sp.oo:                  test_pt = float(end.evalf()) - 1
                elif end   == sp.oo:                   test_pt = float(start.evalf()) + 1
                else:
                    test_pt = (float(start.evalf()) + float(end.evalf())) / 2

                try:
                    if self._in_domain(test_pt, domain):
                        # FIX: use _safe_eval to handle complex-valued f' (e.g. cube roots)
                        val = self._safe_eval(f_prime, test_pt)
                        if val is None:
                            continue
                        if val > 1e-7:
                            intervals['increasing'].append((start, end))
                        elif val < -1e-7:
                            intervals['decreasing'].append((start, end))
                except:
                    pass
        except Exception as e:
            self._log(f"Monotonicity calculation failed: {e}")
        return intervals

    # ─────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────

    def analyze(self, func_string):
        print(f"\n{'='*50}")
        print(f"[{func_string}] Analysis Starting...")
        print(f"{'='*50}")

        start_time = time.time()

        # Normalise input string
        func_string = func_string.replace('^', '**')
        func_string = func_string.replace('e**', 'E**').replace('e^', 'E**')
        for old, new in [('arctan','atan'), ('arcsin','asin'), ('arccos','acos'),
                         ('arccot','acot'), ('arcsec','asec'), ('arccsc','acsc')]:
            func_string = func_string.replace(old, new)

        expr = get_sympified_expr(func_string)
        real_x = sp.Symbol('x', real=True)
        expr = expr.subs({s: real_x for s in expr.free_symbols if s.name == 'x'})
        self.x = real_x

        # ── KEY: domain from original; simplified expr for everything else ──
        # This fixes the 12-second performance bug for cancellable rationals
        # while keeping correct domain holes.
        original_expr = expr
        domain = self.get_domain(original_expr)
        expr   = self._preprocess_expr(original_expr)   # e.g. (x³-x)/(x²-1) → x

        intercepts   = self.get_intercepts(expr, domain)
        extrema      = self.get_extrema(expr, domain)
        inflections  = self.get_inflection_points(expr, domain)
        asymptotes   = self.get_asymptotes(expr, domain)
        parity       = self.get_parity(expr)
        period       = self.get_periodicity(expr)
        monotonicity = self.get_monotonicity(expr, domain, period)

        elapsed = time.time() - start_time
        results = {
            'Function':        original_expr,   # always display original
            'Domain':          domain,
            'Intercepts':      intercepts,
            'Extrema':         extrema,
            'Inflection Points': inflections,
            'Asymptotes':      asymptotes,
            'Parity':          parity,
            'Periodicity':     period,
            'Monotonicity':    monotonicity,
            'Time (s)':        round(elapsed, 4),
        }
        self.print_report(results)
        return results

    # ─────────────────────────────────────────────────────────────
    # Report formatting
    # ─────────────────────────────────────────────────────────────

    def print_report(self, res):

        def format_val(val):
            try:
                if isinstance(val, AccumBounds): return None   # Never leak AccumBounds
                if val.has(sp.I): return None
                val = sp.simplify(val)
                if val.count_ops() > 15:
                    return f"{val} (approx {val.evalf():.3f})"
                if isinstance(val, sp.Float):
                    return f"{float(val):.4f}"
                return str(val)
            except:
                return str(val)

        def clean_set(s):
            if isinstance(s, AccumBounds): return None        # Safety net
            if s == sp.Reals:    return "(-oo, oo)"
            if s == sp.EmptySet: return "None"
            if isinstance(s, list):
                if not s: return "None"
                parts = [clean_set(x) if isinstance(x, sp.Set) else format_val(x) for x in s]
                return ", ".join(p for p in parts if p)
            if isinstance(s, sp.FiniteSet):
                if not s: return "None"
                return ", ".join(format_val(arg) for arg in s)
            elif isinstance(s, sp.ImageSet):
                try:
                    lam  = s.lamda if hasattr(s, 'lamda') else s.args[0]
                    expr = lam.expr if hasattr(lam, 'expr') else lam
                    return f"{str(expr).replace('_n', 'n')} (for integer n)"
                except:
                    return str(s).replace('_n', 'n')
            elif isinstance(s, sp.Union):
                parts = [clean_set(arg) for arg in s.args]
                return " U ".join(p for p in parts if p)
            elif isinstance(s, sp.Intersection):
                return " & ".join(clean_set(arg) for arg in s.args)
            elif isinstance(s, sp.Complement):
                return f"{clean_set(s.args[0])} excluding {clean_set(s.args[1])}"
            elif isinstance(s, sp.Interval):
                lb = "(" if s.left_open  else "["
                rb = ")" if s.right_open else "]"
                return f"{lb}{s.start}, {s.end}{rb}"
            return str(s).replace('_n', 'n')

        print(f"Function:       f(x) = {res['Function']}")
        print(f"Domain:         {clean_set(res['Domain'])}")

        x_raw = res['Intercepts']['x']
        if (x_raw is None
                or isinstance(x_raw, sp.EmptySet.__class__)
                or (isinstance(x_raw, list) and not x_raw)):
            print("X-Intercepts:   None")
        else:
            print(f"X-Intercepts:   {clean_set(x_raw)}")

        y_raw = res['Intercepts']['y']
        print(f"Y-Intercept:    {format_val(y_raw) if y_raw is not None else 'None'}")

        period = res['Periodicity']

        def format_extrema(pts, period):
            if not pts: return "None"

            def fmt_pt(pt):
                x_s = format_val(pt[0])
                y_s = format_val(pt[1])
                return f"({x_s}, {y_s})"

            if period is None:
                by_abs = sorted(pts, key=lambda p: abs(float(p[0].evalf()))
                                if getattr(p[0], 'evalf', None) else float('inf'))
                if len(by_abs) > 6:
                    shown = sorted(by_abs[:6], key=lambda p: float(p[0].evalf()))
                    return ", ".join(fmt_pt(p) for p in shown) + " ... (and infinitely many more)"
                return ", ".join(fmt_pt(p) for p in
                                 sorted(by_abs, key=lambda p: float(p[0].evalf())))

            # Periodic: deduplicate by modular equivalence
            base_pts, seen_mod = [], []
            for x_v, y_v in sorted(pts, key=lambda p: abs(float(p[0].evalf()))):
                try:
                    xf, pf = float(x_v.evalf()), float(period.evalf())
                    mod    = xf % pf
                    if not any(abs(mod - sm) < 1e-3 or abs(mod - sm - pf) < 1e-3
                               or abs(mod - sm + pf) < 1e-3 for sm in seen_mod):
                        seen_mod.append(mod)
                        base_pts.append((x_v, y_v))
                except:
                    base_pts.append((x_v, y_v))
            base_pts.sort(key=lambda p: float(p[0].evalf()))
            return ", ".join(
                f"({format_val(x_v)} + n*{period}, {format_val(y_v)})"
                for x_v, y_v in base_pts
            ) + " (for integer n)"

        print(f"Minima:         {format_extrema(res['Extrema']['minima'], period)}")
        print(f"Maxima:         {format_extrema(res['Extrema']['maxima'], period)}")
        print(f"Inflection pts: {format_extrema(res['Inflection Points'], period)}")

        vert = ", ".join(f"x = {clean_set(v)}" for v in res['Asymptotes']['vertical'])

        # FIX: filter AccumBounds at display level (final safety net)
        horz_list = [h for h in res['Asymptotes']['horizontal']
                     if not isinstance(h, AccumBounds)]
        oblq_list = [o for o in res['Asymptotes']['oblique']
                     if not isinstance(o, AccumBounds)]

        horz = ", ".join(f"y = {clean_set(h)}" for h in horz_list)
        oblq = ", ".join(f"y = {clean_set(o)}" for o in oblq_list)
        print(f"Vertical Asym:  {vert or 'None'}")
        print(f"Horizontal Asym:{horz or 'None'}")
        print(f"Oblique Asym:   {oblq or 'None'}")
        print(f"Parity:         {res['Parity']}")
        print(f"Periodicity:    {format_val(period) if period else 'None'}")

        print("Monotonicity:")
        if not res['Monotonicity']['increasing'] and not res['Monotonicity']['decreasing']:
            print("  None or could not be determined.")
        else:
            def print_intervals(ivals, period, label):
                if not ivals: return
                if period is None:
                    by_abs = sorted(ivals,
                        key=lambda i: abs(float(i[0].evalf()))
                        if getattr(i[0], 'evalf', None) and i[0] not in (-sp.oo, sp.oo)
                        else float('inf'))
                    if len(ivals) > 6:
                        shown = sorted(by_abs[:6],
                            key=lambda i: float(i[0].evalf())
                            if i[0] not in (-sp.oo, sp.oo) else -float('inf'))
                        for s, e in shown:
                            print(f"  ({format_val(s)}, {format_val(e)})\t{label}")
                        print(f"  ... (and infinitely many more {label.lower()} intervals)")
                    else:
                        for s, e in sorted(ivals,
                            key=lambda i: float(i[0].evalf())
                            if i[0] not in (-sp.oo, sp.oo) else -float('inf')):
                            print(f"  ({format_val(s)}, {format_val(e)})\t{label}")
                    return

                base_ints, seen_mod = [], []
                for s, e in sorted(ivals,
                        key=lambda i: 0 if i[0] == -sp.oo else abs(float(i[0].evalf()))):
                    try:
                        if s == -sp.oo or e == sp.oo:
                            base_ints.append((s, e)); continue
                        sf, pf = float(s.evalf()), float(period.evalf())
                        mod = sf % pf
                        if not any(abs(mod - sm) < 1e-3 or abs(mod - sm - pf) < 1e-3
                                   or abs(mod - sm + pf) < 1e-3 for sm in seen_mod):
                            seen_mod.append(mod)
                            base_ints.append((s, e))
                    except:
                        base_ints.append((s, e))

                base_ints.sort(key=lambda i: float(i[0].evalf())
                               if i[0] not in (-sp.oo, sp.oo) else -float('inf'))
                for s, e in base_ints:
                    ss = f"{format_val(s)} + n*{period}" if s not in (-sp.oo, sp.oo) else "-oo"
                    es = f"{format_val(e)} + n*{period}" if e not in (-sp.oo, sp.oo) else "oo"
                    print(f"  ({ss}, {es})\t{label} (for integer n)")

            print_intervals(res['Monotonicity']['increasing'], period, "Increasing")
            print_intervals(res['Monotonicity']['decreasing'], period, "Decreasing")

        print(f"\n[Analyzed in {res['Time (s)']} seconds]")
        print("-" * 50)


# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = FunctionAnalysisEngine(debug=False)

    test_functions = [
        # Originals
        "x^(1/x)",
        "x^3 - 6*x^2 + 9*x + 15",
        "1 / x",
        "sin(x)",
        "x^2 / (x^2 - 4)",
        "e^(-x^2)",
        "ln(x)",
        "(x^2 + 1) / x",
        "x^3 - 3*x",
        "tan(x)",
        "x * e^x",
        "sin(x) / x",
        "sqrt(x - 1)",
        "(x^2 - 1) / (x^2 + 1)",
        "abs(x)",
        "x * ln(x)",
        # Extended stress tests
        "1 / (x^2 + 1)",
        "(x^3 - x) / (x^2 - 1)",       # was 12 s — now < 1 s after cancel()
        "(x^2 - 4) / (x - 2)",
        "x / (x^2 - x - 6)",
        "(x^3 + 1) / (x^2 - 1)",
        "cos(x)",
        "sin(x)^2",                     # period should be pi
        "tan(x)^2",
        "arctan(x)",
        "x - sin(x)",
        "sin(x) + cos(x)",
        "1 / sin(x)",
        "e^x / (1 + e^x)",
        "ln(x^2)",
        "x^2 * e^(-x)",
        "ln(x + sqrt(x^2 + 1))",        # arcsinh — parity should be Odd
        "e^(1/x)",
        "x^4 - 2*x^2 + 1",
        "x^5 - x^3 + x",
        "x^2 + x + 1",
        "sqrt(4 - x^2)",
        "ln(1 - x^2)",
        "1 / sqrt(x^2 - 1)",
        "sqrt(x) * ln(x)",
        "x^(1/3)",                      # monotone on all R
        "x * sin(x)",
        "sin(1/x)",
        "x^2 * sin(1/x)",
        "abs(x^2 - 1)",
        "floor(x)",
        "x + 1/x",
        "(x^3 - 1) / (x^2 + x + 1)",
        "x^2 / (x + 1)",
        "x^x",                          # HA y=0 was spurious — now suppressed
        "ln(ln(x))",                    # VA at x=0 was spurious — now suppressed
        "1 / (1 - x^2)",
    ]

    for f_str in test_functions:
        engine.analyze(f_str)