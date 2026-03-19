import sympy as sp
import time
from functools import wraps
from sympy.calculus.util import continuous_domain, periodicity
from sympy.sets import Reals, Complement, Union, Interval, FiniteSet, EmptySet
from sympy.core.numbers import Infinity, NegativeInfinity

# Optional: Try importing utilities from your existing algo or power_series engines
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
        """Attempts to safely solve an equation, falling back or filtering bad results."""
        try:
            sol = sp.solveset(expr, self.x, domain=domain)
            if isinstance(sol, sp.ConditionSet):
                self._log(f"Warning: solveset returned ConditionSet for {expr}. Only numerical roots might be available.")
                return EmptySet
            return sol
        except Exception as e:
            self._log(f"Error solving {expr}: {e}")
            return EmptySet

    def get_domain(self, expr):
        self._log("Calculating Domain...")
        try:
            dom = continuous_domain(expr, self.x, Reals)
            return dom
        except Exception as e:
            self._log(f"Domain calculation failed: {e}")
            return Reals

    def get_intercepts(self, expr, domain):
        self._log("Calculating Intercepts...")
        intercepts = {'x': [], 'y': None}

        # Y-intercept
        try:
            if domain.contains(0) is not sp.false:
                y_val = expr.subs(self.x, 0)
                if not y_val.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I):
                    intercepts['y'] = sp.simplify(y_val)
        except Exception as e:
            self._log(f"Y-intercept failed: {e}")

        # X-intercepts
        try:
            x_sols = self.safe_solveset(expr)
            if not isinstance(x_sols, (EmptySet.__class__)):
                if isinstance(x_sols, FiniteSet):
                    # If is_real is None, it means SymPy isn't sure, but typically real solutions won't have 'I'
                    clean_xs = [sp.simplify(sol) for sol in x_sols if sol.is_real is not False and not sol.has(sp.I) and domain.contains(sol) is not sp.false]
                    intercepts['x'] = list(set(clean_xs))  # unique
                else:
                    intercepts['x'] = [x_sols] # Store the general analytic set
        except Exception as e:
            self._log(f"X-intercept failed: {e}")

        return intercepts

    def get_extrema(self, expr, domain):
        self._log("Calculating Extrema (Maxima/Minima)...")
        extrema = {'minima': [], 'maxima': []}
        
        def get_principal_points(point_set):
            if isinstance(point_set, FiniteSet):
                return [p for p in point_set if p.is_real is not False and not p.has(sp.I)]
            try:
                # Intersect with a principal domain down to get sample points
                intersected = sp.Intersection(point_set, sp.Interval(-2*sp.pi, 2*sp.pi))
                if isinstance(intersected, FiniteSet):
                    return [p for p in intersected]
            except:
                pass
            return []

        try:
            f_prime = sp.diff(expr, self.x)
            f_double_prime = sp.diff(f_prime, self.x)

            # Find critical points (f' = 0 or f' undefined)
            crit_pts_zero = self.safe_solveset(f_prime)
            # Find points where f' is undefined by finding denominator roots if it's a fraction
            n, d = sp.fraction(sp.cancel(f_prime))
            crit_pts_undef = self.safe_solveset(d)
            
            all_crit = sp.Union(crit_pts_zero, crit_pts_undef)
            
            eval_points = get_principal_points(all_crit)
            for cp in eval_points:
                if domain.contains(cp) is not sp.false:
                        # Use second derivative test
                        f2_val = f_double_prime.subs(self.x, cp)
                        y_val = sp.simplify(expr.subs(self.x, cp))
                        
                        if f2_val.is_positive:
                            extrema['minima'].append((sp.simplify(cp), y_val))
                        elif f2_val.is_negative:
                            extrema['maxima'].append((sp.simplify(cp), y_val))
                        else:
                            # Higher order or first derivative test needed (simplified fallback)
                            # Checking slightly left and right
                            try:
                                left_val = f_prime.subs(self.x, cp - 1e-5).evalf()
                                right_val = f_prime.subs(self.x, cp + 1e-5).evalf()
                                if left_val < 0 < right_val:
                                    extrema['minima'].append((sp.simplify(cp), y_val))
                                elif left_val > 0 > right_val:
                                    extrema['maxima'].append((sp.simplify(cp), y_val))
                            except Exception:
                                pass
        except Exception as e:
            self._log(f"Extrema calculation failed: {e}")

        return extrema

    def get_inflection_points(self, expr, domain):
        self._log("Calculating Inflection Points...")
        inflections = []
        def get_principal_points(point_set):
            if isinstance(point_set, FiniteSet):
                return [p for p in point_set if p.is_real is not False and not p.has(sp.I)]
            try:
                intersected = sp.Intersection(point_set, sp.Interval(-2*sp.pi, 2*sp.pi))
                if isinstance(intersected, FiniteSet):
                    return [p for p in intersected]
            except:
                pass
            return []

        try:
            f_prime = sp.diff(expr, self.x)
            f_double_prime = sp.diff(f_prime, self.x)
            
            candidates = self.safe_solveset(f_double_prime)
            eval_points = get_principal_points(candidates)
            for cp in eval_points:
                if domain.contains(cp) is not sp.false:
                        # Verify sign change
                        left_val = f_double_prime.subs(self.x, cp - 1e-4)
                        right_val = f_double_prime.subs(self.x, cp + 1e-4)
                        try:
                            if left_val * right_val < 0: # Sign changed
                                y_val = sp.simplify(expr.subs(self.x, cp))
                                inflections.append((sp.simplify(cp), y_val))
                        except TypeError:
                            pass
        except Exception as e:
            self._log(f"Inflection points calculation failed: {e}")
            
        return inflections

    def get_asymptotes(self, expr, domain):
        self._log("Calculating Asymptotes...")
        asymptotes = {'vertical': [], 'horizontal': [], 'oblique': []}

        # Horizontal
        try:
            lim_inf = sp.limit(expr, self.x, sp.oo)
            lim_ninf = sp.limit(expr, self.x, -sp.oo)
            if lim_inf.is_real is not False and not lim_inf.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I): asymptotes['horizontal'].append(sp.simplify(lim_inf))
            if lim_ninf.is_real is not False and not lim_ninf.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I) and lim_ninf != lim_inf: asymptotes['horizontal'].append(sp.simplify(lim_ninf))
        except Exception as e:
             self._log(f"Horizontal asymptote failed: {e}")

        # Oblique
        try:
            for inf_dir in [sp.oo, -sp.oo]:
                m = sp.limit(expr / self.x, self.x, inf_dir)
                if m.is_real is not False and not m.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I) and m != 0:
                    c = sp.limit(expr - m * self.x, self.x, inf_dir)
                    if c.is_real is not False and not c.has(sp.oo, -sp.oo, sp.zoo, sp.nan, sp.I):
                        line = sp.simplify(m * self.x + c)
                        if line not in asymptotes['oblique']:
                            asymptotes['oblique'].append(line)
        except Exception as e:
             self._log(f"Oblique asymptote failed: {e}")

        # Vertical
        try:
            # Look at domain boundaries and roots of denominator
            n, d = sp.fraction(sp.cancel(expr))
            if d != 1:
                denom_roots = self.safe_solveset(d)
                
                def get_principal_points(point_set):
                    if isinstance(point_set, FiniteSet):
                        return [p for p in point_set if p.is_real is not False and not p.has(sp.I)]
                    try:
                        intersected = sp.Intersection(point_set, sp.Interval(-2*sp.pi, 2*sp.pi))
                        if isinstance(intersected, FiniteSet):
                            return [p for p in intersected]
                    except:
                        pass
                    return []
                    
                for root in get_principal_points(denom_roots):
                    lim_right = sp.limit(expr, self.x, root, dir='+')
                    lim_left = sp.limit(expr, self.x, root, dir='-')
                    if sp.oo in (lim_right, -lim_right) or sp.oo in (lim_left, -lim_left):
                        asymptotes['vertical'].append(sp.simplify(root))
        except Exception as e:
             self._log(f"Vertical asymptote failed: {e}")

        return asymptotes

    def get_parity(self, expr):
        self._log("Calculating Parity...")
        try:
            f_neg_x = sp.simplify(expr.subs(self.x, -self.x))
            if f_neg_x == expr:
                return "Even"
            elif f_neg_x == -expr:
                return "Odd"
        except Exception:
            pass
        return "Neither even nor odd"

    def get_periodicity(self, expr):
        self._log("Calculating Periodicity...")
        try:
            period = periodicity(expr, self.x)
            return period
        except Exception:
            return None

    def get_monotonicity(self, expr, domain):
        self._log("Calculating Monotonicity...")
        intervals = {'increasing': [], 'decreasing': []}
        
        try:
            f_prime = sp.diff(expr, self.x)
            
            # Find boundaries: critical points (f'=0) + undefined points (f' undef) + domain boundaries
            crit_pts = self.safe_solveset(f_prime)
            n, d = sp.fraction(sp.cancel(f_prime))
            undef_pts = self.safe_solveset(d)
            
            break_points = set()
            
            def add_principal_points(point_set):
                if isinstance(point_set, FiniteSet):
                    break_points.update([p for p in point_set if p.is_real is not False and not p.has(sp.I)])
                else:
                    try:
                        intersected = sp.Intersection(point_set, sp.Interval(-2*sp.pi, 2*sp.pi))
                        if isinstance(intersected, FiniteSet):
                            break_points.update([p for p in intersected])
                    except:
                        pass
                        
            add_principal_points(crit_pts)
            add_principal_points(undef_pts)
                
            # If domain isn't Reals, we'd theoretically need to intersect, but simpler 
            # approach is to evaluate intervals between sorted break points.
            sorted_breaks = sorted(list(break_points), key=lambda pt: float(pt.evalf()))
            
            boundaries = [-sp.oo] + sorted_breaks + [sp.oo]
            
            for i in range(len(boundaries) - 1):
                start = boundaries[i]
                end = boundaries[i+1]
                
                # Create the interval
                iv = Interval(start, end, True, True)
                # Check if this valid in domain
                if not sp.Intersection(iv, domain).is_empty:
                    # Pick a test point
                    if start == -sp.oo and end == sp.oo:
                        test_pt = 0
                    elif start == -sp.oo:
                        test_pt = end - 1
                    elif end == sp.oo:
                        test_pt = start + 1
                    else:
                        test_pt = (start + end) / 2
                    
                    # Ensure test pt is in domain
                    if domain.contains(test_pt):
                        val = f_prime.subs(self.x, test_pt).evalf()
                        if val > 0:
                            intervals['increasing'].append((start, end))
                        elif val < 0:
                            intervals['decreasing'].append((start, end))
        except Exception as e:
             self._log(f"Monotonicity calculation failed: {e}")

        return intervals

    def analyze(self, func_string):
        """High-level orchestration combining all pieces."""
        print(f"\n{'='*50}")
        print(f"[{func_string}] Analysis Starting...")
        print(f"{'='*50}")
        
        start_time = time.time()
        # Replace ^ with ** to avoid XOR parsing issues
        func_string = func_string.replace('^', '**')
        # Replace e with E for proper sympy evaluation if it's acting as Euler's number
        # Note: simplistic replace, could be improved.
        func_string = func_string.replace('e**', 'E**').replace('e^', 'E**')
        expr = get_sympified_expr(func_string)
        
        # Ensure we use the exact symbol parsed from the string
        symbols = [s for s in expr.free_symbols if s.name == 'x']
        if symbols:
            self.x = symbols[0]
        else:
            self.x = sp.Symbol('x', real=True)
            
        domain = self.get_domain(expr)
        intercepts = self.get_intercepts(expr, domain)
        extrema = self.get_extrema(expr, domain)
        inflections = self.get_inflection_points(expr, domain)
        asymptotes = self.get_asymptotes(expr, domain)
        parity = self.get_parity(expr)
        period = self.get_periodicity(expr)
        monotonicity = self.get_monotonicity(expr, domain)
        
        elapsed = time.time() - start_time
        
        # Compile Report
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
        
        # Intercepts
        x_ints = ", ".join(map(str, res['Intercepts']['x'])) if res['Intercepts']['x'] else "None"
        print(f"X-Intercepts:   {x_ints}")
        print(f"Y-Intercept:    {res['Intercepts']['y']}")
        
        # Extrema
        minima = ", ".join([f"({x}, {y})" for x,y in res['Extrema']['minima']])
        maxima = ", ".join([f"({x}, {y})" for x,y in res['Extrema']['maxima']])
        print(f"Minima:         {minima if minima else 'None'}")
        print(f"Maxima:         {maxima if maxima else 'None'}")
        
        # Inflections
        infs = ", ".join([f"({x}, {y})" for x,y in res['Inflection Points']])
        print(f"Inflection pts: {infs if infs else 'None'}")
        
        # Asymptotes
        vert = ", ".join(map(lambda v: f"x = {str(v)}", res['Asymptotes']['vertical']))
        horz = ", ".join(map(lambda h: f"y = {str(h)}", res['Asymptotes']['horizontal']))
        oblq = ", ".join(map(lambda o: f"y = {str(o)}", res['Asymptotes']['oblique']))
        print(f"Vertical Asym:  {vert if vert else 'The function does not have any vertical asymptotes.'}")
        print(f"Horizontal Asym:{horz if horz else 'The function does not have any horizontal asymptotes.'}")
        print(f"Oblique Asym:   {oblq if oblq else 'The function does not have any oblique asymptotes.'}")
        
        print(f"Parity:         {res['Parity']}")
        print(f"Periodicity:    {res['Periodicity']}")
        
        # Monotonicity
        print("Monotonicity:")
        for inc in res['Monotonicity']['increasing']:
             print(f"  ({inc[0]}, {inc[1]})\tIncreasing")
        for dec in res['Monotonicity']['decreasing']:
             print(f"  ({dec[0]}, {dec[1]})\tDecreasing")
        
        print(f"\n[Analyzed in {res['Time (s)']} seconds]")
        print("-" * 50)


# =============================================================================
# EXTENSIVE TEST SUITE (10-15 Target Functions)
# =============================================================================
if __name__ == "__main__":
    engine = FunctionAnalysisEngine(debug=False)

    test_functions = [
        "x^3 - 6*x^2 + 9*x + 15",             # Polynomial (from the user image)
        "1 / x",                              # Simple vertical and horizontal asymptote
        "sin(x)",                             # Periodicity, extrema
        "x^2 / (x^2 - 4)",                    # rational function, horizontal and vertical asymptotes
        "e^(-x^2)",                           # Bell curve, horizontal asymptote
        "ln(x)",                              # Domain restrictions
        "(x^2 + 1) / x",                      # Oblique asymptote
        "x^3 - 3*x",                          # Roots parity test, clean extremas
        "tan(x)",                             # Periodic, Infinite vertical asymptotes
        "x * e^x",                            # Mixed exponential polynomial
        "sin(x) / x",                         # Sinc function 
        "sqrt(x - 1)",                        # Strict domain bound
        "(x^2 - 1) / (x^2 + 1)",              # Horizontal asymptote, smooth bounds
        "abs(x)",                             # Non-differentiable extremas
        "x * ln(x)",                          # Domain and minima 
    ]

    for f_str in test_functions:
        engine.analyze(f_str)
