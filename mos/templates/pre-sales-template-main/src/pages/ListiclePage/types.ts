export type Badge = {
  iconSrc: string
  iconAlt: string
  value?: string
  label: string
}

export type HeroMedia =
  | {
      type: 'image'
      src: string
      alt: string
    }
  | {
      type: 'video'
      srcMp4: string
      poster?: string
      alt?: string
    }

export type Reason = {
  number: number
  title: string
  body: string
  image?: {
    src: string
    alt: string
  }
}

export type Pitch = {
  title: string
  bullets: string[]
  image: {
    src: string
    alt: string
  }
  cta?: {
    label: string
    href: string
  }
}

export type ReviewSlide = {
  /** 1-5. Defaults to 5 if omitted. */
  rating?: number
  text: string
  author: string
  verified?: boolean
  /**
    Up to 3 images recommended (to match the PuppyPad layout):
    - 1 large image
    - 2 tall / slim images
  */
  images: Array<{ src: string; alt: string }>
}

export type Reviews = {
  slides: ReviewSlide[]
  /** Auto-advance interval for the carousel (ms). */
  autoAdvanceMs?: number
}

export type WallReview = {
  author: string
  rating?: number
  verified?: boolean
  text: string
  image?: {
    src: string
    alt: string
  }
  /** If an image exists, where should it render? */
  imagePosition?: 'top' | 'bottom'
}

export type ReviewsWall = {
  title: string
  buttonLabel: string
  columns: WallReview[][]
}

export type Footer = {
  logo: {
    src: string
    alt: string
  }
}

export type FloatingCta = {
  label: string
  href: string
  /** Which reason number should reveal the floating CTA (e.g. 5). */
  showAfterReason?: number
  /** Which element id should reveal the floating CTA (e.g. "listicle-end"). */
  showAfterId?: string
}

export type ListicleConfig = {
  hero: {
    title: string
    subtitle: string
    media?: HeroMedia
  }
  badges: Badge[]
  reasons: Reason[]
  marquee: string[]
  pitch: Pitch
  reviews: Reviews
  reviewsWall: ReviewsWall
  footer: Footer
  floatingCta: FloatingCta
}
