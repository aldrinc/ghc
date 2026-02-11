import { Component, type ReactNode } from "react";

type Props = {
  blockType: string;
  blockId?: string;
  resetKey?: string;
  children: ReactNode;
};

type State = {
  error: Error | null;
};

export class BlockErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // Keep a clear marker in the console so broken blocks can be found quickly.
    // eslint-disable-next-line no-console
    console.error(`[BlockErrorBoundary] ${this.props.blockType}${this.props.blockId ? `#${this.props.blockId}` : ""}`, error);
  }

  componentDidUpdate(prevProps: Props) {
    // Allow blocks to recover once the user edits fields in the Puck sidebar.
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      // eslint-disable-next-line react/no-did-update-set-state
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;

    const { blockType, blockId } = this.props;
    const message = this.state.error.message || "Unknown render error";
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900">
        <div className="font-semibold">Block failed to render</div>
        <div className="mt-1 font-mono text-xs">
          {blockType}
          {blockId ? `#${blockId}` : ""}
        </div>
        <div className="mt-2 whitespace-pre-wrap">{message}</div>
        <div className="mt-3 text-xs text-red-800">
          Fix this block&apos;s `config` / `configJson` fields, or regenerate the page draft.
        </div>
      </div>
    );
  }
}
