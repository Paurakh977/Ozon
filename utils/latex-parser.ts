
/**
 * Convert LaTeX to nerdamer-compatible format
 */
export const latexToNerdamer = (latex: string): string => {
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

    // ==========================================
    // IMPLICIT MULTIPLICATION HANDLING (Part 1)
    // ==========================================
    // Handle cases like: xe^{...} -> x*e^{...} BEFORE function processing
    // This catches patterns like "xe^{-2x}" -> "x*e^{-2x}"
    expr = expr.replace(/([a-zA-Z0-9])e\^/g, '$1*e^');
    
    // Variable followed by backslash command (like \sin, \ln): x\sin -> x*\sin
    expr = expr.replace(/([a-zA-Z0-9])(\\[a-zA-Z]+)/g, '$1*$2');

    // ==========================================
    // TRIG FUNCTION WITH POWER BEFORE ARGUMENT (e.g., \sin^2x)
    // ==========================================
    // CRITICAL: Handle \sin^2x, \cos^{3}y patterns BEFORE other trig handling
    // \sin^2x means (sin(x))^2, not sin(x^2)
    // \sin^{2}x also means (sin(x))^2
    // Handle both braced and unbraced power formats
    expr = expr
        // \sin^{n}x -> (sin(x))^(n) - braced power with variable
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^\{([^}]+)\}([a-zA-Z])/g, '($1($3))^($2)')
        // \sin^nx -> (sin(x))^n - unbraced single/multi digit power with variable
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^(\d+)([a-zA-Z])/g, '($1($3))^$2')
        // \sin^{n}(expr) -> (sin(expr))^(n) - braced power with parenthesized argument
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^\{([^}]+)\}\s*\(([^)]+)\)/g, '($1($3))^($2)')
        // \sin^n(expr) -> (sin(expr))^n - unbraced power with parenthesized argument
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^(\d+)\s*\(([^)]+)\)/g, '($1($3))^$2');

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
    // IMPORTANT: Handle e^{...} patterns AFTER ^{} -> ^() conversion
    // So we now look for e^(...) patterns
    expr = expr
        .replace(/\\exp\s*\(([^)]+)\)/g, 'exp($1)')
        .replace(/\\exp\s*/g, 'exp')
        // e^(...) where ... can be complex like (-2x), (-2*x), etc.
        .replace(/e\^\(([^)]+)\)/g, 'exp($1)')
        // e^x (single character) - but not if followed by more alphanumeric
        .replace(/e\^([a-zA-Z])(?![a-zA-Z0-9])/g, 'exp($1)')
        .replace(/e\^(\d+)(?![a-zA-Z0-9])/g, 'exp($1)');

    // Remove remaining backslashes and clean up
    expr = expr
        .replace(/\\/g, '')
        .replace(/\s+/g, '')
        .trim();

    // ==========================================
    // IMPLICIT MULTIPLICATION HANDLING (Part 2)
    // ==========================================
    // After all function names are converted, add implicit multiplication
    const funcNames = ['sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'log', 'log10', 'exp', 'sqrt', 'abs', 'asin', 'acos', 'atan'];
    
    // Helper: Check if position is at end of a function name
    const isEndOfFunction = (str: string, pos: number): boolean => {
        for (const fn of funcNames) {
            if (pos >= fn.length - 1) {
                const start = pos - fn.length + 1;
                if (str.substring(start, pos + 1) === fn) {
                    return true;
                }
            }
        }
        return false;
    };
    
    // Build result with implicit multiplication
    let result = '';
    for (let i = 0; i < expr.length; i++) {
        const char = expr[i];
        const prevChar = i > 0 ? expr[i - 1] : '';
        
        // Check if we need to insert multiplication
        if (char === '(' && i > 0) {
            // Add * before ( if previous char is alphanumeric AND not part of function name
            if (/[a-zA-Z0-9]/.test(prevChar) && !isEndOfFunction(expr, i - 1)) {
                result += '*';
            }
        } else if (/[a-zA-Z]/.test(char) && i > 0) {
            // Add * before variable if previous char is ) or digit
            if (prevChar === ')') {
                result += '*';
            } else if (/\d/.test(prevChar)) {
                result += '*';
            }
        } else if (/\d/.test(char) && i > 0 && prevChar === ')') {
            // Add * after ) before number
            result += '*';
        } else if (char === '(' && i > 0 && prevChar === ')') {
            // Add * between )( 
            result += '*';
        }
        
        result += char;
    }
    
    // Clean up any double multiplication signs
    result = result.replace(/\*\*/g, '*');
    
    // Remove any leading *
    if (result.startsWith('*')) {
        result = result.substring(1);
    }

    return result;
};

/**
 * Convert nerdamer result back to LaTeX
 */
export const nerdamerToLatex = (result: any): string => {
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
