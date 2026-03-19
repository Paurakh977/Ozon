import sympy as sp
import time
from sympy.calculus.util import continuous_domain, periodicity, AccumBounds
from sympy.calculus.singularities import singularities

try:
    from algo import get_sympified_expr
except ImportError:
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
    
    def get_sympified_expr(user_input):
        transformations = (standard_transformations + (implicit_multiplication_application,))
        return parse_expr(user_input, transformations=transformations)

class FunctionAnalysisEngine:
    """
    A super robust and powerful math engine to analyze real functions.
    Extracts Domain, Intercepts, Extrema (Maxima/Minima), Inflection Points,
    Asymptotes (Vertical, Horizontal, Oblique), Parity, and Monotonicity.
    """

    def __init__(self, debug=False):
        self.debug = debug
        self.x = sp.Symbol('x', real=True)

    def _log(self, msg):
        if self.debug:
            print(f"[Engine] {msg}")

    def safe_solveset(self, expr, domain=sp.Reals):
        try:
            return sp.solveset(expr, self.x, domain=domain)
        except Exception as e:
            self._log(f"Error solving {expr}: {e}")
            return sp.EmptySet

    def _in_domain(self, point, domain):
        """Check if a point is in the domain - handles both sympy and Python bools."""
        try:
            # For numeric points, try direct evaluation first
            if isinstance(point, (int, float)):
                point_val = float(point)
                # Handle Complement sets specially
                if isinstance(domain, sp.Complement):
                    base_set = domain.args[0]
                    excluded = domain.args[1]
                    # Check if point is in base set
                    in_base = self._in_domain(point_val, base_set)
                    if not in_base:
                        return False
                    # Check if point is NOT in excluded set
                    return not self._point_in_set(point_val, excluded)
                # Handle Union
                elif isinstance(domain, sp.Union):
                    for arg in domain.args:
                        if self._in_domain(point_val, arg):
                            return True
                    return False
                # Handle Interval
                elif isinstance(domain, sp.Interval):
                    if domain.left_open:
                        if point_val <= float(domain.start):
                            return False
                    else:
                        if point_val < float(domain.start):
                            return False
                    if domain.right_open:
                        if point_val >= float(domain.end):
                            return False
                    else:
                        if point_val > float(domain.end):
                            return False
                    return True
                elif domain == sp.Reals:
                    return True

            result = domain.contains(point)
            # Handle both SymPy and Python booleans
            if result is True or result == sp.true:
                return True
            if result is False or result == sp.false:
                return False
            # Try to simplify conditional results
            simplified = sp.simplify(result)
            if simplified is True or simplified == sp.true:
                return True
            if simplified is False or simplified == sp.false:
                return False
            # If still can't determine, assume True for Reals
            if domain == sp.Reals:
                return True
            return False
        except Exception:
            return False

    def _point_in_set(self, point_val, s):
        """Check if a numeric point is in a set (for exclusion checking)."""
        try:
            if isinstance(s, sp.FiniteSet):
                for pt in s:
                    try:
                        if abs(float(pt.evalf()) - point_val) < 1e-9:
                            return True
                    except:
                        pass
                return False
            elif isinstance(s, sp.ImageSet):
                # For ImageSets, sample some values and check
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
                for arg in s.args:
                    if self._point_in_set(point_val, arg):
                        return True
                return False
            elif isinstance(s, sp.Interval):
                start = float(s.start) if s.start != -sp.oo else -float('inf')
                end = float(s.end) if s.end != sp.oo else float('inf')
                if s.left_open:
                    in_left = point_val > start
                else:
                    in_left = point_val >= start
                if s.right_open:
                    in_right = point_val < end
                else:
                    in_right = point_val <= end
                return in_left and in_right
            return False
        except:
            return False

    def _extract_real_roots(self, point_set, test_pts_set):
        """Recursively parses all roots from complex SymPy Sets (Finite, Image, Condition, Union, Complement, Interval)"""
        def extract(s):
            if isinstance(s, sp.FiniteSet):
                for p in s:
                    if getattr(p, 'is_real', True): test_pts_set.add(p)
            elif isinstance(s, sp.ImageSet):
                lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                # Sample few periods
                for i in range(-5, 6):
                    try:
                        val = lam.expr.subs(var, i) if hasattr(lam, 'expr') else lam.subs(var, i)
                        if getattr(val, 'is_real', True): test_pts_set.add(val)
                    except: pass
            elif isinstance(s, sp.Interval):
                if s.start != -sp.oo: test_pts_set.add(s.start)
                if s.end != sp.oo: test_pts_set.add(s.end)
            elif isinstance(s, (sp.Union, sp.Intersection, sp.Complement)):
                for arg in s.args: extract(arg)
            elif isinstance(s, sp.ConditionSet):
                # Fallback to identify roots for transcendental mixed functions (e.g., sin(x)/x extrema)
                expr_cond = s.condition.lhs - s.condition.rhs if isinstance(s.condition, sp.Eq) else s.condition
                found_approx = set()
                for guess in [i/2.0 for i in range(-20, 21)]:
                    try:
                        root = sp.nsolve(expr_cond, self.x, guess)
                        if getattr(root, 'is_real', True):
                            val = float(root)
                            if abs(val) < 1e-3:
                                val = 0.0
                            r_val = round(val, 3)
                            if r_val not in found_approx:
                                found_approx.add(r_val)
                                test_pts_set.add(sp.sympify(val))
                    except: pass
        extract(point_set)

    def get_domain(self, expr):
        self._log("Calculating Domain...")
        try:
            return continuous_domain(expr, self.x, sp.Reals)
        except Exception as e:
            self._log(f"Domain calculation failed: {e}")
            return sp.Reals

    def get_intercepts(self, expr, domain):
        self._log("Calculating Intercepts...")
        intercepts = {'x':[], 'y': None}
        
        # Y-intercept: Evaluate strictly if 0 is genuinely mathematically in the Domain. No limit trickery.
        try:
            if self._in_domain(0, domain):
                y_val = expr.subs(self.x, 0)
                if y_val.is_real and not y_val.has(sp.nan, sp.zoo, sp.I):
                    intercepts['y'] = sp.simplify(y_val)
        except Exception: pass
        
        # X-intercepts
        try:
            x_sols = self.safe_solveset(expr)
            if isinstance(x_sols, sp.FiniteSet):
                valid =[]
                for sol in x_sols:
                    try:
                        if sol.is_real and self._in_domain(sol, domain):
                            valid.append(sp.simplify(sol))
                    except: pass
                intercepts['x'] = valid
            elif not isinstance(x_sols, sp.EmptySet.__class__):
                # For infinite periodic roots (ImageSets), mathematically intersect them against the domain!
                clean_sols = sp.Intersection(x_sols, domain)
                intercepts['x'] = clean_sols
        except Exception: pass
        return intercepts

    def get_extrema(self, expr, domain):
        self._log("Calculating Extrema...")
        extrema = {'minima': [], 'maxima':[]}
        try:
            f_prime = sp.diff(expr, self.x)
            roots = self.safe_solveset(f_prime)
            try:
                domain_f_prime = continuous_domain(f_prime, self.x, sp.Reals)
            except Exception:
                try:
                    from sympy.calculus.singularities import singularities
                    sings = singularities(f_prime, self.x)
                    domain_f_prime = sp.Complement(domain, sings)
                except:
                    domain_f_prime = domain
                    
            crit_undef = sp.Complement(sp.Reals, domain_f_prime)
            
            cands = set()
            self._extract_real_roots(roots, cands)
            self._extract_real_roots(crit_undef, cands)
            
            # Explicitly extract domain boundaries (endpoints are candidate extrema)
            def extract_boundaries(s):
                if isinstance(s, sp.Interval):
                    if s.start != -sp.oo: cands.add(s.start)
                    if s.end != sp.oo: cands.add(s.end)
                elif isinstance(s, sp.Union):
                    for arg in s.args: extract_boundaries(arg)
            extract_boundaries(domain)
            
            unique_pts =[]
            for p in cands:
                try:
                    if self._in_domain(p, domain):
                        p_val = float(p.evalf())
                        if not any(abs(p_val - float(up.evalf())) < 1e-5 for up in unique_pts):
                            unique_pts.append(p)
                except: pass
                
            unique_pts.sort(key=lambda p: float(p.evalf()))
            
            for cp in unique_pts:
                cp_val = float(cp.evalf())
                eps = 1e-5
                
                left_in, right_in = True, True
                try: left_in = self._in_domain(cp_val - eps, domain)
                except: pass
                try: right_in = self._in_domain(cp_val + eps, domain)
                except: pass
                
                try:
                    left_val = f_prime.subs(self.x, cp_val - eps).evalf() if left_in else None
                    right_val = f_prime.subs(self.x, cp_val + eps).evalf() if right_in else None
                    y_val = sp.simplify(expr.subs(self.x, cp))
                    
                    if left_val is not None and right_val is not None:
                        if left_val < -1e-7 and right_val > 1e-7: extrema['minima'].append((sp.simplify(cp), y_val))
                        elif left_val > 1e-7 and right_val < -1e-7: extrema['maxima'].append((sp.simplify(cp), y_val))
                    elif left_val is None and right_val is not None: # Left Endpoint
                        if right_val > 1e-7: extrema['minima'].append((sp.simplify(cp), y_val))
                        elif right_val < -1e-7: extrema['maxima'].append((sp.simplify(cp), y_val))
                    elif left_val is not None and right_val is None: # Right Endpoint
                        if left_val > 1e-7: extrema['maxima'].append((sp.simplify(cp), y_val))
                        elif left_val < -1e-7: extrema['minima'].append((sp.simplify(cp), y_val))
                except: pass
        except Exception as e:
            self._log(f"Extrema calculation failed: {e}")
        return extrema

    def get_inflection_points(self, expr, domain):
        self._log("Calculating Inflection Points...")
        inflections =[]
        try:
            f_prime = sp.diff(expr, self.x)
            f_dp = sp.diff(f_prime, self.x)
            
            roots = self.safe_solveset(f_dp)
            try:
                domain_f_dp = continuous_domain(f_dp, self.x, sp.Reals)
            except Exception:
                try:
                    from sympy.calculus.singularities import singularities
                    sings = singularities(f_dp, self.x)
                    domain_f_dp = sp.Complement(domain, sings)
                except:
                    domain_f_dp = domain
                    
            undef = sp.Complement(sp.Reals, domain_f_dp)
            
            cands = set()
            self._extract_real_roots(roots, cands)
            self._extract_real_roots(undef, cands)
            
            unique_pts =[]
            for p in cands:
                try:
                    if self._in_domain(p, domain):
                        p_val = float(p.evalf())
                        if not any(abs(p_val - float(up.evalf())) < 1e-5 for up in unique_pts):
                            unique_pts.append(p)
                except: pass
                
            unique_pts.sort(key=lambda p: float(p.evalf()))
            
            for cp in unique_pts:
                cp_val = float(cp.evalf())
                eps = 1e-5
                try:
                    left_in = self._in_domain(cp_val - eps, domain)
                    right_in = self._in_domain(cp_val + eps, domain)
                    if not (left_in and right_in): continue # Endpoints can't be inflection
                    
                    lv = f_dp.subs(self.x, cp_val - eps).evalf()
                    rv = f_dp.subs(self.x, cp_val + eps).evalf()

                    # Check for sign change - use sign comparison instead of product threshold
                    lv_sign = 1 if lv > 0 else (-1 if lv < 0 else 0)
                    rv_sign = 1 if rv > 0 else (-1 if rv < 0 else 0)
                    if lv_sign != 0 and rv_sign != 0 and lv_sign != rv_sign:
                        y_val = sp.simplify(expr.subs(self.x, cp))
                        inflections.append((sp.simplify(cp), y_val))
                except: pass
        except Exception as e:
            self._log(f"Inflection points failed: {e}")
        return inflections

    def get_asymptotes(self, expr, domain):
        self._log("Calculating Asymptotes...")
        asymptotes = {'vertical': [], 'horizontal': [], 'oblique': []}

        for d in [sp.oo, -sp.oo]:
            try:
                L = sp.limit(expr, self.x, d)
                # AccumBounds indicates oscillation - no horizontal asymptote
                if isinstance(L, AccumBounds):
                    continue
                if L.is_real and not L.is_infinite and not L.has(sp.zoo, sp.nan):
                    val = sp.simplify(L)
                    if val not in asymptotes['horizontal']: asymptotes['horizontal'].append(val)
            except: pass

        for d in [sp.oo, -sp.oo]:
            try:
                m = sp.limit(expr / self.x, self.x, d)
                if m.is_real and not m.is_infinite and m != 0 and not m.has(sp.zoo, sp.nan):
                    c = sp.limit(expr - m * self.x, self.x, d)
                    if c.is_real and not c.is_infinite and not c.has(sp.zoo, sp.nan):
                        line = sp.simplify(m * self.x + c)
                        if line not in asymptotes['oblique']: asymptotes['oblique'].append(line)
            except: pass

        try:
            excluded = sp.Complement(sp.Reals, domain)

            def check_va_at_point(pt, check_left=True, check_right=True):
                """Check if there's a vertical asymptote at a point."""
                if pt.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I):
                    return False
                try:
                    pt_float = float(pt.evalf())
                    if abs(pt_float) > 1e10:  # Skip very large points
                        return False
                except:
                    pass
                try:
                    if check_right:
                        lim_r = sp.limit(expr, self.x, pt, dir='+')
                        if getattr(lim_r, 'is_infinite', False) or lim_r.has(sp.zoo):
                            return True
                    if check_left:
                        lim_l = sp.limit(expr, self.x, pt, dir='-')
                        if getattr(lim_l, 'is_infinite', False) or lim_l.has(sp.zoo):
                            return True
                except: pass
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
                    # Sample at n=0 and n=1 to be sure
                    for n_val in [0, 1]:
                        sample_pt = sample_expr.subs(var, n_val)
                        if check_va_at_point(sample_pt):
                            vas.append(s)
                            break
                elif isinstance(s, sp.Union):
                    for arg in s.args: process_excluded(arg)
                elif isinstance(s, sp.Complement):
                    # Handle nested Complement
                    process_excluded(s.args[1])

            process_excluded(excluded)

            # Also check domain boundary points for asymptotes (e.g., x=0 for ln(x))
            def extract_boundary_asymptotes(dom):
                if isinstance(dom, sp.Interval):
                    if dom.start != -sp.oo and dom.start.is_finite:
                        # Left boundary - only check right limit (into domain)
                        if dom.left_open and check_va_at_point(dom.start, check_left=False, check_right=True):
                            if dom.start not in vas:
                                vas.append(dom.start)
                    if dom.end != sp.oo and dom.end.is_finite:
                        # Right boundary - only check left limit (into domain)
                        if dom.right_open and check_va_at_point(dom.end, check_left=True, check_right=False):
                            if dom.end not in vas:
                                vas.append(dom.end)
                elif isinstance(dom, sp.Union):
                    for arg in dom.args:
                        extract_boundary_asymptotes(arg)
                elif isinstance(dom, sp.Complement):
                    # For Complement, check the first arg (base set)
                    extract_boundary_asymptotes(dom.args[0])

            extract_boundary_asymptotes(domain)

            # Also try direct singularities detection as fallback
            try:
                sings = singularities(expr, self.x)
                if isinstance(sings, sp.FiniteSet):
                    for pt in sings:
                        if pt.is_real and pt not in vas:
                            if check_va_at_point(pt):
                                vas.append(pt)
                elif isinstance(sings, sp.ImageSet):
                    if sings not in vas:
                        lam = sings.lamda if hasattr(sings, 'lamda') else sings.args[0]
                        var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                        sample_expr = lam.expr if hasattr(lam, 'expr') else lam
                        sample_pt = sample_expr.subs(var, 0)
                        if check_va_at_point(sample_pt):
                            vas.append(sings)
                elif isinstance(sings, sp.Union):
                    for s_arg in sings.args:
                        if isinstance(s_arg, sp.FiniteSet):
                            for pt in s_arg:
                                if pt.is_real and pt not in vas and check_va_at_point(pt):
                                    vas.append(pt)
                        elif isinstance(s_arg, sp.ImageSet) and s_arg not in vas:
                            lam = s_arg.lamda if hasattr(s_arg, 'lamda') else s_arg.args[0]
                            var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                            sample_expr = lam.expr if hasattr(lam, 'expr') else lam
                            sample_pt = sample_expr.subs(var, 0)
                            if check_va_at_point(sample_pt):
                                vas.append(s_arg)
            except Exception:
                pass

            # Deduplicate ImageSets that represent the same mathematical set
            def imageset_equivalent(s1, s2):
                """Check if two ImageSets represent equivalent periodic sets."""
                if not (isinstance(s1, sp.ImageSet) and isinstance(s2, sp.ImageSet)):
                    return False
                try:
                    lam1 = s1.lamda if hasattr(s1, 'lamda') else s1.args[0]
                    lam2 = s2.lamda if hasattr(s2, 'lamda') else s2.args[0]
                    expr1 = lam1.expr if hasattr(lam1, 'expr') else lam1
                    expr2 = lam2.expr if hasattr(lam2, 'expr') else lam2
                    var1 = lam1.variables[0] if hasattr(lam1, 'variables') else list(lam1.free_symbols)[0]
                    var2 = lam2.variables[0] if hasattr(lam2, 'variables') else list(lam2.free_symbols)[0]
                    # Sample both and check if they generate the same values (mod period)
                    vals1 = {float(expr1.subs(var1, i).evalf()) for i in range(-3, 4)}
                    vals2 = {float(expr2.subs(var2, i).evalf()) for i in range(-3, 4)}
                    # Check if any value from vals1 is close to any value in vals2
                    for v1 in vals1:
                        for v2 in vals2:
                            if abs(v1 - v2) < 1e-6:
                                return True
                except:
                    pass
                return False

            # Remove duplicate ImageSets
            unique_vas = []
            for v in vas:
                is_dup = False
                for uv in unique_vas:
                    if isinstance(v, sp.ImageSet) and isinstance(uv, sp.ImageSet):
                        if imageset_equivalent(v, uv):
                            is_dup = True
                            break
                    elif v == uv:
                        is_dup = True
                        break
                if not is_dup:
                    unique_vas.append(v)

            for v in unique_vas:
                if v not in asymptotes['vertical']:
                    asymptotes['vertical'].append(v)
        except Exception as e:
            self._log(f"Vertical asymptote failed: {e}")

        return asymptotes

    def get_parity(self, expr):
        self._log("Calculating Parity...")
        try:
            f_neg = sp.simplify(expr.subs(self.x, -self.x))
            f_pos = sp.simplify(expr)
            if f_neg == f_pos: return "Even"
            if f_neg == -f_pos: return "Odd"
            
            # More rigorous fallback
            if expr.equals(expr.subs(self.x, -self.x)): return "Even"
            if expr.equals(-expr.subs(self.x, -self.x)): return "Odd"
        except Exception: pass
        return "Neither even nor odd"

    def get_periodicity(self, expr):
        try: return periodicity(expr, self.x)
        except Exception: return None

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

            # For periodic functions, sample within a bounded range
            if period is not None:
                try:
                    period_val = float(period.evalf())
                    # Sample within 2-3 periods around origin for periodic functions
                    sample_range = max(2 * period_val, 10)
                    self._extract_real_roots_bounded(roots, breaks_set, -sample_range, sample_range)
                    disc_f = sp.Complement(sp.Reals, domain)
                    disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                    self._extract_real_roots_bounded(disc_f, breaks_set, -sample_range, sample_range)
                    self._extract_real_roots_bounded(disc_fp, breaks_set, -sample_range, sample_range)
                except:
                    self._extract_real_roots(roots, breaks_set)
                    disc_f = sp.Complement(sp.Reals, domain)
                    disc_fp = sp.Complement(sp.Reals, domain_f_prime)
                    self._extract_real_roots(disc_f, breaks_set)
                    self._extract_real_roots(disc_fp, breaks_set)
            else:
                self._extract_real_roots(roots, breaks_set)
                disc_f = sp.Complement(sp.Reals, domain)
                disc_fp = sp.Complement(sp.Reals, domain_f_prime)
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

            # For periodic functions, don't use -oo/oo
            if period is not None and unique_breaks:
                b_vals = [b[1] for b in unique_breaks]
            else:
                b_vals = [-sp.oo] + [b[1] for b in unique_breaks] + [sp.oo]

            for i in range(len(b_vals) - 1):
                start = b_vals[i]
                end = b_vals[i + 1]

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
                        val = f_prime.subs(self.x, test_pt).evalf()
                        if val > 1e-7:
                            intervals['increasing'].append((start, end))
                        elif val < -1e-7:
                            intervals['decreasing'].append((start, end))
                except:
                    pass
        except Exception as e:
            self._log(f"Monotonicity calculation failed: {e}")
        return intervals

    def _extract_real_roots_bounded(self, point_set, test_pts_set, lower, upper):
        """Recursively parses roots from SymPy Sets, bounded to a range."""
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
                # Sample within bounds
                for i in range(-20, 21):
                    try:
                        val = lam.expr.subs(var, i) if hasattr(lam, 'expr') else lam.subs(var, i)
                        val_float = float(val.evalf())
                        if getattr(val, 'is_real', True) and lower <= val_float <= upper:
                            test_pts_set.add(val)
                    except:
                        pass
            elif isinstance(s, sp.Interval):
                if s.start != -sp.oo and float(s.start.evalf()) >= lower:
                    test_pts_set.add(s.start)
                if s.end != sp.oo and float(s.end.evalf()) <= upper:
                    test_pts_set.add(s.end)
            elif isinstance(s, (sp.Union, sp.Intersection, sp.Complement)):
                for arg in s.args:
                    extract(arg)
            elif isinstance(s, sp.ConditionSet):
                expr_cond = s.condition.lhs - s.condition.rhs if isinstance(s.condition, sp.Eq) else s.condition
                found_approx = set()
                for guess in [i / 2.0 for i in range(-20, 21)]:
                    if lower <= guess <= upper:
                        try:
                            root = sp.nsolve(expr_cond, self.x, guess)
                            if getattr(root, 'is_real', True):
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

    def analyze(self, func_string):
        print(f"\n{'='*50}")
        print(f"[{func_string}] Analysis Starting...")
        print(f"{'='*50}")
        
        start_time = time.time()
        func_string = func_string.replace('^', '**')
        func_string = func_string.replace('e**', 'E**').replace('e^', 'E**')
        # Handle common function name variants
        func_string = func_string.replace('arctan', 'atan')
        func_string = func_string.replace('arcsin', 'asin')
        func_string = func_string.replace('arccos', 'acos')
        func_string = func_string.replace('arccot', 'acot')
        func_string = func_string.replace('arcsec', 'asec')
        func_string = func_string.replace('arccsc', 'acsc')
        expr = get_sympified_expr(func_string)
        
        real_x = sp.Symbol('x', real=True)
        expr = expr.subs({s: real_x for s in expr.free_symbols if s.name == 'x'})
        self.x = real_x
            
        domain = self.get_domain(expr)
        intercepts = self.get_intercepts(expr, domain)
        extrema = self.get_extrema(expr, domain)
        inflections = self.get_inflection_points(expr, domain)
        asymptotes = self.get_asymptotes(expr, domain)
        parity = self.get_parity(expr)
        period = self.get_periodicity(expr)
        monotonicity = self.get_monotonicity(expr, domain, period)
        
        elapsed = time.time() - start_time
        
        results = {
            'Function': expr,
            'Domain': domain,
            'Intercepts': intercepts,
            'Extrema': extrema,
            'Inflection Points': inflections,
            'Asymptotes': asymptotes,
            'Parity': parity,
            'Periodicity': period,
            'Monotonicity': monotonicity,
            'Time (s)': round(elapsed, 4)
        }
        
        self.print_report(results)
        return results

    def print_report(self, res):
        # Helper: Converts ugly sets into beautiful standard math formats like (-oo, 0) U (0, oo)
        def format_val(val):
            try:
                if val.has(sp.I): return None
                val = sp.simplify(val)
                if val.count_ops() > 15: # Approx long exact roots for readability
                    return f"{val} (approx {val.evalf():.3f})"
                if isinstance(val, sp.Float): return f"{float(val):.4f}"
                return str(val)
            except: return str(val)
            
        def clean_set(s):
            if s == sp.Reals: return "(-oo, oo)"
            if s == sp.EmptySet: return "None"
            if isinstance(s, list):
                if not s: return "None"
                return ", ".join([clean_set(x) if isinstance(x, sp.Set) else format_val(x) for x in s])
            if isinstance(s, sp.FiniteSet):
                if not s: return "None"
                return ", ".join([format_val(arg) for arg in s])
            elif isinstance(s, sp.ImageSet):
                try:
                    lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                    expr = lam.expr if hasattr(lam, 'expr') else lam
                    return f"{str(expr).replace('_n', 'n')} (for integer n)"
                except: return str(s).replace('_n', 'n')
            elif isinstance(s, sp.Union):
                return " U ".join([clean_set(arg) for arg in s.args])
            elif isinstance(s, sp.Intersection):
                return " & ".join([clean_set(arg) for arg in s.args])
            elif isinstance(s, sp.Complement):
                return f"{clean_set(s.args[0])} excluding {clean_set(s.args[1])}"
            elif isinstance(s, sp.Interval):
                lb = "(" if s.left_open else "["
                rb = ")" if s.right_open else "]"
                return f"{lb}{s.start}, {s.end}{rb}"
            return str(s).replace('_n', 'n')

        print(f"Function:       f(x) = {res['Function']}")
        print(f"Domain:         {clean_set(res['Domain'])}")
        
        x_ints_raw = res['Intercepts']['x']
        if x_ints_raw is None or isinstance(x_ints_raw, sp.EmptySet.__class__) or (isinstance(x_ints_raw, list) and len(x_ints_raw) == 0):
            x_ints = "None"
        else:
            x_ints = clean_set(x_ints_raw)
            
        print(f"X-Intercepts:   {x_ints}")
        print(f"Y-Intercept:    {format_val(res['Intercepts']['y']) if res['Intercepts']['y'] is not None else 'None'}")
        
        period = res['Periodicity']
        
        def format_extrema(pts, period):
            if not pts: return "None"
            def fmt_pt(pt):
                return f"({format_val(pt[0])}, {format_val(pt[1])})"
                
            if period is None:
                sorted_pts = sorted(pts, key=lambda p: abs(float(p[0].evalf())) if getattr(p[0], 'evalf', None) else float('inf'))
                if len(sorted_pts) > 6:
                    closest = sorted_pts[:6]
                    closest.sort(key=lambda p: float(p[0].evalf()) if getattr(p[0], 'evalf', None) else float('inf'))
                    return ", ".join([fmt_pt(p) for p in closest]) + " ... (and infinitely many more)"
                else:
                    sorted_pts.sort(key=lambda p: float(p[0].evalf()) if getattr(p[0], 'evalf', None) else float('inf'))
                    return ", ".join([fmt_pt(p) for p in sorted_pts])
            
            base_pts = []
            seen_mod =[]
            pts = sorted(pts, key=lambda p: abs(float(p[0].evalf())) if getattr(p[0], 'evalf', None) else float('inf'))
            for x, y in pts:
                try:
                    x_f, p_f = float(x.evalf()), float(period.evalf())
                    mod_val = x_f % p_f
                    if not any(abs(mod_val - sm) < 1e-3 or abs(mod_val - sm - p_f) < 1e-3 or abs(mod_val - sm + p_f) < 1e-3 for sm in seen_mod):
                        seen_mod.append(mod_val)
                        base_pts.append((x, y))
                except: base_pts.append((x, y))
            base_pts.sort(key=lambda p: float(p[0].evalf()) if getattr(p[0], 'evalf', None) else float('inf'))
            res_str = ", ".join([f"({format_val(x)} + n*{period}, {format_val(y)})" for x, y in base_pts])
            return res_str + " (for integer n)"

        print(f"Minima:         {format_extrema(res['Extrema']['minima'], period)}")
        print(f"Maxima:         {format_extrema(res['Extrema']['maxima'], period)}")
        print(f"Inflection pts: {format_extrema(res['Inflection Points'], period)}")
        
        vert = ", ".join([f"x = {clean_set(v)}" for v in res['Asymptotes']['vertical']])
        horz = ", ".join([f"y = {clean_set(h)}" for h in res['Asymptotes']['horizontal']])
        oblq = ", ".join([f"y = {clean_set(o)}" for o in res['Asymptotes']['oblique']])
        print(f"Vertical Asym:  {vert if vert else 'None'}")
        print(f"Horizontal Asym:{horz if horz else 'None'}")
        print(f"Oblique Asym:   {oblq if oblq else 'None'}")
        
        print(f"Parity:         {res['Parity']}")
        print(f"Periodicity:    {format_val(period) if period else 'None'}")
        
        print("Monotonicity:")
        if not res['Monotonicity']['increasing'] and not res['Monotonicity']['decreasing']:
            print("  None or could not be determined.")
        else:
            def print_intervals(intervals, period, label):
                if not intervals: return
                if period is None:
                    sorted_by_abs = sorted(intervals, key=lambda i: abs(float(i[0].evalf())) if getattr(i[0], 'evalf', None) and i[0] not in [-sp.oo, sp.oo] else float('inf'))
                    if len(intervals) > 6:
                        closest = sorted_by_abs[:6]
                        closest.sort(key=lambda i: float(i[0].evalf()) if getattr(i[0], 'evalf', None) and i[0] not in [-sp.oo, sp.oo] else (-float('inf') if i[0] == -sp.oo else float('inf')))
                        for s, e in closest: print(f"  ({format_val(s)}, {format_val(e)})\t{label}")
                        print(f"  ... (and infinitely many more {label.lower()} intervals)")
                    else:
                        closest = sorted(intervals, key=lambda i: float(i[0].evalf()) if getattr(i[0], 'evalf', None) and i[0] not in[-sp.oo, sp.oo] else (-float('inf') if i[0] == -sp.oo else float('inf')))
                        for s, e in closest: print(f"  ({format_val(s)}, {format_val(e)})\t{label}")
                    return
                
                base_ints, seen_mod, sorted_ints = [], [],[]
                for s, e in intervals:
                    try: sorted_ints.append((0 if s == -sp.oo else abs(float(s.evalf())), s, e))
                    except: sorted_ints.append((float('inf'), s, e))
                sorted_ints.sort(key=lambda x: x[0])
                
                for _, s, e in sorted_ints:
                    try:
                        if s == -sp.oo or e == sp.oo:
                            base_ints.append((s, e)); continue
                        s_f, p_f = float(s.evalf()), float(period.evalf())
                        mod_val = s_f % p_f
                        if not any(abs(mod_val - sm) < 1e-3 or abs(mod_val - sm - p_f) < 1e-3 or abs(mod_val - sm + p_f) < 1e-3 for sm in seen_mod):
                            seen_mod.append(mod_val); base_ints.append((s, e))
                    except: base_ints.append((s, e))
                        
                base_ints.sort(key=lambda i: float(i[0].evalf()) if getattr(i[0], 'evalf', None) and i[0] not in[-sp.oo, sp.oo] else (-float('inf') if i[0] == -sp.oo else float('inf')))
                for s, e in base_ints:
                    start_str = f"{format_val(s)} + n*{period}" if s not in [-sp.oo, sp.oo] else "-oo"
                    end_str = f"{format_val(e)} + n*{period}" if e not in [-sp.oo, sp.oo] else "oo"
                    print(f"  ({start_str}, {end_str})\t{label} (for integer n)")

            print_intervals(res['Monotonicity']['increasing'], period, "Increasing")
            print_intervals(res['Monotonicity']['decreasing'], period, "Decreasing")
        
        print(f"\n[Analyzed in {res['Time (s)']} seconds]")
        print("-" * 50)

if __name__ == "__main__":
    engine = FunctionAnalysisEngine(debug=False)
    
    test_functions =[
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
    ]
    
    test_functions = [
    # --- Rational Functions (edge cases) ---
    "1 / (x^2 + 1)",              # No vertical asymptotes, even
    "(x^3 - x) / (x^2 - 1)",      # Removable discontinuities + oblique asymptote
    "(x^2 - 4) / (x - 2)",        # Hole at x=2 (removable), not a true VA
    "x / (x^2 - x - 6)",          # Two VAs: x=3, x=-2
    "(x^3 + 1) / (x^2 - 1)",      # Oblique asymptote + VA

    # --- Trig & Inverse Trig ---
    "cos(x)",                      # Classic, compare parity vs sin(x)
    "sin(x)^2",                    # Period should be pi, not 2*pi
    "tan(x)^2",                    # Period pi, always non-negative
    "arctan(x)",                   # Horizontal asymptotes ±pi/2, no VA
    "x - sin(x)",                  # Inflection at origin, monotone increasing
    "sin(x) + cos(x)",             # Phase-shifted, period 2*pi
    "1 / sin(x)",                  # csc(x), periodic VAs

    # --- Exponential & Log ---
    "e^x / (1 + e^x)",            # Sigmoid: horizontal asymptotes 0 and 1
    "ln(x^2)",                     # Domain: x != 0, even function
    "x^2 * e^(-x)",               # Interesting: max at x=2, inflection at x = 2±sqrt(2)
    "ln(x + sqrt(x^2 + 1))",      # arcsinh(x), odd, monotone increasing
    "e^(1/x)",                     # Essential singularity at 0

    # --- Parity Edge Cases ---
    "x^4 - 2*x^2 + 1",           # Even, perfect square (x^2-1)^2
    "x^5 - x^3 + x",              # Odd polynomial
    "x^2 + x + 1",                # Neither (asymmetric)

    # --- Challenging Domains ---
    "sqrt(4 - x^2)",              # Semicircle, domain [-2, 2]
    "ln(1 - x^2)",                # Domain (-1, 1), symmetric
    "1 / sqrt(x^2 - 1)",          # Domain: |x| > 1, two pieces
    "sqrt(x) * ln(x)",            # Domain (0, oo), min at x = 1/e^2

    # --- Composite / Unusual ---
    "x^(1/3)",                    # Cube root, odd, inflection at origin
    "x * sin(x)",                 # Product, even, unbounded oscillation
    "sin(1/x)",                   # Oscillates wildly near 0 — stress test!
    "x^2 * sin(1/x)",             # Smoother version, differentiable at 0
    "abs(x^2 - 1)",               # Absolute value of polynomial, cusps at ±1
    "floor(x)",                   # Step function — expect graceful failure

    # --- Functions with Oblique Asymptotes ---
    "x + 1/x",                    # Already tested as (x^2+1)/x but alias form
    "(x^3 - 1) / (x^2 + x + 1)", # Simplifies to (x-1), oblique asymptote
    "x^2 / (x + 1)",             # Oblique: y = x - 1

    # --- Near-Pathological ---
    "x^x",                        # Domain (0, oo) only — tests complex domain
    "ln(ln(x))",                  # Domain (1, oo), nested log
    "1 / (1 - x^2)",             # Two VAs at ±1
]
    for f_str in test_functions:
        engine.analyze(f_str)