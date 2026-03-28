/**
 * App.jsx - Application Root Component
 * --------------------------------------
 * Manages the dark/light theme state.
 * Passes theme and toggleTheme to ChatPage.
 * Sets data-theme for CSS variable tokens.
 */

import React, { useState } from "react";
import ChatPage from "./pages/ChatPage";

export default function App() {
  const [theme, setTheme] = useState("dark");

  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }

  return (
    <div className="app-root" data-theme={theme}>
      <ChatPage theme={theme} toggleTheme={toggleTheme} />
    </div>
  );
}
