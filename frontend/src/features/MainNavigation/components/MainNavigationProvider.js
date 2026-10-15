"use client";

import {
  createContext,
  useContext,
  useState,
} from "react";

const MainNavigationContext = createContext(null);

export default function MainNavigationProvider({ children }) {
  const [registration, setRegistration] = useState(null);
  return (
    <MainNavigationContext.Provider value={{ registration, setRegistration }}>
      {children}
    </MainNavigationContext.Provider>
  );
}

export function useMainNavigationContext() {
  const context = useContext(MainNavigationContext);
  if (!context) throw new Error("導覽必須在 MainNavigationProvider 內使用。");
  return context;
}
