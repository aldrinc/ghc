export type ImageAsset = {
  src: string
  alt: string
}

export type NavItem = {
  label: string
  href: string
}

export type HeaderConfig = {
  logo: ImageAsset & { href?: string }
  nav: NavItem[]
  cta: {
    label: string
    href: string
  }
}

export type MarqueeConfig = {
  items: string[]
  /** If you want the marquee to repeat items more often, increase this. */
  repeat?: number
}

export type GallerySlide = ImageAsset & {
  thumbSrc?: string
}

export type GalleryConfig = {
  freeGifts?: {
    icon: ImageAsset
    title: string
    body: string
    ctaLabel: string
  }

  watchInAction: {
    label: string
  }

  slides: GallerySlide[]
}

export type FaqPill = {
  /** The question shown in the horizontal pill list */
  label: string
  /** The short inline answer shown below the pills when selected */
  answer: string
}

export type BenefitItem = {
  text: string
}

export type SizeOption = {
  id: string
  label: string
  sizeIn: string
  sizeCm: string
}

export type ColorOption = {
  id: string
  label: string
  /** Optional explicit swatch color. */
  swatch?: string
  /** Optional pattern image for the swatch. */
  swatchImageSrc?: string
}

export type OfferOption = {
  id: string
  title: string
  image: ImageAsset
  price: number
  compareAt?: number
  saveLabel?: string
}

export type InventoryRule = {
  sizeId: string
  colorId: string
}

export type PurchaseConfig = {
  faqPills: FaqPill[]

  title: string
  benefits: BenefitItem[]

  size: {
    title: string
    helpLinkLabel: string
    options: SizeOption[]
    shippingDelayLabel: string
  }

  color: {
    title: string
    options: ColorOption[]
    outOfStockTitle: string
    outOfStockBody: string
  }

  offer: {
    title: string
    helperText: string
    seeWhyLabel: string
    options: OfferOption[]
  }

  cta: {
    labelTemplate: string
    subBullets: string[]
    urgency: {
      message: string
      rows: Array<{ label: string; value: string; tone?: 'muted' | 'highlight' }>
    }
  }

  /** Combinations that should show the out-of-stock notice. */
  outOfStock?: InventoryRule[]
  /** Combinations that should show the shipping delay banner. */
  shippingDelay?: InventoryRule[]
}

export type HeroConfig = {
  header: HeaderConfig
  gallery: GalleryConfig
  purchase: PurchaseConfig
}

export type VideoItem = {
  id: string
  thumbnail: ImageAsset
}

export type VideoSectionConfig = {
  badge: string
  title: string
  videos: VideoItem[]
}

export type StoryBullet = {
  title: string
  body: string
}

export type StorySectionConfig = {
  id?: string
  bg: 'peach' | 'blue'
  badge: string
  title: string
  paragraphs: string[]
  emphasisLine?: string
  bullets?: StoryBullet[]
  image: ImageAsset
  /** 'textLeft' matches the screenshots (text left, image right) */
  layout?: 'textLeft' | 'textRight'
}

export type CalloutConfig = {
  leftTitle: string
  leftBody: string
  rightTitle: string
  rightBody: string
}

export type ComparisonRow = {
  label: string
  pup: string
  disposable: string
}

export type ComparisonConfig = {
  id?: string
  badge: string
  title: string
  swipeHint: string
  columns: {
    pup: string
    disposable: string
  }
  rows: ComparisonRow[]
}

export type ReviewSliderConfig = {
  title: string
  body: string
  hint: string
  toggle: { auto: string; manual: string }
  slides: ImageAsset[]
}

export type GuaranteeConfig = {
  id?: string
  badge: string
  title: string
  paragraphs: string[]
  whyTitle: string
  whyBody: string
  closingLine: string

  right: {
    image: ImageAsset
    reviewCard: {
      name: string
      verifiedLabel: string
      rating: number
      text: string
    }
    commentThread: {
      label: string
      comments: Array<{ name: string; text: string }>
    }
  }
}

export type FaqItem = {
  question: string
  answer: string
}

export type FaqConfig = {
  id?: string
  title: string
  items: FaqItem[]
}

export type ReviewTile = {
  id: string
  image: ImageAsset
}

export type ReviewWallConfig = {
  id?: string
  badge: string
  title: string
  ratingLabel: string
  tiles: ReviewTile[]
  showMoreLabel: string
}

export type FooterConfig = {
  logo: ImageAsset
  copyright: string
  company?: string
}

export type ModalsConfig = {
  sizeChart: {
    title: string
    sizes: Array<{
      label: string
      size: string
      idealFor: string
      weight: string
    }>
    note: string
  }

  whyBundle: {
    title: string
    body: string
    quotes: Array<{ text: string; author: string }>
  }

  freeGifts: {
    title: string
    body: string
  }
}

export type PdpConfig = {
  hero: HeroConfig
  videos: VideoSectionConfig
  marquee: MarqueeConfig
  story: {
    problem: StorySectionConfig
    solution: StorySectionConfig & { callout: CalloutConfig }
  }
  comparison: ComparisonConfig
  reviewSlider: ReviewSliderConfig
  guarantee: GuaranteeConfig
  faq: FaqConfig
  reviewWall: ReviewWallConfig
  footer: FooterConfig
  modals: ModalsConfig
}
