export type AssetBriefType = "image" | "video";

export const ASSET_BRIEF_TYPE_OPTIONS: Array<{ value: AssetBriefType; label: string }> = [
  { value: "image", label: "Image" },
  { value: "video", label: "Video" },
];

export const DEFAULT_ASSET_BRIEF_TYPES: AssetBriefType[] = ["image"];
