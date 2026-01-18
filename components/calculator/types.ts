
import React from "react";

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

export interface MathExpression {
    id: string;
    latex: string;
    result?: string;
    color: string;
}
