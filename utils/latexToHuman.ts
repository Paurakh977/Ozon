/**
 * latexToHuman.ts
 * ================
 * Converts LaTeX expressions into human-readable "keyboard" notation.
 *
 * Usage:
 *   import { latexToHuman, logHumanInput } from './latexToHuman';
 *   logHumanInput(id, rawLatex);
 */

// ─────────────────────────────────────────────────────────────
// KNOWN FUNCTION NAMES — longest first (greedy match order)
// ─────────────────────────────────────────────────────────────
const KNOWN_FUNCS: string[] = [
    'arcsinh', 'arccosh', 'arctanh', 'arccoth', 'arcsech', 'arccsch',
    'arcsin', 'arccos', 'arctan', 'arccot', 'arcsec', 'arccsc',
    'sinh', 'cosh', 'tanh', 'coth', 'sech', 'csch',
    'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
    'ln', 'log', 'exp', 'abs',
    'gcd', 'lcm', 'min', 'max',
    'floor', 'ceil', 'sgn', 'sign',
    'det', 'dim', 'ker', 'deg', 'arg', 'mod',
    'Re', 'Im',
];

// Graph variables — x and y are NOT treated as constants needing *
// Everything else (a, b, c, k, n, m, ...) is a constant → needs * between them
const GRAPH_VARS = new Set(['x', 'y', 'r', 't']);

// ─────────────────────────────────────────────────────────────
// PHASE 0 — PRE-NORMALISATION
// ─────────────────────────────────────────────────────────────
function preNormalise(s: string): string {
    s = s.replace(/\$\$/g, '').replace(/(?<![\\])\$/g, '').trim();

    s = s
        .replace(/\\placeholder\{[^}]*\}/g, '?')

        // operatorname / mathrm → \name (WITH backslash so parser treats as \cmd)
        .replace(/\\operatorname\{\\mathrm\{([^}]+)\}\}/g, (_, n) => `\\${n}`)
        .replace(/\\operatorname\{\\([a-zA-Z]+)\}/g, (_, n) => `\\${n}`)
        .replace(/\\operatorname\{([^}]+)\}/g, (_, n) => `\\${n}`)

        // differential variants
        .replace(/\\mathrm\{dx\}/g, 'dx')
        .replace(/\\mathrm\{d\}([a-zA-Z])/g, 'd$1')
        .replace(/\\mathrm\{d([a-zA-Z])\}/g, 'd$1')
        .replace(/\\mathrm\{d\}/g, 'd')
        .replace(/\\text\{d\}([a-zA-Z])/g, 'd$1')
        .replace(/\\text\{dx\}/g, 'dx')
        .replace(/\\differentialD/g, 'd')
        .replace(/\\mathrm\{([^}]+)\}/g, '$1')
        .replace(/\\text\{([^}]+)\}/g, '$1')
        .replace(/\\mbox\{([^}]+)\}/g, '$1')

        // fraction aliases
        .replace(/\\dfrac/g, '\\frac')
        .replace(/\\tfrac/g, '\\frac')
        .replace(/\\cfrac/g, '\\frac')

        // spacing / layout
        .replace(/\\[,;:!]/g, '')
        .replace(/\\quad\b/g, ' ')
        .replace(/\\qquad\b/g, ' ')
        .replace(/\\limits\b/g, '')
        .replace(/\\displaystyle\b/g, '')
        .replace(/\\textstyle\b/g, '')
        .replace(/\\scriptstyle\b/g, '')
        .replace(/\\boldsymbol\{([^}]+)\}/g, '$1')

        // named bracket commands
        .replace(/\\left\s*\\lbrack/g, '[').replace(/\\right\s*\\rbrack/g, ']')
        .replace(/\\lbrack/g, '[').replace(/\\rbrack/g, ']')
        .replace(/\\left\s*\\lbrace/g, '(').replace(/\\right\s*\\rbrace/g, ')')
        .replace(/\\lbrace/g, '{').replace(/\\rbrace/g, '}')
        .replace(/\\left\s*\\langle/g, '<').replace(/\\right\s*\\rangle/g, '>')
        .replace(/\\langle/g, '<').replace(/\\rangle/g, '>')
        .replace(/\\left\s*\\lfloor/g, 'floor(').replace(/\\right\s*\\rfloor/g, ')')
        .replace(/\\lfloor/g, 'floor(').replace(/\\rfloor/g, ')')
        .replace(/\\left\s*\\lceil/g, 'ceil(').replace(/\\right\s*\\rceil/g, ')')
        .replace(/\\lceil/g, 'ceil(').replace(/\\rceil/g, ')')

        // absolute value / norm
        .replace(/\\lvert/g, '|').replace(/\\rvert/g, '|')
        .replace(/\\lVert/g, '‖').replace(/\\rVert/g, '‖')
        .replace(/\\vert\b/g, '|').replace(/\\Vert\b/g, '‖')

        // size modifiers
        .replace(/\\[Bb]igg?[lr]?\s*\(/g, '(').replace(/\\[Bb]igg?[lr]?\s*\)/g, ')')
        .replace(/\\[Bb]igg?[lr]?\s*\[/g, '[').replace(/\\[Bb]igg?[lr]?\s*\]/g, ']')
        .replace(/\\[Bb]igg?[lr]?\s*\|/g, '|')
        .replace(/\\[Bb]igm\s*\|/g, '|').replace(/\\[Bb]igm\s*\\vert/g, '|');

    // Fix \right. (MathLive invisible close delimiter)
    s = fixUnmatchedDelimiters(s);

    // Normalize nested pipes | and mathlive's \left| \right|
    s = normalizeAbsDelimiters(s);

    // Strip remaining \left / \right
    s = s
        .replace(/\\left\s*\(/g, '(').replace(/\\right\s*\)/g, ')')
        .replace(/\\left\s*\[/g, '[').replace(/\\right\s*\]/g, ']')
        .replace(/\\left\s*\\{/g, '(').replace(/\\right\s*\\}/g, ')')
        .replace(/\\left\s*\\Vert/g, '‖').replace(/\\right\s*\\Vert/g, '‖')
        .replace(/\\left\s*\./g, '').replace(/\\right\s*\./g, '')
        .replace(/\\left\b\s*/g, '').replace(/\\right\b\s*/g, '');

    return s;
}

function fixUnmatchedDelimiters(s: string): string {
    const closeFor: Record<string, string> = { '(': ')', '[': ']', '|': '|', '{': '}', '<': '>' };
    const stack: string[] = [];
    let out = '', i = 0;
    while (i < s.length) {
        const lm = s.slice(i).match(/^\\left\s*([(\[|{<])/);
        if (lm) { stack.push(lm[1]); out += s.slice(i, i + lm[0].length); i += lm[0].length; continue; }
        const rd = s.slice(i).match(/^\\right\s*\./);
        if (rd) { const op = stack.pop(); if (op && closeFor[op]) out += '\\right' + closeFor[op]; i += rd[0].length; continue; }
        const rr = s.slice(i).match(/^\\right\s*([)\]|}<>])/);
        if (rr) { stack.pop(); out += s.slice(i, i + rr[0].length); i += rr[0].length; continue; }
        out += s[i++];
    }
    return out;
}

// ─────────────────────────────────────────────────────────────
// PARSER HELPERS
// ─────────────────────────────────────────────────────────────
function extractGroup(str: string, pos: number): { content: string; end: number } {
    const open = str[pos];
    const close = open === '{' ? '}' : open === '(' ? ')' : open === '[' ? ']' : '}';
    let depth = 1, i = pos + 1;
    while (i < str.length && depth > 0) {
        if (str[i] === open) depth++; else if (str[i] === close) depth--;
        i++;``
    }
    return { content: str.substring(pos + 1, i - 1), end: i };
}

function skipSpace(str: string, pos: number): number {
    while (pos < str.length && /\s/.test(str[pos])) pos++;
    return pos;
}

function readToken(str: string, pos: number): { token: string; end: number } {
    pos = skipSpace(str, pos);
    if (pos >= str.length) return { token: '', end: pos };
    if (str[pos] === '\\') {
        let i = pos + 1;
        if (i >= str.length) return { token: '\\', end: i };
        if (!/[a-zA-Z]/.test(str[i])) return { token: str.substring(pos, pos + 2), end: pos + 2 };
        while (i < str.length && /[a-zA-Z]/.test(str[i])) i++;
        return { token: str.substring(pos, i), end: i };
    }
    return { token: str[pos], end: pos + 1 };
}

function readFracArg(str: string, pos: number): { content: string; end: number } {
    pos = skipSpace(str, pos);
    if (pos >= str.length) return { content: '', end: pos };
    if (str[pos] === '{') { const g = extractGroup(str, pos); return { content: g.content, end: g.end }; }
    if (str[pos] === '\\') { const t = readToken(str, pos); return { content: t.token, end: t.end }; }
    return { content: str[pos], end: pos + 1 };
}

function readArg(str: string, pos: number): { content: string; end: number } {
    pos = skipSpace(str, pos);
    if (pos >= str.length) return { content: '', end: pos };
    if (str[pos] === '{') { const g = extractGroup(str, pos); return { content: g.content, end: g.end }; }
    const t = readToken(str, pos);
    return { content: t.token, end: t.end };
}

// ─────────────────────────────────────────────────────────────
// LOOKUP TABLES
// ─────────────────────────────────────────────────────────────
const GREEK: Record<string, string> = {
    '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\delta': 'δ',
    '\\epsilon': 'ε', '\\varepsilon': 'ε', '\\zeta': 'ζ', '\\eta': 'η',
    '\\theta': 'θ', '\\vartheta': 'θ', '\\iota': 'ι', '\\kappa': 'κ',
    '\\lambda': 'λ', '\\mu': 'μ', '\\nu': 'ν', '\\xi': 'ξ',
    '\\pi': 'π', '\\varpi': 'π', '\\rho': 'ρ', '\\varrho': 'ρ',
    '\\sigma': 'σ', '\\varsigma': 'σ', '\\tau': 'τ', '\\upsilon': 'υ',
    '\\phi': 'φ', '\\varphi': 'φ', '\\chi': 'χ', '\\psi': 'ψ', '\\omega': 'ω',
    '\\Gamma': 'Γ', '\\Delta': 'Δ', '\\Theta': 'Θ', '\\Lambda': 'Λ',
    '\\Xi': 'Ξ', '\\Pi': 'Π', '\\Sigma': 'Σ', '\\Upsilon': 'Υ',
    '\\Phi': 'Φ', '\\Psi': 'Ψ', '\\Omega': 'Ω',
};

// Greek symbol chars — used in needsMul to recognise them as value-producing
const GREEK_CHARS = new Set(['α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η', 'θ', 'ι', 'κ', 'λ', 'μ', 'ν', 'ξ', 'π', 'ρ', 'σ', 'τ', 'υ', 'φ', 'χ', 'ψ', 'ω', 'Γ', 'Δ', 'Θ', 'Λ', 'Ξ', 'Π', 'Σ', 'Υ', 'Φ', 'Ψ', 'Ω']);

const SYMBOLS: Record<string, string> = {
    '\\infty': 'inf', '\\partial': '∂', '\\nabla': '∇',
    '\\cdot': '*', '\\times': '*', '\\div': '/',
    '\\pm': '±', '\\mp': '∓',
    '\\leq': '≤', '\\le': '≤', '\\geq': '≥', '\\ge': '≥',
    '\\neq': '≠', '\\ne': '≠', '\\approx': '≈', '\\sim': '~',
    '\\equiv': '≡', '\\propto': '∝',
    '\\to': '→', '\\rightarrow': '→', '\\leftarrow': '←',
    '\\Rightarrow': '⇒', '\\Leftarrow': '⇐', '\\Leftrightarrow': '⇔',
    '\\in': '∈', '\\notin': '∉', '\\subset': '⊂', '\\supset': '⊃',
    '\\cup': '∪', '\\cap': '∩', '\\emptyset': '∅', '\\varnothing': '∅',
    '\\forall': '∀', '\\exists': '∃',
    '\\land': '&&', '\\lor': '||', '\\lnot': '!',
    '\\ldots': '...', '\\cdots': '...', '\\vdots': '...', '\\ddots': '...',
    '\\{': '{', '\\}': '}', '\\|': '‖',
};

const FUNC_MAP: Record<string, string> = {
    '\\sin': 'sin', '\\cos': 'cos', '\\tan': 'tan', '\\cot': 'cot', '\\sec': 'sec', '\\csc': 'csc',
    '\\sinh': 'sinh', '\\cosh': 'cosh', '\\tanh': 'tanh', '\\coth': 'coth', '\\sech': 'sech', '\\csch': 'csch',
    '\\arcsin': 'arcsin', '\\arccos': 'arccos', '\\arctan': 'arctan',
    '\\arccot': 'arccot', '\\arcsec': 'arcsec', '\\arccsc': 'arccsc',
    '\\arcsinh': 'arcsinh', '\\arccosh': 'arccosh', '\\arctanh': 'arctanh',
    '\\arccoth': 'arccoth', '\\arcsech': 'arcsech', '\\arccsch': 'arccsch',
    '\\ln': 'ln', '\\log': 'log', '\\exp': 'exp',
    '\\abs': 'abs', '\\gcd': 'gcd', '\\lcm': 'lcm',
    '\\min': 'min', '\\max': 'max',
    '\\floor': 'floor', '\\ceil': 'ceil',
    '\\sgn': 'sgn', '\\sign': 'sign',
    '\\Re': 'Re', '\\Im': 'Im',
    '\\det': 'det', '\\dim': 'dim', '\\ker': 'ker', '\\deg': 'deg', '\\arg': 'arg', '\\mod': 'mod',

};

// ─────────────────────────────────────────────────────────────
// DEPTH-AWARE OPERATOR DETECTION
// ─────────────────────────────────────────────────────────────
function hasBareAdditive(s: string): boolean {
    let d = 0;
    for (let i = 0; i < s.length; i++) {
        const c = s[i];
        if (c === '(' || c === '[') { d++; continue; }
        if (c === ')' || c === ']') { d--; continue; }
        if (d === 0 && i > 0 && (c === '+' || c === '-')) return true;
    }
    return false;
}

function hasBareOperator(s: string): boolean {
    let d = 0;
    for (let i = 0; i < s.length; i++) {
        const c = s[i];
        if (c === '(' || c === '[') { d++; continue; }
        if (c === ')' || c === ']') { d--; continue; }
        if (d === 0 && i > 0 && (c === '+' || c === '-' || c === '*' || c === '/')) return true;
    }
    return false;
}

function wrapIfAdditive(s: string): string { return hasBareAdditive(s) ? `(${s})` : s; }
function wrapIfCompound(s: string): string { return hasBareOperator(s) ? `(${s})` : s; }
function wrapFrac(num: string, den: string): string {
    return `(${wrapIfAdditive(num)}/${wrapIfCompound(den)})`;
}

// ─────────────────────────────────────────────────────────────
// IMPLICIT MULTIPLICATION — needsMul(left, right)
//
// LEFT side chars that are "value-producing" (can be left of *)
//   digits, letters, ), ], !, greek symbols
//
// RIGHT side chars that start a new value (can be right of *)
//   digits, letters, (, greek symbols, |
//
// Special rules:
//   letter → letter:  INSERT * unless both are graph vars (x,y,r,t)
//                     because "ax" = a*x, "xy" = x*y but "sin" = word
//   !  → anything value-producing: INSERT *   (x! * π)
//   greek → letter or (: INSERT *              (π * |...|, π * x)
//   ) or ] → letter or digit or (: INSERT *
//   digit → letter: INSERT *
//   digit → (: INSERT *
// ─────────────────────────────────────────────────────────────
function isValueChar(c: string): boolean {
    return /[0-9a-zA-Z)\]]/.test(c) || c === '!' || GREEK_CHARS.has(c);
}

function isStartChar(c: string): boolean {
    return /[0-9a-zA-Z(]/.test(c) || GREEK_CHARS.has(c);
}

function needsMul(left: string, right: string): boolean {
    if (!left || !right) return false;
    const L = left[left.length - 1];
    const R = right[0];

    if (!isValueChar(L)) return false;
    if (!isStartChar(R)) return false;

    // ! always multiplies what follows
    if (L === '!') return true;

    // greek symbol on left always multiplies
    if (GREEK_CHARS.has(L)) return true;

    // ) or ] always multiplies letters/digits/(
    if ((L === ')' || L === ']') && /[0-9a-zA-Z(]/.test(R)) return true;

    // digit → letter/( → multiply
    if (/[0-9]/.test(L) && /[a-zA-Z(]/.test(R)) return true;

    // letter → letter: multiply ONLY if they are separate symbols
    // i.e. not both part of a known function name continuation
    // We can't know at emit-time whether it's mid-function, so we use a heuristic:
    // single-char constants (not x/y/r/t) followed by another letter → multiply
    if (/[a-zA-Z]/.test(L) && /[a-zA-Z(]/.test(R)) {
        // If left ends with a known function call like "sin(x)" ending in )
        // that's already handled by ) branch above.
        // Here L is a letter. It's the tail of some identifier.
        // We insert * between single-letter constants: a*x, a*b, k*n etc.
        // But NOT inside function names — those arrive as \cmd tokens so
        // they never pass through here letter-by-letter.
        // Safe heuristic: always insert * between letter and letter/(.
        // Function names are emitted atomically as "sin(x)", "ln(x)" etc.
        // so their internal letters never pass through needsMul individually.
        return true;
    }

    // digit → greek
    if (/[0-9]/.test(L) && GREEK_CHARS.has(R)) return true;

    // letter → greek
    if (/[a-zA-Z]/.test(L) && GREEK_CHARS.has(R)) return true;

    // greek → (
    if (GREEK_CHARS.has(L) && R === '(') return true;

    return false;
}

// ─────────────────────────────────────────────────────────────
// CORE RECURSIVE CONVERTER
// ─────────────────────────────────────────────────────────────
function convertLatex(latex: string): string {
    let s = preNormalise(latex);
    let result = '';

    const emit = (token: string) => {
        if (!token) return;
        if (needsMul(result, token)) result += '*';
        result += token;
    };

    let i = 0;
    while (i < s.length) {
        i = skipSpace(s, i);
        if (i >= s.length) break;
        const ch = s[i];

        // ── {group} ───────────────────────────────────────────────
        if (ch === '{') {
            const g = extractGroup(s, i); i = g.end;
            const trimmed = g.content.trim();
            if (!trimmed || trimmed === '?') continue;
            const inner = convertLatex(trimmed);
            if (inner) emit(wrapIfAdditive(inner));
            continue;
        }

        // ── (group) ───────────────────────────────────────────────
        if (ch === '(') {
            const g = extractGroup(s, i); i = g.end;
            emit(`(${convertLatex(g.content)})`);
            continue;
        }

        // ── [group] ───────────────────────────────────────────────
        if (ch === '[') {
            const g = extractGroup(s, i); i = g.end;
            emit(`[${convertLatex(g.content)}]`);
            continue;
        }

        // ── |expr| → abs(expr) ──────────────────────────────────
        if (ch === "|") {
            let pipeDepth = 1;
            let parenDepth = 0;
            let j = i + 1;
            while (j < s.length) {
                if (s[j] === '(' || s[j] === '[') parenDepth++;
                else if (s[j] === ')' || s[j] === ']') parenDepth--;
                else if (s[j] === '|') {
                    let prev = j > 0 ? s[j - 1] : '';
                    let isOpen = false;
                    if (/[-+*/=({\[<>,_^]/.test(prev)) isOpen = true;
                    else if (/[0-9a-zA-Z)\]}]/.test(prev)) isOpen = false;
                    else if (j + 1 < s.length && /[0-9a-zA-Z(\[]/.test(s[j + 1])) isOpen = true;
                    else isOpen = false;

                    if (isOpen) pipeDepth++;
                    else pipeDepth--;

                    if (pipeDepth === 0) break;
                }
                j++;
            }

            if (pipeDepth === 0 && j < s.length) {
                emit(`abs(${convertLatex(s.substring(i + 1, j))})`);
                i = j + 1;
            } else if (pipeDepth > 0 && parenDepth < 0) {
                const absContent = s.substring(i + 1, j - 1);
                emit(`abs(${convertLatex(absContent)})`);
                i = j;
            } else {
                emit("|");
                i++;
            }
            continue;
        }

        // ── \command ──────────────────────────────────────────────
        if (ch === '\\') {
            const tok = readToken(s, i); const cmd = tok.token; i = tok.end;

            if (GREEK[cmd]) { emit(GREEK[cmd]); continue; }
            if (SYMBOLS[cmd]) { emit(SYMBOLS[cmd]); continue; }

            // ── \frac ─────────────────────────────────────────────
            if (cmd === '\\frac') {
                const nA = readFracArg(s, i); i = nA.end;
                const dA = readFracArg(s, i); i = dA.end;
                const numRaw = nA.content.trim();
                const denRaw = dA.content.trim();
                if (!numRaw || numRaw === '?') continue;
                if (!denRaw || denRaw === '?') {
                    const nH = convertLatex(numRaw);
                    if (nH) emit(wrapIfAdditive(nH));
                    continue;
                }
                const nH = convertLatex(numRaw);
                const dH = convertLatex(denRaw);
                if (!nH) continue;
                emit(wrapFrac(nH, dH));
                continue;
            }

            // ── \sqrt — ALWAYS power form for consistency ──────────
            // \sqrt{x}    → (x)^(1/2)
            // \sqrt[3]{x} → (x)^(1/3)
            if (cmd === "\\sqrt") {
                i = skipSpace(s, i);
                let rootN = "2";
                if (i < s.length && s[i] === "[") {
                    const nr = extractGroup(s, i); i = nr.end;
                    rootN = convertLatex(nr.content);
                }
                const bA = readFracArg(s, i); i = bA.end;
                const body = convertLatex(bA.content);
                const rootWrapped = hasBareOperator(rootN) ? `(${rootN})` : rootN;
                emit(`(${body})^(1/${rootWrapped})`);
                continue;
            }

            // ── \int \iint \iiint \oint ───────────────────────────
            if (cmd === '\\int' || cmd === '\\iint' || cmd === '\\iiint' || cmd === '\\oint') {
                const prefix = cmd === '\\oint' ? 'contour_integral' : cmd === '\\iint' ? 'double_integral' : cmd === '\\iiint' ? 'triple_integral' : 'integral';
                let lower = '', upper = '';
                for (let a = 0; a < 2; a++) {
                    i = skipSpace(s, i); if (i >= s.length) break;
                    if (s[i] === '_') { i++; const b = readArg(s, i); lower = convertLatex(b.content); i = b.end; }
                    else if (s[i] === '^') { i++; const b = readArg(s, i); upper = convertLatex(b.content); i = b.end; }
                    else break;
                }
                const rest = s.substring(i).trim();
                const dm = rest.match(/^([\s\S]*?)\s*d([a-zA-Zα-ωθφ])\s*$/);
                if (dm) {
                    emit(lower && upper
                        ? `${prefix} from ${lower} to ${upper} of ${convertLatex(dm[1].trim())} d${dm[2]}`
                        : `${prefix} of ${convertLatex(dm[1].trim())} d${dm[2]}`);
                    i = s.length;
                } else {
                    emit(lower && upper ? `${prefix} from ${lower} to ${upper} of ` : `${prefix} of `);
                }
                continue;
            }

            // ── \sum ──────────────────────────────────────────────
            if (cmd === '\\sum') {
                let lower = '', upper = '';
                for (let a = 0; a < 2; a++) { i = skipSpace(s, i); if (i >= s.length) break; if (s[i] === '_') { i++; const b = readArg(s, i); lower = convertLatex(b.content); i = b.end; } else if (s[i] === '^') { i++; const b = readArg(s, i); upper = convertLatex(b.content); i = b.end; } else break; }
                emit(lower && upper ? `sum(${lower} to ${upper}, ${convertLatex(s.substring(i).trim())})` : `sum(${convertLatex(s.substring(i).trim())})`);
                i = s.length; continue;
            }

            // ── \prod ─────────────────────────────────────────────
            if (cmd === '\\prod') {
                let lower = '', upper = '';
                for (let a = 0; a < 2; a++) { i = skipSpace(s, i); if (i >= s.length) break; if (s[i] === '_') { i++; const b = readArg(s, i); lower = convertLatex(b.content); i = b.end; } else if (s[i] === '^') { i++; const b = readArg(s, i); upper = convertLatex(b.content); i = b.end; } else break; }
                emit(lower && upper ? `product(${lower} to ${upper}, ${convertLatex(s.substring(i).trim())})` : `product(${convertLatex(s.substring(i).trim())})`);
                i = s.length; continue;
            }

            // ── \lim ──────────────────────────────────────────────
            if (cmd === '\\lim') {
                i = skipSpace(s, i);
                let lp = '';
                if (i < s.length && s[i] === '_') { i++; const b = readArg(s, i); lp = convertLatex(b.content); i = b.end; }
                emit(lp ? `lim(${lp}, ${convertLatex(s.substring(i).trim())})` : `lim(${convertLatex(s.substring(i).trim())})`);
                i = s.length; continue;
            }

            // ── Function names ─────────────────────────────────────
            if (FUNC_MAP[cmd]) {
                const fname = FUNC_MAP[cmd];
                i = skipSpace(s, i);
                let power = '';
                if (i < s.length && s[i] === '^') { i++; const pA = readArg(s, i); power = convertLatex(pA.content); i = pA.end; i = skipSpace(s, i); }
                let sub = '';
                if (i < s.length && s[i] === '_') { i++; const sA = readArg(s, i); sub = convertLatex(sA.content); i = sA.end; i = skipSpace(s, i); }
                let argStr = '';
                if (i < s.length && (s[i] === '{' || s[i] === '(' || s[i] === '[')) { const g = extractGroup(s, i); argStr = convertLatex(g.content); i = g.end; }
                else if (i < s.length && /[a-zA-Zα-ωθφ0-9]/.test(s[i])) { argStr = s[i]; i++; }
                const fn = sub ? `${fname}_${sub}` : fname;
                emit(power ? `${fn}(${argStr})^${power}` : `${fn}(${argStr})`);
                continue;
            }

            // ── \binom ────────────────────────────────────────────
            if (cmd === '\\binom' || cmd === '\\dbinom' || cmd === '\\tbinom') {
                const nA = readArg(s, i); i = nA.end; const kA = readArg(s, i); i = kA.end;
                emit(`C(${convertLatex(nA.content)}, ${convertLatex(kA.content)})`);
                continue;
            }

            // ── Decorators ────────────────────────────────────────
            if (['\\vec', '\\hat', '\\widehat'].includes(cmd)) { const b = readArg(s, i); i = b.end; emit(`${convertLatex(b.content)}^`); continue; }
            if (['\\bar', '\\overline'].includes(cmd)) { const b = readArg(s, i); i = b.end; emit(`${convertLatex(b.content)}̄`); continue; }
            if (['\\tilde', '\\widetilde'].includes(cmd)) { const b = readArg(s, i); i = b.end; emit(`${convertLatex(b.content)}~`); continue; }
            if (['\\underline', '\\underbrace', '\\overbrace'].includes(cmd)) { const b = readArg(s, i); i = b.end; emit(convertLatex(b.content)); continue; }
            if (['\\overset', '\\underset'].includes(cmd)) { const _t = readArg(s, i); i = _t.end; const b = readArg(s, i); i = b.end; emit(convertLatex(b.content)); continue; }
            if (['\\mathbf', '\\mathit', '\\mathsf', '\\mathtt', '\\mathbb', '\\mathcal', '\\mathscr', '\\mathfrak'].includes(cmd)) { const b = readArg(s, i); i = b.end; emit(convertLatex(b.content)); continue; }
            if (['\\displaystyle', '\\textstyle', '\\scriptstyle', '\\scriptscriptstyle',
                '\\normalsize', '\\small', '\\large', '\\Large', '\\LARGE', '\\huge', '\\Huge', '\\tiny',
                '\\left', '\\right', '\\nonumber', '\\label', '\\tag', '\\not'].includes(cmd)) continue;

            emit(cmd.replace(/^\\/, ''));
            continue;
        }

        // ── ^{exponent} ───────────────────────────────────────────
        if (ch === '^') {
            i++;
            const arg = readArg(s, i); i = arg.end;
            const exp = convertLatex(arg.content);
            result += hasBareOperator(exp) ? `^(${exp})` : `^${exp}`;
            continue;
        }

        // ── _{subscript} ──────────────────────────────────────────
        if (ch === '_') {
            i++;
            const arg = readArg(s, i); i = arg.end;
            result += `_${convertLatex(arg.content)}`;
            continue;
        }

        // ── Plain text: greedy match known function names first ───
        {
            let matched = false;
            for (const fn of KNOWN_FUNCS) {
                if (s.startsWith(fn, i)) {
                    const after = i + fn.length;
                    const nextCh = after < s.length ? s[after] : '';
                    if (/[a-zA-Z]/.test(nextCh)) continue;
                    i = after; i = skipSpace(s, i);
                    let power = '';
                    if (i < s.length && s[i] === '^') { i++; const pA = readArg(s, i); power = convertLatex(pA.content); i = pA.end; i = skipSpace(s, i); }
                    let argStr = '';
                    if (i < s.length && (s[i] === '(' || s[i] === '{' || s[i] === '[')) { const g = extractGroup(s, i); argStr = convertLatex(g.content); i = g.end; }
                    else if (i < s.length && /[a-zA-Zα-ωθφ0-9]/.test(s[i])) { argStr = s[i]; i++; }
                    emit(power ? `${fn}(${argStr})^${power}` : `${fn}(${argStr})`);
                    matched = true; break;
                }
            }
            if (matched) continue;
        }

        // ── Plain character ───────────────────────────────────────
        emit(ch);
        i++;
    }

    return result
        .replace(/\s{2,}/g, ' ')
        .replace(/\(\s+/g, '(').replace(/\s+\)/g, ')')
        .replace(/\[\s+/g, '[').replace(/\s+\]/g, ']')
        .trim();
}

// ─────────────────────────────────────────────────────────────
// SPECIAL-FORM DETECTORS
// ─────────────────────────────────────────────────────────────
function handleDerivativeNotation(latex: string): string | null {
    const p = preNormalise(latex).trim();
    const re = /^\\frac\s*\{\s*d(\^\{?([0-9]+)\}?)?\s*\}\s*\{\s*d\s*(\\?[a-zA-Z]+)(\^\{?([0-9]+)\}?)?\s*\}\s*([\s\S]+)$/;
    const m = p.match(re); if (!m) return null;
    const order = m[2] ? parseInt(m[2]) : 1;
    const variable = m[3].replace(/^\\/, '');
    const content = convertLatex(m[6] || '');
    return order === 1 ? `d/d${variable} [${content}]` : `d^${order}/d${variable}^${order} [${content}]`;
}

function handlePartialDerivative(latex: string): string | null {
    const p = preNormalise(latex).trim();
    const re = /^\\frac\s*\{\s*\\partial\s*([^}]*)\}\s*\{\s*\\partial\s*([^}]*)\}/;
    const m = p.match(re); if (!m) return null;
    return `∂${convertLatex(m[1].trim()) || 'f'}/∂${convertLatex(m[2].trim())}`;
}

// ─────────────────────────────────────────────────────────────
// POST-CLEAN
// ─────────────────────────────────────────────────────────────
function postClean(s: string): string {
    return s
        .replace(/([a-zA-Z0-9])right\b/g, '$1').replace(/([a-zA-Z0-9])left\b/g, '$1')
        .replace(/\bright\b/g, '').replace(/\bleft\b/g, '')
        .replace(/\/\s*\)/g, ')').replace(/\/\s*\]/g, ']')
        .replace(/\*{2,}/g, '*')
        // MathLive artifact: -1*func or +1*func → -func / +func
        .replace(/([-+*/(\[,])\s*1\s*\*(?=[a-zA-Z(])/g, '$1')
        .replace(/^1\*(?=[a-zA-Z(])/, '')
        .replace(/\$\$/g, '').replace(/\$/g, '')
        .replace(/\s{2,}/g, ' ')
        .trim();
}

// ─────────────────────────────────────────────────────────────
// PUBLIC API
// ─────────────────────────────────────────────────────────────

/**
 * Convert a LaTeX expression to human-readable keyboard notation.
 */
export function latexToHuman(latex: string): string {
    if (!latex || typeof latex !== 'string' || !latex.trim()) return '';
    const trimmed = latex.trim();
    const deriv = handleDerivativeNotation(trimmed);
    if (deriv) return postClean(deriv);
    const partial = handlePartialDerivative(trimmed);
    if (partial) return postClean(partial);
    return postClean(convertLatex(trimmed));
}

/**
 * Extracts the core mathematical function for analysis, stripping assignments, integrals, and derivatives.
 */
export function extractCoreFunctionForAnalysis(latex: string): string {
    if (!latex || typeof latex !== 'string' || !latex.trim()) return '';
    let s = latex.trim();

    // 1. Strip assignments (e.g. y = ..., f(x) = ...)
    const eqMatch = s.match(/^[a-zA-Z_0-9]+(?:\([^)]+\))?\s*=\s*([\s\S]+)$/);
    if (eqMatch) {
        s = eqMatch[1].trim();
    }

    s = preNormalise(s).trim();

    // 2. Handle Derivatives (e.g. \frac{d}{dx} ...)
    const derivRe = /^\\frac\s*\{\s*d[^{}]*\}\s*\{\s*d[^{}]*\}\s*([\s\S]+)$/;
    const derivMatch = s.match(derivRe);
    if (derivMatch) s = derivMatch[1].trim();

    const partialRe = /^\\frac\s*\{\s*\\partial[^{}]*\}\s*\{\s*\\partial[^{}]*\}\s*([\s\S]+)$/;
    const partialMatch = s.match(partialRe);
    if (partialMatch) s = partialMatch[1].trim();

    // 3. Handle Limits (e.g. \lim_{x \to 0} ...)
    const limRe = /^\\lim(?:_[^{]*|_\s*\{[^}]*\})\s*([\s\S]+)$/;
    const limMatch = s.match(limRe);
    if (limMatch) s = limMatch[1].trim();

    // 4. Handle Integrals
    if (/^\\(i+nt|oint)/.test(s)) {
        let i = 0;
        while (i < s.length && /[a-zA-Z\\]/.test(s[i])) i++;
        for (let a = 0; a < 2; a++) {
            i = skipSpace(s, i);
            if (i >= s.length) break;
            if (s[i] === '_' || s[i] === '^') {
                i++;
                if (s[i] === '{') {
                    const g = extractGroup(s, i);
                    i = g.end;
                } else if (s[i] === '\\') {
                    const t = readToken(s, i);
                    i = t.end;
                } else {
                    i++;
                }
            } else break;
        }
        let rest = s.substring(i).trim();
        const dMatch = rest.match(/^([\s\S]*?)\s*d[a-zA-Zα-ωθφ]\s*$/);
        if (dMatch) s = dMatch[1].trim();
        else s = rest;
    }

    // Clean up any outer brackets like \left[ ... \right] or [ ... ]
    s = s.replace(/^\\left\[([\s\S]*)\\right\]$/, '$1').trim();
    s = s.replace(/^\\left\(([\s\S]*)\\right\)$/, '$1').trim();
    if (s.startsWith('[') && s.endsWith(']')) s = s.slice(1, -1).trim();
    if (s.startsWith('(') && s.endsWith(')')) s = s.slice(1, -1).trim();

    return latexToHuman(s);
}

/**
 * Log both human-readable and raw LaTeX for an expression.
 * Call right after the visibility guard in processExpression.
 *
 * @example
 *   logHumanInput(id, rawLatex);
 */
export function logHumanInput(id: string, rawLatex: string): void {
    const human = latexToHuman(rawLatex);
    console.log(`[HUMAN INPUT] id=${id} → ${human}`);
    console.log(`[RAW  LATEX ] id=${id} → ${rawLatex}`);
}

export function normalizeAbsDelimiters(latex: string, format: 'abs' | 'pipes' | 'latex' = 'abs'): string {
    let s = latex.replace(/\\left\s*\|/g, '|').replace(/\\right\s*\|/g, '|');
    s = s.replace(/\\lvert/g, '|').replace(/\\rvert/g, '|');
    s = s.replace(/\\left\s*\\(?:lvert|vert)/ig, '|').replace(/\\right\s*\\(?:rvert|vert)/ig, '|');
    s = s.replace(/\\vert/ig, '|');

    let result = '';
    let stack: number[] = [];
    
    for (let i = 0; i < s.length; i++) {
        let char = s[i];
        if (char === '|') {
            let prevChar = i > 0 ? s[i-1] : '';
            let nextChar = i < s.length - 1 ? s[i+1] : '';
            
            let prevIsOpOrSpaceOrOpen = /[-+*=/({\[<>,\s^|]/.test(prevChar) || prevChar === '';
            let nextIsOpOrSpaceOrClose = /[-+*=/)\\]}>,\s^|]/.test(nextChar) || nextChar === '';
            
            let isOpen = false;
            
            if (stack.length > 0) {
                if (prevChar && !/[-+*=({\[<>,^|\s]/.test(prevChar)) { 
                    isOpen = false; 
                } else if (prevIsOpOrSpaceOrOpen && !nextIsOpOrSpaceOrClose) {
                    isOpen = true;
                } else {
                    isOpen = false;
                }
            } else {
                isOpen = true;
            }
            
            if (isOpen) {
                stack.push(result.length);
                result += format === 'abs' ? 'abs(' : (format === 'latex' ? '\\left|' : '|');
            } else {
                if (stack.length > 0) {
                    stack.pop();
                    result += format === 'abs' ? ')' : (format === 'latex' ? '\\right|' : '|');
                } else {
                    stack.push(result.length);
                    result += format === 'abs' ? 'abs(' : (format === 'latex' ? '\\left|' : '|');
                }
            }
        } else {
            result += char;
        }
    }
    
    while (stack.length > 0) {
        stack.pop();
        result += format === 'abs' ? ')' : (format === 'latex' ? '\\right|' : '|');
    }
    
    return result;
}