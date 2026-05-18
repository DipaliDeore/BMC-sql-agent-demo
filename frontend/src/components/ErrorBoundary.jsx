/**
 * ErrorBoundary.jsx — catch render errors in the chat UI and offer recovery.
 */

import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-panel" role="alert">
          <h2>Something went wrong</h2>
          <p className="error-boundary-detail">
            {this.state.error?.message ||
              "The chat UI hit an unexpected error."}
          </p>
          <div className="error-boundary-actions">
            <button
              type="button"
              className="ui-btn-primary"
              onClick={this.handleRetry}
            >
              Try again
            </button>
            <button
              type="button"
              className="ui-btn-secondary"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
