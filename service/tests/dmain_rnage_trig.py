import multiprocessing
import sys,os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from engines import solve
# ============================================================
#   TRIGONOMETRIC DOMAIN & RANGE TEST SUITE  (28 functions)
#   Categories: Basic Trig, Inverse Trig, Compositions,
#               Identities & Powers, Reciprocal & Quotient,
#               Competition-Level Trig
# ============================================================

CATEGORIES = {

    # ----------------------------------------------------------
    # CATEGORY 1: BASIC TRIG FUNCTIONS & SHIFTS
    # ----------------------------------------------------------
    "BASIC TRIG FUNCTIONS & SHIFTS": [
        # Domain: R, Range: [-1, 1]
        'sin(x)',
        # Domain: R, Range: [-1, 1]
        'cos(x)',
        # Domain: x != pi/2 + n*pi, Range: (-oo, oo)
        'tan(x)',
        # Domain: x != n*pi, Range: (-oo,-1] U [1,oo)
        'cot(x)',   # = cos(x)/sin(x)
        # Amplitude 3, Range: [-3, 3]
        '3 * sin(x)',
        # Vertical shift — Domain: R, Range: [1, 3]
        'sin(x) + 2',
        # Horizontal shift — Domain: R, Range: [-1, 1]
        'cos(x - pi/3)',
        # Combined: amplitude 2, shift — Domain: R, Range: [-2, 2]
        '2 * sin(x + pi/4)',
    ],

    # ----------------------------------------------------------
    # CATEGORY 2: INVERSE TRIG FUNCTIONS
    # ----------------------------------------------------------
    "INVERSE TRIG FUNCTIONS": [
        # Domain: [-1, 1], Range: [-pi/2, pi/2]
        'asin(x)',
        # Domain: [-1, 1], Range: [0, pi]
        'acos(x)',
        # Domain: R, Range: (-pi/2, pi/2)
        'atan(x)',
        # Domain: R, Range: (0, pi)  — principal value of acot
        'atan(1/x)',         # proxy for acot(x); domain x!=0
        # Domain: |x|>=1, Range: [0,pi/2) U (pi/2, pi]
        'acos(1/x)',         # arcsec(x)
        # Domain: |x|>=1, Range: [-pi/2,0) U (0,pi/2]
        'asin(1/x)',         # arccsc(x)
        # Domain: [-1,1], Range: [0, pi/2]
        'acos(x**2)',
        # Domain: R, Range: (-pi/2, pi/2)
        'atan(x**2)',
    ],

    # ----------------------------------------------------------
    # CATEGORY 3: TRIG COMPOSITIONS & NESTED FUNCTIONS
    # ----------------------------------------------------------
    "TRIG COMPOSITIONS & NESTED": [
        # = sqrt(1-x^2) — Domain: [-1,1], Range: [0,1]
        'sin(acos(x))',
        # = |x|/sqrt(1-x^2) in disguise — Domain: [-1,1], Range: [0,1]
        'cos(asin(x))',
        # = 1-2x^2 — Domain: [-1,1], Range: [-1,1]
        'cos(2*asin(x))',
        # Triangle wave — Domain: R, Range: [0, pi]
        'acos(cos(x))',
        # Sawtooth-like — Domain: R, Range: [-pi/2, pi/2]
        'asin(sin(x))',
        # Domain: R, Range: [0, pi]
        'acos(sin(x))',
        # Domain: [-1,1], Range: [0, pi/2]
        'asin(sqrt(1 - x**2))',
        # Double angle identity inside inverse — Domain: [-1,1], Range: [-pi/4, pi/4]
        'asin(2*x**2 - 1) / 2',
    ],

    # ----------------------------------------------------------
    # CATEGORY 4: TRIG POWERS & IDENTITIES
    # ----------------------------------------------------------
    "TRIG POWERS & IDENTITIES": [
        # Domain: R, Range: [0, 1]
        'sin(x)**2',
        # Domain: R, Range: [0, 1]
        'cos(x)**2',
        # = 1 - (1/2)sin^2(2x) — Domain: R, Range: [1/2, 1]
        'sin(x)**4 + cos(x)**4',
        # = 1 - (3/4)sin^2(2x) — Domain: R, Range: [1/4, 1]
        'sin(x)**6 + cos(x)**6',
        # CONSTANT = 3/2 — Domain: R, Range: {3/2}
        'sin(x)**2 + sin(x + pi/3)**2 + sin(x + 2*pi/3)**2',
        # sin+cos in [-sqrt(2), sqrt(2)] — Range: [-sqrt(2), sqrt(2)]
        'sin(x) + cos(x)',
        # Domain: R, Range: [-1, 1]  (Chebyshev-style)
        'sin(x) * cos(x)',   # = sin(2x)/2
        # Domain: R, Range: [1, sqrt(2)]
        'sqrt(sin(x)**2 + cos(x)**2 + sin(x)*cos(x) + 1)',  # tricky
    ],

    # ----------------------------------------------------------
    # CATEGORY 5: RECIPROCAL & QUOTIENT TRIG
    # ----------------------------------------------------------
    "RECIPROCAL & QUOTIENT TRIG": [
        # Domain: R \ {npi}, Range: (-oo,-1] U [1,oo)
        '1 / sin(x)',              # csc(x)
        # Domain: R \ {pi/2+npi}, Range: (-oo,-1] U [1,oo)
        '1 / cos(x)',              # sec(x)
        # Domain: x!=0, Range: (-1, 1)  — sinc-like odd function
        'sin(x) / abs(x)',
        # Domain: x!=0, Range: approx [-0.2172, 1)
        'sin(x) / x',
        # Domain: x!=0, Range: (0, 1/2]  — always positive, limit 1/2
        '(1 - cos(x)) / x**2',
        # Domain: R \ multiples of pi/2, Range: (-oo,-2] U [2,oo)
        '1 / (sin(x) * cos(x))',   # = 2/sin(2x)
        # Domain: R, Range: approx [-0.4374, 0.4374]
        'sin(x) / (x**2 + 1)',
        # Domain: R \ {pi/2+npi}, Range: approx (-oo, oo)
        'tan(x) / (1 + x**2)',
    ],
}


def run():


    total = sum(len(v) for v in CATEGORIES.values())
    print("=" * 60)
    print(f"   TRIGONOMETRIC DOMAIN & RANGE TEST SUITE  ({total} functions)")
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