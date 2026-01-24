# Fast Math RS - Rust Acceleration for Domain/Range Calculator

This is a Rust extension module that provides high-performance numerical computation
for the domain/range calculator.

## Features

- **Parallel Grid Evaluation**: Efficient evaluation of functions over large grids
- **Brent's Method Optimization**: Fast 1D minimization without scipy overhead
- **Adaptive Grid Generation**: Smarter sampling that focuses on critical regions
- **Sign Change Detection**: Vectorized critical point detection

## Building

### Prerequisites

1. Install Rust: https://rustup.rs/
2. Install maturin: `pip install maturin`

### Development Build

```bash
cd service/fast_math_rs
maturin develop --release
```

This will build and install the module into your current Python environment.

### Production Build

```bash
maturin build --release
pip install target/wheels/fast_math_rs-*.whl
```

## Usage in algo.py

The module is automatically detected and used when available:

```python
try:
    import fast_math_rs
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
```

When enabled, functions like `smart_numerical_range` will use Rust for:
- Grid generation (`generate_multi_scale_grid`)
- Min/max finding (`find_min_max_parallel`)
- 1D optimization (`brent_minimize`)
- Critical point detection (`find_sign_changes`)

## Performance

Expected speedups (varies by function complexity):
- Grid sampling: 2-5x faster
- Min/max finding: 3-10x faster
- 1D optimization: 5-20x faster (Brent vs differential_evolution)

## API Reference

### `linspace(start, end, num) -> List[float]`
Generate linearly spaced points.

### `generate_multi_scale_grid(gen_min, gen_max, scales, samples_per_scale) -> List[float]`
Generate sample points at multiple scales, sorted and deduplicated.

### `find_min_max_parallel(y_values) -> Tuple[float, float]`
Find min/max of a numpy array efficiently.

### `find_sign_changes(values) -> ndarray`
Find indices where sign changes occur.

### `brent_minimize(func, a, b, tol, max_iter) -> Tuple[float, float]`
Brent's method for 1D minimization. Returns (x_min, f_min).

### `batch_find_extrema(func, x_values, chunk_size) -> Tuple[float, float, List[float]]`
Batch evaluate and find extrema.

### `adaptive_grid(min_x, max_x, base_points, special_points, density_radius) -> List[float]`
Generate adaptive grid with higher density near special points.
