
// @ts-ignore - nerdamer doesn't have proper types
import nerdamer from 'nerdamer';
import 'nerdamer/Calculus';
import 'nerdamer/Algebra';
import 'nerdamer/Solve';
import { latexToNerdamer, nerdamerToLatex } from './latex-parser';

/**
 * Compute symbolic derivative using nerdamer
 */
export const computeSymbolicDerivative = (expression: string, variable: string = 'x', order: number = 1): string | null => {
    try {
        const nerdamerExpr = latexToNerdamer(expression);

        let result = nerdamer(nerdamerExpr);

        for (let i = 0; i < order; i++) {
            result = nerdamer.diff(result, variable);
        }

        const tex = nerdamerToLatex(result);

        // If result still contains 'diff' or 'integrate', nerdamer couldn't evaluate it
        const raw = result.toString();
        if (/\bdiff\b/.test(raw) || /\bintegrate\b/.test(raw)) {
            return null;
        }

        return tex;
    } catch {
        return null;
    }
};

/**
 * Compute symbolic integral using nerdamer
 */
export const computeSymbolicIntegral = (expression: string, variable: string = 'x'): string | null => {
    try {
        const nerdamerExpr = latexToNerdamer(expression);

        // Pre-handle integration of inverse hyperbolic functions which nerdamer fails on natively
        const varEsc = variable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        
        // 1. Standard asinh, acosh, atanh
        const matchStd = new RegExp(`^a(sinh|cosh|tanh)\\(\\s*${varEsc}\\s*\\)$`).exec(nerdamerExpr);
        if (matchStd) {
            const func = matchStd[1];
            if (func === 'sinh') return `${variable} \\operatorname{arcsinh}\\left(${variable}\\right) - \\sqrt{${variable}^2 + 1}`;
            if (func === 'cosh') return `${variable} \\operatorname{arccosh}\\left(${variable}\\right) - \\sqrt{${variable}^2 - 1}`;
            if (func === 'tanh') return `${variable} \\operatorname{arctanh}\\left(${variable}\\right) + \\frac{\\ln\\left(1 - ${variable}^2\\right)}{2}`;
        }

        // 2. Transformed reciprocal functions (latexToNerdamer converts acoth(x) -> atanh(1/(x)))
        const matchInv = new RegExp(`^a(tanh|cosh|sinh)\\(\\(?1\\/\\(${varEsc}\\)\\)?\\)$`).exec(nerdamerExpr);
        if (matchInv) {
            const func = matchInv[1];
            if (func === 'tanh') return `${variable} \\operatorname{arccoth}\\left(${variable}\\right) + \\frac{\\ln\\left(${variable}^2 - 1\\right)}{2}`;
            if (func === 'cosh') return `${variable} \\operatorname{arcsech}\\left(${variable}\\right) + \\arcsin\\left(${variable}\\right)`;
            if (func === 'sinh') return `${variable} \\operatorname{arccsch}\\left(${variable}\\right) + \\operatorname{sgn}\\left(${variable}\\right) \\operatorname{arcsinh}\\left(${variable}\\right)`;
        }

        const result = nerdamer.integrate(nerdamerExpr, variable);
        const tex = nerdamerToLatex(result);

        // If result still contains 'integrate' or '\int', nerdamer couldn't fully evaluate it
        const raw = result.toString();
        if (/\bintegrate\b/.test(raw) || /\bint\b/.test(raw) || tex.includes('\\int')) {
            return null;
        }

        return tex;
    } catch {
        return null;
    }
};
