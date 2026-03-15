import multiprocessing
import sys
import os

# ============================================================
# COMBINED DOMAIN & RANGE TEST SUITE
# Merges: UNIFIED DOMAIN & RANGE TEST SUITE (43 functions)
#       + HARD & TRICKY DOMAIN & RANGE TEST SUITE v2 (73 functions)
# Total: 116 functions
# ============================================================

CATEGORIES = {

    # ----------------------------------------------------------
    # FROM SUITE 1
    # ----------------------------------------------------------

    "TRICKY LIMITS & ASYMPTOTES": [
        # Classic removable discontinuity — hole at x=1, range misses y=2
        '(x**2 - 1) / (x - 1)',
        # Removable hole at x=2 — range misses y=4
        '(x**2 - 4) / (x - 2)',
        # Limit definition of e — Domain: (-oo,-1)U(0,oo), Range: (1,e)U(e,oo)
        '(1 + 1/x)**x',
        # L'Hopital limit — range misses y=ln(2)
        '(2**x - 1) / x',
        # Essential singularity — Domain: x!=0, Range: (0,1)
        'exp(-1/x**2)',
        # Asymptotic to 0 — Domain: R, Range: (0,oo)
        'sqrt(x**2 + 1) - x',
        # Max at x=e — Domain: (0,oo), Range: (0, e^(1/e)]
        'x**(1/x)',
        # Signum — Domain: x!=0, Range: {-1, 1}
        'abs(x) / x',
    ],

    "TRICKY DOMAIN RESTRICTIONS & COMPOSITES": [
        # |2x/(1+x^2)| always <=1 — Domain: R, Range: [-pi/2, pi/2]
        'asin(2*x / (1 + x**2))',
        # Domain: [1/e, e], Range: [0, pi]
        'acos(log(x))',
        # Domain: {0}U[1,oo), Range: [0,oo)
        'sqrt(x - sqrt(x))',
        # Heavily nested — Domain: [-1,1], Range: [0,1]
        'sqrt(1 - sqrt(1 - x**2))',
        # Logit — Domain: (-1,1), Range: (-oo,oo)
        'log((1 + x) / (1 - x))',
        # Domain: [1,oo), Range: [0,oo)
        'sqrt(log(x))',
        # Split domain — Domain: (-oo,-2)U(2,oo), Range: (-oo,oo)
        'log(x**2 - 4)',
        # Domain: (-oo,1)U(2,oo), Range: (-oo,oo)
        'log(x**2 - 3*x + 2)',
        # Domain: (-1,1), Range: [1,oo)
        '1 / sqrt(1 - x**2)',
    ],

    "TRIG TRAPS & PERIODICITY": [
        # = sqrt(1-x^2) — Domain: [-1,1], Range: [0,1]
        'sin(acos(x))',
        # = 1-2x^2 — Domain: [-1,1], Range: [-1,1]
        'cos(2*asin(x))',
        # Domain: |x|>=1, Range: [-pi/2,0)U(0,pi/2]
        'asin(1/x)',
        # Periodic open domain, Range: (-oo,0]
        'log(sin(x))',
        # Domain: R, Range: (-oo,oo)
        'atan(x) - x',
    ],

    "CLASSIC CURVE SKETCHING & OPTIMIZATION": [
        # Max at x=1, Range: (-oo, 1/e]
        'x * exp(-x)',
        # Min at x=1/e, Range: [-1/e, oo)
        'x * log(x)',
        # Domain: R, Range: [-sqrt(2), 1)
        '(x - 1) / sqrt(x**2 + 1)',
        # Domain: (-1,oo), Range: [0,oo)
        'x - log(1 + x)',
        # Softplus — Range: (0,oo)
        'log(1 + exp(x))',
        # Local max at x=2, Range: [0,oo)
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

    # ----------------------------------------------------------
    # FROM SUITE 2
    # ----------------------------------------------------------

    "NESTED RADICALS & COMPOSITES": [
        # Domain: [0,1], Range: [0,1/2]
        'sqrt(x * (1 - x))',
        # Domain: [1,oo), Range: [0,oo)
        'sqrt(x * log(x))',
        # Domain: (0,1], Range: [0,oo)
        'sqrt(-log(x))',
        # Domain: [0,1], Range: [0,pi/2]
        'asin(sqrt(x))',
        # Domain: (0,oo), Range: (0,1]  ← solver bug: reported (0,oo)
        'x**(1 - x)',
        # Domain: [-1,1], Range: [0,pi/2]
        'asin(sqrt(1 - x**2))',
        # Domain: (-oo,0)U(0,oo), Range: (-oo,-2]U[2,oo)
        'x + 1/x',
        # Domain: x!=0, Range: [2,oo)
        'abs(x) + 1/abs(x)',
        # Domain: [0,oo), Range: [e^(-1/e), oo)
        'x**x',
        # Domain: (0,oo), Range: (-oo, 1/e]
        '-x * log(x)',
    ],

    "RATIONAL FUNCTION TRAPS": [
        # Domain: R, Range: (0,1]  — 1/((x-1)^2+1)
        '1 / (x**2 - 2*x + 2)',
        # Domain: R, Range: [1/3, 3]
        '(x**2 + x + 1) / (x**2 - x + 1)',
        # Domain: x!=±2, Range: (-oo,0]U(1,oo)
        'x**2 / (x**2 - 4)',
        # Domain: R, Range: [-2sqrt(3)/3, 2sqrt(3)/3]
        '(2*x + 1) / (x**2 + x + 1)',
        # Simplifies to x — Domain: x!=±1, Range: R\{-1,1}
        '(x**3 - x) / (x**2 - 1)',
        # Simplifies to (x+1)/(x-1) — Domain: x!=0,1, Range: R\{-1,1}
        '(x**2 + x) / (x**2 - x)',
        # Cubic — Domain: R, Range: R
        'x**3 - 3*x',
        # Domain: R, Range: [-0.4374, 0.4374]
        'sin(x) / (x**2 + 1)',
    ],

    "INVERSE TRIG NIGHTMARES": [
        # Domain: [-1,1], Range: [0,pi/2]
        'acos(x**2)',
        # Domain: x!=±1, Range: (-pi/2,pi/2)
        'atan(2*x / (1 - x**2))',
        # Domain: [-1,1], Range: [-pi/4,pi/4]
        'asin(2 * x**2 - 1) / 2',
        # Triangle wave — Domain: R, Range: [0,pi]
        'acos(cos(x))',
        # Triangle wave — Domain: R, Range: [-pi/2,pi/2]
        'asin(sin(x))',
        # Domain: x!=0, Range: (-pi/2,0)U(0,pi/2)
        'atan(1/x)',
        # Domain: R, Range: [-atan(1/2), atan(1/2)]
        'atan(x / (1 + x**2))',
        # atanh — Domain: (-1,1), Range: R
        'log((1 + x) / (1 - x)) / 2',
    ],

    "EXPONENTIAL & LOG EDGE CASES": [
        # cosh — Domain: R, Range: [1,oo)
        '(exp(x) + exp(-x)) / 2',
        # tanh — Domain: R, Range: (-1,1)
        '(exp(x) - exp(-x)) / (exp(x) + exp(-x))',
        # x^(ln x) = e^((ln x)^2) — Domain: (0,oo), Range: [1,oo)
        'x**(log(x))',
        # Domain: (0,oo), Range: (-oo, 1/e]
        'log(x) / x',
        # Min = 3·2^(1/3)/2 — Domain: R, Range: [3·2^(1/3)/2, oo)
        'exp(x) + exp(-2*x)',
        # 2cosh — Domain: R, Range: [2,oo)
        'exp(x) + exp(-x)',
        # Domain: (1,oo), Range: R
        'log(log(x))',
        # Taylor remainder — Domain: R, Range: [0,oo)
        'exp(x) - x - 1',
        # -log(x(1-x)) — Domain: (0,1), Range: [2log2,oo)
        '-log(x) - log(1 - x)',
    ],

    "FLOOR / CEILING / FRACTIONAL PART TRAPS": [
        # Domain: R, Range: {0,1}  ← solver bug: reported {1} only
        'ceiling(x) - floor(x)',
        # Domain: R, Range: {-1,0}  ← solver bug: reported {-1} only
        'floor(x) + floor(-x)',
        # Domain: R, Range: [0,1)
        '(x - floor(x))**2',
        # Domain: R, Range: [0,0.25]
        '(x - floor(x)) * (1 - (x - floor(x)))',
        # Hermite identity = floor(2x) — Domain: R, Range: Z
        'floor(x) + floor(x + 0.5)',
        # sin+cos in [-sqrt(2),sqrt(2)] — Domain: R, Range: {-2,-1,0,1}
        'floor(sin(x) + cos(x))',
        # Domain: R, Range: {0,1}  ← solver bug: reported {0} only
        'floor(abs(sin(x)))',
        # Domain: R, Range: {0,1,4,9,...}
        'floor(x)**2',
    ],

    "IMPLICIT DOMAIN TRAPS": [
        # Domain: (0,oo), Range: [sqrt(2),oo)
        'sqrt(x + 1/x)',
        # Domain: R, Range: [0,1]
        'cos(x)**2',
        # Domain: [-1,1], Range: [-pi^2/2, pi^2/16]  ← solver bug: reported (-4.935,oo)
        'asin(x) * acos(x)',
        # = 2cosh+2 — Domain: R, Range: [4,oo)
        '(exp(x) + 1)**2 / exp(x)',
        # = 2/sin(2x) — Domain: x!=npi/2, Range: (-oo,-2]U[2,oo)
        '1 / (sin(x) * cos(x))',
        # Always >=0, lim->0 is 1/2 — Domain: x!=0, Range: (0, 1/2)
        '(1 - cos(x)) / x**2',
        # Domain: (-oo,-3)U(1,oo), Range: R
        'log(x**2 + 2*x - 3)',
        # Hole at ln2 — Domain: (-oo,-1)U[1,oo), Range: [0,ln2)U(ln2,oo)
        'log(1 + sqrt((x - 1) / (x + 1)))',
    ],

    "PARAMETRIC / COMBINED TRAPS": [
        # Domain: R, Range: [-1,1]
        'sin(x + pi/4)',
        # Strictly increasing — Domain: R, Range: R
        'x**3 + sin(x)',
        # Domain: R, Range: [-3^(3/4)/4, 3^(3/4)/4]
        'x / (x**4 + 1)',
        # Domain: (0,oo), Range: [0,oo)
        'log(x)**2',
        # cosh^2 — Domain: R, Range: [1,oo)
        '((exp(x) + exp(-x)) / 2)**2',
        # sin+2 in [1,3] — Domain: R, Range: [1,sqrt(3)]
        'sqrt(sin(x) + 2)',
        # Domain: R, Range: [0,oo)
        'abs(x**2 - 1)',
        # Domain: x!=±1, Range: [0,oo)
        'x**2 / abs(x**2 - 1)',
        # Domain: R, Range: [0,pi]
        'acos(sin(x))',
        # Max e^(1/e) at x=1/e — Domain: (0,oo), Range: (0, e^(1/e)]
        'x**(-x)',
    ],

    "COMPETITION-LEVEL": [
        # Strictly increasing sum — Domain: R, Range: (-3pi/2, 3pi/2)
        'atan(x) + atan(2*x) + atan(3*x)',
        # = 1 - (1/2)sin^2(2x) — Domain: R, Range: [1/2, 1]
        'sin(x)**4 + cos(x)**4',
        # = 1 - (3/4)sin^2(2x) — Domain: R, Range: [1/4, 1]
        'sin(x)**6 + cos(x)**6',
        # CONSTANT FUNCTION = 3/2 — Domain: R, Range: {3/2}
        'sin(x)**2 + sin(x + pi/3)**2 + sin(x + 2*pi/3)**2',
        # Odd sinc-like — Domain: x!=0, Range: (-1,1)  ← solver bug: reported [-1,1]
        'sin(x) / abs(x)',
        # Domain: x!=±1, Range: R
        'log(abs(x**2 - 1))',
        # Perfect square — Domain: R, Range: [0,oo)  ← solver bug: reported (-oo,oo)
        '(sin(x) - x * cos(x))**2',
        # Interior hole at e — Domain: (0,1/e)U(1/e,oo), Range: (0,e)U(e,oo)
        'x**(1 / (1 + log(x)))',
        # Domain: R, Range: {0,1}  ← solver bug: reported {0} only
        'floor(cos(pi * x)**2)',
        # Taylor remainder order 2 — Domain: (-1,oo), Range: [0,oo)  ← solver bug: reported R
        'log(1 + x) - x + x**2/2',
        # Domain: (0,oo), Range: (0,oo)
      
    ],
}


def run():
    from algo import solve

    total = sum(len(v) for v in CATEGORIES.values())
    print("=" * 60)
    print(f"   COMBINED DOMAIN & RANGE TEST SUITE  ({total} functions)")
    print("=" * 60)

    test_num = 1
    for cat_idx, (cat_name, funcs) in enumerate(CATEGORIES.items(), 1):
        print(f"\n{'='*60}")
        print(f"  CATEGORY {cat_idx}: {cat_name}  ({len(funcs)} functions)")
        print(f"{'='*60}")
        for expr in funcs:
            print(f"\nTest {test_num}: {expr}")
            try:
                solve(expr)
            except Exception as e:
                print(f"[ERROR] {e}")
            test_num += 1

    print("\n" + "=" * 60)
    print(f"Completed {total} functions across {len(CATEGORIES)} categories.")
    print("=" * 60)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    run()