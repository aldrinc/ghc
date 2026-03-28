import { useRef } from "react";
import { toast } from "react-hot-toast";
import { Cross2Icon } from "@radix-ui/react-icons";
import { LuPlus } from "react-icons/lu";
import DataUrlVideoPreview from "./DataUrlVideoPreview";
import {
  formatAcceptedVideoDurationLabel,
  formatAcceptedVideoSizeLabel,
  getVideoFileDurationSeconds,
  MAX_UPLOADED_VIDEO_DURATION_SECONDS,
  MAX_UPLOADED_VIDEO_SIZE_BYTES,
} from "../lib/video-limits";

const MAX_UPDATE_IMAGES = 5;
const VIDEO_EXTENSIONS = [".mp4", ".mov", ".webm"];

// Helper function to convert file to data URL
function fileToDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      if (result.startsWith("data:application/octet-stream") && file.type) {
        const correctedResult = result.replace(
          "data:application/octet-stream",
          `data:${file.type}`
        );
        resolve(correctedResult);
      } else {
        resolve(result);
      }
    };
    reader.onerror = (error) => reject(error);
    reader.readAsDataURL(file);
  });
}

function isVideoDataUrl(dataUrl: string): boolean {
  return dataUrl.startsWith("data:video/");
}

function isVideoFile(file: File): boolean {
  return (
    file.type.startsWith("video/") ||
    VIDEO_EXTENSIONS.some((extension) =>
      file.name.toLowerCase().endsWith(extension)
    )
  );
}

interface Props {
  updateImages: string[];
  setUpdateImages: (images: string[]) => void;
  updateVideos: string[];
  setUpdateVideos: (videos: string[]) => void;
}

export function UpdateImagePreview({
  updateImages,
  setUpdateImages,
  updateVideos,
  setUpdateVideos,
}: Props) {
  const mediaItems = [
    ...updateImages.map((image) => ({ type: "image" as const, dataUrl: image })),
    ...updateVideos.map((video) => ({ type: "video" as const, dataUrl: video })),
  ];

  const removeMedia = (type: "image" | "video", index: number) => {
    if (type === "image") {
      setUpdateImages(updateImages.filter((_, i) => i !== index));
      return;
    }
    setUpdateVideos(updateVideos.filter((_, i) => i !== index));
  };

  if (mediaItems.length === 0) return null;

  return (
    <div className="px-3 pt-3">
      <div className="flex flex-wrap gap-2 py-1">
        {mediaItems.map((item, index) => (
          <div key={index} className="relative flex-shrink-0 group overflow-visible">
            <div className="flex h-14 w-14 items-center justify-center rounded-lg border border-gray-200 bg-white p-1 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
              {item.type === "video" || isVideoDataUrl(item.dataUrl) ? (
                <DataUrlVideoPreview
                  dataUrl={item.dataUrl}
                  wrapperClassName="max-h-full max-w-full"
                  className="max-h-full max-w-full object-contain"
                  muted
                  playsInline
                />
              ) : (
                <img
                  src={item.dataUrl}
                  alt={`Reference ${index + 1}`}
                  className="max-h-full max-w-full object-contain"
                />
              )}
            </div>
            <button
              onClick={() =>
                removeMedia(
                  item.type,
                  item.type === "image"
                    ? updateImages.indexOf(item.dataUrl)
                    : updateVideos.indexOf(item.dataUrl)
                )
              }
              className="absolute -right-1 -top-1 z-10 flex h-5 w-5 items-center justify-center rounded-full border border-white bg-gray-900 text-white opacity-0 shadow transition-opacity group-hover:opacity-100 hover:bg-red-600 dark:border-zinc-900"
            >
              <Cross2Icon className="h-2.5 w-2.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function UpdateImageUpload({
  updateImages,
  setUpdateImages,
  updateVideos,
  setUpdateVideos,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const remaining = Math.max(0, MAX_UPDATE_IMAGES - updateImages.length);
  const isAtLimit = remaining === 0 && updateVideos.length === 0;


  const handleButtonClick = () => {
    if (isAtLimit) {
      toast.error(
        `You’ve reached the limit of ${MAX_UPDATE_IMAGES} reference images. Remove one to add another.`
      );
      return;
    }
    fileInputRef.current?.click();
  };

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      try {
        const fileList = Array.from(files);
        const incomingHasVideo = fileList.some(isVideoFile);
        if (incomingHasVideo) {
          if (fileList.length > 1 || updateImages.length > 0 || updateVideos.length > 0) {
            toast.error("Upload either one video or up to five reference images.");
            return;
          }

          const [video] = fileList;
          if (video.size > MAX_UPLOADED_VIDEO_SIZE_BYTES) {
            toast.error(
              `Videos must be ${formatAcceptedVideoSizeLabel()} or smaller.`
            );
            return;
          }

          const durationSeconds = await getVideoFileDurationSeconds(video);
          if (
            durationSeconds !== null &&
            durationSeconds > MAX_UPLOADED_VIDEO_DURATION_SECONDS
          ) {
            toast.error(
              `Videos must be ${formatAcceptedVideoDurationLabel()} or shorter.`
            );
            return;
          }

          const [videoDataUrl] = await Promise.all([fileToDataURL(video)]);
          setUpdateImages([]);
          setUpdateVideos([videoDataUrl]);
          e.target.value = "";
          return;
        }

        if (updateVideos.length > 0) {
          toast.error("Remove the video to add reference images.");
          return;
        }

        if (updateImages.length >= MAX_UPDATE_IMAGES) {
          toast.error(
            `You’ve reached the limit of ${MAX_UPDATE_IMAGES} reference images. Remove one to add another.`
          );
          return;
        }

        const remainingSlots = MAX_UPDATE_IMAGES - updateImages.length;
        let filesToAdd = fileList;
        if (filesToAdd.length > remainingSlots) {
          toast.error(
            `Only ${remainingSlots} more image${
              remainingSlots === 1 ? "" : "s"
            } will be added to stay within the ${MAX_UPDATE_IMAGES}-image limit.`
          );
          filesToAdd = filesToAdd.slice(0, remainingSlots);
        }

        const newImagePromises = filesToAdd.map((file) => fileToDataURL(file));
        const newImages = await Promise.all(newImagePromises);
        setUpdateImages([...updateImages, ...newImages]);
        e.target.value = "";
      } catch (error) {
        toast.error("Error reading image files");
        console.error("Error reading files:", error);
      }
    }
  };

  return (
    <div className="relative inline-block">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/png,image/jpeg,video/mp4,video/quicktime,video/webm"
        onChange={handleFileInputChange}
        className="hidden"
      />
      <button
        type="button"
        onClick={handleButtonClick}
        disabled={isAtLimit}
        className={`p-2 rounded-lg transition-colors ${
          isAtLimit
            ? "text-gray-300 dark:text-zinc-600 cursor-not-allowed"
            : "text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800"
        }`}
        title={
          isAtLimit
            ? `Limit reached (${MAX_UPDATE_IMAGES})`
            : "Add image or video"
        }
      >
        <LuPlus className="w-[18px] h-[18px]" />
      </button>
    </div>
  );
}

export default UpdateImageUpload;
