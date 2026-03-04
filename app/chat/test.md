Below is a **comprehensive calculus cheat‑sheet** that covers the most important definitions, formulas, techniques, and theorems you’ll need for a typical first‑year (and a bit of second‑year) calculus course.  
Feel free to print it, bookmark it, or use it as a quick reference while studying or solving problems.

---

## 1️⃣ BASIC NOTATION & CONCEPTS  

| Symbol | Meaning |
|--------|---------|
| \(f(x)\) | Function of a real variable |
| \(f'(x)\) or \(\displaystyle\frac{df}{dx}\) | First derivative (rate of change) |
| \(f''(x)\) | Second derivative |
| \(\displaystyle\int f(x)\,dx\) | Indefinite integral (antiderivative) |
| \(\displaystyle\int_{a}^{b} f(x)\,dx\) | Definite integral (signed area) |
| \(\displaystyle\lim_{x\to a} f(x)\) | Limit of \(f\) as \(x\) approaches \(a\) |
| \(\displaystyle\sum_{k=1}^{n} a_k\) | Finite sum |
| \(\displaystyle\prod_{k=1}^{n} a_k\) | Finite product |
| \(\displaystyle\int\) | Integral sign |
| \(\displaystyle\partial\) | Partial derivative (for multivariate functions) |
| \(\displaystyle\iint, \iiint\) | Double / triple integrals |
| \(\displaystyle\oint\) | Closed‑curve integral (line integral) |
| \(\displaystyle\delta\) | Dirac delta (distribution) |
| \(\displaystyle\epsilon\) | Arbitrarily small positive number (limit proofs) |

---

## 2️⃣ LIMITS & CONTINUITY  

### 2.1 Common Limits  

| Limit | Result |
|-------|--------|
| \(\displaystyle\lim_{x\to 0}\frac{\sin x}{x}\) | \(1\) |
| \(\displaystyle\lim_{x\to 0}\frac{1-\cos x}{x^2}\) | \(\frac12\) |
| \(\displaystyle\lim_{x\to\infty}\left(1+\frac{a}{x}\right)^x\) | \(e^{a}\) |
| \(\displaystyle\lim_{x\to 0^+}x^p\ln x\) | \(0\) for any \(p>0\) |
| \(\displaystyle\lim_{x\to\infty}\frac{\ln x}{x^p}\) | \(0\) for any \(p>0\) |

### 2.2 Continuity  

- **Definition:** \(f\) is continuous at \(a\) if \(\displaystyle\lim_{x\to a}f(x)=f(a)\).  
- **Types:**  
  - **Removable discontinuity:** limit exists but \(f(a)\) is undefined or different.  
  - **Jump discontinuity:** left‑ and right‑hand limits exist but differ.  
  - **Essential (infinite) discontinuity:** at least one one‑hand limit is infinite.

---

## 3️⃣ DIFFERENTIATION  

### 3.1 Basic Derivative Rules  

| Rule | Formula |
|------|---------|
| **Power** | \(\displaystyle\frac{d}{dx}x^n = nx^{n-1}\) |
| **Constant multiple** | \(\displaystyle\frac{d}{dx}[c\,f(x)] = c\,f'(x)\) |
| **Sum/Difference** | \(\displaystyle\frac{d}{dx}[f\pm g] = f' \pm g'\) |
| **Product** | \(\displaystyle (fg)' = f'g + fg'\) |
| **Quotient** | \(\displaystyle\left(\frac{f}{g}\right)' = \frac{f'g - fg'}{g^2}\) |
| **Chain** | \(\displaystyle\frac{d}{dx}f(g(x)) = f'(g(x))\,g'(x)\) |
| **Inverse function** | \(\displaystyle\frac{d}{dx}f^{-1}(x)=\frac{1}{f'(f^{-1}(x))}\) |

### 3.2 Common Derivatives  

| Function | Derivative |
|----------|-----------|
| \(\sin x\) | \(\cos x\) |
| \(\cos x\) | \(-\sin x\) |
| \(\tan x\) | \(\sec^2 x\) |
| \(\cot x\) | \(-\csc^2 x\) |
| \(\sec x\) | \(\sec x\tan x\) |
| \(\csc x\) | \(-\csc x\cot x\) |
| \(e^x\) | \(e^x\) |
| \(a^x\) | \(a^x\ln a\) |
| \(\ln x\) | \(\frac{1}{x}\) |
| \(\log_a x\) | \(\frac{1}{x\ln a}\) |
| \(\sinh x\) | \(\cosh x\) |
| \(\cosh x\) | \(\sinh x\) |
| \(\tanh x\) | \(\operatorname{sech}^2 x\) |

### 3.3 Higher‑Order Derivatives  

- **Second derivative:** \(f''(x) = \frac{d}{dx}f'(x)\).  
- **n‑th derivative of a polynomial:** If \(f(x)=\sum_{k=0}^{m} a_k x^k\), then \(f^{(n)}(x)=0\) for \(n>m\).  
- **Common patterns:**  
  - \((e^{ax})^{(n)} = a^n e^{ax}\).  
  - \((\sin ax)^{(n)} = a^n \sin\!\big(ax + n\frac{\pi}{2}\big)\).  
  - \((\cos ax)^{(n)} = a^n \cos\!\big(ax + n\frac{\pi}{2}\big)\).

### 3.4 Implicit Differentiation  

Given \(F(x,y)=0\), differentiate both sides w.r.t. \(x\):
\[
\frac{dy}{dx}= -\frac{F_x}{F_y},
\]
where \(F_x = \partial F/\partial x\) and \(F_y = \partial F/\partial y\).

### 3.5 Logarithmic Differentiation  

Useful for \(y = [f(x)]^{g(x)}\):
\[
\ln y = g(x)ln f(x) \;\;\Longrightarrow\;\;
\frac{y'}{y}= g'(x)\ln f(x) + g(x)\frac{f'(x)}{f(x)}.
\]

### 3.6 Related Rates  

1. Write a relation between variables.  
2. Differentiate w.r.t. time \(t\).  
3. Plug in known values and solve for the unknown rate.

---

## 4️⃣ INTEGRATION  

### 4.1 Basic Antiderivative Rules  

| Rule | Formula |
|------|---------|
| **Power** | \(\displaystyle\int x^n dx = \frac{x^{n+1}}{n+1}+C\) ( \(n\neq -1\) ) |
| **Constant multiple** | \(\displaystyle\int c\,f(x)dx = c\int f(x)dx\) |
| **Sum/Difference** | \(\displaystyle\int (f\pm g)dx = \int fdx \pm \int gdx\) |
| **Exponential** | \(\displaystyle\int a^{x}dx = \frac{a^{x}}{\ln a}+C\) |
| **Logarithmic** | \(\displaystyle\int \frac{1}{x}dx = \ln|x|+C\) |
| **Trigonometric** | \(\displaystyle\int \sin x dx = -\cos x +C\) <br> \(\displaystyle\int \cos x dx = \sin x +C\) |
| **Inverse trig** | \(\displaystyle\int \frac{1}{\sqrt{1-x^2}}dx = \arcsin x +C\) <br> \(\displaystyle\int \frac{1}{1+x^2}dx = \arctan x +C\) |

### 4.2 Integration Techniques  

| Technique | When to Use | Key Idea |
|-----------|-------------|----------|
| **Substitution (u‑sub)** | Integrand contains a function and its derivative | Set \(u = g(x)\), \(du = g'(x)dx\) |
| **Integration by Parts** | Product of functions, especially \(u\cdot v'\) | \(\displaystyle\int u\,dv = uv - \int v\,du\) |
| **Partial Fractions** | Rational function where denominator factors | Decompose into sum of simpler fractions |
| **Trigonometric Substitution** | \(\sqrt{a^2\pm x^2}\) or \(\sqrt{x^2-a^2}\) | Use \(x = a\sin\theta\), \(x = a\tan\theta\), \(x = a\sec\theta\) |
| **Trigonometric Identities** | Powers of \(\sin, \cos\) etc. | Use power‑reduction, double‑angle, etc. |
| **Improper Integrals** | Infinite limits or integrand blows up | Treat as limit: \(\int_a^\infty f = \lim_{b\to\infty}\int_a^b f\) |
| **Integration of Rational Functions** | Degree numerator ≥ denominator | Perform polynomial long division first |
| **Differential Equations (separable)** | Form \(dy/dx = g(x)h(y)\) | Separate variables: \(\int \frac{1}{h(y)}dy = \int g(x)dx\) |
| **Reduction Formulas** | Repeated integrals like \(\int \sin^n x dx\) | Derive recurrence relation |

### 4.3 Definite Integral Properties  

- **Linearity:** \(\int_a^b (c_1f + c_2g) = c_1\int_a^b f + c_2\int_a^b g\).  
- **Additivity:** \(\displaystyle\int_a^c f = \int_a^b f + \int_b^c f\).  
- **Reversal:** \(\displaystyle\int_b^a f = -\int_a^b f\).  
- **Mean Value Theorem for Integrals:** If \(f\) is continuous on \([a,b]\), \(\exists c\in(a,b)\) such that \(\displaystyle\int_a^b f = f(c)(b-a)\).  

### 4.4 Fundamental Theorem of Calculus (FTC)  

1. **FTC Part 1 (Derivative of an Integral):**  
   \[
   \frac{d}{dx}\Bigl(\int_a^x f(t)dt\Bigr)=f(x).
   \]

2. **FTC Part 2 (Evaluation):**  
   \[
   \int_a^b f(x)dx = F(b)-F(a),
   \]
   where \(F\) is any antiderivative of \(f\) (\(F' = f\)).  

### 4.5 Area, Volume, and Arc Length  

| Quantity | Formula |
|----------|---------|
| **Area under curve** \(y=f(x)\) | \(\displaystyle A = \int_a^b f(x)dx\) |
| **Area between curves** \(f\) and \(g\) | \(\displaystyle A = \int_a^b |f(x)-g(x)|dx\) |
| **Volume (disk/washer)** | \(\displaystyle V = \pi\int_a^b \bigl(R(x)^2 - r(x)^2\bigr)dx\) |
| **Volume (shells)** | \(\displaystyle V = 2\pi\int_a^b ( \text{radius})(\text{height})\,dx\) |
| **Arc length (Cartesian)** | \(\displaystyle L = \int_a^b \sqrt{1+\bigl(f'(x)\bigr)^2}\,dx\) |
| **Surface area (revolution about x‑axis)** | \(\displaystyle S = 2\pi\int_a^b f(x)\sqrt{1+\bigl(f'(x)\bigr)^2}\,dx\) |

---

## 5️⃣ SERIES & SEQUENCES  

### 5.1 Convergence Tests  

| Test | Condition / Use |
|------|-----------------|
| **Nth‑Term Test** | If \(\lim_{n\to\infty} a_n \neq 0\) → series diverges. |
| **Geometric Series** | \(\displaystyle\sum_{n=0}^\infty ar^n\) converges if \(|r|<1\) to \(\frac{a}{1-r}\). |
| **p‑Series** | \(\displaystyle\sum \frac{1}{n^p}\) converges if \(p>1\). |
| **Comparison Test** | Compare to a known convergent/divergent series. |
| **Limit Comparison Test** | \(\displaystyle\lim_{n\to\infty}\frac{a_n}{b_n}=c\in(0,\infty)\) → same behavior. |
| **Integral Test** | If \(f(n)=a_n\) is positive, decreasing, continuous, then \(\sum a_n\) and \(\int_1^\infty f(x)dx\) share convergence. |
| **Alternating Series Test (Leibniz)** | Terms decreasing to 0 → convergent. |
| **Ratio Test** | \(\displaystyle L=\lim_{n\to\infty}\frac{|a_{n+1}|}{|a_n|}\): <1 converges, >1 diverges, =1 inconclusive. |
| **Root Test** | \(\displaystyle L=\lim_{n\to\infty}\sqrt[n]{|a_n|}\). Same conclusions as ratio test. |
| **Absolute Convergence** | If \(\sum|a_n|\) converges → \(\sum a_n\) converges. |
| **Conditional Convergence** | Converges but not absolutely (e.g., alternating harmonic series). |

### 5.2 Power Series  

- **General form:** \(\displaystyle \sum_{n=0}^{\infty} c_n (x-a)^n\).  
- **Radius of Convergence \(R\):**  
  \[
  R = \frac{1}{\displaystyle\limsup_{n\to\infty}\sqrt[n]{|c_n|}}
  = \lim_{n\to\infty}\left|\frac{c_n}{c_{n+1}}\right| \quad\text{(if limit exists)}.
  \]  
- **Interval of Convergence:** \((a-R, a+R)\) plus possible inclusion of endpoints (test separately).  

### 5.3 Taylor & Maclaurin Series  

- **Taylor series about \(a\):**  
  \[
  f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(a)}{n!}(x-a)^n.
  \]  
- **Maclaurin series:** \(a=0\).  

| Function | Maclaurin series (first few terms) |
|----------|------------------------------------|
| \(e^{x}\) | \(1 + x + \frac{x^2}{2!} + \frac{x^3}{3!} + \cdots\) |
| \(\sin x\) | \(x - \frac{x^3}{3!} + \frac{x^5}{5!} - \cdots\) |
| \(\cos x\) | \(1 - \frac{x^2}{2!} + \frac{x^4}{4!} - \cdots\) |
| \(\ln(1+x)\) | \(x - \frac{x^2}{2} + \frac{x^3}{3} - \cdots\) (|(|x|<1\)) |
| \(\frac{1}{1-x}\) | \(1 + x + x^2 + x^3 + \cdots\) (|x|<1\)) |
| \(\arctan x\) | \(x - \frac{x^3}{3} + \frac{x^5}{5} - \cdots\) (|x|≤1, \(x\neq\pm1\) for convergence) |

- **Remainder (Lagrange form):**  
  \[
  R_n(x)=\frac{f^{(n+1)}(\xi)}{(n+1)!}(x-a)^{n+1},\quad \xi\text{ between }a\text{ and }x.
  \]

---

## 6️⃣ MULTIVARIATE CALCULUS  

### 6.1 Partial Derivatives  

- **Notation:** \(f_x = \frac{\partial f}{\partial x}\), \(f_{xy} = \frac{\partial^2 f}{\partial x\partial y}\).  
- **Clairaut’s theorem (equality of mixed partials):** If \(f\) is \(C^2\) (continuous second partials) on a region, then \(f_{xy}=f_{yx}\).  

### 6.2 Gradient, Directional Derivative  

- **Gradient vector:** \(\displaystyle \nabla f = \bigl(f_x, f_y, f_z\bigr)\).  
- **Directional derivative:** For unit vector \(\mathbf{u}\), \(\displaystyle D_{\mathbf{u}}f = \nabla f\cdot\mathbf{u}\).  

### 6.3 Tangent Plane & Linear Approximation  

For \(z = f(x,y)\) at \((a,b)\):  
\[
z \approx f(a,b) + f_x(a,b)(x-a) + f_y(a,b)(y-b).
\]

### 6.4 Jacobian Matrix  

For \(\mathbf{F}:\mathbb{R}^n\to\mathbb{R}^m\) with components \(F_i\):  
\[
J_{\mathbf{F}} = \left[\frac{\partial F_i}{\partial x_j}\right]_{i=1..m,\;j=1..n}.
\]

### 6.5 Multiple Integrals  

- **Iterated integral (Fubini’s theorem):**  
  \[
  \iint_D f(x,y)\,dA = \int_{a}^{b}\int_{g_1(x)}^{g_2(x)} f(x,y)\,dy\,dx.
  \]  
- **Change of variables (Jacobian):**  
  \[
  \iint_{R} f(x,y)\,dA = \iint_{S} f\bigl(x(u,v),y(u,v)\bigr)\,\bigl|J(u,v)\bigr|\,du\,dv.
  \]  

### 6.6 Polar, Cylindrical, Spherical Coordinates  

| System | Coordinates | Volume element |
|--------|-------------|----------------|
| **Polar** (2‑D) | \(x=r\cos\theta,\; y=r\sin\theta\) | \(dA = r\,dr\,d\theta\) |
| **Cylindrical** (3‑D) | \(x=r\cos\theta,\; y=r\sin\theta,\; z=z\) | \(dV = r\,dr\,d\theta\,dz\) |
| **Spherical** (3‑D) | \(x=\rho\sin\phi\cos\theta,\; y=\rho\sin\phi\sin\theta,\; z=\rho\cos\phi\) | \(dV = \rho^{2}\sin\phi\,d\rho\,d\phi\,d\theta\) |

---

## 7️⃣ DIFFERENTIAL EQUATIONS (DE) – QUICK REFERENCE  

| Type | Standard Form | Solution Sketch |
|------|----------------|-----------------|
| **Separable** | \(\displaystyle \frac{dy}{dx}=g(x)h(y)\) | \(\displaystyle \int\frac{1}{h(y)}dy = \int g(x)dx\) |
| **Linear (first order)** | \(\displaystyle y'+p(x)y = q(x)\) | Integrating factor \(\mu = e^{\int p\,dx}\); then \((\mu y)' = \mu q\) |
| **Exact** | \(M(x,y)dx + N(x,y)dy = 0\) with \(M_y=N_x\) | Find potential function \(\psi\) such that \(\psi_x=M,\; \psi_y=N\) |
| **Bernoulli** | \(y' + p(x)y = q(x) y^n\) | Substitute \(v = y^{1-n}\) → linear in \(v\) |
| **Homogeneous (first order)** | \(y' = F\!\left(\frac{y}{x}\right)\) | Set \(v = y/x\) → separable |
| **Second‑order linear (constant coeff.)** | \(ay''+by'+cy = 0\) | Characteristic equation \(ar^2+br+c=0\) → cases (real distinct, repeated, complex) |
| **Non‑homogeneous linear** | \(ay''+by'+cy = g(x)\) | General solution = homogeneous + particular (method of und. coefficients or variation of parameters) |
| **Laplace Transform** | Useful for ODEs with piecewise or discontinuous forcing | Transform to algebraic equation in \(s\), solve, then inverse‑transform |

---

## 8️⃣ COMMON INTEGRAL TABLE (SELECTED)  

| Integral | Result |
|----------|--------|
| \(\displaystyle\int \frac{dx}{x^2+a^2}\) | \(\displaystyle \frac{1}{a}\arctan\frac{x}{a}+C\) |
| \(\displaystyle\int \frac{dx}{\sqrt{a^2-x^2}}\) | \(\displaystyle \arcsin\frac{x}{a}+C\) |
| \(\displaystyle\int \frac{dx}{\sqrt{x^2-a^2}}\) | \(\displaystyle \ln\bigl|x+\sqrt{x^2-a^2}\bigr|+C\) |
| \(\displaystyle\int \sec x\,dx\) | \(\displaystyle \ln\bigl|\sec x+\tan x\bigr|+C\) |
| \(\displaystyle\int \csc x\,dx\) | \(\displaystyle -\ln\bigl|\csc x+\cot x\bigr|+C\) |
| \(\displaystyle\int \tan x\,dx\) | \(\displaystyle -\ln|\cos x|+C\) |
| \(\displaystyle\int \cot x\,dx\) | \(\displaystyle \ln|\sin x|+C\) |
| \(\displaystyle\int \sinh x\,dx\) | \(\displaystyle \cosh x + C\) |
| \(\displaystyle\int \cosh x\,dx\) | \(\displaystyle \sinh x + C\) |
| \(\displaystyle\int \frac{dx}{\sin x}\) | \(\displaystyle \ln\bigl|\tan\frac{x}{2}\bigr|+C\) |
| \(\displaystyle\int \frac{dx}{\cos x}\) | \(\displaystyle \ln\bigl|\tan\left(\frac{x}{2}+\frac{\pi}{4}\right)\bigr|+C\) |

---

## 9️⃣ QUICK “Cheat‑Sheet” Formulas (One‑Liners)  

- **Derivative of \(\displaystyle \frac{u}{v}\):** \(\displaystyle \left(\frac{u}{v}\right)' = \frac{u'v-uv'}{v^2}\).  
- **Integral of \(\displaystyle \frac{1}{x}\):** \(\displaystyle \ln|x|+C\).  
- **L’Hôpital’s Rule:** If \(\displaystyle\lim_{x\to a}f=g=0\) or \(\pm\infty\), then \(\displaystyle\lim_{x\to a}\frac{f}{g}= \lim_{x\to a}\frac{f'}{g'}\) (provided the latter limit exists).  
- **Sum of a geometric series:** \(\displaystyle S = \frac{a}{1-r}\) for \(|r|<1\).  
- **Integration by parts (tabular method):** Repeatedly differentiate the algebraic part, integrate the exponential/trig part, and alternate signs.  
- **Arc length of \(y=f(x)\):** \(\displaystyle L = \int_a^b\sqrt{1+(f')^2}\,dx\).  
- **Surface area of revolution (about x‑axis):** \(\displaystyle S = 2\pi\int_a^b f(x)\sqrt{1+(f')^2}\,dx\).  
- **Volume by disks:** \(\displaystyle V = \pi\int_a^b [R(x)]^2dx\).  
- **Volume by shells:** \(\displaystyle V = 2\pi\int_a^b (\text{radius})(\text{height})dx\).  

---

## 10️⃣ TIPS & REMINDERS  

1. **Check hypotheses** before applying a theorem (e.g., continuity for FTC, differentiability for chain rule).  
2. **Always add “+ C”** for indefinite integrals.  
3. **When in doubt, differentiate** the antiderivative you propose to verify.  
4. **Use symmetry** (odd/even functions) to simplify integrals over symmetric intervals.  
5. **Plot the region** before setting up double/triple integrals; decide whether Cartesian, polar, cylindrical, or spherical coordinates are easiest.  
6. **Series convergence**: start with the easiest test (nth‑term, geometric, p‑series) before moving to ratio/root.  
7. **Taylor approximations** are great for estimating limits: replace a function by its low‑order polynomial near the point of interest.  
8. **Units & dimensions**: in physics‑oriented problems, keep track of units; they often catch algebraic mistakes.  

---

### 📚 Where to Go Next  

- **Practice**: Work through textbook problems that specifically target each technique.  
- **Visualize**: Use graphing tools (Desmos, GeoGebra) to see curves, regions, and surfaces.  
- **Software**: For messy integrals or series, try symbolic calculators (WolframAlpha, SymPy) to confirm your hand work.  
- **Deepen**: Explore multivariate theorems (Green’s, Stokes’, Divergence) once you’re comfortable with the basics.  

Happy calculus-ing! 🚀  