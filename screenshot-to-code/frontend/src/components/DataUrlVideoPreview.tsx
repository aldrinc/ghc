import {
  forwardRef,
  type SyntheticEvent,
  type VideoHTMLAttributes,
  useEffect,
  useMemo,
  useState,
} from "react";

interface DataUrlVideoPreviewProps
  extends Omit<VideoHTMLAttributes<HTMLVideoElement>, "src"> {
  dataUrl: string;
  wrapperClassName?: string;
  showCompatibilityNote?: boolean;
  noteClassName?: string;
}

function extractMimeType(dataUrl: string): string {
  if (!dataUrl.startsWith("data:")) {
    return "";
  }

  const mimeType = dataUrl.slice(5).split(";")[0];
  return mimeType || "";
}

const DataUrlVideoPreview = forwardRef<
  HTMLVideoElement,
  DataUrlVideoPreviewProps
>(function DataUrlVideoPreview(
  {
    dataUrl,
    wrapperClassName,
    showCompatibilityNote = false,
    noteClassName,
    onLoadedMetadata,
    onError,
    ...videoProps
  },
  ref
) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [previewWarning, setPreviewWarning] = useState<string | null>(null);
  const mimeType = useMemo(() => extractMimeType(dataUrl), [dataUrl]);

  useEffect(() => {
    let isCancelled = false;
    let nextObjectUrl: string | null = null;

    async function buildObjectUrl() {
      if (!dataUrl.startsWith("data:")) {
        setObjectUrl(null);
        return;
      }

      try {
        const response = await fetch(dataUrl);
        const blob = await response.blob();
        if (isCancelled) {
          return;
        }
        nextObjectUrl = URL.createObjectURL(blob);
        setObjectUrl(nextObjectUrl);
      } catch {
        if (!isCancelled) {
          setObjectUrl(null);
        }
      }
    }

    buildObjectUrl();

    return () => {
      isCancelled = true;
      if (nextObjectUrl) {
        URL.revokeObjectURL(nextObjectUrl);
      }
    };
  }, [dataUrl]);

  const handleLoadedMetadata = (event: SyntheticEvent<HTMLVideoElement>) => {
    onLoadedMetadata?.(event);

    if (!showCompatibilityNote) {
      return;
    }

    const duration = event.currentTarget.duration;
    if (!Number.isFinite(duration) || duration <= 0) {
      setPreviewWarning(
        "This browser cannot read the local video duration, but the upload is still attached and will be normalized when sent."
      );
      return;
    }

    setPreviewWarning(null);
  };

  const handleError = (event: SyntheticEvent<HTMLVideoElement>) => {
    onError?.(event);

    if (!showCompatibilityNote) {
      return;
    }

    if (mimeType === "video/quicktime") {
      setPreviewWarning(
        "QuickTime preview can fail in this browser, but the upload is still attached and will be normalized when sent."
      );
      return;
    }

    setPreviewWarning(
      "Preview is unavailable in this browser, but the upload is still attached and will be sent."
    );
  };

  return (
    <div className={wrapperClassName}>
      <video
        {...videoProps}
        ref={ref}
        src={objectUrl ?? dataUrl}
        onLoadedMetadata={handleLoadedMetadata}
        onError={handleError}
      />
      {showCompatibilityNote && previewWarning ? (
        <p
          className={
            noteClassName ??
            "mt-1 text-xs text-amber-700 dark:text-amber-300"
          }
        >
          {previewWarning}
        </p>
      ) : null}
    </div>
  );
});

export default DataUrlVideoPreview;
