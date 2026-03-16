import sympy as sp
import time
from colorama import init, Fore, Style
from sympy import Symbol, limit, oo, Sum, sin, cos, exp, log, factorial, sqrt, AccumBounds, pi
from sympy.series.limitseq import limit_seq

# Initialize Colorama
init(autoreset=True)

def apply_stirling(expr):
    """Fallback replacement for factorials using Stirling's approximation."""
    stirling_expr = expr.replace(
        sp.factorial, 
        lambda arg: sp.sqrt(2 * sp.pi * arg) * (arg / sp.E)**arg
    )
    stirling_expr = sp.expand_power_base(stirling_expr, force=True)
    return sp.cancel(sp.powsimp(stirling_expr, force=True))

def super_fast_limit(expr, n):
    """
    Bypasses the slow SymPy limit engine by extracting asymptotic leading 
    polynomial terms at x -> 0 (n -> oo). This is blazingly fast.
    """
    # 1. Asymptotic LeadTerm Bypass (The Speed Demon for Algebra/Trig)
    if not expr.has(sp.factorial) and not expr.has(sp.gamma):
        try:
            x = sp.Symbol('x', positive=True)
            expr_x = expr.subs(n, 1/x)
            c, p = expr_x.leadterm(x)
            
            # If SymPy isolates a clean leading term c * x^p
            if not c.has(sp.O) and not p.has(sp.O) and not c.has(x):
                if p > 0: return sp.S(0)
                if p < 0: return oo * sp.sign(c)
                if p == 0:
                    c_lim = limit(c, x, 0)
                    if c_lim.is_number: return c_lim
        except Exception:
            pass

    # 2. Factorial/Gamma Log-Stirling Resolution (Kills Combinatorial Explosions)
    if expr.has(sp.factorial) or expr.has(sp.gamma):
        try:
            s_expr = apply_stirling(expr)
            # Expand logarithmic powers immediately to make it linearly calculable
            log_s = sp.expand_log(sp.log(s_expr), force=True)
            L_log = limit(log_s, n, oo)
            if L_log is not None and not L_log.has(sp.Limit):
                return sp.exp(L_log)
        except Exception:
            pass

    # 3. Standard Fallback Engine
    try:
        if expr.has(sp.gamma) or expr.has((-1)**n):
            L = limit_seq(expr, n)
            if L is not None and not L.has(sp.Limit): return L
    except Exception: pass

    try: return limit(expr, n, oo)
    except Exception: return None

def check_sequence_convergence(expr, n):
    if expr.has(sp.factorial):
        try:
            simplified = sp.cancel(sp.combsimp(expr))
            if not simplified.has(sp.factorial):
                expr = simplified
        except Exception:
            pass
            
    L = super_fast_limit(expr, n)
    if L is None or L.has(sp.Limit): return None, "Undetermined"
    if isinstance(L, AccumBounds) or L is sp.nan: return False, "Divergent (Oscillates or DNE)"
    if L.is_finite and L.is_real: return True, f"Converges to {L}"
    return False, f"Diverges to {L}"

def check_series_convergence(expr, n, start_idx=1):
    try:
        abs_n = expr.subs({(-1)**n: 1, (-1)**(n+1): 1, (-1)**(n-1): 1})
        has_fact = expr.has(sp.factorial)
        has_n_exp = any(isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow))

        # 1. DIVERGENCE TEST
        term_limit = super_fast_limit(expr, n)
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0: return False, f"Divergent (nth-term limit = {term_limit} != 0)"

        # 2. ALTERNATING & DIRICHLET (Fast Pattern Matching)
        if expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)):
            if super_fast_limit(abs_n, n) == 0:
                return True, "Convergent (Conditionally via Alternating Test)"
                
        if expr.has(sp.sin(n)) or expr.has(sp.cos(n)):
            rest = expr.subs({sp.sin(n): 1, sp.cos(n): 1})
            if super_fast_limit(rest, n) == 0:
                return True, "Convergent (Conditionally via Dirichlet Test)"

        # 3. DIRECT ASYMPTOTIC TEST (Kills LCT completely if no factorials)
        if not has_fact:
            try:
                x = sp.Symbol('x', positive=True)
                expr_x = abs_n.subs({sp.sin(n): 1, sp.cos(n): 1, n: 1/x})
                c, p = expr_x.leadterm(x)
                if not c.has(sp.O) and not p.has(sp.O):
                    if p.is_number:
                        if p > 1: return True, f"Convergent (Asymptotic p-test ~ 1/n^{p})"
                        if p < 1 and not c.has(sp.log): return False, f"Divergent (Asymptotic p-test ~ 1/n^{p})"
                        if p == 1 and not c.has(sp.log): return False, f"Divergent (Asymptotic harmonic p=1)"
            except Exception:
                pass

        # 4. INTEGRAL TEST (Obliterates Bertrand and heavy Log traps)
        if not has_fact and abs_n.has(sp.log):
            try:
                x_sym = sp.Symbol('x', positive=True)
                res = sp.integrate(abs_n.subs(n, x_sym), (x_sym, 3, oo))
                if res.is_number:
                    if res.is_finite: return True, "Convergent (Integral Test)"
                    else: return False, "Divergent (Integral Test)"
            except Exception:
                pass

        # 5. ROOT TEST (Log-Expanded)
        if has_n_exp and not has_fact:
            log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n)
            if log_root_limit is not None and log_root_limit.is_number and not log_root_limit.has(sp.Limit):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1: return True, f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 6. EXACT RATIO + SERIES-BASED GAUSS TEST (For Combinatorics)
        if has_fact:
            ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n+1) / abs_n))
            ratio_limit = super_fast_limit(ratio_expr, n)
            
            if ratio_limit is not None and ratio_limit.is_number and not ratio_limit.has(sp.Limit):
                if ratio_limit < 1: return True, f"Convergent (Ratio L = {ratio_limit})"
                if ratio_limit > 1: return False, f"Divergent (Ratio L = {ratio_limit})"
                
                # RAABE/GAUSS EXTRACTOR: Instantly extract 'h' from Taylor Series
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    x = sp.Symbol('x', positive=True)
                    try:
                        # Extract the linear slope coefficient at x=0 (n=oo)
                        c, p = (inv_ratio.subs(n, 1/x) - 1).leadterm(x)
                        if p == 1:
                            h = limit(c, x, 0)
                            if h > 1: return True, f"Convergent (Gauss/Raabe h = {h} > 1)"
                            if h < 1: return False, f"Divergent (Gauss/Raabe h = {h} < 1)"
                            if h == 1: return False, f"Divergent (Gauss h = 1 boundaries)"
                    except Exception:
                        pass

        # 7. FINAL ROOT FALLBACK
        if not has_n_exp and not has_fact:
            log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n)
            if log_root_limit is not None and log_root_limit.is_number and not log_root_limit.has(sp.Limit):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1: return True, f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 8. SYMPY ENGINE
        try:
            S = Sum(expr, (n, start_idx, oo))
            is_conv = S.is_convergent()
            if is_conv == sp.S.true: return True, "Convergent (Built-in SymPy)"
            if is_conv == sp.S.false: return False, "Divergent (Built-in SymPy)"
        except NotImplementedError: pass

        return None, "Undetermined by all available heuristics"
            
    except Exception as e:
        return None, f"Error: {str(e)}"

def format_result(res_bool):
    if res_bool is True: return f"{Fore.GREEN}{'Converges':<10}{Style.RESET_ALL}"
    elif res_bool is False: return f"{Fore.RED}{'Diverges':<10}{Style.RESET_ALL}"
    else: return f"{Fore.YELLOW}{'Unknown':<10}{Style.RESET_ALL}"

def main():
    n = Symbol('n', integer=True, positive=True)
    
    sequences =[
        (cos(2/n)**(n**2), "cos(2/n)^(n^2) (Taylor Exp)"),
        ((n / log(n)) * (n**(1/n) - 1), "n/ln(n) * (n^(1/n) - 1)"),
        (sqrt(n + sqrt(n)) - sqrt(n), "sqrt(n + sqrt(n)) - sqrt(n)"),
        (((n**2 + 1)/(n**2 - 1))**(n**2), "((n^2+1)/(n^2-1))^(n^2)"),
        (factorial(n)**(1/n) / n, "(n!)^(1/n) / n (Stirling)"),
        ((n**(n + sp.S(1)/2) * exp(-n)) / factorial(n), "Stirling Asymptotic Boundary"),
        (n**2 * (1 - cos(1/n)), "n^2(1 - cos(1/n))"),
        (n - n**2 * log(1 + 1/n), "n - n^2*ln(1 + 1/n)"),
        ((1 + 1/n + 1/n**2)**n, "(1 + 1/n + 1/n^2)^n"),
        ((sp.pi/2 - sp.atan(n)) * n, "n * (pi/2 - arctan(n))"),
        (n**(sp.S(1)/log(n)), "n^(1/ln(n)) (Log Identity trap)"),
        (log(n+1)**2 - log(n)**2, "ln(n+1)^2 - ln(n)^2"),
        ((1 - 2/n)**(3*n), "(1 - 2/n)^(3n) (Exp transform)"),
        (sp.sin(n)/n, "sin(n)/n (Damped Oscillation)"),
        (sp.sqrt(n**2 + 3*n) - n, "sqrt(n^2+3n) - n"),
        ((n*factorial(n)) / factorial(n+1), "n*n! / (n+1)!"),
        (sp.log(n) / n**(sp.S(1)/10), "ln(n) / n^(0.1)"),
        (n * (sp.exp(1/n) - 1), "n*(e^(1/n) - 1)"),
        (factorial(2*n) / (4**n * factorial(n)**2), "Wallis Sequence (2n!/4^n*n!^2)"),
        (sp.sin(1/n)**2 * n**2, "n^2 * sin(1/n)^2"),
        (((n+1)/(n+2))**(n**2), "((n+1)/(n+2))^(n^2) (Heavy Base)"),
        ((factorial(3*n)**(1/(3*n))) / n, "(3n!)^(1/3n) / n (Heavy Stirling)"),
        (n**2 * (log(n+1) - log(n)) - n, "n^2*(ln(n+1)-ln(n)) - n"),
        (cos(1/sqrt(n))**n, "cos(1/sqrt(n))^n (Root Taylor)"),
        (n**3 * (sin(1/n) - 1/n + 1/(6*n**3)), "n^3*(sin(1/n)-1/n+1/(6n^3))")
    ]

    series =[
        ((-1)**n * log(n) / n, 2, "(-1)^n * ln(n)/n"),
        ((n / (n+1))**(n**2), 1, "(n/(n+1))^(n^2)"),
        ((1 - cos(1/n)), 1, "1 - cos(1/n) (Taylor cancel)"),
        (sin(1/n) - 1/n, 1, "sin(1/n) - 1/n (Cubic cancel)"),
        ((n**(1/n) - 1)**n, 1, "(n^(1/n) - 1)^n"),
        (1 / (n**(1 + 1/log(n))), 2, "1 / n^(1 + 1/ln(n)) (Log Trap!)"),
        (1 / (n * log(n) * log(log(n))**2), 3, "1 / (n*ln(n)*ln(ln(n))^2) (Bertrand)"),
        (sqrt(n**3 + 1) - sqrt(n**3 - 1), 2, "sqrt(n^3+1) - sqrt(n^3-1)"),
        (factorial(2*n) / (4**n * factorial(n)**2), 1, "Wallis Series (Needs Gauss's Test)"),
        (1/n - log(1 + 1/n), 1, "1/n - ln(1 + 1/n) (Taylor Asymp)"),
        (sin(n) / n, 1, "sin(n)/n (Dirichlet bounds)"),
        (n**(sp.S(1)/n) - 1, 1, "n^(1/n) - 1 (Asymptotic ln)"),
        (factorial(n) / n**n, 1, "n! / n^n (Ratio Test boundary)"),
        (n**2 / sp.exp(n), 1, "n^2 / e^n (Polynomial vs Exp)"),
        (factorial(n)**2 / factorial(2*n), 1, "(n!)^2 / (2n)!"),
        ((-1)**n / (n + sp.sin(n)**2), 1, "Alt harmonic with trig noise"),
        ((sp.factorial(3*n)) / (sp.factorial(n)**3 * 27**n), 1, "Heavy Gauss's Test (3n!)"),
        (1 / (n * sp.log(n)**(sp.S(1)/2)), 2, "Divergent p-log (p=1/2)"),
        (sp.exp(-n**2), 1, "e^(-n^2) (Fast Gaussian decay)"),
        ((1 - 1/n)**(n**2), 2, "(1 - 1/n)^(n^2) (Heavy Root Test)"),
        ((-1)**n * sqrt(n) / (n + 100), 1, "(-1)^n * sqrt(n) / (n+100)"),
        ((sqrt(n**2 + 1) - n)**n, 1, "(sqrt(n^2+1) - n)^n (Root Conjugate)"),
        (factorial(2*n) / (factorial(n)**2 * 4**n), 1, "(2n)! / (n!^2 * 4^n) (Wallis Diverge)"),
        (1 / (n * log(n) * log(log(n)) * log(log(log(n)))**2), 4, "Insane Nested Logs (Integral Test)"),
        (log(n)**log(n) / n**log(n), 2, "ln(n)^ln(n) / n^ln(n) (Exp Decay)")
    ]

    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*115}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v6.0 - SEQUENCE CONVERGENCE TESTS':^115}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*115}")
    print(f"{'No.':<3} | {'Description':<38} | {'Result':<10} | {'Time (ms)':<9} | {'Details'}")
    print("-" * 115)
    
    total_seq_time = 0
    for i, (expr, desc) in enumerate(sequences, 1):
        start_t = time.perf_counter()
        is_conv, reason = check_sequence_convergence(expr, n)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_seq_time += elapsed_ms
        print(f"{i:<3} | {desc:<38} | {format_result(is_conv)} | {elapsed_ms:>6.1f} ms | {reason}")

    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*115}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v6.0 - SERIES CONVERGENCE TESTS':^115}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*115}")
    print(f"{'No.':<3} | {'Description':<38} | {'Result':<10} | {'Time (ms)':<9} | {'Details'}")
    print("-" * 115)
    
    total_ser_time = 0
    for i, (expr, start_idx, desc) in enumerate(series, 1):
        start_t = time.perf_counter()
        is_conv, reason = check_series_convergence(expr, n, start_idx)
        end_t = time.perf_counter()
        elapsed_ms = (end_t - start_t) * 1000
        total_ser_time += elapsed_ms
        print(f"{i:<3} | {desc:<38} | {format_result(is_conv)} | {elapsed_ms:>6.1f} ms | {reason}")

    print("\n" + "="*115)
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms")
    print("="*115)

if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    main()