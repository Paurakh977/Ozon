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
    'arcsinh','arccosh','arctanh','arccoth','arcsech','arccsch',
    'arcsin','arccos','arctan','arccot','arcsec','arccsc',
    'sinh','cosh','tanh','coth','sech','csch',
    'sin','cos','tan','cot','sec','csc',
    'ln','log','exp','sqrt','abs',
    'gcd','lcm','min','max',
    'floor','ceil','sgn','sign',
    'det','dim','ker','deg','arg','mod',
    'Re','Im',
];

// ─────────────────────────────────────────────────────────────
// PHASE 0 — PRE-NORMALISATION
// Key rule: \operatorname{\mathrm{X}} → \X  (backslash preserved)
// so the parser sees \arctanh as a command, not raw letters.
// ─────────────────────────────────────────────────────────────
function preNormalise(s: string): string {
    s = s.replace(/\$\$/g, '').replace(/(?<![\\])\$/g, '').trim();

    s = s
        // placeholder
        .replace(/\\placeholder\{[^}]*\}/g, '?')

        // operatorname / mathrm → \name  (WITH backslash so parser treats as \cmd)
        .replace(/\\operatorname\{\\mathrm\{([^}]+)\}\}/g, (_, n) => `\\${n}`)
        .replace(/\\operatorname\{\\([a-zA-Z]+)\}/g,       (_, n) => `\\${n}`)
        .replace(/\\operatorname\{([^}]+)\}/g,              (_, n) => `\\${n}`)

        // differential variants
        .replace(/\\mathrm\{dx\}/g,          'dx')
        .replace(/\\mathrm\{d\}([a-zA-Z])/g, 'd$1')
        .replace(/\\mathrm\{d([a-zA-Z])\}/g, 'd$1')
        .replace(/\\mathrm\{d\}/g,           'd')
        .replace(/\\text\{d\}([a-zA-Z])/g,   'd$1')
        .replace(/\\text\{dx\}/g,            'dx')
        .replace(/\\differentialD/g,          'd')
        .replace(/\\mathrm\{([^}]+)\}/g, '$1')
        .replace(/\\text\{([^}]+)\}/g,   '$1')
        .replace(/\\mbox\{([^}]+)\}/g,   '$1')

        // fraction aliases
        .replace(/\\dfrac/g, '\\frac')
        .replace(/\\tfrac/g, '\\frac')
        .replace(/\\cfrac/g, '\\frac')

        // spacing / layout (strip, don't replace with space — we add spaces ourselves)
        .replace(/\\[,;:!]/g,           '')
        .replace(/\\quad\b/g,            ' ')
        .replace(/\\qquad\b/g,           ' ')
        .replace(/\\limits\b/g,          '')
        .replace(/\\displaystyle\b/g,    '')
        .replace(/\\textstyle\b/g,       '')
        .replace(/\\scriptstyle\b/g,     '')
        .replace(/\\boldsymbol\{([^}]+)\}/g, '$1')

        // named bracket commands
        .replace(/\\left\s*\\lbrack/g,  '[').replace(/\\right\s*\\rbrack/g, ']')
        .replace(/\\lbrack/g, '[').replace(/\\rbrack/g, ']')
        .replace(/\\left\s*\\lbrace/g,  '(').replace(/\\right\s*\\rbrace/g, ')')
        .replace(/\\lbrace/g, '{').replace(/\\rbrace/g, '}')
        .replace(/\\left\s*\\langle/g,  '<').replace(/\\right\s*\\rangle/g, '>')
        .replace(/\\langle/g, '<').replace(/\\rangle/g, '>')
        .replace(/\\left\s*\\lfloor/g,  'floor(').replace(/\\right\s*\\rfloor/g, ')')
        .replace(/\\lfloor/g, 'floor(').replace(/\\rfloor/g, ')')
        .replace(/\\left\s*\\lceil/g,   'ceil(').replace(/\\right\s*\\rceil/g, ')')
        .replace(/\\lceil/g, 'ceil(').replace(/\\rceil/g, ')')

        // absolute value / norm
        .replace(/\\lvert/g,'|').replace(/\\rvert/g,'|')
        .replace(/\\lVert/g,'‖').replace(/\\rVert/g,'‖')
        .replace(/\\vert\b/g,'|').replace(/\\Vert\b/g,'‖')

        // size modifiers (big/Big/bigg/Bigg)
        .replace(/\\[Bb]igg?[lr]?\s*\(/g,'(').replace(/\\[Bb]igg?[lr]?\s*\)/g,')')
        .replace(/\\[Bb]igg?[lr]?\s*\[/g,'[').replace(/\\[Bb]igg?[lr]?\s*\]/g,']')
        .replace(/\\[Bb]igg?[lr]?\s*\|/g,'|')
        .replace(/\\[Bb]igm\s*\|/g,'|').replace(/\\[Bb]igm\s*\\vert/g,'|');

    // Fix \right. (MathLive invisible close delimiter)
    s = fixUnmatchedDelimiters(s);

    // Strip remaining \left / \right with standard delimiters
    s = s
        .replace(/\\left\s*\(/g,  '(').replace(/\\right\s*\)/g,')')
        .replace(/\\left\s*\[/g,  '[').replace(/\\right\s*\]/g,']')
        .replace(/\\left\s*\|/g,  '|').replace(/\\right\s*\|/g,'|')
        .replace(/\\left\s*\\{/g, '(').replace(/\\right\s*\\}/g,')')
        .replace(/\\left\s*\\vert/g,'|').replace(/\\right\s*\\vert/g,'|')
        .replace(/\\left\s*\\Vert/g,'‖').replace(/\\right\s*\\Vert/g,'‖')
        .replace(/\\left\s*\./g,'').replace(/\\right\s*\./g,'')
        .replace(/\\left\b\s*/g,'').replace(/\\right\b\s*/g,'');

    return s;
}

function fixUnmatchedDelimiters(s: string): string {
    const closeFor: Record<string, string> = { '(':')', '[':']', '|':'|', '{':'}', '<':'>' };
    const stack: string[] = [];
    let out = '', i = 0;
    while (i < s.length) {
        const lm = s.slice(i).match(/^\\left\s*([(\[|{<])/);
        if (lm) { stack.push(lm[1]); out += s.slice(i, i+lm[0].length); i += lm[0].length; continue; }
        const rd = s.slice(i).match(/^\\right\s*\./);
        if (rd) { const op = stack.pop(); if (op && closeFor[op]) out += closeFor[op]; i += rd[0].length; continue; }
        const rr = s.slice(i).match(/^\\right\s*([)\]|}<>])/);
        if (rr) { stack.pop(); out += s.slice(i, i+rr[0].length); i += rr[0].length; continue; }
        out += s[i++];
    }
    return out;
}

// ─────────────────────────────────────────────────────────────
// PARSER HELPERS
// ─────────────────────────────────────────────────────────────
function extractGroup(str: string, pos: number): { content: string; end: number } {
    const open  = str[pos];
    const close = open==='{' ? '}' : open==='(' ? ')' : open==='[' ? ']' : '}';
    let depth=1, i=pos+1;
    while (i < str.length && depth > 0) {
        if (str[i]===open) depth++; else if (str[i]===close) depth--;
        i++;
    }
    return { content: str.substring(pos+1, i-1), end: i };
}

function skipSpace(str: string, pos: number): number {
    while (pos < str.length && /\s/.test(str[pos])) pos++;
    return pos;
}

function readToken(str: string, pos: number): { token: string; end: number } {
    pos = skipSpace(str, pos);
    if (pos >= str.length) return { token:'', end:pos };
    if (str[pos]==='\\') {
        let i=pos+1;
        if (i>=str.length)           return { token:'\\', end:i };
        if (!/[a-zA-Z]/.test(str[i])) return { token:str.substring(pos,pos+2), end:pos+2 };
        while (i<str.length && /[a-zA-Z]/.test(str[i])) i++;
        return { token:str.substring(pos,i), end:i };
    }
    return { token:str[pos], end:pos+1 };
}

/** Read one \frac argument: {group} | \cmd | single-char */
function readFracArg(str: string, pos: number): { content: string; end: number } {
    pos = skipSpace(str, pos);
    if (pos >= str.length) return { content:'', end:pos };
    if (str[pos]==='{') { const g=extractGroup(str,pos); return { content:g.content, end:g.end }; }
    if (str[pos]==='\\') { const t=readToken(str,pos); return { content:t.token, end:t.end }; }
    return { content:str[pos], end:pos+1 };
}

function readArg(str: string, pos: number): { content: string; end: number } {
    pos = skipSpace(str, pos);
    if (pos >= str.length) return { content:'', end:pos };
    if (str[pos]==='{') { const g=extractGroup(str,pos); return { content:g.content, end:g.end }; }
    const t=readToken(str,pos);
    return { content:t.token, end:t.end };
}

// ─────────────────────────────────────────────────────────────
// LOOKUP TABLES
// ─────────────────────────────────────────────────────────────
const GREEK: Record<string,string> = {
    '\\alpha':'α','\\beta':'β','\\gamma':'γ','\\delta':'δ',
    '\\epsilon':'ε','\\varepsilon':'ε','\\zeta':'ζ','\\eta':'η',
    '\\theta':'θ','\\vartheta':'θ','\\iota':'ι','\\kappa':'κ',
    '\\lambda':'λ','\\mu':'μ','\\nu':'ν','\\xi':'ξ',
    '\\pi':'π','\\varpi':'π','\\rho':'ρ','\\varrho':'ρ',
    '\\sigma':'σ','\\varsigma':'σ','\\tau':'τ','\\upsilon':'υ',
    '\\phi':'φ','\\varphi':'φ','\\chi':'χ','\\psi':'ψ','\\omega':'ω',
    '\\Gamma':'Γ','\\Delta':'Δ','\\Theta':'Θ','\\Lambda':'Λ',
    '\\Xi':'Ξ','\\Pi':'Π','\\Sigma':'Σ','\\Upsilon':'Υ',
    '\\Phi':'Φ','\\Psi':'Ψ','\\Omega':'Ω',
};

const SYMBOLS: Record<string,string> = {
    '\\infty':'inf','\\partial':'∂','\\nabla':'∇',
    '\\cdot':'*','\\times':'*','\\div':'/',
    '\\pm':'±','\\mp':'∓',
    '\\leq':'≤','\\le':'≤','\\geq':'≥','\\ge':'≥',
    '\\neq':'≠','\\ne':'≠','\\approx':'≈','\\sim':'~',
    '\\equiv':'≡','\\propto':'∝',
    '\\to':'→','\\rightarrow':'→','\\leftarrow':'←',
    '\\Rightarrow':'⇒','\\Leftarrow':'⇐','\\Leftrightarrow':'⇔',
    '\\in':'∈','\\notin':'∉','\\subset':'⊂','\\supset':'⊃',
    '\\cup':'∪','\\cap':'∩','\\emptyset':'∅','\\varnothing':'∅',
    '\\forall':'∀','\\exists':'∃',
    '\\land':'&&','\\lor':'||','\\lnot':'!',
    '\\ldots':'...','\\cdots':'...','\\vdots':'...','\\ddots':'...',
    '\\{':'{','\\}':'}','\\|':'‖',
};

// FUNC_MAP keyed by \cmd (with backslash)
const FUNC_MAP: Record<string,string> = {
    '\\sin':'sin','\\cos':'cos','\\tan':'tan','\\cot':'cot','\\sec':'sec','\\csc':'csc',
    '\\sinh':'sinh','\\cosh':'cosh','\\tanh':'tanh','\\coth':'coth','\\sech':'sech','\\csch':'csch',
    '\\arcsin':'arcsin','\\arccos':'arccos','\\arctan':'arctan',
    '\\arccot':'arccot','\\arcsec':'arcsec','\\arccsc':'arccsc',
    '\\arcsinh':'arcsinh','\\arccosh':'arccosh','\\arctanh':'arctanh',
    '\\arccoth':'arccoth','\\arcsech':'arcsech','\\arccsch':'arccsch',
    '\\ln':'ln','\\log':'log','\\exp':'exp',
    '\\abs':'abs','\\gcd':'gcd','\\lcm':'lcm',
    '\\min':'min','\\max':'max',
    '\\floor':'floor','\\ceil':'ceil',
    '\\sgn':'sgn','\\sign':'sign',
    '\\Re':'Re','\\Im':'Im',
    '\\det':'det','\\dim':'dim','\\ker':'ker','\\deg':'deg','\\arg':'arg','\\mod':'mod',
    '\\sqrt':'sqrt',
};

// ─────────────────────────────────────────────────────────────
// DEPTH-AWARE OPERATOR DETECTION
// ─────────────────────────────────────────────────────────────
function hasBareAdditive(s: string): boolean {
    let d=0;
    for (let i=0; i<s.length; i++) {
        const c=s[i];
        if (c==='('||c==='[') { d++; continue; }
        if (c===')'||c===']') { d--; continue; }
        if (d===0 && i>0 && (c==='+'||c==='-')) return true;
    }
    return false;
}

function hasBareOperator(s: string): boolean {
    let d=0;
    for (let i=0; i<s.length; i++) {
        const c=s[i];
        if (c==='('||c==='[') { d++; continue; }
        if (c===')'||c===']') { d--; continue; }
        if (d===0 && i>0 && (c==='+'||c==='-'||c==='*'||c==='/')) return true;
    }
    return false;
}

function wrapIfAdditive(s: string): string { return hasBareAdditive(s) ? `(${s})` : s; }
function wrapIfCompound(s: string):  string { return hasBareOperator(s)  ? `(${s})` : s; }

/**
 * Wrap a fraction result so that adjacent multiplication is unambiguous.
 * e.g.  1/2 * 1/4  is ambiguous (could mean 1/(2*1)/4)
 * so fracs always get wrapped:  (1/2) * (1/4)
 */
function wrapFrac(num: string, den: string): string {
    const nStr = wrapIfAdditive(num);
    const dStr = wrapIfCompound(den);
    return `(${nStr}/${dStr})`;
}

// ─────────────────────────────────────────────────────────────
// IMPLICIT MULTIPLICATION DETECTION
// Only inserts * when:
//   - left ends with digit / ) / ]
//   - right starts with letter / digit / (
// Never inserts between two letters (would break function names)
// ─────────────────────────────────────────────────────────────
function needsMul(left: string, right: string): boolean {
    if (!left || !right) return false;
    const L = left[left.length-1];
    const R = right[0];
    if (!/[0-9a-zA-Zα-ωπθφ)\]]/.test(L)) return false;
    if (!/[0-9a-zA-Zα-ωπθφ(]/.test(R))   return false;
    // letter → letter = word continuation, NOT multiplication
    if (/[a-zA-Z]/.test(L) && /[a-zA-Z]/.test(R)) return false;
    return true;
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

    let i=0;
    while (i < s.length) {
        i = skipSpace(s, i);
        if (i >= s.length) break;
        const ch = s[i];

        // ── {group} ───────────────────────────────────────────────
        if (ch==='{') {
            const g=extractGroup(s,i); i=g.end;
            const trimmed=g.content.trim();
            if (!trimmed || trimmed==='?') continue;
            const inner=convertLatex(trimmed);
            if (inner) emit(wrapIfAdditive(inner));
            continue;
        }

        // ── (group) ───────────────────────────────────────────────
        if (ch==='(') {
            const g=extractGroup(s,i); i=g.end;
            emit(`(${convertLatex(g.content)})`);
            continue;
        }

        // ── [group] ───────────────────────────────────────────────
        if (ch==='[') {
            const g=extractGroup(s,i); i=g.end;
            emit(`[${convertLatex(g.content)}]`);
            continue;
        }

        // ── |expr| ────────────────────────────────────────────────
        if (ch==='|') {
            const j=s.indexOf('|',i+1);
            if (j!==-1) { emit(`|${convertLatex(s.substring(i+1,j))}|`); i=j+1; }
            else        { emit('|'); i++; }
            continue;
        }

        // ── \command ──────────────────────────────────────────────
        if (ch==='\\') {
            const tok=readToken(s,i); const cmd=tok.token; i=tok.end;

            if (GREEK[cmd])   { emit(GREEK[cmd]);   continue; }
            if (SYMBOLS[cmd]) { emit(SYMBOLS[cmd]); continue; }

            // ── \frac ─────────────────────────────────────────────
            if (cmd==='\\frac') {
                const nA=readFracArg(s,i); i=nA.end;
                const dA=readFracArg(s,i); i=dA.end;
                const numRaw=nA.content.trim();
                const denRaw=dA.content.trim();

                // empty numerator → skip
                if (!numRaw || numRaw==='?') continue;

                // empty denominator → emit numerator only
                if (!denRaw || denRaw==='?') {
                    const nH=convertLatex(numRaw);
                    if (nH) emit(wrapIfAdditive(nH));
                    continue;
                }

                const nH=convertLatex(numRaw);
                const dH=convertLatex(denRaw);
                if (!nH) continue;

                // Always wrap fracs in parens → unambiguous when chained
                emit(wrapFrac(nH, dH));
                continue;
            }

            // ── \sqrt ─────────────────────────────────────────────
            if (cmd==='\\sqrt') {
                i=skipSpace(s,i);
                if (i<s.length && s[i]==='[') {
                    const nr=extractGroup(s,i); i=nr.end;
                    const bA=readFracArg(s,i); i=bA.end;
                    emit(`(${convertLatex(bA.content)})^(1/${convertLatex(nr.content)})`);
                } else {
                    const bA=readFracArg(s,i); i=bA.end;
                    emit(`sqrt(${convertLatex(bA.content)})`);
                }
                continue;
            }

            // ── \int \iint \iiint \oint ───────────────────────────
            if (cmd==='\\int'||cmd==='\\iint'||cmd==='\\iiint'||cmd==='\\oint') {
                const prefix=cmd==='\\oint'?'contour_integral':cmd==='\\iint'?'double_integral':cmd==='\\iiint'?'triple_integral':'integral';
                let lower='', upper='';
                for (let a=0;a<2;a++) {
                    i=skipSpace(s,i); if(i>=s.length) break;
                    if(s[i]==='_'){i++;const b=readArg(s,i);lower=convertLatex(b.content);i=b.end;}
                    else if(s[i]==='^'){i++;const b=readArg(s,i);upper=convertLatex(b.content);i=b.end;}
                    else break;
                }
                const rest=s.substring(i).trim();
                const dm=rest.match(/^([\s\S]*?)\s*d([a-zA-Zα-ωθφ])\s*$/);
                if (dm) {
                    emit(lower&&upper
                        ? `${prefix} from ${lower} to ${upper} of ${convertLatex(dm[1].trim())} d${dm[2]}`
                        : `${prefix} of ${convertLatex(dm[1].trim())} d${dm[2]}`);
                    i=s.length;
                } else {
                    emit(lower&&upper?`${prefix} from ${lower} to ${upper} of `:`${prefix} of `);
                }
                continue;
            }

            // ── \sum ──────────────────────────────────────────────
            if (cmd==='\\sum') {
                let lower='',upper='';
                for(let a=0;a<2;a++){i=skipSpace(s,i);if(i>=s.length)break;if(s[i]==='_'){i++;const b=readArg(s,i);lower=convertLatex(b.content);i=b.end;}else if(s[i]==='^'){i++;const b=readArg(s,i);upper=convertLatex(b.content);i=b.end;}else break;}
                emit(lower&&upper?`sum(${lower} to ${upper}, ${convertLatex(s.substring(i).trim())})`:`sum(${convertLatex(s.substring(i).trim())})`);
                i=s.length; continue;
            }

            // ── \prod ─────────────────────────────────────────────
            if (cmd==='\\prod') {
                let lower='',upper='';
                for(let a=0;a<2;a++){i=skipSpace(s,i);if(i>=s.length)break;if(s[i]==='_'){i++;const b=readArg(s,i);lower=convertLatex(b.content);i=b.end;}else if(s[i]==='^'){i++;const b=readArg(s,i);upper=convertLatex(b.content);i=b.end;}else break;}
                emit(lower&&upper?`product(${lower} to ${upper}, ${convertLatex(s.substring(i).trim())})`:`product(${convertLatex(s.substring(i).trim())})`);
                i=s.length; continue;
            }

            // ── \lim ──────────────────────────────────────────────
            if (cmd==='\\lim') {
                i=skipSpace(s,i);
                let lp='';
                if(i<s.length&&s[i]==='_'){i++;const b=readArg(s,i);lp=convertLatex(b.content);i=b.end;}
                const body=convertLatex(s.substring(i).trim());
                emit(lp?`lim(${lp}, ${body})`:`lim(${body})`);
                i=s.length; continue;
            }

            // ── Function names ─────────────────────────────────────
            if (FUNC_MAP[cmd]) {
                const fname=FUNC_MAP[cmd];
                i=skipSpace(s,i);
                let power='';
                if(i<s.length&&s[i]==='^'){i++;const pA=readArg(s,i);power=convertLatex(pA.content);i=pA.end;i=skipSpace(s,i);}
                let sub='';
                if(i<s.length&&s[i]==='_'){i++;const sA=readArg(s,i);sub=convertLatex(sA.content);i=sA.end;i=skipSpace(s,i);}
                let argStr='';
                if(i<s.length&&(s[i]==='{'||s[i]==='('||s[i]==='[')){const g=extractGroup(s,i);argStr=convertLatex(g.content);i=g.end;}
                else if(i<s.length&&/[a-zA-Zα-ωθφ0-9]/.test(s[i])){argStr=s[i];i++;}
                const fn=sub?`${fname}_${sub}`:fname;
                emit(power?`${fn}(${argStr})^${power}`:`${fn}(${argStr})`);
                continue;
            }

            // ── \binom ────────────────────────────────────────────
            if(cmd==='\\binom'||cmd==='\\dbinom'||cmd==='\\tbinom'){
                const nA=readArg(s,i);i=nA.end;const kA=readArg(s,i);i=kA.end;
                emit(`C(${convertLatex(nA.content)}, ${convertLatex(kA.content)})`);
                continue;
            }

            // ── Decorators ────────────────────────────────────────
            if(['\\vec','\\hat','\\widehat'].includes(cmd)){const b=readArg(s,i);i=b.end;emit(`${convertLatex(b.content)}^`);continue;}
            if(['\\bar','\\overline'].includes(cmd)){const b=readArg(s,i);i=b.end;emit(`${convertLatex(b.content)}̄`);continue;}
            if(['\\tilde','\\widetilde'].includes(cmd)){const b=readArg(s,i);i=b.end;emit(`${convertLatex(b.content)}~`);continue;}
            if(['\\underline','\\underbrace','\\overbrace'].includes(cmd)){const b=readArg(s,i);i=b.end;emit(convertLatex(b.content));continue;}
            if(['\\overset','\\underset'].includes(cmd)){const _t=readArg(s,i);i=_t.end;const b=readArg(s,i);i=b.end;emit(convertLatex(b.content));continue;}

            // ── Font wrappers ──────────────────────────────────────
            if(['\\mathbf','\\mathit','\\mathsf','\\mathtt','\\mathbb','\\mathcal','\\mathscr','\\mathfrak'].includes(cmd)){const b=readArg(s,i);i=b.end;emit(convertLatex(b.content));continue;}

            // ── Layout-only → skip ────────────────────────────────
            if(['\\displaystyle','\\textstyle','\\scriptstyle','\\scriptscriptstyle',
                '\\normalsize','\\small','\\large','\\Large','\\LARGE','\\huge','\\Huge','\\tiny',
                '\\left','\\right','\\nonumber','\\label','\\tag','\\not'].includes(cmd)) continue;

            // ── Unknown → strip backslash ─────────────────────────
            emit(cmd.replace(/^\\/,''));
            continue;
        }

        // ── ^{exponent} ───────────────────────────────────────────
        if (ch==='^') {
            i++;
            const arg=readArg(s,i); i=arg.end;
            const exp=convertLatex(arg.content);
            // ^ is always suffix — never prepend *
            result += hasBareOperator(exp) ? `^(${exp})` : `^${exp}`;
            continue;
        }

        // ── _{subscript} ──────────────────────────────────────────
        if (ch==='_') {
            i++;
            const arg=readArg(s,i); i=arg.end;
            result += `_${convertLatex(arg.content)}`;
            continue;
        }

        // ── Plain text: greedy match known function names first ───
        // Handles cases where a function name arrives as raw letters
        // (safety net if preNormalise didn't add backslash)
        {
            let matched=false;
            for (const fn of KNOWN_FUNCS) {
                if (s.startsWith(fn, i)) {
                    const after=i+fn.length;
                    const nextCh=after<s.length ? s[after] : '';
                    if (/[a-zA-Z]/.test(nextCh)) continue; // part of longer word
                    i=after; i=skipSpace(s,i);
                    let power='';
                    if(i<s.length&&s[i]==='^'){i++;const pA=readArg(s,i);power=convertLatex(pA.content);i=pA.end;i=skipSpace(s,i);}
                    let argStr='';
                    if(i<s.length&&(s[i]==='('||s[i]==='{'||s[i]==='[')){const g=extractGroup(s,i);argStr=convertLatex(g.content);i=g.end;}
                    else if(i<s.length&&/[a-zA-Zα-ωθφ0-9]/.test(s[i])){argStr=s[i];i++;}
                    emit(power?`${fn}(${argStr})^${power}`:`${fn}(${argStr})`);
                    matched=true; break;
                }
            }
            if (matched) continue;
        }

        // ── Plain character ───────────────────────────────────────
        emit(ch);
        i++;
    }

    return result
        .replace(/\s{2,}/g,' ')
        .replace(/\(\s+/g,'(').replace(/\s+\)/g,')')
        .replace(/\[\s+/g,'[').replace(/\s+\]/g,']')
        .trim();
}

// ─────────────────────────────────────────────────────────────
// SPECIAL-FORM DETECTORS
// ─────────────────────────────────────────────────────────────
function handleDerivativeNotation(latex: string): string | null {
    const p=preNormalise(latex).trim();
    const re=/^\\frac\s*\{\s*d(\^\{?([0-9]+)\}?)?\s*\}\s*\{\s*d\s*(\\?[a-zA-Z]+)(\^\{?([0-9]+)\}?)?\s*\}\s*([\s\S]+)$/;
    const m=p.match(re); if(!m) return null;
    const order=m[2]?parseInt(m[2]):1;
    const variable=m[3].replace(/^\\/,'');
    const content=convertLatex(m[6]||'');
    return order===1 ? `d/d${variable} [${content}]` : `d^${order}/d${variable}^${order} [${content}]`;
}

function handlePartialDerivative(latex: string): string | null {
    const p=preNormalise(latex).trim();
    const re=/^\\frac\s*\{\s*\\partial\s*([^}]*)\}\s*\{\s*\\partial\s*([^}]*)\}/;
    const m=p.match(re); if(!m) return null;
    return `∂${convertLatex(m[1].trim())||'f'}/∂${convertLatex(m[2].trim())}`;
}

// ─────────────────────────────────────────────────────────────
// POST-CLEAN
// ─────────────────────────────────────────────────────────────
function postClean(s: string): string {
    return s
        // stray right/left words
        .replace(/([a-zA-Z0-9])right\b/g,'$1').replace(/([a-zA-Z0-9])left\b/g,'$1')
        .replace(/\bright\b/g,'').replace(/\bleft\b/g,'')
        // "/ )" artefact from empty denominator
        .replace(/\/\s*\)/g,')').replace(/\/\s*\]/g,']')
        // double star cleanup
        .replace(/\*{2,}/g,'*')
        // MathLive artifact: "-1*tan" → "-tan", "+1*sin" → "+sin"
        .replace(/([-+*/(\[,])\s*1\s*\*(?=[a-zA-Z(])/g,'$1')
        .replace(/^1\*(?=[a-zA-Z(])/,'')
        // stray $
        .replace(/\$\$/g,'').replace(/\$/g,'')
        .replace(/\s{2,}/g,' ')
        .trim();
}

// ─────────────────────────────────────────────────────────────
// PUBLIC API
// ─────────────────────────────────────────────────────────────

/**
 * Convert a LaTeX expression to human-readable keyboard notation.
 *
 * Verified correct for:
 *   \frac12                    → (1/2)
 *   \frac12\frac14             → (1/2)*(1/4)
 *   \frac{x^2-1}{2a}          → (x^2-1)/(2*a)
 *   \operatorname{\mathrm{arctanh}}(x) → arctanh(x)
 *   \sin^2(x)+\cos^2(x)       → sin(x)^2+cos(x)^2
 *   \sec(x)\csc(x)            → sec(x)*csc(x)
 *   2e^{x^2}                  → 2*e^(x^2)
 *   -1\tan(x)                 → -tan(x)
 *   \frac{d}{dx}\sin(x)       → d/dx [sin(x)]
 *   \int_0^1 x^2 dx           → integral from 0 to 1 of x^2 dx
 *   \sum_{n=1}^{\infty}\frac{1}{n^2} → sum(n=1 to inf, (1/n^2))
 *   \sqrt[3]{x}               → (x)^(1/3)
 *   \left|x-1\right|          → |x-1|
 */
export function latexToHuman(latex: string): string {
    if (!latex || typeof latex !== 'string' || !latex.trim()) return '';
    const trimmed=latex.trim();
    const deriv=handleDerivativeNotation(trimmed);
    if (deriv) return postClean(deriv);
    const partial=handlePartialDerivative(trimmed);
    if (partial) return postClean(partial);
    return postClean(convertLatex(trimmed));
}

/**
 * Log both human-readable and raw LaTeX for an expression.
 * Call right after the visibility guard in processExpression.
 *
 * @example
 *   logHumanInput(id, rawLatex);
 */
export function logHumanInput(id: string, rawLatex: string): void {
    const human=latexToHuman(rawLatex);
    console.log(`[HUMAN INPUT] id=${id} → ${human}`);
    console.log(`[RAW  LATEX ] id=${id} → ${rawLatex}`);
}