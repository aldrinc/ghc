import { useId } from "react";

import { cn } from "@/lib/utils";

export type OnboardingIconName =
  | "business-new"
  | "business-existing"
  | "model-ecommerce"
  | "model-digital-product"
  | "model-service"
  | "model-saas"
  | "model-lead-generation"
  | "model-affiliate"
  | "model-marketplace"
  | "model-other"
  | "offer-product"
  | "offer-service"
  | "offer-software"
  | "offer-course"
  | "offer-lead-generation"
  | "offer-marketplace"
  | "offer-other"
  | "pricing-known"
  | "pricing-later"
  | "setup-workspace"
  | "setup-offer"
  | "setup-market"
  | "setup-docs"
  | "setup-memory";

export type OnboardingIconProps = {
  name: OnboardingIconName;
  className?: string;
  title?: string;
};

type Stops = [string, string, string];

const palettes: Record<string, Stops> = {
  blue: ["#77D8FF", "#248AC7", "#125174"],
  cyan: ["#8DF2DC", "#21B99D", "#0B7568"],
  green: ["#B4EA1A", "#62BD08", "#2F8500"],
  violet: ["#C8A5FF", "#815AE6", "#42318E"],
  pink: ["#FF9DD2", "#FF4B8B", "#C9115E"],
  orange: ["#FFD257", "#FF9C1F", "#E75F12"],
  red: ["#FF8F78", "#FF493E", "#D9122A"],
  slate: ["#D8E7EF", "#86A4B5", "#3D5868"],
};

function Gradient({ id, stops }: { id: string; stops: Stops }) {
  return (
    <linearGradient id={id} x1="7" y1="6" x2="25" y2="26" gradientUnits="userSpaceOnUse">
      <stop stopColor={stops[0]} />
      <stop offset=".55" stopColor={stops[1]} />
      <stop offset="1" stopColor={stops[2]} />
    </linearGradient>
  );
}

function iconBody(name: OnboardingIconName, rawId: string) {
  const gid = (suffix: string) => `${rawId}-${suffix}`;
  const primary = gid("primary");
  const secondary = gid("secondary");
  const tertiary = gid("tertiary");

  switch (name) {
    case "business-new":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.green} />
            <Gradient id={secondary} stops={palettes.blue} />
          </defs>
          <path d="M8.5 22.8c2.8-5.1 7.2-8.9 13.5-11.6 1.2-.5 2.5.7 2 1.9-2.5 6.5-6.3 11-11.6 13.5-1.3.6-2.6-.7-2-2 .3-.6.6-1.2 1-1.8H8.5Z" fill={`url(#${primary})`} />
          <path d="M19.2 8.2 23.8 6l-2.2 4.6" stroke="#B9F45E" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M14.2 18.4 9.4 13.6c-.8-.8-.4-2.2.7-2.4l4.6-.9 1.7 1.7-2.2 6.4Z" fill={`url(#${secondary})`} />
          <path d="M12.1 13.8 14 12" stroke="#DFFFFF" strokeWidth="1.6" strokeLinecap="round" />
        </>
      );
    case "business-existing":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.blue} />
            <Gradient id={secondary} stops={palettes.cyan} />
          </defs>
          <circle cx="16" cy="16" r="10" fill={`url(#${primary})`} />
          <path d="M6.8 16h18.4M16 6.2c2.5 2.5 3.8 5.8 3.8 9.8s-1.3 7.3-3.8 9.8M16 6.2c-2.5 2.5-3.8 5.8-3.8 9.8s1.3 7.3 3.8 9.8" stroke="#DFFFFF" strokeWidth="1.55" strokeLinecap="round" />
          <path d="M9.2 10.2c3.9 1.6 9.7 1.6 13.6 0M9.2 21.8c3.9-1.6 9.7-1.6 13.6 0" stroke="#AEE8FF" strokeWidth="1.55" strokeLinecap="round" />
          <circle cx="23.6" cy="8.4" r="2.3" fill={`url(#${secondary})`} />
        </>
      );
    case "model-ecommerce":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.orange} />
            <Gradient id={secondary} stops={palettes.pink} />
          </defs>
          <path d="M9.3 11.3h13.4l-1 13.3c-.1 1.1-1 2-2.1 2h-7.2c-1.1 0-2-.9-2.1-2l-1-13.3Z" fill={`url(#${primary})`} />
          <path d="M12.3 12.2V10a3.7 3.7 0 0 1 7.4 0v2.2" stroke="#7A3900" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M12.5 17.2h7M13.1 20.3h5.8" stroke="#FFF8DE" strokeWidth="1.7" strokeLinecap="round" />
          <circle cx="22.7" cy="9.1" r="2.5" fill={`url(#${secondary})`} />
        </>
      );
    case "model-digital-product":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.violet} />
            <Gradient id={secondary} stops={palettes.blue} />
          </defs>
          <path d="M8.6 9.2h14.8c1.2 0 2.1.9 2.1 2.1v11.4c0 1.2-.9 2.1-2.1 2.1H8.6c-1.2 0-2.1-.9-2.1-2.1V11.3c0-1.2.9-2.1 2.1-2.1Z" fill={`url(#${primary})`} />
          <path d="M10.2 13.1h11.6M10.2 16.4h7.3M10.2 19.7h9.5" stroke="#F3EAFF" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M12.8 6.7h6.4l1.8 2.6H11l1.8-2.6Z" fill={`url(#${secondary})`} />
        </>
      );
    case "model-service":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.cyan} />
            <Gradient id={secondary} stops={palettes.green} />
          </defs>
          <path d="M8 17.2c2.5-2.2 5.2-2.3 7.7-.2l.9.8c1 .9 2.4.9 3.4 0l3.4-3.1c1-.9 2.6-.2 2.6 1.2 0 .5-.2.9-.6 1.2l-6.7 6.1c-1.4 1.2-3.4 1.5-5.1.6l-5.6-3v-3.6Z" fill={`url(#${primary})`} />
          <path d="M8 13.4h6.4c1.1 0 2 .9 2 2v2.3" stroke="#DFFFFF" strokeWidth="1.7" strokeLinecap="round" />
          <path d="M19.2 8.1h4.4v4.4h-4.4z" rx="1.1" fill={`url(#${secondary})`} />
        </>
      );
    case "model-saas":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.blue} />
            <Gradient id={secondary} stops={palettes.violet} />
          </defs>
          <rect x="6.5" y="8.2" width="19" height="13.9" rx="3" fill={`url(#${primary})`} />
          <path d="M9.8 12.3h12.4M9.8 15.7h5.2M17.4 15.7h4.8" stroke="#DFFFFF" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M12.7 25.2h6.6M16 22.2v3" stroke="#125174" strokeWidth="1.9" strokeLinecap="round" />
          <circle cx="22.7" cy="10.1" r="2.4" fill={`url(#${secondary})`} />
        </>
      );
    case "model-lead-generation":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.red} />
            <Gradient id={secondary} stops={palettes.orange} />
          </defs>
          <path d="M7.7 17.5h4.7l8.6 5.1V9.4l-8.6 5.1H7.7v3Z" fill={`url(#${primary})`} />
          <path d="M12.4 14.5v6.1c0 1.3 1 2.3 2.3 2.3h1.5" stroke="#FFE8E3" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M23.1 12.1c1.2 1 1.9 2.4 1.9 3.9s-.7 2.9-1.9 3.9" stroke={`url(#${secondary})`} strokeWidth="2.1" strokeLinecap="round" />
        </>
      );
    case "model-affiliate":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.pink} />
            <Gradient id={secondary} stops={palettes.green} />
          </defs>
          <path d="M10.4 19.9c-2.2-2.2-2.2-5.8 0-8l1.2-1.2c2.2-2.2 5.8-2.2 8 0" stroke={`url(#${primary})`} strokeWidth="3.2" strokeLinecap="round" />
          <path d="M21.6 12.1c2.2 2.2 2.2 5.8 0 8l-1.2 1.2c-2.2 2.2-5.8 2.2-8 0" stroke={`url(#${secondary})`} strokeWidth="3.2" strokeLinecap="round" />
          <path d="M13.1 18.9 18.9 13.1" stroke="#FFF4FB" strokeWidth="1.9" strokeLinecap="round" />
          <circle cx="23.2" cy="8.8" r="2.4" fill={`url(#${secondary})`} />
        </>
      );
    case "model-marketplace":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.cyan} />
            <Gradient id={secondary} stops={palettes.orange} />
            <Gradient id={tertiary} stops={palettes.pink} />
          </defs>
          <circle cx="10" cy="11" r="3.6" fill={`url(#${primary})`} />
          <circle cx="22" cy="11" r="3.6" fill={`url(#${secondary})`} />
          <circle cx="16" cy="23" r="3.6" fill={`url(#${tertiary})`} opacity=".9" />
          <path d="M12.9 12.8 15 19.7M19.1 12.8 17 19.7M13.4 11h5.2" stroke="#E8FFFA" strokeWidth="1.6" strokeLinecap="round" />
        </>
      );
    case "model-other":
    case "offer-other":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.slate} />
            <Gradient id={secondary} stops={palettes.violet} />
          </defs>
          <path d="M9.1 10.3 16 6.5l6.9 3.8v7.9L16 22l-6.9-3.8v-7.9Z" fill={`url(#${primary})`} />
          <path d="M16 14.2v7.8M9.8 10.7l6.2 3.5 6.2-3.5" stroke="#F8FAFB" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="23.4" cy="23" r="2.6" fill={`url(#${secondary})`} />
        </>
      );
    case "offer-product":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.green} />
            <Gradient id={secondary} stops={palettes.orange} />
          </defs>
          <path d="M8.4 12.2 16 7.9l7.6 4.3v8.6L16 25.1l-7.6-4.3v-8.6Z" fill={`url(#${primary})`} />
          <path d="M16 16.5v8M9.2 12.7l6.8 3.8 6.8-3.8" stroke="#E7FFD1" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M12.6 9.8 20 14" stroke={`url(#${secondary})`} strokeWidth="1.8" strokeLinecap="round" />
        </>
      );
    case "offer-service":
      return iconBody("model-service", rawId);
    case "offer-software":
      return iconBody("model-saas", rawId);
    case "offer-course":
      return iconBody("model-digital-product", rawId);
    case "offer-lead-generation":
      return iconBody("model-lead-generation", rawId);
    case "offer-marketplace":
      return iconBody("model-marketplace", rawId);
    case "pricing-known":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.orange} />
            <Gradient id={secondary} stops={palettes.green} />
          </defs>
          <circle cx="16" cy="16" r="9.8" fill={`url(#${primary})`} />
          <path d="M16 10.2v11.6M19.1 12.6c-.8-.9-2.1-1.4-3.3-1.1-1.3.3-2.1 1.1-2.1 2.1 0 1.2 1.2 1.8 2.7 2.1 1.7.4 3 1 3 2.4 0 1.2-1 2.1-2.4 2.4-1.5.3-3-.1-4-1.2" stroke="#FFF8DE" strokeWidth="1.7" strokeLinecap="round" />
          <circle cx="23.2" cy="8.7" r="2.5" fill={`url(#${secondary})`} />
        </>
      );
    case "pricing-later":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.blue} />
            <Gradient id={secondary} stops={palettes.violet} />
          </defs>
          <circle cx="16" cy="16" r="9.7" fill={`url(#${primary})`} />
          <path d="M16 10.2v6l4.1 2.4" stroke="#DFFFFF" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M9.2 9.6c2.4-2 5.9-2.6 8.9-1.3" stroke="#AEE8FF" strokeWidth="1.6" strokeLinecap="round" opacity=".85" />
          <circle cx="23.2" cy="23.2" r="2.5" fill={`url(#${secondary})`} />
        </>
      );
    case "setup-workspace":
      return iconBody("business-new", rawId);
    case "setup-offer":
      return iconBody("offer-product", rawId);
    case "setup-market":
      return iconBody("business-existing", rawId);
    case "setup-docs":
      return iconBody("model-digital-product", rawId);
    case "setup-memory":
      return (
        <>
          <defs>
            <Gradient id={primary} stops={palettes.violet} />
            <Gradient id={secondary} stops={palettes.cyan} />
          </defs>
          <rect x="8" y="7" width="16" height="18" rx="4" fill={`url(#${primary})`} />
          <path d="M12 11.5h8M12 15.5h8M12 19.5h5.5" stroke="#F3EAFF" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M7.1 12.1h3M7.1 16h3M7.1 19.9h3M21.9 12.1h3M21.9 16h3M21.9 19.9h3" stroke={`url(#${secondary})`} strokeWidth="1.7" strokeLinecap="round" />
        </>
      );
  }
}

export function OnboardingIcon({ name, className, title }: OnboardingIconProps) {
  const rawId = useId().replace(/[^a-zA-Z0-9_-]/g, "");

  return (
    <svg
      className={cn("mos-onboarding-icon", className)}
      data-onboarding-icon={name}
      xmlns="http://www.w3.org/2000/svg"
      width="32"
      height="32"
      viewBox="0 0 32 32"
      fill="none"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
    >
      {title ? <title>{title}</title> : null}
      <rect width="32" height="32" rx="9" fill="#F8FAFB" />
      {iconBody(name, rawId)}
    </svg>
  );
}
