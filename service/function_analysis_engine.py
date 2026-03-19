import sympy as sp
import time
from sympy.calculus.util import continuous_domain, periodicity
from sympy.sets import Reals, Complement, Union, Interval, FiniteSet, EmptySet, ImageSet, ConditionSet

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

    def safe_solveset(self, expr, domain=Reals):
        try:
            sol = sp.solveset(expr, self.x, domain=domain)
            return sol
        except Exception as e:
            self._log(f"Error solving {expr}: {e}")
            return EmptySet

    def _extract_points(self, point_set, domain, expr_ref=None):
        """Intelligently pulls a finite sample of evaluation points from complex analytical sets."""
        points = set()
        
        def process_set(s):
            if isinstance(s, FiniteSet):
                for p in s:
                    if p.is_real is not False and not p.has(sp.I):
                        points.add(p)
            elif isinstance(s, ImageSet):
                try:
                    # Snag representative points near origin for periodic sets
                    intersected = sp.Intersection(s, sp.Interval(-3*sp.pi, 3*sp.pi))
                    if isinstance(intersected, FiniteSet):
                        for p in intersected:
                            points.add(p)
                except: pass
            elif isinstance(s, Union):
                for arg in s.args:
                    process_set(arg)
            elif isinstance(s, ConditionSet):
                # Fallback: Numerical Grid Search for transcendental equations (like x = tan(x))
                try:
                    expr_cond = s.condition.lhs - s.condition.rhs if isinstance(s.condition, sp.Eq) else s.condition
                    for guess in range(-15, 16, 3):
                        try:
                            root = sp.nsolve(expr_cond, self.x, guess)
                            points.add(sp.Float(round(root, 4)))
                        except: pass
                except: pass

        process_set(point_set)
        
        valid_points =[]
        for p in points:
            try:
                if domain.contains(p) is not sp.false:
                    valid_points.append(p)
                else:
                    # Include removable singularities for extrema analysis (e.g. Sinc function at 0)
                    if expr_ref is not None:
                        limit_val = sp.limit(expr_ref, self.x, p)
                        if limit_val.is_real and not limit_val.has(sp.oo, -sp.oo, sp.nan, sp.zoo):
                            valid_points.append(p)
            except: pass
                
        # Deduplicate float proximities
        unique_points = {}
        for p in valid_points:
            val = float(p.evalf())
            found = False
            for k in unique_points.keys():
                if abs(k - val) < 1e-5:
                    found = True
                    break
            if not found:
                unique_points[val] = p
                
        return sorted(list(unique_points.values()), key=lambda p: float(p.evalf()))

    def get_domain(self, expr):
        self._log("Calculating Domain...")
        try:
            return continuous_domain(expr, self.x, Reals)
        except Exception as e:
            self._log(f"Domain calculation failed: {e}")
            return Reals

    def get_intercepts(self, expr, domain):
        self._log("Calculating Intercepts...")
        intercepts = {'x':[], 'y': None}

        try:
            if domain.contains(0) is not sp.false:
                y_val = expr.subs(self.x, 0)
                if not y_val.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I):
                    intercepts['y'] = sp.simplify(y_val)
        except Exception: pass

        try:
            x_sols = self.safe_solveset(expr)
            if not isinstance(x_sols, EmptySet.__class__):
                if isinstance(x_sols, FiniteSet):
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
            
            # Candidates: f' = 0
            crit_pts_zero = self.safe_solveset(f_prime)
            
            # Candidates: f' undefined
            n, d = sp.fraction(sp.cancel(f_prime))
            crit_pts_undef = self.safe_solveset(d)
            
            # Candidates: Non-differentiable sharp corners (e.g., inside absolute values)
            abs_pts = sp.EmptySet
            for arg in expr.atoms(sp.Abs):
                abs_pts = sp.Union(abs_pts, self.safe_solveset(arg.args[0]))
                
            all_crit = sp.Union(crit_pts_zero, crit_pts_undef, abs_pts)
            
            # Candidates: Domain Boundaries
            if isinstance(domain, Interval):
                if domain.start != -sp.oo: all_crit = sp.Union(all_crit, FiniteSet(domain.start))
                if domain.end != sp.oo: all_crit = sp.Union(all_crit, FiniteSet(domain.end))
            elif isinstance(domain, Union):
                for arg in domain.args:
                    if isinstance(arg, Interval):
                        if arg.start != -sp.oo: all_crit = sp.Union(all_crit, FiniteSet(arg.start))
                        if arg.end != sp.oo: all_crit = sp.Union(all_crit, FiniteSet(arg.end))

            eval_points = self._extract_points(all_crit, domain, expr)
            
            for cp in eval_points:
                eps = 1e-5
                left_val, right_val = None, None
                
                # First derivative left-hand evaluation
                try:
                    if domain.contains(cp - eps) is not sp.false:
                        lv = f_prime.subs(self.x, cp - eps).evalf()
                        if abs(lv) > 1e-9: left_val = lv
                except: pass
                
                # First derivative right-hand evaluation
                try:
                    if domain.contains(cp + eps) is not sp.false:
                        rv = f_prime.subs(self.x, cp + eps).evalf()
                        if abs(rv) > 1e-9: right_val = rv
                except: pass
                
                try:
                    y_val = expr.subs(self.x, cp)
                    if y_val.has(sp.nan, sp.zoo):
                        y_val = sp.limit(expr, self.x, cp) # Removable singularity resolution
                    y_val = sp.simplify(y_val)
                except: continue
                    
                # Standard Classification
                if left_val is not None and right_val is not None:
                    if left_val < 0 and right_val > 0: extrema['minima'].append((sp.simplify(cp), y_val))
                    elif left_val > 0 and right_val < 0: extrema['maxima'].append((sp.simplify(cp), y_val))
                # Boundary Extremes Classification
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
            eval_points = self._extract_points(all_cands, domain, expr)
            
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
                        
                    if left_val is not None and right_val is not None:
                        if left_val * right_val < 0:
                            y_val = expr.subs(self.x, cp)
                            if y_val.has(sp.nan, sp.zoo):
                                y_val = sp.limit(expr, self.x, cp)
                            inflections.append((sp.simplify(cp), sp.simplify(y_val)))
                except: pass
        except Exception as e:
            self._log(f"Inflection points calculation failed: {e}")
            
        return inflections

    def get_asymptotes(self, expr, domain):
        self._log("Calculating Asymptotes...")
        asymptotes = {'vertical': [], 'horizontal': [], 'oblique':[]}

        for d in [sp.oo, -sp.oo]:
            try:
                L = sp.limit(expr, self.x, d)
                # Ensure we bypass Oscillating accumulation bounds (e.g. sine limits to infinity)
                if L.is_real is not False and not L.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I) and not isinstance(L, sp.AccumBounds):
                    val = sp.simplify(L)
                    if val not in asymptotes['horizontal']:
                        asymptotes['horizontal'].append(val)
            except: pass

        for d in[sp.oo, -sp.oo]:
            try:
                m = sp.limit(expr / self.x, self.x, d)
                if m.is_real is not False and not m.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I) and not isinstance(m, sp.AccumBounds) and m != 0:
                    c = sp.limit(expr - m * self.x, self.x, d)
                    if c.is_real is not False and not c.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I) and not isinstance(c, sp.AccumBounds):
                        line = sp.simplify(m * self.x + c)
                        if line not in asymptotes['oblique']:
                            asymptotes['oblique'].append(line)
            except: pass

        # Vertical
        try:
            excluded = sp.Complement(sp.Reals, domain)
            candidates = set()
            
            def extract_candidates(s):
                if isinstance(s, FiniteSet):
                    for p in s: candidates.add(p)
                elif isinstance(s, Interval):
                    candidates.add(s.start)
                    candidates.add(s.end)
                elif isinstance(s, Union):
                    for arg in s.args: extract_candidates(arg)
                    
            extract_candidates(excluded)
            extract_candidates(domain.boundary) # Captures isolated boundaries like x=0 for ln(x)
            
            valid_vas = set()
            for c in candidates:
                if c.has(sp.oo, -sp.oo, sp.zoo, sp.nan): continue
                lim_right = sp.limit(expr, self.x, c, dir='+')
                lim_left = sp.limit(expr, self.x, c, dir='-')
                if sp.oo in (lim_right, -lim_right) or sp.oo in (lim_left, -lim_left):
                    valid_vas.add(sp.simplify(c))
                    
            if isinstance(excluded, Union):
                for arg in excluded.args:
                    if isinstance(arg, ImageSet): valid_vas.add(arg)
            elif isinstance(excluded, ImageSet):
                valid_vas.add(excluded)

            asymptotes['vertical'] = list(valid_vas)
        except Exception as e:
            self._log(f"Vertical asymptote failed: {e}")

        return asymptotes

    def get_parity(self, expr):
        self._log("Calculating Parity...")
        try:
            f_neg_x = sp.simplify(expr.subs(self.x, -self.x))
            f_pos_x = sp.simplify(expr)
            if sp.simplify(f_neg_x - f_pos_x) == 0:
                return "Even"
            elif sp.simplify(f_neg_x + f_pos_x) == 0:
                return "Odd"
        except Exception: pass
        return "Neither even nor odd"

    def get_periodicity(self, expr):
        self._log("Calculating Periodicity...")
        try:
            return periodicity(expr, self.x)
        except Exception:
            return None

    def get_monotonicity(self, expr, domain):
        self._log("Calculating Monotonicity...")
        intervals = {'increasing': [], 'decreasing':[], 'oscillates_infinitely': False}
        
        try:
            f_prime = sp.diff(expr, self.x)
            
            crit_pts = self.safe_solveset(f_prime)
            n, d = sp.fraction(sp.cancel(f_prime))
            undef_pts = self.safe_solveset(d)
            
            abs_pts = sp.EmptySet
            for arg in expr.atoms(sp.Abs):
                abs_pts = sp.Union(abs_pts, self.safe_solveset(arg.args[0]))
                
            disc_pts_set = sp.Complement(sp.Reals, domain)
            all_cands = sp.Union(crit_pts, undef_pts, abs_pts, disc_pts_set)
            
            # Identify if roots propagate infinitely
            has_inf_breaks = False
            def check_inf(s):
                nonlocal has_inf_breaks
                if isinstance(s, (ImageSet, ConditionSet)): has_inf_breaks = True
                elif hasattr(s, 'args'):
                    for arg in s.args: check_inf(arg)
            check_inf(all_cands)
            intervals['oscillates_infinitely'] = has_inf_breaks

            # Compile standard bounds into continuous segments
            break_points = set()
            def add_pts(s):
                if isinstance(s, FiniteSet):
                    for p in s:
                        if p.is_real is not False and not p.has(sp.I):
                            break_points.add(p)
                elif isinstance(s, ImageSet):
                    try:
                        intersected = sp.Intersection(s, sp.Interval(-3*sp.pi, 3*sp.pi))
                        if isinstance(intersected, FiniteSet):
                            for p in intersected: break_points.add(p)
                    except: pass
                elif isinstance(s, Union):
                    for arg in s.args: add_pts(arg)
                elif isinstance(s, ConditionSet):
                    try:
                        expr_cond = s.condition.lhs - s.condition.rhs if isinstance(s.condition, sp.Eq) else s.condition
                        for guess in range(-15, 16, 3):
                            try:
                                root = sp.nsolve(expr_cond, self.x, guess)
                                break_points.add(sp.Float(round(root, 4)))
                            except: pass
                    except: pass

            add_pts(all_cands)
            
            if isinstance(domain, Interval):
                if domain.start != -sp.oo: break_points.add(domain.start)
                if domain.end != sp.oo: break_points.add(domain.end)
            elif isinstance(domain, Union):
                for arg in domain.args:
                    if isinstance(arg, Interval):
                        if arg.start != -sp.oo: break_points.add(arg.start)
                        if arg.end != sp.oo: break_points.add(arg.end)

            real_breaks =[]
            for p in break_points:
                try:
                    if p.is_real is not False and not p.has(sp.I, sp.oo, -sp.oo):
                        real_breaks.append(float(p.evalf()))
                except: pass
                
            real_breaks = sorted(list(set(real_breaks)))
            boundaries = [-sp.oo] + real_breaks + [sp.oo]
            
            for i in range(len(boundaries) - 1):
                start = boundaries[i]
                end = boundaries[i+1]
                if start == end: continue
                
                # Protect infinitely propagating behaviors from registering unboundedly false intervals
                if has_inf_breaks and (start == -sp.oo or end == sp.oo):
                    continue
                
                if start == -sp.oo and end == sp.oo:
                    mid = 0; q1 = -10; q2 = 10
                elif start == -sp.oo:
                    mid = end - 1; q1 = end - 10; q2 = end - 0.1
                elif end == sp.oo:
                    mid = start + 1; q1 = start + 0.1; q2 = start + 10
                else:
                    mid = (start + end) / 2
                    span = end - start
                    q1 = start + span * 0.25
                    q2 = start + span * 0.75
                    
                try:
                    # Light verification that internal sub-segment stays uniformly in bounds
                    if domain.contains(mid) == sp.false or domain.contains(q1) == sp.false or domain.contains(q2) == sp.false:
                        continue
                        
                    val = f_prime.subs(self.x, mid).evalf()
                    
                    exact_start, exact_end = start, end
                    for p in break_points:
                        try:
                            if abs(float(p.evalf()) - start) < 1e-7: exact_start = p
                            if abs(float(p.evalf()) - end) < 1e-7: exact_end = p
                        except: pass
                        
                    if exact_start == -sp.oo: exact_start = "-oo"
                    if exact_end == sp.oo: exact_end = "oo"
                    
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
        
        symbols =[s for s in expr.free_symbols if s.name == 'x']
        self.x = symbols[0] if symbols else sp.Symbol('x', real=True)
            
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
        
        x_ints = ", ".join(map(str, res['Intercepts']['x'])) if res['Intercepts']['x'] else "None"
        print(f"X-Intercepts:   {x_ints}")
        print(f"Y-Intercept:    {res['Intercepts']['y']}")
        
        minima = ", ".join([f"({x}, {y})" for x,y in res['Extrema']['minima']])
        maxima = ", ".join([f"({x}, {y})" for x,y in res['Extrema']['maxima']])
        print(f"Minima:         {minima if minima else 'None'}")
        print(f"Maxima:         {maxima if maxima else 'None'}")
        
        infs = ", ".join([f"({x}, {y})" for x,y in res['Inflection Points']])
        print(f"Inflection pts: {infs if infs else 'None'}")
        
        # Asymptote Formatter (clean nested lambdas out of view)
        vert_formatted = []
        for v in res['Asymptotes']['vertical']:
            if isinstance(v, sp.ImageSet):
                vert_formatted.append(f"x = {v.lamda.expr} (for integer {v.lamda.variables[0]})")
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
            for inc in res['Monotonicity']['increasing']: print(f"  ({inc[0]}, {inc[1]})\tIncreasing")
            for dec in res['Monotonicity']['decreasing']: print(f"  ({dec[0]}, {dec[1]})\tDecreasing")
            if res['Monotonicity'].get('oscillates_infinitely', False):
                print("  ... (intervals repeat or oscillate infinitely)")
        
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