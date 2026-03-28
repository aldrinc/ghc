export const MAX_UPLOADED_IMAGE_SIZE_BYTES = 20 * 1024 * 1024;
export const MAX_UPLOADED_VIDEO_SIZE_BYTES = 100 * 1024 * 1024;
export const MAX_UPLOADED_VIDEO_DURATION_SECONDS = 60;

export function formatAcceptedImageSizeLabel(): string {
  return "20MB";
}

export function formatAcceptedVideoSizeLabel(): string {
  return "100MB";
}

export function formatAcceptedVideoDurationLabel(): string {
  return "60 seconds";
}

export async function getVideoFileDurationSeconds(
  file: File
): Promise<number | null> {
  const objectUrl = URL.createObjectURL(file);

  try {
    return await new Promise<number | null>((resolve) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.src = objectUrl;

      const cleanup = () => {
        video.removeAttribute("src");
        video.load();
        URL.revokeObjectURL(objectUrl);
      };

      video.onloadedmetadata = () => {
        const duration = video.duration;
        cleanup();
        if (!Number.isFinite(duration) || duration <= 0) {
          resolve(null);
          return;
        }
        resolve(duration);
      };

      video.onerror = () => {
        cleanup();
        resolve(null);
      };
    });
  } catch {
    URL.revokeObjectURL(objectUrl);
    return null;
  }
}
