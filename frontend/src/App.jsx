/**
 * App.jsx - Application Root Component
 * --------------------------------------
 * Theme: light by default; persisted in localStorage.
 */

import React, { useEffect, useState } from "react";
import ChatPage from "./pages/ChatPage";

const THEME_KEY = "bmcs-sql-agent-theme";

function readStoredTheme() {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v === "dark" || v === "light") return v;
  } catch {
    /* ignore */
  }
  return "light";
}

export default function App() {
  const [theme, setTheme] = useState(readStoredTheme);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }

  return (
    <div className="app-root theme-transition" data-theme={theme}>
      <ChatPage theme={theme} toggleTheme={toggleTheme} />
    </div>
  );
}
