"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, Plus, Trash2, Calculator as CalcIcon, Terminal, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import "mathlive";

declare global {
    interface Window {
        Desmos: any;
        MathfieldElement: any;
    }
    namespace JSX {
        interface IntrinsicElements {
            'math-field': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
                'virtual-keyboard-mode'?: string;
            };
        }
    }
}

interface MathExpression {
    id: string;
    latex: string;
    result?: string;
}

export function Calculator() {
    const calculatorRef = useRef<HTMLDivElement>(null);
    const calculatorInstance = useRef<any>(null);
    const helpersRef = useRef<{ [key: string]: any }>({});
    const { theme, setTheme, resolvedTheme } = useTheme();
    const [expressions, setExpressions] = useState<MathExpression[]>([
        { id: "1", latex: "" },
    ]);
    const [debugInfo, setDebugInfo] = useState<string>("Ready");
    const [libLoaded, setLibLoaded] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);

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

        expressions.forEach(e => processExpression(e.id, e.latex));

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
    const processExpression = (id: string, rawLatex: string) => {
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
                const varMatch = rest.match(/d(\\[a-zA-Z]+|[a-zA-Z])$/);

                if (varMatch) {
                    const rawVariable = varMatch[1];
                    const body = rest.substring(0, rest.lastIndexOf('d' + rawVariable)).trim();

                    if (bounds.min && bounds.max) {
                        // Definite: Visual Shading
                        const plotBody = rawVariable === 'x' ? body : body.split(rawVariable).join("x");

                        Calc.setExpression({
                            id: `curve-${safeId}`,
                            latex: `y = ${plotBody}`,
                            lineStyle: window.Desmos.Styles.DASHED,
                            color: "#2d70b3"
                        });
                        const shadeLatex = `0 \\le y \\le ${plotBody} \\left\\{ ${bounds.min} \\le x \\le ${bounds.max} \\right\\}`;
                        Calc.setExpression({
                            id: `shade-${safeId}`,
                            latex: shadeLatex,
                            color: "#2d70b3",
                            fillOpacity: 0.3,
                            lines: false
                        });

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
                        const plotOriginal = rawVariable === 'x' ? body : body.split(rawVariable).join("x");
                        Calc.setExpression({
                            id: `curve-${safeId}`,
                            latex: `y = ${plotOriginal}`,
                            lineStyle: window.Desmos.Styles.DASHED,
                            color: "#999999"
                        });
                        const bodyWithT = body.split(rawVariable).join("t");
                        Calc.setExpression({
                            id,
                            latex: `y = \\int_{0}^{x} ${bodyWithT} dt`,
                            color: "#2d70b3"
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
                        lineStyle: window.Desmos.Styles.DASHED,
                        color: "#999999",
                        label: "f(x)"
                    });

                    let derivNotation = "";
                    if (order <= 3) {
                        let primes = "";
                        for (let k = 0; k < order; k++) primes += "'";
                        derivNotation = `f_{${safeId}}${primes}(x)`;
                    } else {
                        derivNotation = `\\frac{d^${order}}{dx^${order}} f_{${safeId}}(x)`;
                    }

                    if (!isEvaluation) {
                        Calc.setExpression({
                            id: `plot-deriv-${safeId}`,
                            latex: `y = ${derivNotation}`,
                            color: "#2d70b3",
                            label: `f${order > 1 ? `^(${order})` : "'"}(x)`
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
                            color: "#2d70b3",
                            lineStyle: window.Desmos.Styles.DOTTED
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
                color: "#2d70b3",
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
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, latex: value } : e));
        processExpression(id, value);
    };

    const addExpr = () => {
        const id = Math.random().toString(36).substr(2, 9);
        setExpressions([...expressions, { id, latex: "" }]);
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
                                <div className="mt-2.5 text-[10px] font-mono opacity-30 select-none w-4 text-center">{i + 1}</div>
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
                                            fontSize: '0.95rem',
                                            '--caret-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                            '--smart-fence-color': resolvedTheme === 'dark' ? '#fff' : '#1a1a1a',
                                            '--smart-fence-opacity': '1',
                                            color: resolvedTheme === 'dark' ? '#fff' : '#1a1a1a'
                                        } as React.CSSProperties}
                                    >
                                        {expr.latex}
                                    </math-field>
                                </div>
                                {expr.result && (
                                    <div className="flex items-center justify-center px-2 py-0.5 bg-primary/10 text-primary font-mono text-xs rounded select-all whitespace-nowrap self-center">
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
                </div>
            </div>
        </div>
    );
}