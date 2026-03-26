import sys
import os
import sympy as sp
from colorama import init, Fore, Style

# Assuming this needs to hit the same folder
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from conv_div_engine import evaluate_expression

init(autoreset=True)

list_of_expressions = [
    "x^n / n",  # Harmonic endpoints
    "(x-2)^n / (n * 3^n)",  # Shifted center
    "factorial(n) * x^n",  # Zero radius
    "x^n / factorial(n)",
    "gamma(n + 0.5) / (sqrt(n) * gamma(n))",  # Gamma Boundary Asymptotics
    "n^2 * (exp(1/n) - 1 - 1/n)",  # Taylor Trap
    "(log(n + 1) - log(n)) * n",  # Infinite radius
    "(-1)^n * (x+1)^n / n^2",  # Both endpoints closed
    "n^n / factorial(n) * x^n",  # R = 1/e
    "factorial(2*n) / factorial(n)^2 * (x-3)^n",  # R = 1/4
    "(1 + 1/n)^(n^2) * x^n",  # Exponential limit
    "log(n) / n^2 * x^n",
    "n^log(n) / 2^n",  # Sub-exponential
    "(2^(4*n) * factorial(n)^4) / (factorial(2*n)^2 * (2*n + 1))",  # Wallis Product (Factorial Form) -> pi/2
    "n^3 * (sin(1/n) - 1/n + 1/(6*n^3))",  # Cancellation trap
    "(1 + sin(1/n)/n)^(n^2)",  # Tricky Exp  # Logarithmic
    "(3x - 2)^n / (n * 5^n)",  # Linear shift
    "(x+2)^(2*n) / (9^n * n)",  # Power 2n
    "(-1)^n * (x-1)^n / (sqrt(n) * 2^n)",  # Alternating with sqrt
    "(2x - 1)^n / n^3",  # Multiplier on x
    "factorial(n) / n^n * (x-5)^n",  # R = e
    "((n^2 + 1) / (n^2 - 1))^(n^2) * (x+1)^n",
    "factorial(n) / n^n",  # Ratio Test boundary
    "(factorial(n) * exp(n)) / n^(n + 0.5)",  # Gauss
    "factorial(2*n) / (factorial(n)^2 * 4^n)",  # Wallis Diverge
    "log(n)^log(n) / n^log(n)",  # ln(n)^ln(n) / n^ln(n)
    "1 / n^(1 + 1/log(n))",  # Log Trap
    "(-1)^n * sqrt(n) / (n + 100)",  # (-1)^n * sqrt(n) / (n+100)
    "sqrt(n + 1) - sqrt(n)",  # Telescope Divergent
    # Complex power
    "log(n) / sqrt(n) * (x - pi)^n",  # Log/sqrt at pi
    "factorial(3*n) / factorial(n)^3 * x^n",  # R = 1/27
    "sin(1/n) * x^n",  # Harmonic equivalent
    "(x + E)^n / (n * log(n)^2)",  # Log series
    "n^(1/n) * x^n",  # Root limit 1
    "x^n / n^2",  # P-series p=2
    "n^2 * x^n",  # Polynomial growth
    "x^n / sqrt(n)",  # P-series p=1/2
    "(-1)^n * x^n / n",  # Alternating harmonic
    "(x - 3)^n / (n * 4^n)",
    "n * sin(n)",  # Oscillatory Unbounded
    "cos(2/n)^(n^2)",  # Taylor Exp
    "factorial(n) / 100^n",  # Heavy Growth
    "(n / log(n)) * (n^(1/n) - 1)",  # n/ln(n) * (n^(1/n) - 1)
    "sqrt(n^2 + n) - n",  # sqrt(n^2 + n) - n
    "(1 + 1/n)^(n^2)",  # Exp explosion
    "factorial(n)^(1/n) / n",  # Stirling
    "log(n)^log(n) / n",  # Tower vs Poly
    "(-1)^n * (n / (n + 1))",  # Alt Bounded
    "(1 - 2/n)^(3*n)",  # Exp transform  # Shifted geometric
    "(x + 5)^n / n^3",  # P-series p=3
    "(2x - 1)^n / n^2",  # Linear transform
    "(3x + 2)^n / (n * 2^n)",  # Linear shift
    "(x - pi)^n / (n * E^n)",  # At pi, period e
    "n^n / factorial(n) * x^n",  # Stirling
    "factorial(n) / n^n * x^n",  # Inverse Stirling
    "factorial(4*n) / factorial(n)^4 * x^n",  # 4-factorial
    "binomial(2*n, n) * x^n",  # Central binomial
    "(1 + 1/n)^n * x^n",  # Converges to e
    "(1 + 2/n)^n * x^n",
    "factorial(2*n)^(1/n) / (4^n / n)",  # -> 0
    "factorial(2*n) / (factorial(n) * (2*n)^(n + 1/2))",  # Stirling
    "gamma(n + 3/2) / (sqrt(n) * gamma(n + 1))",  # -> 1
    "sin(n*pi/2) / n",  # -> 0
    "n * sin(pi/n)",  # -> pi
    "(-1)^n * n / (n^2 + 1) + 1/2",  # -> 1/2
    "cos(1/n)^(n^2)",  # -> e^(-1/2)
    "log(n)^log(log(n)) / n",  # -> 0
    "n^(1/log(log(n)))",  # -> oo
    "log(n + log(n)) - log(n)",  # -> 0
    "(1 + 1/n^2)^(n^2)",  # -> e
    "n * (1 - cos(1/n))",  # -> 0
    "factorial(n)^2 / factorial(2*n)",  # -> 0
    # Converges to e^2
    "(n / (n+1))^(n^2) * x^n",  # Complex limit
    "x^n / (n * log(n+1))",  # Log denominator
    "x^n / (n * log(n+1)^2)",
    "(-1)^n * log(n) / n",  # Alt
    "1 / (n * log(n))",  # Classic Divergent
    "1 / (n * log(n)^1.1)",  # Classic Conv
    "sin(1/n)",  # Harmonic Equivalent
    "1 - cos(1/n)",  # Taylor ~1/n^2
    "(n / (n + 1))^n",  # Nth term -> 1/e
    "(n / (n + 1))^(n^2)",  # Root  # Log squared
    "log(n) / n * x^n",  # Log/n
    "log(n) / n^2 * x^n",  # Log/n^2
    "log(n)^2 / n * x^n",  # Log squared/n
    "sin(1/n) * x^n",  # Sine
    "sin(n) * x^n / n",  # Oscillating
    "cos(1/n) * x^n",
    "1 / (n * log(n)^2 * log(log(n)))",  # Conv
    "factorial(n)^2 / factorial(2*n)",  # Conv
    "factorial(n)^3 / factorial(3*n)",  # Conv
    "factorial(3*n) / (factorial(n) * factorial(2*n) * 3^n)",  # Div
    "log(n)^n / n^n",  # Conv (Root -> 0)
    "((2*n + 1) / (3*n - 1))^n",  # Conv Root->2/3
    "(n / (n + log(n)))^n",  # Div (Root L=1)
    "(-1)^n / (n + log(n))",  # Cond Conv
    "(-1)^n * log(n) / n^(3/2)",  # Abs Conv
    "(-1)^n * (1 - 1/n)^n",  # Div nth-term
    "log(n)^log(n) / n^2",  # Div (terms -> oo)
    "log(n)^n / factorial(n)",  # Conv (ratio->0)
    "1 / n^(1 + sin(1/n))",  # Div
    # Cosine
    "tan(1/n) * x^n",  # Tangent
    "factorial(2*n) / (factorial(n)^2 * 4^n) * x^n",  # Catalan-adjacent
    "factorial(n) / (n^n * sqrt(n)) * x^n",  # Stirling with sqrt
    "factorial(n)^2 / factorial(2*n) * x^n",  # Inverse binomial
    "((n^2 + 1) / (n^2 - 1)) * x^n",  # Rational coefficient
    "((n^2 + 1) / (n^2 - 1))^(n^2) * x^n",  # Rational to power
    "(1 + 1/n^2)^(n^3) * x^n",  # Triple power
]


def format_res(res_tuple):
    if not res_tuple:
        return f"{Fore.YELLOW}None{Style.RESET_ALL}"

    res_bool, details, logs = res_tuple[0], res_tuple[1], res_tuple[2]

    if res_bool is True:
        status = f"{Fore.GREEN}{'Converges':<12}{Style.RESET_ALL}"
    elif res_bool is False:
        status = f"{Fore.RED}{'Diverges':<12}{Style.RESET_ALL}"
    else:
        status = f"{Fore.YELLOW}{'Unknown':<12}{Style.RESET_ALL}"

    return f"{status} | {details}"


def main():
    mixed_expressions = [
        # main sequences (5)
        "n * sin(n)",
        "cos(2/n)^(n^2)",
        "factorial(n) / 100^n",
        "(n / log(n)) * (n^(1/n) - 1)",
        "sqrt(n^2 + n) - n",
        # main series (5)
        "(-1)^n * log(n) / n",
        "1 / (n * log(n))",
        "1 / (n * log(n)^1.1)",
        "sin(1/n)",
        "1 - cos(1/n)",
        # second_main sequences (5)
        "((n^2 + 1) / (n^2 - 1))^(n^2)",
        "(1 + log(n)/n)^n",
        "factorial(n)^(1/n^2)",
        "n * (exp(1/n) - cos(1/n))",
        "n^2 * (log(1 + 1/n) - sin(1/n))",
        # second_main series (5)
        "1 / (n * log(n) * log(log(n)))",
        "1 / n^(1 + 1/n)",
        "1 / (n * log(n)^2 * log(log(n)))",
        "factorial(n)^2 / factorial(2*n)",
        "factorial(n)^3 / factorial(3*n)",
        # power_series_main (10)
        "x^n / n",
        "(x - 2)^n / (n * 3^n)",
        "factorial(n) * x^n",
        "x^n / factorial(n)",
        "(-1)^n * (x + 1)^n / n^2",
        "(n^n / factorial(n)) * x^n",
        "(factorial(2*n) / factorial(n)^2) * (x - 3)^n",
        "(1 + 1/n)^(n^2) * x^n",
        "(log(n) / n^2) * x^n",
        "(3*x - 2)^n / (n * 5^n)",
    ]

    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 160}")
    print(
        f"{Fore.CYAN}{Style.BRIGHT}{'UNIVERSAL SMART ENGINE TEST (Sequences, Series, Power Series)':^160}"
    )
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 160}")

    # Table Header
    header = f"{'No':<3} | {'Expression':<35} | {'Detected Type':<15} | {'Sequence Result':<30} | {'Series Result':<30} | {'Power Series Info':<30}"
    print(f"{Fore.YELLOW}{Style.BRIGHT}{header}{Style.RESET_ALL}")
    print("-" * 160)

    for i, expr_str in enumerate(list_of_expressions, 1):
        try:
            res = evaluate_expression(expr_str)
        except Exception as e:
            print(f"{i:<3} | {expr_str:<35} | {Fore.RED}ERROR{Style.RESET_ALL}")
            continue

        if res.get("error"):
            print(
                f"{i:<3} | {expr_str:<35} | {Fore.RED}ERROR{Style.RESET_ALL} : {res['error']}"
            )
            continue

        expr_disp = expr_str if len(expr_str) <= 35 else expr_str[:32] + "..."

        if res["is_power_series"]:
            dtype = f"{Fore.BLUE}Power Series{Style.RESET_ALL}"
            ps_res = res["power_series_result"]
            ps_info = ps_res[1] if ps_res else "N/A"
            ps_info_disp = ps_info if len(ps_info) <= 30 else ps_info[:27] + "..."

            print(
                f"{i:<3} | {expr_disp:<35} | {dtype:<24} | {'-':<30} | {'-':<30} | {Fore.BLUE}{ps_info_disp:<30}{Style.RESET_ALL}"
            )
        else:
            dtype = f"{Fore.CYAN}Seq/Series{Style.RESET_ALL}"
            seq_res = res["seq_result"]
            ser_res = res["ser_result"]

            seq_bool = seq_res[0] if seq_res else None
            ser_bool = ser_res[0] if ser_res else None

            seq_status = (
                f"{Fore.GREEN}Conv{Style.RESET_ALL}"
                if seq_bool is True
                else f"{Fore.RED}Divg{Style.RESET_ALL}"
                if seq_bool is False
                else "Unk"
            )
            ser_status = (
                f"{Fore.GREEN}Conv{Style.RESET_ALL}"
                if ser_bool is True
                else f"{Fore.RED}Divg{Style.RESET_ALL}"
                if ser_bool is False
                else "Unk"
            )

            seq_info = seq_res[1] if seq_res else ""
            ser_info = ser_res[1] if ser_res else ""

            seq_disp = f"{seq_status} - {seq_info}"[
                :38
            ]  # accounts for color codes length
            ser_disp = f"{ser_status} - {ser_info}"[:38]

            # Clean up escape codes messing up widths when slicing:
            # Better to slice the original string then apply color

            seq_inf_trim = seq_info if len(seq_info) <= 22 else seq_info[:19] + "..."
            ser_inf_trim = ser_info if len(ser_info) <= 22 else ser_info[:19] + "..."

            seq_col = f"{seq_status} {seq_inf_trim}"
            ser_col = f"{ser_status} {ser_inf_trim}"

            print(
                f"{i:<3} | {expr_disp:<35} | {dtype:<24} | {seq_col:<39} | {ser_col:<39} | {'-':<30}"
            )


if __name__ == "__main__":
    main()


