import { SignIn } from "@clerk/clerk-react";

export function SignInPage() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg)",
        fontFamily: "var(--font-sans)",
        padding: "2rem",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "2rem",
        }}
      >
        {/* Logo + wordmark */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
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
          <span
            style={{
              fontSize: "1.5rem",
              fontWeight: 600,
              color: "var(--text)",
              letterSpacing: "-0.02em",
            }}
          >
            mOS
          </span>
        </div>

        {/* Clerk sign-in widget */}
        <SignIn
          routing="path"
          path="/sign-in"
          appearance={{
            variables: {
              borderRadius: "5px",
            },
          }}
        />
      </div>
    </div>
  );
}
