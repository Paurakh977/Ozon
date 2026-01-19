
```markdown
# Calculator Module Documentation

This directory contains a modularized Symbolic Graphing Calculator. It integrates the **Desmos API** for graphing and **Nerdamer** for symbolic computation (derivatives, integrals, algebra).

## Directory Structure

```text
components/calculator/
├── Calculator.tsx
├── types.ts
├── hooks/
│   ├── useGraphEngine.ts
│   └── useExpressionLogic.ts
├── utils/
│   ├── colors.ts
│   ├── latex-parser.ts
│   └── symbolic-math.ts
└── ui/
    ├── GraphArea.tsx
    ├── GraphLegend.tsx
    ├── Header.tsx
    └── Sidebar.tsx
```

---

## 1. Core Logic (Utils)
*Located in `components/calculator/utils/`*

These files contain "pure" logic. They do not depend on React or the DOM.

### `latex-parser.ts`
**Role:** The Translator.
*   **Logic:**
    *   **`latexToNerdamer(latex)`**: complex Regex chains that convert display LaTeX (e.g., `\frac{x}{2}`, `\sin x`) into text format understandable by the Nerdamer CAS engine (e.g., `(x)/(2)`, `sin(x)`).
    *   **`nerdamerToLatex(result)`**: Converts computed math results back into LaTeX for display.
    *   **Normalization**: Cleans inputs by removing `\left`, `\right`, and standardized whitespace to ensure consistent parsing.

### `symbolic-math.ts`
**Role:** The Math Brain (CAS).
*   **Logic:**
    *   Initializes `nerdamer` and loads its sub-libraries (`Calculus`, `Algebra`, `Solve`) as side effects.
    *   **`computeSymbolicDerivative`**: Takes a LaTeX string, calculates the derivative symbolically (not numerically), and returns the LaTeX result.
    *   **`computeSymbolicIntegral`**: Computes indefinite and definite integrals symbolically.

### `colors.ts`
**Role:** Styling Helper.
*   **Logic:** Contains the `DEFAULT_COLORS` array and a randomizer function to assign distinct colors to new graph expressions.

---

## 2. State & Engine (Hooks)
*Located in `components/calculator/hooks/`*

These manage the application state and the lifecycle of external libraries.

### `useGraphEngine.ts`
**Role:** The Driver.
*   **Logic:**
    *   **Script Injection**: Asynchronously loads the external Desmos API script (`calculator.js`) into the window.
    *   **Initialization**: Creates the `Desmos.GraphingCalculator` instance once the script is loaded.
    *   **Theme Sync**: Listens to the Next.js theme (Light/Dark) and updates the Desmos `invertedColors` setting in real-time.
    *   **Cleanup**: Destroys the calculator instance when the component unmounts to prevent memory leaks.

### `useExpressionLogic.ts`
**Role:** The Orchestrator / Smart Parser.
*   **Logic:**
    *   **State Management**: Holds the array of `expressions` (id, latex, color, result).
    *   **Smart Parsing (`processExpression`)**: This is the most complex logic in the app. It analyzes user input to detect:
        *   **Integrals**: Parses bounds, plots the function (dotted), creates a shaded area using Desmos inequalities (`min(0, f(x)) <= y <= ...`), and creates a hidden helper expression to calculate the numeric value.
        *   **Derivatives**: Parses the `d/dx` notation, plots the tangent/derivative curve, and sets up hidden expressions.
    *   **Observer Pattern**: Creates hidden "Helper Expressions" in Desmos to observe numeric results (e.g., the area of an integral) and updates the React state to display the result (e.g., `= 4.5`) in the UI.

---

## 3. User Interface (UI)
*Located in `components/calculator/ui/`*

Presentational components that receive data via props.

### `Sidebar.tsx`
**Role:** Input Panel.
*   **Logic:**
    *   Renders the list of math inputs.
    *   Uses the `<math-field>` custom web component for rich math editing.
    *   Handles "Add Expression" and "Remove Expression" events.
    *   Displays the calculated numeric result (if available).

### `GraphLegend.tsx`
**Role:** Dynamic Overlay.
*   **Logic:**
    *   **Visual Parsing**: It re-parses the current LaTeX to determine what to show in the legend.
    *   **Context Awareness**: If the user graphs an integral, the legend splits into three parts:
        1.  Dotted Line (Parent function).
        2.  Solid Line (Antiderivative).
        3.  Shaded Block (Area).
    *   **Symbolic Display**: Calls `symbolic-math` utils to show the actual symbolic derivative equation (e.g., `2x`) in the legend, rather than just "Derivative".

### `GraphArea.tsx`
**Role:** Container.
*   **Logic:** A wrapper `div` that holds the reference (`ref`) where the Desmos calculator is injected. Also acts as the positioning context for the absolute-positioned Legend.

### `Header.tsx`
**Role:** Navigation & Controls.
*   **Logic:** Simple layout for the Title, Sidebar toggle, and Theme toggle button.

---

## 4. The Root
*Located in `components/calculator/`*

### `types.ts`
**Role:** Type Definitions.
*   **Logic:** Defines `MathExpression` interface and global window extensions for Desmos/MathLive to prevent TypeScript errors.

### `Calculator.tsx`
**Role:** Main Entry Point.
*   **Logic:**
    *   Calls `useGraphEngine` to get the calculator instance.
    *   Calls `useExpressionLogic` to bind the state to that instance.
    *   Assembles the UI components (`Header`, `Sidebar`, `GraphArea`) and passes the necessary data and handlers between them.

---

## Data Flow Summary

1.  **User types** in `Sidebar`.
2.  `Calculator.tsx` passes input to `useExpressionLogic`.
3.  `useExpressionLogic` calls `latex-parser` to clean input.
4.  `useExpressionLogic` detects math type (e.g., Integral) and calls the **Desmos Instance**.
5.  **Desmos** calculates the graph and numeric values.
6.  `useExpressionLogic` observers detect the result and update React State.
7.  `Sidebar` updates to show the result (`= value`).
8.  `GraphLegend` updates by calling `symbolic-math` to show the symbolic equation.
```