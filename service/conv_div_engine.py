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
                    if c_lim.is_number: return c_lim
        except Exception: pass
    prof.stop('Asymp-LeadTerm')

    prof.start('Stirling-Log')
    if expr.has(sp.factorial) or expr.has(sp.gamma):
        try:
            s_expr = apply_stirling(expr)
            log_s = sp.expand_log(sp.log(s_expr), force=True)
            L_log = sp.limit(log_s, n, sp.oo)
            if L_log is not None and not L_log.has(sp.Limit):
                prof.stop('Stirling-Log')
                return sp.exp(L_log)
        except Exception: pass
    prof.stop('Stirling-Log')

    prof.start('SymPy-Fallback')
    try:
        res = sp.limit(expr, n, sp.oo)
        prof.stop('SymPy-Fallback')
        return res
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
    
    # ALTERNATING OSCILLATION TEST
    if expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)):
        prof.start('Seq-Alt-Check')
        abs_limit = super_fast_limit(abs_n, n, prof)
        prof.stop('Seq-Alt-Check')
        if abs_limit is not None and abs_limit != 0:
            return False, f"Diverges (Oscillates, |L| = {abs_limit})", prof.get_log_string()

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
                    if p == 1:
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

        # 1. NTH TERM TEST
        prof.start('Nth-Term')
        term_limit = super_fast_limit(expr, n, prof)
        prof.stop('Nth-Term')
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0 and not isinstance(term_limit, sp.AccumBounds): 
                return False, f"Divergent (nth-term L={term_limit} != 0)", prof.get_log_string()
            if isinstance(term_limit, sp.AccumBounds) or term_limit is sp.nan:
                return False, "Divergent (Oscillates or DNE)", prof.get_log_string()

        # 2. ALTERNATING TEST
        prof.start('Alt-Test')
        if expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)):
            if super_fast_limit(abs_n, n, prof) == 0:
                prof.stop('Alt-Test')
                return True, "Convergent (Conditionally via Alternating Test)", prof.get_log_string()
        prof.stop('Alt-Test')

        # 3. ASYMPTOTIC P-TEST
        prof.start('Asymp-p-test')
        if not has_fact:
            try:
                x = sp.Symbol('x', positive=True)
                expr_x = abs_n.subs(n, 1/x)
                c, p = expr_x.leadterm(x)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                    if p > 1: 
                        prof.stop('Asymp-p-test')
                        return True, f"Convergent (Asymptotic p={p} > 1)", prof.get_log_string()
                    if p < 1: 
                        prof.stop('Asymp-p-test')
                        return False, f"Divergent (Asymptotic p={p} < 1)", prof.get_log_string()
                    if p == 1 and not c.has(sp.log): 
                        prof.stop('Asymp-p-test')
                        return False, f"Divergent (Asymptotic Harmonic p=1)", prof.get_log_string()
            except Exception: pass
        prof.stop('Asymp-p-test')

        # 4. LOGARITHMIC ASYMPTOTIC TEST (Kills exponential/log towers instantly)
        prof.start('Log-Asymp-Test')
        if not has_fact and abs_n.has(sp.log):
            try:
                log_asymp_expr = sp.cancel(-sp.expand_log(sp.log(abs_n), force=True) / sp.log(n))
                L_log = super_fast_limit(log_asymp_expr, n, prof)
                if L_log is not None and L_log.is_number and not L_log.has(sp.Limit):
                    prof.stop('Log-Asymp-Test')
                    if L_log > 1: return True, f"Convergent (Log-Asymp p={L_log} > 1)", prof.get_log_string()
                    if L_log < 1: return False, f"Divergent (Log-Asymp p={L_log} < 1)", prof.get_log_string()
            except Exception: pass
        prof.stop('Log-Asymp-Test')

        # 5. CAUCHY CONDENSATION TEST (Flawlessly solves Bertrand/Log boundaries)
        prof.start('Cauchy-Condensation')
        if not has_fact and abs_n.has(sp.log):
            current_term = abs_n
            for i in range(1, 3): # Recursive condensation up to 2 times
                current_term = sp.simplify((2**n) * current_term.subs(n, 2**n))
                try:
                    x = sp.Symbol('x', positive=True)
                    expr_x = current_term.subs(n, 1/x)
                    c, p = expr_x.leadterm(x)
                    if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                        if p > 1: 
                            prof.stop('Cauchy-Condensation')
                            return True, f"Convergent (Condensation L{i} p={p} > 1)", prof.get_log_string()
                        if p < 1: 
                            prof.stop('Cauchy-Condensation')
                            return False, f"Divergent (Condensation L{i} p={p} < 1)", prof.get_log_string()
                        if p == 1 and not c.has(sp.log): 
                            prof.stop('Cauchy-Condensation')
                            return False, f"Divergent (Condensation L{i} p=1)", prof.get_log_string()
                except Exception: pass
        prof.stop('Cauchy-Condensation')

        # 6. EXACT RATIO + SERIES-BASED GAUSS TEST
        if has_fact:
            prof.start('Ratio-Test')
            ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n+1) / abs_n))
            ratio_limit = super_fast_limit(ratio_expr, n, prof)
            if ratio_limit is not None and ratio_limit.is_number and not ratio_limit.has(sp.Limit):
                if ratio_limit < 1: 
                    prof.stop('Ratio-Test')
                    return True, f"Convergent (Ratio L = {ratio_limit})", prof.get_log_string()
                if ratio_limit > 1: 
                    prof.stop('Ratio-Test')
                    return False, f"Divergent (Ratio L = {ratio_limit})", prof.get_log_string()
                
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    x = sp.Symbol('x', positive=True)
                    try:
                        c, p = (inv_ratio.subs(n, 1/x) - 1).leadterm(x)
                        if p == 1:
                            h = sp.limit(c, x, 0)
                            prof.stop('Ratio-Test')
                            if h > 1: return True, f"Convergent (Gauss/Raabe h = {h} > 1)", prof.get_log_string()
                            if h < 1: return False, f"Divergent (Gauss/Raabe h = {h} < 1)", prof.get_log_string()
                    except Exception: pass
            prof.stop('Ratio-Test')

        # 7. ROOT TEST (Log-Expanded)
        if has_n_exp and not has_fact:
            prof.start('Root-Test')
            log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n, prof)
            if log_root_limit is not None and log_root_limit.is_number and not log_root_limit.has(sp.Limit):
                root_limit = sp.exp(log_root_limit)
                prof.stop('Root-Test')
                if root_limit < 1: return True, f"Convergent (Root L = {root_limit})", prof.get_log_string()
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})", prof.get_log_string()
            prof.stop('Root-Test')

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

# def main():
#     n = sp.Symbol('n', integer=True, positive=True)
    
#     # 5 NEW HEAVY SEQUENCES ADDED!
#     sequences =[
#         (n * sp.sin(n), "n * sin(n) (Oscillatory Unbounded)"),                           
#         (sp.cos(2/n)**(n**2), "cos(2/n)^(n^2) (Taylor Exp)"),                            
#         (sp.factorial(n) / 100**n, "n! / 100^n (Heavy Growth)"),                         
#         ((n / sp.log(n)) * (n**(1/n) - 1), "n/ln(n) * (n^(1/n) - 1)"),                   
#         (sp.sqrt(n**2 + n) - n, "sqrt(n^2 + n) - n"),                                    
#         ((1 + 1/n)**(n**2), "(1 + 1/n)^(n^2) (Exp explosion)"),                          
#         (sp.factorial(n)**(1/n) / n, "(n!)^(1/n) / n (Stirling)"),                       
#         (sp.log(n)**sp.log(n) / n, "ln(n)^ln(n) / n (Tower vs Poly)"),                   
#         ((-1)**n * (n / (n + 1)), "(-1)^n * (n/(n+1)) (Alt Bounded)"),                   
#         ((1 - 2/n)**(3*n), "(1 - 2/n)^(3n) (Exp transform)"),                            
#         (n**sp.log(n) / 2**n, "n^ln(n) / 2^n (Sub-exponential)"),                        
#         (sp.factorial(2*n) / (4**n * sp.factorial(n)**2), "Wallis Sequence"),            
#         (n**3 * (sp.sin(1/n) - 1/n + 1/(6*n**3)), "n^3*(sin(1/n)-1/n+1/(6n^3))"),
#         ((1 + sp.sin(1/n)/n)**(n**2), "(1 + sin(1/n)/n)^(n^2) (Tricky Exp)"),
#         (sp.gamma(n + 0.5) / (sp.sqrt(n) * sp.gamma(n)), "Gamma Boundary Asymptotics"),
#         (n**2 * (sp.exp(1/n) - 1 - 1/n), "n^2 * (e^(1/n) - 1 - 1/n) (Taylor Trap)"),
#         ((sp.log(n+1) - sp.log(n)) * n, "n(ln(n+1) - ln(n)) (Limit e Identity)")
#     ]

#     # 5 NEW HEAVY SERIES ADDED!
#     series =[
#         ((-1)**n * sp.log(n) / n, 2, "(-1)^n * ln(n)/n (Alt)"),                          
#         (1 / (n * sp.log(n)), 2, "1 / (n * ln(n)) (Classic Divergent)"),                 
#         (1 / (n * sp.log(n)**1.1), 2, "1 / (n * ln(n)^1.1) (Classic Conv)"),             
#         (sp.sin(1/n), 1, "sin(1/n) (Harmonic Equivalent)"),                              
#         (1 - sp.cos(1/n), 1, "1 - cos(1/n) (Taylor ~1/n^2)"),                            
#         ((n / (n+1))**n, 1, "(n/(n+1))^n (Nth term -> 1/e)"),                            
#         ((n / (n+1))**(n**2), 1, "(n/(n+1))^(n^2) (Root)"),                              
#         (sp.factorial(n) / n**n, 1, "n! / n^n (Ratio Test boundary)"),                   
#         ((sp.factorial(n) * sp.exp(n)) / n**(n+0.5), 1, "n!*e^n / n^(n+0.5) (Gauss)"),   
#         (sp.factorial(2*n) / (sp.factorial(n)**2 * 4**n), 1, "Wallis Diverge"),          
#         (sp.log(n)**sp.log(n) / n**sp.log(n), 2, "ln(n)^ln(n) / n^ln(n)"),               
#         (1 / (n**(1 + 1/sp.log(n))), 2, "1 / n^(1 + 1/ln(n)) (Log Trap)"),               
#         ((-1)**n * sp.sqrt(n) / (n + 100), 1, "(-1)^n * sqrt(n) / (n+100)"),             
#         (sp.sqrt(n+1) - sp.sqrt(n), 1, "sqrt(n+1) - sqrt(n) (Telescope Div)"),           
#         (1 / (n * sp.log(n) * sp.log(sp.log(n))**2), 3, "1/(n*ln(n)*ln(ln(n))^2)"),
#         ((n**(n + 1/n)) / ((n + 1/n)**n), 1, "n^(n+1/n) / (n+1/n)^n (Heavy Base)"),
#         (1 / (n**(sp.S(10001)/10000)), 1, "1 / n^(1.0001) (Poly Edge Trap)"),
#         (sp.log(n)**sp.log(n) / 10**n, 2, "ln(n)^ln(n) / 10^n (Root Extractor)")
#     ]

#     print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
#     print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v8.0 (The True Singularity) - SEQUENCE TESTS':^155}")
#     print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
#     print(f"{'No.':<3} | {'Description':<38} | {'Result':<10} | {'Time':<8} | {'Details':<32} | {'Profiler Logs'}")
#     print("-" * 155)
    
#     total_seq_time = 0
#     for i, (expr, desc) in enumerate(sequences, 1):
#         start_t = time.perf_counter()
#         is_conv, reason, logs = check_sequence_convergence(expr, n)
#         end_t = time.perf_counter()
#         elapsed_ms = (end_t - start_t) * 1000
#         total_seq_time += elapsed_ms
#         print(f"{i:<3} | {desc:<38} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<32} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

#     print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
#     print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v8.0 (The True Singularity) - SERIES TESTS':^155}")
#     print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
#     print(f"{'No.':<3} | {'Description':<38} | {'Result':<10} | {'Time':<8} | {'Details':<32} | {'Profiler Logs'}")
#     print("-" * 155)
    
#     total_ser_time = 0
#     for i, (expr, start_idx, desc) in enumerate(series, 1):
#         start_t = time.perf_counter()
#         is_conv, reason, logs = check_series_convergence(expr, n, start_idx)
#         end_t = time.perf_counter()
#         elapsed_ms = (end_t - start_t) * 1000
#         total_ser_time += elapsed_ms
#         print(f"{i:<3} | {desc:<38} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<32} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

#     print("\n" + "="*155)
#     print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms")
#     print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms")
#     print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms")
#     print("="*155)


# def main():
#     n = sp.Symbol('n', integer=True, positive=True)

#     sequences = [
#         # --- LIMITS & EXPONENTIALS ---
#         (((n**2 + 1)/(n**2 - 1))**( n**2), "((n^2+1)/(n^2-1))^(n^2)  -> e^2"),
#         ((1 + sp.log(n)/n)**n, "(1 + ln(n)/n)^n  -> 1"),
#         ((sp.factorial(n))**(sp.S(1)/n**2), "(n!)^(1/n^2)  -> 1"),
#         (n * (sp.exp(1/n) - sp.cos(1/n)), "n*(e^(1/n) - cos(1/n))  -> 2"),
#         (n**2 * (sp.log(1 + 1/n) - sp.sin(1/n)), "n^2*(ln(1+1/n)-sin(1/n)) -> 1/2"),
#         ((sp.factorial(2*n))**(sp.S(1)/n) / (4**n / n), "(2n!)^(1/n) / (4^n/n)  -> 4/e^2"),

#         # --- STIRLING TRAPS ---
#         (sp.factorial(2*n) / (sp.factorial(n) * (2*n)**(n + sp.S(1)/2)), "(2n)!/(n!*(2n)^(n+1/2)) Stirling"),
#         (sp.gamma(n + sp.S(3)/2) / (sp.sqrt(n) * sp.gamma(n + 1)), "Gamma(n+3/2)/(sqrt(n)*n!)  -> 1"),

#         # --- OSCILLATORY / TRICKY ---
#         (sp.sin(n * sp.pi / 2) / n, "sin(nπ/2)/n  -> 0"),
#         (n * sp.sin(sp.pi / n), "n*sin(π/n)  -> π"),
#         ((-1)**n * n / (n**2 + 1) + sp.S(1)/2, "(-1)^n*n/(n^2+1) + 1/2  -> 1/2"),
#         ((sp.cos(1/n))**( n**2), "cos(1/n)^(n^2)  -> e^(-1/2)"),

#         # --- LOG TOWERS ---
#         (sp.log(n)**sp.log(sp.log(n)) / n, "ln(n)^ln(ln(n)) / n  -> 0"),
#         (n**(sp.S(1)/sp.log(sp.log(n))), "n^(1/ln(ln(n)))  -> oo"),
#         (sp.log(n + sp.log(n)) - sp.log(n), "ln(n+ln(n)) - ln(n)  -> 0"),

#         # --- RECURSIVE / HEAVY ---
#         ((1 + sp.S(1)/n**2)**( n**2), "(1+1/n^2)^(n^2)  -> e"),
#         (n * (1 - sp.cos(1/n)), "n*(1-cos(1/n))  -> 0"),
#         (sp.factorial(n)**2 / sp.factorial(2*n), "(n!)^2 / (2n)!  -> 0"),

#         # --- RAABE BOUNDARY ---
#         ((2*n * sp.factorial(n))**2 / sp.factorial(2*n+1), "(2n*n!)^2 / (2n+1)!  -> 0"),

#         # --- DOUBLE EXPONENTIAL ---
#         (((n + sp.S(1)/n))**n / sp.exp(n), "((n+1/n)/e)^n  -> e^(-1/2)... diverges"),
#     ]

#     series = [
#         # --- P-TEST EDGE CASES ---
#         (1 / (n * sp.log(n) * sp.log(sp.log(n))), 3, "1/(n*ln(n)*ln(ln(n))) Div"),
#         (1 / (n**( sp.S(1) + sp.S(1)/n)), 2, "1/n^(1+1/n) Div (-> harmonic)"),
#         (1 / (n * sp.log(n)**2 * sp.log(sp.log(n))), 3, "1/(n*ln^2(n)*ln(ln(n))) Conv"),

#         # --- RATIO TEST BOUNDARY ---
#         (sp.factorial(n)**2 / sp.factorial(2*n), 1, "(n!)^2 / (2n)! Conv"),
#         ((sp.factorial(n))**3 / sp.factorial(3*n), 1, "(n!)^3 / (3n)! Conv"),
#         (sp.factorial(3*n) / (sp.factorial(n) * sp.factorial(2*n) * 3**n), 1, "(3n)!/(n!(2n)!3^n) Div"),

#         # --- ROOT TEST TRAPS ---
#         ((sp.log(n))**n / n**n, 2, "ln(n)^n / n^n  Conv (Root -> 0)"),
#         (((2*n + 1) / (3*n - 1))**n, 1, "((2n+1)/(3n-1))^n Conv Root->2/3"),
#         ((n / (n + sp.log(n)))**n, 2, "(n/(n+ln(n)))^n  Conv Root->e^-1"),

#         # --- ALTERNATING TRICKY ---
#         ((-1)**n / (n + sp.log(n)), 2, "(-1)^n / (n+ln(n)) Cond Conv"),
#         ((-1)**n * sp.log(n) / n**( sp.S(3)/2), 2, "(-1)^n*ln(n)/n^(3/2) Cond Conv"),
#         ((-1)**n * (1 - 1/n)**n, 1, "(-1)^n*(1-1/n)^n  Div nth-term"),

#         # --- LOG ASYMPTOTIC HELLZONE ---
#         (sp.log(n)**sp.log(n) / n**2, 2, "ln(n)^ln(n) / n^2  Conv"),
#         (sp.log(n)**n / sp.factorial(n), 1, "ln(n)^n / n!  Conv (ratio->0)"),
#         (1 / n**( sp.S(1) + sp.sin(sp.S(1)/n)), 1, "1/n^(1+sin(1/n)) Div"),

#         # --- HEAVY FACTORIAL GAUSS ---
#         (sp.factorial(n) * sp.factorial(n) / sp.factorial(2*n + 1), 1, "n!*n!/(2n+1)! Conv"),
#         ((sp.S(1)*3*5*(2*n-1)) / (sp.S(2)*4*6*(2*n)), 1, "Wallis product terms Div"),

#         # --- CONDENSATION BRUTALITY ---
#         (1 / (n * sp.log(n)**( sp.S(3)/2)), 2, "1/(n*ln(n)^1.5) Conv"),
#         (1 / (n * sp.log(n) * sp.log(sp.log(n))**( sp.S(1)/2)), 3, "1/(n*ln*ln(ln)^0.5) Div"),

#         # --- MIXED EXPONENTIAL ---
#         (sp.exp(-sp.sqrt(n)), 1, "e^(-sqrt(n))  Conv"),
#     ]

#     print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
#     print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v9.0 (LETHAL EDITION) - SEQUENCE TESTS':^155}")
#     print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
#     print(f"{'No.':<3} | {'Description':<46} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}")
#     print("-" * 155)

#     total_seq_time = 0
#     for i, (expr, desc) in enumerate(sequences, 1):
#         start_t = time.perf_counter()
#         is_conv, reason, logs = check_sequence_convergence(expr, n)
#         end_t = time.perf_counter()
#         elapsed_ms = (end_t - start_t) * 1000
#         total_seq_time += elapsed_ms
#         print(f"{i:<3} | {desc:<46} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

#     print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
#     print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v9.0 (LETHAL EDITION) - SERIES TESTS':^155}")
#     print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
#     print(f"{'No.':<3} | {'Description':<46} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}")
#     print("-" * 155)

#     total_ser_time = 0
#     for i, (expr, start_idx, desc) in enumerate(series, 1):
#         start_t = time.perf_counter()
#         is_conv, reason, logs = check_series_convergence(expr, n, start_idx)
#         end_t = time.perf_counter()
#         elapsed_ms = (end_t - start_t) * 1000
#         total_ser_time += elapsed_ms
#         print(f"{i:<3} | {desc:<46} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

#     print("\n" + "=" * 155)
#     print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms")
#     print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms")
#     print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms")
#     print("=" * 155)


def main():
    n = sp.Symbol('n', integer=True, positive=True)

    sequences = [
        # ── FROM v9.0 LETHAL ──────────────────────────────────────────────────────
        (((n**2+1)/(n**2-1))**(n**2),           "((n²+1)/(n²-1))^n²  [→ e²]"),
        ((1 + sp.log(n)/n)**n,                   "(1+ln(n)/n)^n  [→ ∞ DIV]"),
        (sp.factorial(n)**(sp.S(1)/n**2),        "(n!)^(1/n²)  [→ 1]"),
        (n*(sp.exp(1/n) - sp.cos(1/n)),          "n(e^(1/n)-cos(1/n))  [→ 1]"),
        (n**2*(sp.log(1+1/n) - sp.sin(1/n)),     "n²(ln(1+1/n)-sin(1/n))  [→ -1/2]"),
        (sp.factorial(2*n)**(sp.S(1)/n) / (4**n/n), "(2n!)^(1/n)/(4^n/n)  [→ 0]"),
        (sp.factorial(2*n) / (sp.factorial(n) * (2*n)**(n+sp.S(1)/2)), "(2n)!/(n!(2n)^(n+1/2))  [→ 0]"),
        (sp.gamma(n+sp.S(3)/2) / (sp.sqrt(n)*sp.gamma(n+1)), "Γ(n+3/2)/(√n·n!)  [→ 1]"),
        (sp.sin(n*sp.pi/2)/n,                    "sin(nπ/2)/n  [→ 0]"),
        (n*sp.sin(sp.pi/n),                      "n·sin(π/n)  [→ π]"),
        ((-1)**n*n/(n**2+1) + sp.S(1)/2,         "(-1)^n·n/(n²+1)+1/2  [→ 1/2]"),
        (sp.cos(1/n)**(n**2),                    "cos(1/n)^n²  [→ e^(-1/2)]"),
        (sp.log(n)**sp.log(sp.log(n)) / n,       "ln(n)^ln(ln(n))/n  [→ 0]"),
        (n**(sp.S(1)/sp.log(sp.log(n))),         "n^(1/ln(ln(n)))  [→ ∞ DIV]"),
        (sp.log(n+sp.log(n)) - sp.log(n),        "ln(n+ln(n))-ln(n)  [→ 0]"),
        ((1+sp.S(1)/n**2)**(n**2),               "(1+1/n²)^n²  [→ e]"),
        (n*(1-sp.cos(1/n)),                      "n(1-cos(1/n))  [→ 0]"),
        (sp.factorial(n)**2 / sp.factorial(2*n), "(n!)²/(2n)!  [→ 0]"),
        ((2*n*sp.factorial(n))**2 / sp.factorial(2*n+1), "(2n·n!)²/(2n+1)!  [→ 0]"),
        ((n+sp.S(1)/n)**n / sp.exp(n),           "((n+1/n)/e)^n  [→ ∞ DIV]"),

        # ── FROM v7.0 (new unique tests) ─────────────────────────────────────────
        (sp.cos(2/n)**(n**2),                    "cos(2/n)^n²  [→ e^-2]"),
        ((n/sp.log(n))*(n**(sp.S(1)/n)-1),       "n/ln(n)·(n^(1/n)-1)  [→ 1]"),
        (sp.sqrt(n+sp.sqrt(n))-sp.sqrt(n),       "√(n+√n)-√n  [→ 1/2]"),
        (sp.factorial(n)**(sp.S(1)/n)/n,         "(n!)^(1/n)/n  Stirling  [→ e⁻¹]"),
        (n**2*(1-sp.cos(1/n)),                   "n²(1-cos(1/n))  [→ 1/2]"),
        (sp.sqrt(n**2+3*n)-n,                    "√(n²+3n)-n  [→ 3/2]"),
        (n*(sp.exp(1/n)-1),                      "n(e^(1/n)-1)  [→ 1]"),
        (sp.sin(1/n)*n,                          "n·sin(1/n)  [→ 1]"),
        (n**(sp.S(1)/n),                         "n^(1/n)  [→ 1]"),
        ((1+sp.S(2)/n+sp.S(3)/n**2)**n,          "(1+2/n+3/n²)^n  [→ e²]"),
        (sp.log(n+1)-sp.log(n),                  "ln(n+1)-ln(n)  [→ 0]"),
        (n*(1-sp.cos(1/n**2)),                   "n(1-cos(1/n²))  [→ 0]"),
        (sp.factorial(2*n)**(sp.S(1)/(2*n))/n,  "(2n!)^(1/2n)/n  [→ 4/e²]"),
        ((1-sp.S(1)/n**2)**n,                    "(1-1/n²)^n  [→ 1]"),
        (sp.log(n),                              "ln(n)  [→ ∞ DIV]"),
        (n*sp.sin(1/n)*sp.log(n),                "n·sin(1/n)·ln(n)  [→ ∞ DIV]"),
        (sp.sqrt(n)*(n**(sp.S(1)/n)-1),          "√n·(n^(1/n)-1)  [→ 0]"),
        ((-1)**n*n/(n+1),                        "(-1)^n·n/(n+1)  [DIV oscillates]"),
        (n**2*sp.sin(n)/(n**3+1),                "n²sin(n)/(n³+1)  [→ 0]"),
    ]

    series = [
        # ── FROM v9.0 LETHAL ──────────────────────────────────────────────────────
        (1/(n*sp.log(n)*sp.log(sp.log(n))), 3,            "1/(n·lnn·ln(lnn)) Bertrand [DIV]"),
        (1/n**(sp.S(1)+sp.S(1)/n), 2,                     "1/n^(1+1/n)  [DIV harmonic]"),
        (1/(n*sp.log(n)**2*sp.log(sp.log(n))), 3,         "1/(n·ln²n·ln(lnn))  [CONV]"),
        (sp.factorial(n)**2/sp.factorial(2*n), 1,          "(n!)²/(2n)!  Ratio 1/4 [CONV]"),
        (sp.factorial(n)**3/sp.factorial(3*n), 1,          "(n!)³/(3n)!  Ratio 1/27 [CONV]"),
        (sp.factorial(3*n)/(sp.factorial(n)*sp.factorial(2*n)*3**n), 1, "(3n)!/(n!(2n)!3^n)  [DIV]"),
        (sp.log(n)**n/n**n, 2,                             "ln(n)^n/n^n  Root→0 [CONV]"),
        (((2*n+1)/(3*n-1))**n, 1,                          "((2n+1)/(3n-1))^n  Root 2/3 [CONV]"),
        ((n/(n+sp.log(n)))**n, 2,                          "(n/(n+ln(n)))^n  [DIV ~1/n]"),
        ((-1)**n/(n+sp.log(n)), 2,                         "(-1)^n/(n+lnn)  [Cond CONV]"),
        ((-1)**n*sp.log(n)/n**sp.S(3)/2, 2,               "(-1)^n·lnn/n^(3/2)  [Cond CONV]"),
        ((-1)**n*(1-sp.S(1)/n)**n, 1,                      "(-1)^n(1-1/n)^n  [DIV nth-term]"),
        (sp.log(n)**sp.log(n)/n**2, 2,                     "ln(n)^ln(n)/n²  [DIV terms→∞]"),
        (sp.log(n)**n/sp.factorial(n), 1,                  "ln(n)^n/n!  Ratio→0 [CONV]"),
        (1/n**(1+sp.sin(sp.S(1)/n)), 1,                    "1/n^(1+sin(1/n))  [DIV]"),
        (sp.factorial(n)**2/sp.factorial(2*n+1), 1,        "n!·n!/(2n+1)!  Gauss h>1 [CONV]"),
        (sp.factorial(2*n)/(sp.factorial(n)**2*4**n), 1,   "Wallis (2n!/4^n(n!)²)  [DIV]"),
        (1/(n*sp.log(n)**sp.S(3)/2), 2,                    "1/(n·ln(n)^1.5)  [CONV]"),
        (1/(n*sp.log(n)*sp.log(sp.log(n))**sp.S(1)/2), 3, "1/(n·lnn·ln(lnn)^0.5)  [DIV]"),
        (sp.exp(-sp.sqrt(n)), 1,                           "e^(-√n)  [CONV]"),

        # ── FROM v7.0 (new unique tests) ─────────────────────────────────────────
        ((-1)**n*sp.log(n)/n, 2,                           "(-1)^n·lnn/n  [Cond CONV]"),
        ((n/(n+1))**(n**2), 1,                             "(n/(n+1))^n²  Root e⁻¹ [CONV]"),
        (1-sp.cos(1/n), 1,                                 "1-cos(1/n)  ~1/n² [CONV]"),
        (1/(n*sp.log(n)*sp.log(sp.log(n))**2), 3,          "1/(n·lnn·(ln·lnn)²) [CONV]"),
        (sp.factorial(n)/n**n, 1,                          "n!/n^n  Ratio e⁻¹ [CONV]"),
        (1/n**(1+1/sp.log(n)), 2,                          "1/n^(1+1/lnn)  Log Trap [DIV]"),
        (sp.sin(n)/n, 1,                                   "sin(n)/n  Dirichlet [Cond CONV]"),
        (n**(sp.S(1)/n)-1, 1,                              "n^(1/n)-1  ~lnn/n [DIV]"),
        (sp.S(1)/n**2, 1,                                  "1/n²  p=2 [CONV]"),
        (sp.exp(-n), 1,                                    "e^(-n)  geometric [CONV]"),
        (1/(n*sp.log(n)**2), 2,                            "1/(n·ln²n)  Bertrand p=2 [CONV]"),
        ((-1)**n/n**2, 1,                                  "(-1)^n/n²  abs CONV"),
        (sp.exp(-n**2), 1,                                 "e^(-n²)  Gaussian [CONV]"),
        (sp.sin(1/n)**2, 1,                                "sin²(1/n)  ~1/n² [CONV]"),
        (sp.S(1)/sp.factorial(n), 1,                       "1/n!  [CONV → e-1]"),
        ((-1)**n/sp.sqrt(n), 1,                            "(-1)^n/√n  Alternating [Cond CONV]"),
        (sp.S(1)/n, 1,                                     "1/n  harmonic [DIV]"),
        (sp.S(1)/sp.sqrt(n), 1,                            "1/√n  p=1/2 [DIV]"),
        (sp.log(n)/n, 1,                                   "lnn/n  [DIV ~harmonic]"),
        (1/(n*sp.log(n)), 2,                               "1/(n·lnn)  Bertrand p=1 [DIV]"),
        ((-1)**n*sp.sqrt(n)/(n+100), 1,                    "(-1)^n·√n/(n+100)  [Cond CONV]"),
        (sp.factorial(3*n)/(sp.factorial(n)**3*27**n), 1,  "(3n)!/(n!³·27^n)  Gauss h=1 [DIV]"),
        (n**2/sp.exp(n), 1,                                "n²/e^n  Root e⁻¹ [CONV]"),
    ]

    # ── PRINT SEQUENCES ──────────────────────────────────────────────────────────
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v10.0 (OMEGA EDITION) - SEQUENCE TESTS':^155}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*155}")
    print(f"{'No.':<3} | {'Description':<46} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}")
    print("-" * 155)

    total_seq_time = 0
    for i, (expr, desc) in enumerate(sequences, 1):
        start_t = time.perf_counter()
        is_conv, reason, logs = check_sequence_convergence(expr, n)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_seq_time += elapsed_ms
        print(f"{i:<3} | {desc:<46} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

    # ── PRINT SERIES ─────────────────────────────────────────────────────────────
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v10.0 (OMEGA EDITION) - SERIES TESTS':^155}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*155}")
    print(f"{'No.':<3} | {'Description':<46} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}")
    print("-" * 155)

    total_ser_time = 0
    for i, (expr, start_idx, desc) in enumerate(series, 1):
        start_t = time.perf_counter()
        is_conv, reason, logs = check_series_convergence(expr, n, start_idx)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_ser_time += elapsed_ms
        print(f"{i:<3} | {desc:<46} | {format_result(is_conv)} | {elapsed_ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}")

    # ── TOTALS ───────────────────────────────────────────────────────────────────
    print("\n" + "=" * 155)
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms")
    print("=" * 155)


if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    main()


if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    main()


if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    main()