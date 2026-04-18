import type { CSSProperties, ReactNode } from "react";

const shellStyle: CSSProperties = {
  minHeight: "100vh",
  padding: "24px",
  background: "#fffaf4",
  color: "rgba(45, 41, 38, 0.76)",
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  fontSize: "14px",
  lineHeight: 1.5,
};

const shellInnerStyle: CSSProperties = {
  margin: "0 auto",
  width: "100%",
  maxWidth: "640px",
};

type PublicFunnelShellMessageProps = {
  children: ReactNode;
  constrain?: boolean;
};

export function PublicFunnelShellMessage({
  children,
  constrain = false,
}: PublicFunnelShellMessageProps) {
  if (!constrain) {
    return <div style={shellStyle}>{children}</div>;
  }

  return (
    <div style={shellStyle}>
      <div style={shellInnerStyle}>{children}</div>
    </div>
  );
}
