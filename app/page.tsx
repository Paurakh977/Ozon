"use client";

import { useState } from "react";
import { Calculator } from "@/components/Calculator";
import SplashScreen from "@/components/SplashScreen";

export default function Home() {
  const [splashDone, setSplashDone] = useState(false);

  if (!splashDone) {
    return <SplashScreen onComplete={() => setSplashDone(true)} />;
  }

  return <Calculator />;
}
