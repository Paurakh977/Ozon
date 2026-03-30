
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from colorama import Fore
from engines import solve
def main():
    print(f"{Fore.MAGENTA}=== ROBUST SOLVER v4 ===")


    all_stats = []

    print(f"{Fore.WHITE}--- Standard Tests ---")
    standard_stats = []
    for fn in [
        "abs(x)",
        "sin(x)/x",
        "x**x",
        "1/x",
        "floor(x)",
        "x**2",
        "sin(x)",
        "exp(x)",
        "log(x)",
        "x**3",
        "1/(1+x**2)",
    ]:
        s = solve(fn)
        if s:
            all_stats.append(s)
            standard_stats.append(s)
    if standard_stats:
        st_total = sum(s.total_time for s in standard_stats)
        st_avg = st_total / len(standard_stats)
        print(f"{Fore.CYAN}Standard tests: {len(standard_stats)} funcs — total {st_total*1000:.1f}ms, avg {st_avg*1000:.1f}ms")

    print(f"\n{Fore.WHITE}--- Hard/Complex Tests ---")
    hard_stats = []
    for fn in [
        "x * sin(x)",
        "exp(-x**2)",
        "(x**2 - 1)/(x**2 + 1)",
        "sqrt(16 - x**2)",
        "abs(sin(x))",
        "x + sin(x)",
        "tan(x)",
        "log(abs(x))",
        "1/sin(x)",
        "exp(sin(x))",
    ]:
        s = solve(fn)
        if s:
            all_stats.append(s)
            hard_stats.append(s)
    if hard_stats:
        ht_total = sum(s.total_time for s in hard_stats)
        ht_avg = ht_total / len(hard_stats)
        print(f"{Fore.CYAN}Hard/Complex tests: {len(hard_stats)} funcs — total {ht_total*1000:.1f}ms, avg {ht_avg*1000:.1f}ms")

    print(f"\n{Fore.WHITE}--- Extreme/Challenging Tests ---")
    extreme_stats = []
    for fn in [
        "atan(x)", "asin(x)", "acos(x)",
        "sinh(x)", "cosh(x)", "tanh(x)",
        "sin(x**2)", "exp(-abs(x))", "x/(1+x**2)", "x**2/(1+x**4)",
        "sin(x)*cos(x)",
        "(x-1)/(x+1)", "x/(x**2-1)", "(x**2+1)/(x**2-1)",
        "x**(1/3)", "abs(x)**(1/2)", "x**4 - x**2",
        "exp(1/x)", "exp(-1/x**2)", "x*exp(-x**2)",
        "log(x**2+1)", "log(1+x**2)/x**2",
        "sin(x) + cos(x)", "sin(x)**2", "sin(x)**2 + cos(x)**2",
        "sin(x)/x**2", "exp(-x)*sin(x)",
    ]:
        s = solve(fn)
        if s:
            all_stats.append(s)
            extreme_stats.append(s)
    if extreme_stats:
        ex_total = sum(s.total_time for s in extreme_stats)
        ex_avg = ex_total / len(extreme_stats)
        print(f"{Fore.CYAN}Extreme tests: {len(extreme_stats)} funcs — total {ex_total*1000:.1f}ms, avg {ex_avg*1000:.1f}ms")

    print(f"\n{Fore.WHITE}--- User Added Tests ---")
    user_stats = []
    for fn in [
        "log(log(x))",
        "sqrt(sin(x))",
        "x*log(x)",
        "log(x + sqrt(x**2 + 1))",
        "sqrt(x**2 - 4*x + 3)",
        "exp(x)/(1 + exp(x))",
        "sin(1/x)",
        "x - floor(x)",
        "atan(1/x)",
        "sqrt((x-1)/(x+1))",
        "x**2 * sin(1/x)",
        "log(x*(1-x))",
        "x / sqrt(1 - x**2)",
        # Extra regression tests for the two fixed bugs
        "sqrt(cos(x))",
        "log(sin(x))",
        "floor(x) + 1",
        "2*floor(x)",
        "ceiling(x) - floor(x)",
    ]:
        s = solve(fn)
        if s:
            all_stats.append(s)
            user_stats.append(s)
    if user_stats:
        us_total = sum(s.total_time for s in user_stats)
        us_avg = us_total / len(user_stats)
        print(f"{Fore.CYAN}User tests: {len(user_stats)} funcs — total {us_total*1000:.1f}ms, avg {us_avg*1000:.1f}ms")

    # -------------------------------------------------------------------------
    # ADVERSARIAL TESTS
    # Expected correct answers listed as comments for easy verification:
    #
    #  sqrt(x - floor(x))          Domain: (-oo,oo)           Range: [0, 1)
    #  floor(sin(x))               Domain: (-oo,oo)           Range: {-1, 0, 1}
    #  1/(1 - 2*sin(x))            Domain: periodic complement Range: (-oo,-1] U [1/3,+oo)
    #  log(x + 1/x)                Domain: (0, oo)            Range: [log(2), oo)
    #  x**(1/x)                    Domain: (0, oo)            Range: (0, exp(1/E)]
    #  atan(x) + atan(1/x)         Domain: (-oo,0)U(0,oo)     Range: {-pi/2, pi/2}
    #  floor(x**2)                 Domain: (-oo,oo)           Range: non-negative integers {0,1,2,...}
    #  log(x - floor(x))           Domain: RR \ ZZ            Range: (-oo, 0)
    #  (1 - cos(x))/(1 + cos(x))  Domain: periodic complement Range: [0, oo)
    #  acos(1/(1 + x**2))          Domain: (-oo,oo)           Range: [0, pi/2)
    #  sin(x + sin(x))             Domain: (-oo,oo)           Range: [-1, 1]
    #  ceiling(x) * floor(x)       Domain: (-oo,oo)           Range: irregular integers
    # -------------------------------------------------------------------------
    print(f"\n{Fore.WHITE}--- Adversarial Tests ---")
    adversarial_stats = []
    for fn in [
        "sqrt(x - floor(x))",
        "floor(sin(x))",
        "1/(1 - 2*sin(x))",
        "log(x + 1/x)",
        "x**(1/x)",
        "atan(x) + atan(1/x)",
        "floor(x**2)",
        "log(x - floor(x))",
        "(1 - cos(x))/(1 + cos(x))",
        "acos(1/(1 + x**2))",
        "sin(x + sin(x))",
        "ceiling(x) * floor(x)",
    ]:
        s = solve(fn)
        if s:
            all_stats.append(s)
            adversarial_stats.append(s)
    if adversarial_stats:
        adv_total = sum(s.total_time for s in adversarial_stats)
        adv_avg = adv_total / len(adversarial_stats)
        print(f"{Fore.CYAN}Adversarial tests: {len(adversarial_stats)} funcs — total {adv_total*1000:.1f}ms, avg {adv_avg*1000:.1f}ms")

    if all_stats:
        total   = sum(s.total_time for s in all_stats)
        avg     = total / len(all_stats)
        fastest = min(s.total_time for s in all_stats)
        slowest = max(s.total_time for s in all_stats)

        p_parse  = sum(s.parsing_time         for s in all_stats)
        p_domain = sum(s.domain_time          for s in all_stats)
        p_sym    = sum(s.symbolic_range_time   for s in all_stats)
        p_num    = sum(s.numerical_range_time  for s in all_stats)

        print(f"\n{Fore.MAGENTA}{'='*50}")
        print(f"{Fore.MAGENTA}TIMING SUMMARY ({len(all_stats)} functions)")
        print(f"{Fore.MAGENTA}{'='*50}")
        print(f"{Fore.WHITE}Total:   {total*1000:.1f}ms   "
              f"Avg: {avg*1000:.1f}ms   "
              f"Min: {fastest*1000:.1f}ms   "
              f"Max: {slowest*1000:.1f}ms")
        print(f"\n{Fore.CYAN}Breakdown:")
        for label, t in [("Parsing",         p_parse),
                          ("Domain",          p_domain),
                          ("Symbolic range",  p_sym),
                          ("Numerical range", p_num)]:
            print(f"  {label:<20} {t*1000:>8.1f}ms  ({100*t/total:>5.1f}%)")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()