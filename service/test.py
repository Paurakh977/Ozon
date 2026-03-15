import multiprocessing
import sys
import os

TEST_FUNCTIONS =[
    # ==========================================
    # 1. TRICKY LIMITS & ASYMPTOTES
    # ==========================================
    
    # Classic Removable Discontinuity (Hole)
    # Domain: x != 1. Range misses exactly one point: y != 2.
    '(x**2 - 1) / (x - 1)',
    
    # Removable hole at x=2 — range should be ℝ∖{4}
    '(x**2 - 4) / (x - 2)',
    
    # Limit definition of 'e' / split domain
    # Domain: (-oo, -1) U (0, oo). Range: (1, e) U (e, oo)
    '(1 + 1/x)**x',
    
    # L'Hopital's Limit
    # Domain: x != 0. Range misses exactly one point: y != ln(2)
    '(2**x - 1) / x',
    
    # Essential singularity
    # Domain: x != 0. Range: (0, 1) (It never actually reaches 0 or 1)
    'exp(-1/x**2)',
    
    # Asymptotic behavior approaching 0
    # Domain: (-oo, oo). Range: (0, oo). Gets infinitely close to 0 as x -> oo.
    'sqrt(x**2 + 1) - x',
    
    # Extreme points and limit cases
    # Domain: (0, oo). Approaches 1 as x->inf, 0 as x->0+. Max at x=e. Range: (0, e**(1/e)]
    'x**(1/x)',
    
    # Piecewise constant (Signum function)
    # Domain: x != 0. Range is exactly a discrete set: {-1, 1}
    'abs(x) / x',


    # ==========================================
    # 2. TRICKY DOMAIN RESTRICTIONS & COMPOSITES
    # ==========================================
    
    # Hidden All-Reals Domain (|2x/(1+x^2)| is always <= 1). Range: [-pi/2, pi/2]
    'asin(2*x / (1 + x**2))',
    
    # Heavy composite domain restriction
    # Domain:[1/e, e] (ln(x) must be between -1 and 1). Range:[0, pi]
    'acos(log(x))',
    
    # domain: x>=1, range:[0,inf)
    'sqrt(x - sqrt(x))',
    
    # heavily nested, domain [-1,1], range [0,1]
    'sqrt(1 - sqrt(1 - x**2))',
    
    # logit, domain (-1,1), range (-inf,inf)
    'log((1 + x) / (1 - x))',
    
    # implicitly restricted domain[1,inf), range[0,inf)
    'sqrt(log(x))',
    
    # Disconnected/Split Domain Logarithm
    # Domain: (-oo, -2) U (2, oo). Range: (-oo, oo)
    'log(x**2 - 4)',
    
    # domain (-inf,1)∪(2,inf)
    'log(x**2 - 3*x + 2)',
    
    # Strict Open Interval Domain (-1, 1). Range:[1, oo)
    '1 / sqrt(1 - x**2)',
    
    
    # ==========================================
    # 3. TRIG TRAPS & PERIODICITY
    # ==========================================
    
    # = sqrt(1-x²), domain [-1,1], range [0,1]
    'sin(acos(x))',
    
    # = 1-2x², domain [-1,1], range[-1,1]
    'cos(2*asin(x))',
    
    # domain |x|>=1, range [-pi/2,0)∪(0,pi/2]
    'asin(1/x)',
    
    # Infinite Periodic Open Domains
    # Domain: x in (2n*pi, (2n+1)*pi) because sin(x) must be strictly > 0. Range: (-oo, 0]
    'log(sin(x))',
    
    # Inverse trig / Algebraic combo
    # Domain: (-oo, oo). Range: (-pi/2, pi/2)
    'atan(x) - x',


    # ==========================================
    # 4. CLASSIC CURVE SKETCHING & OPTIMIZATION
    # ==========================================
    
    # Classic Optimization Curve. Max at x=1. Range: (-oo, 1/e]
    'x * exp(-x)',
    
    # Global minimum of x*ln(x). Domain: (0, oo). Range:[-1/e, oo)
    'x * log(x)',
    
    # domain (-inf,inf), range (-1,1)
    '(x - 1) / sqrt(x**2 + 1)',
    
    # domain (-1,inf), range[0,inf)
    'x - log(1 + x)',
    
    # softplus, range (0,inf)
    'log(1 + exp(x))',
    
    # goes to inf as x→-inf, local max at x=2
    'x**2 * exp(-x)',


    # ==========================================
    # 5. ASSORTED STANDARD TESTS
    # ==========================================
    
    "sqrt(x**2 - 4)",
    "sqrt(4 - x**2)",
    "sqrt(x/(x-1))",
    "log(x)",
    "log(x-1)",
    "log(x**2 - 1)",
    "exp(-x**2)",
    "exp(x)/(1+exp(x))",
    "sin(x)/x",
    "x*sin(x)",
    "sin(x**2)",
    "atan(x)",
    "tan(x)/(1+x**2)",
    "(x**2+1)/(x**2-1)",
    "1/(x**2+sin(x))"
]


def run():
    from algo import solve

    print("=" * 60)
    print("                 UNIFIED DOMAIN & RANGE TEST SUITE")
    print("=" * 60)

    for i, expr in enumerate(TEST_FUNCTIONS, 1):
        print(f"\n{'-' * 60}")
        print(f"Test {i}: {expr}")
        print(f"{'-' * 60}")
        try:
            solve(expr)
        except Exception as e:
            print(f"[ERROR] Failed to solve {expr}: {e}")

    print("\n" + "=" * 60)
    print(f"Completed {len(TEST_FUNCTIONS)} functions.")
    print("=" * 60)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    run()