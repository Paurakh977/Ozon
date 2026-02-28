
/**
 * Convert LaTeX to nerdamer-compatible format
 */
export const latexToNerdamer = (latex: string): string => {
    let expr = latex
        // Remove LaTeX formatting first
        .replace(/\\left\s*/g, '')
        .replace(/\\right\s*/g, '')
        // Clean empty parentheses artifacts
        .replace(/([a-zA-Z0-9])\s*\(\s*\)/g, '$1')
        .replace(/\(\s*\)/g, '')
        .replace(/\\cdot/g, '*')
        .replace(/\\times/g, '*');

    // ==========================================
    // FIX MATHLIVE BROKEN FUNCTION NAMES (for nerdamer)
    // ==========================================
    // Fix broken hyperbolic assemblies from MathLive
    expr = expr
        .replace(/cs\\operatorname\{\\mathrm\{ch\}\}/g, '\\csch')
        .replace(/se\\operatorname\{\\mathrm\{ch\}\}/g, '\\sech')
        .replace(/co\\operatorname\{\\mathrm\{th\}\}/g, '\\coth');

    // Handle nested \operatorname{\mathrm{...}} → \...
    expr = expr.replace(/\\operatorname\{\\mathrm\{([^}]+)\}\}/g, '\\$1');

    // Handle \operatorname{\func} → \func
    expr = expr.replace(/\\operatorname\{(\\[a-zA-Z]+)\}/g, '$1');

    // Handle \operatorname{arc} → arc
    expr = expr.replace(/\\operatorname\{arc\}/g, 'arc');

    // Convert \operatorname{func} -> \func for proper processing
    expr = expr.replace(/\\operatorname\{([^}]+)\}/g, '\\$1');

    // Reassemble broken inverse trig/hyp: arc\func → \arcfunc
    expr = expr
        .replace(/arc\\(sinh|cosh|tanh|coth|sech|csch)/g, '\\arc$1')
        .replace(/arc\\(sin|cos|tan|cot|sec|csc)/g, '\\arc$1');

    // Handle "arc coth" space pattern if user typed it literally or MathLive separated it
    expr = expr
        .replace(/arc\s+(sinh|cosh|tanh|coth|sech|csch)/g, '\\arc$1')
        .replace(/arc\s+(sin|cos|tan|cot|sec|csc)/g, '\\arc$1');

    // Fix bare broken hyp: cs\ch → \csch etc.
    expr = expr
        .replace(/(^|[^a-zA-Z\\])cs\\ch/g, '$1\\csch')
        .replace(/(^|[^a-zA-Z\\])se\\ch/g, '$1\\sech')
        .replace(/(^|[^a-zA-Z\\])co\\th/g, '$1\\coth');

    // Reassemble broken \trig<space>h → \trigh (hyperbolic functions)
    expr = expr
        .replace(/\\(arcsin|arccos|arctan|arccot|arcsec|arccsc)(\s+)h/g, '\\$1h')
        .replace(/\\(sin|cos|tan|cot|sec|csc)(\s+)h/g, '\\$1h');

    // ==========================================
    // ROBUST FRACTION HANDLING
    // ==========================================
    // Handle \frac{a}{b}, \frac12, \frac1{2} etc.
    while (expr.includes('\\frac')) {
        const match = expr.match(/\\frac/);
        if (!match || match.index === undefined) break;
        const start = match.index;
        
        // Parse Numerator
        let numStart = start + 5; // length of \frac
        while (numStart < expr.length && /\s/.test(expr[numStart])) numStart++;
        
        let numEnd = numStart;
        let numerator = '';
        
        if (numStart < expr.length) {
             if (expr[numStart] === '{') {
                 // Block
                 let depth = 1;
                 numEnd = numStart + 1;
                 while (numEnd < expr.length && depth > 0) {
                     if (expr[numEnd] === '{') depth++;
                     else if (expr[numEnd] === '}') depth--;
                     numEnd++;
                 }
                 numerator = numEnd > expr.length ? expr.substring(numStart + 1) : expr.substring(numStart + 1, numEnd - 1);
             } else if (expr[numStart] === '\\') {
                 // Command e.g. \pi or \sin
                 const cmdMatch = expr.substring(numStart).match(/^(\\[a-zA-Z]+)/);
                 if (cmdMatch) {
                     numerator = cmdMatch[1];
                     numEnd = numStart + cmdMatch[1].length;
                 } else {
                     numerator = expr[numStart] + (expr[numStart+1] || '');
                     numEnd = numStart + 2;
                 }
             } else {
                 // Single char
                 numerator = expr[numStart];
                 numEnd = numStart + 1;
             }
        }

        // Parse Denominator
        let denStart = numEnd;
        while (denStart < expr.length && /\s/.test(expr[denStart])) denStart++;
        
        let denEnd = denStart;
        let denominator = '';
        
        if (denStart < expr.length) {
             if (expr[denStart] === '{') {
                 let depth = 1;
                 denEnd = denStart + 1;
                 while (denEnd < expr.length && depth > 0) {
                     if (expr[denEnd] === '{') depth++;
                     else if (expr[denEnd] === '}') depth--;
                     denEnd++;
                 }
                 denominator = denEnd > expr.length ? expr.substring(denStart + 1) : expr.substring(denStart + 1, denEnd - 1);
             } else if (expr[denStart] === '\\') {
                 const cmdMatch = expr.substring(denStart).match(/^(\\[a-zA-Z]+)/);
                 if (cmdMatch) {
                     denominator = cmdMatch[1];
                     denEnd = denStart + cmdMatch[1].length;
                 } else {
                     denominator = expr[denStart] + (expr[denStart+1] || '');
                     denEnd = denStart + 2;
                 }
             } else {
                 denominator = expr[denStart];
                 denEnd = denStart + 1;
             }
        }
        
        const before = expr.substring(0, start);
        const after = expr.substring(denEnd);
        expr = before + `(${numerator})/(${denominator})` + after;
    }

    expr = expr
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
    // HANDLE MALFORMED \mathrm{} BLOCKS
    // ==========================================
    // Handle cases like \mathrm{\sin^2xd} where trig function is inside \mathrm{}
    // Extract trig functions from inside \mathrm{} blocks before normal processing
    expr = expr
        // \mathrm{\sin^nx d} or \mathrm{\sin^{n}x d} -> \sin^{n}x d
        .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)\^\{?([^}\s]+)\}?([a-zA-Z])\s*d\}/g, '\\$1^{$2}$3 d')
        // \mathrm{\sinx d} -> \sin x d (no power)
        .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)([a-zA-Z])\s*d\}/g, '\\$1 $2 d')
        // \mathrm{\sin(expr)d} -> \sin(expr) d
        .replace(/\\mathrm\{\\?(sin|cos|tan|cot|sec|csc)\s*\(([^)]+)\)\s*d\}/g, '\\$1($2) d')
        // Generic fallback: remove \mathrm{} wrapper but keep content
        .replace(/\\mathrm\{([^}]+)\}/g, '$1');

    // ==========================================
    // TRIG/HYP FUNCTION WITH POWER BEFORE ARGUMENT (e.g., \sin^2x, \sinh^2x)
    // ==========================================
    // CRITICAL: Handle hyperbolic powers BEFORE regular trig to prevent \sinh -> sin(h)
    // \sinh^2x means (sinh(x))^2, \sin^2x means (sin(x))^2
    expr = expr
        // Hyperbolic powers: \sinh^{n}x, \sinh^nx, \sinh^{n}(expr), \sinh^n(expr)
        .replace(/\\(sinh|cosh|tanh|coth|sech|csch)\^\{([^}]+)\}([a-zA-Z])/g, '($1($3))^($2)')
        .replace(/\\(sinh|cosh|tanh|coth|sech|csch)\^(\d+)([a-zA-Z])/g, '($1($3))^$2')
        .replace(/\\(sinh|cosh|tanh|coth|sech|csch)\^\{([^}]+)\}\s*\(([^)]+)\)/g, '($1($3))^($2)')
        .replace(/\\(sinh|cosh|tanh|coth|sech|csch)\^(\d+)\s*\(([^)]+)\)/g, '($1($3))^$2')
        // Regular trig powers: \sin^{n}x, \sin^nx, \sin^{n}(expr), \sin^n(expr)
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^\{([^}]+)\}([a-zA-Z])/g, '($1($3))^($2)')
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^(\d+)([a-zA-Z])/g, '($1($3))^$2')
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^\{([^}]+)\}\s*\(([^)]+)\)/g, '($1($3))^($2)')
        .replace(/\\(sin|cos|tan|cot|sec|csc)\^(\d+)\s*\(([^)]+)\)/g, '($1($3))^$2');

    // ==========================================
    // INVERSE HYPERBOLIC FUNCTIONS (\arcsinh -> asinh, etc.)
    // Must come BEFORE inverse trig and regular functions
    // ==========================================
    expr = expr
        .replace(/\\arcsinh\s*\(([^)]+)\)/g, 'asinh($1)')
        .replace(/\\arccosh\s*\(([^)]+)\)/g, 'acosh($1)')
        .replace(/\\arctanh\s*\(([^)]+)\)/g, 'atanh($1)')
        .replace(/\\arccoth\s*\(([^)]+)\)/g, 'acoth($1)')
        .replace(/\\arcsech\s*\(([^)]+)\)/g, 'asech($1)')
        .replace(/\\arccsch\s*\(([^)]+)\)/g, 'acsch($1)')
        // Handle no parenthesis case
        .replace(/\\arcsinh\s+([a-zA-Z])/g, 'asinh($1)')
        .replace(/\\arccosh\s+([a-zA-Z])/g, 'acosh($1)')
        .replace(/\\arctanh\s+([a-zA-Z])/g, 'atanh($1)')
        .replace(/\\arccoth\s+([a-zA-Z])/g, 'acoth($1)')
        .replace(/\\arcsech\s+([a-zA-Z])/g, 'asech($1)')
        .replace(/\\arccsch\s+([a-zA-Z])/g, 'acsch($1)')
        // Handle immediate variable case
        .replace(/\\arcsinh([a-zA-Z])/g, 'asinh($1)')
        .replace(/\\arccosh([a-zA-Z])/g, 'acosh($1)')
        .replace(/\\arctanh([a-zA-Z])/g, 'atanh($1)')
        .replace(/\\arccoth([a-zA-Z])/g, 'acoth($1)')
        .replace(/\\arcsech([a-zA-Z])/g, 'asech($1)')
        .replace(/\\arccsch([a-zA-Z])/g, 'acsch($1)');

    // ==========================================
    // INVERSE TRIG FUNCTIONS (\arcsin -> asin, etc.)
    // Must come BEFORE regular trig to prevent \arcsin -> arc + sin(..)
    // ==========================================
    expr = expr
        .replace(/\\arcsin\s*\(([^)]+)\)/g, 'asin($1)')
        .replace(/\\arccos\s*\(([^)]+)\)/g, 'acos($1)')
        .replace(/\\arctan\s*\(([^)]+)\)/g, 'atan($1)')
        .replace(/\\arccot\s*\(([^)]+)\)/g, 'acot($1)')
        .replace(/\\arcsec\s*\(([^)]+)\)/g, 'asec($1)')
        .replace(/\\arccsc\s*\(([^)]+)\)/g, 'acsc($1)')
        // Handle no parenthesis case
        .replace(/\\arcsin\s+([a-zA-Z])/g, 'asin($1)')
        .replace(/\\arccos\s+([a-zA-Z])/g, 'acos($1)')
        .replace(/\\arctan\s+([a-zA-Z])/g, 'atan($1)')
        .replace(/\\arccot\s+([a-zA-Z])/g, 'acot($1)')
        .replace(/\\arcsec\s+([a-zA-Z])/g, 'asec($1)')
        .replace(/\\arccsc\s+([a-zA-Z])/g, 'acsc($1)')
        // Handle immediate variable case
        .replace(/\\arcsin([a-zA-Z])/g, 'asin($1)')
        .replace(/\\arccos([a-zA-Z])/g, 'acos($1)')
        .replace(/\\arctan([a-zA-Z])/g, 'atan($1)')
        .replace(/\\arccot([a-zA-Z])/g, 'acot($1)')
        .replace(/\\arcsec([a-zA-Z])/g, 'asec($1)')
        .replace(/\\arccsc([a-zA-Z])/g, 'acsc($1)');

    // ==========================================
    // HYPERBOLIC FUNCTIONS (\sinh -> sinh, etc.)
    // Must come BEFORE regular trig to prevent \sinh -> sin(h)
    // ==========================================
    expr = expr
        .replace(/\\sinh\s*\(([^)]+)\)/g, 'sinh($1)')
        .replace(/\\cosh\s*\(([^)]+)\)/g, 'cosh($1)')
        .replace(/\\tanh\s*\(([^)]+)\)/g, 'tanh($1)')
        .replace(/\\coth\s*\(([^)]+)\)/g, 'coth($1)')
        .replace(/\\sech\s*\(([^)]+)\)/g, 'sech($1)')
        .replace(/\\csch\s*\(([^)]+)\)/g, 'csch($1)')
        .replace(/\\sinh\s+([a-zA-Z])/g, 'sinh($1)')
        .replace(/\\cosh\s+([a-zA-Z])/g, 'cosh($1)')
        .replace(/\\tanh\s+([a-zA-Z])/g, 'tanh($1)')
        .replace(/\\coth\s+([a-zA-Z])/g, 'coth($1)')
        .replace(/\\sech\s+([a-zA-Z])/g, 'sech($1)')
        .replace(/\\csch\s+([a-zA-Z])/g, 'csch($1)')
        .replace(/\\sinh([a-zA-Z])/g, 'sinh($1)')
        .replace(/\\cosh([a-zA-Z])/g, 'cosh($1)')
        .replace(/\\tanh([a-zA-Z])/g, 'tanh($1)')
        .replace(/\\coth([a-zA-Z])/g, 'coth($1)')
        .replace(/\\sech([a-zA-Z])/g, 'sech($1)')
        .replace(/\\csch([a-zA-Z])/g, 'csch($1)');

    // ==========================================
    // REGULAR TRIG FUNCTIONS (\sin -> sin, etc.)
    // ==========================================
    expr = expr
        .replace(/\\sin\s*\(([^)]+)\)/g, 'sin($1)')
        .replace(/\\cos\s*\(([^)]+)\)/g, 'cos($1)')
        .replace(/\\tan\s*\(([^)]+)\)/g, 'tan($1)')
        .replace(/\\cot\s*\(([^)]+)\)/g, 'cot($1)')
        .replace(/\\sec\s*\(([^)]+)\)/g, 'sec($1)')
        .replace(/\\csc\s*\(([^)]+)\)/g, 'csc($1)')
        // Handle trig without explicit parentheses (e.g., \sin x)
        .replace(/\\sin\s+([a-zA-Z])/g, 'sin($1)')
        .replace(/\\cos\s+([a-zA-Z])/g, 'cos($1)')
        .replace(/\\tan\s+([a-zA-Z])/g, 'tan($1)')
        .replace(/\\cot\s+([a-zA-Z])/g, 'cot($1)')
        .replace(/\\sec\s+([a-zA-Z])/g, 'sec($1)')
        .replace(/\\csc\s+([a-zA-Z])/g, 'csc($1)')
        // Handle trig where the argument might not be separated by space
        .replace(/\\sin(\(|\[)/g, 'sin$1')
        .replace(/\\cos(\(|\[)/g, 'cos$1')
        .replace(/\\tan(\(|\[)/g, 'tan$1')
        .replace(/\\cot(\(|\[)/g, 'cot$1')
        .replace(/\\sec(\(|\[)/g, 'sec$1')
        .replace(/\\csc(\(|\[)/g, 'csc$1')
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

    // ==========================================
    // CONVERT UNSUPPORTED INVERSE FUNCTIONS TO NERDAMER EQUIVALENTS
    // ==========================================
    // nerdamer doesn't natively support: asec, acsc, acot, asech, acsch, acoth
    // Convert to equivalent expressions using supported functions:
    //   asec(x) = acos(1/x), acsc(x) = asin(1/x), acot(x) = atan(1/x)
    //   asech(x) = acosh(1/x), acsch(x) = asinh(1/x), acoth(x) = atanh(1/x)
    const convertUnsupportedInverse = (str: string): string => {
        // Longest names first to prevent partial matching (asech before asec)
        const conversions: [string, (arg: string) => string][] = [
            ['asech', (arg) => `acosh(1/(${arg}))`],
            ['acsch', (arg) => `asinh(1/(${arg}))`],
            ['acoth', (arg) => `atanh(1/(${arg}))`],
            ['asec', (arg) => `acos(1/(${arg}))`],
            ['acsc', (arg) => `asin(1/(${arg}))`],
            ['acot', (arg) => `atan(1/(${arg}))`],
        ];
        for (const [funcName, converter] of conversions) {
            let result = '';
            let i = 0;
            while (i < str.length) {
                const remaining = str.substring(i);
                if (remaining.startsWith(funcName + '(')) {
                    // Ensure it's not part of a longer function name
                    if (i > 0 && /[a-zA-Z]/.test(str[i - 1])) {
                        result += str[i];
                        i++;
                        continue;
                    }
                    // Find the matching closing parenthesis (handles nested parens)
                    const argStart = i + funcName.length + 1;
                    let depth = 1;
                    let j = argStart;
                    while (j < str.length && depth > 0) {
                        if (str[j] === '(') depth++;
                        else if (str[j] === ')') depth--;
                        j++;
                    }
                    if (depth === 0) {
                        const arg = str.substring(argStart, j - 1);
                        result += converter(arg);
                        i = j;
                    } else {
                        result += str[i];
                        i++;
                    }
                } else {
                    result += str[i];
                    i++;
                }
            }
            str = result;
        }
        return str;
    };
    expr = convertUnsupportedInverse(expr);

    // Remove remaining backslashes and clean up
    expr = expr
        .replace(/\\/g, '')
        .replace(/\s+/g, '')
        .trim();

    // ==========================================
    // IMPLICIT MULTIPLICATION HANDLING (Part 2)
    // ==========================================
    // After all function names are converted, add implicit multiplication
    const funcNames = [
        'sinh', 'cosh', 'tanh', 'coth', 'sech', 'csch',
        'asin', 'acos', 'atan', 'acot', 'asec', 'acsc',
        'asinh', 'acosh', 'atanh', 'acoth', 'asech', 'acsch', // Added arc hyperbolic functions
        'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
        'log', 'log10', 'exp', 'sqrt', 'abs'
    ];

    
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
 * IMPROVED: Handles standard LaTeX function names for inverse hyperbolic functions
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

        // Convert nerdamer function names back to proper LaTeX
        // CRITICAL: Use negative lookbehind (?<![a-zA-Z]) to prevent cascading replacements.
        // Without it, replacing "sech" would corrupt "arcsech" inside \operatorname{arcsech}.
        // Process longest names first, then shorter ones.
        tex = tex
            // Handle inverse hyperbolic functions
            .replace(/(?<![a-zA-Z])\\?asinh\b/g, '\\operatorname{arcsinh}')
            .replace(/(?<![a-zA-Z])\\?acosh\b/g, '\\operatorname{arccosh}')
            .replace(/(?<![a-zA-Z])\\?atanh\b/g, '\\operatorname{arctanh}')
            .replace(/(?<![a-zA-Z])\\?acoth\b/g, '\\operatorname{arccoth}')
            .replace(/(?<![a-zA-Z])\\?asech\b/g, '\\operatorname{arcsech}')
            .replace(/(?<![a-zA-Z])\\?acsch\b/g, '\\operatorname{arccsch}')
            // Handle inverse trig functions (some nerdamer versions output asin instead of arcsin)
            .replace(/(?<![a-zA-Z])\\?asin\b/g, '\\arcsin')
            .replace(/(?<![a-zA-Z])\\?acos\b/g, '\\arccos')
            .replace(/(?<![a-zA-Z])\\?atan\b/g, '\\arctan')
            .replace(/(?<![a-zA-Z])\\?acot\b/g, '\\arccot')
            .replace(/(?<![a-zA-Z])\\?asec\b/g, '\\arcsec')
            .replace(/(?<![a-zA-Z])\\?acsc\b/g, '\\arccsc')
            // Handle regular hyperbolic functions (prevent matching inside arc* names)
            .replace(/(?<![a-zA-Z])\\?sinh\b/g, '\\sinh')
            .replace(/(?<![a-zA-Z])\\?cosh\b/g, '\\cosh')
            .replace(/(?<![a-zA-Z])\\?tanh\b/g, '\\tanh')
            .replace(/(?<![a-zA-Z])\\?coth\b/g, '\\coth')
            .replace(/(?<![a-zA-Z])\\?sech\b/g, '\\sech')
            .replace(/(?<![a-zA-Z])\\?csch\b/g, '\\csch')
            // Handle log10 BEFORE log to prevent log matching the log prefix of log10
            .replace(/(?<![a-zA-Z])\\?log10\b/g, '\\log_{10}')
            // Handle standard log in nerdamer (which is natural log)
            .replace(/(?<![a-zA-Z])\\?log\b/g, '\\ln');

        // Fix potential double backslashes
        tex = tex.replace(/\\\\/g, '\\');

        return tex;
    } catch {
        return result.toString();
    }
};
