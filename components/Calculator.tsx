
"use client";

import React, { useState } from "react";
import { useTheme } from "next-themes";
import { useGraphEngine } from "./calculator/hooks/useGraphEngine";
import { useExpressionLogic } from "./calculator/hooks/useExpressionLogic";
import { Header } from "../ui/Header";
import { Sidebar } from "../ui/Sidebar";
import { GraphArea } from "../ui/GraphArea";
import { GraphLegend } from "../ui/GraphLegend";

export function Calculator() {
    const { theme, setTheme, resolvedTheme } = useTheme();
    const [sidebarOpen, setSidebarOpen] = useState(true);

    const { calculatorRef, calculatorInstance, libLoaded } = useGraphEngine(resolvedTheme);

    const {
        expressions,
        debugInfo,
        legendOpen,
        setLegendOpen,
        handleInput,
        handleColorChange,
        addExpr,
        removeExpr,
        toggleVisibility,
        setVisibilityMode
    } = useExpressionLogic(calculatorInstance);

    if (!libLoaded) return <div className="h-screen w-full flex items-center justify-center font-mono">Loading Engine...</div>;

    return (
        <div className="flex flex-col h-screen w-full bg-background overflow-hidden">
            <Header
                sidebarOpen={sidebarOpen}
                setSidebarOpen={setSidebarOpen}
                theme={theme}
                setTheme={setTheme}
            />

            <div className="flex-1 flex overflow-hidden">
                <div className={`flex flex-col border-r bg-card z-10 shadow-lg transition-all duration-300 ease-in-out relative ${sidebarOpen ? 'w-[400px] translate-x-0' : 'w-0 border-r-0 -translate-x-full opacity-0 overflow-hidden'}`}>
                    <Sidebar
                        expressions={expressions}
                        handleColorChange={handleColorChange}
                        handleInput={handleInput}
                        removeExpr={removeExpr}
                        addExpr={addExpr}
                        toggleVisibility={toggleVisibility}
                        setVisibilityMode={setVisibilityMode}
                        debugInfo={debugInfo}
                        resolvedTheme={resolvedTheme}
                    />
                </div>

                <GraphArea ref={calculatorRef}>
                    <GraphLegend
                        expressions={expressions}
                        legendOpen={legendOpen}
                        setLegendOpen={setLegendOpen}
                        resolvedTheme={resolvedTheme}
                    />
                </GraphArea>
            </div>
        </div>
    );
}