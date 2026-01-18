
import React from "react";
import { Moon, Sun, Calculator as CalcIcon, PanelLeftClose, PanelLeftOpen } from "lucide-react";

interface HeaderProps {
    sidebarOpen: boolean;
    setSidebarOpen: (open: boolean) => void;
    theme: string | undefined;
    setTheme: (theme: string) => void;
}

export const Header: React.FC<HeaderProps> = ({ sidebarOpen, setSidebarOpen, theme, setTheme }) => {
    return (
        <header className="h-12 border-b flex items-center justify-between px-4 bg-card z-20 shadow-sm shrink-0">
            <div className="flex items-center gap-3">
                <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground">
                    {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
                </button>
                <h1 className="font-bold text-lg flex items-center gap-2">
                    <CalcIcon className="text-primary h-5 w-5" />
                    <span className="font-serif italic font-medium">ƒ</span>(x) Engine
                </h1>
            </div>
            <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className="p-2 rounded-full hover:bg-accent transition-colors">
                {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
        </header>
    );
};
