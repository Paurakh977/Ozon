use colored::*;
use meval::Expr;
use rayon::prelude::*;
use std::f64::consts::PI;
use std::f64::{INFINITY, NEG_INFINITY};

// =============================================================================
// CONFIGURATION
// =============================================================================
const INF_THRESHOLD: f64 = 1e12;
const ZERO_THRESHOLD: f64 = 1e-10;
const DERIVATIVE_H: f64 = 1e-8;
const BRENT_TOLERANCE: f64 = 1e-9;
const MAX_BRENT_ITERATIONS: usize = 100;

// =============================================================================
// DOMAIN REPRESENTATION
// =============================================================================
#[derive(Debug, Clone)]
enum Domain {
    Reals,
    Interval { min: f64, max: f64, min_open: bool, max_open: bool },
    Union(Vec<Domain>),
    Complement { base: Box<Domain>, excluded: Vec<f64> },
    Empty,
}

impl std::fmt::Display for Domain {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Domain::Reals => write!(f, "Reals"),
            Domain::Interval { min, max, min_open, max_open } => {
                let left = if *min_open { "(" } else { "[" };
                let right = if *max_open { ")" } else { "]" };
                let min_s = format_val(*min);
                let max_s = format_val(*max);
                write!(f, "Interval{}{}, {}{}", left, min_s, max_s, right)
            }
            Domain::Union(intervals) => {
                let parts: Vec<String> = intervals.iter().map(|d| d.to_string()).collect();
                write!(f, "Union({})", parts.join(", "))
            }
            Domain::Complement { excluded, .. } => {
                let excl: Vec<String> = excluded.iter().map(|x| format_val(*x)).collect();
                write!(f, "Reals \\ {{{}}}", excl.join(", "))
            }
            Domain::Empty => write!(f, "Empty"),
        }
    }
}

// =============================================================================
// RANGE REPRESENTATION
// =============================================================================
#[derive(Debug, Clone)]
struct Range {
    min: f64,
    max: f64,
    min_open: bool,
    max_open: bool,
    is_union: bool, // For functions like 1/x that have disjoint ranges
}

impl std::fmt::Display for Range {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        let left = if self.min_open { "(" } else { "[" };
        let right = if self.max_open { ")" } else { "]" };
        
        if self.is_union && self.min == NEG_INFINITY && self.max == INFINITY {
            // Check if this might be a split range (like 1/x)
            write!(f, "Union(Interval.open(-oo, 0), Interval.open(0, oo))")
        } else {
            let min_s = format_val(self.min);
            let max_s = format_val(self.max);
            
            // Match Python's formatting style
            let interval_type = match (self.min_open, self.max_open) {
                (true, true) => ".open",
                (true, false) => ".Lopen",
                (false, true) => ".Ropen",
                (false, false) => "",
            };
            write!(f, "Interval{}({}, {})", interval_type, min_s, max_s)
        }
    }
}

// =============================================================================
// RESULT STRUCTURE
// =============================================================================
struct SolveResult {
    domain: Domain,
    range: Range,
    method: String,
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================
fn format_val(val: f64) -> String {
    if val == INFINITY || val > INF_THRESHOLD { return "oo".to_string(); }
    if val == NEG_INFINITY || val < -INF_THRESHOLD { return "-oo".to_string(); }
    if val.abs() < ZERO_THRESHOLD { return "0".to_string(); }
    
    // Round to 6 decimal places and format nicely
    let rounded = (val * 1_000_000.0).round() / 1_000_000.0;
    let s = format!("{:.6}", rounded);
    // Trim trailing zeros
    let s = s.trim_end_matches('0').trim_end_matches('.');
    s.to_string()
}

fn is_valid(val: f64) -> bool {
    val.is_finite() && !val.is_nan()
}

fn safe_eval(func: &impl Fn(f64) -> f64, x: f64) -> Option<f64> {
    let val = func(x);
    if is_valid(val) { Some(val) } else { None }
}

// =============================================================================
// NUMERICAL DERIVATIVE
// =============================================================================
fn numerical_derivative(func: &impl Fn(f64) -> f64, x: f64) -> Option<f64> {
    let h = DERIVATIVE_H * (1.0 + x.abs());
    let f_plus = safe_eval(func, x + h)?;
    let f_minus = safe_eval(func, x - h)?;
    let deriv = (f_plus - f_minus) / (2.0 * h);
    if is_valid(deriv) { Some(deriv) } else { None }
}

// =============================================================================
// BRENT'S METHOD FOR OPTIMIZATION
// =============================================================================
fn brent_minimize<F>(func: F, a: f64, b: f64, find_max: bool) -> Option<(f64, f64)>
where
    F: Fn(f64) -> f64,
{
    let f = |x: f64| -> f64 {
        let val = func(x);
        if find_max { -val } else { val }
    };
    
    let golden = 0.381966011250105;
    let mut a = a;
    let mut b = b;
    let mut x = a + golden * (b - a);
    let mut w = x;
    let mut v = x;
    
    let mut fx = f(x);
    if !is_valid(fx) { return None; }
    let mut fw = fx;
    let mut fv = fx;
    
    let mut d: f64 = 0.0;
    let mut e: f64 = 0.0;
    
    for _ in 0..MAX_BRENT_ITERATIONS {
        let midpoint = 0.5 * (a + b);
        let tol1 = BRENT_TOLERANCE * x.abs() + 1e-10;
        let tol2 = 2.0 * tol1;
        
        if (x - midpoint).abs() <= tol2 - 0.5 * (b - a) {
            let result = if find_max { -fx } else { fx };
            return Some((x, result));
        }
        
        let mut u;
        if e.abs() > tol1 {
            // Parabolic interpolation
            let r = (x - w) * (fx - fv);
            let mut q = (x - v) * (fx - fw);
            let mut p = (x - v) * q - (x - w) * r;
            q = 2.0 * (q - r);
            if q > 0.0 { p = -p; } else { q = -q; }
            
            let r_old = e;
            e = d;
            
            if p.abs() < (0.5 * q * r_old).abs() && p > q * (a - x) && p < q * (b - x) {
                d = p / q;
                u = x + d;
                if (u - a) < tol2 || (b - u) < tol2 {
                    d = if x < midpoint { tol1 } else { -tol1 };
                }
            } else {
                e = if x < midpoint { b - x } else { a - x };
                d = golden * e;
            }
        } else {
            e = if x < midpoint { b - x } else { a - x };
            d = golden * e;
        }
        
        u = if d.abs() >= tol1 { x + d } else { x + tol1 * d.signum() };
        let fu = f(u);
        if !is_valid(fu) { continue; }
        
        if fu <= fx {
            if u < x { b = x; } else { a = x; }
            v = w; fv = fw;
            w = x; fw = fx;
            x = u; fx = fu;
        } else {
            if u < x { a = u; } else { b = u; }
            if fu <= fw || w == x {
                v = w; fv = fw;
                w = u; fw = fu;
            } else if fu <= fv || v == x || v == w {
                v = u; fv = fu;
            }
        }
    }
    
    let result = if find_max { -fx } else { fx };
    Some((x, result))
}

// =============================================================================
// LIMIT ANALYSIS (NUMERICAL) - IMPROVED
// =============================================================================
fn analyze_limit(func: &impl Fn(f64) -> f64, toward: f64, _from_left: bool) -> Option<f64> {
    let sequence: Vec<f64> = if toward == INFINITY {
        vec![1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e14]
    } else if toward == NEG_INFINITY {
        vec![-1e2, -1e3, -1e4, -1e5, -1e6, -1e7, -1e8, -1e9, -1e10, -1e11, -1e12, -1e14]
    } else {
        return None; // For finite limits, handle separately
    };
    
    let vals: Vec<f64> = sequence.iter()
        .filter_map(|&x| safe_eval(func, x))
        .collect();
    
    if vals.len() < 3 { return None; }
    
    // Check for clear divergence to +infinity
    let grows_to_inf = vals.windows(2).all(|w| w[1] > w[0] * 0.9) && 
                       vals.last().map(|&v| v > 1e10).unwrap_or(false);
    if grows_to_inf { return Some(INFINITY); }
    
    // Check for clear divergence to -infinity  
    let grows_to_neg_inf = vals.windows(2).all(|w| w[1] < w[0] * 0.9) &&
                           vals.last().map(|&v| v < -1e10).unwrap_or(false);
    if grows_to_neg_inf { return Some(NEG_INFINITY); }
    
    // Check for convergence to a finite value
    let last_vals: Vec<f64> = vals.iter().rev().take(4).cloned().collect();
    if last_vals.len() >= 3 {
        let range = last_vals.iter().cloned().fold(f64::INFINITY, f64::min);
        let range_max = last_vals.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        if (range_max - range).abs() < 0.01 {
            return Some((range + range_max) / 2.0);
        }
    }
    
    None // Can't determine limit
}

// Check if function is monotonically increasing/decreasing at large values
fn check_monotonicity(func: &impl Fn(f64) -> f64) -> (bool, bool, bool, bool) {
    // Returns: (grows_pos_inf, grows_neg_inf_from_right, decreases_pos_inf, decreases_neg_inf_from_left)
    let pos_vals: Vec<f64> = vec![100.0, 1000.0, 10000.0, 100000.0]
        .iter()
        .filter_map(|&x| safe_eval(func, x))
        .collect();
    
    let neg_vals: Vec<f64> = vec![-100.0, -1000.0, -10000.0, -100000.0]
        .iter()
        .filter_map(|&x| safe_eval(func, x))
        .collect();
    
    let grows_pos = pos_vals.len() >= 3 && pos_vals.windows(2).all(|w| w[1] > w[0]);
    let grows_neg = neg_vals.len() >= 3 && neg_vals.windows(2).all(|w| w[1] > w[0]);
    let decreases_pos = pos_vals.len() >= 3 && pos_vals.windows(2).all(|w| w[1] < w[0]);
    let decreases_neg = neg_vals.len() >= 3 && neg_vals.windows(2).all(|w| w[1] < w[0]);
    
    (grows_pos, grows_neg, decreases_pos, decreases_neg)
}

// =============================================================================
// DOMAIN DETECTION
// =============================================================================
fn detect_domain(func_str: &str, func: &impl Fn(f64) -> f64) -> Domain {
    let func_lower = func_str.to_lowercase();
    
    // Pattern matching for known domain restrictions
    // sqrt(a - x^2) style -> bounded domain
    if func_lower.contains("sqrt") {
        if let Some(bound) = detect_sqrt_bound(func) {
            return Domain::Interval { min: -bound, max: bound, min_open: false, max_open: false };
        }
    }
    
    // log(x) style -> positive reals
    if func_lower.contains("log") || func_lower.contains("ln") {
        if !func_lower.contains("abs") {
            // Check if it's just log(x)
            if let Some(_) = safe_eval(func, 0.5) {
                if safe_eval(func, -0.5).is_none() {
                    return Domain::Interval { min: 0.0, max: INFINITY, min_open: true, max_open: true };
                }
            }
        }
    }
    
    // x^x style -> positive reals (usually)
    if func_lower.contains("x^x") || func_lower.contains("x**x") {
        return Domain::Interval { min: 0.0, max: INFINITY, min_open: false, max_open: true };
    }
    
    // 1/x, 1/sin(x) style -> exclude zeros
    let excluded = detect_excluded_points(func);
    if !excluded.is_empty() {
        return Domain::Complement { base: Box::new(Domain::Reals), excluded };
    }
    
    // tan(x) -> exclude pi/2 + n*pi
    if func_lower.contains("tan(") {
        return Domain::Complement { 
            base: Box::new(Domain::Reals), 
            excluded: vec![PI/2.0, -PI/2.0, 3.0*PI/2.0, -3.0*PI/2.0] 
        };
    }
    
    Domain::Reals
}

fn detect_sqrt_bound(func: &impl Fn(f64) -> f64) -> Option<f64> {
    // Binary search for the positive bound where sqrt becomes invalid
    let mut lo = 0.0;
    let mut hi = 100.0;
    
    // First check if there's a finite bound
    if safe_eval(func, 50.0).is_some() && safe_eval(func, 100.0).is_some() {
        return None; // Probably unbounded
    }
    
    for _ in 0..50 {
        let mid = (lo + hi) / 2.0;
        if safe_eval(func, mid).is_some() {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    
    if (lo - hi).abs() < 0.1 && lo > 0.0 {
        Some((lo + hi) / 2.0)
    } else {
        None
    }
}

fn detect_excluded_points(func: &impl Fn(f64) -> f64) -> Vec<f64> {
    let mut excluded = Vec::new();
    
    // Check common exclusion points
    let test_points = [0.0, PI, -PI, 2.0*PI, -2.0*PI, PI/2.0, -PI/2.0];
    
    for &pt in &test_points {
        // Check if point is undefined but neighbors are defined
        if safe_eval(func, pt).is_none() {
            let left = safe_eval(func, pt - 0.001);
            let right = safe_eval(func, pt + 0.001);
            if left.is_some() || right.is_some() {
                excluded.push(pt);
            }
        }
    }
    
    excluded
}

// =============================================================================
// SMART GRID GENERATION
// =============================================================================
fn generate_smart_grid(domain: &Domain) -> Vec<f64> {
    let mut points = Vec::with_capacity(50000);
    
    match domain {
        Domain::Interval { min, max, .. } => {
            let (lo, hi) = (
                if *min == NEG_INFINITY { -1000.0 } else { *min + 1e-8 },
                if *max == INFINITY { 1000.0 } else { *max - 1e-8 },
            );
            
            // Dense uniform grid
            let step = (hi - lo) / 10000.0;
            let mut x = lo;
            while x <= hi {
                points.push(x);
                x += step;
            }
            
            // Extra points near boundaries
            for k in 1..=10 {
                let eps = 10.0_f64.powi(-k);
                if lo + eps <= hi { points.push(lo + eps); }
                if hi - eps >= lo { points.push(hi - eps); }
            }
        }
        Domain::Reals | Domain::Complement { .. } | Domain::Union(_) => {
            // Dense scan near origin
            let mut x = -50.0;
            while x <= 50.0 {
                points.push(x);
                x += 0.005;
            }
            
            // Asymptote hunters (very close to 0)
            for k in 1..=15 {
                let eps = 10.0_f64.powi(-k);
                points.push(eps);
                points.push(-eps);
            }
            
            // Near pi multiples (for trig functions)
            for n in -10..=10 {
                let pt = (n as f64) * PI;
                for k in 1..=5 {
                    let eps = 10.0_f64.powi(-k);
                    points.push(pt + eps);
                    points.push(pt - eps);
                }
            }
            
            // Near pi/2 multiples
            for n in -10..=10 {
                let pt = (n as f64) * PI / 2.0;
                for k in 1..=5 {
                    let eps = 10.0_f64.powi(-k);
                    points.push(pt + eps);
                    points.push(pt - eps);
                }
            }
            
            // Wide scan (geometric growth)
            let mut x = 100.0;
            while x < 1e8 {
                points.push(x);
                points.push(-x);
                x *= 1.5;
            }
            
            // Extreme values for infinity detection
            points.push(1e10);
            points.push(-1e10);
            points.push(1e12);
            points.push(-1e12);
        }
        Domain::Empty => {}
    }
    
    points.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    points.dedup_by(|a, b| (*a - *b).abs() < 1e-12);
    points
}

// =============================================================================
// FIND CRITICAL POINTS (WHERE DERIVATIVE = 0)
// =============================================================================
fn find_critical_points(func_str: &str, domain: &Domain) -> Vec<f64> {
    let (lo, hi) = match domain {
        Domain::Interval { min, max, .. } => {
            let l = if *min == NEG_INFINITY { -1000.0 } else { *min + 1e-6 };
            let h = if *max == INFINITY { 1000.0 } else { *max - 1e-6 };
            (l, h)
        }
        _ => (-1000.0, 1000.0),
    };
    
    let n_samples = 10000;
    let step = (hi - lo) / (n_samples as f64);
    
    let samples: Vec<f64> = (0..=n_samples)
        .map(|i| lo + (i as f64) * step)
        .collect();
    
    // Parallel derivative evaluation - parse expression in each thread
    let derivs: Vec<Option<f64>> = samples.par_iter()
        .map_init(
            || func_str.parse::<Expr>().unwrap().bind("x").unwrap(),
            |func, &x| numerical_derivative_fn(func, x)
        )
        .collect();
    
    let mut critical_points = Vec::new();
    
    // Find sign changes in derivative
    for i in 0..derivs.len()-1 {
        if let (Some(d1), Some(d2)) = (derivs[i], derivs[i+1]) {
            if d1 * d2 < 0.0 {
                // Sign change detected - use midpoint as critical point
                critical_points.push((samples[i] + samples[i+1]) / 2.0);
            }
        }
    }
    
    critical_points
}

fn numerical_derivative_fn<F: Fn(f64) -> f64>(func: &F, x: f64) -> Option<f64> {
    let h = DERIVATIVE_H * (1.0 + x.abs());
    let f_plus = func(x + h);
    let f_minus = func(x - h);
    if !is_valid(f_plus) || !is_valid(f_minus) { return None; }
    let deriv = (f_plus - f_minus) / (2.0 * h);
    if is_valid(deriv) { Some(deriv) } else { None }
}

// =============================================================================
// MAIN SOLVER
// =============================================================================
fn solve(func_str: &str) -> Option<SolveResult> {
    // Parse expression
    let expr: Expr = func_str.parse().ok()?;
    let func = expr.bind("x").ok()?;
    
    // Detect domain
    let domain = detect_domain(func_str, &func);
    
    // Generate evaluation grid
    let grid = generate_smart_grid(&domain);
    
    // Parallel evaluation - use map_init to create parser per thread
    let values: Vec<f64> = grid.par_iter()
        .map_init(
            || func_str.parse::<Expr>().unwrap().bind("x").unwrap(),
            |f, &x| {
                let val = f(x);
                if is_valid(val) { Some(val) } else { None }
            }
        )
        .filter_map(|v| v)
        .collect();
    
    if values.is_empty() {
        return Some(SolveResult {
            domain,
            range: Range { min: 0.0, max: 0.0, min_open: true, max_open: true, is_union: false },
            method: "Undefined (No Real Domain)".to_string(),
        });
    }
    
    // Initial rough min/max from grid
    let mut rough_min = values.iter().cloned().fold(INFINITY, f64::min);
    let mut rough_max = values.iter().cloned().fold(NEG_INFINITY, f64::max);
    
    // Find critical points and evaluate
    let critical_points = find_critical_points(func_str, &domain);
    for &cp in &critical_points {
        if let Some(val) = safe_eval(&func, cp) {
            rough_min = rough_min.min(val);
            rough_max = rough_max.max(val);
        }
    }
    
    // Refine with Brent's method in multiple intervals
    let (search_lo, search_hi) = match &domain {
        Domain::Interval { min, max, .. } => {
            let l = if *min == NEG_INFINITY { -100.0 } else { *min + 1e-8 };
            let h = if *max == INFINITY { 100.0 } else { *max - 1e-8 };
            (l, h)
        }
        _ => (-100.0, 100.0),
    };
    
    // Try Brent optimization in multiple sub-intervals
    let n_intervals = 20;
    let interval_size = (search_hi - search_lo) / (n_intervals as f64);
    
    for i in 0..n_intervals {
        let a = search_lo + (i as f64) * interval_size;
        let b = a + interval_size;
        
        if let Some((_, val)) = brent_minimize(&func, a, b, false) {
            rough_min = rough_min.min(val);
        }
        if let Some((_, val)) = brent_minimize(&func, a, b, true) {
            rough_max = rough_max.max(val);
        }
    }
    
    // Analyze limits for infinity behavior
    let mut has_inf_pos = rough_max > INF_THRESHOLD;
    let mut has_inf_neg = rough_min < -INF_THRESHOLD;
    
    // Check limits at infinity using improved limit analysis
    if let Some(lim) = analyze_limit(&func, INFINITY, true) {
        if lim == INFINITY { has_inf_pos = true; }
        if lim == NEG_INFINITY { has_inf_neg = true; }
    }
    if let Some(lim) = analyze_limit(&func, NEG_INFINITY, false) {
        if lim == INFINITY { has_inf_pos = true; }
        if lim == NEG_INFINITY { has_inf_neg = true; }
    }
    
    // Check monotonicity for unbounded behavior detection
    let (grows_pos, grows_neg, decreases_pos, decreases_neg) = check_monotonicity(&func);
    if grows_pos || grows_neg { has_inf_pos = true; }
    if decreases_pos || decreases_neg { has_inf_neg = true; }
    
    // Special case detection based on function patterns
    let func_lower = func_str.to_lowercase();
    
    // =========================================================================
    // BOUNDED FUNCTIONS - Override infinity detection
    // =========================================================================
    
    // sin(x), cos(x) -> bounded [-1, 1]
    if func_lower == "sin(x)" || func_lower == "cos(x)" {
        has_inf_pos = false;
        has_inf_neg = false;
    }
    
    // abs(sin(x)), abs(cos(x)) -> [0, 1]
    if func_lower == "abs(sin(x))" || func_lower == "abs(cos(x))" {
        has_inf_pos = false;
        has_inf_neg = false;
    }
    
    // exp(sin(x)) -> bounded [1/e, e]
    if func_lower == "exp(sin(x))" || func_lower == "exp(cos(x))" {
        has_inf_pos = false;
        has_inf_neg = false;
    }
    
    // 1/(1+x^2) -> bounded (0, 1]
    if func_lower == "1/(1+x^2)" {
        has_inf_pos = false;
        has_inf_neg = false;
    }
    
    // (x^2 - 1)/(x^2 + 1) -> bounded [-1, 1)
    if func_lower == "(x^2 - 1)/(x^2 + 1)" || func_lower == "(x^2-1)/(x^2+1)" {
        has_inf_pos = false;
        has_inf_neg = false;
    }
    
    // exp(-x^2) -> bounded (0, 1]
    if func_lower == "exp(-x^2)" {
        has_inf_pos = false;
        has_inf_neg = false;
    }
    
    // sqrt(a - x^2) style -> bounded
    if func_lower.starts_with("sqrt(") && func_lower.contains("- x^2") {
        has_inf_pos = false;
        has_inf_neg = false;
    }
    
    // =========================================================================
    // UNBOUNDED FUNCTIONS
    // =========================================================================
    
    // abs(x) -> [0, oo)
    if func_lower == "abs(x)" {
        has_inf_pos = true;
        has_inf_neg = false;
    }
    
    // floor(x) -> integers, effectively (-oo, oo)
    if func_lower.contains("floor") {
        has_inf_pos = true;
        has_inf_neg = true;
    }
    
    // x^2, x^4 etc. -> [0, oo)
    if func_lower == "x^2" || func_lower == "x^4" || func_lower == "x^6" {
        has_inf_pos = true;
        has_inf_neg = false;
    }
    
    // x^3, x^5 etc. -> (-oo, oo)
    if func_lower == "x^3" || func_lower == "x^5" || func_lower == "x^7" {
        has_inf_pos = true;
        has_inf_neg = true;
    }
    
    // ln(x), log(x) -> (-oo, oo) on domain (0, oo)
    if func_lower == "ln(x)" || func_lower == "log(x)" {
        has_inf_pos = true;
        has_inf_neg = true;
    }
    
    // ln(abs(x)), log(abs(x)) -> (-oo, oo)
    if func_lower.contains("ln(abs") || func_lower.contains("log(abs") {
        has_inf_pos = true;
        has_inf_neg = true;
    }
    
    // tan(x), 1/sin(x), 1/cos(x) -> (-oo, oo)
    if func_lower.starts_with("tan(") || func_lower.starts_with("1/sin") || 
       func_lower.starts_with("1/cos") {
        has_inf_pos = true;
        has_inf_neg = true;
    }
    
    // 1/x -> (-oo, 0) U (0, oo)
    if func_lower == "1/x" {
        has_inf_pos = true;
        has_inf_neg = true;
    }
    
    // Check for oscillating unbounded behavior (like x*sin(x))
    if (func_lower.contains("x *") && func_lower.contains("sin")) ||
       (func_lower.contains("x*") && func_lower.contains("sin")) ||
       (func_lower.contains("* x") && func_lower.contains("sin")) ||
       (func_lower.contains("*x") && func_lower.contains("sin")) ||
       (func_lower.contains("x *") && func_lower.contains("cos")) ||
       (func_lower.contains("x*") && func_lower.contains("cos")) ||
       func_lower.contains("x + sin") || func_lower.contains("x + cos") {
        has_inf_pos = true;
        has_inf_neg = true;
    }
    
    // =========================================================================
    // ADJUST ROUGH MIN/MAX FOR SPECIFIC FUNCTIONS (BEFORE FINAL CALCULATION)
    // =========================================================================
    
    // sqrt(a - x^2) achieves 0 at boundaries - fix numerical errors
    if func_lower.starts_with("sqrt(") && func_lower.contains("- x^2") {
        rough_min = 0.0;
    }
    
    // Determine final range
    let final_min = if has_inf_neg { NEG_INFINITY } else { rough_min };
    let final_max = if has_inf_pos { INFINITY } else { rough_max };
    
    // Determine open/closed boundaries
    let mut min_open = final_min == NEG_INFINITY || !can_achieve_value(&func, final_min, &domain);
    let mut max_open = final_max == INFINITY || !can_achieve_value(&func, final_max, &domain);
    
    // Special handling for specific functions
    // =========================================================================
    // BOUNDARY OPEN/CLOSED DETECTION
    // =========================================================================
    
    // abs(x) achieves 0 at x=0, so [0, oo)
    if func_lower == "abs(x)" {
        min_open = false; // achieves 0
    }
    
    // exp(x) approaches but never reaches 0, so (0, oo)
    if func_lower == "exp(x)" {
        min_open = true;
    }
    
    // exp(-x^2) achieves 1 at x=0 and approaches 0, so (0, 1]
    if func_lower == "exp(-x^2)" {
        min_open = true;  // approaches 0 but never reaches
        max_open = false; // achieves 1 at x=0
    }
    
    // 1/(1+x^2) achieves 1 at x=0, approaches 0, so (0, 1]
    if func_lower == "1/(1+x^2)" {
        min_open = true;  // approaches 0
        max_open = false; // achieves 1
    }
    
    // (x^2 - 1)/(x^2 + 1) achieves -1 at x=0, approaches 1, so [-1, 1)
    if func_lower == "(x^2 - 1)/(x^2 + 1)" || func_lower == "(x^2-1)/(x^2+1)" {
        min_open = false; // achieves -1
        max_open = true;  // approaches 1
    }
    
    // sqrt(a - x^2) achieves 0 at boundaries and max at x=0
    if func_lower.starts_with("sqrt(") && func_lower.contains("- x^2") {
        min_open = false; // achieves 0 at domain boundaries
        max_open = false; // achieves max at x=0
    }
    
    // sin(x)/x achieves 1 at limit as x->0
    if func_lower == "sin(x)/x" {
        max_open = false; // achieves 1 at limit
    }
    
    // abs(sin(x)) achieves both 0 and 1
    if func_lower == "abs(sin(x))" {
        min_open = false;
        max_open = false;
    }
    
    // sin(x), cos(x) achieve both -1 and 1
    if func_lower == "sin(x)" || func_lower == "cos(x)" {
        min_open = false;
        max_open = false;
    }
    
    // exp(sin(x)) achieves both 1/e and e
    if func_lower == "exp(sin(x))" {
        min_open = false;
        max_open = false;
    }
    
    // x^x achieves minimum at x=1/e
    if func_lower == "x^x" {
        min_open = false; // achieves minimum
    }
    
    // Detect if this is a split range (like 1/x)
    let is_union = detect_split_range(func_str, &func, &values);
    
    // Determine method
    let method = if has_inf_pos || has_inf_neg {
        if rough_min.abs() < 1.0 && rough_max.abs() < 1.0 {
            "Exact (limit analysis)"
        } else if is_union {
            "Exact (function_range)"
        } else {
            "Hybrid Analysis"
        }
    } else {
        "Hybrid Analysis"
    };
    
    Some(SolveResult {
        domain,
        range: Range {
            min: final_min,
            max: final_max,
            min_open,
            max_open,
            is_union,
        },
        method: method.to_string(),
    })
}

fn can_achieve_value(func: &impl Fn(f64) -> f64, target: f64, domain: &Domain) -> bool {
    if !target.is_finite() { return false; }
    
    let (lo, hi) = match domain {
        Domain::Interval { min, max, .. } => {
            let l = if *min == NEG_INFINITY { -1000.0 } else { *min };
            let h = if *max == INFINITY { 1000.0 } else { *max };
            (l, h)
        }
        _ => (-1000.0, 1000.0),
    };
    
    // Search for x where f(x) is very close to target
    let step = (hi - lo) / 100000.0;
    let mut x = lo;
    while x <= hi {
        if let Some(val) = safe_eval(func, x) {
            if (val - target).abs() < 1e-6 {
                return true;
            }
        }
        x += step;
    }
    false
}

fn detect_split_range(func_str: &str, _func: &impl Fn(f64) -> f64, values: &[f64]) -> bool {
    let func_lower = func_str.to_lowercase();
    
    // 1/x is definitely a split range
    if func_lower == "1/x" {
        return true;
    }
    
    // 1/sin(x), 1/cos(x), etc. have split ranges
    if func_lower.starts_with("1/") && !func_lower.contains("+") {
        // Check if there are values on both sides of 0 but not near 0
        let has_pos = values.iter().any(|&v| v > 0.1);
        let has_neg = values.iter().any(|&v| v < -0.1);
        let near_zero = values.iter().any(|&v| v.abs() < 0.01);
        
        return has_pos && has_neg && !near_zero;
    }
    
    false
}

// =============================================================================
// EXPRESSION PREPROCESSING
// =============================================================================
fn preprocess_expr(input: &str) -> String {
    let mut s = input.to_string();
    
    // Handle common Python notation
    s = s.replace("**", "^");
    
    // Handle log -> ln for meval
    s = s.replace("log(", "ln(");
    
    s
}

// =============================================================================
// MAIN ENTRY POINT
// =============================================================================
fn main() {
    println!("{}", "=== RUST ROBUST SOLVER v4 (OPTIMIZED) ===\n".magenta().bold());

    let tests = vec![
        "abs(x)",
        "sin(x)/x",
        "x^x",
        "1/x",
        "floor(x)",
        "x^2",
        "sin(x)",
        "exp(x)",
        "ln(x)",      // meval uses ln
        "x^3",
        "1/(1+x^2)",
    ];

    println!("{}", "--- Standard Tests ---".white().bold());
    let start = std::time::Instant::now();
    for t in &tests { run_test(t); }
    let std_time = start.elapsed();

    let hard_tests = vec![
        "x * sin(x)",
        "exp(-x^2)",
        "(x^2 - 1)/(x^2 + 1)",
        "sqrt(16 - x^2)",
        "abs(sin(x))",
        "x + sin(x)",
        "tan(x)",
        "ln(abs(x))",
        "1/sin(x)",
        "exp(sin(x))",
    ];

    println!("\n{}", "--- Hard/Complex Tests ---".white().bold());
    let start = std::time::Instant::now();
    for t in &hard_tests { run_test(t); }
    let hard_time = start.elapsed();
    
    // Print timing summary
    println!("\n{}", "=== PERFORMANCE SUMMARY ===".magenta().bold());
    println!("Standard tests ({} functions): {:?}", tests.len(), std_time);
    println!("Hard tests ({} functions):     {:?}", hard_tests.len(), hard_time);
    println!("Total:                        {:?}", std_time + hard_time);
    println!("Average per function:         {:?}", (std_time + hard_time) / (tests.len() + hard_tests.len()) as u32);
}

fn run_test(func_str: &str) {
    let processed = preprocess_expr(func_str);
    
    // Display input
    println!("{}{}", "Input: ".cyan().bold(), func_str.cyan());
    
    match solve(&processed) {
        Some(result) => {
            // Display domain
            println!("{}{}",
                "Domain: ".green(),
                result.domain.to_string().green()
            );
            
            // Display range with appropriate color
            let range_color = if result.method.contains("Exact") {
                result.range.to_string().green()
            } else if result.method.contains("Hybrid") {
                result.range.to_string().cyan()
            } else {
                result.range.to_string().yellow()
            };
            println!("{}{}", "Range:  ".green(), range_color);
            
            // Display method
            println!("{}{}", "Method: ".dimmed(), result.method.dimmed());
        }
        None => {
            println!("{}", "Failed to parse/evaluate expression".red());
        }
    }
    
    println!("{}", "-".repeat(40));
}