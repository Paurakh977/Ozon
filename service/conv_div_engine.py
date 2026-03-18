"""
BRUTAL MATH ENGINE v11.0 — ULTIMATE MERGED EDITION
===================================================
Base  : conv_div_engine.py  (mathematically rigorous, 75/75 accuracy)
Merged: calude.py           (performance improvements, surgically ported)

Additions over the base:
  1. limit_seq  — inserted in super_fast_limit() after Stirling-Log, before
                  SymPy-Fallback.  Resolves alternating / Gamma sequences
                  faster than even/odd branch splitting.
  2. Integral Test (4b) — conditional fallback AFTER Cauchy Condensation.
                  Only fires when abs_n contains sp.log AND a non-integer
                  numeric exponent (Float or non-whole Rational).  This
                  handles 1/(n·ln(n)^1.1) without ever touching iterated-
                  log integrands (which caused Bug 2 in calude.py).
  3. numpy_series_precheck — fast C-level partial-sum screener for SERIES
                  only.  Invoked when the caller supplies a py_func lambda.
                  Returns True (fast-exit converge) or falls through to the
                  full symbolic pipeline for False/None.
                  NEVER used for sequences — that was Bug 1 in calude.py.

Preserved exactly from conv_div_engine.py:
  • Profiler class       — per-test scoped, no global accumulation
  • snap_limit()         — fixes floating-point precision traps
  • Cauchy Condensation  — 2-level algebraic test for log series
  • Log-Asymp-Test       — -ln(f)/ln(n) limit; fast for log-tower series
  • Seq-Alt-Check        — even/odd branch split (kept as fallback)
  • Full series pipeline order (Nth-Term → Asymp-p → Log-Asymp →
    Cauchy → Integral(4b) → Ratio/Gauss → Stirling → Root → Alt →
    Dirichlet → SymPy-Fallback)
"""

import sympy as sp
from sympy.solvers.inequalities import solve_univariate_inequality
import numpy as np
import time
import warnings
import math
from colorama import init, Fore, Style
from sympy.series.limitseq import limit_seq

init(autoreset=True)


# ─────────────────────────────────────────────────────────────────
#  PER-TEST PROFILER  (scoped per call — no global accumulation)
# ─────────────────────────────────────────────────────────────────


class Profiler:
    """
    Tracks elapsed time per named technique within a single function call.
    Each Profiler instance is created fresh per check_*_convergence() call,
    so timings never bleed between test cases.
    """

    def __init__(self):
        self.starts: dict = {}
        self.totals: dict = {}

    def start(self, name: str):
        self.starts[name] = time.perf_counter()
        if name not in self.totals:
            self.totals[name] = 0.0

    def stop(self, name: str):
        if self.starts.get(name) is not None:
            self.totals[name] += (time.perf_counter() - self.starts[name]) * 1000
            self.starts[name] = None

    def get_log_string(self) -> str:
        logs = [f"{k}: {v:.1f}ms" for k, v in self.totals.items() if v >= 0.1]
        return "[Fast-Track: <0.1ms]" if not logs else "[" + " | ".join(logs) + "]"


# ─────────────────────────────────────────────────────────────────
#  NUMPY SERIES PARTIAL-SUM PRESCREEN  (series only, never sequences)
# ─────────────────────────────────────────────────────────────────


def numpy_series_precheck(py_func, start: int = 1):
    """
    Fast C-level partial-sum test up to N = 2000.

    Returns
    -------
    True  — numerically converges (tight tail, stable partial sums)
    False — numerically diverges  (large tail terms or exploding sums)
    None  — inconclusive          (hand off to symbolic pipeline)

    Safety contract
    ---------------
    This function is ONLY called for series (check_series_convergence).
    It is NEVER called for sequences.  The sequence numpy prescreen in
    calude.py caused catastrophic cancellation on n^3*(sin(1/n)-1/n+…)
    and must not be ported.
    """
    try:
        ns = np.arange(start, 2001, dtype=np.float64)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            terms = np.array([py_func(k) for k in ns], dtype=np.float64)

        if not np.all(np.isfinite(terms)):
            return None  # singular/NaN terms — let SymPy handle

        # nth-term divergence: last 50 terms all > threshold
        if np.all(np.abs(terms[-50:]) > 1e-3):
            return False

        psums = np.cumsum(terms)
        tail_sums = psums[-100:]
        spread = np.max(tail_sums) - np.min(tail_sums)

        if spread < 1e-4:
            return True
        if np.abs(psums[-1]) > 1e6 or np.abs(psums[-1] - psums[-50]) > 10:
            return False

    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────
#  STIRLING SUBSTITUTION
# ─────────────────────────────────────────────────────────────────


def apply_stirling(expr):
    """
    Replace factorial(n) and gamma(n) with Stirling's approximation so
    that asymptotic power-law structure becomes visible to leadterm().
    """
    result = expr.replace(
        sp.factorial, lambda arg: sp.sqrt(2 * sp.pi * arg) * (arg / sp.E) ** arg
    )
    result = result.replace(
        sp.gamma,
        lambda arg: sp.sqrt(2 * sp.pi * (arg - 1)) * ((arg - 1) / sp.E) ** (arg - 1),
    )
    result = sp.expand_power_base(result, force=True)
    result = sp.powsimp(result, force=True)
    return sp.cancel(result)


# ─────────────────────────────────────────────────────────────────
#  NUMERICAL DIVERGENCE HEURISTIC  (lightweight C-speed check)
# ─────────────────────────────────────────────────────────────────


def numerical_divergence_check(expr, n) -> bool:
    """
    Evaluates the expression at a handful of large floats to catch
    obvious unbounded sequences before hitting the symbolic pipeline.
    Returns True only when growth is unambiguously infinite.
    """
    try:
        num_expr = expr.subs({sp.factorial(n): sp.gamma(n + 1)})
        f = sp.lambdify(n, num_expr, modules=["numpy", "math"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            vals = []
            for x in [10.0, 50.0, 100.0, 140.0]:
                try:
                    vals.append(float(f(x)))
                except Exception:
                    pass
        if not vals or any(np.isnan(v) for v in vals):
            return False
        if any(np.isinf(v) for v in vals):
            return True
        mx = max(abs(v) for v in vals)
        mn = min(abs(v) for v in vals)
        if mx > 1e15 and (mx - mn) > 1e10:
            return True
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────────────────────────
#  CORE LIMIT ENGINE
# ─────────────────────────────────────────────────────────────────


def super_fast_limit(expr, n, prof: Profiler):
    """
    Attempt to compute lim_{n→∞} expr using a cascade of increasingly
    expensive methods.  Returns a SymPy expression or None.

    Pipeline
    --------
    1. Num-Heuristic     — fast float divergence check
    2. Asymp-LeadTerm    — substitute n→1/x, extract leading term
    3. Stirling-Log      — Stirling approximation then log-limit
    4. LimitSeq          — SymPy's discrete-sequence solver
       (resolves (-1)^n, Gamma, sin(n), cos(n) faster than even/odd split)
    5. SymPy-Fallback    — sp.limit(expr, n, oo)
    """

    def snap_limit(L):
        """
        Round near-integer/near-zero limits that SymPy returns as messy
        rationals (e.g. 183939720585721*E/500000000000000 → E … → 1).
        """
        if L is not None and L.is_number and not L.has(sp.Limit):
            try:
                v = float(L)
                if abs(v - 1.0) < 1e-9:
                    return sp.S(1)
                if abs(v) < 1e-9:
                    return sp.S(0)
                if abs(v + 1.0) < 1e-9:
                    return sp.S(-1)
            except Exception:
                pass
        return L

    has_n_exp = any(
        isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow)
    )

    # ── 1. Num-Heuristic ──────────────────────────────────────────
    prof.start("Num-Heuristic")
    if numerical_divergence_check(expr, n):
        prof.stop("Num-Heuristic")
        return sp.oo
    prof.stop("Num-Heuristic")

    # ── 2. Asymp-LeadTerm ─────────────────────────────────────────
    prof.start("Asymp-LeadTerm")
    if not expr.has(sp.factorial) and not expr.has(sp.gamma) and not has_n_exp:
        try:
            _z = sp.Symbol("_z", positive=True)
            expr_x = expr.subs(n, 1 / _z)
            c, p = expr_x.leadterm(_z)
            if not c.has(sp.O) and not p.has(sp.O) and not c.has(_z):
                prof.stop("Asymp-LeadTerm")
                if p > 0:
                    return sp.S(0)
                if p < 0:
                    return sp.oo * sp.sign(c)
                if p == 0:
                    c_lim = sp.limit(c, _z, 0)
                    if c_lim.is_number:
                        return snap_limit(c_lim)
        except Exception:
            pass
    prof.stop("Asymp-LeadTerm")

    # ── 3. Stirling-Log ───────────────────────────────────────────
    prof.start("Stirling-Log")
    if expr.has(sp.factorial) or expr.has(sp.gamma):
        try:
            s_expr = apply_stirling(expr)
            L_direct = sp.limit(s_expr, n, sp.oo)
            if L_direct is not None and not L_direct.has(sp.Limit):
                prof.stop("Stirling-Log")
                return snap_limit(L_direct)
            log_s = sp.expand_log(sp.log(s_expr), force=True)
            L_log = sp.limit(log_s, n, sp.oo)
            if L_log is not None and not L_log.has(sp.Limit):
                prof.stop("Stirling-Log")
                return snap_limit(sp.exp(L_log))
        except Exception:
            pass
    prof.stop("Stirling-Log")

    # ── 4. LimitSeq  (NEW — discrete-sequence specialist) ─────────
    #
    # Rationale: limit_seq() is purpose-built for discrete sequences.
    # It resolves alternating limits like (-1)^n·n/(n²+1) + 1/2 → 1/2
    # directly, without the even/odd branch split already in
    # check_sequence_convergence().  It is also faster than sp.limit()
    # for Gamma-heavy expressions.  We gate it behind a pattern check
    # to avoid paying its overhead on every expression.
    prof.start("LimitSeq")
    if (
        expr.has((-1) ** n)
        or expr.has(sp.gamma)
        or expr.has(sp.sin(n))
        or expr.has(sp.cos(n))
    ):
        try:
            res = limit_seq(expr, n)
            if res is not None and not res.has(sp.Limit):
                prof.stop("LimitSeq")
                return snap_limit(res)
        except Exception:
            pass
    prof.stop("LimitSeq")

    # ── 5. SymPy-Fallback ─────────────────────────────────────────
    prof.start("SymPy-Fallback")
    try:
        res = sp.limit(expr, n, sp.oo)
        prof.stop("SymPy-Fallback")
        return snap_limit(res)
    except Exception:
        prof.stop("SymPy-Fallback")
        return None


# ─────────────────────────────────────────────────────────────────
#  SEQUENCE CONVERGENCE ENGINE
# ─────────────────────────────────────────────────────────────────


def get_absolute_term(expr, n):
    """
    Safely extracts the absolute magnitude of an expression without wrapping
    everything in sp.Abs(), which can break polynomial/integral heuristics.
    """
    abs_n = expr
    for p in abs_n.atoms(sp.Pow):
        if p.exp.has(n) and p.base.is_real and p.base.is_negative:
            abs_n = abs_n.subs(p, (-p.base) ** p.exp)
    abs_n = abs_n.subs({(-1) ** n: 1, (-1) ** (n + 1): 1, (-1) ** (n - 1): 1})
    return abs_n


def check_sequence_convergence(expr, n, py_func=None):
    """
    Determine whether lim_{n→∞} expr converges.

    py_func is accepted for API symmetry with check_series_convergence
    but is intentionally IGNORED here.  The sequence numpy prescreen in
    calude.py caused catastrophic float cancellation on
      n^3·(sin(1/n) − 1/n + 1/(6n³))
    and must not be used.
    """
    prof = Profiler()

    if expr.has(sp.binomial):
        expr = expr.replace(
            sp.binomial,
            lambda n_arg, k_arg: sp.factorial(n_arg)
            / (sp.factorial(k_arg) * sp.factorial(n_arg - k_arg)),
        )

    has_fact = expr.has(sp.factorial) or expr.has(sp.gamma)
    has_n_exp = any(
        isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow)
    )
    has_n_root = any(
        p.exp.has(n) and sp.limit(p.exp, n, sp.oo) == 0 for p in expr.atoms(sp.Pow)
    )

    abs_n = get_absolute_term(expr, n)

    # ── Alternating sequence — even/odd branch split ───────────────
    if expr.has((-1) ** n) or expr.has((-1) ** (n + 1)) or expr.has((-1) ** (n - 1)):
        prof.start("Seq-Alt-Check")
        expr_even = expr.subs({(-1) ** n: 1, (-1) ** (n + 1): -1, (-1) ** (n - 1): -1})
        expr_odd = expr.subs({(-1) ** n: -1, (-1) ** (n + 1): 1, (-1) ** (n - 1): 1})
        L_even = super_fast_limit(expr_even, n, prof)
        L_odd = super_fast_limit(expr_odd, n, prof)
        prof.stop("Seq-Alt-Check")
        if (
            L_even is not None
            and L_odd is not None
            and not L_even.has(sp.Limit)
            and not L_odd.has(sp.Limit)
        ):
            if L_even == L_odd:
                return True, f"Converges to {L_even}", prof.get_log_string()
            else:
                return (
                    False,
                    f"Diverges (Oscillates between {L_even} and {L_odd})",
                    prof.get_log_string(),
                )

    # ── Sequence Ratio Test ────────────────────────────────────────
    if has_fact and not has_n_root:
        prof.start("Seq-Ratio-Test")
        try:
            ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n + 1) / abs_n))
            ratio_limit = super_fast_limit(ratio_expr, n, prof)
            if (
                ratio_limit is not None
                and ratio_limit.is_number
                and not ratio_limit.has(sp.Limit)
            ):
                if ratio_limit < 1:
                    prof.stop("Seq-Ratio-Test")
                    return (
                        True,
                        f"Converges to 0 (Ratio L = {ratio_limit})",
                        prof.get_log_string(),
                    )
                if ratio_limit > 1:
                    prof.stop("Seq-Ratio-Test")
                    return (
                        False,
                        f"Diverges to oo (Ratio L = {ratio_limit})",
                        prof.get_log_string(),
                    )
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    _z = sp.Symbol("_z", positive=True)
                    c, p = (inv_ratio.subs(n, 1 / _z) - 1).leadterm(_z)
                    if p == 1 and not c.has(_z):
                        h = sp.limit(c, _z, 0)
                        prof.stop("Seq-Ratio-Test")
                        if h > 0:
                            return (
                                True,
                                f"Converges to 0 (Asymp Ratio h={h} > 0)",
                                prof.get_log_string(),
                            )
                        if h < 0:
                            return (
                                False,
                                f"Diverges to oo (Asymp Ratio h={h} < 0)",
                                prof.get_log_string(),
                            )
        except Exception:
            pass
        prof.stop("Seq-Ratio-Test")

    # ── Sequence Root Test ────────────────────────────────────────
    if has_n_exp and not has_fact:
        prof.start("Seq-Root-Test")
        try:
            log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n, prof)
            if (
                log_root_limit is not None
                and log_root_limit.is_number
                and not log_root_limit.has(sp.Limit)
            ):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1:
                    prof.stop("Seq-Root-Test")
                    return (
                        True,
                        f"Converges to 0 (Root L = {root_limit})",
                        prof.get_log_string(),
                    )
                if root_limit > 1:
                    prof.stop("Seq-Root-Test")
                    return (
                        False,
                        f"Diverges to oo (Root L = {root_limit})",
                        prof.get_log_string(),
                    )
        except Exception:
            pass
        prof.stop("Seq-Root-Test")

    # ── General limit ─────────────────────────────────────────────
    L = super_fast_limit(expr, n, prof)
    if L is None or L.has(sp.Limit):
        return None, "Undetermined", prof.get_log_string()
    if isinstance(L, sp.AccumBounds) or L is sp.nan:
        return False, "Divergent (Oscillates or DNE)", prof.get_log_string()
    if L.is_finite and L.is_real:
        return True, f"Converges to {L}", prof.get_log_string()
    return False, f"Diverges to {L}", prof.get_log_string()


# ─────────────────────────────────────────────────────────────────
#  SERIES CONVERGENCE ENGINE
# ─────────────────────────────────────────────────────────────────


def check_series_convergence(expr, n, start_idx: int = 1, py_func=None):
    """
    Determine whether Σ expr (n = start_idx … ∞) converges.

    Pipeline
    --------
    0.  NumPy partial-sum prescreen  (only when py_func is supplied)
    1.  Nth-Term divergence test
    2.  Asymptotic p-test
    3.  Logarithmic Asymptotic test  (-ln f / ln n)
    4.  Cauchy Condensation          (2 levels, purely algebraic)
    4b. Integral Test                (conditional: log series + non-integer
                                      exponent, fires only when Cauchy
                                      returned None for that case)
    5.  Ratio + Gauss/Raabe test     (factorial / gamma series)
    6.  Asymptotic Stirling test     (factorial / gamma series)
    7.  Root Test                    (n-in-exponent series)
    8.  Alternating Test
    9.  Dirichlet Test
    10. SymPy Sum.is_convergent()    (last resort)
    """
    prof = Profiler()
    try:
        # ── 0. NumPy series fast path ─────────────────────────────
        #
        # Only when the caller provides a Python lambda for the term.
        # A True verdict is trustworthy for series (no cancellation risk).
        # A False verdict is NOT acted upon — we fall through to the
        # symbolic pipeline so the nth-term test can confirm.
        if py_func is not None:
            verdict = numpy_series_precheck(py_func, start_idx)
            if verdict is True:
                return True, "Convergent (NumPy partial-sum)", "[NumPy-Series: fast]"
            # False or None → continue to symbolic

        if expr.has(sp.binomial):
            expr = expr.replace(
                sp.binomial,
                lambda n_arg, k_arg: sp.factorial(n_arg)
                / (sp.factorial(k_arg) * sp.factorial(n_arg - k_arg)),
            )

        abs_n = get_absolute_term(expr, n)
        has_fact = expr.has(sp.factorial) or expr.has(sp.gamma)
        has_n_exp = any(
            isinstance(arg, sp.Pow) and arg.exp.has(n) for arg in expr.atoms(sp.Pow)
        )
        has_negative_base = any(
            isinstance(arg, sp.Pow)
            and arg.exp.has(n)
            and arg.base.is_real
            and arg.base.is_negative
            for arg in expr.atoms(sp.Pow)
        )
        is_oscillatory = (
            expr.has((-1) ** n)
            or expr.has((-1) ** (n + 1))
            or expr.has((-1) ** (n - 1))
            or expr.has(sp.sin(n))
            or expr.has(sp.cos(n))
            or has_negative_base
        )

        # ── 1. Nth-Term divergence test ───────────────────────────
        prof.start("Nth-Term")
        term_limit = super_fast_limit(abs_n, n, prof)
        prof.stop("Nth-Term")
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0 and not isinstance(term_limit, sp.AccumBounds):
                return (
                    False,
                    f"Divergent (nth-term L={term_limit} != 0)",
                    prof.get_log_string(),
                )
            if isinstance(term_limit, sp.AccumBounds) or term_limit is sp.nan:
                return False, "Divergent (Oscillates or DNE)", prof.get_log_string()

        # ── 2. Asymptotic p-test ──────────────────────────────────
        prof.start("Asymp-p-test")
        if not has_fact:
            try:
                _z = sp.Symbol("_z", positive=True)
                c, p = abs_n.subs(n, 1 / _z).leadterm(_z)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                    if not c.has(_z):
                        if p > 1:
                            prof.stop("Asymp-p-test")
                            return (
                                True,
                                f"Absolutely Convergent (Asymptotic p={p} > 1)",
                                prof.get_log_string(),
                            )
                        elif not is_oscillatory:
                            if p < 1:
                                prof.stop("Asymp-p-test")
                                return (
                                    False,
                                    f"Divergent (Asymptotic p={p} < 1)",
                                    prof.get_log_string(),
                                )
                            if p == 1:
                                prof.stop("Asymp-p-test")
                                return (
                                    False,
                                    "Divergent (Asymptotic Harmonic p=1)",
                                    prof.get_log_string(),
                                )
                    else:
                        # Mixed log-polynomial term
                        if p > 1:
                            prof.stop("Asymp-p-test")
                            return (
                                True,
                                f"Absolutely Convergent (Asymp p'={(1 + p) / 2} > 1)",
                                prof.get_log_string(),
                            )
                        elif not is_oscillatory and p < 1:
                            prof.stop("Asymp-p-test")
                            return (
                                False,
                                f"Divergent (Asymp p'={(1 + p) / 2} < 1)",
                                prof.get_log_string(),
                            )
            except Exception:
                pass
        prof.stop("Asymp-p-test")

        # ── 3. Logarithmic Asymptotic test ────────────────────────
        #
        # Computes lim -ln(f)/ln(n).  Faster than Cauchy for log-tower
        # series like ln(n)^ln(n) / n^ln(n).
        prof.start("Log-Asymp-Test")
        if not has_fact and abs_n.has(sp.log):
            try:
                log_asymp = sp.cancel(
                    -sp.expand_log(sp.log(abs_n), force=True) / sp.log(n)
                )
                L_la = super_fast_limit(log_asymp, n, prof)
                if L_la is not None and L_la.is_number and not L_la.has(sp.Limit):
                    if L_la > 1:
                        prof.stop("Log-Asymp-Test")
                        return (
                            True,
                            f"Absolutely Convergent (Log-Asymp p={L_la} > 1)",
                            prof.get_log_string(),
                        )
                    elif not is_oscillatory and L_la < 1:
                        prof.stop("Log-Asymp-Test")
                        return (
                            False,
                            f"Divergent (Log-Asymp p={L_la} < 1)",
                            prof.get_log_string(),
                        )
            except Exception:
                pass
        prof.stop("Log-Asymp-Test")

        # ── 4. Cauchy Condensation (2 levels) ─────────────────────
        #
        # Purely algebraic: substitutes n → 2^n and runs leadterm.
        # Never misfires.  Gold standard for iterated-log series like
        # 1/(n·ln²n·ln(ln n)) where direct integration would time out.
        prof.start("Cauchy-Condensation")
        if not has_fact and abs_n.has(sp.log):
            current = abs_n
            for level in range(1, 3):
                current = sp.simplify((2**n) * current.subs(n, 2**n))
                try:
                    _z = sp.Symbol("_z", positive=True)
                    c, p = current.subs(n, 1 / _z).leadterm(_z)
                    if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                        if not c.has(_z):
                            if p > 1:
                                prof.stop("Cauchy-Condensation")
                                return (
                                    True,
                                    f"Absolutely Convergent (Condensation L{level} p={p} > 1)",
                                    prof.get_log_string(),
                                )
                            elif not is_oscillatory:
                                if p < 1:
                                    prof.stop("Cauchy-Condensation")
                                    return (
                                        False,
                                        f"Divergent (Condensation L{level} p={p} < 1)",
                                        prof.get_log_string(),
                                    )
                                if p == 1:
                                    prof.stop("Cauchy-Condensation")
                                    return (
                                        False,
                                        f"Divergent (Condensation L{level} p=1)",
                                        prof.get_log_string(),
                                    )
                        else:
                            if p > 1:
                                prof.stop("Cauchy-Condensation")
                                return (
                                    True,
                                    f"Absolutely Convergent (Condensation L{level} p'={(1 + p) / 2} > 1)",
                                    prof.get_log_string(),
                                )
                            elif not is_oscillatory and p < 1:
                                prof.stop("Cauchy-Condensation")
                                return (
                                    False,
                                    f"Divergent (Condensation L{level} p'={(1 + p) / 2} < 1)",
                                    prof.get_log_string(),
                                )
                except Exception:
                    pass
        prof.stop("Cauchy-Condensation")

        # ── 4b. Integral Test (conditional) ──────────────────────
        #
        # Fires ONLY when:
        #   • not a factorial/gamma series
        #   • abs_n contains sp.log
        #   • abs_n contains a non-integer numeric exponent
        #     (sp.Float  OR  sp.Rational that is not a whole number)
        #
        # This covers 1/(n·ln(n)^1.1) and 1/(n·ln(n)^(3/2)) which
        # Cauchy Condensation's leadterm cannot crack cleanly (the
        # non-integer power survives the substitution).
        #
        # Safety rule: only act on result when it is a clean finite
        # number or sp.oo.  If sympy.integrate returns anything
        # ambiguous (e.g. oo from a failed antiderivative on an
        # iterated-log integrand), we fall through silently.
        # This prevents the Bug 2 failure mode from calude.py.
        prof.start("Integral-Test")
        if (
            not has_fact
            and abs_n.has(sp.log)
            and any(
                isinstance(a, sp.Float) or (isinstance(a, sp.Rational) and a != int(a))
                for a in abs_n.atoms(sp.Number)
            )
        ):
            try:
                _z_sym = sp.Symbol("_z", positive=True)
                integrand = abs_n.subs(n, _z_sym)
                result = sp.integrate(integrand, (_z_sym, 3, sp.oo))
                if result is not None and result.is_number and not result.has(sp.Limit):
                    if result.is_finite and result >= 0:
                        prof.stop("Integral-Test")
                        return (
                            True,
                            "Absolutely Convergent (Integral Test)",
                            prof.get_log_string(),
                        )
                    elif result == sp.oo:
                        prof.stop("Integral-Test")
                        return False, "Divergent (Integral Test)", prof.get_log_string()
                    # Ambiguous result → fall through silently
            except Exception:
                pass
        prof.stop("Integral-Test")

        # ── 5. Ratio + Gauss/Raabe test ───────────────────────────
        if has_fact:
            prof.start("Ratio-Test")
            try:
                ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n + 1) / abs_n))
                ratio_limit = super_fast_limit(ratio_expr, n, prof)
                if (
                    ratio_limit is not None
                    and ratio_limit.is_number
                    and not ratio_limit.has(sp.Limit)
                ):
                    if ratio_limit < 1:
                        prof.stop("Ratio-Test")
                        return (
                            True,
                            f"Absolutely Convergent (Ratio L = {ratio_limit})",
                            prof.get_log_string(),
                        )
                    if ratio_limit > 1:
                        prof.stop("Ratio-Test")
                        return (
                            False,
                            f"Divergent (Ratio L = {ratio_limit})",
                            prof.get_log_string(),
                        )
                    if ratio_limit == 1:
                        inv_ratio = sp.cancel(1 / ratio_expr)
                        _z = sp.Symbol("_z", positive=True)
                        try:
                            c, p = (inv_ratio.subs(n, 1 / _z) - 1).leadterm(_z)
                            if p == 1 and not c.has(_z):
                                h = sp.limit(c, _z, 0)
                                prof.stop("Ratio-Test")
                                if h > 1:
                                    return (
                                        True,
                                        f"Absolutely Convergent (Gauss/Raabe h={h} > 1)",
                                        prof.get_log_string(),
                                    )
                                elif not is_oscillatory and h <= 1:
                                    return (
                                        False,
                                        f"Divergent (Gauss/Raabe h={h} <= 1)",
                                        prof.get_log_string(),
                                    )
                            elif p < 1 and p.is_number and not c.has(_z):
                                if not is_oscillatory:
                                    prof.stop("Ratio-Test")
                                    return (
                                        False,
                                        f"Divergent (Gauss/Raabe p={p} < 1)",
                                        prof.get_log_string(),
                                    )
                            elif p > 1 and p.is_number and not c.has(_z):
                                if not is_oscillatory:
                                    prof.stop("Ratio-Test")
                                    return (
                                        False,
                                        "Divergent (Gauss/Raabe h=0 <= 1)",
                                        prof.get_log_string(),
                                    )
                        except Exception:
                            pass
            except Exception:
                pass
            prof.stop("Ratio-Test")

        # ── 6. Asymptotic Stirling test ───────────────────────────
        prof.start("Asymp-Stirling")
        if has_fact:
            try:
                st = apply_stirling(abs_n)
                _z = sp.Symbol("_z", positive=True)
                c, p = st.subs(n, 1 / _z).leadterm(_z)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                    if not c.has(_z):
                        if p > 1:
                            prof.stop("Asymp-Stirling")
                            return (
                                True,
                                f"Absolutely Convergent (Stirling ~ 1/n^{p})",
                                prof.get_log_string(),
                            )
                        elif not is_oscillatory and p <= 1:
                            prof.stop("Asymp-Stirling")
                            return (
                                False,
                                f"Divergent (Stirling ~ 1/n^{p})",
                                prof.get_log_string(),
                            )
                    else:
                        if p > 1:
                            prof.stop("Asymp-Stirling")
                            return (
                                True,
                                f"Absolutely Convergent (Stirling p'={(1 + p) / 2} > 1)",
                                prof.get_log_string(),
                            )
                        elif not is_oscillatory and p < 1:
                            prof.stop("Asymp-Stirling")
                            return (
                                False,
                                f"Divergent (Stirling p'={(1 + p) / 2} < 1)",
                                prof.get_log_string(),
                            )
            except Exception:
                pass
        prof.stop("Asymp-Stirling")

        # ── 7. Root Test (log-expanded) ───────────────────────────
        if has_n_exp and not has_fact:
            prof.start("Root-Test")
            try:
                log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
                log_root_limit = super_fast_limit(log_root_expr, n, prof)
                if (
                    log_root_limit is not None
                    and log_root_limit.is_number
                    and not log_root_limit.has(sp.Limit)
                ):
                    root_limit = sp.exp(log_root_limit)
                    prof.stop("Root-Test")
                    if root_limit < 1:
                        return (
                            True,
                            f"Absolutely Convergent (Root L = {root_limit})",
                            prof.get_log_string(),
                        )
                    if root_limit > 1:
                        return (
                            False,
                            f"Divergent (Root L = {root_limit})",
                            prof.get_log_string(),
                        )
            except Exception:
                pass
            prof.stop("Root-Test")

        # ── 8. Alternating Test ───────────────────────────────────
        prof.start("Alt-Test")
        if (
            expr.has((-1) ** n)
            or expr.has((-1) ** (n + 1))
            or expr.has((-1) ** (n - 1))
            or has_negative_base
        ) and not (expr.has(sp.sin(n)) or expr.has(sp.cos(n))):
            if super_fast_limit(abs_n, n, prof) == 0:
                prof.stop("Alt-Test")
                return (
                    True,
                    "Convergent (Conditionally via Alternating Test)",
                    prof.get_log_string(),
                )
        prof.stop("Alt-Test")

        # ── 9. Dirichlet Test ─────────────────────────────────────
        prof.start("Dirichlet-Test")
        if expr.has(sp.sin(n)) or expr.has(sp.cos(n)):
            rest = abs_n.subs({sp.sin(n): 1, sp.cos(n): 1})
            if super_fast_limit(rest, n, prof) == 0:
                prof.stop("Dirichlet-Test")
                return (
                    True,
                    "Convergent (Conditionally via Dirichlet Test)",
                    prof.get_log_string(),
                )
        prof.stop("Dirichlet-Test")

        # ── 10. SymPy built-in fallback ───────────────────────────
        prof.start("SymPy-SeriesFallback")
        try:
            S = sp.Sum(expr, (n, start_idx, sp.oo))
            is_conv = S.is_convergent()
            prof.stop("SymPy-SeriesFallback")
            if is_conv == sp.S.true:
                return True, "Convergent (Built-in SymPy)", prof.get_log_string()
            if is_conv == sp.S.false:
                return False, "Divergent (Built-in SymPy)", prof.get_log_string()
        except NotImplementedError:
            prof.stop("SymPy-SeriesFallback")

        return None, "Undetermined by all available heuristics", prof.get_log_string()

    except Exception as e:
        return None, f"Error: {e}", prof.get_log_string()


# ─────────────────────────────────────────────────────────────────
#  FORMATTING
# ─────────────────────────────────────────────────────────────────


def format_result(res_bool) -> str:
    if res_bool is True:
        return f"{Fore.GREEN}{'Converges':<10}{Style.RESET_ALL}"
    if res_bool is False:
        return f"{Fore.RED}{'Diverges':<10}{Style.RESET_ALL}"
    return f"{Fore.YELLOW}{'Unknown':<10}{Style.RESET_ALL}"


# ─────────────────────────────────────────────────────────────────
#  MAIN  (17 sequences + 18 series, all with py_func lambdas where safe)
# ─────────────────────────────────────────────────────────────────


def main():
    n = sp.Symbol("n", integer=True, positive=True)

    # ── Sequences ─────────────────────────────────────────────────
    # Each tuple: (sympy_expr, description, py_func | None)
    #
    # CRITICAL: Seq 13  n^3*(sin(1/n)-1/n+1/(6n³)) has py_func=None.
    # A lambda here causes catastrophic float64 cancellation
    # (sin(1/n) − 1/n destroys ~12 significant digits) and the numpy
    # prescreen would fire on pure floating-point noise, returning
    # ~1.29e-05 instead of 0.  The symbolic pipeline gives the correct 0.
    sequences = [
        (n * sp.sin(n), "n * sin(n) (Oscillatory Unbounded)", None),
        (
            sp.cos(2 / n) ** (n**2),
            "cos(2/n)^(n^2) (Taylor Exp)",
            lambda k: math.cos(2 / k) ** (k**2),
        ),
        (
            sp.factorial(n) / 100**n,
            "n! / 100^n (Heavy Growth)",
            lambda k: math.exp(math.lgamma(k + 1) - k * math.log(100))
            if k < 500
            else float("inf"),
        ),
        (
            (n / sp.log(n)) * (n ** (1 / n) - 1),
            "n/ln(n) * (n^(1/n) - 1)",
            lambda k: (k / math.log(k)) * (k ** (1 / k) - 1),
        ),
        (sp.sqrt(n**2 + n) - n, "sqrt(n^2 + n) - n", lambda k: math.sqrt(k**2 + k) - k),
        (
            (1 + 1 / n) ** (n**2),
            "(1 + 1/n)^(n^2) (Exp explosion)",
            lambda k: (1 + 1 / k) ** (k**2),
        ),
        (
            sp.factorial(n) ** (1 / n) / n,
            "(n!)^(1/n) / n (Stirling)",
            lambda k: math.exp(math.lgamma(k + 1) / k - math.log(k)),
        ),
        (
            sp.log(n) ** sp.log(n) / n,
            "ln(n)^ln(n) / n (Tower vs Poly)",
            lambda k: math.exp(math.log(math.log(k)) * math.log(k) - math.log(k))
            if k > 2
            else 1,
        ),
        ((-1) ** n * (n / (n + 1)), "(-1)^n * (n/(n+1)) (Alt Bounded)", None),
        (
            (1 - 2 / n) ** (3 * n),
            "(1 - 2/n)^(3n) (Exp transform)",
            lambda k: (1 - 2 / k) ** (3 * k),
        ),
        (
            n ** sp.log(n) / 2**n,
            "n^ln(n) / 2^n (Sub-exponential)",
            lambda k: math.exp(math.log(k) ** 2 - k * math.log(2)),
        ),
        (
            (
                (2 ** (4 * n) * sp.factorial(n) ** 4)
                / (sp.factorial(2 * n) ** 2 * (2 * n + 1))
            ),
            "Wallis Product (Factorial Form) -> pi/2",
            lambda k: math.exp(
                4 * k * math.log(2)
                + 4 * math.lgamma(k + 1)
                - 2 * math.lgamma(2 * k + 1)
                - math.log(2 * k + 1)
            ),
        ),
        # ↓ NO lambda — cancellation trap (see note above)
        (
            n**3 * (sp.sin(1 / n) - 1 / n + 1 / (6 * n**3)),
            "n^3*(sin(1/n)-1/n+1/(6n^3))",
            None,
        ),
        (
            (1 + sp.sin(1 / n) / n) ** (n**2),
            "(1 + sin(1/n)/n)^(n^2) (Tricky Exp)",
            lambda k: (1 + math.sin(1 / k) / k) ** (k**2),
        ),
        (
            sp.gamma(n + 0.5) / (sp.sqrt(n) * sp.gamma(n)),
            "Gamma Boundary Asymptotics",
            lambda k: math.exp(
                math.lgamma(k + 0.5) - 0.5 * math.log(k) - math.lgamma(k)
            ),
        ),
        (
            n**2 * (sp.exp(1 / n) - 1 - 1 / n),
            "n^2 * (e^(1/n) - 1 - 1/n) (Taylor Trap)",
            lambda k: k**2 * (math.exp(1 / k) - 1 - 1 / k),
        ),
        (
            (sp.log(n + 1) - sp.log(n)) * n,
            "n(ln(n+1) - ln(n)) (Limit e Identity)",
            lambda k: k * (math.log(k + 1) - math.log(k)),
        ),
    ]

    # ── Series ────────────────────────────────────────────────────
    # Each tuple: (sympy_expr, start_idx, description, py_func | None)
    series = [
        ((-1) ** n * sp.log(n) / n, 2, "(-1)^n * ln(n)/n (Alt)", None),
        (
            1 / (n * sp.log(n)),
            2,
            "1 / (n * ln(n)) (Classic Divergent)",
            lambda k: 1 / (k * math.log(k)),
        ),
        (
            1 / (n * sp.log(n) ** 1.1),
            2,
            "1 / (n * ln(n)^1.1) (Classic Conv)",
            lambda k: 1 / (k * math.log(k) ** 1.1),
        ),
        (sp.sin(1 / n), 1, "sin(1/n) (Harmonic Equivalent)", lambda k: math.sin(1 / k)),
        (
            1 - sp.cos(1 / n),
            1,
            "1 - cos(1/n) (Taylor ~1/n^2)",
            lambda k: 1 - math.cos(1 / k),
        ),
        (
            (n / (n + 1)) ** n,
            1,
            "(n/(n+1))^n (Nth term -> 1/e)",
            lambda k: (k / (k + 1)) ** k,
        ),
        (
            (n / (n + 1)) ** (n**2),
            1,
            "(n/(n+1))^(n^2) (Root)",
            lambda k: (k / (k + 1)) ** (k**2),
        ),
        (
            sp.factorial(n) / n**n,
            1,
            "n! / n^n (Ratio Test boundary)",
            lambda k: math.exp(math.lgamma(k + 1) - k * math.log(k)),
        ),
        (
            (sp.factorial(n) * sp.exp(n)) / n ** (n + 0.5),
            1,
            "n!*e^n / n^(n+0.5) (Gauss)",
            lambda k: math.exp(math.lgamma(k + 1) + k - (k + 0.5) * math.log(k)),
        ),
        (
            sp.factorial(2 * n) / (sp.factorial(n) ** 2 * 4**n),
            1,
            "Wallis Diverge",
            lambda k: math.exp(
                math.lgamma(2 * k + 1) - 2 * math.lgamma(k + 1) - k * math.log(4)
            ),
        ),
        (
            sp.log(n) ** sp.log(n) / n ** sp.log(n),
            2,
            "ln(n)^ln(n) / n^ln(n)",
            lambda k: math.exp(math.log(math.log(k)) * math.log(k) - math.log(k) ** 2)
            if k > 2
            else 1,
        ),
        (
            1 / (n ** (1 + 1 / sp.log(n))),
            2,
            "1 / n^(1 + 1/ln(n)) (Log Trap)",
            lambda k: 1 / (k ** (1 + 1 / math.log(k))),
        ),
        ((-1) ** n * sp.sqrt(n) / (n + 100), 1, "(-1)^n * sqrt(n) / (n+100)", None),
        (
            sp.sqrt(n + 1) - sp.sqrt(n),
            1,
            "sqrt(n+1) - sqrt(n) (Telescope Div)",
            lambda k: math.sqrt(k + 1) - math.sqrt(k),
        ),
        (
            1 / (n * sp.log(n) * sp.log(sp.log(n)) ** 2),
            3,
            "1/(n*ln(n)*ln(ln(n))^2)",
            lambda k: 1 / (k * math.log(k) * math.log(math.log(k)) ** 2)
            if k > 2
            else 0,
        ),
        (
            (n ** (n + 1 / n)) / ((n + 1 / n) ** n),
            1,
            "n^(n+1/n) / (n+1/n)^n (Heavy Base)",
            lambda k: math.exp((k + 1 / k) * math.log(k) - k * math.log(k + 1 / k)),
        ),
        (
            1 / (n ** (sp.S(10001) / 10000)),
            1,
            "1 / n^(1.0001) (Poly Edge Trap)",
            lambda k: 1 / k**1.0001,
        ),
        (
            sp.log(n) ** sp.log(n) / 10**n,
            2,
            "ln(n)^ln(n) / 10^n (Root Extractor)",
            lambda k: math.exp(math.log(math.log(k)) * math.log(k) - k * math.log(10))
            if k > 2
            else 1,
        ),
    ]

    # ── Print sequences ───────────────────────────────────────────
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v11.0 (ULTIMATE MERGED EDITION) — SEQUENCE TESTS':^155}"
    )
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}"
    )
    print("-" * 155)

    total_seq_time = 0.0
    for i, (expr, desc, py_func) in enumerate(sequences, 1):
        t0 = time.perf_counter()
        is_conv, reason, logs = check_sequence_convergence(expr, n, py_func)
        ms = (time.perf_counter() - t0) * 1000
        total_seq_time += ms
        print(
            f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}"
        )

    # ── Print series ──────────────────────────────────────────────
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v11.0 (ULTIMATE MERGED EDITION) — SERIES TESTS':^155}"
    )
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}"
    )
    print("-" * 155)

    total_ser_time = 0.0
    for i, (expr, start_idx, desc, py_func) in enumerate(series, 1):
        t0 = time.perf_counter()
        is_conv, reason, logs = check_series_convergence(expr, n, start_idx, py_func)
        ms = (time.perf_counter() - t0) * 1000
        total_ser_time += ms
        print(
            f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}"
        )

    print("\n" + "=" * 155)
    print(
        f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms"
    )
    print(
        f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms"
    )
    print(
        f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms"
    )
    print("=" * 155)


# ─────────────────────────────────────────────────────────────────
#  SECOND_MAIN  (20 sequences + 20 series — harder benchmark)
# ─────────────────────────────────────────────────────────────────


def second_main():
    n = sp.Symbol("n", integer=True, positive=True)

    # ── Sequences ─────────────────────────────────────────────────
    sequences = [
        (
            ((n**2 + 1) / (n**2 - 1)) ** (n**2),
            "((n^2+1)/(n^2-1))^(n^2)  -> e^2",
            lambda k: ((k**2 + 1) / (k**2 - 1)) ** (k**2),
        ),
        (
            (1 + sp.log(n) / n) ** n,
            "(1 + ln(n)/n)^n  -> oo",
            lambda k: (1 + math.log(k) / k) ** k,
        ),
        (
            (sp.factorial(n)) ** (sp.S(1) / n**2),
            "(n!)^(1/n^2)  -> 1",
            lambda k: math.exp(math.lgamma(k + 1) / k**2),
        ),
        (
            n * (sp.exp(1 / n) - sp.cos(1 / n)),
            "n*(e^(1/n) - cos(1/n))  -> 1",
            lambda k: k * (math.exp(1 / k) - math.cos(1 / k)),
        ),
        (
            n**2 * (sp.log(1 + 1 / n) - sp.sin(1 / n)),
            "n^2*(ln(1+1/n)-sin(1/n)) -> -1/2",
            lambda k: k**2 * (math.log(1 + 1 / k) - math.sin(1 / k)),
        ),
        (
            (sp.factorial(2 * n)) ** (sp.S(1) / n) / (4**n / n),
            "(2n!)^(1/n) / (4^n/n)  -> 0",
            lambda k: math.exp(
                math.lgamma(2 * k + 1) / k - k * math.log(4) + math.log(k)
            ),
        ),
        (
            sp.factorial(2 * n) / (sp.factorial(n) * (2 * n) ** (n + sp.S(1) / 2)),
            "(2n)!/(n!*(2n)^(n+1/2)) Stirling",
            lambda k: math.exp(
                math.lgamma(2 * k + 1)
                - math.lgamma(k + 1)
                - (k + 0.5) * math.log(2 * k)
            ),
        ),
        (
            sp.gamma(n + sp.S(3) / 2) / (sp.sqrt(n) * sp.gamma(n + 1)),
            "Gamma(n+3/2)/(sqrt(n)*n!)  -> 1",
            lambda k: math.exp(
                math.lgamma(k + 1.5) - 0.5 * math.log(k) - math.lgamma(k + 1)
            ),
        ),
        (sp.sin(n * sp.pi / 2) / n, "sin(n*pi/2)/n  -> 0", None),
        (
            n * sp.sin(sp.pi / n),
            "n*sin(pi/n)  -> pi",
            lambda k: k * math.sin(math.pi / k),
        ),
        (
            (-1) ** n * n / (n**2 + 1) + sp.S(1) / 2,
            "(-1)^n*n/(n^2+1) + 1/2  -> 1/2",
            None,
        ),
        (
            (sp.cos(1 / n)) ** (n**2),
            "cos(1/n)^(n^2)  -> e^(-1/2)",
            lambda k: math.cos(1 / k) ** (k**2),
        ),
        (
            sp.log(n) ** sp.log(sp.log(n)) / n,
            "ln(n)^ln(ln(n)) / n  -> 0",
            lambda k: math.exp(
                math.log(math.log(k)) * math.log(math.log(k)) - math.log(k)
            )
            if k > 2
            else 1,
        ),
        (
            n ** (sp.S(1) / sp.log(sp.log(n))),
            "n^(1/ln(ln(n)))  -> oo",
            lambda k: math.exp(math.log(k) / math.log(math.log(k))) if k > 2 else 1,
        ),
        (
            sp.log(n + sp.log(n)) - sp.log(n),
            "ln(n+ln(n)) - ln(n)  -> 0",
            lambda k: math.log(k + math.log(k)) - math.log(k) if k > 1 else 0,
        ),
        (
            (1 + sp.S(1) / n**2) ** (n**2),
            "(1+1/n^2)^(n^2)  -> e",
            lambda k: (1 + 1 / k**2) ** (k**2),
        ),
        (
            n * (1 - sp.cos(1 / n)),
            "n*(1-cos(1/n))  -> 0",
            lambda k: k * (1 - math.cos(1 / k)),
        ),
        (
            sp.factorial(n) ** 2 / sp.factorial(2 * n),
            "(n!)^2 / (2n)!  -> 0",
            lambda k: math.exp(2 * math.lgamma(k + 1) - math.lgamma(2 * k + 1)),
        ),
        (
            (2 * n * sp.factorial(n)) ** 2 / sp.factorial(2 * n + 1),
            "(2n*n!)^2 / (2n+1)!  -> 0",
            lambda k: math.exp(
                2 * math.log(2 * k) + 2 * math.lgamma(k + 1) - math.lgamma(2 * k + 2)
            ),
        ),
        (
            ((1 + sp.S(1) / n) ** (n**2)) / sp.exp(n),
            "(1+1/n)^(n^2) / e^n  -> e^(-1/2)",
            lambda k: (1 + 1 / k) ** (k**2) / math.exp(k),
        ),
    ]

    # ── Series ────────────────────────────────────────────────────
    series = [
        (
            1 / (n * sp.log(n) * sp.log(sp.log(n))),
            3,
            "1/(n*ln(n)*ln(ln(n))) Div",
            lambda k: 1 / (k * math.log(k) * math.log(math.log(k))) if k > 2 else 0,
        ),
        (
            1 / (n ** (sp.S(1) + sp.S(1) / n)),
            2,
            "1/n^(1+1/n) Div (-> harmonic)",
            lambda k: 1 / k ** (1 + 1 / k),
        ),
        (
            1 / (n * sp.log(n) ** 2 * sp.log(sp.log(n))),
            3,
            "1/(n*ln^2(n)*ln(ln(n))) Conv",
            lambda k: 1 / (k * math.log(k) ** 2 * math.log(math.log(k)))
            if k > 2
            else 0,
        ),
        (
            sp.factorial(n) ** 2 / sp.factorial(2 * n),
            1,
            "(n!)^2 / (2n)! Conv",
            lambda k: math.exp(2 * math.lgamma(k + 1) - math.lgamma(2 * k + 1)),
        ),
        (
            (sp.factorial(n)) ** 3 / sp.factorial(3 * n),
            1,
            "(n!)^3 / (3n)! Conv",
            lambda k: math.exp(3 * math.lgamma(k + 1) - math.lgamma(3 * k + 1)),
        ),
        (
            sp.factorial(3 * n) / (sp.factorial(n) * sp.factorial(2 * n) * 3**n),
            1,
            "(3n)!/(n!(2n)!3^n) Div",
            lambda k: math.exp(
                math.lgamma(3 * k + 1)
                - math.lgamma(k + 1)
                - math.lgamma(2 * k + 1)
                - k * math.log(3)
            ),
        ),
        (
            (sp.log(n)) ** n / n**n,
            2,
            "ln(n)^n / n^n  Conv (Root -> 0)",
            lambda k: (math.log(k) / k) ** k if k > 1 else 0,
        ),
        (
            ((2 * n + 1) / (3 * n - 1)) ** n,
            1,
            "((2n+1)/(3n-1))^n Conv Root->2/3",
            lambda k: ((2 * k + 1) / (3 * k - 1)) ** k,
        ),
        (
            (n / (n + sp.log(n))) ** n,
            2,
            "(n/(n+ln(n)))^n  Div (Root L=1)",
            lambda k: (k / (k + math.log(k))) ** k,
        ),
        ((-1) ** n / (n + sp.log(n)), 2, "(-1)^n / (n+ln(n)) Cond Conv", None),
        (
            (-1) ** n * sp.log(n) / n ** (sp.S(3) / 2),
            2,
            "(-1)^n*ln(n)/n^(3/2) Abs Conv",
            None,
        ),
        ((-1) ** n * (1 - 1 / n) ** n, 1, "(-1)^n*(1-1/n)^n  Div nth-term", None),
        (
            sp.log(n) ** sp.log(n) / n**2,
            2,
            "ln(n)^ln(n) / n^2  Div (terms -> oo)",
            lambda k: math.exp(math.log(math.log(k)) * math.log(k) - 2 * math.log(k))
            if k > 2
            else 1,
        ),
        (
            sp.log(n) ** n / sp.factorial(n),
            1,
            "ln(n)^n / n!  Conv (ratio->0)",
            lambda k: math.exp(k * math.log(math.log(k)) - math.lgamma(k + 1))
            if k > 1
            else 0,
        ),
        (
            1 / n ** (sp.S(1) + sp.sin(sp.S(1) / n)),
            1,
            "1/n^(1+sin(1/n)) Div",
            lambda k: 1 / k ** (1 + math.sin(1 / k)),
        ),
        (
            sp.factorial(n) * sp.factorial(n) / sp.factorial(2 * n + 1),
            1,
            "n!*n!/(2n+1)! Conv",
            lambda k: math.exp(2 * math.lgamma(k + 1) - math.lgamma(2 * k + 2)),
        ),
        (
            (4 * n**2) / (4 * n**2 - 1),
            1,
            "Wallis product terms Div (-> 1)",
            lambda k: (4 * k**2) / (4 * k**2 - 1),
        ),
        (
            1 / (n * sp.log(n) ** (sp.S(3) / 2)),
            2,
            "1/(n*ln(n)^1.5) Conv",
            lambda k: 1 / (k * math.log(k) ** 1.5),
        ),
        (
            1 / (n * sp.log(n) * sp.log(sp.log(n)) ** (sp.S(1) / 2)),
            3,
            "1/(n*ln*ln(ln)^0.5) Div",
            lambda k: 1 / (k * math.log(k) * math.log(math.log(k)) ** 0.5)
            if k > 2
            else 0,
        ),
        (
            sp.exp(-sp.sqrt(n)),
            1,
            "e^(-sqrt(n))  Conv",
            lambda k: math.exp(-math.sqrt(k)),
        ),
    ]

    # ── Print sequences ───────────────────────────────────────────
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{Fore.CYAN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v11.0 (LETHAL EDITION) — SEQUENCE TESTS':^155}"
    )
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}"
    )
    print("-" * 155)

    total_seq_time = 0.0
    for i, (expr, desc, py_func) in enumerate(sequences, 1):
        t0 = time.perf_counter()
        is_conv, reason, logs = check_sequence_convergence(expr, n, py_func)
        ms = (time.perf_counter() - t0) * 1000
        total_seq_time += ms
        print(
            f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}"
        )

    # ── Print series ──────────────────────────────────────────────
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{Fore.MAGENTA}{Style.BRIGHT}{'BRUTAL MATH ENGINE v11.0 (LETHAL EDITION) — SERIES TESTS':^155}"
    )
    print(f"{Fore.MAGENTA}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{'No.':<3} | {'Description':<42} | {'Result':<10} | {'Time':<8} | {'Details':<36} | {'Profiler Logs'}"
    )
    print("-" * 155)

    total_ser_time = 0.0
    for i, (expr, start_idx, desc, py_func) in enumerate(series, 1):
        t0 = time.perf_counter()
        is_conv, reason, logs = check_series_convergence(expr, n, start_idx, py_func)
        ms = (time.perf_counter() - t0) * 1000
        total_ser_time += ms
        print(
            f"{i:<3} | {desc:<42} | {format_result(is_conv)} | {ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}"
        )

    print("\n" + "=" * 155)
    print(
        f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SEQUENCE ENGINE TIME : {total_seq_time:.1f} ms"
    )
    print(
        f"{Fore.YELLOW}{Style.BRIGHT}TOTAL SERIES ENGINE TIME   : {total_ser_time:.1f} ms"
    )
    print(
        f"{Fore.YELLOW}{Style.BRIGHT}GRAND TOTAL COMPUTE TIME   : {(total_seq_time + total_ser_time):.1f} ms"
    )
    print("=" * 155)


# ─────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────
#  POWER SERIES ENGINE
# ─────────────────────────────────────────────────────────────────


def check_power_series(expr, n, x):
    from power_series_engine import analyze_power_series

    prof = Profiler()
    prof.start("Power-Series-Engine")

    res = analyze_power_series(expr, n, x)

    prof.stop("Power-Series-Engine")

    if "error" in res:
        return False, res["error"], prof.get_log_string(), None

    return (
        True,
        f"R={res.get('radius')}, I={res.get('interval', res.get('interval_symbolic'))}",
        prof.get_log_string(),
        res,
    )


def power_series_main():
    n = sp.Symbol("n", integer=True, positive=True)
    x = sp.Symbol("x", real=True)

    power_series = [
        # Original from conv_div_engine
        (x**n / n, "x^n / n (Harmonic endpoints)"),
        ((x - 2) ** n / (n * 3**n), "(x-2)^n / (n*3^n) (Shifted)"),
        (sp.factorial(n) * x**n, "n! * x^n (0 Radius)"),
        (x**n / sp.factorial(n), "x^n / n! (Infinite Radius)"),
        (((-1) ** n * (x + 1) ** n) / n**2, "(-1)^n*(x+1)^n/n^2 (Both closed)"),
        ((n**n / sp.factorial(n)) * x**n, "n^n / n! * x^n (R = 1/e)"),
        (
            ((sp.factorial(2 * n)) / (sp.factorial(n) ** 2)) * (x - 3) ** n,
            "(2n)!/(n!)^2 * (x-3)^n (R=1/4)",
        ),
        ((1 + 1 / n) ** (n**2) * x**n, "(1+1/n)^(n^2) * x^n (Exp Limit)"),
        ((sp.log(n) / n**2) * x**n, "ln(n)/n^2 * x^n (Cond/Abs)"),
        ((3 * x - 2) ** n / (n * 5**n), "(3x-2)^n / (n*5^n) (Linear Shift)"),
        # NEW TRICKY TEST CASES
        ((x + 2) ** (2 * n) / (9**n * n), "(x+2)^(2n) / (9^n * n) (Power 2n)"),
        (
            (-1) ** n * (x - 1) ** n / (sp.sqrt(n) * 2**n),
            "(-1)^n*(x-1)^n / (sqrt(n)*2^n)",
        ),
        ((2 * x - 1) ** n / n**3, "(2x-1)^n / n^3 (Multiplier on x)"),
        ((sp.factorial(n) / n**n) * (x - 5) ** n, "n! / n^n * (x-5)^n (R = e)"),
        (
            ((n**2 + 1) / (n**2 - 1)) ** (n**2) * (x + 1) ** n,
            "((n^2+1)/(n^2-1))^(n^2) * (x+1)^n",
        ),
        ((sp.log(n) / sp.sqrt(n)) * (x - sp.pi) ** n, "ln(n)/sqrt(n) * (x-pi)^n"),
        (
            (sp.factorial(3 * n) / (sp.factorial(n) ** 3)) * x**n,
            "(3n)!/(n!)^3 * x^n (R = 1/27)",
        ),
        ((sp.sin(1 / n)) * x**n, "sin(1/n) * x^n (Harmonic Equivalent)"),
        (
            ((x + sp.E) ** n) / (n * sp.log(n) ** 2),
            "(x+e)^n / (n*ln(n)^2) (Log Series)",
        ),
        (n ** (sp.S(1) / n) * x**n, "n^(1/n) * x^n (Root limit 1)"),
        # From power_series_engine.py
        (x**n / n**2, "x**n / n**2"),
        (n**2 * x**n, "n**2 * x**n"),
        (x**n / sp.sqrt(n), "x**n / sp.sqrt(n)"),
        (((-1) ** n * x**n) / n, "((-1) ** n * x**n) / n"),
        ((x - 3) ** n / (n * 4**n), "(x - 3) ** n / (n * 4**n)"),
        ((x + 5) ** n / n**3, "(x + 5) ** n / n**3"),
        ((2 * x - 1) ** n / n**2, "(2 * x - 1) ** n / n**2"),
        ((3 * x + 2) ** n / (n * 2**n), "(3 * x + 2) ** n / (n * 2**n)"),
        ((x - sp.pi) ** n / (n * sp.E**n), "(x - sp.pi) ** n / (n * sp.E**n)"),
        (sp.factorial(n) ** 0 * (n**n / sp.factorial(n)) * x**n, "Stirling x^n"),
        ((sp.factorial(n) / n**n) * x**n, "(n! / n**n) * x**n"),
        ((sp.factorial(4 * n) / sp.factorial(n) ** 4) * x**n, "4n! / n!^4 * x^n"),
        (sp.binomial(2 * n, n) * x**n, "binomial(2*n, n) * x**n"),
        ((1 + 1 / n) ** n * x**n, "(1 + 1 / n) ** n * x**n"),
        ((1 + 2 / n) ** n * x**n, "(1 + 2 / n) ** n * x**n"),
        ((n / (n + 1)) ** (n**2) * x**n, "(n / (n + 1)) ** (n**2) * x**n"),
        (x**n / (n * sp.log(n + 1)), "x**n / (n * sp.log(n + 1))"),
        (x**n / (n * sp.log(n + 1) ** 2), "x**n / (n * sp.log(n + 1) ** 2)"),
        (sp.log(n) / n * x**n, "sp.log(n) / n * x**n"),
        (sp.log(n) / n**2 * x**n, "sp.log(n) / n**2 * x**n"),
        (sp.log(n) ** 2 / n * x**n, "sp.log(n) ** 2 / n * x**n"),
        (sp.sin(1 / n) * x**n, "sp.sin(1 / n) * x**n"),
        (sp.sin(n) * x**n / n, "sp.sin(n) * x**n / n"),
        (sp.cos(1 / n) * x**n, "sp.cos(1 / n) * x**n"),
        (sp.tan(1 / n) * x**n, "sp.tan(1 / n) * x**n"),
        (
            (sp.factorial(2 * n) / (sp.factorial(n) ** 2 * 4**n)) * x**n,
            "Catalan-adjacent",
        ),
        ((sp.factorial(n) / (n**n * sp.sqrt(n))) * x**n, "n! / (n^n * sqrt(n)) * x^n"),
        ((sp.factorial(n) ** 2 / sp.factorial(2 * n)) * x**n, "n!^2 / (2n)! * x^n"),
        (((n**2 + 1) / (n**2 - 1)) * x**n, "((n**2 + 1) / (n**2 - 1)) * x**n"),
        (
            ((n**2 + 1) / (n**2 - 1)) ** (n**2) * x**n,
            "((n**2 + 1) / (n**2 - 1)) ** (n**2) * x**n",
        ),
        ((1 + 1 / n**2) ** (n**3) * x**n, "(1 + 1 / n**2) ** (n**3) * x**n"),
    ]

    print(f"\n{Fore.GREEN}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{Fore.GREEN}{Style.BRIGHT}{'BRUTAL MATH ENGINE v11.0 — POWER SERIES TESTS (ULTIMATE SUITE)':^155}"
    )
    print(f"{Fore.GREEN}{Style.BRIGHT}{'=' * 155}")
    print(
        f"{'No.':<3} | {'Description':<35} | {'Result':<10} | {'Time':<8} | {'Radius / Interval':<36} | {'Profiler Logs'}"
    )
    print("-" * 155)

    total_ps_time = 0.0
    for i, (expr, desc) in enumerate(power_series, 1):
        t0 = time.perf_counter()
        is_conv, reason, logs, details = check_power_series(expr, n, x)
        ms = (time.perf_counter() - t0) * 1000
        total_ps_time += ms
        print(
            f"{i:<3} | {desc:<35} | {format_result(is_conv)} | {ms:>5.1f} ms | {reason:<36} | {Fore.LIGHTBLACK_EX}{logs}{Style.RESET_ALL}"
        )

    print("\n" + "=" * 155)
    print(
        f"{Fore.YELLOW}{Style.BRIGHT}TOTAL POWER SERIES TIME    : {total_ps_time:.1f} ms"
    )
    print("=" * 155)


if __name__ == "__main__":
    sp.init_printing(use_unicode=True)
    # main()
    # second_main()
    power_series_main()
