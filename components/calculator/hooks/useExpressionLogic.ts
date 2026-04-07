
import { useState, useRef, useEffect } from "react";
import { MathExpression, VisibilityMode } from "../types";
import { getNextColor } from "../../../utils/colors";
import { computeSymbolicDerivative, computeSymbolicIntegral } from "../../../utils/symbolic-math";
import { logHumanInput } from '../../../utils/latexToHuman';

// Helper to determine if parent curve should be visible based on mode
const isParentVisible = (mode: VisibilityMode): boolean => mode === 'all' || mode === 'parent';
// Helper to determine if operated curve (derivative/integral) should be visible based on mode
const isOperatedVisible = (mode: VisibilityMode): boolean => mode === 'all' || mode === 'operated';

export const useExpressionLogic = (calculatorInstance: React.MutableRefObject<any>) => {
    const helpersRef = useRef<{ [key: string]: any }>({});
    // Track when visibility update is in progress to prevent re-processing
    const visibilityUpdateInProgress = useRef<Set<string>>(new Set());
    const [expressions, setExpressions] = useState<MathExpression[]>([
        { id: "1", latex: "", color: "#2d70b3", visible: true, visibilityMode: 'all' },
    ]);
    const [debugInfo, setDebugInfo] = useState<string>("Ready");
    const [legendOpen, setLegendOpen] = useState(true);

    // ==========================================
    //      THE LOGIC: SMART TRANSFORMER
    // ==========================================
    const processExpression = (id: string, rawLatex: string, color: string, visible: boolean = true, visibilityMode: VisibilityMode = 'all', sliderBounds?: { min: string, max: string, step: string }, isAreaMode: boolean = false) => {
        // CRITICAL: Skip if visibility update is in progress
        if (visibilityUpdateInProgress.current.has(id)) {
            return;
        }

        // Log the raw LaTeX and human-readable form immediately (before any cleaning)
        try { logHumanInput(id, rawLatex); } catch (e) { /* noop */ }
        
        const Calc = calculatorInstance.current;
        if (!Calc) return;

        // 1. Generate Safe Variable ID
        const safeId = `E${id.replace(/-/g, "")}`;

        // 2. Clear All Associated Expressions (including main id to prevent stale curves
        //    when switching from plain expression to derivative/integral mode)
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

        if (!rawLatex || typeof rawLatex !== 'string' || !rawLatex.trim()) {
            setExpressions(prev => prev.map(e => e.id === id ? { ...e, result: undefined } : e));
            Calc.removeExpression({ id: id });
            return;
        }

        // 3. Minimal Cleaning
        // We only normalize things that Desmos strictly hates.
        let clean = rawLatex
            // Strip $$ or $ math delimiters that AI sometimes wraps expressions in
            .replace(/^\$\$?\s*/g, "").replace(/\s*\$\$?$/g, "")
            // CRITICAL: Convert LaTeX curly braces to Desmos-compatible left/right braces FIRST
            // MathLive converts { } to \lbrace \rbrace for visual braces (piecewise/domain)
            // Desmos needs \left\{ and \right\} for visual braces to render properly
            // This must be the FIRST replacement to catch raw input
            .replace(/\\+left\s*\\+lbrace/g, '\\left\\{')
            .replace(/\\+right\s*\\+rbrace/g, '\\right\\}')
            .replace(/\\+left\s*\\+\{/g, '\\left\\{')
            .replace(/\\+right\s*\\+\}/g, '\\right\\}')
            .replace(/\\+lbrace/g, '\\left\\{')
            .replace(/\\+rbrace/g, '\\right\\}')
            // NOTE: Do not globally replace \{ because it might conflict if it's already \left\{
            .replace(/(?<!\\left)\\+\{/g, '\\left\\{')
            .replace(/(?<!\\right)\\+\}/g, '\\right\\}')
            // Clean up MathLive's extra grouping braces around piecewise
            // Case 1: {\left\{ ... }\right\}
            .replace(/\{\s*\\left\\\{([^]*?)\}\s*\\right\\\}/g, '\\left\\{$1\\right\\}')
            // Case 2: {\left\{ ... \right\}}
            .replace(/\{\s*\\left\\\{([^]*?)\\right\\\}\s*\}/g, '\\left\\{$1\\right\\}')
            .replace(/\\bigm/g, "") // Fix for \bigm| issue
            .replace(/\\!/g, "")
            .replace(/\\,/g, " ").replace(/\\:/g, " ").replace(/\\;/g, " ")
            .replace(/\\limits/g, "")
            .replace(/\\differentialD/g, "d")
            // Normalize big delimiter variants (\bigl, \bigr, \Bigl, \Bigr, \Biggl, \Biggr)
            // Desmos ONLY supports () for grouping — [ ] and { } do NOT work as grouping delimiters!
            // So ALL bracket types (round, square, curly) must become plain ( )
            // EXCEPT: We must NOT convert \{ and \} here because they may be domain restrictions
            // The domain restriction handler will deal with them later
            .replace(/\\[Bb]igg?[lr]\s*\(/g, "(")
            .replace(/\\[Bb]igg?[lr]\s*\)/g, ")")
            .replace(/\\[Bb]igg?[lr]\s*\[/g, "(")
            .replace(/\\[Bb]igg?[lr]\s*\]/g, ")")
            .replace(/\\[Bb]igg?[lr]\s*\|/g, "|")
            // Handle various dx patterns from different input methods
            .replace(/\\mathrm\{dx\}/g, "dx")  // \mathrm{dx} -> dx (sidebar insertion)
            .replace(/\\mathrm\{d\}([a-zA-Z])/g, "d$1") // \mathrm{d}x -> dx
            .replace(/\\mathrm\{d([a-zA-Z])\}/g, "d$1")  // \mathrm{dy}, \mathrm{dt} etc
            .replace(/\\mathrm\{d\}/g, "d")  // \mathrm{d}x -> dx (virtual keyboard) -- FALLBACK
            .replace(/\\text\{dx\}/g, "dx")  // \text{dx} -> dx
            .replace(/\\text\{d\}/g, "d")  // \text{d}x -> dx
            .replace(/\\operatorname\{d\}([a-zA-Z])/g, "d$1")  // \operatorname{d}x -> dx
            .replace(/\\operatorname\{d\}/g, "d")  // \operatorname{d} -> d (fallback)
            .replace(/\\dfrac/g, "\\frac")
            .trim();

        // ==========================================
        // FIX MATHLIVE BROKEN FUNCTION NAMES
        // ==========================================
        // MathLive sometimes breaks up or wraps function names in complex ways
        // e.g., \operatorname{\mathrm{arccsc}}, arc\cot, cs\operatorname{\mathrm{ch}}

        // Fix broken hyperbolic assemblies: cs\operatorname{\mathrm{ch}} → \csch etc.
        clean = clean
            .replace(/cs\\operatorname\{\\mathrm\{ch\}\}/g, '\\csch')
            .replace(/se\\operatorname\{\\mathrm\{ch\}\}/g, '\\sech')
            .replace(/co\\operatorname\{\\mathrm\{th\}\}/g, '\\coth');

        // Handle nested \operatorname{\mathrm{...}} → \... (MathLive wraps unknown funcs)
        clean = clean.replace(/\\operatorname\{\\mathrm\{([^}]+)\}\}/g, '\\$1');

        // Handle \operatorname{\func} → \func (another MathLive variant)
        clean = clean.replace(/\\operatorname\{(\\[a-zA-Z]+)\}/g, '$1');

        // Handle \operatorname{arc} → arc (plain text prefix)
        clean = clean.replace(/\\operatorname\{arc\}/g, 'arc');
        
        // Handle \text{arc} and \mathrm{arc} generated by MathLive fallback
        clean = clean.replace(/\\text\{arc\}\s*/g, 'arc');
        clean = clean.replace(/\\mathrm\{arc\}\s*/g, 'arc');

        // Convert \operatorname{func} → \func for trig/hyperbolic Desmos compatibility
        clean = clean.replace(/\\operatorname\{((?:arc)?(?:sin|cos|tan|cot|sec|csc)h?|sinh|cosh|tanh|coth|sech|csch)\}/g, '\\$1');

        // Reassemble broken inverse trig/hyp: arc\func → \arcfunc
        // Handle hyperbolic FIRST to prevent partial matching (arcsinh before arcsin)
        clean = clean
            .replace(/arc\\(sinh|cosh|tanh|coth|sech|csch)/g, '\\arc$1')
            .replace(/arc\\(sin|cos|tan|cot|sec|csc)/g, '\\arc$1');

        // Fix bare broken hyp after operatorname cleanup: cs\ch → \csch etc.
        clean = clean
            .replace(/(^|[^a-zA-Z\\])cs\\ch/g, '$1\\csch')
            .replace(/(^|[^a-zA-Z\\])se\\ch/g, '$1\\sech')
            .replace(/(^|[^a-zA-Z\\])co\\th/g, '$1\\coth');

        // Reassemble broken \trig<space>h → \trigh (hyperbolic functions)
        // MathLive splits \coth → \cot + h, \arctanh → \arctan + h, etc.
        // Safe: MathLive-known hyp commands (\sinh, \cosh, \tanh) have no space
        // Inverse forms first (longer match prevents \arcsin h matching before \arcsec h)
        clean = clean
            .replace(/\\(arcsin|arccos|arctan|arccot|arcsec|arccsc)(\s+)h/g, '\\$1h')
            .replace(/\\(sin|cos|tan|cot|sec|csc)(\s+)h/g, '\\$1h');

        // Ensure reassembled hyperbolic names don't stick to their argument variable
        // \cothx → \coth x, \arctanhx → \arctanh x
        clean = clean.replace(/\\(arcsinh|arccosh|arctanh|arccoth|arcsech|arccsch|sinh|cosh|tanh|coth|sech|csch)([a-zA-Z])/g, '\\$1 $2');

        // Ensure e^ exponents are properly braced for Desmos (safety normalization)
        // e^x → e^{x} for single char without braces
        clean = clean.replace(/(^|[^a-zA-Z\\])e\^([a-zA-Z0-9])(?=[^a-zA-Z0-9{]|$)/g, '$1e^{$2}');

        // Fix Logarithm bases: \log_5 10 -> \log_{$1} 10
        clean = clean.replace(/\\log_(\d+)/g, "\\log_{$1}");

        // ==========================================
        // NORMALIZE ROUND PARENTHESES FOR DESMOS
        // ==========================================
        // Desmos handles both \left(...\right) and plain (...) parentheses
        // MathLive often outputs \left(...\right) for everything
        // For user-defined functions like f(x), g(x), Desmos works better with plain ()
        // We normalize \left( and \right) to plain parentheses
        // This ensures expressions like f(x)+g(x) work correctly
        // Built-in functions like \sin(x) work fine with plain parentheses too
        // Convert all \left/\right bracket variants that Desmos can't use for grouping.
        // Desmos ONLY supports () — so \left[ \right] and \left\{ \right\} must also become ( )
        // We do NOT convert \left| here — those are absolute values, handled below.
        clean = clean
            .replace(/\\left\(/g, '(')
            .replace(/\\right\)/g, ')')
            .replace(/\\left\[/g, '(')
            .replace(/\\right\]/g, ')');

        // ==========================================
        // UNIVERSAL FIX: ANY FUNCTION FOLLOWED BY \left DELIMITER
        // ==========================================
        // Desmos cannot parse \func\left|...\right|, \func\left[...\right]
        // directly — it needs \func(\left|...\right|) with explicit outer parens.
        // This applies to ANY function: \ln, \sin, \cos, \sqrt, \sec, \exp, f, g, h, etc.
        //
        // NOTE: We DO NOT handle \left\{ ... \right\} here because that would break
        // domain restrictions and piecewise functions. Domain restrictions use {...}
        // at the end of expressions, and piecewise functions use {...} with colons.
        // These need to be preserved as-is for Desmos.
        //
        // Pattern matched: \word\s*\left DELIM ... \right DELIM
        // → \word(\left DELIM ... \right DELIM)
        const wrapFuncDelimiter = (s: string): string => {
            // Pairs: [openToken, closeToken, openLen, closeLen]
            // NOTE: We only handle | pipes here, NOT curly braces
            // Curly braces are reserved for domain restrictions and piecewise
            const pairs: [string, string, number, number][] = [
                ['\\left|',  '\\right|',  6, 7],
            ];

            let result = s;

            for (const [openTok, closeTok, openLen, closeLen] of pairs) {
                // Match: any \word (or single letter) optionally followed by spaces, then openTok
                // The \word can be: \ln, \sin, \cos, \sec, \sqrt, \operatorname{...}, etc.
                // We also match a plain letter (user-defined function like f, g, h)
                const pattern = new RegExp(
                    '(\\\\[a-zA-Z]+(?:\\{[^}]*\\})?|(?<![a-zA-Z])[a-zA-Z])\\s*' +
                    openTok.replace(/[\\|]/g, '\\$&'),
                    'g'
                );

                let match: RegExpExecArray | null;
                while ((match = pattern.exec(result)) !== null) {
                    const matchStart = match.index;
                    const delimStart = matchStart + match[0].length - openLen;

                    // Find the matching close token, tracking nested open tokens
                    let depth = 1;
                    let i = delimStart + openLen;
                    while (i < result.length && depth > 0) {
                        if (result.substring(i).startsWith(openTok))  { depth++; i += openLen; }
                        else if (result.substring(i).startsWith(closeTok)) { depth--; if (depth === 0) break; i += closeLen; }
                        else { i++; }
                    }

                    if (depth === 0) {
                        const closeEnd = i + closeLen;
                        const innerBlock = result.substring(delimStart, closeEnd);
                        const funcPart   = result.substring(matchStart, delimStart);
                        const before     = result.substring(0, matchStart);
                        const after      = result.substring(closeEnd);
                        result = before + funcPart + '(' + innerBlock + ')' + after;
                        // Resume search after the newly inserted '(' to avoid infinite loops
                        pattern.lastIndex = before.length + funcPart.length + 1;
                    }
                }
            }
            return result;
        };
        clean = wrapFuncDelimiter(clean);

        // ==========================================
        // HANDLE MALFORMED \mathrm{} BLOCKS
        // ==========================================
        // Handle cases like \mathrm{\sin^2xd} where trig function is inside \mathrm{}
        // Extract trig functions from inside \mathrm{} blocks
        clean = clean
            // \mathrm{\sin^nx d} or \mathrm{\sin^{n}x d} -> \sin^{n}x d
            .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)\^\{?([^}\s]+)\}?([a-zA-Z])\s*d\}/g, '\\$1^{$2}$3 d')
            // \mathrm{\sinx d} -> \sin x d (no power)
            .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)([a-zA-Z])\s*d\}/g, '\\$1 $2 d')
            // \mathrm{\sin(expr)d} -> \sin(expr) d
            .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)\s*\(([^)]+)\)\s*d\}/g, '\\$1($2) d')
            // Generic fallback: remove remaining \mathrm{} wrappers
            .replace(/\\mathrm\{([^}]+)\}/g, '$1');

        // ========================================
        // ABSOLUTE VALUE NORMALIZATION (Comprehensive)
        // ========================================
        // Convert any \mathrm{abs}, \operatorname{abs}, \abs, or plain abs into \operatorname{abs}
        // which Desmos fully supports, including for nested patterns natively.
        clean = clean.replace(/\\mathrm\{\\?abs\}/g, "\\operatorname{abs}");
        clean = clean.replace(/\\abs(?![a-zA-Z])/g, "\\operatorname{abs}");
        clean = clean.replace(/(^|[^a-zA-Z\\])abs(?![a-zA-Z])/g, "$1\\operatorname{abs}");

        clean = clean.replace(/\\left\\vert\s*/g, "\\left|");
        clean = clean.replace(/\\right\\vert\s*/g, "\\right|");
        clean = clean.replace(/\\lvert\s*/g, "\\left|");
        clean = clean.replace(/\\rvert\s*/g, "\\right|");
        clean = clean.replace(/\\vert\s*/g, "|");

        // Evaluate ambiguous pipes |x| or nested pipes |x-|x|| heuristically.
        // Also tracks parenDepth so that a ) closing a paren that was open when | started
        // will auto-insert \right| first. Fixes: \ln(|\cos(x)) → \ln(\left|\cos(x)\right|)
        const convertSimplePipes = (str: string): string => {
            let result = str;
            result = result.replace(/\\left\|/g, "LEFT_PIPE_TOKEN");
            result = result.replace(/\\right\|/g, "RIGHT_PIPE_TOKEN");

            let finalStr = "";
            let pipeDepth = 0;
            let parenDepth = 0;
            // Stack: records parenDepth at which each | was opened
            const pipeOpenedAt: number[] = [];

            for (let i = 0; i < result.length; i++) {
                const char = result[i];

                if (char === '(') {
                    parenDepth++;
                    finalStr += char;
                } else if (char === ')') {
                    // Before reducing parenDepth, close any pipes that opened at a DEEPER level
                    // (i.e., inside the parentheses being closed)
                    // DON'T close pipes opened at the SAME level - those need explicit | closing
                    while (pipeOpenedAt.length > 0 &&
                           pipeOpenedAt[pipeOpenedAt.length - 1] > parenDepth) {
                        finalStr += "\\right|";
                        pipeOpenedAt.pop();
                        pipeDepth = Math.max(0, pipeDepth - 1);
                    }
                    parenDepth = Math.max(0, parenDepth - 1);
                    finalStr += char;
                } else if (char === '|') {
                    let prev = '';
                    for (let k = i - 1; k >= 0; k--) {
                        if (result[k] !== ' ') { prev = result[k]; break; }
                    }
                    let next = '';
                    for (let k = i + 1; k < result.length; k++) {
                        if (result[k] !== ' ') { next = result[k]; break; }
                    }

                    let isOpen = false;
                    if (pipeDepth === 0) {
                        isOpen = true;
                    } else {
                        if (/[-+*/=({<>,_^]/.test(prev)) {
                            isOpen = true;
                        } else if (/[0-9a-zA-Z)\]}]/.test(prev)) {
                            isOpen = false;
                        } else {
                            isOpen = /[0-9a-zA-Z(]/.test(next);
                        }
                    }

                    if (isOpen) {
                        finalStr += "\\left|";
                        pipeOpenedAt.push(parenDepth);
                        pipeDepth++;
                    } else {
                        finalStr += "\\right|";
                        if (pipeOpenedAt.length > 0) pipeOpenedAt.pop();
                        pipeDepth = Math.max(0, pipeDepth - 1);
                    }
                } else {
                    finalStr += char;
                }
            }

            finalStr = finalStr.replace(/LEFT_PIPE_TOKEN/g, "\\left|");
            finalStr = finalStr.replace(/RIGHT_PIPE_TOKEN/g, "\\right|");
            // Auto-close any remaining unclosed pipes at end of string
            while (pipeDepth > 0) {
                finalStr += "\\right|";
                pipeDepth--;
            }
            return finalStr;
        };
        clean = convertSimplePipes(clean);

        // Auto-prefix bare math function names with backslash for Desmos
        // IMPORTANT: Longer names (arcsin) must come BEFORE shorter ones (sin)
        // to prevent partial matching issues
        const funcs = [
            "arcsin", "arccos", "arctan", "arccot", "arcsec", "arccsc",
            "arcsinh", "arccosh", "arctanh", "arccoth", "arcsech", "arccsch",
            "sinh", "cosh", "tanh", "coth", "sech", "csch",
            "sin", "cos", "tan", "sec", "csc", "cot",
            "ln", "log", "exp"
        ];
        funcs.forEach(f => {
            const regex = new RegExp(`(^|[^\\\\a-zA-Z])(${f})(?![a-zA-Z])`, "g");
            clean = clean.replace(regex, "$1\\$2");
        });

        // 1. Fix Unicode pi to \pi
        clean = clean.replace(/π/g, "\\pi");
        
        // 2. Fix curly braces around left/right pipes inside absolute values (e.g. \left|{a}\right| -> \left|a\right|)
        // Handles up to 1 level of nested curly braces (like exponents)
        clean = clean.replace(/\\left\|\{([^{}]+|\{[^{}]*\})*\}\\right\|/g, (match) => {
            const inner = match.substring(7, match.length - 8);
            return `\\left|${inner}\\right|`;
        });

        // 3. Fix curly braces immediately following function expressions like \ln{(a^4)} -> \ln(a^4)
        // Handles up to 1 level of nested curly braces (like exponents)
        const mathFuncs = "ln|log|exp|sin|cos|tan|csc|sec|cot|arcsin|arccos|arctan|sinh|cosh|tanh|coth|sech|csch";
        clean = clean.replace(new RegExp(`\\\\(${mathFuncs})\\s*\\{([^{}]+|\\\\{[^{}]*\\\\})*\\}`, 'g'), (match, funcName) => {
            const startIdx = match.indexOf('{');
            const inner = match.substring(startIdx + 1, match.length - 1);
            return `\\${funcName} ${inner}`;
        });

        // ==========================================
        // DOMAIN/RANGE RESTRICTIONS - MUST PRESERVE CURLY BRACES
        // ==========================================
        // Domain restrictions like sin(x){-π < x < π} need to be preserved as-is
        // Check if the expression ends with a domain restriction pattern and preserve it
        // Pattern: expression followed by {condition} at the end
        
        // The curly braces were already converted at the start (lines 73-76)
        // Now check if this is a domain restriction and normalize the content inside
        
        // Now check if this is a domain restriction and handle it properly
        // Domain restriction patterns: function/domain or variable/domain at end
        // Examples: sin(x)\left\{-π < x < π\right\}, x^2\left\{0 < y < 4\right\}
        const hasDomainRestriction = /(\\.+|\w+)\\left\\{.*\\right\\}$/.test(clean);
        
        if (hasDomainRestriction) {
            // Check if the content inside the braces is a condition (has comparison operators)
            // Use a non-greedy match or match from the last \left\{ to ensure we don't grab too much
            const domainMatch = clean.match(/\\left\\{((?:(?!\\left\\{).)*)\\right\\}$/);
            if (domainMatch) {
                let innerContent = domainMatch[1];
                
                // Normalize common LaTeX to what Desmos understands
                // This must happen BEFORE checking for comparison operators
                let normalizedContent = innerContent
                    .replace(/\\le/g, '<=')
                    .replace(/\\ge/g, '>=')
                    .replace(/\\leq/g, '<=')
                    .replace(/\\geq/g, '>=')
                    .replace(/\\lt/g, '<')
                    .replace(/\\gt/g, '>')
                    .replace(/\\neq/g, '!=')
                    .replace(/\\ne/g, '!=')
                    .replace(/≠/g, '!=')
                    .replace(/≤/g, '<=')
                    .replace(/≥/g, '>=')
                    .replace(/π/g, '\\pi')
                    .replace(/θ/g, '\\theta');
                
                // Check if it looks like a domain condition (has <, >, ≤, ≥, =, !=)
                // Check the NORMALIZED content, not the original
                if (/[<>=!]/.test(normalizedContent)) {
                    // This IS a domain restriction - rebuild with normalized content
                    // Replace the exact match with normalized content and \left\{ \right\}
                    clean = clean.replace(domainMatch[0], '\\left\\{' + normalizedContent + '\\right\\}');
                }
            }
        }

        // ==========================================
        // PIECEWISE FUNCTIONS - HANDLE CURLY BRACES PROPERLY
        // ==========================================
        // Piecewise functions: {condition: value, default} - need to preserve braces
        // Check if this is a piecewise expression (has : inside braces)
        // Now it uses \left\{ and \right\}
        const isPiecewise = /\\left\\{.*:.*,.*\\right\\}/.test(clean) || /\\left\\{.*<.*:.*,.*/.test(clean) || /\\left\\{.*>.*:.*,.*/.test(clean);
        
        if (isPiecewise) {
            // Piecewise is already handled properly because it has \left\{ and \right\}
        }

        setDebugInfo(clean);

        // --- Helper: Robust Bounds Parser ---
        const parseBounds = (startIdx: number, str: string) => {
            try {
                let i = startIdx;
                let min = "", max = "";
                const skipSpace = () => { while (i < str.length && /\s/.test(str[i])) i++; };

                const parseGroup = () => {
                    skipSpace();
                    if (i >= str.length) return "";
                    if (str[i] === "{") {
                        let depth = 1;
                        i++;
                        const start = i;
                        while (i < str.length && depth > 0) {
                            if (str[i] === '{') depth++;
                            if (str[i] === '}') depth--;
                            i++;
                        }
                        if (depth > 0) return "";
                        return str.substring(start, i - 1);
                    }
                    if (str[i] === '\\') {
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

        try {
            // --- BRANCH A: Summation ---
            if (clean.startsWith("\\sum")) {
                const bounds = parseBounds(4, clean);
                if (bounds.min && bounds.max) {
                    Calc.setExpression({
                        id: `val-${safeId}`,
                        latex: `S_{${safeId}} = ${clean}`,
                        secret: true,
                        hidden: true
                    });
                    helperLatex = `S_{${safeId}}`;
                    handled = true;
                }
            }

            // --- BRANCH B: Definite/Indefinite Integral ---
            if (!handled && clean.startsWith("\\int")) {
                const bounds = parseBounds(4, clean);
                // Clean thin spaces (\,) and other spacing before parsing - they're just formatting
                const rest = clean.substring(bounds.end).trim()
                    .replace(/\\,/g, '')
                    .replace(/\\!/g, '')
                    .replace(/\s+/g, ' ')  // Normalize multiple spaces to single
                    .trim();
                
                // Match the differential at the end: d followed by variable (dx, dt, dy, etc.)
                // After cleaning, \mathrm{d}x and \mathrm{dx} are already converted to dx
                // So we just need to match: optional space, d, optional space, variable
                const varMatch = rest.match(/\s?d\s?(\\?[a-zA-Z])$/);

                if (varMatch) {
                    const rawVariable = varMatch[1];
                    // Build pattern to remove the differential from the expression
                    const dPattern = new RegExp(`\\s?d\\s?${rawVariable.replace('\\', '\\\\')}$`);
                    const body = rest.replace(dPattern, '').trim();

                    if (bounds.min && bounds.max) {
                        const cleanMin = bounds.min.replace(/\\left\s*/g, "").replace(/\\right\s*/g, "").trim();
                        const cleanMax = bounds.max.replace(/\\left\s*/g, "").replace(/\\right\s*/g, "").trim();

                        let plotBody = rawVariable === 'x' ? body : body.split(rawVariable).join("x");
                        plotBody = plotBody
                            .replace(/\\left\s*/g, "(")
                            .replace(/\\right\s*/g, ")")
                            .replace(/\\bigl\s*/g, "(")
                            .replace(/\\bigr\s*/g, ")")
                            .replace(/\\Bigl\s*/g, "(")
                            .replace(/\\Bigr\s*/g, ")")
                            .trim();

                        // Remove outer parens if they are just wrapping the whole expression
                        // Remove outer parens if they are just wrapping the whole expression
                        while (plotBody.startsWith('(') && plotBody.endsWith(')')) {
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
                            } else {
                                break;
                            }
                        }

                        if (plotBody) {
                            Calc.setExpression({
                                id: `curve-${safeId}`,
                                latex: `y = ${plotBody}`,
                                color: color,
                                lineWidth: 2,
                                lineStyle: window.Desmos.Styles.DOTTED,
                                label: "Parent Function",
                                showLabel: true,
                                hidden: !isParentVisible(visibilityMode)
                            });

                            // For Area Mode: We visualize the area being calculated
                            // If isAreaMode is true, the user wants |f(x)| area.
                            // The shading should represent that.
                            // Standard integral: between curve and axis, signed (min(0, f(x)) to max(0, f(x)))
                            // Area: always positive. Visually |f(x)| area is same geometry, just summed positively.
                            // So visual shading can remain same (showing the region), but maybe filled differently?
                            // Actually, standard shading `0 <= y <= f(x)` or `f(x) <= y <= 0` creates the visual.
                            // Let's stick to standard shading but maybe change opacity or label?
                            
                            const shadeLatex = `\\min(0, ${plotBody}) \\le y \\le \\max(0, ${plotBody}) \\left\\{ ${cleanMin} \\le x \\le ${cleanMax} \\right\\}`;
                            Calc.setExpression({
                                id: `shade-${safeId}`,
                                latex: shadeLatex,
                                color: color,
                                fillOpacity: 0.3,
                                lines: false,
                                hidden: !isOperatedVisible(visibilityMode)
                            });
                        }

                        // Calculate Integral Value OR Area Value
                        // If Area Mode: Integral of |f(x)|
                        // If Integral Mode: Integral of f(x)
                        
                        // If Area Mode: Integral of |f(x)|
                        // If Integral Mode: Integral of f(x)
                        
                        let calculationLatex = clean;
                        if (isAreaMode) {
                            // Inject absolute value around the body of the integral
                            // We need to enclose the integrand in \left| ... \right|
                            
                            // Reconstruct the integral string for calculation
                            calculationLatex = `\\int_{${bounds.min}}^{${bounds.max}} \\left| ${body} \\right| ${varMatch[0]}`;
                        } else {
                            // Use original clean string for normal integral
                            calculationLatex = clean;
                        }

                        Calc.setExpression({
                            id: `val-${safeId}`,
                            latex: `I_{${safeId}} = ${calculationLatex}`,
                            secret: true,
                            hidden: true
                        });
                        helperLatex = `I_{${safeId}}`;
                        handled = true;
                    } else {
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
                            showLabel: true,
                            hidden: !isParentVisible(visibilityMode)
                        });
                        const bodyWithT = body.split(rawVariable).join("t");
                        Calc.setExpression({
                            id,
                            latex: `y = \\int_{0}^{x} ${bodyWithT} dt`,
                            color: color,
                            lineStyle: window.Desmos.Styles.SOLID,
                            label: "Integral",
                            showLabel: true,
                            hidden: !isOperatedVisible(visibilityMode)
                        });
                        handled = true;
                    }
                }
            }

            // --- BRANCH C: Derivative (Symbolic & Numeric) ---
            if (!handled && clean.startsWith("\\frac")) {
                // Updated regex to handle various derivative notations:
                // - \frac{d}{dx}f(x), \frac{d^2}{dx^2}f(x), \frac{d^{2}}{dx^{2}}f(x)
                // - With or without spaces, with or without braces around exponent
                // Groups: [1]=^n or ^{n}, [2]=n (order), [3]=variable, [4]=^n or ^{n}, [5]=n, [6]=content
                const derivRegex = /^\\frac\s*\{\s*d(\^\{?([0-9]+)\}?)?\s*\}\s*\{\s*d\s*(\\?[a-zA-Z]+)(\^\{?([0-9]+)\}?)?\s*\}\s*(.+)$/;
                const derivMatch = clean.match(derivRegex);

                if (derivMatch) {
                    const order = derivMatch[2] ? parseInt(derivMatch[2]) : 1;
                    const variable = derivMatch[3];
                    let content = derivMatch[6];
                    
                    // Clean up placeholder notation that might be present
                    content = content.replace(/\\placeholder\{[^}]*\}/g, '').trim();

                    let isEvaluation = false;
                    let targetVal = "";
                    let body = content;

                    // Handle evaluation notation: |_{x=2} or \bigm|_{x=2} (bigm already removed)
                    // Look for |_{ pattern for evaluation point
                    const barIndex = content.lastIndexOf("|_{");
                    if (barIndex !== -1 && content.trim().endsWith("}")) {
                        const possibleBody = content.substring(0, barIndex).trim();
                        const evalPart = content.substring(barIndex + 3, content.length - 1);
                        const parts = evalPart.split("=");
                        // Variable might be 'x' or '\theta' etc - compare without backslash
                        const cleanVar = variable.replace(/^\\/,'');
                        const evalVar = parts[0].trim().replace(/^\\/,'');
                        if (parts.length === 2 && evalVar === cleanVar) {
                            isEvaluation = true;
                            targetVal = parts[1].trim();
                            body = possibleBody;
                        }
                    }

                    // Use clean variable for Desmos (remove backslash if present)
                    const desmosVar = variable.replace(/^\\/,'');
                    
                    // Function definition - must be hidden to prevent Desmos from plotting it
                    Calc.setExpression({
                        id: `funcD-${safeId}`,
                        latex: `f_{${safeId}}(${desmosVar}) = ${body}`,
                        secret: true,
                        hidden: true
                    });

                    // Parent function curve (dotted line)
                    Calc.setExpression({
                        id: `plot-orig-${safeId}`,
                        latex: `y = f_{${safeId}}(x)`,
                        lineStyle: window.Desmos.Styles.DOTTED,
                        color: color,
                        label: "Parent Function",
                        showLabel: true,
                        hidden: !isParentVisible(visibilityMode)
                    });

                    let derivNotation = "";
                    if (order <= 3) {
                        let primes = "";
                        for (let k = 0; k < order; k++) primes += "'";
                        derivNotation = `f_{${safeId}}${primes}(x)`;
                    } else {
                        derivNotation = `\\frac{d^${order}}{dx^${order}} f_{${safeId}}(x)`;
                    }

                    // Derivative curve (solid line)
                    const derivLabel = `Derivative: f${order > 1 ? `^(${order})` : "'"}(x)`;
                    Calc.setExpression({
                        id: `plot-deriv-${safeId}`,
                        latex: `y = ${derivNotation}`,
                        color: color,
                        label: derivLabel,
                        showLabel: true,
                        lineStyle: window.Desmos.Styles.SOLID,
                        hidden: !isOperatedVisible(visibilityMode)
                    });

                    if (isEvaluation) {
                        let valLatex = "";
                        if (order <= 3) {
                            let primes = "";
                            for (let k = 0; k < order; k++) primes += "'";
                            valLatex = `f_{${safeId}}${primes}(${targetVal})`;
                        } else {
                            valLatex = `\\frac{d^${order}}{d${desmosVar}^${order}} f_{${safeId}}(${targetVal})`;
                        }
                        Calc.setExpression({
                            id: `val-${safeId}`,
                            latex: `V_{${safeId}} = ${valLatex}`,
                            secret: true,
                            hidden: true
                        });
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

            // ==========================================
            // AUTO-GRAPH EXPRESSIONS THAT NEED y=
            // ==========================================
            // In Desmos API, expressions like "f(x)+2" or "sin(x)" need "y=" prefix to be graphed
            // But definitions like "f(x)=x^2" or "a=5" should NOT get the prefix
            // Check if expression:
            // 1. Contains x (or is a function of x)
            // 2. Does NOT contain = or inequality operators (not a definition/relation)
            // 3. Is not just a number
            const hasEquals = finalLatex.includes('=');
            // Use negative lookahead to prevent \left matching as \le, \geq matching as \ge etc.
            const hasInequality = /\\leq|\\geq|\\le(?![a-z])|\\ge(?![a-z])|\\lt(?![a-z])|\\gt(?![a-z])|<|>/.test(finalLatex);
            const hasX = /[^a-zA-Z]x[^a-zA-Z]|^x[^a-zA-Z]|[^a-zA-Z]x$|^x$/.test(finalLatex) || 
                         finalLatex.includes('(x)');  // Function calls like f(x), g(x), sin(x)
            const isJustNumber = /^-?\d+\.?\d*$/.test(finalLatex.trim());
            
            // If it's an expression with x but no equals/inequality, add y= to make it graph
            // Inequalities like |x-2| ≤ 3 should be passed to Desmos as-is (it handles them natively)
            if (!hasEquals && !hasInequality && hasX && !isJustNumber) {
                finalLatex = `y=${finalLatex}`;
                console.log(`[DEBUG] Added y= prefix: "${finalLatex}"`);
            }

            console.log(`[DEBUG] Setting expression id=${id}, latex="${finalLatex}"`);

            // FORCE REMOVAL: Clean up the expression ID before setting it again.
            // This clears any "defined in more than one place" errors that might be stuck.
            Calc.removeExpression({ id: id });
            
            Calc.setExpression({
                id: id,
                latex: finalLatex,
                color: color,
                showLabel: true,
                hidden: visibilityMode === 'none' || !visible,
                ...(sliderBounds ? { sliderBounds } : {})
            });
            
            // Debug: Show all expressions in Desmos right now
            setTimeout(() => {
                const allExprs = Calc.getExpressions();
                console.log('[DEBUG] Current Desmos state:', allExprs.map((e: any) => `${e.id}: ${e.latex}`));
            }, 100);
        }

        // --- 4. Result Calculation & Variable Detection (Universal Helper) ---
        
        // Helper to extract variables from latex
        const extractVariables = (latex: string): string[] => {
             let s = latex;

             // 0. Handle function definitions: h(x)=..., f(x,y)=...
             // The function name is being DEFINED, not used as a free variable
             const funcDefMatch = s.match(/^([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\s*\(([^)]*?)\)\s*=/);
             if (funcDefMatch) {
                 // Only analyze the RHS (after the '=')
                 const eqIdx = s.indexOf('=');
                 s = eqIdx >= 0 ? s.substring(eqIdx + 1) : s;
             }

             // 1. Remove standard derivative notation FIRST: \frac{d}{dx}, \frac{d^2}{dx^2}
             // This removes the entire derivative operator block so 'd' inside it is gone.
             // Updated regex to handle \theta (d\theta) and other commands
             s = s.replace(/\\frac\s*\{\s*d(\^\{?[0-9]+\}?)?\s*\}\s*\{\s*d(\\[a-zA-Z]+|[a-zA-Z])(\^\{?[0-9]+\}?)?\s*\}/g, '');
             
             // Remove partial derivatives: \frac{\partial}{\partial x}
             s = s.replace(/\\frac\s*\{\s*\\partial(\^\{?[0-9]+\}?)?\s*\}\s*\{\s*\\partial(\\[a-zA-Z]+|[a-zA-Z])(\^\{?[0-9]+\}?)?\s*\}/g, '');

             // 2. Remove standard differentials (dx, dy, dt, dtheta) that are likely operators
             // Revert to safer specific list to avoid destroying words starting with d (like 'distance' -> 'istance' if i was in set)
             // We use a list of common differentials.
             const differentials = [
                'dx', 'dy', 'dt', 'du', 'dv', 'dw', 'dz', 'dr', 'ds', 'dp', 'dq', 'dk', 'dn', 'dm', 
                'd\\theta', 'd\\alpha', 'd\\beta', 'd\\gamma', 'd\\phi', 'd\\rho'
             ];
             differentials.forEach(diff => {
                 // Use a global replace. Escape special regex chars if any (backslash is already double escaped in string)
                 // straightforward replaceAll equivalent
                 s = s.split(diff).join('');
             });
             
             // Remove commands (\arcsin, \frac, etc.)
             s = s.replace(/\\[a-zA-Z]+/g, '');
             
             // Remove known constants and functions (bare text versions)
             // Includes inverse trig: arcsin, arccos, arctan, arccot, arcsec, arccsc
             // Includes inverse hyperbolic: arcsinh, arccosh, arctanh, arccoth, arcsech, arccsch
             // Longer names first to avoid partial matching issues
             s = s.replace(/(arcsinh|arccosh|arctanh|arccoth|arcsech|arccsch|arcsin|arccos|arctan|arccot|arcsec|arccsc|arsinh|arcosh|artanh|arcoth|arsech|arcsch|sinh|cosh|tanh|coth|sech|csch|sin|cos|tan|cot|sec|csc|ln|log|exp|sqrt|abs|pi|theta|floor|ceil|round|sgn|min|max|diff|limit|sum|prod|int|oint|iint|iiint|gd|arc|step|sign|mod|nCr|nPr|gcd|lcm)/g, '');
             
             // Remove independent variables that don't need sliders
             // Note: x, y, r, t are context variables usually
             s = s.replace(/(x|y|r|t)/g, '');
             
             // Remove the bare letter 'e' (Euler's number) and 'd' (differential operator)
             // 'd' alone should not be treated as a slider variable
             s = s.replace(/\b[de]\b/g, '');
             // Also remove isolated single 'd' or 'e' that remain after other removals
             // (they often appear as leftover from derivative/differential notation)
             s = s.replace(/(?:^|[^a-zA-Z])d(?=[^a-zA-Z]|$)/g, (match) => match.replace('d', ''));
             s = s.replace(/(?:^|[^a-zA-Z])e(?=[^a-zA-Z]|$)/g, (match) => match.replace('e', ''));
             
             // Find remaining single letters
             const matches = s.match(/[a-zA-Z]/g);
             return matches ? Array.from(new Set(matches)) : [];
        };

        const usedVars = extractVariables(clean);
        
        // Find undefined variables
        const existingExprs = Calc.getExpressions();
        // Get list of defined variables (LHS of assignments)
        const definedVars = new Set<string>();
        existingExprs.forEach((e: any) => {
            // Check if it's a definition like a=... or f(x)=...
            // Simple check: splitting by =
            if (e.latex && e.latex.includes('=') && e.id !== id && e.id !== safeId) {
                const lhs = e.latex.split('=')[0].trim();
                // Clean LHS potentially
                 const cleanLhs = lhs.replace(/\\left|\\right/g, '').trim();
                 // If it looks like a simple variable like "a" or "z_1"
                 if (/^[a-zA-Z](_\{?[a-zA-Z0-9]+\}?)?$/.test(cleanLhs)) {
                     definedVars.add(cleanLhs);
                 }
                 // Also recognize function definitions like f(x), g(x,y), h(t)
                 // The function name is defined and should not be treated as missing
                 const funcMatch = cleanLhs.match(/^([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\s*\(/);
                 if (funcMatch) {
                     definedVars.add(funcMatch[1]);
                 }
            }
        });
        // Also check the CURRENT expression — if it's a function definition, its own
        // name should not be flagged as missing (e.g., h(x)=x^2 should not show 'h')
        const ownLhs = clean.split('=')[0]?.trim().replace(/\\left|\\right/g, '').trim();
        const ownFuncMatch = ownLhs?.match(/^([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\s*\(/);
        if (ownFuncMatch) {
            definedVars.add(ownFuncMatch[1]);
        }

        const missing = usedVars.filter(v => !definedVars.has(v));
        
        // Update state with missing variables
        // We use a timeout to avoid react state update during render cycle issues if any,
        // and to bundle updates? No, direct update.
        // But we need to update ONLY if changed to avoid loops.
        // We can't easily check 'prev' here inside processExpression without access to current state variable "expressions".
        // But we can blindly update if we are careful. 
        // Better: handleInput updates local state. processExpression is side effect.
        // We can dispatch a state update.
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, missingVariables: missing } : e));

        // Result Calculation Logic
        // Only create helper if NO INDEPENDENT variables (like x, y) are present
        
        // Check for independent variables (graphing vars)
        // Note: 'y' is allowed in implicit eq, but we want result for '2z'.
        const checkStr = clean
            .replace(/\\[a-zA-Z]+/g, '') 
            .replace(/(sin|cos|tan|cot|sec|csc|ln|log|exp|sqrt|abs|pi|e|theta|floor|ceil|round|sgn|min|max|gcd|lcm|mod|nCr|nPr)/g, '');
        
        // We consider x, y, r, t, theta as graph paramters -> no scalar result
        const hasGraphVars = /(x|y|r|t)/.test(checkStr);
        const isDefinition = clean.includes('=');

        // Check for simple slider definition: "a = 2"
        let isSliderDef = false;
        let sliderVar = "";
        if (isDefinition) {
            // Match plain variable assignment: a = ... or a_{1} = ...
            // Reject if it's a function f(x)= or if the var is x/y
            const match = clean.match(/^([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\s*=/);
            if (match && !/^(x|y|r|t)$/.test(match[1])) {
                isSliderDef = true;
                sliderVar = match[1];
            }
        }
        
        // Check for y = constant definition (e.g., y = 2a)
        let isYConstant = false;
        let constantRHS = "";
        if (isDefinition) {
             const yMatch = clean.match(/^y\s*=\s*(.*)$/);
             if (yMatch) {
                 const rhs = yMatch[1];
                 // Check if RHS has graph vars (x, r, t) - excluding y since we are defining it
                 // We remove text commands and constants first to avoid false positives
                 const checkRHS = rhs
                    .replace(/\\[a-zA-Z]+/g, '')
                    .replace(/(sin|cos|tan|cot|sec|csc|ln|log|exp|sqrt|abs|pi|e|theta)/g, '');
                 
                 if (!/(x|r|t)/.test(checkRHS)) {
                      isYConstant = true;
                      constantRHS = rhs;
                 }
             }
        }

        // Observe if special handler used OR (not a definition AND not a function of x/y)
        // OR if it is a slider definition (to sync value back)
        // OR if it is a y=constant expression
        const shouldObserve = (handled && helperLatex !== clean) 
            || (!isDefinition && !hasGraphVars) 
            || isSliderDef
            || isYConstant;

        if (shouldObserve) {        
            try {
                // If slider, watch the variable. 
                // If y=constant, watch the RHS.
                // Else watch the expression.
                const exprToWatch = isSliderDef ? sliderVar : (isYConstant ? constantRHS : helperLatex);
                const helper = Calc.HelperExpression({ latex: exprToWatch });
                helpersRef.current[safeId] = helper;

                helper.observe('numericValue', () => {
                    const val = helper.numericValue;
                    setExpressions(prev => prev.map(e => {
                        if (e.id === id) {
                            if (val !== undefined && !isNaN(val) && isFinite(val)) {
                                const display = Math.abs(val) < 1e-10 ? "0" :
                                    Math.abs(val) > 1e10 ? val.toExponential(4) :
                                        parseFloat(val.toFixed(6)).toString();
                                
                                const update: Partial<MathExpression> = { result: display };
                                
                                // Sync slider value back to latex if playing
                                // This allows the slider to move visually
                                if (isSliderDef && e.isPlaying) {
                                    update.latex = `${sliderVar}=${display}`;
                                }
                                
                                return { ...e, ...update };
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
        }
    };

    const handleInput = (id: string, value: string) => {
        // Ensure value is a string (safeguard against non-string inputs)
        const safeValue = typeof value === 'string' ? value : '';

        const expr = expressions.find(e => e.id === id);
        
        // Skip processing if latex hasn't changed (prevents re-processing on visibility changes)
        if (expr && expr.latex === safeValue) {
            return;
        }
        
        // Also skip if visibility update is in progress for this expression
        if (visibilityUpdateInProgress.current.has(id)) {
            return;
        }
        
        const currentColor = expr ? expr.color : "#2d70b3";
        const currentVisible = expr ? expr.visible : true;
        const currentMode = expr ? expr.visibilityMode : 'all';
        const currentSliderBounds = expr ? expr.sliderBounds : undefined;
        // Keep current Area Mode if it exists
        const currentAreaMode = expr ? (expr.isAreaMode || false) : false;
        
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, latex: safeValue } : e));
        processExpression(id, safeValue, currentColor, currentVisible, currentMode, currentSliderBounds, currentAreaMode);
    };

    const handleColorChange = (id: string, newColor: string) => {
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, color: newColor } : e));
        const expr = expressions.find(e => e.id === id);
        if (expr) processExpression(id, expr.latex, newColor, expr.visible, expr.visibilityMode, expr.sliderBounds, expr.isAreaMode);
    };

    const updateSliderBounds = (id: string, min: string, max: string, step: string = "") => {
        const bounds = { min, max, step };
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, sliderBounds: bounds } : e));
        if (calculatorInstance.current) {
             calculatorInstance.current.setExpression({ id, sliderBounds: bounds });
        }
    };
    
    const setExpressionPlaying = (id: string, playing: boolean) => {
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, isPlaying: playing } : e));
        if (calculatorInstance.current) {
             calculatorInstance.current.setExpression({ id, playing });
        }
    };

    const addExpr = (initialLatex: string = "", customColor?: string) => {
        const id = Math.random().toString(36).substr(2, 9);
        const lastExpr = expressions[expressions.length - 1];
        const newColor = customColor || getNextColor(lastExpr?.color);
        setExpressions(prev => [...prev, { 
            id, 
            latex: initialLatex, 
            color: newColor, 
            visible: true, 
            visibilityMode: 'all',
            missingVariables: [],
            isAreaMode: false
        }]);
        // If we have initial latex, render it immediately
        if (initialLatex) {
             setTimeout(() => processExpression(id, initialLatex, newColor, true, 'all'), 0);
        }
    };

    const toggleVisibility = (id: string) => {
        // Mark that visibility update is in progress to prevent re-processing
        visibilityUpdateInProgress.current.add(id);
        
        setExpressions(prev => prev.map(e => {
            if (e.id === id) {
                const newVisible = !e.visible;
                const newMode: VisibilityMode = newVisible ? 'all' : 'none';
                // Update Desmos expression visibility
                if (calculatorInstance.current) {
                    const safeId = `E${id.replace(/-/g, "")}`;
                    const Calc = calculatorInstance.current;
                    
                    // Get all current expressions to check what exists
                    const allExprs = Calc.getExpressions();
                    const exprIds = allExprs.map((ex: any) => ex.id);
                    
                    // Parent curves (dotted lines) - graphical elements
                    const parentIds = [`curve-${safeId}`, `plot-orig-${safeId}`];
                    // Operated curves (solid lines - derivative/integral result) - graphical elements
                    const operatedIds = [id, `shade-${safeId}`, `plot-deriv-${safeId}`];
                    
                    // Only update visibility for graphical elements (parent + operated)
                    const graphicalIds = [...parentIds, ...operatedIds];
                    
                    // Update visibility for graphical expressions only
                    graphicalIds.forEach(eid => {
                        if (exprIds.includes(eid)) {
                            const isParent = parentIds.includes(eid);
                            const shouldHide = isParent 
                                ? !isParentVisible(newMode) 
                                : !isOperatedVisible(newMode);
                            try {
                                // For parent curves, also re-specify the lineStyle to ensure it stays dotted
                                if (isParent) {
                                    Calc.setExpression({ 
                                        id: eid, 
                                        hidden: shouldHide,
                                        lineStyle: window.Desmos.Styles.DOTTED
                                    });
                                } else {
                                    Calc.setExpression({ id: eid, hidden: shouldHide });
                                }
                            } catch (err) {
                                console.warn(`Failed to update visibility for ${eid}`, err);
                            }
                        }
                    });
                }
                return { ...e, visible: newVisible, visibilityMode: newMode };
            }
            return e;
        }));
        
        // Clear the visibility update flag after a short delay to allow React to finish re-rendering
        setTimeout(() => {
            visibilityUpdateInProgress.current.delete(id);
        }, 100);
    };

    // New function for granular visibility control
    const setVisibilityMode = (id: string, mode: VisibilityMode) => {
        // Mark that visibility update is in progress to prevent re-processing
        visibilityUpdateInProgress.current.add(id);
        
        setExpressions(prev => prev.map(e => {
            if (e.id === id) {
                const newVisible = mode !== 'none';
                // Update Desmos expression visibility
                if (calculatorInstance.current) {
                    const safeId = `E${id.replace(/-/g, "")}`;
                    const Calc = calculatorInstance.current;
                    
                    // Get all current expressions to check what exists
                    const allExprs = Calc.getExpressions();
                    const exprIds = allExprs.map((ex: any) => ex.id);
                    
                    // Parent curves (dotted lines) - graphical elements
                    const parentIds = [`curve-${safeId}`, `plot-orig-${safeId}`];
                    // Operated curves (solid lines - derivative/integral result) - graphical elements
                    const operatedIds = [id, `shade-${safeId}`, `plot-deriv-${safeId}`];
                    
                    // Only update visibility for graphical elements (parent + operated)
                    const graphicalIds = [...parentIds, ...operatedIds];
                    
                    // Update visibility for graphical expressions only
                    graphicalIds.forEach(eid => {
                        if (exprIds.includes(eid)) {
                            const isParent = parentIds.includes(eid);
                            const shouldHide = isParent 
                                ? !isParentVisible(mode) 
                                : !isOperatedVisible(mode);
                            try {
                                // For parent curves, also re-specify the lineStyle to ensure it stays dotted
                                if (isParent) {
                                    Calc.setExpression({ 
                                        id: eid, 
                                        hidden: shouldHide,
                                        lineStyle: window.Desmos.Styles.DOTTED
                                    });
                                } else {
                                    Calc.setExpression({ id: eid, hidden: shouldHide });
                                }
                            } catch (err) {
                                console.warn(`Failed to update visibility for ${eid}`, err);
                            }
                        }
                    });
                }
                return { ...e, visible: newVisible, visibilityMode: mode };
            }
            return e;
        }));
        
        // Clear the visibility update flag after a short delay to allow React to finish re-rendering
        setTimeout(() => {
            visibilityUpdateInProgress.current.delete(id);
        }, 100);
    };
    const toggleAreaMode = (id: string) => {
        // Find current expression to get state
        const expr = expressions.find(e => e.id === id);
        if (!expr) return;
        
        const newAreaMode = !expr.isAreaMode;
        
        // Update state
        setExpressions(prev => prev.map(e => e.id === id ? { ...e, isAreaMode: newAreaMode } : e));
        
        // Trigger reprocessing with new mode
        processExpression(id, expr.latex, expr.color, expr.visible, expr.visibilityMode, expr.sliderBounds, newAreaMode);
    };

    const removeExpr = (id: string) => {
        setExpressions(prev => prev.filter(e => e.id !== id));
        if (calculatorInstance.current) {
            const safeId = `E${id.replace(/-/g, "")}`;
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

    // Re-process expressions when the engine loads or component mounts
    useEffect(() => {
        if (calculatorInstance.current) {
            expressions.forEach(e => processExpression(e.id, e.latex, e.color, e.visible, e.visibilityMode, e.sliderBounds, e.isAreaMode));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [!!calculatorInstance.current]);

    return {
        expressions,
        debugInfo,
        legendOpen,
        setLegendOpen,
        handleInput,
        handleColorChange,
        addExpr,
        removeExpr,
        toggleVisibility,
        setVisibilityMode,
        toggleAreaMode,
        processExpression,
        updateSliderBounds,
        setExpressionPlaying
    };
};
