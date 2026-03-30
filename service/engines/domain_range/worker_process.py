"""
Standalone worker process for SymPy computations.

This module MUST NOT import from algo.py. On Windows, multiprocessing uses
the 'spawn' context which re-imports this file in the subprocess from scratch.
Circular import risk and wasteful re-initialisation are both avoided by keeping
this file fully self-contained.

All SymPy imports are lazy (inside functions) to minimise subprocess startup time.
"""

import numpy as np

from sympy import (
    Abs,
    Add,
    Complement,
    Dummy,
    EmptySet,
    FiniteSet,
    Interval,
    Max,
    Mul,
    Pow,
    Rational,
    S,
    Symbol,
    Union,
    ceiling,
    cos,
    cot,
    csc,
    floor,
    gcd,
    lambdify,
    limit,
    nan,
    nsimplify,
    oo,
    pi,
    sec,
    sign,
    sin,
    solveset,
    tan,
    zoo,
)
from sympy import Union as SymUnion
from sympy import denom as sympy_denom

from sympy.calculus.util import (
    AccumBounds,
    continuous_domain,
    function_range,
    maximum,
    minimum,
)

from sympy.sets.conditionset import ConditionSet


def _float_to_odd_rational_w(exp_val):
    """Convert float exponent to p/q Rational with odd q, or None."""

    for q in [3, 5, 7, 9, 11]:
        for p in range(1, 2 * q):
            if abs(float(exp_val) - p / q) < 1e-6:
                return Rational(p, q)
            if abs(float(exp_val) + p / q) < 1e-6:
                return Rational(-p, q)
    return None


def _has_real_odd_root_w(expr, var):

    for sub in expr.atoms(Pow):
        if sub.base.has(var):
            if isinstance(sub.exp, Rational):
                if sub.exp.q % 2 == 1 and sub.exp.q > 1:
                    return True
            elif getattr(sub.exp, "is_Float", False) or getattr(
                sub.exp, "is_Number", False
            ):
                r = _float_to_odd_rational_w(sub.exp)
                if r is not None and r.q % 2 == 1 and r.q > 1:
                    return True
    return False


def _rewrite_real_roots_w(expr, var):

    replacements = {}
    for sub in expr.atoms(Pow):
        if sub.base.has(var):
            rat_exp = None
            if isinstance(sub.exp, Rational):
                rat_exp = sub.exp
            elif getattr(sub.exp, "is_Float", False) or getattr(
                sub.exp, "is_Number", False
            ):
                rat_exp = _float_to_odd_rational_w(sub.exp)
            if rat_exp is not None:
                p, q = rat_exp.p, rat_exp.q
                if q % 2 == 1 and q > 1:
                    if p % 2 == 1:
                        replacements[sub] = sign(sub.base) * Abs(sub.base) ** rat_exp
                    else:
                        replacements[sub] = Abs(sub.base) ** rat_exp
    for old, new in replacements.items():
        expr = expr.subs(old, new)
    return expr


# ---------------------------------------------------------------------------
# Trig period detection (worker-side, no algo.py dependency)
# ---------------------------------------------------------------------------


def _get_fundamental_period_w(f, x):
    """
    Determine the fundamental period of f(x) by inspecting trig sub-expressions.
    Returns a SymPy expression or None.
    """

    TRIG_PERIODS = {
        sin: 2 * pi,
        cos: 2 * pi,
        tan: pi,
        cot: pi,
        sec: 2 * pi,
        csc: 2 * pi,
    }

    candidates = []
    for func_cls, base_period in TRIG_PERIODS.items():
        for sub in f.atoms(func_cls):
            arg = sub.args[0]
            coeff = arg.coeff(x)
            if coeff != 0 and coeff.is_real:
                try:
                    candidates.append(base_period / abs(coeff))
                except Exception:
                    pass

    if not candidates:
        return None

    result = candidates[0]
    for p in candidates[1:]:
        try:
            result = (result * p) / gcd(result, p)
        except Exception:
            result = Max(result, p)

    return result


def _expand_periodic_domain_w(f, x, domain):
    """
    Worker-side periodic domain expansion.

    Detects when continuous_domain() returned only one period of a genuinely
    periodic domain and expands it into a Union covering ±NUM_PERIODS periods.

    This is the same logic as expand_periodic_domain() in algo.py but written
    without any imports from that module.

    Returns (domain, was_expanded: bool).
    """

    NUM_PERIODS = 12

    # ── Guard 1: must have trig ──────────────────────────────────────────
    TRIG_FUNCS = (sin, cos, tan, cot, sec, csc)
    if not any(f.has(tc) for tc in TRIG_FUNCS):
        return domain, False

    # ── Guard 2: determinable period ─────────────────────────────────────
    period_sym = _get_fundamental_period_w(f, x)
    if period_sym is None:
        return domain, False

    try:
        period_float = float(period_sym.evalf())
    except Exception:
        return domain, False

    if period_float <= 0 or period_float > 1e6:
        return domain, False

    # ── Guard 3: domain looks like a single truncated period ─────────────

    if isinstance(domain, Complement):
        base = domain.args[0]
        if isinstance(base, Interval):
            component_list = [base]
        elif isinstance(base, Union) and all(
            isinstance(a, Interval) for a in base.args
        ):
            component_list = list(base.args)
        else:
            return domain, False
    elif isinstance(domain, Interval):
        component_list = [domain]
    elif isinstance(domain, Union) and all(
        isinstance(a, Interval) for a in domain.args
    ):
        component_list = list(domain.args)
    else:
        return domain, False

    try:
        span_start = min(float(c.start.evalf()) for c in component_list)
        span_end = max(float(c.end.evalf()) for c in component_list)
    except Exception:
        return domain, False

    span_width = span_end - span_start
    if span_width >= period_float - 1e-6:
        return domain, False

    # ── Guard 4: numerical verification ──────────────────────────────────
    try:
        # Build a safe numeric evaluator (handles odd-power roots)
        f_rw = _rewrite_real_roots_w(f, x) if _has_real_odd_root_w(f, x) else f
        modules = [
            {
                "Heaviside": lambda t: np.heaviside(t, 0.5),
                "Max": np.maximum,
                "Min": np.minimum,
            },
            "numpy",
        ]
        f_num_raw = lambdify(x, f_rw, modules=modules)

        def safe_eval(xv):
            try:
                v = f_num_raw(float(xv))
                if isinstance(v, complex):
                    return v.real if abs(v.imag) < 1e-10 else np.nan
                v = float(v)
                return v if np.isfinite(v) else np.nan
            except Exception:
                return np.nan

        mid = span_start + span_width * 0.5
        val_base = safe_eval(mid)
        val_next = safe_eval(mid + period_float)
        base_ok = np.isfinite(val_base) and np.isreal(val_base)
        next_ok = np.isfinite(val_next) and np.isreal(val_next)

        if not (base_ok and next_ok):
            return domain, False

        # Verify that a point in the GAP between periods is invalid
        gap_pt = span_end + period_float * 0.25
        val_gap = safe_eval(gap_pt)
        gap_invalid = (not np.isfinite(val_gap)) or (not np.isreal(val_gap))

        if not gap_invalid:
            # Domain is actually denser than one period — don't expand
            return domain, False

    except Exception:
        return domain, False

    # ── Build the periodic union ──────────────────────────────────────────
    try:
        all_intervals = []
        for k in range(-NUM_PERIODS, NUM_PERIODS + 1):
            shift = k * period_sym
            for comp in component_list:
                all_intervals.append(
                    Interval(
                        comp.start + shift,
                        comp.end + shift,
                        comp.left_open,
                        comp.right_open,
                    )
                )
        return Union(*all_intervals), True
    except Exception:
        return domain, False


# ---------------------------------------------------------------------------
# Behavior analysis (standalone, no algo.py dependency)
# ---------------------------------------------------------------------------


def _analyze_function_behavior_standalone(f, x, domain):
    """
    Standalone version of analyze_function_behavior.
    Returns (has_inf_neg, has_inf_pos, left_lim, right_lim, sing_limits).
    """

    has_inf_pos = False
    has_inf_neg = False
    left_lim = None
    right_lim = None
    sing_limits = []

    f_for_limits = _rewrite_real_roots_w(f, x) if _has_real_odd_root_w(f, x) else f

    try:
        lim_pos = limit(f_for_limits, x, oo)
        if lim_pos == oo:
            has_inf_pos = True
            right_lim = oo
        elif lim_pos == -oo:
            has_inf_neg = True
            right_lim = -oo
        elif isinstance(lim_pos, AccumBounds):
            if lim_pos.max == oo:
                has_inf_pos = True
            if lim_pos.min == -oo:
                has_inf_neg = True
        elif lim_pos.has(oo) and (lim_pos.has(AccumBounds) or lim_pos.has(sign)):
            has_inf_pos = True
            has_inf_neg = True
        elif lim_pos not in [zoo, nan] and not lim_pos.has(oo):
            right_lim = lim_pos
    except Exception:
        pass

    try:
        lim_neg = limit(f_for_limits, x, -oo)
        if lim_neg == oo:
            has_inf_pos = True
            left_lim = oo
        elif lim_neg == -oo:
            has_inf_neg = True
            left_lim = -oo
        elif isinstance(lim_neg, AccumBounds):
            if lim_neg.max == oo:
                has_inf_pos = True
            if lim_neg.min == -oo:
                has_inf_neg = True
        elif lim_neg.has(oo) and (lim_neg.has(AccumBounds) or lim_neg.has(sign)):
            has_inf_pos = True
            has_inf_neg = True
        elif lim_neg not in [zoo, nan] and not lim_neg.has(oo):
            left_lim = lim_neg
    except Exception:
        pass

    if f_for_limits.has(Abs):
        try:
            if limit(f_for_limits, x, oo) == oo:
                has_inf_pos = True
            if limit(f_for_limits, x, -oo) == oo:
                has_inf_pos = True
        except Exception:
            pass

    try:
        d = sympy_denom(f_for_limits)
        if d != 1:
            sing_pts = solveset(d, x, S.Reals)
            if isinstance(sing_pts, FiniteSet):
                for pt in sing_pts:
                    try:
                        ll = limit(f_for_limits, x, pt, "-")
                        if ll == oo:
                            has_inf_pos = True
                        elif ll == -oo:
                            has_inf_neg = True
                        elif ll not in [zoo, nan] and not ll.has(oo):
                            sing_limits.append((ll, pt))

                        lr = limit(f_for_limits, x, pt, "+")
                        if lr == oo:
                            has_inf_pos = True
                        elif lr == -oo:
                            has_inf_neg = True
                        elif lr not in [zoo, nan] and not lr.has(oo):
                            sing_limits.append((lr, pt))
                    except Exception:
                        pass
    except Exception:
        pass

    try:
        boundary_pts = []
        if isinstance(domain, Union):
            for comp in domain.args:
                if isinstance(comp, Interval):
                    if comp.start.is_finite:
                        boundary_pts.append((comp.start, "+"))
                    if comp.end.is_finite:
                        boundary_pts.append((comp.end, "-"))
        elif isinstance(domain, Interval):
            if domain.start.is_finite:
                boundary_pts.append((domain.start, "+"))
            if domain.end.is_finite:
                boundary_pts.append((domain.end, "-"))

        for pt, dir in boundary_pts:
            try:
                l = limit(f_for_limits, x, pt, dir)
                if l == oo:
                    has_inf_pos = True
                elif l == -oo:
                    has_inf_neg = True
                elif l not in [zoo, nan] and not l.has(oo):
                    sing_limits.append((l, pt))
            except Exception:
                pass
    except Exception:
        pass

    return has_inf_neg, has_inf_pos, left_lim, right_lim, sing_limits


# ---------------------------------------------------------------------------
# Robust integer-valued check (worker-side, mirrors algo.py logic)
# ---------------------------------------------------------------------------


def _is_term_integer_valued_w(term):
    """
    True if a single additive term is provably integer-valued.
    Handles: integer constants, floor(g), ceiling(g), n*floor(g), n*ceiling(g).
    """

    if term.is_integer and term.is_number:
        return True
    if term.func in (floor, ceiling):
        return True
    if term.func is Mul:
        non_num = [a for a in term.args if not (a.is_number and a.is_integer)]
        return len(non_num) == 1 and non_num[0].func in (floor, ceiling)
    return False


def _has_integer_valued_output_w(f):
    """
    Standalone version of has_integer_valued_output.
    Returns True ONLY when the entire expression is provably integer-valued.
    x - floor(x) → False.  floor(x) + 1 → True.
    """

    if f.func in (floor, ceiling):
        return True
    if f.func is Mul:
        non_num = [a for a in f.args if not (a.is_number and a.is_integer)]
        if len(non_num) == 1 and non_num[0].func in (floor, ceiling):
            return True
        return False
    if f.func is Add:
        return all(_is_term_integer_valued_w(term) for term in f.args)
    return False


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


def worker_loop(q_in, q_out):
    """
    Main loop executed inside the worker subprocess.

    Receives (task_type, args) tuples and puts ('ok', result) or
    ('err', message) back.  All SymPy imports are lazy so subprocess
    startup stays fast (~30 ms).

    Task types
    ----------
    domain          → continuous_domain + periodic expansion
    range           → function_range
    min_max         → minimum + maximum
    limit           → _analyze_function_behavior_standalone
    solveset_empty  → solveset(f - val) == EmptySet?
    integer_check   → _has_integer_valued_output_w
    """
    while True:
        try:
            msg = q_in.get()
            if msg is None:  # sentinel → clean shutdown
                break

            task_type, args = msg

            # ── domain ────────────────────────────────────────────────────
            if task_type == "domain":
                f, x, search_set = args

                raw_domain = continuous_domain(f, x, search_set)

                # Post-process: expand if SymPy only found one trig period
                expanded, was_expanded = _expand_periodic_domain_w(f, x, raw_domain)
                res = expanded

            # ── range ─────────────────────────────────────────────────────
            elif task_type == "range":
                # function_range works best on a single-connected domain;
                # for a Union domain we compute per-component and union results.

                f, x, domain = args

                if isinstance(domain, SymUnion):
                    sub_ranges = []
                    for comp in domain.args:
                        try:
                            sr = function_range(f, x, comp)
                            if sr not in (None, EmptySet):
                                sub_ranges.append(sr)
                        except Exception:
                            pass
                    res = SymUnion(*sub_ranges) if sub_ranges else None
                else:
                    res = function_range(f, x, domain)

            # ── composited_range ──────────────────────────────────────────
            elif task_type == "composited_range":

                def extract_base_intervals(dom):
                    if isinstance(dom, Complement):
                        return extract_base_intervals(dom.args[0])
                    elif isinstance(dom, Union):
                        intervals = [a for a in dom.args if isinstance(a, Interval)]
                        if intervals:
                            return Union(*intervals)
                        return S.EmptySet
                    return dom

                def _composited_range_recursive(expr, var, dom):
                    if expr == var:
                        return dom
                    if expr.is_number:
                        return FiniteSet(expr)
                    if expr.count(var) != 1:
                        return None
                    try:
                        if hasattr(expr, "__call__") and not hasattr(expr, "args"):
                            return None
                        arg = next(a for a in expr.args if a.has(var))
                        inner_dom = _composited_range_recursive(arg, var, dom)
                        if inner_dom is None or inner_dom == S.EmptySet:
                            return None
                        dummy = Dummy("u", real=True)
                        outer_expr = expr.subs(arg, dummy)
                        return function_range(outer_expr, dummy, inner_dom)
                    except Exception:
                        return None

                f, x, domain = args
                res = _composited_range_recursive(f, x, extract_base_intervals(domain))

            # ── min/max ───────────────────────────────────────────────────
            elif task_type == "min_max":
                f, x, domain = args
                search_dom = domain if domain.is_subset(S.Reals) else S.Reals
                mn = minimum(f, x, search_dom)
                mx = maximum(f, x, search_dom)
                res = (mn, mx)

            # ── limit analysis ────────────────────────────────────────────
            elif task_type == "limit":
                f, x, domain = args
                res = _analyze_function_behavior_standalone(f, x, domain)

            # ── solveset_empty ────────────────────────────────────────────
            elif task_type == "solveset_empty":
                f, x, val, domain = args
                search_dom = domain if domain.is_subset(S.Reals) else S.Reals
                try:
                    if getattr(val, "is_Float", False) or isinstance(val, float):
                        val_exact = nsimplify(val, rational=True)
                    else:
                        val_exact = val
                    sol = solveset(f - val_exact, x, search_dom)
                    if sol == EmptySet:
                        res = True
                    elif isinstance(sol, ConditionSet):
                        res = "unknown"
                    else:
                        res = False
                except Exception:
                    res = "unknown"

            # ── integer_check (optional explicit task) ────────────────────
            elif task_type == "integer_check":
                (f,) = args
                res = _has_integer_valued_output_w(f)

            else:
                res = None

            q_out.put(("ok", res))

        except Exception as e:
            q_out.put(("err", str(e)))
