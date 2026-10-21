import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col h-full bg-surface-container-low/95 backdrop-blur-xl border-l border-starlight-white/10 p-6 items-center justify-center text-center">
          <div className="w-12 h-12 rounded-full bg-error/10 border border-error/20 flex items-center justify-center text-error mb-4">
            <span className="material-symbols-outlined text-2xl">warning</span>
          </div>
          <h3 className="font-headline-sm text-base text-starlight-white font-semibold mb-1">
            {this.props.fallbackTitle || 'Something went wrong'}
          </h3>
          <p className="font-body-md text-xs text-on-surface-variant/70 max-w-xs mb-4">
            An error occurred while rendering this panel.
          </p>
          {this.state.error && (
            <pre className="text-[10px] text-error/80 bg-surface-container-lowest/80 p-2.5 rounded border border-error/20 max-w-xs overflow-x-auto text-left mb-4 font-mono">
              {this.state.error.message}
            </pre>
          )}
          <button
            onClick={this.handleRetry}
            className="px-4 py-1.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-xs font-label-sm text-starlight-white border border-starlight-white/10 transition-colors uppercase tracking-wider"
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
