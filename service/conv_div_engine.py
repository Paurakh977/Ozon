import sympy as sp
import time
import warnings
import numpy as np
from colorama import init, Fore, Style

# Initialize Colorama
init(autoreset=True)

class Profiler:
    """Robust profiler that tracks execution time and prevents double-counting."""
    def __init__(self):
        self.starts = {}
        self.totals = {}

    def start(self, name):
        self.starts[name] = time.perf_counter()
        if name not in self.totals:
            self.totals[name] = 0.0

    def stop(self, name):
        if name in self.starts and self.starts[name] is not None:
            elapsed = (time.perf_counter() - self.starts[name]) * 1000
            self.totals[name] += elapsed
            self.starts[name] = None 

    def get_log_string(self):
        logs =[f"{k}: {v:.1f}ms" for k, v in self.totals.items() if v >= 0.1]
        if not logs:
            return "[Fast-Track: <0.1ms]"
        return "[" + " | ".join(logs) + "]"

def apply_stirling(expr):
    """Fallback replacement for factorials and Gamma using Stirling's approximation."""
    stirling_expr = expr.replace(
        sp.factorial, 
        lambda arg: sp.sqrt(2 * sp.pi * arg) * (arg / sp.E)**arg
    )
    stirling_expr = stirling_expr.replace(
        sp.gamma,
        lambda arg: sp.sqrt(2 * sp.pi * (arg - 1)) * ((arg - 1) / sp.E)**(arg - 1)
    )
    stirling_expr = sp.expand_power_base(stirling_expr, force=True)
    stirling_expr = sp.powsimp(stirling_expr, force=True)
    return sp.cancel(stirling_expr)

def numerical_divergence_check(expr, n):
    """Uses raw NumPy C-speed float evaluation to detect obvious unbounded divergence instantly."""
    try:
        num_expr = expr.subs({sp.factorial(n): sp.gamma(n+1)})
        f = sp.lambdify(n, num_expr, modules=['numpy', 'math'])
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore") 
            vals = []
            for x_val in[10.0, 50.0, 100.0, 140.0]:
                try: vals.append(float(f(x_val)))
                except Exception: pass
            
        if not vals or any(np.isnan(v) for v in vals): return False 
        if any(np.isinf(v) for v in vals): return True
            
        max_val = max(abs(v) for v in vals)
        min_val = min(abs(v) for v in vals)
        
        if max_val > 1e15 and (max_val - min_val) > 1e10: return True 
    except Exception:
        pass
    return False

def super_fast_limit(expr, n, prof):
    """Bypasses slow SymPy limit engine by extracting asymptotic polynomials."""
    
    def snap_limit(L):
        """Fixes floating-point precision traps (e.g. L = 183939720585721*E/500000000000000 -> 1)"""
        if L is not None and L.is_number and not L.has(sp.Limit):
            try:
                val = float(L)
                if abs(val - 1.0) < 1e-9: return sp.S(1)
                if abs(val) < 1e-9: return sp.S(0)
                if abs(val + 1.0) < 1e-9: return sp.S(-1)
            except Exception:
                pass
        return L

    has_n_exp = any(isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow))

    prof.start('Num-Heuristic')
    if numerical_divergence_check(expr, n):
        prof.stop('Num-Heuristic')
        return sp.oo
    prof.stop('Num-Heuristic')

    prof.start('Asymp-LeadTerm')
    if not expr.has(sp.factorial) and not expr.has(sp.gamma) and not has_n_exp:
        try:
            x = sp.Symbol('x', positive=True)
            expr_x = expr.subs(n, 1/x)
            c, p = expr_x.leadterm(x)
            if not c.has(sp.O) and not p.has(sp.O) and not c.has(x):
                prof.stop('Asymp-LeadTerm')
                if p > 0: return sp.S(0)
                if p < 0: return sp.oo * sp.sign(c)
                if p == 0:
                    c_lim = sp.limit(c, x, 0)
                    if c_lim.is_number: return snap_limit(c_lim)
        except Exception: pass
    prof.stop('Asymp-LeadTerm')

    prof.start('Stirling-Log')
    if expr.has(sp.factorial) or expr.has(sp.gamma):
        try:
            s_expr = apply_stirling(expr)
            
            L_direct = sp.limit(s_expr, n, sp.oo)
            if L_direct is not None and not L_direct.has(sp.Limit):
                prof.stop('Stirling-Log')
                return snap_limit(L_direct)

            log_s = sp.expand_log(sp.log(s_expr), force=True)
            L_log = sp.limit(log_s, n, sp.oo)
            if L_log is not None and not L_log.has(sp.Limit):
                prof.stop('Stirling-Log')
                return snap_limit(sp.exp(L_log))
        except Exception: pass
    prof.stop('Stirling-Log')

    prof.start('SymPy-Fallback')
    try:
        res = sp.limit(expr, n, sp.oo)
        prof.stop('SymPy-Fallback')
        return snap_limit(res)
    except Exception: 
        prof.stop('SymPy-Fallback')
        return None

def check_sequence_convergence(expr, n):
    prof = Profiler()
    has_fact = expr.has(sp.factorial) or expr.has(sp.gamma)
    has_n_exp = any(isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow))
    
    has_n_root = False
    for p in expr.atoms(sp.Pow):
        if p.exp.has(n) and sp.limit(p.exp, n, sp.oo) == 0:
            has_n_root = True
            break

    abs_n = expr.subs({(-1)**n: 1, (-1)**(n+1): 1, (-1)**(n-1): 1})
    
    if expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)):
        prof.start('Seq-Alt-Check')
        expr_even = expr.subs({(-1)**n: 1, (-1)**(n+1): -1, (-1)**(n-1): -1})
        expr_odd  = expr.subs({(-1)**n: -1, (-1)**(n+1): 1, (-1)**(n-1): 1})
        L_even = super_fast_limit(expr_even, n, prof)
        L_odd = super_fast_limit(expr_odd, n, prof)
        prof.stop('Seq-Alt-Check')
        
        if L_even is not None and L_odd is not None and not L_even.has(sp.Limit) and not L_odd.has(sp.Limit):
            if L_even == L_odd:
                return True, f"Converges to {L_even}", prof.get_log_string()
            else:
                return False, f"Diverges (Oscillates between {L_even} and {L_odd})", prof.get_log_string()

    # SEQUENCE RATIO TEST 
    if has_fact and not has_n_root:
        prof.start('Seq-Ratio-Test')
        try:
            ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n+1) / abs_n))
            ratio_limit = super_fast_limit(ratio_expr, n, prof)
            if ratio_limit is not None and ratio_limit.is_number and not ratio_limit.has(sp.Limit):
                if ratio_limit < 1:
                    prof.stop('Seq-Ratio-Test')
                    return True, f"Converges to 0 (Ratio L = {ratio_limit})", prof.get_log_string()
                if ratio_limit > 1:
                    prof.stop('Seq-Ratio-Test')
                    return False, f"Diverges to oo (Ratio L = {ratio_limit})", prof.get_log_string()
                    
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    x = sp.Symbol('x', positive=True)
                    c, p = (inv_ratio.subs(n, 1/x) - 1).leadterm(x)
                    if p == 1 and not c.has(x):
                        h = sp.limit(c, x, 0)
                        prof.stop('Seq-Ratio-Test')
                        if h > 0: return True, f"Converges to 0 (Asymp Ratio h={h} > 0)", prof.get_log_string()
                        if h < 0: return False, f"Diverges to oo (Asymp Ratio h={h} < 0)", prof.get_log_string()
        except Exception: pass
        prof.stop('Seq-Ratio-Test')

    # SEQUENCE ROOT TEST
    if has_n_exp and not has_fact:
        prof.start('Seq-Root-Test')
        try:
            log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n, prof)
            if log_root_limit is not None and log_root_limit.is_number and not log_root_limit.has(sp.Limit):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1:
                    prof.stop('Seq-Root-Test')
                    return True, f"Converges to 0 (Root L = {root_limit})", prof.get_log_string()
                if root_limit > 1:
                    prof.stop('Seq-Root-Test')
                    return False, f"Diverges to oo (Root L = {root_limit})", prof.get_log_string()
        except Exception: pass
        prof.stop('Seq-Root-Test')

    L = super_fast_limit(expr, n, prof)
    if L is None or L.has(sp.Limit): return None, "Undetermined", prof.get_log_string()
    if isinstance(L, sp.AccumBounds) or L is sp.nan: return False, "Divergent (Oscillates or DNE)", prof.get_log_string()
    if L.is_finite and L.is_real: return True, f"Converges to {L}", prof.get_log_string()
    return False, f"Diverges to {L}", prof.get_log_string()


def check_series_convergence(expr, n, start_idx=1):
    prof = Profiler()
    try:
        abs_n = expr.subs({(-1)**n: 1, (-1)**(n+1): 1, (-1)**(n-1): 1})
        has_fact = expr.has(sp.factorial) or expr.has(sp.gamma)
        has_n_exp = any(isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow))
        
        is_oscillatory = expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)) or expr.has(sp.sin(n)) or expr.has(sp.cos(n))

        # 1. NTH TERM TEST 
        prof.start('Nth-Term')
        term_limit = super_fast_limit(abs_n, n, prof)
        prof.stop('Nth-Term')
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0 and not isinstance(term_limit, sp.AccumBounds): 
                return False, f"Divergent (nth-term L={term_limit} != 0)", prof.get_log_string()
            if isinstance(term_limit, sp.AccumBounds) or term_limit is sp.nan:
                return False, "Divergent (Oscillates or DNE)", prof.get_log_string()

        # 2. ASYMPTOTIC P-TEST
        prof.start('Asymp-p-test')
        if not has_fact:
            try:
                x = sp.Symbol('x', positive=True)
                expr_x = abs_n.subs(n, 1/x)
                c, p = expr_x.leadterm(x)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                    if not c.has(x):
                        if p > 1: 
                            prof.stop('Asymp-p-test')
                            return True, f"Absolutely Convergent (Asymptotic p={p} > 1)", prof.get_log_string()
                        elif not is_oscillatory: 
                            if p < 1: 
                                prof.stop('Asymp-p-test')
                                return False, f"Divergent (Asymptotic p={p} < 1)", prof.get_log_string()
                            if p == 1: 
                                prof.stop('Asymp-p-test')
                                return False, f"Divergent (Asymptotic Harmonic p=1)", prof.get_log_string()
                    else:
                        # Mixed log-polynomial term (e.g., ln(n)/n^(3/2))
                        # Mathematically shift p by an epsilon margin to rigorously force Generalized Limit Comparison
                        if p > 1:
                            p_prime = (1 + p) / 2
                            prof.stop('Asymp-p-test')
                            return True, f"Absolutely Convergent (Asymp p'={p_prime} > 1)", prof.get_log_string()
                        elif not is_oscillatory:
                            if p < 1:
                                p_prime = (1 + p) / 2
                                prof.stop('Asymp-p-test')
                                return False, f"Divergent (Asymp p'={p_prime} < 1)", prof.get_log_string()
                            # If p == 1, fall through safely to Cauchy/Log-Asymp tests
            except Exception: pass
        prof.stop('Asymp-p-test')

        # 3. LOGARITHMIC ASYMPTOTIC TEST
        prof.start('Log-Asymp-Test')
        if not has_fact and abs_n.has(sp.log):
            try:
                log_asymp_expr = sp.cancel(-sp.expand_log(sp.log(abs_n), force=True) / sp.log(n))
                L_log = super_fast_limit(log_asymp_expr, n, prof)
                if L_log is not None and L_log.is_number and not L_log.has(sp.Limit):
                    if L_log > 1: 
                        prof.stop('Log-Asymp-Test')
                        return True, f"Absolutely Convergent (Log-Asymp p={L_log} > 1)", prof.get_log_string()
                    elif not is_oscillatory:
                        if L_log < 1: 
                            prof.stop('Log-Asymp-Test')
                            return False, f"Divergent (Log-Asymp p={L_log} < 1)", prof.get_log_string()
            except Exception: pass
        prof.stop('Log-Asymp-Test')

        # 4. CAUCHY CONDENSATION TEST
        prof.start('Cauchy-Condensation')
        if not has_fact and abs_n.has(sp.log):
            current_term = abs_n
            for i in range(1, 3): 
                current_term = sp.simplify((2**n) * current_term.subs(n, 2**n))
                try:
                    x = sp.Symbol('x', positive=True)
                    expr_x = current_term.subs(n, 1/x)
                    c, p = expr_x.leadterm(x)
                    if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                        if not c.has(x):
                            if p > 1: 
                                prof.stop('Cauchy-Condensation')
                                return True, f"Absolutely Convergent (Condensation L{i} p={p} > 1)", prof.get_log_string()
                            elif not is_oscillatory:
                                if p < 1: 
                                    prof.stop('Cauchy-Condensation')
                                    return False, f"Divergent (Condensation L{i} p={p} < 1)", prof.get_log_string()
                                if p == 1: 
                                    prof.stop('Cauchy-Condensation')
                                    return False, f"Divergent (Condensation L{i} p=1)", prof.get_log_string()
                        else:
                            if p > 1:
                                p_prime = (1 + p) / 2
                                prof.stop('Cauchy-Condensation')
                                return True, f"Absolutely Convergent (Condensation L{i} p'={p_prime} > 1)", prof.get_log_string()
                            elif not is_oscillatory:
                                if p < 1:
                                    p_prime = (1 + p) / 2
                                    prof.stop('Cauchy-Condensation')
                                    return False, f"Divergent (Condensation L{i} p'={p_prime} < 1)", prof.get_log_string()
                except Exception: pass
        prof.stop('Cauchy-Condensation')

        # 5. EXACT RATIO + SERIES-BASED GAUSS TEST
        if has_fact:
            prof.start('Ratio-Test')
            ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n+1) / abs_n))
            ratio_limit = super_fast_limit(ratio_expr, n, prof)
            if ratio_limit is not None and ratio_limit.is_number and not ratio_limit.has(sp.Limit):
                if ratio_limit < 1: 
                    prof.stop('Ratio-Test')
                    return True, f"Absolutely Convergent (Ratio L = {ratio_limit})", prof.get_log_string()
                if ratio_limit > 1: 
                    prof.stop('Ratio-Test')
                    return False, f"Divergent (Ratio L = {ratio_limit})", prof.get_log_string()
                
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    x = sp.Symbol('x', positive=True)
                    try:
                        c, p = (inv_ratio.subs(n, 1/x) - 1).leadterm(x)
                        if p == 1:
                            if not c.has(x):
                                h = sp.limit(c, x, 0)
                                prof.stop('Ratio-Test')
                                if h > 1: return True, f"Absolutely Convergent (Gauss/Raabe h={h} > 1)", prof.get_log_string()
                                if h <= 1: return False, f"Divergent (Gauss/Raabe h={h} <= 1)", prof.get_log_string()
                        elif p < 1 and p.is_number and not c.has(x):
                            prof.stop('Ratio-Test')
                            return False, f"Divergent (Gauss/Raabe p={p} < 1)", prof.get_log_string()
                        elif p > 1 and p.is_number and not c.has(x):
                            prof.stop('Ratio-Test')
                            return False, f"Divergent (Gauss/Raabe h=0 <= 1)", prof.get_log_string()
                    except Exception: pass
            prof.stop('Ratio-Test')

        # 6. ASYMPTOTIC STIRLING TEST
        prof.start('Asymp-Stirling')
        if has_fact:
            try:
                stirling_term = apply_stirling(abs_n)
                x = sp.Symbol('x', positive=True)
                c, p = stirling_term.subs(n, 1/x).leadterm(x)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                    if not c.has(x):
                        if p > 1: 
                            prof.stop('Asymp-Stirling')
                            return True, f"Absolutely Convergent (Stirling ~ 1/n^{p})", prof.get_log_string()
                        elif not is_oscillatory:
                            if p <= 1: 
                                prof.stop('Asymp-Stirling')
                                return False, f"Divergent (Stirling ~ 1/n^{p})", prof.get_log_string()
                    else:
                        if p > 1:
                            p_prime = (1 + p) / 2
                            prof.stop('Asymp-Stirling')
                            return True, f"Absolutely Convergent (Stirling p'={p_prime} > 1)", prof.get_log_string()
                        elif not is_oscillatory:
                            if p < 1:
                                p_prime = (1 + p) / 2
                                prof.stop('Asymp-Stirling')
                                return False, f"Divergent (Stirling p'={p_prime} < 1)", prof.get_log_string()
            except Exception: pass
        prof.stop('Asymp-Stirling')

        # 7. ROOT TEST (Log-Expanded)
        if has_n_exp and not has_fact:
            prof.start('Root-Test')
            log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n, prof)
            if log_root_limit is not None and log_root_limit.is_number and not log_root_limit.has(sp.Limit):
                root_limit = sp.exp(log_root_limit)
                prof.stop('Root-Test')
                if root_limit < 1: return True, f"Absolutely Convergent (Root L = {root_limit})", prof.get_log_string()
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})", prof.get_log_string()
            prof.stop('Root-Test')

        # 8. ALTERNATING TEST 
        prof.start('Alt-Test')
        if expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)):
            if super_fast_limit(abs_n, n, prof) == 0:
                prof.stop('Alt-Test')
                return True, "Convergent (Conditionally via Alternating Test)", prof.get_log_string()
        prof.stop('Alt-Test')

        # 9. DIRICHLET TEST
        prof.start('Dirichlet-Test')
        if expr.has(sp.sin(n)) or expr.has(sp.cos(n)):
            rest = abs_n.subs({sp.sin(n): 1, sp.cos(n): 1})
            if super_fast_limit(rest, n, prof) == 0:
                prof.stop('Dirichlet-Test')
                return True, "Convergent (Conditionally via Dirichlet Test)", prof.get_log_string()
        prof.stop('Dirichlet-Test')

        # 10. SYMPY ENGINE FALLBACK
        prof.start('SymPy-SeriesFallback')
        try:
            S = sp.Sum(expr, (n, start_idx, sp.oo))
            is_conv = S.is_convergent()
            prof.stop('SymPy-SeriesFallback')
            if is_conv == sp.S.true: return True, "Convergent (Built-in SymPy)", prof.get_log_string()
            if is_conv == sp.S.false: return False, "Divergent (Built-in SymPy)", prof.get_log_string()
        except NotImplementedError: 
            prof.stop('SymPy-SeriesFallback')

        return None, "Undetermined by all available heuristics", prof.get_log_string()
            
    except Exception as e:
        return None, f"Error: {str(e)}", prof.get_log_string()

def format_result(res_bool):
    if res_bool is True: return f"{Fore.GREEN}{'Converges':<10}{Style.RESET_ALL}"
    elif res_bool is False: return f"{Fore.RED}{'Diverges':<10}{Style.RESET_ALL}"
    else: return f"{Fore.YELLOW}{'Unknown':<10}{Style.RESET_ALL}"

def main():
    n = sp.Symbol('n', integer=True, positive=True)
    
    sequences =[
        (n * sp.sin(n), "n * sin(n) (Oscillatory Unbounded)"),                           
        (sp.cos(2/n)**(n**2), "cos(2/n)^(n^2) (Taylor Exp)"),                            
        (sp.factorial(n) / 100**n, "n! / 100^n (Heavy Growth)"),                         
        ((n / sp.log(n)) * (n**(1/n) - 1), "n/ln(n) * (n^(1/n) - 1)"),                   
        (sp.sqrt(n**2 + n) - n, "sqrt(n^2 + n) - n"),                                    
        ((1 + 1/n)**(n**2), "(1 + 1/n)^(n^2) (Exp explosion)"),                          
        (sp.factorial(n)**(1/n) / n, "(n!)^(1/n) / n (Stirling)"),                       
        (sp.log(n)**sp.log(n) / n, "ln(n)^ln(n) / n (Tower vs Poly)"),                   
        ((-1)**n * (n / (n + 1)), "(-1)^n * (n/(n+1)) (Alt Bounded)"),                   
        ((1 - 2/n)**(3*n), "(1 - 2/n)^(3n) (Exp transform)"),                            
        (n**sp.log(n) / 2**n, "n^ln(n) / 2^n (Sub-exponential)"),                        
        (((2**(4*n) * sp.factorial(n)**4) / (sp.factorial(2*n)**2 * (2*n + 1))), "Wallis Product (Factorial Form) -> pi/2"),            
        (n**3 * (sp.sin(1/n) - 1/n + 1/(6*n**3)), "n^3*(sin(1/n)-1/n+1/(6n^3))"),
        ((1 + sp.sin(1/n)/n)**(n**2), "(1 + sin(1/n)/n)^(n^2) (Tricky Exp)"),
        (sp.gamma(n + 0.5) / (sp.sqrt(n) * sp.gamma(n)), "Gamma Boundary Asymptotics"),
        (n**2 * (sp.exp(1/n) - 1 - 1/n), "n^2 * (e^(1/n) - 1 - 1/n) (Taylor Trap)"),
        ((sp.log(n+1) - sp.log(n)) * n, "n(ln(n+1) - ln(n)) (Limit e Identity)")
    ]

    series =[
        ((-1)**n * sp.log(n) / n, 2, "(-1)^n * ln(n)/n (Alt)"),                          
        (1 / (n * sp.log(n)), 2, "1 / (n * ln(n)) (Classic Divergent)"),                 
        (1 / (n * sp.log(n)**1.1), 2, "1 / (n * ln(n)^1.1) (Classic Conv)"),             
        (sp.sin(1/n), 1, "sin(1/n) (Harmonic Equivalent)"),                              
        (1 - sp.cos(1/n), 1, "1 - cos(1/n) (Taylor ~1/n^2)"),                            
        ((n / (n+1))**n, 1, "(n/(n+1))^n (Nth term -> 1/e)"),                            
        ((n / (n+1))**(n**2), 1, "(n/(n+1))^(n^2) (Root)"),                              
        (sp.factorial(n) / n**n, 1, "n! / n^n (Ratio Test boundary)"),                   
        ((sp.factorial(n) * sp.exp(n)) / n**(n+0.5), 1, "n!*e^n / n^(n+0.5) (Gauss)"),   
        (sp.factorial(2*n) / (sp.factorial(n)**2 * 4**n), 1, "Wallis Diverge"),          
        (sp.log(n)**sp.log(n) / n**sp.log(n), 2, "ln(n)^ln(n) / n^ln(n)"),               
        (1 / (n**(1 + 1/sp.log(n))), 2, "1 / n^(1 + 1/ln(n)) (Log Trap)"),               
        ((-1)**n * sp.sqrt(n) / (n + 100), 1, "(-1)^n * sqrt(n) / (n+100)"),             
        (sp.sqrt(n+1) - sp.sqrt(n), 1, "sqrt(n+1) - sqrt(n) (Telescope Div)"),           
        (1 / (n * sp.log(n) * sp.log(sp.log(n))**2), 3, "1/(n*ln(n)*ln(ln(n))^2)"),
        ((n**(n + 1/n)) / ((n + 1/n)**n), 1, "n^(n+1/n) / (n+1/n)^n (Heavy Base)"),
        (1 / (n**(sp.S(10001)/10000)), 1, "1 / n^(1.0001) (Poly Edge Trap)"),
        (sp.log(n)**sp.log(n) / 10**n, 2, "ln(n)^ln(n) / 10^n (Root Extractor)")
    ]

    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v10.0 (The Final Polish) - SEQUENCE TESTS':^155}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
    print(f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<32} | {'Profiler Logs'}")
    print("-" * 155)
    
    total_seq_time = 0
    for i, (expr, desc) in enumerate(sequences, 1):
        start_t = time.perf_counter()
        is_conv, reason, logs = check_sequence_convergence(expr, n)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_seq_time += elapsed_ms
        print(f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<32} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v10.0 (The Final Polish) - SERIES TESTS':^155}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
    print(f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<32} | {'Profiler Logs'}")
    print("-" * 155)
    
    total_ser_time = 0
    for i, (expr, start_idx, desc) in enumerate(series, 1):
        start_t = time.perf_counter()
        is_conv, reason, logs = check_series_convergence(expr, n, start_idx)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_ser_time += elapsed_ms
        print(f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<32} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

    print("\n" + "="*155)
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms")
    print("="*155)

def second_main():
    n = sp.Symbol('n', integer=True, positive=True)

    sequences =[
        (((n**2 + 1)/(n**2 - 1))**( n**2), "((n^2+1)/(n^2-1))^(n^2)  -> e^2"),
        ((1 + sp.log(n)/n)**n, "(1 + ln(n)/n)^n  -> oo"),
        ((sp.factorial(n))**(sp.S(1)/n**2), "(n!)^(1/n^2)  -> 1"),
        (n * (sp.exp(1/n) - sp.cos(1/n)), "n*(e^(1/n) - cos(1/n))  -> 1"),
        (n**2 * (sp.log(1 + 1/n) - sp.sin(1/n)), "n^2*(ln(1+1/n)-sin(1/n)) -> -1/2"),
        ((sp.factorial(2*n))**(sp.S(1)/n) / (4**n / n), "(2n!)^(1/n) / (4^n/n)  -> 0"),
        (sp.factorial(2*n) / (sp.factorial(n) * (2*n)**(n + sp.S(1)/2)), "(2n)!/(n!*(2n)^(n+1/2)) Stirling"),
        (sp.gamma(n + sp.S(3)/2) / (sp.sqrt(n) * sp.gamma(n + 1)), "Gamma(n+3/2)/(sqrt(n)*n!)  -> 1"),
        (sp.sin(n * sp.pi / 2) / n, "sin(nπ/2)/n  -> 0"),
        (n * sp.sin(sp.pi / n), "n*sin(π/n)  -> π"),
        ((-1)**n * n / (n**2 + 1) + sp.S(1)/2, "(-1)^n*n/(n^2+1) + 1/2  -> 1/2"),
        ((sp.cos(1/n))**( n**2), "cos(1/n)^(n^2)  -> e^(-1/2)"),
        (sp.log(n)**sp.log(sp.log(n)) / n, "ln(n)^ln(ln(n)) / n  -> 0"),
        (n**(sp.S(1)/sp.log(sp.log(n))), "n^(1/ln(ln(n)))  -> oo"),
        (sp.log(n + sp.log(n)) - sp.log(n), "ln(n+ln(n)) - ln(n)  -> 0"),
        ((1 + sp.S(1)/n**2)**( n**2), "(1+1/n^2)^(n^2)  -> e"),
        (n * (1 - sp.cos(1/n)), "n*(1-cos(1/n))  -> 0"),
        (sp.factorial(n)**2 / sp.factorial(2*n), "(n!)^2 / (2n)!  -> 0"),
        ((2*n * sp.factorial(n))**2 / sp.factorial(2*n+1), "(2n*n!)^2 / (2n+1)!  -> 0"),
        (((1 + sp.S(1)/n)**(n**2)) / sp.exp(n), "(1+1/n)^(n^2) / e^n  -> e^(-1/2)"),
    ]

    series =[
        (1 / (n * sp.log(n) * sp.log(sp.log(n))), 3, "1/(n*ln(n)*ln(ln(n))) Div"),
        (1 / (n**( sp.S(1) + sp.S(1)/n)), 2, "1/n^(1+1/n) Div (-> harmonic)"),
        (1 / (n * sp.log(n)**2 * sp.log(sp.log(n))), 3, "1/(n*ln^2(n)*ln(ln(n))) Conv"),
        (sp.factorial(n)**2 / sp.factorial(2*n), 1, "(n!)^2 / (2n)! Conv"),
        ((sp.factorial(n))**3 / sp.factorial(3*n), 1, "(n!)^3 / (3n)! Conv"),
        (sp.factorial(3*n) / (sp.factorial(n) * sp.factorial(2*n) * 3**n), 1, "(3n)!/(n!(2n)!3^n) Div"),
        ((sp.log(n))**n / n**n, 2, "ln(n)^n / n^n  Conv (Root -> 0)"),
        (((2*n + 1) / (3*n - 1))**n, 1, "((2n+1)/(3n-1))^n Conv Root->2/3"),
        ((n / (n + sp.log(n)))**n, 2, "(n/(n+ln(n)))^n  Div (Root L=1)"),
        ((-1)**n / (n + sp.log(n)), 2, "(-1)^n / (n+ln(n)) Cond Conv"),
        ((-1)**n * sp.log(n) / n**( sp.S(3)/2), 2, "(-1)^n*ln(n)/n^(3/2) Abs Conv"),
        ((-1)**n * (1 - 1/n)**n, 1, "(-1)^n*(1-1/n)^n  Div nth-term"),
        (sp.log(n)**sp.log(n) / n**2, 2, "ln(n)^ln(n) / n^2  Div (terms -> oo)"),
        (sp.log(n)**n / sp.factorial(n), 1, "ln(n)^n / n!  Conv (ratio->0)"),
        (1 / n**( sp.S(1) + sp.sin(sp.S(1)/n)), 1, "1/n^(1+sin(1/n)) Div"),
        (sp.factorial(n) * sp.factorial(n) / sp.factorial(2*n + 1), 1, "n!*n!/(2n+1)! Conv"),
        ((4*n**2) / (4*n**2 - 1), 1, "Wallis product terms Div (-> 1)"),
        (1 / (n * sp.log(n)**( sp.S(3)/2)), 2, "1/(n*ln(n)^1.5) Conv"),
        (1 / (n * sp.log(n) * sp.log(sp.log(n))**( sp.S(1)/2)), 3, "1/(n*ln*ln(ln)^0.5) Div"),
        (sp.exp(-sp.sqrt(n)), 1, "e^(-sqrt(n))  Conv"),
    ]

    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v10.0 (LETHAL EDITION) - SEQUENCE TESTS':^155}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
    print(f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}")
    print("-" * 155)

    total_seq_time = 0
    for i, (expr, desc) in enumerate(sequences, 1):
        start_t = time.perf_counter()
        is_conv, reason, logs = check_sequence_convergence(expr, n)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_seq_time += elapsed_ms
        print(f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v10.0 (LETHAL EDITION) - SERIES TESTS':^155}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
    print(f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}")
    print("-" * 155)

    total_ser_time = 0
    for i, (expr, start_idx, desc) in enumerate(series, 1):
        start_t = time.perf_counter()
        is_conv, reason, logs = check_series_convergence(expr, n, start_idx)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_ser_time += elapsed_ms
        print(f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

    print("\n" + "=" * 155)
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms")
    print("=" * 155)

if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    main()
    second_main()