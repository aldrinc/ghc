const channelNames: Record<string, string> = {
  META_ADS_LIBRARY: "Meta",
  TIKTOK_CREATIVE_CENTER: "TikTok",
  GOOGLE_ADS_TRANSPARENCY: "Google",
};

function titleCase(input: string) {
  return input
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

export function channelDisplayName(channel?: string | null): string {
  if (!channel) return "Unknown";
  const normalized = channel.toString().trim();
  if (!normalized) return "Unknown";
  if (channelNames[normalized]) return channelNames[normalized];
  const spaced = normalized.replace(/_/g, " ");
  return titleCase(spaced);
}
