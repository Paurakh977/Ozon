import time,os,sys,math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from engines import TangentEngine, TangentResult, _lx, _latex_tangent, _parse

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

class TestReporter:

    PASS_THRESH = 1e-5

    def __init__(self):
        self.engine = TangentEngine()

    def run_all(self):
        engine    = self.engine
        grand_t0  = time.perf_counter()
        total_ok = total_err = total_warn = 0
        all_results: list[TangentResult] = []

        # Loop through categories
        for category, funcs in CATEGORIES.items():

            print(f"\n\n########## {category} ##########\n")

            for fs in funcs:
                r = engine.compute(fs)
                
                try:
                    fx_latex = _lx(_parse(r.func_str))
                except Exception:
                    fx_latex = r"\text{error parsing}"

                # Format everything locally for displaying
                summary = {
                    "function": fx_latex,
                    "f(a)": _lx(r.ft_expr) if r.ft_expr is not None else "",
                    "f'(a)": _lx(r.fpt_expr) if r.fpt_expr is not None else "",
                    "lhs": _lx(r.lhs_expr) if r.lhs_expr is not None else "",
                    "rhs": _lx(r.rhs_expr) if r.rhs_expr is not None else "",
                    "derivative": _lx(r.deriv_expr) if r.deriv_expr is not None else "",
                    "tangent_equation": _latex_tangent(r),
                    "strategy": r.strategy,
                    "status": r.status,
                    "error": r.error,
                    "num_error": r.num_error
                }

                # ✅ Proper printing INSIDE loop
                print("==============================")
                print(f"For this function -> {summary['function']}")

                for key, value in summary.items():
                    if key != "function":
                        print(f"  • Its {key} is -> {value}")

                print("==============================\n")
                
                # ✅ Store results
                all_results.append(r)

        elapsed = time.perf_counter() - grand_t0
        n = len(all_results)

        print(f"\nProcessed {n} functions in {elapsed:.4f} seconds.\n")

        return all_results

if __name__ == "__main__":
    reporter = TestReporter()
    reporter.run_all()

