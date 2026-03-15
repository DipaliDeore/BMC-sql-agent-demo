/**
 * App.jsx - Application Root Component
 * --------------------------------------
 * Manages the dark/light theme state.
 * Passes theme and toggleTheme to ChatPage.
 * Applies theme-based styles to the root container.
 */

import React, { useState } from "react";
import ChatPage from "./pages/ChatPage";

export default function App() {
  // Theme state: "dark" or "light" (default: dark)
  const [theme, setTheme] = useState("dark");

  // Toggle between dark and light mode
  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }

  // Apply theme colors to the root div
  const isDark = theme === "dark";

  return (
    <div
      style={{
        backgroundColor: isDark ? "#0f0f0f" : "#ffffff",
        color: isDark ? "#e5e5e5" : "#111111",
        minHeight: "100vh",
      }}
    >
      <ChatPage theme={theme} toggleTheme={toggleTheme} />
    </div>
  );
}
