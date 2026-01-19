use colored::*;
use fasteval::{Compiler, Evaler, Parser, Slab};
use rayon::prelude::*;
use std::f64;

// --- Configuration ---
const DENSE_RANGE: f64 = 100.0;
const DENSE_STEPS: usize = 2_000_000; 
const WIDE_RANGE: f64 = 1_000_000.0; 
const WIDE_STEPS: usize = 1_000_000; 
const INF_CHECK: f64 = 1e15; 

fn main() {
    println!("{}", "=== RUST ROBUST SOLVER (FASTEVAL) ===\n".magenta().bold());

    let tests = vec![
        "abs(x)",
        "sin(x)/x",
        "x^x", 
        "1/x",
        "floor(x)",
        "x^2",
        "sin(x)",
        "exp(x)",
        "log(x)",
        "x^3",
        "1/(1+x^2)",
    ];

    println!("{}", "--- Standard Tests ---".white());
    for t in tests { solve(t); }

    let hard_tests = vec![
        "x * sin(x)",
        "exp(-x^2)",
        "(x^2 - 1)/(x^2 + 1)",
        "sqrt(16 - x^2)",
        "abs(sin(x))",
        "x + sin(x)",
        "tan(x)",
        "log(abs(x))",
        "1/sin(x)",
        "exp(sin(x))",
    ];

    println!("\n{}", "--- Hard/Complex Tests ---".white());
    for t in hard_tests { solve(t); }
}

fn solve(func_str: &str) {
    print!("{}: ", func_str.cyan());

    // 1. Setup Parser & Slab (Memory for the expression)
    let mut slab = Slab::new();
    let parser = Parser::new();
    
    // 2. Parse and Compile
    // We do this ONCE. The 'slab' and 'compiled' instruction are thread-safe (Sync).
    let compiled = match parser.parse(func_str, &mut slab.ps) {
        Ok(p) => {
            // Compile to stack-based instructions for speed
            p.from(&slab.ps).compile(&slab.ps, &mut slab.cs)
        },
        Err(_) => {
            println!("{}", "[FAIL] Parsing Error".red());
            return;
        }
    };

    // Helper to evaluate at x using the compiled instruction
    // We pass &slab (read-only) to all threads.
    let eval_at = |x: f64| -> (f64, f64) {
        // Define a simple callback map for variable 'x'
        let mut map_cb = |name:&str, _args:Vec<f64>| -> Option<f64> {
            if name == "x" { Some(x) } else { None }
        };
        
        // Execute
        match compiled.eval(&slab, &mut map_cb) {
            Ok(y) => {
                if y.is_nan() { (f64::INFINITY, f64::NEG_INFINITY) } 
                else { (y, y) }
            },
            Err(_) => (f64::INFINITY, f64::NEG_INFINITY) // Ignore errors (complex/undefined)
        }
    };

    // 3. Parallel Grid Search (Brute Force)
    
    // Range 1: Dense
    let dense_step = (DENSE_RANGE * 2.0) / DENSE_STEPS as f64;
    let local_res = (0..DENSE_STEPS).into_par_iter()
        .map(|i| {
            let x = -DENSE_RANGE + (i as f64 * dense_step);
            eval_at(x)
        })
        .reduce(|| (f64::INFINITY, f64::NEG_INFINITY), |a, b| (a.0.min(b.0), a.1.max(b.1)));

    // Range 2: Wide
    let wide_step = (WIDE_RANGE * 2.0) / WIDE_STEPS as f64;
    let global_res = (0..WIDE_STEPS).into_par_iter()
        .map(|i| {
            let x = -WIDE_RANGE + (i as f64 * wide_step);
            eval_at(x)
        })
        .reduce(|| (f64::INFINITY, f64::NEG_INFINITY), |a, b| (a.0.min(b.0), a.1.max(b.1)));

    // 4. Asymptotic Check
    let neg_inf_val = eval_at(-INF_CHECK).0;
    let pos_inf_val = eval_at(INF_CHECK).0;

    // Combine results
    let mut min_val = local_res.0.min(global_res.0);
    let mut max_val = local_res.1.max(global_res.1);

    // Heuristics for Infinity
    if neg_inf_val < -1e10 || pos_inf_val < -1e10 { min_val = f64::NEG_INFINITY; }
    if neg_inf_val > 1e10 || pos_inf_val > 1e10 { max_val = f64::INFINITY; }
    if min_val < -1e12 { min_val = f64::NEG_INFINITY; }
    if max_val > 1e12 { max_val = f64::INFINITY; }

    // Print Result
    let min_str = fmt_val(min_val);
    let max_str = fmt_val(max_val);

    if min_val == f64::INFINITY && max_val == f64::NEG_INFINITY {
        println!("{}", "Undefined / Complex".yellow());
    } else {
        println!("{} Interval[{}, {}]", "Range:".green(), min_str, max_str);
    }
}

fn fmt_val(val: f64) -> String {
    if val == f64::INFINITY { return "oo".to_string(); }
    if val == f64::NEG_INFINITY { return "-oo".to_string(); }
    if val.abs() < 1e-9 { return "0".to_string(); }
    let rounded = (val * 10000.0).round() / 10000.0;
    rounded.to_string()
}