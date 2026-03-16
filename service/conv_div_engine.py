import sympy as sp
import time
from colorama import init, Fore, Style
from sympy import Symbol, limit, oo, Sum, sin, cos, exp, log, factorial, sqrt, AccumBounds, pi
from sympy.series.limitseq import limit_seq

# Initialize Colorama
init(autoreset=True)

def apply_stirling(expr):
    """
    Replaces factorials with Stirling's continuous asymptotic approximation.
    n! ≈ sqrt(2*pi*n) * (n/e)^n
    This radically speeds up sequences at infinity compared to discrete logic.
    """
    return expr.replace(
        sp.factorial, 
        lambda arg: sp.sqrt(2 * sp.pi * arg) * (arg / sp.E)**arg
    )

def fast_limit(expr, n, use_stirling=True):
    """Bypasses slow limit_seq utilizing Stirling's approximation."""
    if use_stirling and expr.has(sp.factorial):
        try:
            stirling_expr = apply_stirling(expr)
            L = limit(stirling_expr, n, oo)
            if L is not None and not L.has(sp.Limit): 
                return L
        except Exception: 
            pass

    # Fallback to limit_seq for exact sequence methods or discrete alternations
    if expr.has(sp.gamma) or expr.has((-1)**n):
        try:
            L = limit_seq(expr, n)
            if L is not None and not L.has(sp.Limit): 
                return L
        except Exception: 
            pass

    try:
        return limit(expr, n, oo)
    except Exception:
        return None

def check_sequence_convergence(expr, n):
    # PRE-OPTIMIZATION: Try to instantly reduce exact factorial ratios first
    if expr.has(sp.factorial):
        try:
            simplified = sp.cancel(sp.combsimp(expr))
            if not simplified.has(sp.factorial):
                expr = simplified
        except Exception:
            pass
            
    L = fast_limit(expr, n, use_stirling=True)
    if L is None or L.has(sp.Limit):
        return None, "Undetermined"
        
    if isinstance(L, AccumBounds) or L is sp.nan:
        return False, "Divergent (Oscillates or DNE)"
        
    if L.is_finite and L.is_real:
        return True, f"Converges to {L}"
    return False, f"Diverges to {L}"

def check_series_convergence(expr, n, start_idx=1):
    try:
        # 1. OPTIMIZED ABS_N EXTRACTION (Dictionary sub avoids heavy expansion delays)
        abs_n = expr.subs({(-1)**n: 1, (-1)**(n+1): 1, (-1)**(n-1): 1})
        
        # Determine mathematical properties early to route tests intelligently
        has_fact = expr.has(sp.factorial)
        has_n_exp = any(isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow))

        # 2. DIVERGENCE TEST (nth-term)
        term_limit = fast_limit(expr, n, use_stirling=True)
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0:
                return False, f"Divergent (nth-term limit = {term_limit} != 0)"

        # 3. ALTERNATING & DIRICHLET (Fast Pattern Matching)
        if expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)):
            if fast_limit(abs_n, n, use_stirling=True) == 0:
                return True, "Convergent (Conditionally via Alternating Series Test)"
                
        if expr.has(sp.sin(n)) or expr.has(sp.cos(n)):
            rest = expr.subs({sp.sin(n): 1, sp.cos(n): 1})
            if fast_limit(rest, n, use_stirling=True) == 0:
                return True, "Convergent (Conditionally via Dirichlet Test)"

        # 4. ROOT TEST (Fast-tracked explicitly for n-exponents via Log Trick)
        if has_n_exp and not has_fact:
            # Logarithmic root test completely bypasses fraction symbolic exponentiation issues
            log_root_expr = sp.log(abs_n) / n
            log_root_limit = fast_limit(log_root_expr, n, use_stirling=True)
            if log_root_limit is not None and log_root_limit.is_number and not log_root_limit.has(sp.Limit):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1: return True, f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 5. RATIO & GAUSS'S TEST (Fast-tracked exclusively for Factorials)
        if has_fact:
            abs_next = abs_n.subs(n, n+1)
            # Combsimp reduces heavy factorials instantly and exactly
            ratio_expr = sp.cancel(sp.combsimp(abs_next / abs_n))
            
            # Exact algebra simplifies factorials, NO Stirling here to avoid precision loss on L=1
            ratio_limit = fast_limit(ratio_expr, n, use_stirling=False)
            if ratio_limit is not None and ratio_limit.is_number and not ratio_limit.has(sp.Limit):
                if ratio_limit < 1: return True, f"Convergent (Ratio L = {ratio_limit})"
                if ratio_limit > 1: return False, f"Divergent (Ratio L = {ratio_limit})"
                
                # GAUSS'S TEST (Evaluate the h-index explicitly)
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    h_expr = sp.cancel(n * (inv_ratio - 1))
                    h_limit = fast_limit(h_expr, n, use_stirling=False)
                    
                    if h_limit is not None and h_limit.is_number and not h_limit.has(sp.Limit):
                        if h_limit > 1: return True, f"Convergent (Gauss's h = {h_limit} > 1)"
                        if h_limit < 1: return False, f"Divergent (Gauss's h = {h_limit} < 1)"
                        if h_limit == 1 and not ratio_expr.has(sp.log):
                            return False, f"Divergent (Gauss's Test h = 1)"
            
            # CRITICAL LCT OPTIMIZATION: LCT always hangs on factorial limit bounds. 
            # If it has factorials, LCT is useless. Skip routing it entirely.

        # 6. HARMONIC LIMIT COMPARISON TEST (Executed only for standard algebra)
        if not has_fact:
            lct_limit = fast_limit(sp.cancel(abs_n * n), n, use_stirling=True)
            if lct_limit is not None and not lct_limit.has(sp.Limit):
                if lct_limit == oo or (lct_limit.is_number and lct_limit > 0):
                    return False, f"Divergent (Harmonic Limit Comparison L = {lct_limit})"

        # 7. ASYMPTOTIC LIMIT COMPARISON (Taylor Engine)
        if not has_fact:
            try:
                x = sp.Symbol('x', positive=True)
                # Dictionary substitution prevents heavy re-evaluation 
                expr_x = abs_n.subs({sp.sin(n): 1, sp.cos(n): 1, n: 1/x})
                c, p = expr_x.leadterm(x)
                
                if p.is_number and not c.has(sp.log):
                    if p > 1: return True, f"Convergent (Taylor Asymptotic ~ 1/n^{p})"
                    if p <= 1 and p > 0: return False, f"Divergent (Taylor Asymptotic ~ 1/n^{p})"
            except Exception:
                pass

        # 8. FALLBACK ROOT TEST (If limits got messy up top)
        if not has_n_exp and not has_fact:
            log_root_expr = sp.log(abs_n) / n
            log_root_limit = fast_limit(log_root_expr, n, use_stirling=True)
            if log_root_limit is not None and log_root_limit.is_number and not log_root_limit.has(sp.Limit):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1: return True, f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 9. FINAL FALLBACK: Built-in SymPy Integrals/Summations (Slowest)
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
    print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v4.0 - SEQUENCE CONVERGENCE TESTS':^115}")
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
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v4.0 - SERIES CONVERGENCE TESTS':^115}")
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