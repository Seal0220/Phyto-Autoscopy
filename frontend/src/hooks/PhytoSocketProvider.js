"use client";

import {
  createContext,
  useContext,
} from "react";

import usePhytoSocket from "@/hooks/usePhytoSocket";

const PhytoSocketContext = createContext(null);

export default function PhytoSocketProvider({ children }) {
  const socket = usePhytoSocket();

  return (
    <PhytoSocketContext.Provider value={socket}>
      {children}
    </PhytoSocketContext.Provider>
  );
}

export function usePhytoSocketContext() {
  const context = useContext(PhytoSocketContext);

  if (!context) {
    throw new Error("usePhytoSocketContext 必須在 PhytoSocketProvider 內使用。");
  }

  return context;
}
