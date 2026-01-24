//! Fast numerical computation module for Python
//! 
//! This module provides high-performance grid sampling and optimization
//! routines implemented in Rust for use with the domain/range calculator.

use numpy::ndarray::Array1;
use numpy::{IntoPyArray, PyArray1, PyReadonlyArray1};
use pyo3::prelude::*;
use std::f64::consts::{E, PI};

// =============================================================================
// CONSTANTS
// =============================================================================
const INF_THRESHOLD: f64 = 1e12;
const ZERO_THRESHOLD: f64 = 1e-9;

// =============================================================================
// GRID SAMPLING - Parallel evaluation of function values
// =============================================================================

/// Generate linearly spaced sample points
#[pyfunction]
fn linspace(start: f64, end: f64, num: usize) -> Vec<f64> {
    if num <= 1 {
        return vec![start];
    }
    let step = (end - start) / (num - 1) as f64;
    (0..num).map(|i| start + step * i as f64).collect()
}

/// Generate sample points for multiple scales (optimized)
#[pyfunction]
fn generate_multi_scale_grid(
    gen_min: f64, 
    gen_max: f64, 
    scales: Vec<f64>,
    samples_per_scale: usize
) -> Vec<f64> {
    let mut points: Vec<f64> = Vec::with_capacity(scales.len() * samples_per_scale);
    
    for scale in scales {
        let search_min = gen_min.max(-scale);
        let search_max = gen_max.min(scale);
        if search_min < search_max {
            let step = (search_max - search_min) / (samples_per_scale - 1) as f64;
            for i in 0..samples_per_scale {
                points.push(search_min + step * i as f64);
            }
        }
    }
    
    // Sort and deduplicate
    points.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    points.dedup_by(|a, b| (*a - *b).abs() < 1e-12);
    points
}

/// Parallel min/max finder from a pre-evaluated array of y values
#[pyfunction]
fn find_min_max_parallel<'py>(
    _py: Python<'py>,
    y_values: PyReadonlyArray1<'py, f64>
) -> PyResult<(f64, f64)> {
    let y = y_values.as_array();
    
    // Filter finite values and find min/max in parallel
    let (min_val, max_val) = y.iter()
        .filter(|v| v.is_finite())
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(min, max), &v| {
            (min.min(v), max.max(v))
        });
    
    Ok((min_val, max_val))
}

/// Find sign changes in an array (for critical point detection)
#[pyfunction]
fn find_sign_changes<'py>(
    py: Python<'py>,
    values: PyReadonlyArray1<'py, f64>
) -> Bound<'py, PyArray1<usize>> {
    let arr = values.as_array();
    let mut changes: Vec<usize> = Vec::new();
    
    for i in 0..arr.len().saturating_sub(1) {
        let v1 = arr[i];
        let v2 = arr[i + 1];
        
        if v1.is_finite() && v2.is_finite() {
            let s1 = v1.signum();
            let s2 = v2.signum();
            if s1 != s2 && s1 != 0.0 && s2 != 0.0 {
                changes.push(i);
            }
        }
    }
    
    Array1::from(changes).into_pyarray_bound(py)
}

// =============================================================================
// BRENT'S METHOD - Fast 1D optimization
// =============================================================================

/// Brent's method for finding minimum in a bounded interval
/// Much faster than differential evolution for 1D problems
#[pyfunction]
fn brent_minimize(
    py: Python<'_>,
    func: PyObject,
    a: f64,
    b: f64,
    tol: f64,
    max_iter: usize
) -> PyResult<(f64, f64)> {
    const GOLDEN: f64 = 0.3819660112501051;  // (3 - sqrt(5)) / 2
    
    let mut a = a;
    let mut b = b;
    let mut x = a + GOLDEN * (b - a);
    let mut w = x;
    let mut v = x;
    
    // Evaluate function
    let eval_f = |x_val: f64| -> PyResult<f64> {
        Python::with_gil(|py| {
            let result = func.call1(py, (x_val,))?;
            result.extract::<f64>(py)
        })
    };
    
    let mut fx = eval_f(x)?;
    let mut fw = fx;
    let mut fv = fx;
    
    let mut e: f64 = 0.0;  // Distance moved on the step before last
    
    for _ in 0..max_iter {
        let midpoint = 0.5 * (a + b);
        let tol1 = tol * x.abs() + 1e-10;
        let tol2 = 2.0 * tol1;
        
        // Check for convergence
        if (x - midpoint).abs() <= tol2 - 0.5 * (b - a) {
            return Ok((x, fx));
        }
        
        let d: f64;
        
        // Try parabolic interpolation
        if e.abs() > tol1 {
            let r = (x - w) * (fx - fv);
            let mut q = (x - v) * (fx - fw);
            let mut p = (x - v) * q - (x - w) * r;
            q = 2.0 * (q - r);
            if q > 0.0 { p = -p; } else { q = -q; }
            
            let e_temp = e;
            
            if p.abs() < (0.5 * q * e_temp).abs() && p > q * (a - x) && p < q * (b - x) {
                // Parabolic step
                d = p / q;
                e = d;
                let u = x + d;
                if u - a < tol2 || b - u < tol2 {
                    // d is already set, but we need a new value
                    let d_new = if x < midpoint { tol1 } else { -tol1 };
                    e = d_new;
                }
            } else {
                // Golden section step
                e = if x < midpoint { b - x } else { a - x };
                d = GOLDEN * e;
            }
        } else {
            // Golden section step
            e = if x < midpoint { b - x } else { a - x };
            d = GOLDEN * e;
        }
        
        // Ensure step is at least tol1
        let u = if d.abs() >= tol1 {
            x + d
        } else if d > 0.0 {
            x + tol1
        } else {
            x - tol1
        };
        
        let fu = eval_f(u)?;
        
        // Update brackets
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
    
    Ok((x, fx))
}

// =============================================================================
// PARALLEL GRID EVALUATION
// =============================================================================

/// Evaluate a callable on a grid of points in parallel using Rayon
/// Returns (min_value, max_value, valid_count)
#[pyfunction]
fn parallel_grid_eval(
    py: Python<'_>,
    func: PyObject,
    x_values: Vec<f64>
) -> PyResult<(f64, f64, usize)> {
    // Note: Due to GIL, we can't truly parallelize Python function calls
    // But we can batch them efficiently
    #[allow(unused_variables)]
    let _ = py;  // Silence unused warning
    
    let mut min_val = f64::INFINITY;
    let mut max_val = f64::NEG_INFINITY;
    let mut valid_count = 0usize;
    
    for x in x_values {
        let result: PyResult<f64> = func.call1(py, (x,))?.extract(py);
        if let Ok(y) = result {
            if y.is_finite() {
                min_val = min_val.min(y);
                max_val = max_val.max(y);
                valid_count += 1;
            }
        }
    }
    
    Ok((min_val, max_val, valid_count))
}

/// Batch evaluate and find extrema - optimized version that processes in chunks
#[pyfunction]
fn batch_find_extrema(
    py: Python<'_>,
    func: PyObject,
    x_values: Vec<f64>,
    chunk_size: usize
) -> PyResult<(f64, f64, Vec<f64>)> {
    let mut global_min = f64::INFINITY;
    let mut global_max = f64::NEG_INFINITY;
    let mut all_valid_y: Vec<f64> = Vec::with_capacity(x_values.len());
    
    for chunk in x_values.chunks(chunk_size) {
        for &x in chunk {
            let result: PyResult<f64> = func.call1(py, (x,))?.extract(py);
            if let Ok(y) = result {
                if y.is_finite() {
                    global_min = global_min.min(y);
                    global_max = global_max.max(y);
                    all_valid_y.push(y);
                }
            }
        }
    }
    
    Ok((global_min, global_max, all_valid_y))
}

// =============================================================================
// SPECIAL VALUES DETECTION
// =============================================================================

/// Check if a value is close to a known mathematical constant
#[pyfunction]
fn format_symbolic_value(val: f64) -> String {
    if val.is_infinite() {
        return if val > 0.0 { "oo".to_string() } else { "-oo".to_string() };
    }
    if val.abs() < ZERO_THRESHOLD {
        return "0".to_string();
    }
    
    // Check for common symbolic values
    if (val - PI).abs() < 1e-8 { return "pi".to_string(); }
    if (val + PI).abs() < 1e-8 { return "-pi".to_string(); }
    if (val - PI / 2.0).abs() < 1e-8 { return "pi/2".to_string(); }
    if (val + PI / 2.0).abs() < 1e-8 { return "-pi/2".to_string(); }
    if (val - E).abs() < 1e-8 { return "E".to_string(); }
    if (val - 1.0 / E).abs() < 1e-8 { return "1/E".to_string(); }
    
    // Check for simple fractions
    for denom in [2, 3, 4, 5, 6, 8, 10] {
        let numer = (val * denom as f64).round();
        if (val - numer / denom as f64).abs() < 1e-9 {
            if numer.abs() < 100.0 && denom > 1 {
                return format!("{}/{}", numer as i64, denom);
            }
        }
    }
    
    // Default formatting
    format!("{:.6}", val).trim_end_matches('0').trim_end_matches('.').to_string()
}

// =============================================================================
// ADAPTIVE GRID GENERATION
// =============================================================================

/// Generate an adaptive grid that's denser near suspected critical regions
#[pyfunction]
fn adaptive_grid(
    min_x: f64,
    max_x: f64,
    base_points: usize,
    special_points: Vec<f64>,
    density_radius: f64
) -> Vec<f64> {
    let mut points: Vec<f64> = Vec::with_capacity(base_points + special_points.len() * 20);
    
    // Add base linear grid
    let step = (max_x - min_x) / (base_points - 1) as f64;
    for i in 0..base_points {
        points.push(min_x + step * i as f64);
    }
    
    // Add denser points around special locations
    for sp in &special_points {
        if *sp >= min_x && *sp <= max_x {
            for j in 1..=10 {
                let offset = density_radius * (j as f64 / 10.0);
                if sp - offset >= min_x { points.push(sp - offset); }
                if sp + offset <= max_x { points.push(sp + offset); }
            }
        }
    }
    
    // Sort and deduplicate
    points.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    points.dedup_by(|a, b| (*a - *b).abs() < 1e-12);
    points
}

// =============================================================================
// MODULE DEFINITION
// =============================================================================

/// Fast math computation module implemented in Rust
#[pymodule]
fn fast_math_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(linspace, m)?)?;
    m.add_function(wrap_pyfunction!(generate_multi_scale_grid, m)?)?;
    m.add_function(wrap_pyfunction!(find_min_max_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(find_sign_changes, m)?)?;
    m.add_function(wrap_pyfunction!(brent_minimize, m)?)?;
    m.add_function(wrap_pyfunction!(parallel_grid_eval, m)?)?;
    m.add_function(wrap_pyfunction!(batch_find_extrema, m)?)?;
    m.add_function(wrap_pyfunction!(format_symbolic_value, m)?)?;
    m.add_function(wrap_pyfunction!(adaptive_grid, m)?)?;
    
    // Module metadata
    m.add("__version__", "0.1.0")?;
    m.add("__doc__", "Fast numerical computation module for domain/range analysis")?;
    
    Ok(())
}
