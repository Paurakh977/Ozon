import time,os,sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from engines import analyze_power_series


if __name__ == "__main__":
    import pprint

    # String-based test suite - no need for symbol definitions!
    test_series = [
        "x^n / n",  # Harmonic endpoints
        "(x-2)^n / (n * 3^n)",  # Shifted center
        "factorial(n) * x^n",  # Zero radius
        "x^n / factorial(n)",  # Infinite radius
        "(-1)^n * (x+1)^n / n^2",  # Both endpoints closed
        "n^n / factorial(n) * x^n",  # R = 1/e
        "factorial(2*n) / factorial(n)^2 * (x-3)^n",  # R = 1/4
        "(1 + 1/n)^(n^2) * x^n",  # Exponential limit
        "log(n) / n^2 * x^n",  # Logarithmic
        "(3x - 2)^n / (n * 5^n)",  # Linear shift
        "(x+2)^(2*n) / (9^n * n)",  # Power 2n
        "(-1)^n * (x-1)^n / (sqrt(n) * 2^n)",  # Alternating with sqrt
        "(2x - 1)^n / n^3",  # Multiplier on x
        "factorial(n) / n^n * (x-5)^n",  # R = e
        "((n^2 + 1) / (n^2 - 1))^(n^2) * (x+1)^n",  # Complex power
        "log(n) / sqrt(n) * (x - pi)^n",  # Log/sqrt at pi
        "factorial(3*n) / factorial(n)^3 * x^n",  # R = 1/27
        "sin(1/n) * x^n",  # Harmonic equivalent
        "(x + E)^n / (n * log(n)^2)",  # Log series
        "n^(1/n) * x^n",  # Root limit 1
        "x^n / n^2",  # P-series p=2
        "n^2 * x^n",  # Polynomial growth
        "x^n / sqrt(n)",  # P-series p=1/2
        "(-1)^n * x^n / n",  # Alternating harmonic
        "(x - 3)^n / (n * 4^n)",  # Shifted geometric
        "(x + 5)^n / n^3",  # P-series p=3
        "(2x - 1)^n / n^2",  # Linear transform
        "(3x + 2)^n / (n * 2^n)",  # Linear shift
        "(x - pi)^n / (n * E^n)",  # At pi, period e
        "n^n / factorial(n) * x^n",  # Stirling
        "factorial(n) / n^n * x^n",  # Inverse Stirling
        "factorial(4*n) / factorial(n)^4 * x^n",  # 4-factorial
        "binomial(2*n, n) * x^n",  # Central binomial
        "(1 + 1/n)^n * x^n",  # Converges to e
        "(1 + 2/n)^n * x^n",  # Converges to e^2
        "(n / (n+1))^(n^2) * x^n",  # Complex limit
        "x^n / (n * log(n+1))",  # Log denominator
        "x^n / (n * log(n+1)^2)",  # Log squared
        "log(n) / n * x^n",  # Log/n
        "log(n) / n^2 * x^n",  # Log/n^2
        "log(n)^2 / n * x^n",  # Log squared/n
        "sin(1/n) * x^n",  # Sine
        "sin(n) * x^n / n",  # Oscillating
        "cos(1/n) * x^n",  # Cosine
        "tan(1/n) * x^n",  # Tangent
        "factorial(2*n) / (factorial(n)^2 * 4^n) * x^n",  # Catalan-adjacent
        "factorial(n) / (n^n * sqrt(n)) * x^n",  # Stirling with sqrt
        "factorial(n)^2 / factorial(2*n) * x^n",  # Inverse binomial
        "((n^2 + 1) / (n^2 - 1)) * x^n",  # Rational coefficient
        "((n^2 + 1) / (n^2 - 1))^(n^2) * x^n",  # Rational to power
        "(1 + 1/n^2)^(n^3) * x^n",  # Triple power
    ]

    # test_series = [
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 1 — STANDARD (Warm-up, but with traps)
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 1. x^n / n (classic)
    #     # R=1, I=[-1, 1)  — left: AST converges, right: harmonic diverges
    #     "x^n / n",
    #     # 2. x^n / n^2
    #     # R=1, I=[-1, 1]  — both endpoints abs. convergent (p-series p=2>1)
    #     "x^n / n^2",
    #     # 3. n^2 * x^n
    #     # R=1, I=(-1, 1)  — both endpoints: n^2*(±1)^n → ∞, diverge
    #     "n^2 * x^n",
    #     # 4. x^n / sqrt(n)
    #     # R=1, I=[-1, 1)  — left: AST (1/√n→0 monotone), right: p=1/2<1 diverges
    #     "x^n / sqrt(n)",
    #     # 5. (-1)^n * x^n / n
    #     # R=1, I=(-1, 1]  — NOTE: (-1)^n flips AST behavior!
    #     # right x=1: (-1)^n/n → AST converges. left x=-1: (-1)^(2n)/n = 1/n → diverges
    #     "(-1)^n * x^n / n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 2 — SHIFTED CENTERS & COEFFICIENT TRANSFORMATIONS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 6. (x-3)^n / (n * 4^n)
    #     # R=4, center=3, I=[-1, 7)  — left: AST, right: harmonic diverges
    #     "(x - 3)^n / (n * 4^n)",
    #     # 7. (x+5)^n / n^3
    #     # R=1, center=-5, I=[-6, -4]  — both abs. convergent (p=3>1)
    #     "(x + 5)^n / n^3",
    #     # 8. (2x - 1)^n / n^2
    #     # Linear transform: center=1/2, R_x=1/2, I=[0, 1]
    #     # Both endpoints abs. convergent
    #     "(2x - 1)^n / n^2",
    #     # 9. (3x + 2)^n / (n * 2^n)
    #     # Linear: center=-2/3, R_x=2/3, I=[-4/3, 0)
    #     # left: AST converges, right: harmonic diverges
    #     "(3x + 2)^n / (n * 2^n)",
    #     # 10. (x - pi)^n / (n * E^n)
    #     # R=e, center=π, I=[π-e, π+e)
    #     # left: AST converges, right: harmonic diverges
    #     "(x - pi)^n / (n * E^n)",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 3 — FACTORIAL & STIRLING-HEAVY (Engine killers)
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 11. n^n / n! * x^n
    #     # Stirling: n^n/n! ~ e^n/√(2πn). R=1/e.
    #     # left x=-1/e: (-1)^n * C/√n → 0, AST → CONVERGES. I=[-1/e, 1/e)
    #     "n^n / factorial(n) * x^n",
    #     # 12. n! / n^n * x^n
    #     # Stirling inverse: n!/n^n ~ √(2πn)/e^n. R=e.
    #     # Both endpoints: terms → 0 but oscillate — endpoint behavior open: I=(5-e, e+5)... here centered at 0
    #     # I=(-e, e) — both open (terms ~ √n * (±1)^n doesn't → 0 cleanly at rate needed)
    #     # Actually |a_n|^(1/n) = (n!/n^n)^(1/n) → 1/e, R=e. Endpoints: |a_n * R^n| ~ √(2πn) → ∞, DIVERGE
    #     "factorial(n) / n^n * x^n",
    #     # 13. (2n)! / (n!)^2 * x^n  — central binomial coefficients
    #     # Stirling: (2n)!/(n!)^2 ~ 4^n/√(πn). R=1/4.
    #     # left x=-1/4: (-1)^n/√(πn) → AST → CONVERGES. I=[-1/4, 1/4)
    #     "factorial(2*n) / factorial(n)^2 * x^n",
    #     # 14. (3n)! / (n!)^3 * x^n
    #     # Stirling: (3n)!/(n!)^3 ~ 27^n * C/√n. R=1/27.
    #     # left: AST → CONVERGES. I=[-1/27, 1/27)
    #     "factorial(3*n) / factorial(n)^3 * x^n",
    #     # 15. (4n)! / (n!)^4 * x^n
    #     # Stirling: (4n)!/(n!)^4 ~ 256^n * C/n. R=1/256.
    #     # left: AST ~ C/√n → 0 → CONVERGES. I=[-1/256, 1/256)
    #     "factorial(4*n) / factorial(n)^4 * x^n",
    #     # 16. binomial(2*n, n) * x^n  (same as #13 but via binomial)
    #     # Should match: R=1/4, I=[-1/4, 1/4)
    #     "binomial(2*n, n) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 4 — EXPONENTIAL/LIMIT COEFFICIENT TESTS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 17. (1 + 1/n)^n * x^n
    #     # Coefficients → e as n→∞. Root test: L = e*|x|. R=1/e.
    #     # Both endpoints: |(1+1/n)^n * (±1/e)^n| → 1 ≠ 0 → DIVERGE. I=(-1/e, 1/e)
    #     "(1 + 1/n)^n * x^n",
    #     # 18. (1 + 1/n)^(n^2) * x^n
    #     # ln(a_n) = n^2 * ln(1+1/n) ≈ n - 1/2. So a_n ~ e^n / √e.
    #     # R=1/e. Both endpoints diverge (terms → 1/√e ≠ 0). I=(-1/e, 1/e)
    #     "(1 + 1/n)^(n^2) * x^n",
    #     # 19. (1 + 2/n)^n * x^n
    #     # Coefficients → e^2. R=e^(-2).
    #     # Both endpoints diverge. I=(-1/e^2, 1/e^2)
    #     "(1 + 2/n)^n * x^n",
    #     # 20. (n/(n+1))^(n^2) * x^n
    #     # ln(a_n) = n^2 * ln(n/(n+1)) = n^2 * ln(1 - 1/(n+1)) ≈ -n + 1/2
    #     # a_n ~ e^(-n) * √e. R=e. Both endpoints: terms → √e ≠ 0 → DIVERGE. I=(-e, e)
    #     "(n / (n+1))^(n^2) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 5 — LOGARITHMIC & SLOW-DECAY COEFFICIENTS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 21. x^n / (n * log(n+1))
    #     # R=1. Right x=1: ∑1/(n·ln(n)) diverges (integral test).
    #     # Left x=-1: AST → CONVERGES. I=[-1, 1)
    #     "x^n / (n * log(n+1))",
    #     # 22. x^n / (n * log(n+1)^2)
    #     # R=1. Right x=1: ∑1/(n·ln²n) CONVERGES (integral test, p=2).
    #     # Left x=-1: also converges (abs). I=[-1, 1]
    #     "x^n / (n * log(n+1)^2)",
    #     # 23. log(n) / n * x^n
    #     # R=1. Right x=1: ∑ln(n)/n diverges. Left x=-1: AST → CONVERGES. I=[-1, 1)
    #     "log(n) / n * x^n",
    #     # 24. log(n) / n^2 * x^n
    #     # R=1. Both endpoints: ∑ln(n)/n² converges (comparison/integral). I=[-1, 1]
    #     "log(n) / n^2 * x^n",
    #     # 25. log(n)^2 / n * x^n
    #     # R=1. Right x=1: ∑ln²(n)/n diverges. Left: AST → CONVERGES. I=[-1, 1)
    #     "log(n)^2 / n * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 6 — TRIG/SPECIAL FUNCTION COEFFICIENTS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 26. sin(1/n) * x^n
    #     # sin(1/n) ~ 1/n for large n → behaves like harmonic.
    #     # R=1, I=[-1, 1)
    #     "sin(1/n) * x^n",
    #     # 27. sin(n) * x^n / n
    #     # |sin(n)| ≤ 1, limsup |a_n|^(1/n) = 1. R=1.
    #     # Endpoints tricky — sin(n) doesn't go to 0, terms oscillate. Both DIVERGE.
    #     # I=(-1, 1)
    #     "sin(n) * x^n / n",
    #     # 28. cos(1/n) * x^n
    #     # cos(1/n) → 1. Root test: R=1.
    #     # Both endpoints: cos(1/n)*(±1)^n → ±1 ≠ 0 → DIVERGE. I=(-1, 1)
    #     "cos(1/n) * x^n",
    #     # 29. tan(1/n) * x^n
    #     # tan(1/n) ~ 1/n → same as harmonic. R=1.
    #     # I=[-1, 1)
    #     "tan(1/n) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 7 — DOUBLE FACTORIAL & EXOTIC RATIOS
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 30. (2*n choose n) / 4^n * x^n  — Catalan-adjacent
    #     # (2n)!/(n!^2 * 4^n) ~ 1/√(πn) → 0. R=1.
    #     # left: AST → CONVERGES. right: ∑1/√(πn) diverges. I=[-1, 1)
    #     "factorial(2*n) / (factorial(n)^2 * 4^n) * x^n",
    #     # 31. n! / (n^n * sqrt(n)) * x^n
    #     # Stirling: n!/(n^n√n) ~ √(2π)/e^n. R=e.
    #     # Both endpoints: |a_n * e^n| ~ √(2π) → constant ≠ 0 → DIVERGE. I=(-e, e)
    #     "factorial(n) / (n^n * sqrt(n)) * x^n",
    #     # 32. (n!)^2 / factorial(2*n) * x^n
    #     # = 1/C(2n,n). By Stirling: (n!)^2/(2n)! ~ √(πn)/4^n. R=4.
    #     # left x=-4: AST with terms ~ √(πn)*(−1)^n — terms → ∞, DIVERGE.
    #     # right x=4: terms ~ √(πn) → ∞, DIVERGE. I=(-4, 4)
    #     "factorial(n)^2 / factorial(2*n) * x^n",
    #     # 33. (n^2 + 1) / (n^2 - 1) * x^n  (n >= 2)
    #     # Coefficients → 1 as n→∞. R=1.
    #     # Both endpoints: terms → ±1 ≠ 0 → DIVERGE. I=(-1, 1)
    #     "((n^2 + 1) / (n^2 - 1)) * x^n",
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # TIER 8 — ABSOLUTE MONSTERS (Maximum difficulty)
    #     # ──────────────────────────────────────────────────────────────────────────
    #     # 34. ((n^2+1)/(n^2-1))^(n^2) * x^n
    #     # ln(a_n) = n^2 * ln(1 + 2/(n^2-1)) ≈ 2. So a_n → e^2.
    #     # Root: |a_n|^(1/n) → 1. R=1.
    #     # Both endpoints: a_n*(±1)^n → ±e^2 ≠ 0 → DIVERGE. I=(-1, 1)
    #     "((n^2 + 1) / (n^2 - 1))^(n^2) * x^n",
    #     # 35. (1 + 1/n^2)^(n^3) * x^n
    #     # ln(a_n) = n^3 * ln(1+1/n^2) ≈ n. a_n ~ e^n.
    #     # Root: |a_n|^(1/n) → e. R=1/e.
    #     # Both endpoints: a_n*(±1/e)^n → 1 ≠ 0 → DIVERGE. I=(-1/e, 1/e)
    #     "(1 + 1/n^2)^(n^3) * x^n",
    # ]


    test_series = [expr for expr in test_series]
    print("=" * 80)
    print("POWER SERIES ENGINE v2.0 — OPTIMIZED EDITION")
    print("=" * 80)

    total_time = 0
    for s in test_series:
        print(f"\n--- Analyzing: {s} ---")
        t0 = time.perf_counter()
        res = analyze_power_series(s)
        elapsed = (time.perf_counter() - t0) * 1000
        total_time += elapsed
        print(f"Time: {elapsed:.1f}ms")
        pprint.pprint(res)

    print(f"\n{'=' * 80}")
    print(f"Total analysis time: {total_time:.1f}ms for {len(test_series)} series")
    print(f"Average: {total_time / len(test_series):.1f}ms per series")
    print("=" * 80)
