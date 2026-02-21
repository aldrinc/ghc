import fs from 'fs';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';

const TEMPLATE_TYPES = new Set([
  'review_card',
  'social_comment',
  'testimonial_media',
  'pdp_ugc_standard',
  'pdp_bold_claim',
  'pdp_personal_highlight',
]);
const MAX_NAME_LENGTH = 80;
const MAX_REVIEW_LENGTH = 800;
const MAX_COMMENT_LENGTH = 600;
const MAX_HEADER_TITLE = 40;
const MAX_META_LABEL = 24;
const MAX_VIEW_REPLIES = 40;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const PDP_OUTPUT_PRESETS = new Set(['tiktok', 'feed']);
const PDP_DEFAULT_OUTPUT_PRESET = 'tiktok';
const PDP_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;
const MAX_PDP_HANDLE = 40;
const MAX_PDP_COMMENT = 220;
const MAX_PDP_CTA = 60;
const MAX_PDP_LOGO_TEXT = 24;
const MAX_PDP_RATING_VALUE = 16;
const MAX_PDP_RATING_DETAIL = 60;
const MAX_PDP_BRAND_NAME = 80;
const MAX_PDP_BRAND_NOTES = 260;
const NANO_REFERENCE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp']);
const NANO_REFERENCE_DATA_MIME_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/webp',
]);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PDP_DEFAULT_AVATAR_PATH = path.resolve(__dirname, '../templates/assets/pdp-default-avatar.svg');

const resolvePdpDefaultAvatarUrl = () => {
  if (!fs.existsSync(PDP_DEFAULT_AVATAR_PATH)) {
    throw new Error(`Default PDP avatar file does not exist: ${PDP_DEFAULT_AVATAR_PATH}`);
  }
  return pathToFileURL(PDP_DEFAULT_AVATAR_PATH).href;
};

const isPlainObject = (value) =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const assertString = (value, field, maxLength) => {
  if (typeof value !== 'string') {
    throw new Error(`${field} must be a string.`);
  }
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(`${field} must not be empty.`);
  }
  if (maxLength && trimmed.length > maxLength) {
    throw new Error(`${field} must be at most ${maxLength} characters.`);
  }
  return trimmed;
};

const assertBoolean = (value, field) => {
  if (typeof value !== 'boolean') {
    throw new Error(`${field} must be a boolean.`);
  }
  return value;
};

const assertOptionalString = (value, field, maxLength) => {
  if (value == null) {
    return undefined;
  }
  return assertString(value, field, maxLength);
};

const assertColor = (value, field) => {
  const color = assertString(value, field, 24);
  if (!PDP_COLOR_PATTERN.test(color)) {
    throw new Error(`${field} must be a hex color like #fff or #ffffff.`);
  }
  return color;
};

const assertRating = (value, field) => {
  if (!Number.isInteger(value)) {
    throw new Error(`${field} must be an integer between 1 and 5.`);
  }
  if (value < 1 || value > 5) {
    throw new Error(`${field} must be an integer between 1 and 5.`);
  }
  return value;
};

const resolveImageUrl = (value, baseDir, field) => {
  const url = assertString(value, field);
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  if (url.startsWith('data:')) {
    return url;
  }
  if (url.startsWith('file://')) {
    const filePath = url.replace('file://', '');
    if (!fs.existsSync(filePath)) {
      throw new Error(`${field} file does not exist: ${filePath}`);
    }
    return url;
  }

  const resolvedPath = path.resolve(baseDir || process.cwd(), url);
  if (!fs.existsSync(resolvedPath)) {
    throw new Error(`${field} file does not exist: ${resolvedPath}`);
  }
  return pathToFileURL(resolvedPath).href;
};

const assertNanoReferenceImageUrl = (resolvedUrl, field) => {
  if (typeof resolvedUrl !== 'string' || !resolvedUrl.trim()) {
    throw new Error(`${field} must be a non-empty image source.`);
  }
  const trimmed = resolvedUrl.trim();
  if (trimmed.startsWith('data:')) {
    const match = trimmed.match(/^data:([^;]+);/i);
    const mimeType = match ? match[1].trim().toLowerCase() : '';
    if (!NANO_REFERENCE_DATA_MIME_TYPES.has(mimeType)) {
      throw new Error(`${field} must use png/jpg/jpeg/webp when using data URLs.`);
    }
    return;
  }

  let pathname = trimmed;
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('file://')) {
    try {
      pathname = new URL(trimmed).pathname || trimmed;
    } catch {
      pathname = trimmed;
    }
  }

  const extension = path.extname(pathname).toLowerCase();
  if (!NANO_REFERENCE_EXTENSIONS.has(extension)) {
    throw new Error(`${field} must reference a png/jpg/jpeg/webp image.`);
  }
};

const validatePdpOutput = (output) => {
  if (output == null) {
    return { preset: PDP_DEFAULT_OUTPUT_PRESET };
  }
  if (!isPlainObject(output)) {
    throw new Error('output must be an object when provided.');
  }
  const allowedKeys = new Set(['preset']);
  for (const key of Object.keys(output)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`output contains unsupported key: ${key}`);
    }
  }

  const preset = assertString(output.preset, 'output.preset', 24).toLowerCase();
  if (!PDP_OUTPUT_PRESETS.has(preset)) {
    throw new Error(`output.preset must be one of: ${Array.from(PDP_OUTPUT_PRESETS).join(', ')}`);
  }
  return { preset };
};

const validatePdpBrand = (brand, baseDir) => {
  if (!isPlainObject(brand)) {
    throw new Error('brand must be an object.');
  }
  const allowedKeys = new Set([
    'logoUrl',
    'logoText',
    'stripBgColor',
    'stripTextColor',
    'name',
    'assets',
  ]);
  for (const key of Object.keys(brand)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`brand contains unsupported key: ${key}`);
    }
  }

  const stripBgColor = assertColor(brand.stripBgColor, 'brand.stripBgColor');
  const stripTextColor = assertColor(brand.stripTextColor, 'brand.stripTextColor');

  let logoUrl;
  if (brand.logoUrl != null) {
    logoUrl = resolveImageUrl(brand.logoUrl, baseDir, 'brand.logoUrl');
  }
  const logoText = assertOptionalString(brand.logoText, 'brand.logoText', MAX_PDP_LOGO_TEXT);

  if (!logoUrl && !logoText) {
    throw new Error('brand.logoUrl or brand.logoText is required.');
  }

  const name = assertOptionalString(brand.name, 'brand.name', MAX_PDP_BRAND_NAME);
  const assets = validatePdpBrandAssets(brand.assets, baseDir);

  return { stripBgColor, stripTextColor, logoUrl, logoText, name, assets };
};

const validatePdpBrandPalette = (palette) => {
  if (!isPlainObject(palette)) {
    throw new Error('brand.assets.palette must be an object when provided.');
  }
  const allowedKeys = new Set(['primary', 'secondary', 'accent']);
  for (const key of Object.keys(palette)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`brand.assets.palette contains unsupported key: ${key}`);
    }
  }

  const output = {};
  if (palette.primary != null) {
    output.primary = assertColor(palette.primary, 'brand.assets.palette.primary');
  }
  if (palette.secondary != null) {
    output.secondary = assertColor(palette.secondary, 'brand.assets.palette.secondary');
  }
  if (palette.accent != null) {
    output.accent = assertColor(palette.accent, 'brand.assets.palette.accent');
  }

  if (Object.keys(output).length === 0) {
    throw new Error('brand.assets.palette must include at least one color token.');
  }
  return output;
};

const validatePdpBrandAssets = (assets, baseDir) => {
  if (assets == null) {
    return undefined;
  }
  if (!isPlainObject(assets)) {
    throw new Error('brand.assets must be an object when provided.');
  }
  const allowedKeys = new Set(['logoUrl', 'referenceImages', 'palette', 'notes']);
  for (const key of Object.keys(assets)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`brand.assets contains unsupported key: ${key}`);
    }
  }

  let logoUrl;
  if (assets.logoUrl != null) {
    logoUrl = resolveImageUrl(assets.logoUrl, baseDir, 'brand.assets.logoUrl');
    assertNanoReferenceImageUrl(logoUrl, 'brand.assets.logoUrl');
  }

  let referenceImages;
  if (assets.referenceImages != null) {
    if (!Array.isArray(assets.referenceImages) || assets.referenceImages.length === 0) {
      throw new Error('brand.assets.referenceImages must be a non-empty array when provided.');
    }
    referenceImages = assets.referenceImages.map((entry, index) =>
      resolveImageUrl(entry, baseDir, `brand.assets.referenceImages[${index}]`),
    );
    referenceImages.forEach((entry, index) => {
      assertNanoReferenceImageUrl(entry, `brand.assets.referenceImages[${index}]`);
    });
  }

  let palette;
  if (assets.palette != null) {
    palette = validatePdpBrandPalette(assets.palette);
  }

  const notes = assertOptionalString(assets.notes, 'brand.assets.notes', MAX_PDP_BRAND_NOTES);

  if (!logoUrl && !referenceImages && !palette && !notes) {
    throw new Error('brand.assets must include at least one of logoUrl, referenceImages, palette, or notes.');
  }

  return { logoUrl, referenceImages, palette, notes };
};

const validatePdpRating = (rating) => {
  if (!isPlainObject(rating)) {
    throw new Error('rating must be an object.');
  }
  const allowedKeys = new Set(['valueText', 'detailText']);
  for (const key of Object.keys(rating)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`rating contains unsupported key: ${key}`);
    }
  }
  const valueText = assertString(rating.valueText, 'rating.valueText', MAX_PDP_RATING_VALUE);
  const detailText = assertString(rating.detailText, 'rating.detailText', MAX_PDP_RATING_DETAIL);
  return { valueText, detailText };
};

const validatePdpCta = (cta) => {
  if (!isPlainObject(cta)) {
    throw new Error('cta must be an object.');
  }
  const allowedKeys = new Set(['text']);
  for (const key of Object.keys(cta)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`cta contains unsupported key: ${key}`);
    }
  }
  const text = assertString(cta.text, 'cta.text', MAX_PDP_CTA);
  return { text };
};

const validatePdpPromptVars = (vars) => {
  if (!isPlainObject(vars)) {
    throw new Error('background.promptVars must be an object.');
  }
  const allowedKeys = new Set(['product', 'scene', 'subject', 'extra', 'avoid']);
  for (const key of Object.keys(vars)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`background.promptVars contains unsupported key: ${key}`);
    }
  }

  const product = assertString(vars.product, 'background.promptVars.product', 220);
  const scene = assertOptionalString(vars.scene, 'background.promptVars.scene', 220);
  const subject = assertOptionalString(vars.subject, 'background.promptVars.subject', 220);
  const extra = assertOptionalString(vars.extra, 'background.promptVars.extra', 600);

  let avoid;
  if (vars.avoid != null) {
    if (!Array.isArray(vars.avoid) || vars.avoid.length === 0) {
      throw new Error('background.promptVars.avoid must be a non-empty array when provided.');
    }
    avoid = vars.avoid.map((entry, index) =>
      assertString(entry, `background.promptVars.avoid[${index}]`, 160),
    );
  }

  return { product, scene, subject, extra, avoid };
};

const validatePdpBackground = (background, baseDir) => {
  if (!isPlainObject(background)) {
    throw new Error('background must be an object.');
  }
  const allowedKeys = new Set([
    'imageUrl',
    'alt',
    'prompt',
    'promptVars',
    'referenceImages',
    'referenceFirst',
    'imageModel',
    'imageConfig',
  ]);
  for (const key of Object.keys(background)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`background contains unsupported key: ${key}`);
    }
  }

  let imageUrl;
  if (background.imageUrl != null) {
    imageUrl = resolveImageUrl(background.imageUrl, baseDir, 'background.imageUrl');
  }
  const alt = assertOptionalString(background.alt, 'background.alt', 200);
  const prompt = assertOptionalString(background.prompt, 'background.prompt', 6000);

  let promptVars;
  if (background.promptVars != null) {
    promptVars = validatePdpPromptVars(background.promptVars);
  }

  if (prompt && promptVars) {
    throw new Error('Provide either background.prompt or background.promptVars, not both.');
  }
  if (imageUrl && (prompt || promptVars)) {
    throw new Error('Provide either background.imageUrl or background.prompt/background.promptVars, not both.');
  }

  if (!imageUrl && !prompt && !promptVars) {
    throw new Error('background.imageUrl is required unless background.prompt or background.promptVars is provided.');
  }

  let referenceImages;
  if (background.referenceImages != null) {
    if (!Array.isArray(background.referenceImages) || background.referenceImages.length === 0) {
      throw new Error('background.referenceImages must be a non-empty array when provided.');
    }
    referenceImages = background.referenceImages.map((entry, index) =>
      assertString(entry, `background.referenceImages[${index}]`, 2000),
    );
  }

  let referenceFirst;
  if (background.referenceFirst != null) {
    referenceFirst = assertBoolean(background.referenceFirst, 'background.referenceFirst');
  }

  const imageModel = assertOptionalString(background.imageModel, 'background.imageModel', 120);

  let imageConfig;
  if (background.imageConfig != null) {
    if (!isPlainObject(background.imageConfig)) {
      throw new Error('background.imageConfig must be an object when provided.');
    }
    imageConfig = background.imageConfig;
  }

  if (imageUrl) {
    if (referenceImages != null || referenceFirst != null || imageModel != null || imageConfig != null) {
      throw new Error(
        'background.referenceImages/referenceFirst/imageModel/imageConfig are only allowed when generating a background (omit background.imageUrl).',
      );
    }
  }

  return {
    imageUrl,
    alt,
    prompt,
    promptVars,
    referenceImages,
    referenceFirst,
    imageModel,
    imageConfig,
  };
};

const validatePdpComment = (comment, options) => {
  const { baseDir, prefix } = options;
  if (!isPlainObject(comment)) {
    throw new Error(`${prefix} must be an object.`);
  }
  const allowedKeys = new Set(['handle', 'text', 'avatarUrl', 'verified']);
  for (const key of Object.keys(comment)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`${prefix} contains unsupported key: ${key}`);
    }
  }
  const handle = assertString(comment.handle, `${prefix}.handle`, MAX_PDP_HANDLE);
  const text = assertString(comment.text, `${prefix}.text`, MAX_PDP_COMMENT);
  let avatarUrl = resolvePdpDefaultAvatarUrl();
  if (comment.avatarUrl != null) {
    if (typeof comment.avatarUrl !== 'string') {
      throw new Error(`${prefix}.avatarUrl must be a string.`);
    }
    const candidate = comment.avatarUrl.trim();
    if (candidate) {
      avatarUrl = resolveImageUrl(candidate, baseDir, `${prefix}.avatarUrl`);
    }
  }
  let verified;
  if (comment.verified != null) {
    verified = assertBoolean(comment.verified, `${prefix}.verified`);
  }
  return { handle, text, avatarUrl, verified };
};

const validateMeta = (meta, options = {}) => {
  const {
    allowedKeys = ['location', 'date', 'timeAgo', 'reactionCount'],
    fieldPrefix = 'meta',
  } = options;
  if (meta == null) {
    return undefined;
  }
  if (!isPlainObject(meta)) {
    throw new Error(`${fieldPrefix} must be an object when provided.`);
  }
  const allowedKeySet = new Set(allowedKeys);
  const output = {};

  for (const key of Object.keys(meta)) {
    if (!allowedKeySet.has(key)) {
      throw new Error(`${fieldPrefix} contains unsupported key: ${key}`);
    }
  }

  if (meta.location != null) {
    output.location = assertString(meta.location, `${fieldPrefix}.location`, 120);
  }
  if (meta.date != null) {
    const dateValue = assertString(meta.date, `${fieldPrefix}.date`, 32);
    if (!DATE_PATTERN.test(dateValue)) {
      throw new Error(`${fieldPrefix}.date must use YYYY-MM-DD format.`);
    }
    output.date = dateValue;
  }
  if (meta.timeAgo != null) {
    output.timeAgo = assertString(meta.timeAgo, `${fieldPrefix}.timeAgo`, 24);
  }
  if (meta.reactionCount != null) {
    if (!Number.isInteger(meta.reactionCount) || meta.reactionCount < 0) {
      throw new Error(`${fieldPrefix}.reactionCount must be a non-negative integer.`);
    }
    output.reactionCount = meta.reactionCount;
  }

  return output;
};

const validateHeader = (header) => {
  if (!isPlainObject(header)) {
    throw new Error('header must be an object.');
  }
  const allowedKeys = new Set(['title', 'showSortIcon']);
  for (const key of Object.keys(header)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`header contains unsupported key: ${key}`);
    }
  }

  const title = assertString(header.title, 'header.title', MAX_HEADER_TITLE);
  if (typeof header.showSortIcon !== 'boolean') {
    throw new Error('header.showSortIcon must be a boolean.');
  }

  return { title, showSortIcon: header.showSortIcon };
};

const validateThreadMeta = (meta, prefix) => {
  if (!isPlainObject(meta)) {
    throw new Error(`${prefix} must be an object.`);
  }
  const allowedKeys = new Set(['time', 'followLabel', 'authorLabel']);
  for (const key of Object.keys(meta)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`${prefix} contains unsupported key: ${key}`);
    }
  }

  const time = assertString(meta.time, `${prefix}.time`, 24);
  const output = { time };

  if (meta.followLabel != null) {
    output.followLabel = assertString(meta.followLabel, `${prefix}.followLabel`, MAX_META_LABEL);
  }
  if (meta.authorLabel != null) {
    output.authorLabel = assertString(meta.authorLabel, `${prefix}.authorLabel`, MAX_META_LABEL);
  }

  return output;
};

const validateReactionCount = (value, field) => {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${field} must be a non-negative integer.`);
  }
  return value;
};

const validateThreadComment = (comment, options) => {
  const { baseDir, prefix } = options;
  if (!isPlainObject(comment)) {
    throw new Error(`${prefix} must be an object.`);
  }

  const allowedKeys = new Set([
    'name',
    'text',
    'avatarUrl',
    'meta',
    'reactionCount',
    'attachmentUrl',
    'replies',
    'viewRepliesText',
  ]);
  for (const key of Object.keys(comment)) {
    if (!allowedKeys.has(key)) {
      throw new Error(`${prefix} contains unsupported key: ${key}`);
    }
  }

  const name = assertString(comment.name, `${prefix}.name`, MAX_NAME_LENGTH);
  const text = assertString(comment.text, `${prefix}.text`, MAX_COMMENT_LENGTH);
  const avatarUrl = resolveImageUrl(comment.avatarUrl, baseDir, `${prefix}.avatarUrl`);
  const meta = validateThreadMeta(comment.meta, `${prefix}.meta`);
  let reactionCount;
  if (comment.reactionCount != null) {
    reactionCount = validateReactionCount(comment.reactionCount, `${prefix}.reactionCount`);
  }

  let attachmentUrl;
  if (comment.attachmentUrl != null) {
    attachmentUrl = resolveImageUrl(comment.attachmentUrl, baseDir, `${prefix}.attachmentUrl`);
  }

  let viewRepliesText;
  if (comment.viewRepliesText != null) {
    viewRepliesText = assertString(comment.viewRepliesText, `${prefix}.viewRepliesText`, MAX_VIEW_REPLIES);
  }

  let replies;
  if (comment.replies != null) {
    if (!Array.isArray(comment.replies) || comment.replies.length === 0) {
      throw new Error(`${prefix}.replies must be a non-empty array when provided.`);
    }
    replies = comment.replies.map((reply, index) =>
      validateThreadComment(reply, { baseDir, prefix: `${prefix}.replies[${index}]` }),
    );
  }

  return {
    name,
    text,
    avatarUrl,
    meta,
    reactionCount,
    attachmentUrl,
    replies,
    viewRepliesText,
  };
};

export const validatePayload = (payload, options = {}) => {
  if (!isPlainObject(payload)) {
    throw new Error('Payload must be an object.');
  }

  const template = payload.template;
  if (typeof template !== 'string' || !TEMPLATE_TYPES.has(template)) {
    throw new Error(`template must be one of: ${Array.from(TEMPLATE_TYPES).join(', ')}`);
  }

  if (template === 'review_card') {
    const name = assertString(payload.name, 'name', MAX_NAME_LENGTH);
    const review = assertString(payload.review, 'review', MAX_REVIEW_LENGTH);
    const meta = validateMeta(payload.meta, {
      allowedKeys: ['location', 'date'],
      fieldPrefix: 'meta',
    });

    const output = {
      ...payload,
      template,
      name,
      review,
      meta,
    };

    output.verified = assertBoolean(payload.verified, 'verified');
    output.rating = assertRating(payload.rating, 'rating');
    if (payload.heroImageUrl != null) {
      output.heroImageUrl = resolveImageUrl(payload.heroImageUrl, options.baseDir, 'heroImageUrl');
    }
    if (payload.avatarUrl != null) {
      output.avatarUrl = resolveImageUrl(payload.avatarUrl, options.baseDir, 'avatarUrl');
    }

    return output;
  }

  if (template === 'social_comment') {
    const header = validateHeader(payload.header);
    if (!Array.isArray(payload.comments) || payload.comments.length === 0) {
      throw new Error('comments must be a non-empty array.');
    }

    const comments = payload.comments.map((comment, index) =>
      validateThreadComment(comment, { baseDir: options.baseDir, prefix: `comments[${index}]` }),
    );

    return {
      ...payload,
      template,
      header,
      comments,
    };
  }

  if (template === 'testimonial_media') {
    const imageUrl = resolveImageUrl(payload.imageUrl, options.baseDir, 'imageUrl');
    let alt;
    if (payload.alt != null) {
      alt = assertString(payload.alt, 'alt', 200);
    }
    return {
      ...payload,
      template,
      imageUrl,
      alt,
    };
  }

  if (
    template === 'pdp_ugc_standard' ||
    template === 'pdp_bold_claim' ||
    template === 'pdp_personal_highlight'
  ) {
    const allowedKeys = new Set([
      'template',
      'output',
      'brand',
      'rating',
      'cta',
      'background',
      'comment',
      'imageModel',
    ]);
    for (const key of Object.keys(payload)) {
      if (!allowedKeys.has(key)) {
        throw new Error(`Payload contains unsupported key: ${key}`);
      }
    }

    const output = validatePdpOutput(payload.output);
    const brand = validatePdpBrand(payload.brand, options.baseDir);
    const rating = validatePdpRating(payload.rating);
    const cta = validatePdpCta(payload.cta);
    const background = validatePdpBackground(payload.background, options.baseDir);

    let imageModel;
    if (payload.imageModel != null) {
      imageModel = assertString(payload.imageModel, 'imageModel', 120);
    }

    const comment = validatePdpComment(payload.comment, { baseDir: options.baseDir, prefix: 'comment' });
    return {
      template,
      output,
      brand,
      rating,
      cta,
      background,
      comment,
      imageModel,
    };
  }

  throw new Error('Unsupported template.');
};
