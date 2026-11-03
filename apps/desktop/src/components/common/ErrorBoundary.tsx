import React from 'react';

interface ErrorBoundaryProps {
  /** Short name of the guarded region, used in the visible message and console. */
  region: string;
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Keeps a failure in one screen region from unmounting the whole app, and makes
 * the failure visible instead of leaving a blank area.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error(`[${this.props.region}] render failure:`, error, info.componentStack);
  }

  render(): React.ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="region-error" role="alert">
        <strong>{this.props.region} failed to render.</strong>
        <span>{error.message}</span>
        <button type="button" onClick={() => this.setState({ error: null })}>
          Retry
        </button>
      </div>
    );
  }
}
