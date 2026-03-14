import re

with open("algo.py", "r") as f:
    content = f.read()

eval_logic = """    # Strategy D: numerical fallback
    with Timer("numerical_range") as t:
        if range_res is None:
            debug_print("Strategy D: numerical fallback" +
                        (" (after timeout)" if any_timed_out else ""), Fore.CYAN)
            range_res_str, method = smart_numerical_range(
                f, x, domain, behavior_info=behavior_info
            )
            if RUST_AVAILABLE:
                method += " [Rust]"
            if isinstance(range_res_str, str) and "Error" not in range_res_str:
                from sympy import Interval, Union, oo
                try:
                    range_res = eval(range_res_str)
                except Exception:
                    range_res = range_res_str
            else:
                range_res = range_res_str
    stats.numerical_range_time = t.elapsed"""

content = re.sub(r'    # Strategy D: numerical fallback\n    with Timer\("numerical_range"\) as t:.*?stats\.numerical_range_time = t\.elapsed', eval_logic, content, flags=re.DOTALL)

with open("algo.py", "w") as f:
    f.write(content)
