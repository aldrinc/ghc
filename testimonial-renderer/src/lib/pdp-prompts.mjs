const aspectRatioForPreset = (preset) => {
  if (preset === 'feed') {
    return '4:5';
  }
  if (preset === 'tiktok') {
    return '9:16';
  }
  throw new Error(`Unsupported output preset: ${preset}`);
};

const bubbleSpaceHintForTemplate = (template) => {
  switch (template) {
    case 'pdp_ugc_standard':
      return [
        'Leave clean negative space in the lower-left area for a small comment bubble overlay.',
        'Keep the product and hands on the right side of the frame and do not place the product in the lower-left.',
      ].join(' ');
    case 'pdp_bold_claim':
      return [
        'Leave clean negative space in the top-right area for a small comment bubble overlay.',
        'Keep the product in the lower-middle or lower-left of the frame and do not place the product in the top-right.',
      ].join(' ');
    case 'pdp_personal_highlight':
      return [
        'Leave clean negative space in the top-left area for a small comment bubble overlay.',
        'Keep the product held lower-right or lower-middle, not in the top-left.',
      ].join(' ');
    default:
      throw new Error(`Unsupported PDP template: ${template}`);
  }
};

const baseUgcStyleBlock = (aspectRatio) =>
  [
    'Slightly off-center framing, a tiny bit of motion blur, natural skin texture with small imperfections, hair slightly messy, clothes lightly wrinkled.',
    'Mixed indoor lighting (warm lamp + daylight spill), auto white balance, auto exposure, mild digital noise and JPEG compression, soft focus (not razor sharp), realistic colors.',
    'Ordinary home background with a little clutter. No studio setup. No seamless backdrop. No dramatic lighting. No flash.',
    'No on-image text overlays, no captions, no watermarks, no UI elements.',
    `${aspectRatio} aspect ratio.`,
  ].join(' ');

const stringifyAvoid = (avoid) => {
  if (!Array.isArray(avoid) || avoid.length === 0) {
    return null;
  }
  const cleaned = avoid.map((x) => (typeof x === 'string' ? x.trim() : '')).filter(Boolean);
  if (cleaned.length === 0) {
    return null;
  }
  return `Avoid: ${cleaned.join('; ')}.`;
};

export const buildPdpBackgroundPrompt = ({ template, preset, vars }) => {
  if (typeof template !== 'string' || !template.trim()) {
    throw new Error('template is required to build PDP background prompt.');
  }
  if (typeof preset !== 'string' || !preset.trim()) {
    throw new Error('preset is required to build PDP background prompt.');
  }
  if (!vars || typeof vars !== 'object') {
    throw new Error('vars is required to build PDP background prompt.');
  }

  const aspectRatio = aspectRatioForPreset(preset);
  const bubbleHint = bubbleSpaceHintForTemplate(template);

  const product = typeof vars.product === 'string' ? vars.product.trim() : '';
  if (!product) {
    throw new Error('background.promptVars.product is required to build PDP background prompt.');
  }

  const subject = typeof vars.subject === 'string' ? vars.subject.trim() : '';
  const scene = typeof vars.scene === 'string' ? vars.scene.trim() : '';
  const extra = typeof vars.extra === 'string' ? vars.extra.trim() : '';
  const avoidLine = stringifyAvoid(vars.avoid);

  const lines = [];
  if (template === 'pdp_bold_claim') {
    lines.push(
      `A casual smartphone photo of ${product} on a simple surface at home (not studio), photographed quickly by hand.`,
    );
    if (scene) {
      lines.push(`Scene: ${scene}.`);
    }
  } else {
    const who = subject ? subject : 'a real customer';
    lines.push(`A casual, unposed smartphone photo of ${who} holding ${product}.`);
    if (scene) {
      lines.push(`Scene: ${scene}.`);
    }
  }

  lines.push(bubbleHint);
  lines.push(baseUgcStyleBlock(aspectRatio));

  if (extra) {
    lines.push(extra.endsWith('.') ? extra : `${extra}.`);
  }
  if (avoidLine) {
    lines.push(avoidLine);
  }

  return lines.join(' ');
};
