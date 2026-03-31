import sys,os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engines import FunctionAnalysisEngine

def pretty_print(result):
    print("\n" + "="*60)
    
    # Function
    print(f"Function: {result.get('Function')}")
    print(f"Domain  : {result.get('Domain')}")
    
    # Intercepts
    intercepts = result.get('Intercepts', {})
    print("\nIntercepts:")
    print(f"  x-intercepts: {intercepts.get('x')}")
    print(f"  y-intercept : {intercepts.get('y')}")
    
    # Extrema
    extrema = result.get('Extrema', {})
    print("\nExtrema:")
    print(f"  Minima: {extrema.get('minima')}")
    print(f"  Maxima: {extrema.get('maxima')}")
    
    # Inflection Points
    print("\nInflection Points:")
    print(f"  {result.get('Inflection Points')}")
    
    # Asymptotes
    asym = result.get('Asymptotes', {})
    print("\nAsymptotes:")
    print(f"  Vertical  : {asym.get('vertical')}")
    print(f"  Horizontal: {asym.get('horizontal')}")
    print(f"  Oblique   : {asym.get('oblique')}")
    
    # Other properties
    print("\nOther Properties:")
    print(f"  Parity      : {result.get('Parity')}")
    print(f"  Periodicity : {result.get('Periodicity')}")
    
    # Monotonicity
    mono = result.get('Monotonicity', {})
    print("\nMonotonicity:")
    print(f"  Increasing: {mono.get('increasing')}")
    print(f"  Decreasing: {mono.get('decreasing')}")
    
    print("="*60)


if __name__ == "__main__":
    engine = FunctionAnalysisEngine(debug=False)

    test_functions = [
        # Originals
        "(sin(ln((x)^(1/2)))/x!)",
        "x^(1/x)",
        "x^3 - 6*x^2 + 9*x + 15",
        "1 / x",
        "sin(x)",
        "x^2 / (x^2 - 4)",
        "e^(-x^2)",
        "ln(x)",
        "(x^2 + 1) / x",
        "x^3 - 3*x",
        "tan(x)",
        "x * e^x",
        "sin(x) / x",
        "sqrt(x - 1)",
        "(x^2 - 1) / (x^2 + 1)",
        "abs(x)",
        "x * ln(x)",
        # Extended stress tests
        "1 / (x^2 + 1)",
        "(x^3 - x) / (x^2 - 1)",       # was 12 s — now < 1 s after cancel()
        "(x^2 - 4) / (x - 2)",
        "x / (x^2 - x - 6)",
        "(x^3 + 1) / (x^2 - 1)",
        "cos(x)",
        "sin(x)^2",                     # period should be pi
        "tan(x)^2",
        "arctan(x)",
        "x - sin(x)",
        "sin(x) + cos(x)",
        "1 / sin(x)",
        "e^x / (1 + e^x)",
        "ln(x^2)",
        "x^2 * e^(-x)",
        "ln(x + sqrt(x^2 + 1))",        # arcsinh — parity should be Odd
        "e^(1/x)",
        "x^4 - 2*x^2 + 1",
        "x^5 - x^3 + x",
        "x^2 + x + 1",
        "sqrt(4 - x^2)",
        "ln(1 - x^2)",
        "1 / sqrt(x^2 - 1)",
        "sqrt(x) * ln(x)",
        "x^(1/3)",                      # monotone on all R
        "x * sin(x)",
        "sin(1/x)",
        "x^2 * sin(1/x)",
        "abs(x^2 - 1)",
        "floor(x)",
        "x + 1/x",
        "(x^3 - 1) / (x^2 + x + 1)",
        "x^2 / (x + 1)",
        "x^x",                          # HA y=0 was spurious — now suppressed
        "ln(ln(x))",                    # VA at x=0 was spurious — now suppressed
        "1 / (1 - x^2)",
    ]

    for f_str in test_functions:
        result = engine.analyze(f_str)
        pretty_print(result)