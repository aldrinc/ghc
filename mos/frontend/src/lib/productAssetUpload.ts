export const SUPPORTED_PRODUCT_IMAGE_MIME_TYPES = [
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
  "image/gif",
] as const;

export const SUPPORTED_PRODUCT_VIDEO_MIME_TYPES = [
  "video/mp4",
  "video/webm",
  "video/quicktime",
] as const;

export const SUPPORTED_PRODUCT_DOCUMENT_MIME_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
] as const;

export const SUPPORTED_PRODUCT_IMAGE_ACCEPT = SUPPORTED_PRODUCT_IMAGE_MIME_TYPES.join(",");
export const SUPPORTED_PRODUCT_ASSET_ACCEPT = [
  ...SUPPORTED_PRODUCT_IMAGE_MIME_TYPES,
  ...SUPPORTED_PRODUCT_VIDEO_MIME_TYPES,
  ...SUPPORTED_PRODUCT_DOCUMENT_MIME_TYPES,
].join(",");

export const SUPPORTED_PRODUCT_IMAGE_LABEL = "PNG, JPEG, WebP, or GIF";
export const SUPPORTED_PRODUCT_ASSET_LABEL =
  "PNG, JPEG, WebP, GIF, MP4, WebM, MOV, PDF, DOC, or DOCX";

const supportedProductImageMimeTypeSet = new Set<string>(SUPPORTED_PRODUCT_IMAGE_MIME_TYPES);
const supportedProductAssetMimeTypeSet = new Set<string>([
  ...SUPPORTED_PRODUCT_IMAGE_MIME_TYPES,
  ...SUPPORTED_PRODUCT_VIDEO_MIME_TYPES,
  ...SUPPORTED_PRODUCT_DOCUMENT_MIME_TYPES,
]);

export function isSupportedProductImageFile(file: File): boolean {
  return supportedProductImageMimeTypeSet.has((file.type || "").trim().toLowerCase());
}

export function areSupportedProductAssetFiles(files: File[]): boolean {
  return files.every((file) => supportedProductAssetMimeTypeSet.has((file.type || "").trim().toLowerCase()));
}
