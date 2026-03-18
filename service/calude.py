import sympy as sp
import numpy as np
import time
from colorama import init, Fore, Style
from sympy import Symbol, limit, oo, Sum, sin, cos, exp, log, factorial, sqrt, AccumBounds, pi
from sympy.series.limitseq import limit_seq

init(autoreset=True)

# ─────────────────────────────────────────────────────────────────
#  TECHNIQUE TIMING TRACKER
# ─────────────────────────────────────────────────────────────────
class TechniqueTimer:
    def __init__(self):
        self.hits = {}   # technique -> [times]

    def record(self, name, ms):
        self.hits.setdefault(name, []).append(ms)

    def report(self):
        print(f"\n{'='*115}")
        print(f"{Fore.CYAN}{Style.BRIGHT}{'TECHNIQUE BREAKDOWN':^115}")
        print(f"{'='*115}")
        print(f"{'Technique':<40} | {'Hits':>5} | {'Total ms':>10} | {'Avg ms':>8} | {'Max ms':>8}")
        print("-"*115)
        for name, times in sorted(self.hits.items(), key=lambda x: -sum(x[1])):
            total = sum(times)
            avg   = total / len(times)
            mx    = max(times)
            print(f"{name:<40} | {len(times):>5} | {total:>10.2f} | {avg:>8.2f} | {mx:>8.2f}")
        print("="*115)

TIMER = TechniqueTimer()

# ─────────────────────────────────────────────────────────────────
#  NUMPY NUMERICAL PRE-SCREENER  (fast C-level shortcut)
# ─────────────────────────────────────────────────────────────────
def numpy_sequence_precheck(py_func):
    """
    Evaluate the sequence numerically at large n values.
    Returns (True/False/None, limit_approx_or_None).
    - True  -> numerically converges to a finite limit
    - False -> numerically diverges
    - None  -> inconclusive (hand off to SymPy)
    """
    t0 = time.perf_counter()
    try:
        ns = np.array([1e4, 2e4, 5e4, 1e5, 5e5, 1e6], dtype=np.float64)
        vals = np.array([py_func(n) for n in ns], dtype=np.float64)

        if not np.all(np.isfinite(vals)):
            TIMER.record("NumPy Pre-screen", (time.perf_counter()-t0)*1000)
            return False, None

        diffs = np.abs(np.diff(vals))
        if diffs[-1] < 1e-6 and diffs[-1] < diffs[0] * 0.01:
            TIMER.record("NumPy Pre-screen", (time.perf_counter()-t0)*1000)
            return True, float(vals[-1])

        if np.abs(vals[-1]) > 1e8 or (np.all(np.abs(np.diff(vals)) > 1e-2)):
            TIMER.record("NumPy Pre-screen", (time.perf_counter()-t0)*1000)
            return False, None

    except Exception:
        pass
    TIMER.record("NumPy Pre-screen", (time.perf_counter()-t0)*1000)
    return None, None


def numpy_series_precheck(py_func, start=1):
    """
    Partial-sum numerical test up to N=2000.
    Returns (True/False/None).
    """
    t0 = time.perf_counter()
    try:
        ns   = np.arange(start, 2001, dtype=np.float64)
        terms = np.array([py_func(n) for n in ns], dtype=np.float64)

        if not np.all(np.isfinite(terms)):
            TIMER.record("NumPy Series Pre-screen", (time.perf_counter()-t0)*1000)
            return None          # singular terms -> let SymPy handle

        # nth-term divergence: if last 50 terms are all > threshold
        tail = np.abs(terms[-50:])
        if np.all(tail > 1e-3):
            TIMER.record("NumPy Series Pre-screen", (time.perf_counter()-t0)*1000)
            return False

        # partial sums
        psums = np.cumsum(terms)
        tail_sums = psums[-100:]
        spread = np.max(tail_sums) - np.min(tail_sums)
        if spread < 1e-4:
            TIMER.record("NumPy Series Pre-screen", (time.perf_counter()-t0)*1000)
            return True
        if np.abs(psums[-1]) > 1e6 or np.abs(psums[-1] - psums[-50]) > 10:
            TIMER.record("NumPy Series Pre-screen", (time.perf_counter()-t0)*1000)
            return False

    except Exception:
        pass
    TIMER.record("NumPy Series Pre-screen", (time.perf_counter()-t0)*1000)
    return None


# ─────────────────────────────────────────────────────────────────
#  SYMPY CORE (unchanged logic, timing instrumented)
# ─────────────────────────────────────────────────────────────────
def apply_stirling(expr):
    stirling_expr = expr.replace(
        sp.factorial,
        lambda arg: sp.sqrt(2 * sp.pi * arg) * (arg / sp.E)**arg
    )
    stirling_expr = sp.expand_power_base(stirling_expr, force=True)
    return sp.cancel(sp.powsimp(stirling_expr, force=True))


def super_fast_limit(expr, n):
    # 1. Asymptotic LeadTerm
    if not expr.has(sp.factorial) and not expr.has(sp.gamma):
        t0 = time.perf_counter()
        try:
            x = sp.Symbol('x', positive=True)
            expr_x = expr.subs(n, 1/x)
            c, p = expr_x.leadterm(x)
            if not c.has(sp.O) and not p.has(sp.O) and not c.has(x):
                if p > 0:
                    TIMER.record("LeadTerm Asymptotic", (time.perf_counter()-t0)*1000)
                    return sp.S(0)
                if p < 0:
                    TIMER.record("LeadTerm Asymptotic", (time.perf_counter()-t0)*1000)
                    return oo * sp.sign(c)
                if p == 0:
                    c_lim = limit(c, x, 0)
                    if c_lim.is_number:
                        TIMER.record("LeadTerm Asymptotic", (time.perf_counter()-t0)*1000)
                        return c_lim
        except Exception:
            pass
        TIMER.record("LeadTerm Asymptotic", (time.perf_counter()-t0)*1000)

    # 2. Stirling/Gamma
    if expr.has(sp.factorial) or expr.has(sp.gamma):
        t0 = time.perf_counter()
        try:
            s_expr = apply_stirling(expr)
            log_s  = sp.expand_log(sp.log(s_expr), force=True)
            L_log  = limit(log_s, n, oo)
            if L_log is not None and not L_log.has(sp.Limit):
                TIMER.record("Stirling Log-Limit", (time.perf_counter()-t0)*1000)
                return sp.exp(L_log)
        except Exception:
            pass
        TIMER.record("Stirling Log-Limit", (time.perf_counter()-t0)*1000)

    # 3. limit_seq for oscillating / gamma
    t0 = time.perf_counter()
    try:
        if expr.has(sp.gamma) or expr.has((-1)**n):
            L = limit_seq(expr, n)
            if L is not None and not L.has(sp.Limit):
                TIMER.record("limit_seq", (time.perf_counter()-t0)*1000)
                return L
    except Exception:
        pass
    TIMER.record("limit_seq", (time.perf_counter()-t0)*1000)

    # 4. SymPy standard limit
    t0 = time.perf_counter()
    try:
        result = limit(expr, n, oo)
        TIMER.record("SymPy limit()", (time.perf_counter()-t0)*1000)
        return result
    except Exception:
        pass
    TIMER.record("SymPy limit()", (time.perf_counter()-t0)*1000)
    return None


def check_sequence_convergence(expr, n, py_func=None):
    # NumPy fast path
    if py_func is not None:
        conv, approx = numpy_sequence_precheck(py_func)
        if conv is True:
            sym_val = super_fast_limit(expr, n)
            label = str(sym_val) if (sym_val and sym_val.is_finite) else f"~{approx:.6g}"
            return True, f"Converges to {label}"
        if conv is False:
            return False, "Diverges (NumPy numerical)"

    if expr.has(sp.factorial):
        try:
            simplified = sp.cancel(sp.combsimp(expr))
            if not simplified.has(sp.factorial):
                expr = simplified
        except Exception:
            pass

    L = super_fast_limit(expr, n)
    if L is None or L.has(sp.Limit):
        return None, "Undetermined"
    if isinstance(L, AccumBounds) or L is sp.nan:
        return False, "Divergent (Oscillates or DNE)"
    if L.is_finite and L.is_real:
        return True, f"Converges to {L}"
    return False, f"Diverges to {L}"


def check_series_convergence(expr, n, start_idx=1, py_func=None):
    try:
        # NumPy fast path
        if py_func is not None:
            verdict = numpy_series_precheck(py_func, start_idx)
            if verdict is True:
                return True, "Convergent (NumPy partial-sum)"
            if verdict is False:
                # still verify with nth-term before declaring divergent
                pass   # fall through to symbolic

        abs_n    = expr.subs({(-1)**n: 1, (-1)**(n+1): 1, (-1)**(n-1): 1})
        has_fact = expr.has(sp.factorial)
        has_n_exp = any(isinstance(arg, sp.Pow) and arg.exp.has(n)
                        for arg in expr.atoms(sp.Pow))

        # 1. Divergence test
        t0 = time.perf_counter()
        term_limit = super_fast_limit(expr, n)
        TIMER.record("Divergence Test", (time.perf_counter()-t0)*1000)
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0:
                return False, f"Divergent (nth-term limit = {term_limit} != 0)"

        # 2. Absolute convergence check then Alternating / Dirichlet
        is_alternating = (expr.has((-1)**n) or expr.has((-1)**(n+1)) or expr.has((-1)**(n-1)))
        if is_alternating and not has_fact:
            try:
                x      = sp.Symbol('x', positive=True)
                expr_x = abs_n.subs(n, 1/x)
                c, p   = expr_x.leadterm(x)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number and p > 1:
                    return True, f"Convergent (Absolutely, p-test ~ 1/n^{p})"
            except Exception:
                pass
        if is_alternating:
            if super_fast_limit(abs_n, n) == 0:
                return True, "Convergent (Conditionally via Alternating Test)"
        if expr.has(sp.sin(n)) or expr.has(sp.cos(n)):
            rest = expr.subs({sp.sin(n): 1, sp.cos(n): 1})
            if super_fast_limit(rest, n) == 0:
                return True, "Convergent (Conditionally via Dirichlet Test)"

        # 3. Asymptotic p-test
        if not has_fact:
            t0 = time.perf_counter()
            try:
                x      = sp.Symbol('x', positive=True)
                expr_x = abs_n.subs({sp.sin(n): 1, sp.cos(n): 1, n: 1/x})
                c, p   = expr_x.leadterm(x)
                if not c.has(sp.O) and not p.has(sp.O):
                    if p.is_number:
                        TIMER.record("Asymptotic p-test", (time.perf_counter()-t0)*1000)
                        if p > 1: return True,  f"Convergent (Asymptotic p-test ~ 1/n^{p})"
                        if p < 1 and not c.has(sp.log): return False, f"Divergent (Asymptotic p-test ~ 1/n^{p})"
                        if p == 1 and not c.has(sp.log): return False, f"Divergent (Asymptotic harmonic p=1)"
            except Exception:
                pass
            TIMER.record("Asymptotic p-test", (time.perf_counter()-t0)*1000)

        # 4. Integral test
        if not has_fact and abs_n.has(sp.log):
            t0 = time.perf_counter()
            try:
                x_sym = sp.Symbol('x', positive=True)
                res   = sp.integrate(abs_n.subs(n, x_sym), (x_sym, 3, oo))
                TIMER.record("Integral Test", (time.perf_counter()-t0)*1000)
                if res.is_number:
                    if res.is_finite: return True,  "Convergent (Integral Test)"
                    else:             return False, "Divergent (Integral Test)"
            except Exception:
                TIMER.record("Integral Test", (time.perf_counter()-t0)*1000)

        # 5. Root test (log-expanded)
        if has_n_exp and not has_fact:
            t0 = time.perf_counter()
            log_root_expr  = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n)
            TIMER.record("Root Test", (time.perf_counter()-t0)*1000)
            if (log_root_limit is not None and log_root_limit.is_number
                    and not log_root_limit.has(sp.Limit)):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1: return True,  f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 6. Ratio + Gauss test
        if has_fact:
            t0 = time.perf_counter()
            ratio_expr  = sp.cancel(sp.combsimp(abs_n.subs(n, n+1) / abs_n))
            ratio_limit = super_fast_limit(ratio_expr, n)
            TIMER.record("Ratio Test", (time.perf_counter()-t0)*1000)
            if (ratio_limit is not None and ratio_limit.is_number
                    and not ratio_limit.has(sp.Limit)):
                if ratio_limit < 1: return True,  f"Convergent (Ratio L = {ratio_limit})"
                if ratio_limit > 1: return False, f"Divergent (Ratio L = {ratio_limit})"
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    x = sp.Symbol('x', positive=True)
                    t0 = time.perf_counter()
                    try:
                        c, p = (inv_ratio.subs(n, 1/x) - 1).leadterm(x)
                        if p == 1:
                            h = limit(c, x, 0)
                            TIMER.record("Gauss/Raabe Test", (time.perf_counter()-t0)*1000)
                            if h > 1: return True,  f"Convergent (Gauss/Raabe h = {h} > 1)"
                            if h < 1: return False, f"Divergent (Gauss/Raabe h = {h} < 1)"
                            if h == 1: return False, f"Divergent (Gauss h = 1 boundaries)"
                    except Exception:
                        TIMER.record("Gauss/Raabe Test", (time.perf_counter()-t0)*1000)

        # 7. Root fallback
        if not has_n_exp and not has_fact:
            t0 = time.perf_counter()
            log_root_expr  = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n)
            TIMER.record("Root Test (fallback)", (time.perf_counter()-t0)*1000)
            if (log_root_limit is not None and log_root_limit.is_number
                    and not log_root_limit.has(sp.Limit)):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1: return True,  f"Convergent (Root L = {root_limit})"
                if root_limit > 1: return False, f"Divergent (Root L = {root_limit})"

        # 8. SymPy built-in
        t0 = time.perf_counter()
        try:
            S        = Sum(expr, (n, start_idx, oo))
            is_conv  = S.is_convergent()
            TIMER.record("SymPy Sum.is_convergent()", (time.perf_counter()-t0)*1000)
            if is_conv == sp.S.true:  return True,  "Convergent (Built-in SymPy)"
            if is_conv == sp.S.false: return False, "Divergent (Built-in SymPy)"
        except NotImplementedError:
            TIMER.record("SymPy Sum.is_convergent()", (time.perf_counter()-t0)*1000)

        return None, "Undetermined by all available heuristics"

    except Exception as e:
        return None, f"Error: {str(e)}"


# ─────────────────────────────────────────────────────────────────
#  FORMATTING
# ─────────────────────────────────────────────────────────────────
def format_result(res_bool):
    if res_bool is True:  return f"{Fore.GREEN}{'Converges':<10}{Style.RESET_ALL}"
    if res_bool is False: return f"{Fore.RED}{'Diverges':<10}{Style.RESET_ALL}"
    return f"{Fore.YELLOW}{'Unknown':<10}{Style.RESET_ALL}"


# ─────────────────────────────────────────────────────────────────
#  MAIN
def main():
    n = sp.Symbol('n', integer=True, positive=True)
    import math

    # ══════════════════════════════════════════════════════════════
    # SEQUENCES  (expr, description, python_lambda | None)
    # ══════════════════════════════════════════════════════════════
    sequences = [

        # ── CLASSIC LIMITS ────────────────────────────────────────
        (sp.cos(2/n)**(n**2),
         "cos(2/n)^(n^2)  [→ e^-2]",
         lambda n: math.cos(2/n)**(n**2)),

        ((n/sp.log(n))*(n**(sp.S(1)/n)-1),
         "n/ln(n)*(n^(1/n)-1)  [→ 1]",
         lambda n: (n/math.log(n))*(n**(1/n)-1)),

        (sp.sqrt(n+sp.sqrt(n))-sp.sqrt(n),
         "√(n+√n)-√n  [→ 1/2]",
         lambda n: math.sqrt(n+math.sqrt(n))-math.sqrt(n)),

        (sp.sqrt(n**2+3*n)-n,
         "√(n²+3n)-n  [→ 3/2]",
         lambda n: math.sqrt(n**2+3*n)-n),

        (sp.sqrt(n**2+n)-n,
         "√(n²+n)-n  [→ 1/2]",
         lambda n: math.sqrt(n**2+n)-n),

        (n*(sp.exp(sp.S(1)/n)-1),
         "n(e^(1/n)-1)  [→ 1]",
         lambda n: n*(math.exp(1/n)-1)),

        (sp.sin(sp.S(1)/n)*n,
         "n·sin(1/n)  [→ 1]",
         lambda n: n*math.sin(1/n)),

        (n**(sp.S(1)/n),
         "n^(1/n)  [→ 1]",
         lambda n: n**(1/n)),

        (sp.log(n+1)-sp.log(n),
         "ln(n+1)-ln(n)  [→ 0]",
         lambda n: math.log(n+1)-math.log(n)),

        ((sp.log(n+1)-sp.log(n))*n,
         "n·(ln(n+1)-ln(n))  [→ 1]",
         lambda n: n*(math.log(n+1)-math.log(n))),

        (n*(1-sp.cos(sp.S(1)/n)),
         "n*(1-cos(1/n))  [→ 0]",
         lambda n: n*(1-math.cos(1/n))),

        (n**2*(1-sp.cos(sp.S(1)/n)),
         "n²(1-cos(1/n))  [→ 1/2]",
         lambda n: n**2*(1-math.cos(1/n))),

        (n*(1-sp.cos(sp.S(1)/n**2)),
         "n(1-cos(1/n²))  [→ 0]",
         lambda n: n*(1-math.cos(1/n**2))),

        # ── EXPONENTIAL / POWER LIMITS ───────────────────────────
        (((n**2+1)/(n**2-1))**(n**2),
         "((n²+1)/(n²-1))^n²  [→ e²]",
         lambda n: ((n**2+1)/(n**2-1))**(n**2)),

        ((1+sp.S(1)/n)**(n**2),
         "(1+1/n)^(n^2)  [→ ∞ Exp explosion]",
         lambda n: (1+1/n)**(n**2)),

        ((1+sp.S(2)/n+sp.S(3)/n**2)**n,
         "(1+2/n+3/n²)^n  [→ e²]",
         lambda n: (1+2/n+3/n**2)**n),

        ((1-sp.S(2)/n)**(3*n),
         "(1-2/n)^(3n)  [→ e^-6]",
         lambda n: (1-2/n)**(3*n)),

        ((1-sp.S(1)/n**2)**n,
         "(1-1/n²)^n  [→ 1]",
         lambda n: (1-1/n**2)**n),

        (sp.cos(sp.S(1)/n)**(n**2),
         "cos(1/n)^(n^2)  [→ e^(-1/2)]",
         lambda n: math.cos(1/n)**(n**2)),

        ((1+sp.S(1)/n**2)**(n**2),
         "(1+1/n²)^(n^2)  [→ e]",
         lambda n: (1+1/n**2)**(n**2)),

        (((1+sp.S(1)/n)**(n**2))/sp.exp(n),
         "(1+1/n)^(n^2)/e^n  [→ e^(-1/2)]",
         lambda n: (1+1/n)**(n**2)/math.exp(n)),

        ((1+sp.sin(sp.S(1)/n)/n)**(n**2),
         "(1+sin(1/n)/n)^(n^2)  [Tricky Exp → e]",
         lambda n: (1+math.sin(1/n)/n)**(n**2)),

        ((1+sp.log(n)/n)**n,
         "(1+ln(n)/n)^n  [→ ∞]",
         lambda n: (1+math.log(n)/n)**n),

        # ── FACTORIAL / STIRLING ─────────────────────────────────
        (sp.factorial(n)**(sp.S(1)/n)/n,
         "(n!)^(1/n)/n  Stirling  [→ e⁻¹]",
         lambda n: math.exp(math.lgamma(n+1)/n-math.log(n))),

        (sp.factorial(n)**(sp.S(1)/n**2),
         "(n!)^(1/n^2)  [→ 1]",
         lambda n: math.exp(math.lgamma(n+1)/n**2)),

        ((sp.factorial(2*n))**(sp.S(1)/(2*n))/n,
         "(2n!)^(1/2n)/n  Stirling  [→ 4/e²]",
         lambda n: math.exp(math.lgamma(2*n+1)/(2*n)-math.log(n))),

        ((sp.factorial(2*n))**(sp.S(1)/n)/(sp.S(4)**n/n),
         "(2n!)^(1/n)/(4^n/n)  [→ 0]",
         lambda n: math.exp(math.lgamma(2*n+1)/n - n*math.log(4) + math.log(n))),

        (sp.factorial(n)/sp.S(100)**n,
         "n!/100^n  [→ ∞ Heavy Growth]",
         lambda n: math.exp(math.lgamma(n+1)-n*math.log(100)) if n < 500 else float('inf')),

        (sp.factorial(n)**2/sp.factorial(2*n),
         "(n!)^2/(2n)!  [→ 0]",
         lambda n: math.exp(2*math.lgamma(n+1)-math.lgamma(2*n+1))),

        ((2*n*sp.factorial(n))**2/sp.factorial(2*n+1),
         "(2n·n!)^2/(2n+1)!  [→ 0]",
         lambda n: math.exp(2*math.log(2*n)+2*math.lgamma(n+1)-math.lgamma(2*n+2))),

        (sp.factorial(2*n)/(sp.factorial(n)*(2*n)**(n+sp.S(1)/2)),
         "(2n)!/(n!*(2n)^(n+1/2))  Stirling",
         lambda n: math.exp(math.lgamma(2*n+1)-math.lgamma(n+1)-(n+0.5)*math.log(2*n))),

        (((2**( 4*n)*sp.factorial(n)**4)/(sp.factorial(2*n)**2*(2*n+1))),
         "Wallis Product → π/2",
         lambda n: math.exp(4*n*math.log(2)+4*math.lgamma(n+1)-2*math.lgamma(2*n+1)-math.log(2*n+1))),

        # ── GAMMA ────────────────────────────────────────────────
        (sp.gamma(n+sp.S(1)/2)/(sp.sqrt(n)*sp.gamma(n)),
         "Γ(n+1/2)/(√n·Γ(n))  Gamma Asymptotics",
         lambda n: math.exp(math.lgamma(n+0.5)-0.5*math.log(n)-math.lgamma(n))),

        (sp.gamma(n+sp.S(3)/2)/(sp.sqrt(n)*sp.gamma(n+1)),
         "Γ(n+3/2)/(√n·n!)  [→ 1]",
         lambda n: math.exp(math.lgamma(n+1.5)-0.5*math.log(n)-math.lgamma(n+1))),

        # ── TAYLOR / SERIES EXPANSIONS ───────────────────────────
        (n**2*(sp.exp(sp.S(1)/n)-1-sp.S(1)/n),
         "n²(e^(1/n)-1-1/n)  Taylor Trap  [→ 1/2]",
         lambda n: n**2*(math.exp(1/n)-1-1/n)),

        (n**3*(sp.sin(sp.S(1)/n)-sp.S(1)/n+sp.S(1)/(6*n**3)),
         "n³(sin(1/n)-1/n+1/(6n³))  [→ -1/120]",
         lambda n: n**3*(math.sin(1/n)-1/n+1/(6*n**3))),

        (n**2*(sp.log(1+sp.S(1)/n)-sp.sin(sp.S(1)/n)),
         "n²(ln(1+1/n)-sin(1/n))  [→ -1/2]",
         lambda n: n**2*(math.log(1+1/n)-math.sin(1/n))),

        (n*(sp.exp(sp.S(1)/n)-sp.cos(sp.S(1)/n)),
         "n*(e^(1/n)-cos(1/n))  [→ 1]",
         lambda n: n*(math.exp(1/n)-math.cos(1/n))),

        # ── LOG / SUB-EXPONENTIAL ────────────────────────────────
        (sp.log(n)**sp.log(n)/n,
         "ln(n)^ln(n)/n  [→ 0, Tower vs Poly]",
         lambda n: math.exp(math.log(math.log(n))*math.log(n)-math.log(n)) if n > 2 else 1),

        (sp.log(n)**sp.log(sp.log(n))/n,
         "ln(n)^ln(ln(n))/n  [→ 0]",
         lambda n: math.exp(math.log(math.log(n))*math.log(math.log(n))-math.log(n)) if n > 2 else 1),

        (n**sp.log(n)/sp.S(2)**n,
         "n^ln(n)/2^n  [→ 0 Sub-exponential]",
         lambda n: math.exp(math.log(n)**2 - n*math.log(2))),

        (sp.log(n+sp.log(n))-sp.log(n),
         "ln(n+ln(n))-ln(n)  [→ 0]",
         lambda n: math.log(n+math.log(n))-math.log(n) if n > 1 else 0),

        (n**(sp.S(1)/sp.log(sp.log(n))),
         "n^(1/ln(ln(n)))  [→ ∞]",
         lambda n: math.exp(math.log(n)/math.log(math.log(n))) if n > 2 else 1),

        (sp.log(n),
         "ln(n)  [→ ∞  DIVERGES]",
         lambda n: math.log(n)),

        (n*sp.sin(sp.S(1)/n)*sp.log(n),
         "n·sin(1/n)·ln(n)  [→ ∞  DIVERGES]",
         lambda n: n*math.sin(1/n)*math.log(n)),

        (sp.sqrt(n)*(n**(sp.S(1)/n)-1),
         "√n·(n^(1/n)-1)  [→ 0, ~ln(n)/√n]",
         lambda n: math.sqrt(n)*(n**(1/n)-1)),

        # ── OSCILLATORY ──────────────────────────────────────────
        (n*sp.sin(n),
         "n·sin(n)  [Oscillatory Unbounded]",
         None),

        ((-1)**n*(n/(n+1)),
         "(-1)^n·n/(n+1)  [oscillates, DNE]",
         None),

        ((-1)**n*n/(n**2+1)+sp.S(1)/2,
         "(-1)^n·n/(n²+1)+1/2  [→ 1/2]",
         None),

        (n**2*sp.sin(n)/(n**3+1),
         "n²sin(n)/(n³+1)  [→ 0 bounded/decay]",
         None),

        (sp.sin(n*sp.pi/2)/n,
         "sin(nπ/2)/n  [→ 0]",
         None),

        (n*sp.sin(sp.pi/n),
         "n·sin(π/n)  [→ π]",
         lambda n: n*math.sin(math.pi/n)),
    ]

    # ══════════════════════════════════════════════════════════════
    # SERIES  (expr, start_idx, description, python_lambda | None)
    # ══════════════════════════════════════════════════════════════
    series = [

        # ── CLASSIC p-SERIES / HARMONIC ──────────────────────────
        (sp.S(1)/n, 1,
         "1/n  harmonic  [DIV]",
         lambda n: 1/n),

        (sp.S(1)/n**2, 1,
         "1/n²  p=2  [conv]",
         lambda n: 1/n**2),

        (sp.S(1)/sp.sqrt(n), 1,
         "1/√n  p=1/2  [DIV]",
         lambda n: 1/math.sqrt(n)),

        (sp.S(1)/n**(sp.S(10001)/10000), 1,
         "1/n^1.0001  Poly Edge Trap  [conv]",
         lambda n: 1/n**1.0001),

        (sp.S(1)/(n**(1+sp.S(1)/sp.log(n))), 2,
         "1/n^(1+1/lnn)  Log Trap  [DIV]",
         lambda n: 1/(n**(1+1/math.log(n)))),

        # ── BERTRAND / LOG-REFINEMENTS ───────────────────────────
        (sp.S(1)/(n*sp.log(n)), 2,
         "1/(n·lnn)  Bertrand p=1  [DIV]",
         lambda n: 1/(n*math.log(n))),

        (sp.S(1)/(n*sp.log(n)**sp.S(11)/10), 2,
         "1/(n·ln(n)^1.1)  [conv]",
         lambda n: 1/(n*math.log(n)**1.1)),

        (sp.S(1)/(n*sp.log(n)**2), 2,
         "1/(n·ln²n)  Bertrand p=2  [conv]",
         lambda n: 1/(n*math.log(n)**2)),

        (sp.S(1)/(n*sp.log(n)**sp.S(3)/2), 2,
         "1/(n·ln(n)^1.5)  [conv]",
         lambda n: 1/(n*math.log(n)**1.5)),

        (sp.S(1)/(n*sp.log(n)*sp.log(sp.log(n))), 3,
         "1/(n·lnn·ln(lnn))  [DIV]",
         lambda n: 1/(n*math.log(n)*math.log(math.log(n))) if n > 2 else 0),

        (sp.S(1)/(n*sp.log(n)*sp.log(sp.log(n))**2), 3,
         "1/(n·lnn·(lnlnn)²)  Bertrand  [conv]",
         lambda n: 1/(n*math.log(n)*math.log(math.log(n))**2) if n > 2 else 0),

        (sp.S(1)/(n*sp.log(n)**2*sp.log(sp.log(n))), 3,
         "1/(n·ln²(n)·ln(ln(n)))  [conv]",
         lambda n: 1/(n*math.log(n)**2*math.log(math.log(n))) if n > 2 else 0),

        (sp.S(1)/(n*sp.log(n)*sp.log(sp.log(n))**sp.S(1)/2), 3,
         "1/(n·ln·ln(ln)^0.5)  [DIV]",
         lambda n: 1/(n*math.log(n)*math.log(math.log(n))**0.5) if n > 2 else 0),

        # ── LOG / TOWER ──────────────────────────────────────────
        (sp.log(n)/n, 1,
         "lnn/n  [DIV ~harmonic]",
         lambda n: math.log(n)/n),

        (sp.log(n)**sp.log(n)/n, 2,
         "ln(n)^ln(n)/n  [Tower vs Poly]",
         lambda n: math.exp(math.log(math.log(n))*math.log(n)-math.log(n)) if n > 2 else 1),

        (sp.log(n)**sp.log(n)/n**sp.log(n), 2,
         "ln(n)^ln(n)/n^ln(n)",
         lambda n: math.exp(math.log(math.log(n))*math.log(n)-math.log(n)**2) if n > 2 else 1),

        (sp.log(n)**sp.log(n)/n**2, 2,
         "ln(n)^ln(n)/n²  [DIV terms→∞]",
         lambda n: math.exp(math.log(math.log(n))*math.log(n)-2*math.log(n)) if n > 2 else 1),

        (sp.log(n)**sp.log(n)/10**n, 2,
         "ln(n)^ln(n)/10^n  [Root conv]",
         lambda n: math.exp(math.log(math.log(n))*math.log(n)-n*math.log(10)) if n > 2 else 1),

        (sp.log(n)**n/sp.factorial(n), 1,
         "ln(n)^n/n!  [Ratio→0 conv]",
         lambda n: math.exp(n*math.log(math.log(n))-math.lgamma(n+1)) if n > 1 else 0),

        # ── GEOMETRIC / EXPONENTIAL ──────────────────────────────
        (sp.exp(-n), 1,
         "e^(-n)  geometric  [conv]",
         lambda n: math.exp(-n)),

        (sp.exp(-sp.sqrt(n)), 1,
         "e^(-√n)  [conv]",
         lambda n: math.exp(-math.sqrt(n))),

        (sp.exp(-n**2), 1,
         "e^(-n²)  Gaussian  [conv]",
         lambda n: math.exp(-n**2)),

        (n**2/sp.exp(n), 1,
         "n²/e^n  [conv]",
         lambda n: n**2*math.exp(-n)),

        # ── FACTORIAL / RATIO TEST ───────────────────────────────
        (sp.S(1)/sp.factorial(n), 1,
         "1/n!  [conv → e-1]",
         lambda n: 1/math.factorial(int(n)) if n < 170 else 0),

        (sp.factorial(n)/n**n, 1,
         "n!/n^n  [Ratio e⁻¹ conv]",
         lambda n: math.exp(math.lgamma(n+1)-n*math.log(n))),

        (sp.factorial(n)**2/sp.factorial(2*n), 1,
         "(n!)²/(2n)!  [Ratio 1/4 conv]",
         lambda n: math.exp(2*math.lgamma(n+1)-math.lgamma(2*n+1))),

        (sp.factorial(n)**3/sp.factorial(3*n), 1,
         "(n!)³/(3n)!  [conv]",
         lambda n: math.exp(3*math.lgamma(n+1)-math.lgamma(3*n+1))),

        (sp.factorial(n)**2/sp.factorial(2*n+1), 1,
         "n!·n!/(2n+1)!  [conv]",
         lambda n: math.exp(2*math.lgamma(n+1)-math.lgamma(2*n+2))),

        (sp.factorial(2*n)/(sp.factorial(n)**2*4**n), 1,
         "(2n)!/(n!)²·4^n  Wallis  [DIV]",
         lambda n: math.exp(math.lgamma(2*n+1)-2*math.lgamma(n+1)-n*math.log(4))),

        (sp.factorial(3*n)/(sp.factorial(n)*sp.factorial(2*n)*3**n), 1,
         "(3n)!/(n!(2n)!3^n)  [DIV]",
         lambda n: math.exp(math.lgamma(3*n+1)-math.lgamma(n+1)-math.lgamma(2*n+1)-n*math.log(3))),

        (sp.factorial(3*n)/(sp.factorial(n)**3*27**n), 1,
         "(3n)!/(n!³·27^n)  Gauss h=1  [DIV]",
         lambda n: math.exp(math.lgamma(3*n+1)-3*math.lgamma(n+1)-n*math.log(27))),

        ((sp.factorial(n)*sp.exp(n))/n**(n+sp.S(1)/2), 1,
         "n!·e^n/n^(n+1/2)  Gauss  [→ √(2π)]",
         lambda n: math.exp(math.lgamma(n+1)+n-( n+0.5)*math.log(n))),

        # ── TRIGONOMETRIC ────────────────────────────────────────
        (sp.sin(sp.S(1)/n), 1,
         "sin(1/n)  [~harmonic DIV]",
         lambda n: math.sin(1/n)),

        (1-sp.cos(sp.S(1)/n), 1,
         "1-cos(1/n)  [~1/n² conv]",
         lambda n: 1-math.cos(1/n)),

        (sp.sin(sp.S(1)/n)**2, 1,
         "sin²(1/n)  [~1/n² conv]",
         lambda n: math.sin(1/n)**2),

        (sp.sin(n)/n, 1,
         "sin(n)/n  Dirichlet  [cond. conv]",
         None),

        # ── ROOT TEST ────────────────────────────────────────────
        ((n/(n+1))**(n**2), 1,
         "(n/(n+1))^n²  [Root e⁻¹ conv]",
         lambda n: (n/(n+1))**(n**2)),

        ((n/(n+1))**n, 1,
         "(n/(n+1))^n  [Nth term→e⁻¹ conv]",
         lambda n: (n/(n+1))**n),

        (((2*n+1)/(3*n-1))**n, 1,
         "((2n+1)/(3n-1))^n  [Root→2/3 conv]",
         lambda n: ((2*n+1)/(3*n-1))**n),

        ((n/(n+sp.log(n)))**n, 2,
         "(n/(n+ln(n)))^n  [Root L=1 DIV]",
         lambda n: (n/(n+math.log(n)))**n),

        (sp.log(n)**n/n**n, 2,
         "ln(n)^n/n^n  [Root→0 conv]",
         lambda n: (math.log(n)/n)**n if n > 1 else 0),

        (n**(n+sp.S(1)/n)/(n+sp.S(1)/n)**n, 1,
         "n^(n+1/n)/(n+1/n)^n  Heavy Base",
         lambda n: math.exp((n+1/n)*math.log(n)-n*math.log(n+1/n))),

        ((4*n**2)/(4*n**2-1), 1,
         "Wallis product terms  [DIV →1]",
         lambda n: (4*n**2)/(4*n**2-1)),

        # ── ALTERNATING ──────────────────────────────────────────
        ((-1)**n*sp.log(n)/n, 2,
         "(-1)^n·ln(n)/n  [Cond. conv]",
         None),

        ((-1)**n/n**2, 1,
         "(-1)^n/n²  [Abs. conv]",
         None),

        ((-1)**n/sp.sqrt(n), 1,
         "(-1)^n/√n  Alternating  [cond. conv]",
         None),

        ((-1)**n/( n+sp.log(n)), 2,
         "(-1)^n/(n+ln(n))  [Cond. conv]",
         None),

        ((-1)**n*sp.sqrt(n)/(n+100), 1,
         "(-1)^n·√n/(n+100)  [cond. conv]",
         None),

        ((-1)**n*sp.log(n)/n**sp.S(3)/2, 2,
         "(-1)^n·ln(n)/n^(3/2)  [Abs. conv]",
         None),

        ((-1)**n*(1-sp.S(1)/n)**n, 1,
         "(-1)^n·(1-1/n)^n  [DIV nth-term]",
         None),

        # ── TELESCOPE / SQRT ─────────────────────────────────────
        (sp.sqrt(n+1)-sp.sqrt(n), 1,
         "√(n+1)-√n  Telescope  [DIV]",
         lambda n: math.sqrt(n+1)-math.sqrt(n)),

        (sp.S(1)/(n**sp.S(1)+sp.sin(sp.S(1)/n)), 1,
         "1/n^(1+sin(1/n))  [DIV]",
         lambda n: 1/n**(1+math.sin(1/n))),

        (sp.S(1)/(n**(sp.S(1)+sp.S(1)/n)), 2,
         "1/n^(1+1/n)  [DIV →harmonic]",
         lambda n: 1/n**(1+1/n)),
    ]

    # ── PRINT SEQUENCES ──────────────────────────────────────────
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*115}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE - SEQUENCE CONVERGENCE TESTS':^115}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'='*115}")
    print(f"{'No.':<3} | {'Description':<46} | {'Result':<10} | {'Time (ms)':>9} | {'Details'}")
    print("-"*115)

    total_seq_time = 0
    for i, (expr, desc, py_func) in enumerate(sequences, 1):
        t0 = time.perf_counter()
        is_conv, reason = check_sequence_convergence(expr, n, py_func)
        elapsed = (time.perf_counter()-t0)*1000
        total_seq_time += elapsed
        print(f"{i:<3} | {desc:<46} | {format_result(is_conv)} | {elapsed:>7.1f} ms | {reason}")

    # ── PRINT SERIES ─────────────────────────────────────────────
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'='*115}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE - SERIES CONVERGENCE TESTS':^115}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'='*115}")
    print(f"{'No.':<3} | {'Description':<46} | {'Result':<10} | {'Time (ms)':>9} | {'Details'}")
    print("-"*115)

    total_ser_time = 0
    for i, (expr, start_idx, desc, py_func) in enumerate(series, 1):
        t0 = time.perf_counter()
        is_conv, reason = check_series_convergence(expr, n, start_idx, py_func)
        elapsed = (time.perf_counter()-t0)*1000
        total_ser_time += elapsed
        print(f"{i:<3} | {desc:<46} | {format_result(is_conv)} | {elapsed:>7.1f} ms | {reason}")

    # ── TOTALS ───────────────────────────────────────────────────
    print(f"\n{'='*115}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms  ({len(sequences)} tests)")
    print(f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms  ({len(series)} tests)")
    print(f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time+total_ser_time):.1f} ms")
    print("="*115)

    TIMER.report()
if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    main()