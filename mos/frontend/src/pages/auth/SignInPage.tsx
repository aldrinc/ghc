import { SignIn } from "@clerk/clerk-react";
import type { CSSProperties } from "react";

const authShellStyle: CSSProperties = {
  minHeight: "100vh",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  background: "var(--bg)",
  fontFamily: "var(--font-sans)",
  padding: "2rem",
};

const authContentStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "2rem",
};

const wordmarkStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.625rem",
};

const wordmarkTextStyle: CSSProperties = {
  fontSize: "1.5rem",
  fontWeight: 600,
  color: "var(--text)",
  letterSpacing: "0",
};

const signInAppearance = {
  layout: {
    animations: false,
  },
  variables: {
    borderRadius: "5px",
  },
  elements: {
    rootBox: {
      minHeight: "390px",
    },
    cardBox: {
      transition: "none",
      animation: "none",
    },
    card: {
      transition: "none",
      animation: "none",
    },
  },
};

export function SignInPage() {
  return (
    <div style={authShellStyle}>
      <div style={authContentStyle}>
        <div style={wordmarkStyle}>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 16 16"
            width="36"
            height="36"
          >
            <rect width="16" height="16" rx="3" fill="#0a3b2d" />
            <path
              d="M4 12V4h2l2 3 2-3h2v8h-2V7.5L8 10 6 7.5V12z"
              fill="white"
            />
          </svg>
          <span style={wordmarkTextStyle}>mOS</span>
        </div>

        <SignIn
          routing="path"
          path="/sign-in"
          appearance={signInAppearance}
        />
      </div>
    </div>
  );
}
