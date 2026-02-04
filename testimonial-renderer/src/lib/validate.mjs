import fs from 'fs';
import path from 'path';
import { pathToFileURL } from 'url';

const TEMPLATE_TYPES = new Set(['review_card', 'social_comment', 'testimonial_media']);
const MAX_NAME_LENGTH = 80;
const MAX_REVIEW_LENGTH = 800;
const MAX_COMMENT_LENGTH = 600;
const MAX_HEADER_TITLE = 40;
const MAX_META_LABEL = 24;
const MAX_VIEW_REPLIES = 40;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

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

  throw new Error('Unsupported template.');
};
