
import React, { forwardRef } from "react";

interface GraphAreaProps {
    children?: React.ReactNode;
}

export const GraphArea = forwardRef<HTMLDivElement, GraphAreaProps>(({ children }, ref) => {
    return (
        <div className="flex-1 relative bg-white dark:bg-black transition-all">
            <div ref={ref} className="absolute inset-0 w-full h-full" />
            {children}
        </div>
    );
});

GraphArea.displayName = "GraphArea";
