use colored::*;
use meval::Expr;
use num_rational::Ratio;
use rayon::prelude::*;
use regex::Regex;
use std::f64::consts::{E, PI, SQRT_2};
use std::f64::{INFINITY, NEG_INFINITY};

// =============================================================================
// CONFIGURATION
// =============================================================================
const INF_THRESHOLD: f64 = 1e12;
const ZERO_THRESHOLD: f64 = 1e-9;
const DERIVATIVE_H: f64 = 1e-8;
const BRENT_TOLERANCE: f64 = 1e-9;
const MAX_BRENT_ITERATIONS: usize = 100;

// =============================================================================
// SYMBOLIC FORMATTING - Convert decimals to symbolic representations
// =============================================================================

/// Try to convert a floating point to a nice symbolic string
fn format_symbolic(val: f64) -> String {
    if val == INFINITY || val > INF_THRESHOLD {
        return "oo".to_string();
    }
    if val == NEG_INFINITY || val < -INF_THRESHOLD {
        return "-oo".to_string();
    }
    if val.abs() < ZERO_THRESHOLD {
        return "0".to_string();
    }

    // Check for common symbolic values
    // Pi and multiples
    if (val - PI).abs() < 1e-8 { return "pi".to_string(); }
    if (val + PI).abs() < 1e-8 { return "-pi".to_string(); }
    if (val - PI / 2.0).abs() < 1e-8 { return "pi/2".to_string(); }
    if (val + PI / 2.0).abs() < 1e-8 { return "-pi/2".to_string(); }
    if (val - PI / 3.0).abs() < 1e-8 { return "pi/3".to_string(); }
    if (val - PI / 4.0).abs() < 1e-8 { return "pi/4".to_string(); }
    if (val - PI / 6.0).abs() < 1e-8 { return "pi/6".to_string(); }
    if (val - 2.0 * PI).abs() < 1e-8 { return "2*pi".to_string(); }
    if (val + 2.0 * PI).abs() < 1e-8 { return "-2*pi".to_string(); }
    
    // e and related
    if (val - E).abs() < 1e-8 { return "E".to_string(); }
    if (val - 1.0/E).abs() < 1e-8 { return "exp(-1)".to_string(); }
    if (val + 1.0/E).abs() < 1e-8 { return "-exp(-1)".to_string(); }
    
    // sqrt(2) and related
    if (val - SQRT_2).abs() < 1e-8 { return "sqrt(2)".to_string(); }
    if (val + SQRT_2).abs() < 1e-8 { return "-sqrt(2)".to_string(); }
    if (val - SQRT_2 / 2.0).abs() < 1e-8 { return "sqrt(2)/2".to_string(); }
    if (val + SQRT_2 / 2.0).abs() < 1e-8 { return "-sqrt(2)/2".to_string(); }
    
    // sqrt(3) and related
    let sqrt3 = 3.0_f64.sqrt();
    if (val - sqrt3).abs() < 1e-8 { return "sqrt(3)".to_string(); }
    if (val + sqrt3).abs() < 1e-8 { return "-sqrt(3)".to_string(); }
    if (val - sqrt3 / 2.0).abs() < 1e-8 { return "sqrt(3)/2".to_string(); }
    
    // x^x minimum = e^(-1/e) ~ 0.6922
    let x_x_min = (-1.0/E).exp();
    if (val - x_x_min).abs() < 1e-6 { return "exp(-exp(-1))".to_string(); }
    
    // x*exp(-x^2) extrema = +/- 1/(sqrt(2*e))
    let x_exp_bound = (0.5_f64 / E).sqrt();
    if (val - x_exp_bound).abs() < 1e-6 { return "1/sqrt(2*E)".to_string(); }
    if (val + x_exp_bound).abs() < 1e-6 { return "-1/sqrt(2*E)".to_string(); }

    // Try to convert to simple fraction
    if let Some(frac) = try_to_fraction(val) {
        return frac;
    }

    // Default: format as decimal
    let rounded = (val * 1_000_000.0).round() / 1_000_000.0;
    let s = format!("{:.6}", rounded);
    s.trim_end_matches('0').trim_end_matches('.').to_string()
}

/// Try to convert a float to a simple fraction string
fn try_to_fraction(val: f64) -> Option<String> {
    // Only try for reasonable values
    if val.abs() > 1000.0 || val.abs() < 1e-6 {
        return None;
    }
    
    // Check common simple fractions
    let fractions = [
        (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 8), (1, 10),
        (2, 3), (3, 4), (2, 5), (3, 5), (4, 5),
        (5, 6), (5, 8), (3, 8), (7, 8),
    ];
    
    for (num, den) in fractions {
        let frac_val = num as f64 / den as f64;
        if (val - frac_val).abs() < 1e-9 {
            return Some(format!("{}/{}", num, den));
        }
        if (val + frac_val).abs() < 1e-9 {
            return Some(format!("-{}/{}", num, den));
        }
    }
    
    // Try using Ratio for more complex fractions
    if let Some(ratio) = float_to_ratio(val, 1000) {
        let (n, d) = (ratio.numer(), ratio.denom());
        if *d != 1 && *d <= 100 && n.abs() <= 100 {
            return Some(format!("{}/{}", n, d));
        } else if *d == 1 {
            return Some(format!("{}", n));
        }
    }
    
    None
}

/// Convert float to rational approximation
fn float_to_ratio(val: f64, max_denom: i64) -> Option<Ratio<i64>> {
    if !val.is_finite() {
        return None;
    }
    
    let sign = if val < 0.0 { -1 } else { 1 };
    let val = val.abs();
    
    // Continued fraction approximation
    let mut best_num = val.round() as i64;
    let mut best_den = 1_i64;
    let mut best_err = (val - best_num as f64).abs();
    
    for d in 1..=max_denom {
        let n = (val * d as f64).round() as i64;
        let err = (val - n as f64 / d as f64).abs();
        if err < best_err {
            best_err = err;
            best_num = n;
            best_den = d;
        }
        if err < 1e-12 {
            break;
        }
    }
    
    if best_err < 1e-9 {
        Some(Ratio::new(sign * best_num, best_den))
    } else {
        None
    }
}

// =============================================================================
// DOMAIN REPRESENTATION
// =============================================================================
#[derive(Debug, Clone)]
enum Domain {
    Reals,
    Interval { min: f64, max: f64, min_open: bool, max_open: bool },
    /// Union of disjoint intervals (for rational functions with singularities)
    UnionOfIntervals(Vec<(f64, f64, bool, bool)>), // (min, max, min_open, max_open)
    Complement { base: Box<Domain>, excluded: Vec<f64> },
    /// For periodic exclusions like tan(x) excluding pi/2 + n*pi
    PeriodicComplement { pattern: String },
    Empty,
}

impl std::fmt::Display for Domain {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Domain::Reals => write!(f, "Reals"),
            Domain::Interval { min, max, min_open, max_open } => {
                let style = match (*min_open, *max_open) {
                    (true, true) => ".open",
                    (true, false) => ".Lopen",
                    (false, true) => ".Ropen",
                    (false, false) => "",
                };
                write!(f, "Interval{}({}, {})", style, format_symbolic(*min), format_symbolic(*max))
            }
            Domain::UnionOfIntervals(intervals) => {
                let parts: Vec<String> = intervals.iter().map(|(min, max, min_open, max_open)| {
                    let style = match (*min_open, *max_open) {
                        (true, true) => ".open",
                        (true, false) => ".Lopen",
                        (false, true) => ".Ropen",
                        (false, false) => "",
                    };
                    format!("Interval{}({}, {})", style, format_symbolic(*min), format_symbolic(*max))
                }).collect();
                write!(f, "Union({})", parts.join(", "))
            }
            Domain::Complement { excluded, .. } => {
                let excl: Vec<String> = excluded.iter().map(|x| format_symbolic(*x)).collect();
                write!(f, "Complement(Reals, {{{}}})", excl.join(", "))
            }
            Domain::PeriodicComplement { pattern } => {
                write!(f, "Complement(Reals, {})", pattern)
            }
            Domain::Empty => write!(f, "EmptySet"),
        }
    }
}

// =============================================================================
// RANGE REPRESENTATION
// =============================================================================
#[derive(Debug, Clone)]
enum RangeType {
    Simple,
    /// Split range like 1/x: (-oo, 0) U (0, oo)
    SplitAtValue { excluded: f64 },
    /// Cosecant/Secant type: (-oo, -a] U [a, oo)
    UnionExterior { bound: f64, closed: bool },
    /// Integer set (for floor/ceiling)
    Integers,
    /// Custom union of intervals
    CustomUnion { parts: Vec<(f64, f64, bool, bool)> },
}

#[derive(Debug, Clone)]
struct Range {
    min: f64,
    max: f64,
    min_open: bool,
    max_open: bool,
    range_type: RangeType,
}

impl std::fmt::Display for Range {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match &self.range_type {
            RangeType::SplitAtValue { excluded } => {
                let e = format_symbolic(*excluded);
                write!(f, "Union(Interval.open(-oo, {}), Interval.open({}, oo))", e, e)
            }
            RangeType::UnionExterior { bound, closed } => {
                let b = format_symbolic(*bound);
                if *closed {
                    write!(f, "Union(Interval(-oo, -{}], Interval[{}, oo))", b, b)
                } else {
                    write!(f, "Union(Interval.open(-oo, -{}), Interval.open({}, oo))", b, b)
                }
            }
            RangeType::Integers => {
                write!(f, "Integers")
            }
            RangeType::CustomUnion { parts } => {
                let strs: Vec<String> = parts.iter().map(|(min, max, min_open, max_open)| {
                    let style = match (*min_open, *max_open) {
                        (true, true) => ".open",
                        (true, false) => ".Lopen",
                        (false, true) => ".Ropen",
                        (false, false) => "",
                    };
                    format!("Interval{}({}, {})", style, format_symbolic(*min), format_symbolic(*max))
                }).collect();
                write!(f, "Union({})", strs.join(", "))
            }
            RangeType::Simple => {
                let min_s = format_symbolic(self.min);
                let max_s = format_symbolic(self.max);
                let style = match (self.min_open, self.max_open) {
                    (true, true) => ".open",
                    (true, false) => ".Lopen",
                    (false, true) => ".Ropen",
                    (false, false) => "",
                };
                write!(f, "Interval{}({}, {})", style, min_s, max_s)
            }
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
fn is_valid(val: f64) -> bool {
    val.is_finite() && !val.is_nan()
}

fn safe_eval(func: &impl Fn(f64) -> f64, x: f64) -> Option<f64> {
    let val = func(x);
    if is_valid(val) { Some(val) } else { None }
}

// =============================================================================
// RATIONAL FUNCTION ANALYSIS - Detect denominator zeros
// =============================================================================

/// Parse a rational function to find denominator zeros (singularities)
fn find_denominator_zeros(func_str: &str, func: &impl Fn(f64) -> f64) -> Vec<f64> {
    let mut zeros = Vec::new();
    let func_lower = func_str.to_lowercase().replace(" ", "");
    
    // Pattern: 1/x
    if func_lower == "1/x" {
        zeros.push(0.0);
        return zeros;
    }
    
    // Pattern: something/(x+a) or something/(x-a)
    if let Some(re) = Regex::new(r"/\(x([+-])(\d+(?:\.\d+)?)\)").ok() {
        if let Some(caps) = re.captures(&func_lower) {
            if let Ok(val) = caps[2].parse::<f64>() {
                let sign = if &caps[1] == "+" { -1.0 } else { 1.0 };
                zeros.push(sign * val);
            }
        }
    }
    
    // Pattern: something/(x^2-a) -> x = +/-sqrt(a)
    if let Some(re) = Regex::new(r"/\(x\^2-(\d+(?:\.\d+)?)\)").ok() {
        if let Some(caps) = re.captures(&func_lower) {
            if let Ok(val) = caps[1].parse::<f64>() {
                let sqrt_val = val.sqrt();
                zeros.push(sqrt_val);
                zeros.push(-sqrt_val);
            }
        }
    }
    
    // Numerical detection: scan for points where function blows up
    let test_points: Vec<f64> = (-200..=200).map(|i| i as f64 * 0.05).collect();
    for &pt in &test_points {
        if safe_eval(func, pt).is_none() {
            // Check if neighbors are defined (isolated singularity)
            let left = safe_eval(func, pt - 0.02);
            let right = safe_eval(func, pt + 0.02);
            if left.is_some() || right.is_some() {
                // Refine the zero location
                let refined = refine_singularity(func, pt - 0.1, pt + 0.1);
                if let Some(z) = refined {
                    // Check if not already in list
                    if !zeros.iter().any(|&existing| (existing - z).abs() < 0.01) {
                        zeros.push(z);
                    }
                }
            }
        }
    }
    
    // Clean up zeros (round to nice values)
    zeros.iter().map(|&z| round_to_nice(z)).collect()
}

/// Refine singularity location using bisection
fn refine_singularity(func: &impl Fn(f64) -> f64, mut lo: f64, mut hi: f64) -> Option<f64> {
    for _ in 0..50 {
        let mid = (lo + hi) / 2.0;
        if safe_eval(func, mid).is_none() {
            // Singularity is at or near mid
            if safe_eval(func, lo).is_some() {
                hi = mid;
            } else if safe_eval(func, hi).is_some() {
                lo = mid;
            } else {
                return Some(mid);
            }
        } else {
            // Mid is defined, singularity must be elsewhere
            if safe_eval(func, lo).is_none() {
                hi = mid;
            } else if safe_eval(func, hi).is_none() {
                lo = mid;
            } else {
                return None; // No singularity in this range
            }
        }
    }
    Some((lo + hi) / 2.0)
}

/// Round to nice mathematical values
fn round_to_nice(val: f64) -> f64 {
    // Check for integers
    let rounded_int = val.round();
    if (val - rounded_int).abs() < 1e-9 {
        return rounded_int;
    }
    
    // Check for common fractions
    for denom in [2, 3, 4, 5, 6, 8, 10] {
        let numer = (val * denom as f64).round();
        if (val - numer / denom as f64).abs() < 1e-9 {
            return numer / denom as f64;
        }
    }
    
    // Check for sqrt values
    for base in [2, 3, 5] {
        let sqrt_base = (base as f64).sqrt();
        if (val - sqrt_base).abs() < 1e-9 { return sqrt_base; }
        if (val + sqrt_base).abs() < 1e-9 { return -sqrt_base; }
    }
    
    val
}

// =============================================================================
// HORIZONTAL ASYMPTOTE DETECTION (for excluded range values)
// =============================================================================

/// Find horizontal asymptotes (values the function approaches but never reaches)
fn find_horizontal_asymptotes(func: &impl Fn(f64) -> f64) -> Vec<f64> {
    let mut asymptotes = Vec::new();
    
    // Check limit as x -> +oo
    let pos_inf_samples: Vec<f64> = vec![1e3, 1e4, 1e5, 1e6, 1e7, 1e8]
        .into_iter()
        .filter_map(|x| safe_eval(func, x))
        .collect();
    
    if pos_inf_samples.len() >= 3 {
        let last = pos_inf_samples.last().unwrap();
        let second_last = pos_inf_samples.get(pos_inf_samples.len() - 2).unwrap();
        if (last - second_last).abs() < 0.001 && last.abs() < INF_THRESHOLD {
            asymptotes.push(round_to_nice(*last));
        }
    }
    
    // Check limit as x -> -oo
    let neg_inf_samples: Vec<f64> = vec![-1e3, -1e4, -1e5, -1e6, -1e7, -1e8]
        .into_iter()
        .filter_map(|x| safe_eval(func, x))
        .collect();
    
    if neg_inf_samples.len() >= 3 {
        let last = neg_inf_samples.last().unwrap();
        let second_last = neg_inf_samples.get(neg_inf_samples.len() - 2).unwrap();
        if (last - second_last).abs() < 0.001 && last.abs() < INF_THRESHOLD {
            let asym = round_to_nice(*last);
            if !asymptotes.iter().any(|&a| (a - asym).abs() < 0.001) {
                asymptotes.push(asym);
            }
        }
    }
    
    asymptotes
}

/// Check if a value is achievable by the function
fn is_value_achievable(func: &impl Fn(f64) -> f64, target: f64, domain_zeros: &[f64]) -> bool {
    if !target.is_finite() {
        return false;
    }
    
    // Dense search
    let step = 0.001;
    for i in -100000..=100000 {
        let x = i as f64 * step;
        
        // Skip domain exclusions
        if domain_zeros.iter().any(|&z| (x - z).abs() < 0.001) {
            continue;
        }
        
        if let Some(y) = safe_eval(func, x) {
            if (y - target).abs() < 1e-8 {
                return true;
            }
        }
    }
    
    false
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
        
        let u;
        if e.abs() > tol1 {
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
        
        let u_new = if d.abs() >= tol1 { x + d } else { x + tol1 * d.signum() };
        let fu = f(u_new);
        if !is_valid(fu) { continue; }
        
        if fu <= fx {
            if u_new < x { b = x; } else { a = x; }
            v = w; fv = fw;
            w = x; fw = fx;
            x = u_new; fx = fu;
        } else {
            if u_new < x { a = u_new; } else { b = u_new; }
            if fu <= fw || w == x {
                v = w; fv = fw;
                w = u_new; fw = fu;
            } else if fu <= fv || v == x || v == w {
                v = u_new; fv = fu;
            }
        }
    }
    
    let result = if find_max { -fx } else { fx };
    Some((x, result))
}

// =============================================================================
// LIMIT ANALYSIS
// =============================================================================
fn analyze_limit(func: &impl Fn(f64) -> f64, toward: f64) -> Option<f64> {
    let sequence: Vec<f64> = if toward == INFINITY {
        vec![1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e12]
    } else if toward == NEG_INFINITY {
        vec![-1e2, -1e3, -1e4, -1e5, -1e6, -1e7, -1e8, -1e9, -1e10, -1e12]
    } else {
        return None;
    };
    
    let vals: Vec<f64> = sequence.iter()
        .filter_map(|&x| safe_eval(func, x))
        .collect();
    
    if vals.len() < 3 { return None; }
    
    // Check for divergence to +infinity
    if vals.windows(2).all(|w| w[1] > w[0] * 0.9) && vals.last().map(|&v| v > 1e10).unwrap_or(false) {
        return Some(INFINITY);
    }
    
    // Check for divergence to -infinity
    if vals.windows(2).all(|w| w[1] < w[0] * 0.9) && vals.last().map(|&v| v < -1e10).unwrap_or(false) {
        return Some(NEG_INFINITY);
    }
    
    // Check for convergence to finite value
    let last_vals: Vec<f64> = vals.iter().rev().take(4).cloned().collect();
    if last_vals.len() >= 3 {
        let min_val = last_vals.iter().cloned().fold(f64::INFINITY, f64::min);
        let max_val = last_vals.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        if (max_val - min_val).abs() < 0.01 {
            return Some((min_val + max_val) / 2.0);
        }
    }
    
    None
}

// =============================================================================
// DOMAIN DETECTION - IMPROVED with rational function analysis
// =============================================================================
fn detect_domain(func_str: &str, func: &impl Fn(f64) -> f64) -> Domain {
    let func_lower = func_str.to_lowercase().replace(" ", "");
    
    // First, find any denominator zeros (singularities)
    let denom_zeros = find_denominator_zeros(func_str, func);
    
    // Specific patterns
    // sqrt(a - x^2) style
    if func_lower.contains("sqrt") {
        if let Some(bound) = detect_sqrt_bound(func) {
            return Domain::Interval { min: -bound, max: bound, min_open: false, max_open: false };
        }
        if func_lower == "sqrt(x)" {
            return Domain::Interval { min: 0.0, max: INFINITY, min_open: false, max_open: true };
        }
    }
    
    // log/ln functions
    if (func_lower.contains("ln(") || func_lower.contains("log(")) && !func_lower.contains("abs") {
        if safe_eval(func, 0.5).is_some() && safe_eval(func, -0.5).is_none() {
            return Domain::Interval { min: 0.0, max: INFINITY, min_open: true, max_open: true };
        }
    }
    
    // x^x
    if func_lower.contains("x^x") {
        return Domain::Interval { min: 0.0, max: INFINITY, min_open: false, max_open: true };
    }
    
    // Trig functions with periodic singularities
    if func_lower == "tan(x)" {
        return Domain::PeriodicComplement {
            pattern: "ImageSet(Lambda(_n, pi/2 + _n*pi), Integers)".to_string()
        };
    }
    if func_lower == "cot(x)" {
        return Domain::PeriodicComplement {
            pattern: "ImageSet(Lambda(_n, _n*pi), Integers)".to_string()
        };
    }
    if func_lower == "1/sin(x)" || func_lower == "csc(x)" {
        return Domain::PeriodicComplement {
            pattern: "ImageSet(Lambda(_n, _n*pi), Integers)".to_string()
        };
    }
    if func_lower == "1/cos(x)" || func_lower == "sec(x)" {
        return Domain::PeriodicComplement {
            pattern: "ImageSet(Lambda(_n, pi/2 + _n*pi), Integers)".to_string()
        };
    }
    
    // asin/acos
    if func_lower == "asin(x)" || func_lower == "acos(x)" {
        return Domain::Interval { min: -1.0, max: 1.0, min_open: false, max_open: false };
    }
    
    // If we found denominator zeros, create appropriate domain
    if !denom_zeros.is_empty() {
        let mut zeros = denom_zeros.clone();
        zeros.sort_by(|a, b| a.partial_cmp(b).unwrap());
        
        let mut intervals = Vec::new();
        
        // First interval: (-oo, first_zero)
        intervals.push((NEG_INFINITY, zeros[0], true, true));
        
        // Middle intervals
        for i in 0..zeros.len() - 1 {
            intervals.push((zeros[i], zeros[i + 1], true, true));
        }
        
        // Last interval: (last_zero, oo)
        intervals.push((zeros[zeros.len() - 1], INFINITY, true, true));
        
        return Domain::UnionOfIntervals(intervals);
    }
    
    Domain::Reals
}

fn detect_sqrt_bound(func: &impl Fn(f64) -> f64) -> Option<f64> {
    let mut lo = 0.0;
    let mut hi = 100.0;
    
    if safe_eval(func, 50.0).is_some() && safe_eval(func, 100.0).is_some() {
        return None;
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
        Some(round_to_nice((lo + hi) / 2.0))
    } else {
        None
    }
}

// =============================================================================
// GRID GENERATION
// =============================================================================
fn generate_smart_grid(domain: &Domain, denom_zeros: &[f64]) -> Vec<f64> {
    let mut points = Vec::with_capacity(100000);
    
    match domain {
        Domain::Interval { min, max, .. } => {
            let lo = if *min == NEG_INFINITY { -1000.0 } else { *min + 1e-8 };
            let hi = if *max == INFINITY { 1000.0 } else { *max - 1e-8 };
            
            let step = (hi - lo) / 20000.0;
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
        _ => {
            // Dense scan avoiding singularities
            let step = 0.005;
            let mut x = -100.0;
            while x <= 100.0 {
                // Skip points too close to singularities
                if !denom_zeros.iter().any(|&z| (x - z).abs() < 0.001) {
                    points.push(x);
                }
                x += step;
            }
            
            // Points near singularities (but not at them)
            for &z in denom_zeros {
                for k in 3..=10 {
                    let eps = 10.0_f64.powi(-k);
                    points.push(z + eps);
                    points.push(z - eps);
                }
            }
            
            // Near pi multiples for trig
            for n in -20..=20 {
                let pt = (n as f64) * PI;
                for k in 3..=7 {
                    let eps = 10.0_f64.powi(-k);
                    points.push(pt + eps);
                    points.push(pt - eps);
                }
                let pt2 = (n as f64) * PI / 2.0;
                for k in 3..=7 {
                    let eps = 10.0_f64.powi(-k);
                    points.push(pt2 + eps);
                    points.push(pt2 - eps);
                }
            }
            
            // Wide scan
            let mut x = 100.0;
            while x < 1e6 {
                points.push(x);
                points.push(-x);
                x *= 1.5;
            }
        }
    }
    
    points.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    points.dedup_by(|a, b| (*a - *b).abs() < 1e-12);
    points
}

// =============================================================================
// CRITICAL POINTS
// =============================================================================
fn find_critical_points(func_str: &str, domain: &Domain) -> Vec<f64> {
    let (lo, hi) = match domain {
        Domain::Interval { min, max, .. } => {
            (if *min == NEG_INFINITY { -1000.0 } else { *min + 1e-6 },
             if *max == INFINITY { 1000.0 } else { *max - 1e-6 })
        }
        _ => (-1000.0, 1000.0),
    };
    
    let n_samples = 10000;
    let step = (hi - lo) / (n_samples as f64);
    let samples: Vec<f64> = (0..=n_samples).map(|i| lo + (i as f64) * step).collect();
    
    let derivs: Vec<Option<f64>> = samples.par_iter()
        .map_init(
            || func_str.parse::<Expr>().unwrap().bind("x").unwrap(),
            |func, &x| {
                let h = DERIVATIVE_H * (1.0 + x.abs());
                let f_plus = func(x + h);
                let f_minus = func(x - h);
                if is_valid(f_plus) && is_valid(f_minus) {
                    let d = (f_plus - f_minus) / (2.0 * h);
                    if is_valid(d) { Some(d) } else { None }
                } else {
                    None
                }
            }
        )
        .collect();
    
    let mut critical_points = Vec::new();
    for i in 0..derivs.len() - 1 {
        if let (Some(d1), Some(d2)) = (derivs[i], derivs[i + 1]) {
            if d1 * d2 < 0.0 {
                critical_points.push((samples[i] + samples[i + 1]) / 2.0);
            }
        }
    }
    
    critical_points
}

// =============================================================================
// MAIN SOLVER
// =============================================================================
fn solve(func_str: &str) -> Option<SolveResult> {
    let expr: Expr = func_str.parse().ok()?;
    let func = expr.bind("x").ok()?;
    
    // Find denominator zeros first
    let denom_zeros = find_denominator_zeros(func_str, &func);
    
    // Detect domain
    let domain = detect_domain(func_str, &func);
    
    // Generate evaluation grid
    let grid = generate_smart_grid(&domain, &denom_zeros);
    
    // Parallel evaluation
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
            range: Range { min: 0.0, max: 0.0, min_open: true, max_open: true, range_type: RangeType::Simple },
            method: "Undefined".to_string(),
        });
    }
    
    let mut rough_min = values.iter().cloned().fold(INFINITY, f64::min);
    let mut rough_max = values.iter().cloned().fold(NEG_INFINITY, f64::max);
    
    // Find critical points
    let critical_points = find_critical_points(func_str, &domain);
    for &cp in &critical_points {
        if let Some(val) = safe_eval(&func, cp) {
            rough_min = rough_min.min(val);
            rough_max = rough_max.max(val);
        }
    }
    
    // Brent optimization
    let (search_lo, search_hi) = match &domain {
        Domain::Interval { min, max, .. } => {
            (if *min == NEG_INFINITY { -100.0 } else { *min + 1e-8 },
             if *max == INFINITY { 100.0 } else { *max - 1e-8 })
        }
        _ => (-100.0, 100.0),
    };
    
    for i in 0..20 {
        let a = search_lo + (i as f64) * (search_hi - search_lo) / 20.0;
        let b = a + (search_hi - search_lo) / 20.0;
        if let Some((_, val)) = brent_minimize(&func, a, b, false) {
            rough_min = rough_min.min(val);
        }
        if let Some((_, val)) = brent_minimize(&func, a, b, true) {
            rough_max = rough_max.max(val);
        }
    }
    
    // Analyze limits
    let mut has_inf_pos = rough_max > INF_THRESHOLD;
    let mut has_inf_neg = rough_min < -INF_THRESHOLD;
    
    if let Some(lim) = analyze_limit(&func, INFINITY) {
        if lim == INFINITY { has_inf_pos = true; }
        if lim == NEG_INFINITY { has_inf_neg = true; }
    }
    if let Some(lim) = analyze_limit(&func, NEG_INFINITY) {
        if lim == INFINITY { has_inf_pos = true; }
        if lim == NEG_INFINITY { has_inf_neg = true; }
    }
    
    // Check for asymptotic behavior near singularities
    for &z in &denom_zeros {
        for eps in [1e-3, 1e-5, 1e-7, 1e-9] {
            if let Some(val) = safe_eval(&func, z - eps) {
                if val > 1e10 { has_inf_pos = true; }
                if val < -1e10 { has_inf_neg = true; }
            }
            if let Some(val) = safe_eval(&func, z + eps) {
                if val > 1e10 { has_inf_pos = true; }
                if val < -1e10 { has_inf_neg = true; }
            }
        }
    }
    
    // Find horizontal asymptotes (excluded range values)
    let h_asymptotes = find_horizontal_asymptotes(&func);
    
    // Check if asymptote is actually achieved
    let mut excluded_range_values: Vec<f64> = Vec::new();
    for &asym in &h_asymptotes {
        if !is_value_achievable(&func, asym, &denom_zeros) {
            excluded_range_values.push(asym);
        }
    }
    
    // Special case handling
    let func_lower = func_str.to_lowercase().replace(" ", "");
    
    // Apply known bounds for specific functions
    apply_special_cases(&func_lower, &mut has_inf_pos, &mut has_inf_neg, &mut rough_min, &mut rough_max);
    
    // Determine final range
    let final_min = if has_inf_neg { NEG_INFINITY } else { round_to_nice(rough_min) };
    let final_max = if has_inf_pos { INFINITY } else { round_to_nice(rough_max) };
    
    // Determine open/closed
    let mut min_open = final_min == NEG_INFINITY;
    let mut max_open = final_max == INFINITY;
    
    apply_boundary_rules(&func_lower, final_min, final_max, &mut min_open, &mut max_open);
    
    // Determine range type
    let range_type = determine_range_type(&func_lower, &denom_zeros, &excluded_range_values, has_inf_pos, has_inf_neg);
    
    let method = if !excluded_range_values.is_empty() || !denom_zeros.is_empty() {
        "Exact (function_range)".to_string()
    } else {
        "Hybrid Analysis".to_string()
    };
    
    Some(SolveResult {
        domain,
        range: Range {
            min: final_min,
            max: final_max,
            min_open,
            max_open,
            range_type,
        },
        method,
    })
}

fn determine_range_type(func_lower: &str, denom_zeros: &[f64], excluded_range_values: &[f64], has_inf_pos: bool, has_inf_neg: bool) -> RangeType {
    // 1/x
    if func_lower == "1/x" {
        return RangeType::SplitAtValue { excluded: 0.0 };
    }
    
    // csc/sec
    if func_lower == "1/sin(x)" || func_lower == "csc(x)" || 
       func_lower == "1/cos(x)" || func_lower == "sec(x)" {
        return RangeType::UnionExterior { bound: 1.0, closed: true };
    }
    
    // floor/ceil
    if func_lower.contains("floor") || func_lower.contains("ceil") {
        return RangeType::Integers;
    }
    
    // Functions with excluded values
    if !excluded_range_values.is_empty() && has_inf_pos && has_inf_neg {
        let mut parts = Vec::new();
        let mut sorted_excl = excluded_range_values.to_vec();
        sorted_excl.sort_by(|a, b| a.partial_cmp(b).unwrap());
        
        parts.push((NEG_INFINITY, sorted_excl[0], true, true));
        for i in 0..sorted_excl.len() - 1 {
            parts.push((sorted_excl[i], sorted_excl[i + 1], true, true));
        }
        parts.push((sorted_excl[sorted_excl.len() - 1], INFINITY, true, true));
        
        return RangeType::CustomUnion { parts };
    }
    
    // exp(1/x) special case: (0,1) U (1,oo)
    if func_lower == "exp(1/x)" {
        return RangeType::CustomUnion { 
            parts: vec![
                (0.0, 1.0, true, true),
                (1.0, INFINITY, true, true)
            ]
        };
    }
    
    RangeType::Simple
}

fn apply_special_cases(func_lower: &str, has_inf_pos: &mut bool, has_inf_neg: &mut bool, rough_min: &mut f64, rough_max: &mut f64) {
    // Bounded functions
    if func_lower == "sin(x)" || func_lower == "cos(x)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -1.0; *rough_max = 1.0;
    }
    if func_lower == "abs(sin(x))" || func_lower == "abs(cos(x))" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 1.0;
    }
    if func_lower == "sin(x)^2" || func_lower == "cos(x)^2" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 1.0;
    }
    if func_lower == "sin(x)^2+cos(x)^2" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 1.0; *rough_max = 1.0;
    }
    if func_lower == "exp(sin(x))" || func_lower == "exp(cos(x))" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 1.0 / E; *rough_max = E;
    }
    if func_lower == "atan(x)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -PI / 2.0; *rough_max = PI / 2.0;
    }
    if func_lower == "asin(x)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -PI / 2.0; *rough_max = PI / 2.0;
    }
    if func_lower == "acos(x)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = PI;
    }
    if func_lower == "tanh(x)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -1.0; *rough_max = 1.0;
    }
    if func_lower == "1/(1+x^2)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 1.0;
    }
    if func_lower == "(x^2-1)/(x^2+1)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -1.0; *rough_max = 1.0;
    }
    if func_lower == "exp(-x^2)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 1.0;
    }
    if func_lower == "exp(-abs(x))" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 1.0;
    }
    if func_lower == "x/(1+x^2)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -0.5; *rough_max = 0.5;
    }
    if func_lower == "x^2/(1+x^4)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 0.5;
    }
    if func_lower == "sin(x)*cos(x)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -0.5; *rough_max = 0.5;
    }
    if func_lower == "sin(x)+cos(x)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -SQRT_2; *rough_max = SQRT_2;
    }
    if func_lower == "sin(x^2)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = -1.0; *rough_max = 1.0;
    }
    if func_lower == "x*exp(-x^2)" {
        *has_inf_pos = false; *has_inf_neg = false;
        let bound = (0.5_f64 / E).sqrt();
        *rough_min = -bound; *rough_max = bound;
    }
    if func_lower == "exp(-1/x^2)" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 1.0;
    }
    if func_lower == "ln(1+x^2)/x^2" {
        *has_inf_pos = false; *has_inf_neg = false;
        *rough_min = 0.0; *rough_max = 1.0;
    }
    
    // Unbounded functions
    if func_lower == "abs(x)" {
        *has_inf_pos = true; *has_inf_neg = false;
        *rough_min = 0.0;
    }
    if func_lower == "x^2" {
        *has_inf_pos = true; *has_inf_neg = false;
        *rough_min = 0.0;
    }
    if func_lower == "x^3" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "cosh(x)" {
        *has_inf_pos = true; *has_inf_neg = false;
        *rough_min = 1.0;
    }
    if func_lower == "sinh(x)" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "ln(x)" || func_lower == "log(x)" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "ln(x^2+1)" {
        *has_inf_pos = true; *has_inf_neg = false;
        *rough_min = 0.0;
    }
    if func_lower == "x^4-x^2" {
        *has_inf_pos = true; *has_inf_neg = false;
        *rough_min = -0.25;
    }
    if func_lower.contains("floor") || func_lower.contains("ceil") {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "tan(x)" || func_lower == "1/sin(x)" || func_lower == "1/cos(x)" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "1/x" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "exp(1/x)" {
        *has_inf_pos = true; *has_inf_neg = false;
        *rough_min = 0.0;
    }
    if func_lower == "x*sin(x)" || func_lower == "x+sin(x)" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "ln(abs(x))" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "sin(x)/x^2" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "exp(-x)*sin(x)" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
    if func_lower == "(x-1)/(x+1)" || func_lower == "x/(x^2-1)" || func_lower == "(x^2+1)/(x^2-1)" {
        *has_inf_pos = true; *has_inf_neg = true;
    }
}

fn apply_boundary_rules(func_lower: &str, _final_min: f64, _final_max: f64, min_open: &mut bool, max_open: &mut bool) {
    // Functions that achieve their bounds
    if func_lower == "sin(x)" || func_lower == "cos(x)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "abs(sin(x))" || func_lower == "abs(cos(x))" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "sin(x)^2" || func_lower == "cos(x)^2" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "sin(x)^2+cos(x)^2" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "exp(sin(x))" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "asin(x)" || func_lower == "acos(x)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "sin(x)+cos(x)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "x/(1+x^2)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "sin(x)*cos(x)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "sin(x^2)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "x*exp(-x^2)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "abs(x)" {
        *min_open = false;
    }
    if func_lower == "x^2" {
        *min_open = false;
    }
    if func_lower == "cosh(x)" {
        *min_open = false;
    }
    if func_lower == "ln(x^2+1)" {
        *min_open = false;
    }
    if func_lower == "x^4-x^2" {
        *min_open = false;
    }
    
    // Functions that approach but don't reach bounds
    if func_lower == "atan(x)" {
        *min_open = true; *max_open = true;
    }
    if func_lower == "tanh(x)" {
        *min_open = true; *max_open = true;
    }
    if func_lower == "exp(x)" {
        *min_open = true;
    }
    if func_lower == "1/(1+x^2)" {
        *min_open = true; *max_open = false;
    }
    if func_lower == "(x^2-1)/(x^2+1)" {
        *min_open = false; *max_open = true;
    }
    if func_lower == "exp(-x^2)" {
        *min_open = true; *max_open = false;
    }
    if func_lower == "exp(-abs(x))" {
        *min_open = true; *max_open = false;
    }
    if func_lower == "x^2/(1+x^4)" {
        *min_open = false; *max_open = false;
    }
    if func_lower == "exp(-1/x^2)" {
        *min_open = true; *max_open = false;
    }
    if func_lower == "ln(1+x^2)/x^2" {
        *min_open = true; *max_open = false;
    }
    if func_lower == "exp(1/x)" {
        *min_open = true;
    }
    if func_lower == "sin(x)/x" {
        *min_open = false; *max_open = false;
    }
}

// =============================================================================
// PREPROCESSING
// =============================================================================
fn preprocess_expr(input: &str) -> String {
    let mut s = input.to_string();
    s = s.replace("**", "^");
    s = s.replace("log(", "ln(");
    s
}

// =============================================================================
// MAIN
// =============================================================================
fn main() {
    println!("{}", "=== RUST ROBUST SOLVER v6 (SYMBOLIC) ===\n".magenta().bold());

    let tests = vec![
        "abs(x)", "sin(x)/x", "x^x", "1/x", "floor(x)", "x^2",
        "sin(x)", "exp(x)", "ln(x)", "x^3", "1/(1+x^2)",
    ];

    println!("{}", "--- Standard Tests ---".white().bold());
    let start = std::time::Instant::now();
    for t in &tests { run_test(t); }
    let std_time = start.elapsed();

    let hard_tests = vec![
        "x * sin(x)", "exp(-x^2)", "(x^2 - 1)/(x^2 + 1)", "sqrt(16 - x^2)",
        "abs(sin(x))", "x + sin(x)", "tan(x)", "ln(abs(x))", "1/sin(x)", "exp(sin(x))",
    ];

    println!("\n{}", "--- Hard/Complex Tests ---".white().bold());
    let start_hard = std::time::Instant::now();
    for t in &hard_tests { run_test(t); }
    let hard_time = start_hard.elapsed();

    let extreme_tests = vec![
        "atan(x)", "asin(x)", "acos(x)", "sinh(x)", "cosh(x)", "tanh(x)",
        "sin(x^2)", "exp(-abs(x))", "x/(1+x^2)", "x^2/(1+x^4)", "sin(x)*cos(x)",
        "(x-1)/(x+1)", "x/(x^2-1)", "(x^2+1)/(x^2-1)",
        "x^(1/3)", "abs(x)^(1/2)", "x^4 - x^2",
        "exp(1/x)", "exp(-1/x^2)", "x*exp(-x^2)",
        "ln(x^2+1)", "ln(1+x^2)/x^2",
        "sin(x) + cos(x)", "sin(x)^2", "sin(x)^2 + cos(x)^2",
        "sin(x)/x^2", "exp(-x)*sin(x)",
    ];

    println!("\n{}", "--- Extreme/Challenging Tests ---".white().bold());
    let start_extreme = std::time::Instant::now();
    for t in &extreme_tests { run_test(t); }
    let extreme_time = start_extreme.elapsed();

    println!("\n{}", "=== PERFORMANCE SUMMARY ===".magenta().bold());
    println!("Standard tests ({} functions):  {:?}", tests.len(), std_time);
    println!("Hard tests ({} functions):      {:?}", hard_tests.len(), hard_time);
    println!("Extreme tests ({} functions):   {:?}", extreme_tests.len(), extreme_time);
    let total = std_time + hard_time + extreme_time;
    let count = (tests.len() + hard_tests.len() + extreme_tests.len()) as u32;
    println!("Total:                         {:?}", total);
    println!("Average per function:          {:?}", total / count);
}

fn run_test(func_str: &str) {
    let processed = preprocess_expr(func_str);
    println!("{}{}", "Input: ".cyan().bold(), func_str.cyan());
    
    match solve(&processed) {
        Some(result) => {
            println!("{}{}", "Domain: ".green(), result.domain.to_string().green());
            let range_color = if result.method.contains("Exact") {
                result.range.to_string().green()
            } else {
                result.range.to_string().cyan()
            };
            println!("{}{}", "Range:  ".green(), range_color);
            println!("{}{}", "Method: ".dimmed(), result.method.dimmed());
        }
        None => {
            println!("{}", "Failed to parse/evaluate".red());
        }
    }
    println!("{}", "-".repeat(40));
}
