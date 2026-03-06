export const PAYMENT_ICON_KEYS = [
  "american_express",
  "apple_pay",
  "google_pay",
  "maestro",
  "mastercard",
  "paypal",
  "visa",
] as const;

export type PaymentIconKey = (typeof PAYMENT_ICON_KEYS)[number];

export type FooterLink = {
  label: string;
  href: string;
};
