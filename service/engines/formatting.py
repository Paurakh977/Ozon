import sympy as sp
from sympy import S, EmptySet, FiniteSet, Interval, ImageSet, Complement, Union, Symbol, ConditionSet, Float

def _format_periodic_union(obj, fmt_val_fn, fmt_interval_fn):
    """
    Detect a uniformly-periodic Union and format it as  U_{n in Z} [a+nT, b+nT]
    instead of listing dozens of identical-looking intervals.

    Returns a formatted string if periodic, else None.
    """
    if not isinstance(obj, Union):
        return None

    parts = [a for a in obj.args if isinstance(a, Interval)]
    if len(parts) < 5:
        return None

    # Sort by start point
    try:
        parts_sorted = sorted(parts, key=lambda iv: float(iv.start.evalf()))
    except Exception:
        return None

    # Check equal spacing (period)
    try:
        spacings = [
            float((parts_sorted[i + 1].start - parts_sorted[i].start).evalf())
            for i in range(len(parts_sorted) - 1)
        ]
        lengths = [float((p.end - p.start).evalf()) for p in parts_sorted]
        tol = 1e-6
        if (
            max(abs(s - spacings[0]) for s in spacings) > tol
            or max(abs(l - lengths[0]) for l in lengths) > tol
        ):
            return None
    except Exception:
        return None

    # Pick the anchor interval closest to x=0
    anchor = min(parts_sorted, key=lambda iv: abs(float(iv.start.evalf())))

    lb = "(" if anchor.left_open else "["
    rb = ")" if anchor.right_open else "]"

    try:
        a_str = fmt_val_fn(anchor.start)
        b_str = fmt_val_fn(anchor.end)
        T_str = fmt_val_fn(parts_sorted[1].start - parts_sorted[0].start)
        return f"U_{{n in Z}} {lb}{a_str} + {T_str}*n, {b_str} + {T_str}*n{rb}"
    except Exception:
        return None

def format_math_set(obj):
    if isinstance(obj, str):
        if obj == "Reals":
            return "(-oo, oo)"
        elif obj == "Integers":
            return "Integers"
        try:
            # We don't want to eval random strings if they aren't safe
            # but let's leave it as is if it was in the original code
            pass
        except Exception:
            return obj

    if obj == S.Reals:
        return "(-oo, oo)"
    if obj == S.Integers:
        return "Integers"
    if obj == EmptySet:
        return "EmptySet"
    if obj is None:
        return "None"

    def fmt_val(val):
        if val == S.Infinity:
            return "oo"
        if val == S.NegativeInfinity:
            return "-oo"
        if getattr(val, "is_Float", False):
            s = str(val)
            if "e" not in s.lower() and "." in s:
                s = s.rstrip("0").rstrip(".")
                if not s:
                    return "0"
            return s
        return str(val)

    if isinstance(obj, (list, tuple)):
        return "[" + ", ".join(format_math_set(item) for item in obj) + "]"

    if isinstance(obj, dict):
        return {k: format_math_set(v) for k, v in obj.items()}

    if isinstance(obj, FiniteSet):
        items = sorted([fmt_val(arg) for arg in obj.args])
        return "{" + ", ".join(items) + "}"

    def fmt_interval(interv):
        lo_str = fmt_val(interv.start)
        hi_str = fmt_val(interv.end)
        left_bracket = "(" if interv.left_open or lo_str == "-oo" else "["
        right_bracket = ")" if interv.right_open or hi_str == "oo" else "]"
        return f"{left_bracket}{lo_str}, {hi_str}{right_bracket}"

    if isinstance(obj, Interval):
        return fmt_interval(obj)

    if isinstance(obj, ImageSet):
        try:
            expr = obj.lamda.expr
            var = obj.lamda.variables[0]
            n_sym = Symbol("n")
            expr_n = expr.subs(var, n_sym)
            return f"{{{fmt_val(expr_n)} | n in Z}}"
        except Exception:
            return str(obj)

    if isinstance(obj, Complement):
        base, exc = obj.args
        base_str = format_math_set(base)
        exc_str = format_math_set(exc)
        if base_str == "(-oo, oo)":
            base_str = "R"
        return f"{base_str} \\ {exc_str}"

    if isinstance(obj, Union):
        # ── Attempt compact periodic representation ──────────────────────
        periodic_str = _format_periodic_union(obj, fmt_val, fmt_interval)
        if periodic_str is not None:
            return periodic_str

        parts = []
        for arg in obj.args:
            if isinstance(arg, Interval):
                parts.append(fmt_interval(arg))
            elif isinstance(arg, FiniteSet):
                items = sorted([fmt_val(x) for x in arg.args])
                parts.append("{" + ", ".join(items) + "}")
            else:
                parts.append(format_math_set(arg))
        return " U ".join(parts)

    if isinstance(obj, ConditionSet):
        try:
            expr = obj.condition.lhs - obj.condition.rhs if isinstance(obj.condition, sp.Eq) else obj.condition
            base_str = format_math_set(obj.base_set)
            return f"{{x in {base_str} | {fmt_val(expr)} = 0}}"
        except Exception:
            return str(obj)

    return fmt_val(obj)

def round_sympy_expr(expr, digits=3):
    if isinstance(expr, (list, tuple)):
        return type(expr)(round_sympy_expr(item, digits) for item in expr)

    if isinstance(expr, dict):
        return {k: round_sympy_expr(v, digits) for k, v in expr.items()}

    if isinstance(expr, Float):
        return Float(round(float(expr), digits), digits)

    elif isinstance(expr, Interval):
        return Interval(
            round_sympy_expr(expr.start, digits),
            round_sympy_expr(expr.end, digits),
            expr.left_open,
            expr.right_open,
        )

    elif isinstance(expr, Union):
        return Union(*[round_sympy_expr(arg, digits) for arg in expr.args])

    elif isinstance(expr, FiniteSet):
        return FiniteSet(*[round_sympy_expr(arg, digits) for arg in expr.args])

    elif isinstance(expr, Complement):
        return Complement(
            round_sympy_expr(expr.args[0], digits),
            round_sympy_expr(expr.args[1], digits),
            evaluate=False
        )
        
    elif isinstance(expr, ImageSet):
        return ImageSet(
            expr.lamda,
            round_sympy_expr(expr.base_set, digits)
        )

    return expr
