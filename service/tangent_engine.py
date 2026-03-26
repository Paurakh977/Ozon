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
import time, math, textwrap, traceback
from dataclasses import dataclass
from typing import Optional

import sympy as sp
from sympy import (
    symbols, sympify, diff, limit, simplify, expand, factor, latex,
    lambdify, zoo, nan, oo, pi, E,
    floor, ceiling, Abs, Piecewise,
    sin, cos, tan, exp, log, sqrt, asin, acos, atan
)
import numpy as np

from algo import get_sympified_expr

# ── symbols ──────────────────────────────────────────────────────────────────
x = symbols('x', real=True)   # running variable in the tangent line
a = symbols('a', real=True)   # constant tangency point

# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TangentResult:
    func_str:     str
    ft_expr:      Optional[sp.Expr] = None   # f(a)
    fpt_expr:     Optional[sp.Expr] = None   # f'(a)  — the slope
    lhs_expr:     Optional[sp.Expr] = None   # y - f(a)
    rhs_expr:     Optional[sp.Expr] = None   # f'(a) * (x - a)
    deriv_expr:   Optional[sp.Expr] = None   # f'(x) in full
    strategy:     str               = "symbolic"
    status:       str               = "OK"
    error:        str               = ""
    time_s:       float             = 0.0
    num_error:    float             = float('nan')

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse(func_str: str) -> sp.Expr:
    return get_sympified_expr(func_str, local_dict={'x': x, 'a': a})


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
            -f_lam(a_val + 2*h)
            + 8*f_lam(a_val + h)
            - 8*f_lam(a_val - h)
            + f_lam(a_val - 2*h)
        ) / (12*h)
    except Exception:
        return float('nan')


def _test_point(f_expr: sp.Expr) -> float:
    candidates = [1.5, 2.0, 0.5, 3.0, 0.3, 0.7, 4.0, -1.5]
    try:
        f_lam = lambdify(x, f_expr, modules=['numpy', 'sympy'])
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
        t0 = time.perf_counter()
        try:
            self._core(func_str, res)
        except Exception as exc:
            res.status = "ERROR"
            res.error  = f"{type(exc).__name__}: {exc}"
        res.time_s = time.perf_counter() - t0
        return res

    def _core(self, func_str: str, res: TangentResult):
        f_expr = _parse(func_str)

        # ── Derivative ────────────────────────────────────────────────────
        deriv_raw = self._differentiate(f_expr, res)
        deriv     = _simplify(deriv_raw)
        res.deriv_expr = deriv

        # ── Evaluate at tangency point a ──────────────────────────────────
        fa  = _eval_at_a(f_expr, a)   # f(a)
        fpa = _eval_at_a(deriv,  a)   # f'(a)

        res.ft_expr  = fa
        res.fpt_expr = fpa

        # ── Build  y - f(a) = f'(a)·(x - a) ─────────────────────────────
        res.lhs_expr = sp.Symbol('y') - fa          # symbolic LHS for display
        res.rhs_expr = _simplify(fpa * (x - a))     # RHS simplified

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
            h = sp.Symbol('h', positive=True)
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
            f_lam = lambdify(x, f_expr, modules=['numpy'])
            num_v = _num_deriv(f_lam, a_val)
            if math.isfinite(sym_v) and math.isfinite(num_v):
                return abs(sym_v - num_v)
        except Exception:
            pass
        return float('nan')


# ─────────────────────────────────────────────────────────────────────────────
#  ANSI COLORS  (terminal only)
# ─────────────────────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"


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
    (r"\operatorname{atan}",  r"\arctan"),
    (r"\operatorname{asin}",  r"\arcsin"),
    (r"\operatorname{acos}",  r"\arccos"),
    (r"\operatorname{acot}",  r"\arccot"),
    (r"\operatorname{asec}",  r"\arcsec"),
    (r"\operatorname{acsc}",  r"\arccsc"),
    # natural log
    (r"\log",                 r"\ln"),
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


# ─────────────────────────────────────────────────────────────────────────────
#  TERMINAL PRINTER
# ─────────────────────────────────────────────────────────────────────────────

def _sep(char='─', width=110, color=C.GRAY):
    print(color + char * width + C.RESET)


def _lx(expr: sp.Expr) -> str:
    """Return a clean LaTeX string for a single SymPy expression."""
    return _clean_latex(latex(expr))


def _print_terminal_result(res: TangentResult, idx: int):
    ok     = res.status == "OK"
    num_ok = (not math.isnan(res.num_error)) and res.num_error < 1e-5
    tag_col = C.GREEN if (ok and num_ok) else (C.YELLOW if ok else C.RED)
    tag_sym = "✓" if (ok and num_ok) else ("⚠" if ok else "✗")
    num_str = f"{res.num_error:.2e}" if not math.isnan(res.num_error) else "N/A"
    num_col = C.GREEN if num_ok else C.YELLOW

    # LaTeX for f(x) from the raw input string
    try:
        fx_latex = _lx(_parse(res.func_str))
    except Exception:
        fx_latex = res.func_str

    _sep('─')
    print(
        f"{tag_col}{C.BOLD}{tag_sym} [{idx:>3}]{C.RESET}  "
        f"{C.CYAN}$$ f(x) = {fx_latex} $${C.RESET}   "
        f"{C.GRAY}Δ={num_col}{num_str}{C.GRAY}  {res.time_s*1000:.0f}ms{C.RESET}"
    )
    if ok and res.ft_expr is not None:
        print(f"         {C.GRAY}f'(x){C.RESET} = {C.WHITE}$$ {_lx(res.deriv_expr)} $${C.RESET}")
        print(f"         {C.GRAY}f(a) {C.RESET} = {C.MAGENTA}$$ {_lx(res.ft_expr)} $${C.RESET}")
        print(f"         {C.GRAY}f'(a){C.RESET} = {C.MAGENTA}$$ {_lx(res.fpt_expr)} $${C.RESET}")
        print(f"\n  {C.YELLOW}{C.BOLD}TANGENT:{C.RESET}  "
              f"{C.BLUE}$$ {_latex_tangent(res)} $${C.RESET}")
    else:
        print(f"  {C.RED}{res.error[:100]}{C.RESET}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  TEST SUITE
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES = {
    "TRICKY LIMITS & ASYMPTOTES": [
        '(x**2 - 1) / (x - 1)',
        '(x**2 - 4) / (x - 2)',
        '(1 + 1/x)**x',
        '(2**x - 1) / x',
        'exp(-1/x**2)',
        'sqrt(x**2 + 1) - x',
        'x**(1/x)',
        'abs(x) / x',
    ],
    "TRICKY DOMAIN RESTRICTIONS & COMPOSITES": [
        'asin(2*x / (1 + x**2))',
        'acos(log(x))',
        'sqrt(x - sqrt(x))',
        'sqrt(1 - sqrt(1 - x**2))',
        'log((1 + x) / (1 - x))',
        'sqrt(log(x))',
        'log(x**2 - 4)',
        'log(x**2 - 3*x + 2)',
        '1 / sqrt(1 - x**2)',
    ],
    "TRIG TRAPS & PERIODICITY": [
        'sin(acos(x))',
        'cos(2*asin(x))',
        'asin(1/x)',
        'log(sin(x))',
        'atan(x) - x',
    ],
    "CLASSIC CURVE SKETCHING & OPTIMIZATION": [
        'x * exp(-x)',
        'x * log(x)',
        '(x - 1) / sqrt(x**2 + 1)',
        'x - log(1 + x)',
        'log(1 + exp(x))',
        'x**2 * exp(-x)',
    ],
    "ASSORTED STANDARD TESTS": [
        'sqrt(x**2 - 4)',
        'sqrt(4 - x**2)',
        'sqrt(x/(x-1))',
        'log(x)',
        'log(x-1)',
        'log(x**2 - 1)',
        'exp(-x**2)',
        'exp(x)/(1+exp(x))',
        'sin(x)/x',
        'x*sin(x)',
        'sin(x**2)',
        'atan(x)',
        'tan(x)/(1+x**2)',
        '(x**2+1)/(x**2-1)',
        '1/(x**2+sin(x))',
    ],
    "NESTED RADICALS & COMPOSITES": [
        'sqrt(x * (1 - x))',
        'sqrt(x * log(x))',
        'sqrt(-log(x))',
        'asin(sqrt(x))',
        'x**(1 - x)',
        'asin(sqrt(1 - x**2))',
        'x + 1/x',
        'abs(x) + 1/abs(x)',
        'x**x',
        '-x * log(x)',
    ],
    "RATIONAL FUNCTION TRAPS": [
        '1 / (x**2 - 2*x + 2)',
        '(x**2 + x + 1) / (x**2 - x + 1)',
        'x**2 / (x**2 - 4)',
        '(2*x + 1) / (x**2 + x + 1)',
        '(x**3 - x) / (x**2 - 1)',
        '(x**2 + x) / (x**2 - x)',
        'x**3 - 3*x',
        'sin(x) / (x**2 + 1)',
    ],
    "INVERSE TRIG NIGHTMARES": [
        'acos(x**2)',
        'atan(2*x / (1 - x**2))',
        'asin(2 * x**2 - 1) / 2',
        'acos(cos(x))',
        'asin(sin(x))',
        'atan(1/x)',
        'atan(x / (1 + x**2))',
        'log((1 + x) / (1 - x)) / 2',
    ],
    "EXPONENTIAL & LOG EDGE CASES": [
        '(exp(x) + exp(-x)) / 2',
        '(exp(x) - exp(-x)) / (exp(x) + exp(-x))',
        'x**(log(x))',
        'log(x) / x',
        'exp(x) + exp(-2*x)',
        'exp(x) + exp(-x)',
        'log(log(x))',
        'exp(x) - x - 1',
        '-log(x) - log(1 - x)',
    ],
    "IMPLICIT DOMAIN TRAPS": [
        'sqrt(x + 1/x)',
        'cos(x)**2',
        'asin(x) * acos(x)',
        '(exp(x) + 1)**2 / exp(x)',
        '1 / (sin(x) * cos(x))',
        '(1 - cos(x)) / x**2',
        'log(x**2 + 2*x - 3)',
        'log(1 + sqrt((x - 1) / (x + 1)))',
    ],
    "PARAMETRIC / COMBINED TRAPS": [
        'sin(x + pi/4)',
        'x**3 + sin(x)',
        'x / (x**4 + 1)',
        'log(x)**2',
        '((exp(x) + exp(-x)) / 2)**2',
        'sqrt(sin(x) + 2)',
        'abs(x**2 - 1)',
        'x**2 / abs(x**2 - 1)',
        'acos(sin(x))',
        'x**(-x)',
    ],
    "COMPETITION-LEVEL": [
        'atan(x) + atan(2*x) + atan(3*x)',
        'sin(x)**4 + cos(x)**4',
        'sin(x)**6 + cos(x)**6',
        'sin(x)**2 + sin(x + pi/3)**2 + sin(x + 2*pi/3)**2',
        'sin(x) / abs(x)',
        'log(abs(x**2 - 1))',
        '(sin(x) - x * cos(x))**2',
        'x**(1 / (1 + log(x)))',
        'log(1 + x) - x + x**2/2',
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
#  LaTeX FILE WRITER
# ─────────────────────────────────────────────────────────────────────────────

# Category accent colours (RGB) — one per category, cycling if needed
_CAT_COLORS = [
    ("catA", "0,100,200"),
    ("catB", "180,0,80"),
    ("catC", "0,150,80"),
    ("catD", "160,80,0"),
    ("catE", "80,0,160"),
    ("catF", "0,140,140"),
    ("catG", "200,60,0"),
    ("catH", "60,120,0"),
    ("catI", "120,0,120"),
    ("catJ", "0,80,160"),
    ("catK", "160,40,40"),
    ("catL", "40,120,80"),
]


def _write_latex_file(all_results: list, path: str = "tangent_equations.tex"):
    """
    Write a clean, compilable .tex file.

    Layout per function
    ───────────────────
    ▸ f(x) = ...     f'(x) = ...
    $$
      y - \\Bigl(f(a)\\Bigr) = f'(a)\\,(x - a)
    $$
    """
    L = []   # lines accumulator

    # ── Preamble ─────────────────────────────────────────────────────────────
    L += [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage{amsmath, amssymb, geometry, xcolor, titlesec, enumitem, microtype}",
        r"\geometry{top=2cm, bottom=2cm, left=2.2cm, right=2.2cm}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{2pt}",
        r"",
        r"% ── category colours ───────────────────────────────────────────",
    ]
    for name, rgb in _CAT_COLORS:
        L.append(rf"\definecolor{{{name}}}{{RGB}}{{{rgb}}}")

    L += [
        r"",
        r"% ── section style ───────────────────────────────────────────────",
        r"\newcommand{\catsec}[2]{%",
        r"  \vspace{1em}",
        r"  \noindent\colorbox{#1!15}{\parbox{\dimexpr\linewidth-2\fboxsep}{%",
        r"    \bfseries\color{#1}\large #2}}",
        r"  \vspace{0.3em}",
        r"}",
        r"",
        r"\begin{document}",
        r"",
        r"% ── Title ───────────────────────────────────────────────────────",
        r"\begin{center}",
        r"  {\LARGE\bfseries Tangent Line Equations}\\[8pt]",
        r"  \large\textbf{Form:}\quad",
        r"  $y \;-\; f(a) \;=\; f'(a)\,(x - a)$\\[4pt]",
        r"  {\small $a$ = constant tangency point \quad $x$ = running variable}",
        r"\end{center}",
        r"\medskip",
        r"\noindent\rule{\linewidth}{0.6pt}",
        r"\bigskip",
        r"",
    ]

    # ── Per-category blocks ───────────────────────────────────────────────────
    res_idx = 0
    for cat_idx, (cat, funcs) in enumerate(CATEGORIES.items()):
        cat_results = all_results[res_idx : res_idx + len(funcs)]
        res_idx += len(funcs)

        col_name = _CAT_COLORS[cat_idx % len(_CAT_COLORS)][0]
        safe_cat = cat.replace("&", r"\&")

        L.append(rf"\catsec{{{col_name}}}{{{safe_cat}}}")
        L.append(r"")
        L.append(r"\begin{enumerate}[leftmargin=*, label=\textbf{\arabic*.}, itemsep=10pt]")
        L.append(r"")

        for r in cat_results:
            # ── Parse LaTeX strings ──────────────────────────────────────
            try:
                fx_tex = latex(_parse(r.func_str))
            except Exception:
                fx_tex = r"\text{" + r.func_str + "}"

            fp_tex  = latex(r.deriv_expr) if r.deriv_expr is not None else r"\text{N/A}"

            L.append(r"  \item")

            # ── function + derivative line ───────────────────────────────
            L.append(
                rf"  {{\color{{{col_name}}}$f(x) = {fx_tex}$}}"
                rf"\hfill"
                rf"$f'(x) = {fp_tex}$"
            )
            L.append(r"  \par\smallskip")

            # ── tangent equation in display math ─────────────────────────
            if r.status == "OK" and r.ft_expr is not None:
                lhs_tex = r"y - \Bigl(" + latex(r.ft_expr) + r"\Bigr)"
                rhs_tex = latex(r.rhs_expr)
                tang_tex = lhs_tex + r" \;=\; " + rhs_tex

                L.append(r"  \[")
                L.append(rf"    \color{{{col_name}}} {tang_tex}")
                L.append(r"  \]")

                # small verification note
                if not math.isnan(r.num_error):
                    chk = r"\checkmark" if r.num_error < 1e-5 else r"\boldsymbol{\times}\;\text{MISMATCH}"
                    L.append(
                        rf"  {{\footnotesize\color{{gray}}"
                        rf"$|\text{{sym}}-\text{{num}}| = {r.num_error:.2e}\;{chk}$}}"
                    )
            else:
                safe_err = r.error[:100].replace("\\", "").replace("_", r"\_").replace("#", r"\#")
                L.append(rf"  \textcolor{{red}}{{\textbf{{ERROR:}} {safe_err}}}")

            L.append(r"")

        L.append(r"\end{enumerate}")
        L.append(r"")

    L.append(r"\end{document}")

    return


# ─────────────────────────────────────────────────────────────────────────────
#  RUNNER
# ─────────────────────────────────────────────────────────────────────────────

class TestReporter:

    PASS_THRESH = 1e-5

    def __init__(self):
        self.engine = TangentEngine()

    def run_all(self, latex_out: str = "tangent_equations.tex"):
        engine    = self.engine
        grand_t0  = time.perf_counter()
        total_ok = total_err = total_warn = 0
        all_results: list[TangentResult] = []
        idx = 0

        for cat, funcs in CATEGORIES.items():
            _sep('═', 110, C.BLUE)
            print(f"{C.BLUE}{C.BOLD}  ◆  {cat}  ({len(funcs)} functions){C.RESET}")
            _sep('═', 110, C.BLUE)
            print()

            for fs in funcs:
                idx += 1
                r = engine.compute(fs)
                all_results.append(r)

                num_ok = (not math.isnan(r.num_error)) and r.num_error < self.PASS_THRESH
                if r.status == "ERROR":
                    total_err += 1
                elif not num_ok and not math.isnan(r.num_error):
                    total_warn += 1
                else:
                    total_ok += 1

                _print_terminal_result(r, idx)

        elapsed = time.perf_counter() - grand_t0
        n = len(all_results)
        _sep('═', 110, C.CYAN)
        print(
            f"{C.CYAN}{C.BOLD}  SUMMARY:{C.RESET}  {n} functions  |  "
            f"{C.GREEN}✓ OK: {total_ok}{C.RESET}   "
            f"{C.YELLOW}⚠ WARN: {total_warn}{C.RESET}   "
            f"{C.RED}✗ ERR: {total_err}{C.RESET}   |  "
            f"total {elapsed:.1f}s   avg {elapsed/n*1000:.0f}ms/func"
        )
        _sep('═', 110, C.CYAN)

        return all_results


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os, shutil
    here     = os.path.dirname(os.path.abspath(__file__))
    tex_here = os.path.join(here, "tangent_equations.tex")

    reporter = TestReporter()
    reporter.run_all(latex_out=tex_here)