"""
Standalone worker process for SymPy computations.

This module MUST NOT import from algo.py. On Windows, multiprocessing uses
the 'spawn' context which re-imports this file in the subprocess from scratch.
If this file imported algo.py, that would trigger algo's module-level code
(colorama.init, warnings.filterwarnings, _sympy_worker = None, etc.) in the
subprocess — harmless but wasteful, and a circular-import risk.

All SymPy imports are done locally inside functions to minimise subprocess
startup time (~200ms if done at module level vs ~30ms lazy).
"""


# ---------------------------------------------------------------------------
# Standalone helpers (copied from algo.py to avoid circular import)
# ---------------------------------------------------------------------------

def _float_to_odd_rational_w(exp_val):
    """Convert float exponent to p/q Rational with odd q, or None."""
    from sympy import Rational
    for q in [3, 5, 7, 9, 11]:
        for p in range(1, 2 * q):
            if abs(float(exp_val) - p / q) < 1e-6:
                return Rational(p, q)
            if abs(float(exp_val) + p / q) < 1e-6:
                return Rational(-p, q)
    return None


def _has_real_odd_root_w(expr, var):
    from sympy import Pow, Rational
    for sub in expr.atoms(Pow):
        if sub.base.has(var):
            if isinstance(sub.exp, Rational):
                if sub.exp.q % 2 == 1 and sub.exp.q > 1:
                    return True
            elif getattr(sub.exp, 'is_Float', False) or getattr(sub.exp, 'is_Number', False):
                r = _float_to_odd_rational_w(sub.exp)
                if r is not None and r.q % 2 == 1 and r.q > 1:
                    return True
    return False


def _rewrite_real_roots_w(expr, var):
    from sympy import Pow, Rational, sign, Abs
    replacements = {}
    for sub in expr.atoms(Pow):
        if sub.base.has(var):
            rat_exp = None
            if isinstance(sub.exp, Rational):
                rat_exp = sub.exp
            elif getattr(sub.exp, 'is_Float', False) or getattr(sub.exp, 'is_Number', False):
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


def _analyze_function_behavior_standalone(f, x, domain):
    """
    Standalone version of analyze_function_behavior.
    Inlined here so the worker never imports from algo.py.
    """
    from sympy import limit, oo, zoo, nan, sign, Abs, solveset, FiniteSet, S
    from sympy.calculus.util import AccumBounds

    has_inf_pos = False
    has_inf_neg = False
    left_lim = None
    right_lim = None
    sing_limits = []

    f_for_limits = _rewrite_real_roots_w(f, x) if _has_real_odd_root_w(f, x) else f

    try:
        lim_pos = limit(f_for_limits, x, oo)
        if lim_pos == oo:
            has_inf_pos = True; right_lim = oo
        elif lim_pos == -oo:
            has_inf_neg = True; right_lim = -oo
        elif isinstance(lim_pos, AccumBounds):
            if lim_pos.max == oo:  has_inf_pos = True
            if lim_pos.min == -oo: has_inf_neg = True
        elif lim_pos.has(oo) and (lim_pos.has(AccumBounds) or lim_pos.has(sign)):
            has_inf_pos = True; has_inf_neg = True
        elif lim_pos not in [zoo, nan]:
            right_lim = lim_pos
    except Exception:
        pass

    try:
        lim_neg = limit(f_for_limits, x, -oo)
        if lim_neg == oo:
            has_inf_pos = True; left_lim = oo
        elif lim_neg == -oo:
            has_inf_neg = True; left_lim = -oo
        elif isinstance(lim_neg, AccumBounds):
            if lim_neg.max == oo:  has_inf_pos = True
            if lim_neg.min == -oo: has_inf_neg = True
        elif lim_neg.has(oo) and (lim_neg.has(AccumBounds) or lim_neg.has(sign)):
            has_inf_pos = True; has_inf_neg = True
        elif lim_neg not in [zoo, nan]:
            left_lim = lim_neg
    except Exception:
        pass

    if f_for_limits.has(Abs):
        try:
            if limit(f_for_limits, x, oo)  == oo: has_inf_pos = True
            if limit(f_for_limits, x, -oo) == oo: has_inf_pos = True
        except Exception:
            pass

    try:
        from sympy import denom as sympy_denom
        d = sympy_denom(f_for_limits)
        if d != 1:
            sing_pts = solveset(d, x, S.Reals)
            if isinstance(sing_pts, FiniteSet):
                for pt in sing_pts:
                    try:
                        ll = limit(f_for_limits, x, pt, '-')
                        lr = limit(f_for_limits, x, pt, '+')
                        if ll == oo: has_inf_pos = True
                        elif ll == -oo: has_inf_neg = True
                        elif ll not in [zoo, nan]: sing_limits.append(ll)
                        
                        if lr == oo: has_inf_pos = True
                        elif lr == -oo: has_inf_neg = True
                        elif lr not in [zoo, nan]: sing_limits.append(lr)
                    except Exception:
                        pass
    except Exception:
        pass

    return has_inf_neg, has_inf_pos, left_lim, right_lim, sing_limits


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def worker_loop(q_in, q_out):
    """
    Main loop executed inside the worker subprocess.

    Receives (task_type, args) tuples and puts ('ok', result) or
    ('err', message) back.  All SymPy imports are lazy so subprocess
    startup stays fast.
    """
    while True:
        try:
            msg = q_in.get()
            if msg is None:          # sentinel → clean shutdown
                break

            task_type, args = msg

            if task_type == 'domain':
                from sympy.calculus.util import continuous_domain
                res = continuous_domain(*args)

            elif task_type == 'range':
                from sympy.calculus.util import function_range
                res = function_range(*args)

            elif task_type == 'min_max':
                from sympy.calculus.util import minimum, maximum
                from sympy import S
                f, x, domain = args
                search_dom = domain if domain.is_subset(S.Reals) else S.Reals
                mn = minimum(f, x, search_dom)
                mx = maximum(f, x, search_dom)
                res = (mn, mx)

            elif task_type == 'limit':
                f, x, domain = args
                res = _analyze_function_behavior_standalone(f, x, domain)

            elif task_type == 'solveset_empty':
                from sympy import solveset, S, EmptySet, nsimplify
                from sympy.sets.conditionset import ConditionSet
                f, x, val, domain = args
                search_dom = domain if domain.is_subset(S.Reals) else S.Reals
                try:
                    # Convert float values to exact rationals/constants to avoid
                    # solveset hangs or EmptySet false positives with floats.
                    if getattr(val, 'is_Float', False) or isinstance(val, float):
                        val_exact = nsimplify(val, rational=True)
                    else:
                        val_exact = val
                    sol = solveset(f - val_exact, x, search_dom)
                    if sol == EmptySet:
                        res = True
                    elif isinstance(sol, ConditionSet):
                        res = 'unknown'
                    else:
                        res = False
                except Exception:
                    res = 'unknown'

            else:
                res = None

            q_out.put(('ok', res))

        except Exception as e:
            q_out.put(('err', str(e)))