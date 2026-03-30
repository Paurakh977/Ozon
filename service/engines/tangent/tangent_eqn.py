"""
=============================================================================
 ROBUST TANGENT LINE ENGINE  (SymPy 1.14+)
=============================================================================
  • Tangent form:  y - f(a) = f'(a) · (x - a)
      where  a  is the constant tangency point
             x  is the running variable
  • Example: f(x) = x²  →  y - a² = 2a(x - a)
  • Three-tier derivative strategy:
       1. Symbolic diff + simplify
       2. Limit-based fallback for removable singularities / Piecewise mess
       3. Numerical central-difference verification (always runs)
=============================================================================
"""

from __future__ import annotations
import math, textwrap, traceback
from dataclasses import dataclass
from typing import Optional

import sympy as sp
from sympy import (
    symbols,
    sympify,
    diff,
    limit,
    simplify,
    expand,
    factor,
    latex,
    lambdify,
    zoo,
    nan,
    oo,
    pi,
    E,
    floor,
    ceiling,
    Abs,
    Piecewise,
    sin,
    cos,
    tan,
    exp,
    log,
    sqrt,
    asin,
    acos,
    atan,
)
import numpy as np

from engines import get_sympified_expr


x = symbols("x", real=True)  # running variable in the tangent line
a = symbols("a", real=True)  # constant tangency point


@dataclass
class TangentResult:
    func_str: str
    ft_expr: Optional[sp.Expr] = None  # f(a)
    fpt_expr: Optional[sp.Expr] = None  # f'(a)  — the slope
    lhs_expr: Optional[sp.Expr] = None  # y - f(a)
    rhs_expr: Optional[sp.Expr] = None  # f'(a) * (x - a)
    deriv_expr: Optional[sp.Expr] = None  # f'(x) in full
    strategy: str = "symbolic"
    status: str = "OK"
    error: str = ""
    num_error: float = float("nan")


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _parse(func_str: str) -> sp.Expr:
    return get_sympified_expr(func_str, local_dict={"x": x, "a": a})


def _simplify(expr: sp.Expr) -> sp.Expr:
    try:
        s = simplify(expr)
        s2 = expand(s)
        try:
            sf = factor(s2)
            if len(str(sf)) <= len(str(s2)):
                s2 = sf
        except Exception:
            pass
        return s2
    except Exception:
        return expr


def _eval_at_a(expr: sp.Expr, a_sym: sp.Symbol) -> sp.Expr:
    """Substitute x → a, with limit fallback."""
    try:
        val = expr.subs(x, a_sym)
        if val in (zoo, nan, sp.nan, sp.zoo):
            raise ValueError("zoo/nan")
        if x in val.free_symbols:
            raise ValueError("x still present")
        return simplify(val)
    except Exception:
        try:
            return simplify(limit(expr, x, a_sym))
        except Exception:
            return sp.Integer(0)


def _num_deriv(f_lam, a_val: float, h: float = 1e-7) -> float:
    try:
        return (
            -f_lam(a_val + 2 * h)
            + 8 * f_lam(a_val + h)
            - 8 * f_lam(a_val - h)
            + f_lam(a_val - 2 * h)
        ) / (12 * h)
    except Exception:
        return float("nan")


def _test_point(f_expr: sp.Expr) -> float:
    candidates = [1.5, 2.0, 0.5, 3.0, 0.3, 0.7, 4.0, -1.5]
    try:
        f_lam = lambdify(x, f_expr, modules=["numpy", "sympy"])
    except Exception:
        return 1.5
    for c in candidates:
        try:
            v = f_lam(c)
            if isinstance(v, (int, float, np.floating)) and np.isfinite(float(v)):
                return float(c)
        except Exception:
            continue
    return 1.5


# ─────────────────────────────────────────────────────────────────────────────
#  ENGINE
# ─────────────────────────────────────────────────────────────────────────────


class TangentEngine:
    def compute(self, func_str: str) -> TangentResult:
        res = TangentResult(func_str=func_str)
        try:
            self._core(func_str, res)
        except Exception as exc:
            res.status = "ERROR"
            res.error = f"{type(exc).__name__}: {exc}"

        return res

    def _core(self, func_str: str, res: TangentResult):
        f_expr = _parse(func_str)

        # ── Derivative ────────────────────────────────────────────────────
        deriv_raw = self._differentiate(f_expr, res)
        deriv = _simplify(deriv_raw)
        res.deriv_expr = deriv

        # ── Evaluate at tangency point a ──────────────────────────────────
        fa = _eval_at_a(f_expr, a)  # f(a)
        fpa = _eval_at_a(deriv, a)  # f'(a)

        res.ft_expr = fa
        res.fpt_expr = fpa

        # ── Build  y - f(a) = f'(a)·(x - a) ─────────────────────────────
        res.lhs_expr = sp.Symbol("y") - fa  # symbolic LHS for display
        res.rhs_expr = _simplify(fpa * (x - a))  # RHS simplified

        res.status = "OK"

        # ── Numerical verification ────────────────────────────────────────
        res.num_error = self._numcheck(f_expr, deriv)

    def _differentiate(self, f_expr: sp.Expr, res: TangentResult) -> sp.Expr:
        # Tier 1 – symbolic diff
        try:
            d = diff(f_expr, x)
            if not d.atoms(sp.Derivative):
                res.strategy = "symbolic"
                return d
        except Exception:
            pass
        # Tier 2 – limit definition
        try:
            h = sp.Symbol("h", positive=True)
            d = limit((f_expr.subs(x, x + h) - f_expr) / h, h, 0)
            if d not in (zoo, nan):
                res.strategy = "limit-def"
                return d
        except Exception:
            pass
        raise RuntimeError("All derivative strategies failed.")

    def _numcheck(self, f_expr: sp.Expr, deriv: sp.Expr) -> float:
        try:
            a_val = _test_point(f_expr)
            sym_v = float(complex(deriv.subs(x, a_val).evalf()).real)
            f_lam = lambdify(x, f_expr, modules=["numpy"])
            num_v = _num_deriv(f_lam, a_val)
            if math.isfinite(sym_v) and math.isfinite(num_v):
                return abs(sym_v - num_v)
        except Exception:
            pass
        return float("nan")


# ─────────────────────────────────────────────────────────────────────────────
#  LATEX BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

# Fix SymPy's \operatorname{atan} etc → proper arc names
_LATEX_REPLACEMENTS = [
    # inverse hyperbolic (longest first)
    (r"\operatorname{atanh}", r"\arctanh"),
    (r"\operatorname{asinh}", r"\arcsinh"),
    (r"\operatorname{acosh}", r"\arccosh"),
    (r"\operatorname{acoth}", r"\arccoth"),
    (r"\operatorname{asech}", r"\arcsech"),
    (r"\operatorname{acsch}", r"\arccsch"),
    # inverse trig
    (r"\operatorname{atan}", r"\arctan"),
    (r"\operatorname{asin}", r"\arcsin"),
    (r"\operatorname{acos}", r"\arccos"),
    (r"\operatorname{acot}", r"\arccot"),
    (r"\operatorname{asec}", r"\arcsec"),
    (r"\operatorname{acsc}", r"\arccsc"),
    # natural log
    (r"\log", r"\ln"),
]


def _clean_latex(s: str) -> str:
    """Fix SymPy's operatorname wrappers → proper \\arc... names."""
    for old, new in _LATEX_REPLACEMENTS:
        s = s.replace(old, new)
    return s


def _latex_tangent(res: TangentResult) -> str:
    """Return the tangent equation as a standard compilable LaTeX string."""
    if res.status == "ERROR" or res.ft_expr is None:
        return r"\text{ERROR}"
    lhs = r"y - \left(" + latex(res.ft_expr) + r"\right)"
    rhs = latex(res.rhs_expr)
    return _clean_latex(lhs + " = " + rhs)


# ─────────────────────────────────────────────────────────────────────────────
#  SYMPY STRING → HUMAN-READABLE  (atan→arctan etc.)
# ─────────────────────────────────────────────────────────────────────────────

_SYM_REPLACEMENTS = [
    # longer names first so 'atan' doesn't hit before 'atanh'
    ("atanh", "arctanh"),
    ("asinh", "arcsinh"),
    ("acosh", "arccosh"),
    ("atan", "arctan"),
    ("asin", "arcsin"),
    ("acos", "arccos"),
    ("acot", "arccot"),
]


def _pretty(expr) -> str:
    """Convert a SymPy expr to a string with arc-prefixed inverse trig names."""
    s = str(expr)
    for old, new in _SYM_REPLACEMENTS:
        s = s.replace(old, new)
    return s


def _pretty_func(func_str: str) -> str:
    """Same replacement for the raw function string."""
    s = func_str
    for old, new in _SYM_REPLACEMENTS:
        s = s.replace(old, new)
    return s


def _lx(expr: sp.Expr) -> str:
    """Return a clean LaTeX string for a single SymPy expression."""
    return _clean_latex(latex(expr))
