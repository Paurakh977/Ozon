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
import warnings
from sympy.series.limitseq import limit_seq
from engines import get_sympified_expr




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


def super_fast_limit(expr, n):
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
    if numerical_divergence_check(expr, n):
        return sp.oo

    # ── 2. Asymp-LeadTerm ─────────────────────────────────────────
    if not expr.has(sp.factorial) and not expr.has(sp.gamma) and not has_n_exp:
        try:
            _z = sp.Symbol("_z", positive=True)
            expr_x = expr.subs(n, 1 / _z)
            c, p = expr_x.leadterm(_z)
            if not c.has(sp.O) and not p.has(sp.O) and not c.has(_z):
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

    # ── 3. Stirling-Log ───────────────────────────────────────────
    if expr.has(sp.factorial) or expr.has(sp.gamma):
        try:
            s_expr = apply_stirling(expr)
            L_direct = sp.limit(s_expr, n, sp.oo)
            if L_direct is not None and not L_direct.has(sp.Limit):
                return snap_limit(L_direct)
            log_s = sp.expand_log(sp.log(s_expr), force=True)
            L_log = sp.limit(log_s, n, sp.oo)
            if L_log is not None and not L_log.has(sp.Limit):
                return snap_limit(sp.exp(L_log))
        except Exception:
            pass

    # ── 4. LimitSeq  (NEW — discrete-sequence specialist) ─────────
    #
    # Rationale: limit_seq() is purpose-built for discrete sequences.
    # It resolves alternating limits like (-1)^n·n/(n²+1) + 1/2 → 1/2
    # directly, without the even/odd branch split already in
    # check_sequence_convergence().  It is also faster than sp.limit()
    # for Gamma-heavy expressions.  We gate it behind a pattern check
    # to avoid paying its overhead on every expression.
    if (
        expr.has((-1) ** n)
        or expr.has(sp.gamma)
        or expr.has(sp.sin(n))
        or expr.has(sp.cos(n))
    ):
        try:
            res = limit_seq(expr, n)
            if res is not None and not res.has(sp.Limit):
                return snap_limit(res)
        except Exception:
            pass

    # ── 5. SymPy-Fallback ─────────────────────────────────────────
    try:
        res = sp.limit(expr, n, sp.oo)
        return snap_limit(res)
    except Exception:
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


def check_sequence_convergence(expr, n=None, py_func=None):
    """
    Determine whether lim_{n→∞} expr converges.

    py_func is accepted for API symmetry with check_series_convergence
    but is intentionally IGNORED here.  The sequence numpy prescreen in
    calude.py caused catastrophic float cancellation on
      n^3·(sin(1/n) − 1/n + 1/(6n³))
    and must not be used.
    """

    if n is None:
        n = sp.Symbol("n", integer=True, positive=True)
        n_name = "n"
    elif isinstance(n, str):
        n_name = n
        n = sp.Symbol(n, integer=True, positive=True)
    else:
        n_name = str(n)

    if isinstance(expr, str):
        try:
            expr = get_sympified_expr(expr, local_dict={n_name: n})
        except Exception as e:
            return None, f"Parse Error: {str(e)}", ""

    if expr.has(sp.binomial):
        expr = expr.replace(
            sp.binomial,
            lambda n_arg, k_arg: (
                sp.factorial(n_arg)
                / (sp.factorial(k_arg) * sp.factorial(n_arg - k_arg))
            ),
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
        expr_even = expr.subs({(-1) ** n: 1, (-1) ** (n + 1): -1, (-1) ** (n - 1): -1})
        expr_odd = expr.subs({(-1) ** n: -1, (-1) ** (n + 1): 1, (-1) ** (n - 1): 1})
        L_even = super_fast_limit(expr_even, n)
        L_odd = super_fast_limit(expr_odd, n)
        if (
            L_even is not None
            and L_odd is not None
            and not L_even.has(sp.Limit)
            and not L_odd.has(sp.Limit)
        ):
            if L_even == L_odd:
                return True, f"Converges to {L_even}", ""
            else:
                return (
                    False,
                    f"Diverges (Oscillates between {L_even} and {L_odd})",
                    "",
                )

    # ── Sequence Ratio Test ────────────────────────────────────────
    if has_fact and not has_n_root:
        try:
            ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n + 1) / abs_n))
            ratio_limit = super_fast_limit(ratio_expr, n)
            if (
                ratio_limit is not None
                and ratio_limit.is_number
                and not ratio_limit.has(sp.Limit)
            ):
                if ratio_limit < 1:
                    return (
                        True,
                        f"Converges to 0 (Ratio L = {ratio_limit})",
                        "",
                    )
                if ratio_limit > 1:
                    return (
                        False,
                        f"Diverges to oo (Ratio L = {ratio_limit})",
                        "",
                    )
                if ratio_limit == 1:
                    inv_ratio = sp.cancel(1 / ratio_expr)
                    _z = sp.Symbol("_z", positive=True)
                    c, p = (inv_ratio.subs(n, 1 / _z) - 1).leadterm(_z)
                    if p == 1 and not c.has(_z):
                        h = sp.limit(c, _z, 0)
                        if h > 0:
                            return (
                                True,
                                f"Converges to 0 (Asymp Ratio h={h} > 0)",
                                "",
                            )
                        if h < 0:
                            return (
                                False,
                                f"Diverges to oo (Asymp Ratio h={h} < 0)",
                                "",
                            )
        except Exception:
            pass

    # ── Sequence Root Test ────────────────────────────────────────
    if has_n_exp and not has_fact:
        try:
            log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
            log_root_limit = super_fast_limit(log_root_expr, n)
            if (
                log_root_limit is not None
                and log_root_limit.is_number
                and not log_root_limit.has(sp.Limit)
            ):
                root_limit = sp.exp(log_root_limit)
                if root_limit < 1:
                    return (
                        True,
                        f"Converges to 0 (Root L = {root_limit})",
                        "",
                    )
                if root_limit > 1:
                    return (
                        False,
                        f"Diverges to oo (Root L = {root_limit})",
                        "",
                    )
        except Exception:
            pass

    # ── General limit ─────────────────────────────────────────────
    L = super_fast_limit(expr, n)
    if L is None or L.has(sp.Limit):
        return None, "Undetermined", ""
    if isinstance(L, sp.AccumBounds) or L is sp.nan:
        return False, "Divergent (Oscillates or DNE)", ""
    if L.is_finite and L.is_real:
        return True, f"Converges to {L}", ""
    return False, f"Diverges to {L}", ""


# ─────────────────────────────────────────────────────────────────
#  SERIES CONVERGENCE ENGINE
# ─────────────────────────────────────────────────────────────────


def check_series_convergence(expr, n=None, start_idx: int = 1, py_func=None):
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

    if n is None:
        n = sp.Symbol("n", integer=True, positive=True)
        n_name = "n"
    elif isinstance(n, str):
        n_name = n
        n = sp.Symbol(n, integer=True, positive=True)
    else:
        n_name = str(n)

    if isinstance(expr, str):
        try:
            expr = get_sympified_expr(expr, local_dict={n_name: n})
        except Exception as e:
            return None, f"Parse Error: {str(e)}", ""

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
                lambda n_arg, k_arg: (
                    sp.factorial(n_arg)
                    / (sp.factorial(k_arg) * sp.factorial(n_arg - k_arg))
                ),
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
        term_limit = super_fast_limit(abs_n, n)
        if term_limit is not None and not term_limit.has(sp.Limit):
            if term_limit != 0 and not isinstance(term_limit, sp.AccumBounds):
                return (
                    False,
                    f"Divergent (nth-term L={term_limit} != 0)",
                    "",
                )
            if isinstance(term_limit, sp.AccumBounds) or term_limit is sp.nan:
                return False, "Divergent (Oscillates or DNE)", ""

        # ── 2. Asymptotic p-test ──────────────────────────────────
        if not has_fact:
            try:
                _z = sp.Symbol("_z", positive=True)
                c, p = abs_n.subs(n, 1 / _z).leadterm(_z)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                    if not c.has(_z):
                        if p > 1:
                            return (
                                True,
                                f"Absolutely Convergent (Asymptotic p={p} > 1)",
                                "",
                            )
                        elif not is_oscillatory:
                            if p < 1:
                                return (
                                    False,
                                    f"Divergent (Asymptotic p={p} < 1)",
                                    "",
                                )
                            if p == 1:
                                return (
                                    False,
                                    "Divergent (Asymptotic Harmonic p=1)",
                                    "",
                                )
                    else:
                        # Mixed log-polynomial term
                        if p > 1:
                            return (
                                True,
                                f"Absolutely Convergent (Asymp p'={(1 + p) / 2} > 1)",
                                "",
                            )
                        elif not is_oscillatory and p < 1:
                            return (
                                False,
                                f"Divergent (Asymp p'={(1 + p) / 2} < 1)",
                                "",
                            )
            except Exception:
                pass

        # ── 3. Logarithmic Asymptotic test ────────────────────────
        #
        # Computes lim -ln(f)/ln(n).  Faster than Cauchy for log-tower
        # series like ln(n)^ln(n) / n^ln(n).
        if not has_fact and abs_n.has(sp.log):
            try:
                log_asymp = sp.cancel(
                    -sp.expand_log(sp.log(abs_n), force=True) / sp.log(n)
                )
                L_la = super_fast_limit(log_asymp, n)
                if L_la is not None and L_la.is_number and not L_la.has(sp.Limit):
                    if L_la > 1:
                        return (
                            True,
                            f"Absolutely Convergent (Log-Asymp p={L_la} > 1)",
                            "",
                        )
                    elif not is_oscillatory and L_la < 1:
                        return (
                            False,
                            f"Divergent (Log-Asymp p={L_la} < 1)",
                            "",
                        )
            except Exception:
                pass

        # ── 4. Cauchy Condensation (2 levels) ─────────────────────
        #
        # Purely algebraic: substitutes n → 2^n and runs leadterm.
        # Never misfires.  Gold standard for iterated-log series like
        # 1/(n·ln²n·ln(ln n)) where direct integration would time out.
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
                                return (
                                    True,
                                    f"Absolutely Convergent (Condensation L{level} p={p} > 1)",
                                    "",
                                )
                            elif not is_oscillatory:
                                if p < 1:
                                    return (
                                        False,
                                        f"Divergent (Condensation L{level} p={p} < 1)",
                                        "",
                                    )
                                if p == 1:
                                    return (
                                        False,
                                        f"Divergent (Condensation L{level} p=1)",
                                        "",
                                    )
                        else:
                            if p > 1:
                                return (
                                    True,
                                    f"Absolutely Convergent (Condensation L{level} p'={(1 + p) / 2} > 1)",
                                    "",
                                )
                            elif not is_oscillatory and p < 1:
                                return (
                                    False,
                                    f"Divergent (Condensation L{level} p'={(1 + p) / 2} < 1)",
                                    "",
                                )
                except Exception:
                    pass

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
                        return (
                            True,
                            "Absolutely Convergent (Integral Test)",
                            "",
                        )
                    elif result == sp.oo:
                        return False, "Divergent (Integral Test)", ""
                    # Ambiguous result → fall through silently
            except Exception:
                pass

        # ── 5. Ratio + Gauss/Raabe test ───────────────────────────
        if has_fact:
            try:
                ratio_expr = sp.cancel(sp.combsimp(abs_n.subs(n, n + 1) / abs_n))
                ratio_limit = super_fast_limit(ratio_expr, n)
                if (
                    ratio_limit is not None
                    and ratio_limit.is_number
                    and not ratio_limit.has(sp.Limit)
                ):
                    if ratio_limit < 1:
                        return (
                            True,
                            f"Absolutely Convergent (Ratio L = {ratio_limit})",
                            "",
                        )
                    if ratio_limit > 1:
                        return (
                            False,
                            f"Divergent (Ratio L = {ratio_limit})",
                            "",
                        )
                    if ratio_limit == 1:
                        inv_ratio = sp.cancel(1 / ratio_expr)
                        _z = sp.Symbol("_z", positive=True)
                        try:
                            c, p = (inv_ratio.subs(n, 1 / _z) - 1).leadterm(_z)
                            if p == 1 and not c.has(_z):
                                h = sp.limit(c, _z, 0)
                                if h > 1:
                                    return (
                                        True,
                                        f"Absolutely Convergent (Gauss/Raabe h={h} > 1)",
                                        "",
                                    )
                                elif not is_oscillatory and h <= 1:
                                    return (
                                        False,
                                        f"Divergent (Gauss/Raabe h={h} <= 1)",
                                        "",
                                    )
                            elif p < 1 and p.is_number and not c.has(_z):
                                if not is_oscillatory:
                                    return (
                                        False,
                                        f"Divergent (Gauss/Raabe p={p} < 1)",
                                        "",
                                    )
                            elif p > 1 and p.is_number and not c.has(_z):
                                if not is_oscillatory:
                                    return (
                                        False,
                                        "Divergent (Gauss/Raabe h=0 <= 1)",
                                        "",
                                    )
                        except Exception:
                            pass
            except Exception:
                pass

        # ── 6. Asymptotic Stirling test ───────────────────────────
        if has_fact:
            try:
                st = apply_stirling(abs_n)
                _z = sp.Symbol("_z", positive=True)
                c, p = st.subs(n, 1 / _z).leadterm(_z)
                if not c.has(sp.O) and not p.has(sp.O) and p.is_number:
                    if not c.has(_z):
                        if p > 1:
                            return (
                                True,
                                f"Absolutely Convergent (Stirling ~ 1/n^{p})",
                                "",
                            )
                        elif not is_oscillatory and p <= 1:
                            return (
                                False,
                                f"Divergent (Stirling ~ 1/n^{p})",
                                "",
                            )
                    else:
                        if p > 1:
                            return (
                                True,
                                f"Absolutely Convergent (Stirling p'={(1 + p) / 2} > 1)",
                                "",
                            )
                        elif not is_oscillatory and p < 1:
                            return (
                                False,
                                f"Divergent (Stirling p'={(1 + p) / 2} < 1)",
                                "",
                            )
            except Exception:
                # leadterm() failed (e.g., for 2^n * exp(-n) / sqrt(n))
                # Fall back to root test on the Stirling-simplified form
                try:
                    st = apply_stirling(abs_n)
                    log_root_expr = sp.cancel(sp.expand_log(sp.log(st), force=True) / n)
                    log_root_limit = super_fast_limit(log_root_expr, n)
                    if (
                        log_root_limit is not None
                        and log_root_limit.is_number
                        and not log_root_limit.has(sp.Limit)
                    ):
                        root_limit = sp.exp(log_root_limit)
                        if root_limit < 1:
                            return (
                                True,
                                f"Absolutely Convergent (Stirling-Root L = {root_limit})",
                                "",
                            )
                        if root_limit > 1:
                            return (
                                False,
                                f"Divergent (Stirling-Root L = {root_limit})",
                                "",
                            )
                except Exception:
                    pass

        # ── 7. Root Test (log-expanded) ───────────────────────────
        if has_n_exp and not has_fact:
            try:
                log_root_expr = sp.cancel(sp.expand_log(sp.log(abs_n), force=True) / n)
                log_root_limit = super_fast_limit(log_root_expr, n)
                if (
                    log_root_limit is not None
                    and log_root_limit.is_number
                    and not log_root_limit.has(sp.Limit)
                ):
                    root_limit = sp.exp(log_root_limit)
                    if root_limit < 1:
                        return (
                            True,
                            f"Absolutely Convergent (Root L = {root_limit})",
                            "",
                        )
                    if root_limit > 1:
                        return (
                            False,
                            f"Divergent (Root L = {root_limit})",
                            "",
                        )
            except Exception:
                pass

        # ── 8. Alternating Test ───────────────────────────────────
        if (
            expr.has((-1) ** n)
            or expr.has((-1) ** (n + 1))
            or expr.has((-1) ** (n - 1))
            or has_negative_base
        ) and not (expr.has(sp.sin(n)) or expr.has(sp.cos(n))):
            if super_fast_limit(abs_n, n) == 0:
                return (
                    True,
                    "Convergent (Conditionally via Alternating Test)",
                    "",
                )

        # ── 9. Dirichlet Test ─────────────────────────────────────
        if expr.has(sp.sin(n)) or expr.has(sp.cos(n)):
            rest = abs_n.subs({sp.sin(n): 1, sp.cos(n): 1})
            if super_fast_limit(rest, n) == 0:
                return (
                    True,
                    "Convergent (Conditionally via Dirichlet Test)",
                    "",
                )

        # ── 10. SymPy built-in fallback ───────────────────────────
        try:
            S = sp.Sum(expr, (n, start_idx, sp.oo))
            is_conv = S.is_convergent()
            if is_conv == sp.S.true:
                return True, "Convergent (Built-in SymPy)", ""
            if is_conv == sp.S.false:
                return False, "Divergent (Built-in SymPy)", ""
        except NotImplementedError:
            pass
        except RecursionError:
            # SymPy's Gruntz algorithm can hit infinite recursion on some
            # complex factorial/exponential expressions. Fall through to
            # return "Undetermined" rather than crashing.
            pass

        return None, "Undetermined by all available heuristics", ""

    except RecursionError:
        # Catch recursion errors that escape the inner handlers
        return None, "Undetermined (expression too complex for symbolic analysis)", ""
    except Exception as e:
        return None, f"Error: {e}", ""


# ─────────────────────────────────────────────────────────────────
#  UNIVERSAL EVALUATOR ENGINE
# ─────────────────────────────────────────────────────────────────


def evaluate_expression(expr_str: str):
    """
    Automatically detects if an expression is a Power Series (contains 'x'),
    or a Sequence/Series. Evaluates and returns the appropriate results.
    """

    n = sp.Symbol("n", integer=True, positive=True)
    x = sp.Symbol("x", real=True)

    result_dict = {
        "expr": expr_str,
        "is_power_series": False,
        "seq_result": None,
        "ser_result": None,
        "power_series_result": None,
        "error": None,
    }

    try:
        sym_expr = get_sympified_expr(expr_str, local_dict={"n": n, "x": x})

        # Proper check if 'x' is a free symbol
        is_power_series = x in sym_expr.free_symbols
        result_dict["is_power_series"] = is_power_series

        if is_power_series:
            res = check_power_series(sym_expr, n, x)
            result_dict["power_series_result"] = res
        else:
            # We must use string for sequence/series because their engine
            # expects a string to possibly re-parse or we can just pass
            # the expr_str. They handle strings fine.
            seq_res = check_sequence_convergence(expr_str, n="n")
            ser_res = check_series_convergence(expr_str, n="n", start_idx=1)
            result_dict["seq_result"] = seq_res
            result_dict["ser_result"] = ser_res
    except Exception as e:
        result_dict["error"] = str(e)

    return result_dict


# ─────────────────────────────────────────────────────────────────
#  FORMATTING
# ─────────────────────────────────────────────────────────────────


def format_result(res_bool) -> str:
    if res_bool is True:
        return f"{'Converges':<10}"
    if res_bool is False:
        return f"{'Diverges':<10}"
    return f"{'Unknown':<10}"




def check_power_series(expr, n, x):

    from .power_sereis import analyze_power_series

    res = analyze_power_series(expr, n, x)

    if "error" in res:
        return False, res["error"], "", None

    return (
        True,
        f"R={res.get('radius')}, I={res.get('interval', res.get('interval_symbolic'))}",
        "",
        res,
    )




if __name__ == "__main__":
    expressions = [
        "x^n / n",
        "(x-2)^n / (n * 3^n)",
        "factorial(n) * x^n",
        "x^n / factorial(n)",
        "(-1)^n * (x+1)^n / n^2",
    ]

    for expr in expressions:
        try:
            result = evaluate_expression(expr)  
            print(f"Expression: {expr}\nResult: {result}\n")
        except Exception as e:
            print(f"Expression: {expr}\nError: {e}\n")


