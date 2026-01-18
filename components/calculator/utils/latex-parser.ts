
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
