import type { CompanySwipeAsset } from "@/types/swipes";
import type { LibraryItem, MediaAsset } from "@/types/library";

function randomId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `lib-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function unixSecondsToIso(sec?: number | null) {
  if (!sec) return undefined;
  return new Date(sec * 1000).toISOString();
}

const apiBaseUrl =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL) || undefined;

function toAbsoluteUrl(url?: string | null): string | undefined {
  if (!url) return undefined;
  if (/^(https?:)?\/\//i.test(url) || url.startsWith("data:") || url.startsWith("blob:")) return url;
  const base =
    apiBaseUrl?.replace(/\/$/, "") ||
    (typeof window !== "undefined" ? window.location.origin.replace(/\/$/, "") : "");
  if (!base) return url;
  return `${base}${url.startsWith("/") ? "" : "/"}${url}`;
}

function guessAssetType(input: any): MediaAsset["type"] {
  const assetType = (input?.asset_type || input?.type || "").toString().toLowerCase();
  const mime = (input?.mime_type || input?.mimeType || "").toString().toLowerCase();
  const url = (
    input?.media_url ||
    input?.preview_url ||
    input?.stored_url ||
    input?.source_url ||
    input?.url ||
    ""
  )
    .toString()
    .toLowerCase();
  if (assetType.includes("video") || mime.startsWith("video/")) return "video";
  if (assetType.includes("image") || mime.startsWith("image/")) return "image";
  if (url.endsWith(".mp4") || url.includes("video")) return "video";
  return "image";
}

export function mapMediaAssets(rawAssets: any[] | undefined | null): MediaAsset[] {
  if (!rawAssets || !Array.isArray(rawAssets)) return [];
  const normalizeRole = (value: any): string => (value ?? "").toString().trim().toLowerCase();
  const isThumbnailRole = (asset: any): boolean => normalizeRole(asset?.role) === "thumbnail";

  const thumbnailAssets = rawAssets.filter(isThumbnailRole);
  const nonThumbnailAssets = rawAssets.filter((asset) => !isThumbnailRole(asset));

  // If we only have thumbnails, surface them rather than showing an empty media state.
  const assetsToRender = nonThumbnailAssets.length ? nonThumbnailAssets : thumbnailAssets;

  const toCandidateUrl = (asset: any): string | undefined =>
    toAbsoluteUrl(
      asset?.preview_url ||
        asset?.thumbnail_url ||
        asset?.stored_url ||
        asset?.source_url ||
        asset?.url,
    );

  const thumbnailUrlCandidates = Array.from(
    new Set(thumbnailAssets.map(toCandidateUrl).filter(Boolean) as string[]),
  );

  const videoCount = assetsToRender.reduce(
    (acc, asset) => acc + (guessAssetType(asset) === "video" ? 1 : 0),
    0,
  );
  const videoPosterFallback = videoCount === 1 ? thumbnailUrlCandidates[0] : undefined;

  const isProbablyRenderableImage = (url: string | undefined): url is string => {
    if (!url) return false;
    if (url.startsWith("data:image/")) return true;
    // Prefer parsing the path extension so querystrings (e.g. presigned URLs) don't confuse detection.
    try {
      const parsed = new URL(url, "http://localhost");
      const path = parsed.pathname.toLowerCase();
      if (/\.(png|jpe?g|gif|webp|avif|bmp|svg)$/.test(path)) return true;
      if (/\.(mp4|mov|m4v|webm|mkv|m3u8|ts)$/.test(path)) return false;
    } catch {
      // Fall back to heuristics below.
    }
    // Best-effort: avoid using video URLs as <img> src (can render as blank tiles).
    return guessAssetType({ url }) === "image";
  };

  return assetsToRender
    .map((asset) => {
      const status = (asset?.mirror_status || asset?.status || "").toString().toLowerCase();
      const normalizedStatus = ["pending", "succeeded", "failed", "partial"].includes(status)
        ? (status as MediaAsset["status"])
        : undefined;

      const type = guessAssetType(asset);
      const fullUrl = toAbsoluteUrl(asset?.media_url || asset?.stored_url || asset?.source_url || asset?.url);
      const previewUrl = toCandidateUrl(asset);

      if (!previewUrl && !fullUrl && normalizedStatus !== "pending") return null;

      if (type === "video") {
        // Prefer mirrored previews over provider thumbnails (provider URLs can expire).
        const posterUrl = [
          toAbsoluteUrl(asset?.preview_url),
          videoPosterFallback,
          toAbsoluteUrl(asset?.thumbnail_url),
          toAbsoluteUrl(asset?.preview_image_url),
          toAbsoluteUrl(asset?.poster_url),
        ].find(isProbablyRenderableImage);
        return {
          type,
          url: fullUrl || previewUrl || "",
          fullUrl: fullUrl || undefined,
          thumbUrl: posterUrl,
          posterUrl,
          status: normalizedStatus,
        } satisfies MediaAsset;
      }

      const url = previewUrl || fullUrl || "";
      return {
        type,
        url,
        thumbUrl: url,
        fullUrl: fullUrl || undefined,
        status: normalizedStatus,
      } satisfies MediaAsset;
    })
    .filter(Boolean) as MediaAsset[];
}

function mapStatus(status?: string | null): LibraryItem["status"] {
  if (!status) return "unknown";
  const s = status.toString().toLowerCase();
  if (s.includes("active")) return "active";
  if (s.includes("inactive") || s.includes("paused")) return "inactive";
  return "unknown";
}

export function normalizeFacebookAdToLibraryItem(raw: any): LibraryItem {
  const snapshot = raw?.snapshot ?? {};

  const cardAssets: MediaAsset[] = (snapshot.cards ?? [])
    .map((card: any) => {
      const videoUrl = card.video_hd_url || card.video_sd_url || card.watermarked_video_hd_url || card.watermarked_video_sd_url;
      const imageUrl = card.resized_image_url || card.original_image_url || card.watermarked_resized_image_url;
      const thumb = card.video_preview_image_url || imageUrl;
      if (videoUrl) {
        return { type: "video" as const, url: videoUrl, thumbUrl: thumb };
      }
      if (imageUrl) {
        return { type: "image" as const, url: imageUrl, thumbUrl: thumb, alt: card.body || card.title };
      }
      return null;
    })
    .filter(Boolean) as MediaAsset[];

  const imageAssets: MediaAsset[] = (snapshot.images ?? [])
    .map((img: any) => {
      const url = img.original_image_url || img.resized_image_url;
      if (!url) return null;
      return {
        type: "image" as const,
        url,
        thumbUrl: img.resized_image_url || img.original_image_url,
        alt: snapshot.title || snapshot.page_name || raw.page_name || "Ad image",
      };
    })
    .filter(Boolean) as MediaAsset[];

  const videoAssets: MediaAsset[] = (snapshot.videos ?? [])
    .map((v: any) => {
      const url = v.video_hd_url || v.video_sd_url || v.url || v.src || v.playable_url;
      if (!url) return null;
      return {
        type: "video" as const,
        url,
        thumbUrl: v.thumbnail_url || v.preview_image_url,
      };
    })
    .filter(Boolean) as MediaAsset[];

  const mediaAssets = mapMediaAssets(raw?.media_assets);
  const media =
    videoAssets.length > 0
      ? videoAssets
      : imageAssets.length > 0
      ? imageAssets
      : cardAssets.length > 0
      ? cardAssets
      : mediaAssets;

  return {
    id: raw.ad_archive_id || raw.ad_id || raw.collation_id || randomId(),
    kind: "ad",
    brandName:
      snapshot.page_name ||
      raw.page_name ||
      raw?.advertiser?.ad_library_page_info?.page_info?.page_name ||
      "Unknown brand",
    brandAvatarUrl:
      snapshot.page_profile_picture_url ||
      raw?.advertiser?.ad_library_page_info?.page_info?.profile_photo,
    platform: raw.publisher_platform
      ? Array.isArray(raw.publisher_platform)
        ? raw.publisher_platform
        : [raw.publisher_platform]
      : [],
    status: raw.is_active === true ? "active" : raw.is_active === false ? "inactive" : mapStatus(raw.ad_status),
    startAt: unixSecondsToIso(raw.start_date),
    endAt: unixSecondsToIso(raw.end_date),
    capturedAt: unixSecondsToIso(raw.captured_at),
    headline: snapshot.title,
    body: snapshot.body?.text || snapshot.body,
    ctaText: snapshot.cta_text,
    destinationUrl: snapshot.link_url,
    media,
    raw,
  };
}

function parseMaybeJson(raw: any): any {
  if (!raw) return null;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return raw;
}

export function normalizeBreakdownAdToLibraryItem(ad: any): LibraryItem {
  const rawJson = parseMaybeJson(ad?.raw_json);
  // If raw_json carries the full snapshot, reuse the Facebook normalizer.
  if (rawJson?.snapshot) {
    return { ...normalizeFacebookAdToLibraryItem(rawJson), raw: ad };
  }

  const thesis = ad?.breakdown?.algorithmic_thesis;
  return {
    id: ad?.ad_id || ad?.external_ad_id || randomId(),
    kind: "ad",
    brandName: ad?.brand_name || "Unknown brand",
    platform: ad?.channel ? [ad.channel] : [],
    status: mapStatus(ad?.ad_status),
    startAt: ad?.start_date,
    endAt: ad?.end_date,
    destinationUrl: ad?.landing_url || ad?.destination_domain,
    headline: ad?.headline,
    body: ad?.primary_text || thesis,
    ctaText: ad?.cta_text || ad?.cta_type,
    hookScore: ad?.breakdown?.hook_score,
    funnelStage: undefined,
    media: mapMediaAssets(ad?.media_assets),
    raw: ad,
  };
}

function mapSwipePlatforms(swipe: CompanySwipeAsset, snapshot: any): string[] {
  const set = new Set<string>();
  if (swipe.platforms) {
    swipe.platforms
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean)
      .forEach((p) => set.add(p));
  }
  const publisher = snapshot?.publisher_platform || snapshot?.publishing_platform;
  if (Array.isArray(publisher)) {
    publisher.filter(Boolean).forEach((p) => set.add(p));
  } else if (publisher) {
    set.add(publisher);
  }
  return Array.from(set);
}

function mapSwipeImages(snapshot: any, fallbackAlt?: string): MediaAsset[] {
  const images = Array.isArray(snapshot?.images) ? snapshot.images : [];
  const cards = Array.isArray(snapshot?.cards) ? snapshot.cards : [];
  return [...images, ...cards]
    .map((img: any) => {
      if (!img) return null;
      const hasVideo =
        img.video_hd_url || img.video_sd_url || img.url?.toString().toLowerCase().includes("video");
      if (hasVideo) return null;
      const resized =
        img.resized_image_url || img.thumbnail_url || img.watermarked_resized_image_url || img.preview_image_url;
      const original = img.original_image_url || img.watermarked_original_image_url;
      const url = resized || original;
      if (!url) return null;
      return {
        type: "image" as const,
        url,
        thumbUrl: resized || original,
        fullUrl: original || resized,
        alt: img.body || img.title || fallbackAlt,
      };
    })
    .filter(Boolean) as MediaAsset[];
}

function mapSwipeVideos(snapshot: any, posterFallback?: string): MediaAsset[] {
  const videos = Array.isArray(snapshot?.videos) ? snapshot.videos : [];
  const cards = Array.isArray(snapshot?.cards) ? snapshot.cards : [];
  return [...videos, ...cards]
    .map((v: any) => {
      if (!v) return null;
      const url = v.video_hd_url || v.video_sd_url || v.url || v.src || v.playable_url;
      if (!url) return null;
      const thumb =
        v.thumbnail_url ||
        v.preview_image_url ||
        v.video_preview_image_url ||
        v.watermarked_preview_image_url ||
        posterFallback;
      return { type: "video" as const, url, thumbUrl: thumb, posterUrl: thumb, fullUrl: url };
    })
    .filter(Boolean) as MediaAsset[];
}

function mapSwipeStoredMedia(mediaList: CompanySwipeAsset["media"], fallbackAlt?: string): MediaAsset[] {
  if (!mediaList || !Array.isArray(mediaList)) return [];
  return mediaList
    .map((m: any) => {
      if (!m) return null;
      const url = m.thumbnail_url || m.url || m.download_url || m.path || m.thumbnail_path;
      const fullUrl = m.url || m.download_url || url;
      if (!url) return null;
      const type = guessAssetType({ asset_type: m.type, mime_type: m.mime_type, url: fullUrl });
      const thumb = m.thumbnail_url || m.thumbnail_path || url;
      return {
        type,
        url: thumb || fullUrl,
        thumbUrl: thumb || fullUrl,
        fullUrl: fullUrl || thumb,
        posterUrl: type === "video" ? thumb || fullUrl : undefined,
        alt: fallbackAlt,
      } satisfies MediaAsset;
    })
    .filter(Boolean) as MediaAsset[];
}

export function normalizeSwipeToLibraryItem(swipe: CompanySwipeAsset): LibraryItem {
  const snapshot = (swipe as any)?.snapshot || (swipe as any)?.ad_library_object?.snapshot || swipe.ad_library_object || {};
  const title = snapshot?.title || swipe.title;
  const pageName = snapshot?.page_name || title || "Saved swipe";
  const snapshotBody = snapshot?.body;
  const body =
    typeof snapshotBody?.text === "string"
      ? snapshotBody.text
      : typeof snapshotBody === "string"
      ? snapshotBody
      : typeof swipe.body === "string"
      ? swipe.body
      : undefined;
  const ctaText = snapshot?.cta_text || swipe.cta_text;
  const destinationUrl = snapshot?.link_url || swipe.landing_page || swipe.ad_source_link;

  const snapshotImages = mapSwipeImages(snapshot, title || pageName);
  const snapshotVideos = mapSwipeVideos(snapshot, snapshotImages[0]?.thumbUrl);
  const storedMedia = mapSwipeStoredMedia(swipe.media, title || pageName);

  const media: MediaAsset[] = [...snapshotVideos, ...snapshotImages];
  if (storedMedia.length) {
    media.push(...storedMedia);
  }

  return {
    id: swipe.external_platform_ad_id || swipe.external_ad_id || swipe.id,
    kind: "swipe",
    brandName: pageName,
    platform: mapSwipePlatforms(swipe, snapshot),
    headline: title,
    body,
    ctaText,
    destinationUrl,
    media,
    status: swipe.active === true ? "active" : swipe.active === false ? "inactive" : undefined,
    raw: swipe,
  };
}

export function normalizeExploreAdToLibraryItem(ad: any): LibraryItem {
  const media = mapMediaAssets(ad?.media_assets);
  const scoresRaw = ad?.scores || {};
  return {
    id: ad?.ad_id || ad?.id || randomId(),
    kind: "ad",
    brandName: ad?.brand_name || "Unknown brand",
    platform: ad?.channel ? [ad.channel] : [],
    status: mapStatus(ad?.ad_status),
    startAt: ad?.facts?.start_date || ad?.start_date,
    endAt: ad?.end_date,
    capturedAt: ad?.last_seen_at,
    headline: ad?.headline,
    body: ad?.primary_text,
    ctaText: ad?.cta_text,
    destinationUrl: ad?.landing_url || ad?.destination_domain,
    media,
    raw: ad,
    scores: {
      performanceScore: scoresRaw.performance_score ?? scoresRaw.performanceScore,
      performanceStars: scoresRaw.performance_stars ?? scoresRaw.performanceStars,
      winningScore: scoresRaw.winning_score ?? scoresRaw.winningScore,
      confidence: scoresRaw.confidence,
      scoreVersion: scoresRaw.score_version ?? scoresRaw.scoreVersion,
    },
  };
}
