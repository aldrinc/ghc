import { useEffect, useRef, useState } from "react";
import { Button } from "../ui/button";
import { ScreenRecorderState } from "../../types";
import { blobToBase64DataUrl } from "./utils";
import fixWebmDuration from "webm-duration-fix";
import toast from "react-hot-toast";
import OutputSettingsSection from "../settings/OutputSettingsSection";
import { Stack } from "../../lib/stacks";
import {
  formatAcceptedVideoDurationLabel,
  formatAcceptedVideoSizeLabel,
  MAX_UPLOADED_VIDEO_DURATION_SECONDS,
  MAX_UPLOADED_VIDEO_SIZE_BYTES,
} from "../../lib/video-limits";

interface Props {
  screenRecorderState: ScreenRecorderState;
  setScreenRecorderState: (state: ScreenRecorderState) => void;
  generateCode: (
    referenceImages: string[],
    inputMode: "image" | "video"
  ) => void;
  stack: Stack;
  setStack: (stack: Stack) => void;
}

function ScreenRecorder({
  screenRecorderState,
  setScreenRecorderState,
  generateCode,
  stack,
  setStack,
}: Props) {
  const [screenRecordingDataUrl, setScreenRecordingDataUrl] = useState<
    string | null
  >(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (recordingTimeoutRef.current !== null) {
        window.clearTimeout(recordingTimeoutRef.current);
      }
    };
  }, []);

  const startScreenRecording = async () => {
    try {
      // Get the screen recording stream
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: { echoCancellation: true },
      });
      mediaStreamRef.current = stream;

      // TODO: Test across different browsers
      // Create the media recorder
      const options = { mimeType: "video/webm" };
      const mediaRecorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = mediaRecorder;

      const chunks: BlobPart[] = [];

      // Accumalate chunks as data is available
      mediaRecorder.ondataavailable = (e: BlobEvent) => chunks.push(e.data);

      // When media recorder is stopped, create a data URL
      mediaRecorder.onstop = async () => {
        if (recordingTimeoutRef.current !== null) {
          window.clearTimeout(recordingTimeoutRef.current);
          recordingTimeoutRef.current = null;
        }

        // TODO: Do I need to fix duration if it's not a webm?
        const completeBlob = await fixWebmDuration(
          new Blob(chunks, {
            type: options.mimeType,
          })
        );

        if (completeBlob.size > MAX_UPLOADED_VIDEO_SIZE_BYTES) {
          toast.error(
            `Recordings must stay under ${formatAcceptedVideoSizeLabel()}.`
          );
          setScreenRecordingDataUrl(null);
          setScreenRecorderState(ScreenRecorderState.INITIAL);
          return;
        }

        const dataUrl = await blobToBase64DataUrl(completeBlob);

        setScreenRecordingDataUrl(dataUrl);
        setScreenRecorderState(ScreenRecorderState.FINISHED);
      };

      // Start recording
      mediaRecorder.start();
      recordingTimeoutRef.current = window.setTimeout(() => {
        toast.error(
          `Screen recordings are limited to ${formatAcceptedVideoDurationLabel()}. Stopping now.`
        );
        stopScreenRecording();
      }, MAX_UPLOADED_VIDEO_DURATION_SECONDS * 1000);
      setScreenRecorderState(ScreenRecorderState.RECORDING);
    } catch (error) {
      toast.error("Could not start screen recording");
      throw error;
    }
  };

  const stopScreenRecording = () => {
    if (recordingTimeoutRef.current !== null) {
      window.clearTimeout(recordingTimeoutRef.current);
      recordingTimeoutRef.current = null;
    }

    // Stop the recorder
    const activeRecorder = mediaRecorderRef.current;
    if (activeRecorder) {
      activeRecorder.stop();
      mediaRecorderRef.current = null;
    }

    // Stop the screen sharing stream
    const activeStream = mediaStreamRef.current;
    if (activeStream) {
      activeStream.getTracks().forEach((track) => {
        track.stop();
      });
      mediaStreamRef.current = null;
    }
  };

  const kickoffGeneration = () => {
    if (screenRecordingDataUrl) {
      generateCode([screenRecordingDataUrl], "video");
    } else {
      toast.error("Screen recording does not exist. Please try again.");
      throw new Error("No screen recording data url");
    }
  };

  return (
    <div className="flex items-center justify-center my-3">
      {screenRecorderState === ScreenRecorderState.INITIAL && (
        <Button onClick={startScreenRecording}>Record Screen</Button>
      )}

      {screenRecorderState === ScreenRecorderState.RECORDING && (
        <div className="flex items-center flex-col gap-y-4">
          <div className="flex items-center mr-2 text-xl gap-x-1">
            <span className="block h-10 w-10 bg-red-600 rounded-full mr-1 animate-pulse"></span>
            <span>Recording...</span>
          </div>
          <Button onClick={stopScreenRecording}>Finish Recording</Button>
        </div>
      )}

      {screenRecorderState === ScreenRecorderState.FINISHED && (
        <div className="flex items-center flex-col gap-y-4 w-full max-w-md">
          <div className="flex items-center mr-2 text-xl gap-x-1">
            <span>Screen Recording Captured.</span>
          </div>
          {screenRecordingDataUrl && (
            <video
              muted
              autoPlay
              loop
              className="w-full border border-gray-200 rounded-md"
              src={screenRecordingDataUrl}
            />
          )}
          <div className="w-full">
            <OutputSettingsSection
              stack={stack}
              setStack={setStack}
            />
          </div>
          <div className="flex gap-x-2 w-full">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() =>
                setScreenRecorderState(ScreenRecorderState.INITIAL)
              }
            >
              Re-record
            </Button>
            <Button className="flex-1" onClick={kickoffGeneration}>Generate</Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ScreenRecorder;
