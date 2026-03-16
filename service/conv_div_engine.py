import sympy as sp
import time
from colorama import init, Fore, Style
from sympy import Symbol, limit, oo, Sum, sin, cos, exp, log, factorial, sqrt, AccumBounds, pi
from sympy.series.limitseq import limit_seq

# Initialize Colorama
init(autoreset=True)

def fast_limit(expr, n):
    """Bypasses slow limit_seq unless factorials or discrete alternations are detected."""
    if expr.has(sp.factorial) or expr.has(sp.gamma) or expr.has((-1)**n):
        try:
            L = limit_seq(expr, n)
            if L is not None and not L.has(sp.Limit): return L
        except Exception: pass
    try:
        return limit(expr, n, oo)
    except Exception:
        return None

def check_sequence_convergence(expr, n):
    L = fast_limit(expr, n)
    if L is None or L.has(sp.Limit):
        return None, "Undetermined"
        
    if isinstance(L, AccumBounds) or L is sp.nan:
        return False, "Divergent (Oscillates or DNE)"
        
    if L.is_finite and L.is_real:
        return True, f"Converges to {L}"
    return False, f"Diverges to {L}"

def check_series_convergence(expr, n, start_idx=1):
    try:
        abs_n = sp.cancel(expr.subs((-1)**n, 1).subs((-1)**(n+1), 1).subs((-1)**(n-1), 1))
        
        # 1. DIVERGENCE TEST (nth-term)
        term_limit = fast_limit(expr, n)
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0:
                return False, f"Divergent (nth-term limit = {term_limit} != 0)"

        # 2. ALTERNATING & DIRICHLET (Fast Pattern Matching)
        if expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)):
            if fast_limit(abs_n, n) == 0:
                return True, "Convergent (Conditionally via Alternating Series Test)"
                
        if expr.has(sp.sin(n)) or expr.has(sp.cos(n)):
            rest = expr.subs(sp.sin(n), 1).subs(sp.cos(n), 1)
            if fast_limit(rest, n) == 0:
                return True, "Convergent (Conditionally via Dirichlet Test)"

        # 3. HARMONIC LIMIT COMPARISON TEST (Super Fast Divergence Catcher)
        lct_limit = fast_limit(sp.cancel(abs_n * n), n)
        if lct_limit is not None and not lct_limit.has(sp.Limit):
            if lct_limit == oo or (lct_limit.is_number and lct_limit > 0):
                return False, f"Divergent (Harmonic Limit Comparison L = {lct_limit})"

        # 4. ASYMPTOTIC LIMIT COMPARISON (Taylor Engine - Skipped for factorials)
        if not expr.has(sp.factorial):
            try:
                x = sp.Symbol('x', positive=True)
                expr_x = sp.cancel(abs_n.subs(sp.sin(n), 1).subs(sp.cos(n), 1).subs(n, 1/x))
                c, p = expr_x.leadterm(x)
                
                if p.is_number and not c.has(sp.log):
                    if p > 1: return True, f"Convergent (Taylor Asymptotic ~ 1/n^{p})"
                    if p <= 1 and p > 0: return False, f"Divergent (Taylor Asymptotic ~ 1/n^{p})"
            except Exception:
                pass

        # Detect characteristics for execution priority
        has_fact = expr.has(sp.factorial)
        has_n_exp = any(isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow))

        # 5. ROOT TEST (Executed FIRST if n is in the exponent)
        if has_n_exp and not has_fact:
            root_limit = fast_limit(sp.Pow(abs_n, 1/n), n)
            if root_limit is not None and root_limit.is_number and not root_limit.has(sp.Limit):
                if root_limit < 1: return True, f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 6. FAST RATIO TEST & GAUSS'S TEST
        if has_fact or has_n_exp:
            abs_next = abs_n.subs(n, n+1)
            # MAGIC WAND: combsimp reduces heavy factorials instantly before limiting
            ratio_expr = sp.cancel(sp.combsimp(abs_next / abs_n))
            
            ratio_limit = fast_limit(ratio_expr, n)
            if ratio_limit is not None and ratio_limit.is_number and not ratio_limit.has(sp.Limit):
                if ratio_limit < 1: return True, f"Convergent (Ratio L = {ratio_limit})"
                if ratio_limit > 1: return False, f"Divergent (Ratio L = {ratio_limit})"
                
                # GAUSS'S TEST (If Ratio == 1, evaluate the h-index directly)
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    h_expr = sp.cancel(n * (inv_ratio - 1))
                    h_limit = fast_limit(h_expr, n)
                    
                    if h_limit is not None and h_limit.is_number and not h_limit.has(sp.Limit):
                        if h_limit > 1: return True, f"Convergent (Gauss's h = {h_limit} > 1)"
                        if h_limit < 1: return False, f"Divergent (Gauss's h = {h_limit} < 1)"
                        # If Gauss's h-index is exactly 1 for factorial-based functions, it diverges!
                        if h_limit == 1 and not ratio_expr.has(sp.log):
                            return False, f"Divergent (Gauss's Test h = 1)"

        # 7. ROOT TEST (Executed LAST if not triggered above)
        if not has_n_exp:
            root_limit = fast_limit(sp.Pow(abs_n, 1/n), n)
            if root_limit is not None and root_limit.is_number and not root_limit.has(sp.Limit):
                if root_limit < 1: return True, f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 8. FINAL FALLBACK: Built-in SymPy Is_Convergent (Slowest)
        try:
            S = Sum(expr, (n, start_idx, oo))
            is_conv = S.is_convergent()
            if is_conv == sp.S.true: return True, "Convergent (Built-in SymPy)"
            if is_conv == sp.S.false: return False, "Divergent (Built-in SymPy)"
        except NotImplementedError:
            pass

        return None, "Undetermined by all available heuristics"
            
    except Exception as e:
        return None, f"Error calculating series: {str(e)}"

def format_result(res_bool):
    if res_bool is True:
        return f"{Fore.GREEN}{'Converges':<10}{Style.RESET_ALL}"
    elif res_bool is False:
        return f"{Fore.RED}{'Diverges':<10}{Style.RESET_ALL}"
    else:
        return f"{Fore.YELLOW}{'Unknown':<10}{Style.RESET_ALL}"

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
        (sp.sin(1/n)**2 * n**2, "n^2 * sin(1/n)^2")
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
        ((1 - 1/n)**(n**2), 2, "(1 - 1/n)^(n^2) (Heavy Root Test)")
    ]

    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*115}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v3.0 - SEQUENCE CONVERGENCE TESTS':^115}")
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
        res_str = format_result(is_conv)
        print(f"{i:<3} | {desc:<38} | {res_str} | {elapsed_ms:>6.1f} ms | {reason}")

    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*115}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v3.0 - SERIES CONVERGENCE TESTS':^115}")
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
        res_str = format_result(is_conv)
        print(f"{i:<3} | {desc:<38} | {res_str} | {elapsed_ms:>6.1f} ms | {reason}")

    print("\n" + "="*115)
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms")
    print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms")
    print("="*115)

if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    main()