"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, Plus, Trash2, Calculator as CalcIcon, Terminal, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import "mathlive";
// @ts-ignore - nerdamer doesn't have proper types
import nerdamer from 'nerdamer';
import 'nerdamer/Calculus';
import 'nerdamer/Algebra';
import 'nerdamer/Solve';

declare global {
    interface Window {
        Desmos: any;
    }
    namespace JSX {
        interface IntrinsicElements {
            'math-field': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
                'virtual-keyboard-mode'?: string;
                'read-only'?: boolean;
                'smart-fence'?: string;
            };
        }
    }
}

interface MathExpression {
    id: string;
    latex: string;
    result?: string;
    color: string;
}

const DEFAULT_COLORS = ["#c74440", "#2d70b3", "#388c46", "#6042a6", "#fa7e19", "#000000"];
const getRandomColor = () => DEFAULT_COLORS[Math.floor(Math.random() * DEFAULT_COLORS.length)];

// ==========================================
//      SYMBOLIC COMPUTATION UTILITIES
// ==========================================

/**
 * Convert LaTeX to nerdamer-compatible format
 */
const latexToNerdamer = (latex: string): string => {
    let expr = latex
        // Remove LaTeX formatting first
        .replace(/\\left\s*/g, '')
        .replace(/\\right\s*/g, '')
        .replace(/\\cdot/g, '*')
        .replace(/\\times/g, '*')
        // Handle fractions: \frac{a}{b} -> (a)/(b)
        // Need to handle nested braces properly
        .replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '($1)/($2)')
        // Handle sqrt: \sqrt{x} -> sqrt(x)
        .replace(/\\sqrt\s*\{([^{}]*)\}/g, 'sqrt($1)')
        // Handle nth root: \sqrt[n]{x} -> x^(1/n)
        .replace(/\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}/g, '($2)^(1/($1))')
        // Handle powers: x^{n} -> x^(n) - do this BEFORE removing backslashes
        .replace(/\^\{([^{}]*)\}/g, '^($1)')
        // Handle subscripts (remove them for now)
        .replace(/_\{[^{}]*\}/g, '')
        .replace(/_[a-zA-Z0-9]/g, '')
        // Handle absolute value
        .replace(/\|([^|]+)\|/g, 'abs($1)')
        // Handle pi
        .replace(/\\pi/g, 'pi');
    
    // Handle trig functions - nerdamer uses sin(x), cos(x), etc.
    expr = expr
        .replace(/\\sin\s*\(([^)]+)\)/g, 'sin($1)')
        .replace(/\\cos\s*\(([^)]+)\)/g, 'cos($1)')
        .replace(/\\tan\s*\(([^)]+)\)/g, 'tan($1)')
        .replace(/\\cot\s*\(([^)]+)\)/g, 'cot($1)')
        .replace(/\\sec\s*\(([^)]+)\)/g, 'sec($1)')
        .replace(/\\csc\s*\(([^)]+)\)/g, 'csc($1)')
        .replace(/\\arcsin\s*\(([^)]+)\)/g, 'asin($1)')
        .replace(/\\arccos\s*\(([^)]+)\)/g, 'acos($1)')
        .replace(/\\arctan\s*\(([^)]+)\)/g, 'atan($1)')
        // Handle trig without explicit parentheses (e.g., \sin x)
        .replace(/\\sin\s+([a-zA-Z])/g, 'sin($1)')
        .replace(/\\cos\s+([a-zA-Z])/g, 'cos($1)')
        .replace(/\\tan\s+([a-zA-Z])/g, 'tan($1)')
        .replace(/\\cot\s+([a-zA-Z])/g, 'cot($1)')
        .replace(/\\sec\s+([a-zA-Z])/g, 'sec($1)')
        .replace(/\\csc\s+([a-zA-Z])/g, 'csc($1)')
        // Handle remaining \sin, \cos etc followed by variable
        .replace(/\\(sin|cos|tan|cot|sec|csc)([a-zA-Z])/g, '$1($2)')
        .replace(/\\(sin|cos|tan|cot|sec|csc)\s*/g, '$1');
    
    // Handle ln and log - IMPORTANT: nerdamer uses 'log' for natural log!
    // Order matters: most specific patterns first
    expr = expr
        // \ln with parentheses
        .replace(/\\ln\s*\(([^)]+)\)/g, 'log($1)')
        // \ln followed by space and variable
        .replace(/\\ln\s+([a-zA-Z])/g, 'log($1)')
        // \ln directly followed by variable (no space)
        .replace(/\\ln([a-zA-Z])/g, 'log($1)')
        // \ln at end or followed by operator - wrap next char/expr
        .replace(/\\ln\s*$/g, 'log')
        // Standalone \ln followed by something
        .replace(/\\ln\b/g, 'log');
    
    // For \log (base 10), use log10 - but be careful not to double-convert
    expr = expr
        .replace(/\\log\s*\(([^)]+)\)/g, 'log10($1)')
        .replace(/\\log\s+([a-zA-Z])/g, 'log10($1)')
        .replace(/\\log([a-zA-Z])/g, 'log10($1)')
        .replace(/\\log\b/g, 'log10');
    
    // Handle e^x -> exp(x)
    expr = expr
        .replace(/\\exp\s*\(([^)]+)\)/g, 'exp($1)')
        .replace(/\\exp\s*/g, 'exp')
        .replace(/e\^\(([^)]+)\)/g, 'exp($1)')
        .replace(/e\^([a-zA-Z0-9])/g, 'exp($1)');
    
    // Remove remaining backslashes and clean up
    expr = expr
        .replace(/\\/g, '')
        .replace(/\s+/g, '')
        .trim();
    
    return expr;
};

/**
 * Convert nerdamer result back to LaTeX
 */
const nerdamerToLatex = (result: any): string => {
    try {
        let tex = result.toTeX();
        
        // nerdamer's toTeX() returns proper LaTeX like \frac{x^4}{4}
        // We just need to clean up spacing issues
        tex = tex
            // Clean up multiple spaces
            .replace(/\s+/g, ' ')
            .trim();
        
        return tex;
    } catch {
        return result.toString();
    }
};

/**
 * Compute symbolic derivative using nerdamer
 */
const computeSymbolicDerivative = (expression: string, variable: string = 'x', order: number = 1): string | null => {
    try {
        const nerdamerExpr = latexToNerdamer(expression);
        console.log('[Derivative] Input:', expression, '-> Nerdamer:', nerdamerExpr);
        
        let result = nerdamer(nerdamerExpr);
        
        for (let i = 0; i < order; i++) {
            result = nerdamer.diff(result, variable);
        }
        
        const tex = nerdamerToLatex(result);
        console.log('[Derivative] Result:', tex);
        return tex;
    } catch (e) {
        console.warn('Symbolic derivative computation failed:', e);
        return null;
    }
};

/**
 * Compute symbolic integral using nerdamer
 */
const computeSymbolicIntegral = (expression: string, variable: string = 'x'): string | null => {
    try {
        const nerdamerExpr = latexToNerdamer(expression);
        console.log('[Integral] Input:', expression, '-> Nerdamer:', nerdamerExpr);
        
        const result = nerdamer.integrate(nerdamerExpr, variable);
        const tex = nerdamerToLatex(result);
        console.log('[Integral] Result:', tex);
        return tex;
    } catch (e) {
        console.warn('Symbolic integral computation failed:', e);
        return null;
    }
};

export function Calculator() {
    const calculatorRef = useRef<HTMLDivElement>(null);
    const calculatorInstance = useRef<any>(null);
    const helpersRef = useRef<{ [key: string]: any }>({});
    const { theme, setTheme, resolvedTheme } = useTheme();
    const [expressions, setExpressions] = useState<MathExpression[]>([
        { id: "1", latex: "", color: "#2d70b3" },
    ]);
    const [debugInfo, setDebugInfo] = useState<string>("Ready");
    const [libLoaded, setLibLoaded] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [legendOpen, setLegendOpen] = useState(true);

    // 1. MathLive Configuration
    useEffect(() => {
        if (typeof window !== 'undefined') {
            import("mathlive").then((ml) => {
                // @ts-ignore
                ml.MathfieldElement.fontsDirectory = "https://unpkg.com/mathlive@0.108.2/dist/fonts";
                // @ts-ignore
                ml.MathfieldElement.soundsDirectory = null;
            });
        }
    }, []);

    // 2. Load Desmos
    useEffect(() => {
        if (window.Desmos) {
            setLibLoaded(true);
            return;
        }
        const script = document.createElement("script");
        script.src = "https://www.desmos.com/api/v1.11/calculator.js?apiKey=dcb31709b452b1cf9dc26972add0fda6";
        script.async = true;
        script.onload = () => setLibLoaded(true);
        document.body.appendChild(script);
    }, []);

    // 3. Initialize Desmos
    useEffect(() => {
        if (!libLoaded || !calculatorRef.current || calculatorInstance.current) return;

        calculatorInstance.current = window.Desmos.GraphingCalculator(calculatorRef.current, {
            expressions: false,
            keypad: false,
            settingsMenu: true,
            zoomButtons: true,
            invertedColors: resolvedTheme === 'dark',
            border: false,
        });

        expressions.forEach(e => processExpression(e.id, e.latex, e.color));

        return () => {
            if (calculatorInstance.current) {
                calculatorInstance.current.destroy();
                calculatorInstance.current = null;
            }
        };
    }, [libLoaded]);

    // Theme Sync
    useEffect(() => {
        calculatorInstance.current?.updateSettings({ invertedColors: resolvedTheme === 'dark' });
    }, [resolvedTheme]);


    // ==========================================
    //      THE LOGIC: SMART TRANSFORMER
    // ==========================================
    const processExpression = (id: string, rawLatex: string, color: string) => {
        const Calc = calculatorInstance.current;
        if (!Calc) return;

        // 1. Generate Safe Variable ID
        const safeId = `E${id.replace(/-/g, "")}`;

        // 2. Clear All Associated Expressions
        const cleanupList = [
            id,
            `curve-${safeId}`, `shade-${safeId}`,
            `val-${safeId}`, `func-${safeId}`, `label-${safeId}`,
            `funcD-${safeId}`,
            `plot-orig-${safeId}`, `plot-deriv-${safeId}`
        ];
        cleanupList.forEach(eid => Calc.removeExpression({ id: eid }));

        // Cleanup old helper if exists
        if (helpersRef.current[safeId]) {
            // Desmos helpers don't have a clear destroy method, 
            // but we drop the reference and hopefully the engine cleans up listeners
            delete helpersRef.current[safeId];
        }

        if (!rawLatex.trim()) {
            setExpressions(prev => prev.map(e => e.id === id ? { ...e, result: undefined } : e));
            return;
        }

        // 3. Minimal Cleaning
        // We only normalize things that Desmos strictly hates.
        let clean = rawLatex
            .replace(/\\bigm/g, "") // Fix for \bigm| issue
            .replace(/\\!/g, "")
            .replace(/\\,/g, " ").replace(/\\:/g, " ").replace(/\\;/g, " ")
            .replace(/\\limits/g, "")
            .replace(/\\differentialD/g, "d")
            .replace(/\\mathrm\{d\}/g, "d")
            .replace(/\\dfrac/g, "\\frac")
            .trim();

        // Fix Logarithm bases: \log_5 10 -> \log_{5} 10
        clean = clean.replace(/\\log_(\d+)/g, "\\log_{$1}");

        // ========================================
        // ABSOLUTE VALUE NORMALIZATION (Comprehensive)
        // ========================================
        // Desmos recognizes: \left|...\right| or just |...|
        // We normalize all variants to \left|...\right| for consistency

        // 1. Handle \mathrm{\abs}(...) or \mathrm{abs}(...) -> \left|...\right|
        //    Also handles \operatorname{abs}(...)
        clean = clean.replace(/\\mathrm\{\\?abs\}\s*\\left\(([^)]*?)\\right\)/g, "\\left|$1\\right|");
        clean = clean.replace(/\\mathrm\{\\?abs\}\s*\(([^)]*?)\)/g, "\\left|$1\\right|");
        clean = clean.replace(/\\mathrm\{\\?abs\}\s*\{([^}]*?)\}/g, "\\left|$1\\right|");
        clean = clean.replace(/\\operatorname\{abs\}\s*\\left\(([^)]*?)\\right\)/g, "\\left|$1\\right|");
        clean = clean.replace(/\\operatorname\{abs\}\s*\(([^)]*?)\)/g, "\\left|$1\\right|");

        // 2. Handle \left\vert ... \right\vert -> \left| ... \right|
        clean = clean.replace(/\\left\\vert\s*/g, "\\left|");
        clean = clean.replace(/\\right\\vert\s*/g, "\\right|");

        // 3. Handle \lvert ... \rvert -> \left| ... \right|
        clean = clean.replace(/\\lvert\s*/g, "\\left|");
        clean = clean.replace(/\\rvert\s*/g, "\\right|");

        // 4. Handle standalone \vert ... \vert -> \left| ... \right|
        //    Be careful to match paired \vert commands
        clean = clean.replace(/\\vert\s*([^\\]*?)\\vert/g, "\\left|$1\\right|");

        // 5. Handle \abs{...} command -> \left| ... \right|
        clean = clean.replace(/\\abs\s*\{([^}]*)\}/g, "\\left|$1\\right|");

        // 6. Handle simple |...| (unescaped vertical bars)
        //    First pass already handled \left| and \right|
        //    Now handle remaining standalone |content| pairs
        //    We need to be careful not to double-process
        //    Strategy: Only convert |...| if not preceded by \left or \right
        const convertSimplePipes = (str: string): string => {
            let result = '';
            let i = 0;
            while (i < str.length) {
                // Check if this is a standalone | (not \left| or \right|)
                if (str[i] === '|') {
                    // Check if preceded by \left or \right
                    const before = str.substring(Math.max(0, i - 6), i);
                    if (before.endsWith('\\left') || before.endsWith('\\right')) {
                        result += str[i];
                        i++;
                        continue;
                    }
                    // Find matching closing |
                    let j = i + 1;
                    let depth = 1;
                    while (j < str.length && depth > 0) {
                        if (str[j] === '|') {
                            const beforeJ = str.substring(Math.max(0, j - 6), j);
                            if (!beforeJ.endsWith('\\left') && !beforeJ.endsWith('\\right')) {
                                depth--;
                            }
                        }
                        if (depth > 0) j++;
                    }
                    if (depth === 0) {
                        // Found matching pair
                        const content = str.substring(i + 1, j);
                        result += '\\left|' + content + '\\right|';
                        i = j + 1;
                    } else {
                        result += str[i];
                        i++;
                    }
                } else {
                    result += str[i];
                    i++;
                }
            }
            return result;
        };
        clean = convertSimplePipes(clean);

        // Ensure standard functions have backslashes if missing
        const funcs = ["sin", "cos", "tan", "sec", "csc", "cot", "ln", "log", "exp"];
        funcs.forEach(f => {
            const regex = new RegExp(`(^|[^\\\\a-zA-Z])(${f})(?![a-zA-Z])`, "g");
            clean = clean.replace(regex, "$1\\$2");
        });

        setDebugInfo(clean);

        // --- Helper: Robust Bounds Parser ---
        const parseBounds = (startIdx: number, str: string) => {
            try {
                let i = startIdx;
                let min = "", max = "";

                // Helper to skip whitespace
                const skipSpace = () => { while (i < str.length && /\s/.test(str[i])) i++; };

                const parseGroup = () => {
                    skipSpace();
                    if (i >= str.length) return "";
                    if (str[i] === "{") {
                        let depth = 1;
                        i++;
                        let start = i;
                        while (i < str.length && depth > 0) {
                            if (str[i] === '{') depth++;
                            if (str[i] === '}') depth--;
                            i++;
                        }
                        if (depth > 0) return ""; // Unbalanced
                        return str.substring(start, i - 1);
                    }
                    if (str[i] === '\\') { // Command
                        const start = i;
                        i++;
                        while (i < str.length && /[a-zA-Z]/.test(str[i])) i++;
                        return str.substring(start, i);
                    }
                    return str[i++];
                };

                for (let step = 0; step < 2; step++) {
                    skipSpace();
                    if (i >= str.length) break;

                    if (str[i] === '_') {
                        i++;
                        min = parseGroup();
                    } else if (str[i] === '^') {
                        i++;
                        max = parseGroup();
                    } else {
                        break;
                    }
                }
                return { min, max, end: i };
            } catch (e) {
                console.error("Parse bounds error", e);
                return { min: "", max: "", end: startIdx };
            }
        };
        // Flag to track if we handled the expression with a custom parser
        let handled = false;
        let helperLatex = clean;

        try { // Safe block for custom parsers

            // --- BRANCH A: Summation ---
            if (clean.startsWith("\\sum")) {
                const bounds = parseBounds(4, clean);
                if (bounds.min && bounds.max) {
                    // Just plotting help here if needed? 
                    // Desmos plots sums fine if set as y = ... but usually Sum is a scalar.
                    // We already handled value via Helper.
                    // If we want to show it on graph (as a line y=val), we can:
                    Calc.setExpression({
                        id: `val-${safeId}`,
                        latex: `S_{${safeId}} = ${clean}`,
                        secret: true
                    });

                    // Update helper to listen to the calculated sum variable
                    helperLatex = `S_{${safeId}}`;
                    handled = true;
                }
            }

            // --- BRANCH B: Definite/Indefinite Integral ---
            if (!handled && clean.startsWith("\\int")) {
                const bounds = parseBounds(4, clean);
                const rest = clean.substring(bounds.end).trim();
                
                // Handle both dx and \mathrm{d}x patterns
                const varMatch = rest.match(/(?:\\mathrm\{d\}|d)(\\[a-zA-Z]+|[a-zA-Z])$/);

                if (varMatch) {
                    const rawVariable = varMatch[1];
                    // Remove the differential pattern from body
                    const dPattern = new RegExp(`(?:\\\\mathrm\\{d\\}|d)${rawVariable.replace('\\', '\\\\')}$`);
                    const body = rest.replace(dPattern, '').trim();

                    if (bounds.min && bounds.max) {
                        // Clean bounds from LaTeX artifacts
                        const cleanMin = bounds.min.replace(/\\left\s*/g, "").replace(/\\right\s*/g, "").trim();
                        const cleanMax = bounds.max.replace(/\\left\s*/g, "").replace(/\\right\s*/g, "").trim();
                        
                        // Definite: Visual Shading
                        // Clean up the body for plotting - remove LaTeX formatting that Desmos doesn't need
                        let plotBody = rawVariable === 'x' ? body : body.split(rawVariable).join("x");

                        // Remove \left and \right delimiters as they can cause parsing issues
                        plotBody = plotBody
                            .replace(/\\left\s*/g, "")
                            .replace(/\\right\s*/g, "")
                            .replace(/\\bigl\s*/g, "")
                            .replace(/\\bigr\s*/g, "")
                            .replace(/\\Bigl\s*/g, "")
                            .replace(/\\Bigr\s*/g, "")
                            .trim();
                        
                        // Also remove outer parentheses if present
                        if (plotBody.startsWith('(') && plotBody.endsWith(')')) {
                            let depth = 0;
                            let isOuter = true;
                            for (let i = 0; i < plotBody.length - 1; i++) {
                                if (plotBody[i] === '(') depth++;
                                else if (plotBody[i] === ')') depth--;
                                if (depth === 0 && i < plotBody.length - 1) {
                                    isOuter = false;
                                    break;
                                }
                            }
                            if (isOuter) {
                                plotBody = plotBody.substring(1, plotBody.length - 1).trim();
                            }
                        }

                        // Only plot if we have a valid body
                        if (plotBody) {
                            Calc.setExpression({
                                id: `curve-${safeId}`,
                                latex: `y = ${plotBody}`,
                                color: color,
                                lineWidth: 2,
                                lineStyle: window.Desmos.Styles.DOTTED,
                                label: "Parent Function",
                                showLabel: true,
                            });

                            // Shade the area between the curve and the x-axis (works for both positive and negative regions)
                            // Using min(0, f(x)) ≤ y ≤ max(0, f(x)) to capture both cases
                            const shadeLatex = `\\min(0, ${plotBody}) \\le y \\le \\max(0, ${plotBody}) \\left\\{ ${cleanMin} \\le x \\le ${cleanMax} \\right\\}`;
                            Calc.setExpression({
                                id: `shade-${safeId}`,
                                latex: shadeLatex,
                                color: color,
                                fillOpacity: 0.3,
                                lines: false
                            });
                        }

                        // Create the value expression for Desmos
                        Calc.setExpression({
                            id: `val-${safeId}`,
                            latex: `I_{${safeId}} = ${clean}`,
                            secret: true
                        });

                        // Update helper to listen to the calculated integral variable
                        helperLatex = `I_{${safeId}}`;
                        handled = true;
                    } else {
                        // Indefinite
                        let plotOriginal = rawVariable === 'x' ? body : body.split(rawVariable).join("x");
                        plotOriginal = plotOriginal
                            .replace(/\\left\s*/g, "")
                            .replace(/\\right\s*/g, "")
                            .trim();

                        Calc.setExpression({
                            id: `curve-${safeId}`,
                            latex: `y = ${plotOriginal}`,
                            lineStyle: window.Desmos.Styles.DOTTED,
                            color: color,
                            label: "Parent Function",
                            showLabel: true
                        });
                        const bodyWithT = body.split(rawVariable).join("t");
                        Calc.setExpression({
                            id,
                            latex: `y = \\int_{0}^{x} ${bodyWithT} dt`,
                            color: color,
                            lineStyle: window.Desmos.Styles.SOLID,
                            label: "Integral",
                            showLabel: true
                        });
                        handled = true;
                    }
                }
            }

            // --- BRANCH C: Derivative (Symbolic & Numeric) ---
            if (!handled && clean.startsWith("\\frac")) {
                const derivRegex = /^\\frac\s*\{\s*d(\^\{?([0-9]+)\}?)?\s*\}\s*\{\s*d(\\[a-zA-Z]+|[a-zA-Z])(\^\{?([0-9]+)\}?)?\s*\}\s*(.+)$/;
                const derivMatch = clean.match(derivRegex);

                if (derivMatch) {
                    const order = derivMatch[2] ? parseInt(derivMatch[2]) : 1;
                    const variable = derivMatch[3];
                    let content = derivMatch[6];

                    let isEvaluation = false;
                    let targetVal = "";
                    let body = content;

                    const barIndex = content.lastIndexOf("|_{");
                    if (barIndex !== -1 && content.trim().endsWith("}")) {
                        const possibleBody = content.substring(0, barIndex).trim();
                        const evalPart = content.substring(barIndex + 3, content.length - 1);
                        const parts = evalPart.split("=");
                        if (parts.length === 2 && parts[0].trim() === variable) {
                            isEvaluation = true;
                            targetVal = parts[1].trim();
                            body = possibleBody;
                        }
                    }

                    // For visuals: Plot the derivative function
                    Calc.setExpression({
                        id: `funcD-${safeId}`,
                        latex: `f_{${safeId}}(${variable}) = ${body}`,
                        secret: true
                    });

                    // Only plot the curve if it's NOT a specific evaluation (or we can plot the point?)
                    // If it is evaluation, user usually just wants the number (handled by helper)
                    // But we might want to see the function being derived?
                    Calc.setExpression({
                        id: `plot-orig-${safeId}`,
                        latex: `y = f_{${safeId}}(x)`,
                        lineStyle: window.Desmos.Styles.DOTTED,
                        color: color,
                        label: "Parent Function",
                        showLabel: true
                    });

                    let derivNotation = "";
                    if (order <= 3) {
                        let primes = "";
                        for (let k = 0; k < order; k++) primes += "'";
                        derivNotation = `f_{${safeId}}${primes}(x)`;
                    } else {
                        derivNotation = `\\frac{d^${order}}{dx^${order}} f_{${safeId}}(x)`;
                    }

                    const derivLabel = `Derivative: f${order > 1 ? `^(${order})` : "'"}(x)`;
                    if (!isEvaluation) {
                        Calc.setExpression({
                            id: `plot-deriv-${safeId}`,
                            latex: `y = ${derivNotation}`,
                            color: color,
                            label: derivLabel,
                            showLabel: true,
                            lineStyle: window.Desmos.Styles.SOLID
                        });
                    } else {
                        // It's an evaluation. Visuals?
                        // Maybe show the point on the derivative curve?
                        // Latex: (target, value)
                        // But we don't have value sync here easily w/o helper.
                        // Let's just create the derivative curve hidden or dashed?
                        Calc.setExpression({
                            id: `plot-deriv-${safeId}`,
                            latex: `y = ${derivNotation}`,
                            color: color,
                            label: derivLabel,
                            showLabel: true,
                            lineStyle: window.Desmos.Styles.SOLID
                        });

                        // Handle Value Calculation
                        let valLatex = "";
                        if (order <= 3) {
                            let primes = "";
                            for (let k = 0; k < order; k++) primes += "'";
                            valLatex = `f_{${safeId}}${primes}(${targetVal})`;
                        } else {
                            valLatex = `\\frac{d^${order}}{d${variable}^${order}} f_{${safeId}}(${targetVal})`;
                        }
                        Calc.setExpression({
                            id: `val-${safeId}`,
                            latex: `V_{${safeId}} = ${valLatex}`,
                            secret: true
                        });

                        // Configure helper to listen to this result
                        helperLatex = `V_{${safeId}}`;
                    }
                    handled = true;
                }
            }

        } catch (err) {
            console.warn("Smart parser error, falling back to Desmos native:", err);
        }

        // --- BRANCH D: Standard (Fallback) ---
        if (!handled) {
            let finalLatex = clean;
            if (!finalLatex.startsWith("\\int") && !finalLatex.startsWith("\\frac") && finalLatex.endsWith("dx")) {
                finalLatex = finalLatex.replace(/d[x-z]$/, "");
            }

            Calc.setExpression({
                id: id,
                latex: finalLatex,
                color: color,
                showLabel: true
            });
        }

        // --- 4. Result Calculation (Universal Helper) ---
        try {
            const helper = Calc.HelperExpression({ latex: helperLatex });
            helpersRef.current[safeId] = helper;

            helper.observe('numericValue', () => {
                const val = helper.numericValue;
                setExpressions(prev => prev.map(e => {
                    if (e.id === id) {
                        // Only show result if it's a finite number
                        // Checks: not NaN, not undefined
                        if (val !== undefined && !isNaN(val) && isFinite(val)) {
                            // Round to reasonable decimals for display
                            // Desmos usually does this, but we get raw number
                            // Let's format nicely:
                            const display = Math.abs(val) < 1e-10 ? "0" :
                                Math.abs(val) > 1e10 ? val.toExponential(4) :
                                    parseFloat(val.toFixed(6)).toString();
                            return { ...e, result: display };
                        } else {
                            return { ...e, result: undefined };
                        }
                    }
                    return e;
                }));
            });
        } catch (e) {
            console.warn("Helper creation failed", e);
        }
    };

    const handleInput = (id: string, value: string) => {
        const expr = expressions.find(e => e.id === id);
        const currentColor = expr ? expr.color : "#2d70b3";
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, latex: value } : e));
        processExpression(id, value, currentColor);
    };

    const handleColorChange = (id: string, newColor: string) => {
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, color: newColor } : e));
        const expr = expressions.find(e => e.id === id);
        if (expr) processExpression(id, expr.latex, newColor);
    };

    const addExpr = () => {
        const id = Math.random().toString(36).substr(2, 9);
        setExpressions([...expressions, { id, latex: "", color: getRandomColor() }]);
    };

    const removeExpr = (id: string) => {
        setExpressions(expressions.filter(e => e.id !== id));
        if (calculatorInstance.current) {
            // Re-generate safe ID to clean up correctly
            const safeId = `E${id.replace(/-/g, "")}`;

            // Cleanup helper
            if (helpersRef.current[safeId]) {
                delete helpersRef.current[safeId];
            }

            calculatorInstance.current.removeExpression({ id });
            calculatorInstance.current.removeExpression({ id: `curve-${safeId}` });
            calculatorInstance.current.removeExpression({ id: `shade-${safeId}` });
            calculatorInstance.current.removeExpression({ id: `val-${safeId}` });
            calculatorInstance.current.removeExpression({ id: `func-${safeId}` });
            calculatorInstance.current.removeExpression({ id: `label-${safeId}` });
            calculatorInstance.current.removeExpression({ id: `funcD-${safeId}` });
            calculatorInstance.current.removeExpression({ id: `plot-orig-${safeId}` });
            calculatorInstance.current.removeExpression({ id: `plot-deriv-${safeId}` });
        }
    };

    const getLegendData = (rawLatex: string) => {
        let clean = rawLatex
            .replace(/\\bigm/g, "")
            .replace(/\\!/g, "")
            .replace(/\\,/g, " ").replace(/\\:/g, " ").replace(/\\;/g, " ")
            .replace(/\\limits/g, "")
            .replace(/\\differentialD/g, "d")
            .replace(/\\mathrm\{d\}/g, "d")
            .replace(/\\dfrac/g, "\\frac")
            .trim();

        // Fix Logarithm bases
        clean = clean.replace(/\\log_(\d+)/g, "\\log_{$1}");

        // ==========================================
        //      DERIVATIVE PARSING WITH SYMBOLIC RESULT
        // ==========================================
        const derivRegex = /^\\frac\s*\{\s*d(\^\{?([0-9]+)\}?)?\s*\}\s*\{\s*d(\\[a-zA-Z]+|[a-zA-Z])(\^\{?([0-9]+)\}?)?\s*\}\s*(.+)$/;
        const derivMatch = clean.match(derivRegex);
        if (derivMatch) {
            const order = derivMatch[2] ? parseInt(derivMatch[2]) : 1;
            const variable = derivMatch[3] ? derivMatch[3].replace('\\', '') : 'x';
            
            // Extract the function being derived
            let content = derivMatch[6];
            const barIndex = content.lastIndexOf("|_{");
            if (barIndex !== -1 && content.trim().endsWith("}")) {
                content = content.substring(0, barIndex).trim();
            }
            
            // Clean up parent label
            let parentLabel = content
                .replace(/\\left\s*/g, '')
                .replace(/\\right\s*/g, '')
                .trim();
            
            if (parentLabel.length > 30) {
                parentLabel = `f(${variable})`;
            }
            
            // Compute symbolic derivative using nerdamer
            const symbolicResult = computeSymbolicDerivative(content, variable, order);
            
            // Build the result label with proper order indication
            let resultLabel: string;
            let orderLabel = '';
            if (order === 1) {
                orderLabel = "f'(" + variable + ")";
            } else if (order === 2) {
                orderLabel = "f''(" + variable + ")";
            } else if (order === 3) {
                orderLabel = "f'''(" + variable + ")";
            } else {
                orderLabel = `f^{(${order})}(${variable})`;
            }
            
            if (symbolicResult) {
                // We got a symbolic result! Show it with the order notation
                resultLabel = symbolicResult;
            } else {
                // Fallback to showing the derivative notation
                const derivNotation = order > 1 
                    ? `\\frac{d^{${order}}}{d${variable}^{${order}}}` 
                    : `\\frac{d}{d${variable}}`;
                resultLabel = `${derivNotation}\\left(${parentLabel}\\right)`;
            }

            return [
                { type: 'dotted', label: parentLabel, math: true, description: 'Parent Function' },
                { type: 'solid', label: resultLabel, math: true, description: symbolicResult ? `${orderLabel} = Result` : 'Derivative' }
            ];
        }

        // ==========================================
        //      INTEGRAL PARSING WITH SYMBOLIC RESULT
        // ==========================================
        if (clean.startsWith("\\int")) {
            // Robust regex to capture integral bounds
            // Matches: \int, optional _{...} or _x, optional ^{...} or ^x, then the body
            const boundsRegex = /^\\int(?:_\{([^}]*)\}|_(-?[0-9a-zA-Z\\]+))?(?:\^\{([^}]*)\}|\^(-?[0-9a-zA-Z\\]+))?/;
            const boundsMatch = clean.match(boundsRegex);
            
            // Extract and CLEAN bounds (remove \left, \right, etc.)
            let lowerBound = boundsMatch ? (boundsMatch[1] ?? boundsMatch[2] ?? null) : null;
            let upperBound = boundsMatch ? (boundsMatch[3] ?? boundsMatch[4] ?? null) : null;
            
            // Clean bounds from LaTeX artifacts
            if (lowerBound) {
                lowerBound = lowerBound
                    .replace(/\\left\s*/g, '')
                    .replace(/\\right\s*/g, '')
                    .trim();
            }
            if (upperBound) {
                upperBound = upperBound
                    .replace(/\\left\s*/g, '')
                    .replace(/\\right\s*/g, '')
                    .trim();
            }
            
            const hasBounds = lowerBound !== null && upperBound !== null;
            
            // Extract body by removing the matched bounds portion
            let body = boundsMatch ? clean.substring(boundsMatch[0].length).trim() : clean.substring(4).trim();
            
            // Extract differential variable (dx, dt, etc.) - handle \mathrm{d}x too
            let diffVar = 'x';
            const dMatch = body.match(/(?:\\mathrm\{d\}|d)(\\[a-zA-Z]+|[a-zA-Z])$/);
            if (dMatch) {
                const rawVar = dMatch[1];
                diffVar = rawVar.replace('\\', '');
                // Remove the differential from the body
                const dPattern = new RegExp(`(?:\\\\mathrm\\{d\\}|d)${rawVar.replace('\\', '\\\\')}$`);
                body = body.replace(dPattern, '').trim();
            }
            
            // Clean up body: remove \left, \right
            let cleanBody = body
                .replace(/\\left\s*/g, '')
                .replace(/\\right\s*/g, '')
                .trim();
            
            // Remove outer parentheses if they wrap the entire expression
            if (cleanBody.startsWith('(') && cleanBody.endsWith(')')) {
                let depth = 0;
                let isOuter = true;
                for (let i = 0; i < cleanBody.length - 1; i++) {
                    if (cleanBody[i] === '(') depth++;
                    else if (cleanBody[i] === ')') depth--;
                    if (depth === 0 && i < cleanBody.length - 1) {
                        isOuter = false;
                        break;
                    }
                }
                if (isOuter) {
                    cleanBody = cleanBody.substring(1, cleanBody.length - 1).trim();
                }
            }
            
            // Parent function label (simplify if too long)
            const parentLabel = cleanBody.length > 25 ? `f(${diffVar})` : cleanBody;
            
            // Compute symbolic integral using nerdamer
            const symbolicIntegral = computeSymbolicIntegral(cleanBody, diffVar);
            
            if (hasBounds) {
                // DEFINITE INTEGRAL: Return 3 items
                // 1. Parent function (dotted) - the curve being integrated
                // 2. Antiderivative (solid) - the symbolic result or notation
                // 3. Area (shaded) - the definite integral visualization
                
                let antiderivLabel: string;
                if (symbolicIntegral) {
                    antiderivLabel = symbolicIntegral;
                } else {
                    antiderivLabel = `F(${diffVar})`;
                }
                
                // Build clean area label
                const areaLabel = `\\int_{${lowerBound}}^{${upperBound}} ${parentLabel} \\, d${diffVar}`;
                
                return [
                    { type: 'dotted', label: parentLabel, math: true, description: 'Parent Function (Integrand)' },
                    { type: 'solid', label: antiderivLabel, math: true, description: symbolicIntegral ? 'Antiderivative' : 'Antiderivative F(x)' },
                    { type: 'area', label: areaLabel, math: true, description: 'Definite Integral (Area)' }
                ];
            } else {
                // INDEFINITE INTEGRAL: Return 2 items
                // 1. Parent function (dotted) - the integrand
                // 2. Antiderivative (solid) - the symbolic result
                
                let antiderivLabel: string;
                if (symbolicIntegral) {
                    // Add + C for indefinite integral
                    antiderivLabel = `${symbolicIntegral} + C`;
                } else {
                    antiderivLabel = `\\int ${parentLabel}\\, d${diffVar}`;
                }
                
                return [
                    { type: 'dotted', label: parentLabel, math: true, description: 'Parent Function (Integrand)' },
                    { type: 'solid', label: antiderivLabel, math: true, description: symbolicIntegral ? 'Antiderivative' : 'Integral' }
                ];
            }
        }
        
        return [{ type: 'solid', label: clean, math: true }];
    };

    if (!libLoaded) return <div className="h-screen w-full flex items-center justify-center font-mono">Loading Engine...</div>;

    return (
        <div className="flex flex-col h-screen w-full bg-background overflow-hidden">
            <header className="h-12 border-b flex items-center justify-between px-4 bg-card z-20 shadow-sm shrink-0">
                <div className="flex items-center gap-3">
                    <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground">
                        {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
                    </button>
                    <h1 className="font-bold text-lg flex items-center gap-2">
                        <CalcIcon className="text-primary h-5 w-5" />
                        <span className="font-serif italic font-medium">ƒ</span>(x) Engine
                    </h1>
                </div>
                <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className="p-2 rounded-full hover:bg-accent transition-colors">
                    {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
                </button>
            </header>

            <div className="flex-1 flex overflow-hidden">
                <div className={`flex flex-col border-r bg-card z-10 shadow-lg transition-all duration-300 ease-in-out relative ${sidebarOpen ? 'w-[400px] translate-x-0' : 'w-0 border-r-0 -translate-x-full opacity-0 overflow-hidden'}`}>
                    <div className="p-3 flex-1 overflow-y-auto space-y-2">
                        {expressions.map((expr, i) => (
                            <div key={expr.id} className="group relative flex items-start gap-2 bg-muted/30 p-2 rounded-lg border border-transparent focus-within:border-primary/50 focus-within:bg-muted/50 transition-all">
                                <div className="flex flex-col items-center gap-1 mt-2">
                                    <div className="text-xs font-mono opacity-30 select-none w-4 text-center">{i + 1}</div>
                                    <input 
                                        type="color" 
                                        value={expr.color} 
                                        onChange={(e) => handleColorChange(expr.id, e.target.value)}
                                        className="w-4 h-4 rounded-full overflow-hidden p-0 border-0 cursor-pointer"
                                        title="Change Graph Color"
                                    />
                                </div>
                                <div className="flex-1 min-w-0 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: 'none' }}>
                                    {/* @ts-ignore */}
                                    <math-field
                                        smart-fence="on"
                                        onInput={(e: any) => handleInput(expr.id, e.target.value)}
                                        value={expr.latex}
                                        style={{
                                            minWidth: '100%',
                                            width: 'fit-content',
                                            backgroundColor: 'transparent',
                                            outline: 'none',
                                            fontSize: '1.1rem',
                                            '--caret-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                            '--smart-fence-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                            '--smart-fence-opacity': '1',
                                            '--selection-background-color': resolvedTheme === 'dark' ? 'rgba(120, 100, 255, 0.3)' : 'rgba(80, 70, 229, 0.2)',
                                            '--selection-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                            color: resolvedTheme === 'dark' ? '#fff' : '#1a1a1a'
                                        } as React.CSSProperties}
                                    >
                                        {expr.latex}
                                    </math-field>
                                </div>
                                {expr.result && (
                                    <div className="flex items-center justify-center px-2 py-0.5 bg-primary/10 text-primary font-mono text-sm rounded select-all whitespace-nowrap self-center">
                                        = {expr.result}
                                    </div>
                                )}
                                <button onClick={() => removeExpr(expr.id)} className="mt-1 opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-red-500 transition-all">
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))}
                    </div>

                    <div className="p-3 border-t bg-muted/10 space-y-2">
                        <button onClick={addExpr} className="w-full py-2 border border-dashed border-border rounded-lg flex items-center justify-center gap-2 text-sm text-muted-foreground hover:text-primary transition-all hover:bg-muted/50 hover:border-primary/30">
                            <Plus size={14} /> Add Expression
                        </button>
                        <div className="font-mono text-[10px] bg-black/5 dark:bg-white/5 p-2 rounded flex justify-between items-center opacity-50 hover:opacity-100 transition-opacity">
                            <div className="flex items-center gap-2 font-bold whitespace-nowrap">
                                <Terminal size={10} /> Output
                            </div>
                            <div className="truncate max-w-[200px] text-right">{debugInfo}</div>
                        </div>
                    </div>
                </div>

                <div className="flex-1 relative bg-white dark:bg-black transition-all">
                    <div ref={calculatorRef} className="absolute inset-0 w-full h-full" />
                    
                    {/* Graph Legend Overlay */}
                    <div className={`absolute top-4 right-4 bg-card/90 backdrop-blur-sm rounded-lg shadow-md border text-xs z-10 select-none transition-all duration-200 overflow-hidden flex flex-col ${legendOpen ? 'max-h-[60vh] w-[220px]' : 'w-auto h-auto'}`}>
                        <div 
                            className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 border-b border-border/50"
                            onClick={() => setLegendOpen(!legendOpen)}
                        >
                            <div className="flex items-center gap-2">
                                {/* @ts-ignore */}
                                <CalcIcon size={14} className="opacity-70" />
                                <span className={`font-bold opacity-70 ${!legendOpen && 'hidden'}`}>Graph Legend</span>
                            </div>
                            <div className={`transition-transform duration-200 ${legendOpen ? 'rotate-0' : 'rotate-180'}`}>
                                <PanelLeftClose size={14} className="rotate-90" />
                            </div>
                        </div>

                        {legendOpen && (
                            <div className="p-3 pt-2 overflow-y-auto space-y-4">
                                {expressions.filter(e => e.latex.trim()).map((expr, i) => {
                                    const items = getLegendData(expr.latex);
                                    return (
                                        <div key={expr.id} className="flex flex-col gap-1.5">
                                            <div className="flex items-center gap-2 font-medium opacity-90 text-[10px] uppercase tracking-wider text-muted-foreground">
                                                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: expr.color }}></div>
                                                <span>Expr {i + 1}</span>
                                            </div>
                                            <div className="grid grid-cols-[24px_1fr] gap-x-2 gap-y-2 items-center pl-1">
                                                {items.map((item, idx) => (
                                                    <React.Fragment key={idx}>
                                                        <div className="flex items-center justify-center">
                                                            {item.type === 'dotted' && (
                                                                <div className="w-full border-t-[3px] border-dotted" style={{ borderColor: expr.color }}></div>
                                                            )}
                                                            {item.type === 'solid' && (
                                                                <div className="w-full h-0.5" style={{ backgroundColor: expr.color }}></div>
                                                            )}
                                                            {item.type === 'area' && (
                                                                <div className="w-full h-3 rounded-[2px] opacity-40 border border-transparent" style={{ backgroundColor: expr.color }}></div>
                                                            )}
                                                        </div>
                                                        <div className="min-w-0">
                                                            {item.math ? (
                                                                /* @ts-ignore */
                                                                <math-field read-only style={{
                                                                    fontSize: '0.85rem',
                                                                    backgroundColor: 'transparent',
                                                                    color: 'inherit',
                                                                    padding: 0,
                                                                    margin: 0,
                                                                    border: 'none',
                                                                    outline: 'none',
                                                                    '--caret-color': 'transparent',
                                                                }}>{item.label}</math-field>
                                                            ) : (
                                                                <span className="opacity-70 truncate block">{item.label}</span>
                                                            )}
                                                        </div>
                                                    </React.Fragment>
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}
                                
                                {expressions.every(e => !e.latex.trim()) && (
                                    <div className="text-muted-foreground italic text-center py-2 opacity-50">No graphs active</div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}