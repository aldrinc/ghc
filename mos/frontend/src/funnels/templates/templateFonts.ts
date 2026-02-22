import { useEffect } from "react";

const TEMPLATE_FONT_STYLESHEET_ID = "mos-template-fonts";
const TEMPLATE_FONT_URL =
  "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Merriweather:wght@700;900&family=Poppins:wght@400;500;600;700;800;900&display=swap";

function ensurePreconnect(id: string, href: string, crossOrigin?: boolean) {
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "preconnect";
  link.href = href;
  if (crossOrigin) {
    link.crossOrigin = "anonymous";
  }
  document.head.appendChild(link);
}

function ensureTemplateFontsLoaded() {
  if (document.getElementById(TEMPLATE_FONT_STYLESHEET_ID)) return;

  ensurePreconnect("mos-fonts-googleapis-preconnect", "https://fonts.googleapis.com");
  ensurePreconnect("mos-fonts-gstatic-preconnect", "https://fonts.gstatic.com", true);

  const link = document.createElement("link");
  link.id = TEMPLATE_FONT_STYLESHEET_ID;
  link.rel = "stylesheet";
  link.href = TEMPLATE_FONT_URL;
  link.media = "print";
  link.onload = () => {
    link.media = "all";
    link.onload = null;
  };
  document.head.appendChild(link);
}

export function useTemplateFonts() {
  useEffect(() => {
    ensureTemplateFontsLoaded();
  }, []);
}
