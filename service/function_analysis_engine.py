import sympy as sp
import time
from sympy.calculus.util import continuous_domain, periodicity

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
            sol = sp.solveset(expr, self.x, domain=domain)
            return sol
        except Exception as e:
            self._log(f"Error solving {expr}: {e}")
            return sp.EmptySet

    def _extract_points(self, point_set, domain, expr_ref=None):
        points = set()
        
        def process_set(s):
            if isinstance(s, sp.FiniteSet):
                for p in s:
                    if p.is_real is not False and not p.has(sp.I): points.add(p)
            elif isinstance(s, sp.ImageSet):
                try:
                    lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                    if hasattr(lam, 'variables'):
                        var = lam.variables[0]
                        ex = lam.expr
                    else:
                        fv = list(lam.free_symbols)
                        var = fv[0] if fv else None
                        ex = lam
                    
                    if var is not None:
                        for i in range(-5, 6): points.add(ex.subs(var, i))
                    else:
                        points.add(ex)
                except: pass
            elif isinstance(s, sp.ConditionSet):
                try:
                    expr_cond = s.condition.lhs - s.condition.rhs if isinstance(s.condition, sp.Eq) else s.condition
                    for guess in[i/2.0 for i in range(-30, 31)]:
                        try:
                            root = sp.nsolve(expr_cond, self.x, guess)
                            points.add(root) 
                        except: pass
                except: pass
            elif hasattr(s, 'args'):
                for arg in s.args: process_set(arg)

        process_set(point_set)
        
        valid_points =[]
        for p in points:
            try:
                if domain.contains(p) is not sp.false:
                    valid_points.append(p)
                else:
                    if expr_ref is not None:
                        limit_val = sp.limit(expr_ref, self.x, p)
                        if limit_val.is_real and not getattr(limit_val, 'is_infinite', False) and not limit_val.has(sp.nan, sp.zoo):
                            valid_points.append(p)
            except: pass
                
        return valid_points

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
        
        # 🔑 Y-INTERCEPT FIX: Gracefully handle Removable Singularities (like sin(x)/x)
        try:
            y_val = expr.subs(self.x, 0)
            if y_val.has(sp.nan, sp.zoo) or domain.contains(0) == sp.false:
                y_val = sp.limit(expr, self.x, 0)
            if y_val.is_real and not getattr(y_val, 'is_infinite', False) and not y_val.has(sp.nan, sp.zoo, sp.I):
                intercepts['y'] = sp.simplify(y_val)
        except Exception: pass
        
        try:
            x_sols = self.safe_solveset(expr)
            if not isinstance(x_sols, sp.EmptySet.__class__):
                if isinstance(x_sols, sp.FiniteSet):
                    clean_xs =[sp.simplify(sol) for sol in x_sols if sol.is_real is not False and not sol.has(sp.I) and domain.contains(sol) is not sp.false]
                    intercepts['x'] = list(set(clean_xs))
                else:
                    intercepts['x'] =[x_sols]
        except Exception: pass
        return intercepts

    def get_extrema(self, expr, domain):
        self._log("Calculating Extrema...")
        extrema = {'minima':[], 'maxima':[]}
        try:
            f_prime = sp.diff(expr, self.x)
            crit_pts_zero = self.safe_solveset(f_prime)
            n, d = sp.fraction(sp.cancel(f_prime))
            crit_pts_undef = self.safe_solveset(d)
            all_crit = sp.Union(crit_pts_zero, crit_pts_undef)
            
            explicit_cands = set()
            for arg in expr.atoms(sp.Abs):
                s = self.safe_solveset(arg.args[0])
                if isinstance(s, sp.FiniteSet):
                    for p in s: explicit_cands.add(p)
                    
            if isinstance(domain, sp.Interval):
                if domain.start != -sp.oo: explicit_cands.add(domain.start)
                if domain.end != sp.oo: explicit_cands.add(domain.end)
            elif isinstance(domain, sp.Union):
                for arg in domain.args:
                    if isinstance(arg, sp.Interval):
                        if arg.start != -sp.oo: explicit_cands.add(arg.start)
                        if arg.end != sp.oo: explicit_cands.add(arg.end)

            eval_points_raw = self._extract_points(all_crit, domain, expr)
            
            for p in explicit_cands:
                try:
                    if domain.contains(p) is not sp.false: eval_points_raw.append(p)
                except: pass
                
            unique_points = {}
            for p in eval_points_raw:
                try:
                    val = float(p.evalf())
                    if not any(abs(k - val) < 1e-3 for k in unique_points.keys()): unique_points[val] = p
                except: pass
            eval_points = sorted(list(unique_points.values()), key=lambda p: float(p.evalf()))
            
            for cp in eval_points:
                eps = 1e-5
                left_val, right_val = None, None
                try:
                    if domain.contains(cp - eps) is not sp.false:
                        lv = f_prime.subs(self.x, cp - eps).evalf()
                        if abs(lv) > 1e-9: left_val = lv
                except: pass
                try:
                    if domain.contains(cp + eps) is not sp.false:
                        rv = f_prime.subs(self.x, cp + eps).evalf()
                        if abs(rv) > 1e-9: right_val = rv
                except: pass
                
                try:
                    y_val = expr.subs(self.x, cp)
                    if y_val.has(sp.nan, sp.zoo): y_val = sp.limit(expr, self.x, cp) 
                    y_val = sp.simplify(y_val)
                except: continue
                    
                if left_val is not None and right_val is not None:
                    if left_val < 0 and right_val > 0: extrema['minima'].append((sp.simplify(cp), y_val))
                    elif left_val > 0 and right_val < 0: extrema['maxima'].append((sp.simplify(cp), y_val))
                elif left_val is None and right_val is not None:
                    if right_val > 0: extrema['minima'].append((sp.simplify(cp), y_val))
                    elif right_val < 0: extrema['maxima'].append((sp.simplify(cp), y_val))
                elif left_val is not None and right_val is None:
                    if left_val > 0: extrema['maxima'].append((sp.simplify(cp), y_val))
                    elif left_val < 0: extrema['minima'].append((sp.simplify(cp), y_val))
        except Exception as e:
            self._log(f"Extrema calculation failed: {e}")
        return extrema

    def get_inflection_points(self, expr, domain):
        self._log("Calculating Inflection Points...")
        inflections =[]
        try:
            f_prime = sp.diff(expr, self.x)
            f_double_prime = sp.diff(f_prime, self.x)
            candidates = self.safe_solveset(f_double_prime)
            n, d = sp.fraction(sp.cancel(f_double_prime))
            candidates_undef = self.safe_solveset(d)
            all_cands = sp.Union(candidates, candidates_undef)
            
            explicit_cands = set()
            if isinstance(domain, sp.Interval):
                if domain.start != -sp.oo: explicit_cands.add(domain.start)
                if domain.end != sp.oo: explicit_cands.add(domain.end)
            elif isinstance(domain, sp.Union):
                for arg in domain.args:
                    if isinstance(arg, sp.Interval):
                        if arg.start != -sp.oo: explicit_cands.add(arg.start)
                        if arg.end != sp.oo: explicit_cands.add(arg.end)

            eval_points_raw = self._extract_points(all_cands, domain, expr)
            for p in explicit_cands:
                try:
                    if domain.contains(p) is not sp.false: eval_points_raw.append(p)
                except: pass
                
            unique_points = {}
            for p in eval_points_raw:
                try:
                    val = float(p.evalf())
                    if not any(abs(k - val) < 1e-3 for k in unique_points.keys()): unique_points[val] = p
                except: pass
            eval_points = sorted(list(unique_points.values()), key=lambda p: float(p.evalf()))
            
            for cp in eval_points:
                eps = 1e-4
                left_val, right_val = None, None
                try:
                    if domain.contains(cp - eps) is not sp.false:
                        lv = f_double_prime.subs(self.x, cp - eps).evalf()
                        if abs(lv) > 1e-9: left_val = lv
                    if domain.contains(cp + eps) is not sp.false:
                        rv = f_double_prime.subs(self.x, cp + eps).evalf()
                        if abs(rv) > 1e-9: right_val = rv
                        
                    if left_val is not None and right_val is not None and left_val * right_val < 0:
                        y_val = expr.subs(self.x, cp)
                        if y_val.has(sp.nan, sp.zoo): y_val = sp.limit(expr, self.x, cp)
                        inflections.append((sp.simplify(cp), sp.simplify(y_val)))
                except: pass
        except Exception as e:
            self._log(f"Inflection points failed: {e}")
        return inflections

    def get_asymptotes(self, expr, domain):
        self._log("Calculating Asymptotes...")
        asymptotes = {'vertical':[], 'horizontal':[], 'oblique': []}

        for d in[sp.oo, -sp.oo]:
            try:
                L = sp.limit(expr, self.x, d)
                if not L.has(sp.Limit) and L.is_real is not False and not getattr(L, 'is_infinite', False) and not L.has(sp.zoo, sp.nan, sp.I) and not isinstance(L, sp.AccumBounds):
                    val = sp.simplify(L)
                    if val not in asymptotes['horizontal']: asymptotes['horizontal'].append(val)
            except: pass

        for d in [sp.oo, -sp.oo]:
            try:
                m = sp.limit(expr / self.x, self.x, d)
                if not m.has(sp.Limit) and m.is_real is not False and not getattr(m, 'is_infinite', False) and not m.has(sp.zoo, sp.nan, sp.I) and not isinstance(m, sp.AccumBounds) and m != 0:
                    c = sp.limit(expr - m * self.x, self.x, d)
                    if not c.has(sp.Limit) and c.is_real is not False and not getattr(c, 'is_infinite', False) and not c.has(sp.zoo, sp.nan, sp.I) and not isinstance(c, sp.AccumBounds):
                        line = sp.simplify(m * self.x + c)
                        if line not in asymptotes['oblique']: asymptotes['oblique'].append(line)
            except: pass

        try:
            excluded = sp.Complement(sp.Reals, domain)
            candidates = set()
            
            def extract_candidates(s):
                if isinstance(s, sp.FiniteSet):
                    for p in s: candidates.add(p)
                elif isinstance(s, sp.Interval):
                    candidates.add(s.start)
                    candidates.add(s.end)
                elif isinstance(s, sp.ImageSet):
                    try:
                        lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                        if hasattr(lam, 'variables'):
                            var = lam.variables[0]
                            ex = lam.expr
                        else:
                            fv = list(lam.free_symbols)
                            var = fv[0] if fv else None
                            ex = lam
                            
                        if var is not None:
                            for i in range(-5, 6): candidates.add(ex.subs(var, i))
                        else:
                            candidates.add(ex)
                    except: pass
                elif isinstance(s, sp.ConditionSet):
                    try:
                        expr_cond = s.condition.lhs - s.condition.rhs if isinstance(s.condition, sp.Eq) else s.condition
                        for guess in[i/2.0 for i in range(-30, 31)]:
                            try:
                                root = sp.nsolve(expr_cond, self.x, guess)
                                candidates.add(root) 
                            except: pass
                    except: pass
                elif hasattr(s, 'args'):
                    for arg in s.args: extract_candidates(arg)
                    
            extract_candidates(excluded)
            if hasattr(domain, 'boundary'): extract_candidates(domain.boundary)
            
            valid_vas = set()
            for c in candidates:
                try:
                    if c.has(sp.oo, -sp.oo, sp.zoo, sp.nan): continue
                    
                    is_asym = False
                    try:
                        val1 = abs(complex(expr.subs(self.x, c - 1e-5).evalf()))
                        val2 = abs(complex(expr.subs(self.x, c + 1e-5).evalf()))
                        if val1 > 1000 or val2 > 1000:
                            is_asym = True
                    except: pass
                    
                    if not is_asym:
                        try:
                            lim_right = sp.limit(expr, self.x, c, dir='+')
                            if getattr(lim_right, 'is_infinite', False) or lim_right.has(sp.oo, -sp.oo, sp.zoo):
                                is_asym = True
                            else:
                                lim_left = sp.limit(expr, self.x, c, dir='-')
                                if getattr(lim_left, 'is_infinite', False) or lim_left.has(sp.oo, -sp.oo, sp.zoo):
                                    is_asym = True
                        except: pass
                                
                    if is_asym:
                        valid_vas.add(sp.simplify(c))
                except: pass
                
            image_sets =[]
            def get_imagesets(s):
                if isinstance(s, sp.ImageSet): image_sets.append(s)
                elif hasattr(s, 'args'):
                    for arg in s.args: get_imagesets(arg)
            get_imagesets(excluded)
            
            for iset in image_sets:
                try:
                    lam = iset.lamda if hasattr(iset, 'lamda') else iset.args[0]
                    if hasattr(lam, 'variables'):
                        sample = lam.expr.subs(lam.variables[0], 0)
                    else:
                        fv = list(lam.free_symbols)
                        sample = lam.subs(fv[0], 0) if fv else lam
                    
                    is_asym = False
                    try:
                        val1 = abs(complex(expr.subs(self.x, sample - 1e-5).evalf()))
                        val2 = abs(complex(expr.subs(self.x, sample + 1e-5).evalf()))
                        if val1 > 1000 or val2 > 1000:
                            is_asym = True
                    except: pass
                    
                    if not is_asym:
                        try:
                            lim_right = sp.limit(expr, self.x, sample, dir='+')
                            if getattr(lim_right, 'is_infinite', False) or lim_right.has(sp.oo, -sp.oo, sp.zoo):
                                is_asym = True
                        except: pass
                            
                    if is_asym:
                        valid_vas.add(iset)
                except Exception as e: pass

            final_vas =[]
            imageset_vas =[v for v in valid_vas if isinstance(v, sp.ImageSet)]
            final_vas.extend(imageset_vas)
            
            for v in valid_vas:
                if not isinstance(v, sp.ImageSet):
                    covered = False
                    for iset in imageset_vas:
                        try:
                            if iset.contains(v) == True: covered = True
                        except: pass
                    if not covered: final_vas.append(v)
            
            asymptotes['vertical'] = final_vas
        except Exception as e:
            self._log(f"Vertical asymptote failed: {e}")

        return asymptotes

    def get_parity(self, expr):
        self._log("Calculating Parity...")
        try:
            f_neg_x = sp.simplify(expr.subs(self.x, -self.x))
            f_pos_x = sp.simplify(expr)
            if sp.simplify(f_neg_x - f_pos_x) == 0: return "Even"
            elif sp.simplify(f_neg_x + f_pos_x) == 0: return "Odd"
        except Exception: pass
        return "Neither even nor odd"

    def get_periodicity(self, expr):
        try: return periodicity(expr, self.x)
        except Exception: return None

    def get_monotonicity(self, expr, domain):
        self._log("Calculating Monotonicity...")
        intervals = {'increasing':[], 'decreasing':[], 'oscillates_infinitely': False}
        
        try:
            f_prime = sp.diff(expr, self.x)
            crit_pts = self.safe_solveset(f_prime)
            n, d = sp.fraction(sp.cancel(f_prime))
            undef_pts = self.safe_solveset(d)
            disc_pts_set = sp.Complement(sp.Reals, domain)
            all_cands = sp.Union(crit_pts, undef_pts, disc_pts_set)
            
            has_inf_breaks = False
            def check_inf(s):
                nonlocal has_inf_breaks
                if isinstance(s, sp.ImageSet): has_inf_breaks = True
                elif isinstance(s, sp.ConditionSet):
                    if s.has(sp.sin, sp.cos, sp.tan, sp.sec, sp.csc, sp.cot): has_inf_breaks = True
                elif hasattr(s, 'args'):
                    for arg in s.args: check_inf(arg)
            check_inf(all_cands)
            intervals['oscillates_infinitely'] = has_inf_breaks

            break_points = set()
            def add_pts(s):
                if isinstance(s, sp.FiniteSet):
                    for p in s:
                        if p.is_real is not False and not p.has(sp.I): break_points.add(p)
                elif isinstance(s, sp.ImageSet):
                    try:
                        lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                        if hasattr(lam, 'variables'):
                            var = lam.variables[0]
                            ex = lam.expr
                        else:
                            fv = list(lam.free_symbols)
                            var = fv[0] if fv else None
                            ex = lam
                        
                        if var is not None:
                            for i in range(-5, 6): break_points.add(ex.subs(var, i))
                        else:
                            break_points.add(ex)
                    except: pass
                elif isinstance(s, sp.ConditionSet):
                    try:
                        expr_cond = s.condition.lhs - s.condition.rhs if isinstance(s.condition, sp.Eq) else s.condition
                        for guess in[i/2.0 for i in range(-30, 31)]:
                            try:
                                root = sp.nsolve(expr_cond, self.x, guess)
                                break_points.add(root)
                            except: pass
                    except: pass
                elif hasattr(s, 'args'):
                    for arg in s.args: add_pts(arg)

            add_pts(all_cands)
            
            for arg in expr.atoms(sp.Abs):
                s = self.safe_solveset(arg.args[0])
                if isinstance(s, sp.FiniteSet):
                    for p in s: break_points.add(p)
            
            if isinstance(domain, sp.Interval):
                if domain.start != -sp.oo: break_points.add(domain.start)
                if domain.end != sp.oo: break_points.add(domain.end)
            elif isinstance(domain, sp.Union):
                for arg in domain.args:
                    if isinstance(arg, sp.Interval):
                        if arg.start != -sp.oo: break_points.add(arg.start)
                        if arg.end != sp.oo: break_points.add(arg.end)

            real_breaks_raw =[]
            for p in break_points:
                try:
                    if p.is_real is not False and not p.has(sp.I, sp.oo, -sp.oo):
                        real_breaks_raw.append(float(p.evalf()))
                except: pass
                
            real_breaks_unique =[]
            for val in real_breaks_raw:
                if not any(abs(val - v) < 1e-3 for v in real_breaks_unique):
                    real_breaks_unique.append(val)
            
            real_breaks = sorted(real_breaks_unique)
            boundaries =[-sp.oo] + real_breaks +[sp.oo]
            
            for i in range(len(boundaries) - 1):
                start = boundaries[i]
                end = boundaries[i+1]
                if start == end: continue
                
                if has_inf_breaks and (start == -sp.oo or end == sp.oo): continue
                
                if start == -sp.oo and end == sp.oo: mid = 0; q1 = -10; q2 = 10
                elif start == -sp.oo: mid = end - 1; q1 = end - 10; q2 = end - 0.1
                elif end == sp.oo: mid = start + 1; q1 = start + 0.1; q2 = start + 10
                else:
                    mid = (start + end) / 2
                    span = end - start
                    q1 = start + span * 0.25; q2 = start + span * 0.75
                    
                try:
                    if domain.contains(mid) == sp.false or domain.contains(q1) == sp.false or domain.contains(q2) == sp.false: continue
                    val = f_prime.subs(self.x, mid).evalf()
                    
                    exact_start = "-oo" if start == -sp.oo else start
                    exact_end = "oo" if end == sp.oo else end
                    
                    if start != -sp.oo:
                        for p in break_points:
                            try:
                                if abs(float(p.evalf()) - start) < 1e-5: exact_start = sp.simplify(p)
                            except: pass
                            
                    if end != sp.oo:
                        for p in break_points:
                            try:
                                if abs(float(p.evalf()) - end) < 1e-5: exact_end = sp.simplify(p)
                            except: pass
                    
                    if val > 1e-9: intervals['increasing'].append((exact_start, exact_end))
                    elif val < -1e-9: intervals['decreasing'].append((exact_start, exact_end))
                except: pass

        except Exception as e:
            self._log(f"Monotonicity calculation failed: {e}")

        return intervals

    def analyze(self, func_string):
        print(f"\n{'='*50}")
        print(f"[{func_string}] Analysis Starting...")
        print(f"{'='*50}")
        
        start_time = time.time()
        func_string = func_string.replace('^', '**')
        func_string = func_string.replace('e**', 'E**').replace('e^', 'E**')
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
        monotonicity = self.get_monotonicity(expr, domain)
        
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
        print(f"Function:       f(x) = {res['Function']}")
        print(f"Domain:         {res['Domain']}")
        
        # 🔑 CLEAN SET UPGRADE: Neatly formats SymPy Sets into clear general logic
        def clean_set(s):
            if isinstance(s, sp.ImageSet):
                try:
                    lam = s.lamda if hasattr(s, 'lamda') else s.args[0]
                    expr = lam.expr if hasattr(lam, 'expr') else lam
                    var = lam.variables[0] if hasattr(lam, 'variables') else list(lam.free_symbols)[0]
                    return f"{expr}".replace('_n', 'n') + f" (for integer n)"
                except: return str(s).replace('_n', 'n')
            elif isinstance(s, sp.Union):
                return " U ".join([clean_set(arg) for arg in s.args])
            elif isinstance(s, sp.Complement):
                return f"[{clean_set(s.args[0])}] excluding {s.args[1]}"
            return str(s).replace('_n', 'n')

        x_ints_raw = res['Intercepts']['x']
        if not x_ints_raw:
            x_ints = "None"
        else:
            x_ints = ", ".join([clean_set(x) if isinstance(x, (sp.ImageSet, sp.Union, sp.Complement)) else str(x).replace('_n', 'n') for x in x_ints_raw])
            
        print(f"X-Intercepts:   {x_ints}")
        print(f"Y-Intercept:    {res['Intercepts']['y']}")
        
        period = res['Periodicity']
        
        def format_extrema(pts, period):
            if not pts: return "None"
            if period is None:
                sorted_by_abs = sorted(pts, key=lambda p: abs(float(p[0].evalf())) if getattr(p[0], 'evalf', None) else float('inf'))
                if len(pts) > 6:
                    closest = sorted_by_abs[:6]
                    # 🔑 LEFT-TO-RIGHT FIX: Re-sort sequentially for beautiful natural display
                    closest = sorted(closest, key=lambda p: float(p[0].evalf()) if getattr(p[0], 'evalf', None) else float('inf'))
                    formatted = ", ".join([f"({sp.simplify(x)}, {sp.simplify(y)})" for x,y in closest])
                    return f"{formatted} ... (and infinitely many more)"
                
                closest = sorted(pts, key=lambda p: float(p[0].evalf()) if getattr(p[0], 'evalf', None) else float('inf'))
                return ", ".join([f"({sp.simplify(x)}, {sp.simplify(y)})" for x,y in closest])
            
            base_pts = []
            seen_mod =[]
            pts = sorted(pts, key=lambda p: abs(float(p[0].evalf())) if getattr(p[0], 'evalf', None) else float('inf'))
            for x, y in pts:
                try:
                    x_f = float(x.evalf())
                    p_f = float(period.evalf())
                    mod_val = x_f % p_f
                    if not any(abs(mod_val - sm) < 1e-3 or abs(mod_val - sm - p_f) < 1e-3 or abs(mod_val - sm + p_f) < 1e-3 for sm in seen_mod):
                        seen_mod.append(mod_val)
                        base_pts.append((x, y))
                except:
                    base_pts.append((x, y))
            res_str = ", ".join([f"({sp.simplify(x)} + n*{period}, {y})" for x, y in base_pts])
            return res_str + " (for integer n)"

        minima = format_extrema(res['Extrema']['minima'], period)
        maxima = format_extrema(res['Extrema']['maxima'], period)
        infs = format_extrema(res['Inflection Points'], period)

        print(f"Minima:         {minima}")
        print(f"Maxima:         {maxima}")
        print(f"Inflection pts: {infs}")
        
        vert_formatted =[]
        for v in res['Asymptotes']['vertical']:
            if isinstance(v, (sp.ImageSet, sp.Union, sp.Complement)):
                vert_formatted.append(f"x = {clean_set(v)}")
            else:
                vert_formatted.append(f"x = {v}")
                
        vert = ", ".join(vert_formatted)
        horz = ", ".join(map(lambda h: f"y = {str(h)}", res['Asymptotes']['horizontal']))
        oblq = ", ".join(map(lambda o: f"y = {str(o)}", res['Asymptotes']['oblique']))
        print(f"Vertical Asym:  {vert if vert else 'The function does not have any vertical asymptotes.'}")
        print(f"Horizontal Asym:{horz if horz else 'The function does not have any horizontal asymptotes.'}")
        print(f"Oblique Asym:   {oblq if oblq else 'The function does not have any oblique asymptotes.'}")
        
        print(f"Parity:         {res['Parity']}")
        print(f"Periodicity:    {res['Periodicity']}")
        
        print("Monotonicity:")
        if not res['Monotonicity']['increasing'] and not res['Monotonicity']['decreasing']:
            print("  None or could not be determined.")
        else:
            def print_intervals(intervals, period, label):
                if not intervals: return
                if period is None:
                    sorted_by_abs = sorted(intervals, key=lambda i: abs(float(i[0].evalf())) if getattr(i[0], 'evalf', None) and i[0] not in ['-oo', 'oo'] else float('inf'))
                    if len(intervals) > 6:
                        closest = sorted_by_abs[:6]
                        # 🔑 LEFT-TO-RIGHT FIX: Re-sort sequentially for logical display
                        closest = sorted(closest, key=lambda i: float(i[0].evalf()) if getattr(i[0], 'evalf', None) and i[0] not in ['-oo', 'oo'] else (-float('inf') if i[0] == '-oo' else float('inf')))
                        for inc in closest:
                            print(f"  ({inc[0]}, {inc[1]})\t{label}")
                        print(f"  ... (and infinitely many more {label.lower()} intervals)")
                    else:
                        closest = sorted(intervals, key=lambda i: float(i[0].evalf()) if getattr(i[0], 'evalf', None) and i[0] not in ['-oo', 'oo'] else (-float('inf') if i[0] == '-oo' else float('inf')))
                        for inc in closest:
                            print(f"  ({inc[0]}, {inc[1]})\t{label}")
                    return
                
                base_ints = []
                seen_mod = []
                sorted_ints =[]
                for s, e in intervals:
                    try:
                        val = 0 if s == '-oo' else float(s.evalf())
                        sorted_ints.append( (abs(val), s, e) )
                    except:
                        sorted_ints.append( (float('inf'), s, e) )
                sorted_ints.sort(key=lambda x: x[0])
                
                for _, s, e in sorted_ints:
                    try:
                        if s == '-oo' or e == 'oo':
                            base_ints.append((s, e))
                            continue
                        s_f = float(s.evalf())
                        p_f = float(period.evalf())
                        mod_val = s_f % p_f
                        if not any(abs(mod_val - sm) < 1e-3 or abs(mod_val - sm - p_f) < 1e-3 or abs(mod_val - sm + p_f) < 1e-3 for sm in seen_mod):
                            seen_mod.append(mod_val)
                            base_ints.append((s, e))
                    except:
                        base_ints.append((s, e))
                        
                for s, e in base_ints:
                    start_str = f"{sp.simplify(s)} + n*{period}" if s not in ['-oo', 'oo'] else str(s)
                    end_str = f"{sp.simplify(e)} + n*{period}" if e not in ['-oo', 'oo'] else str(e)
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
    
    for f_str in test_functions:
        engine.analyze(f_str)