import type { SiteConfig } from './types'

/**
 * Single-source configuration for:
 * - all page content (headings, bullets, listicle items, reviews, CTAs)
 * - UI copy (labels / aria text)
 * - optional theme overrides (CSS variables)
 * - basic meta tags
 */
export const siteConfig: SiteConfig = {
  meta: {
    lang: 'en',
    title: 'PuppyPad Listicle',
    description: '5 Reasons Why Shelters & Dog Owners Are Going Crazy Over This Reusable Pee Pad'
  },

  /**
   * Optional runtime theming.
   *
   * This does NOT replace src/theme/tokens.css — it just overrides any tokens you specify.
   *
   * Example:
   * tokens: {
   *   '--color-brand': '#111827',
   *   '--hero-bg': '#fff7ed',
   *   '--marquee-speed': '35s'
   * }
   */
  theme: {
    tokens: {}
  },

  /**
   * Small UI strings that otherwise end up hard-coded inside components.
   * Keep these here so the entire site is driven by config.
   */
  copy: {
    common: {
      starsAriaLabelTemplate: '{rating} out of 5 stars'
    },

    modal: {
      closeAriaLabel: 'Close',
      dialogAriaLabel: 'Dialog'
    },

    reviews: {
      sectionAriaLabel: 'Customer reviews',
      prevButtonAriaLabel: 'Previous review',
      nextButtonAriaLabel: 'Next review',
      dotsAriaLabel: 'Review navigation',
      goToReviewAriaLabelTemplate: 'Go to review {index}'
    },

    reviewWall: {
      verifiedLabel: 'Verified Customer'
    }
  },

  page: {
    hero: {
      title: 'This New Pee Pad Attracts Dogs Like A Magnet 🧲',
      subtitle: '5 Reasons Why Shelters & Dog Owners Are Going Crazy Over This Reusable Pee Pad',
      media: {
        type: 'image',
        src: '/assets/Attraction.webp',
        alt: 'PuppyPad in use'
      }
      // To use video instead:
      // media: {
      //   type: 'video',
      //   srcMp4: '/assets/hero.mp4',
      //   poster: '/assets/hero-poster.webp'
      // }
    },

    badges: [
      {
        iconSrc: '/assets/5-stars-reviews-icon.webp',
        iconAlt: '5 star reviews',
        value: '150,000',
        label: '5-STAR REVIEWS'
      },
      {
        iconSrc: '/assets/free-shipping-icon.webp',
        iconAlt: 'Free shipping',
        label: 'FAST AND FREE SHIPPING'
      },
      {
        iconSrc: '/assets/risk-free-icon.webp',
        iconAlt: 'Risk free trial',
        label: '90-DAY RISK-FREE TRIAL'
      }
    ],

    reasons: [
      {
        number: 1,
        title: 'Dogs Use It Right Away Without Training',
        body:
          "You know that frustrating moment when your dog pees RIGHT NEXT to the pad? PuppyPad has something others don't... A patented scent in the pee pad that naturally attracts dogs to it. No hoping they'll figure it out. They just... use it. First time. Every time. Even the most stubborn dogs.",
        image: {
          src: '/assets/Attraction.webp',
          alt: 'Dog sniffing a reusable pee pad'
        }
      },
      {
        number: 2,
        title: 'It Lasts For Over A Year',
        body:
          "Imagine never having to buy pee pads again for a whole year... One pack of PuppyPads lasts well over a year and are easy to wash too. Just throw it in the washer or use a hose. The washing kills all the bacteria so there's never any smell."
      },
      {
        number: 3,
        title: 'It Holds Pee All Day Without Leaking',
        body:
          "You know how disposable pads turn into soggy messes after one accident? This holds 4 full pees thanks to Gravity Lock®. It creates a one way valve effect—pee can enter but can't escape out... even under pressure (Until you wash it where it gets destroyed) And unlike those disposables your dog shreds for fun, this one's tough. Even the most aggressive dogs can't rip it.",
        image: {
          src: '/assets/Product-IMG-3-Gray.webp',
          alt: 'Dog sitting on a PuppyPad'
        }
      },
      {
        number: 4,
        title: "There's No Smell & It Grips To The Floor",
        body:
          "You know that embarrassing pee smell when guests come over? PuppyPad has an antimicrobial layer that destroys any smell. And unlike disposables that slide around (dangerous for everyone), the anti-slip rubber dots lock this pad in place."
      },
      {
        number: 5,
        title: 'Try It Out For 90 Days',
        body:
          "Ready To Give PuppyPad A Try? If your dog doesn't use it or you're not completely happy... we offer a 90 day guarantee. And, if you order today you'll also get 3 free training gifts. Just know we're down to our last few hundred PuppyPads... and once they're gone, it's a 6-week wait.",
        image: {
          src: '/assets/reason5.webp',
          alt: 'Guarantee badge with PuppyPad'
        }
      }
    ],

    marquee: [
      'Limited Time Only',
      'Free Gifts',
      'Anti-Slip',
      'Fast Absorption',
      'No Training Required',
      'Reusable',

    ],

    pitch: {
      title: 'The Only Pee Pad That Requires No Training And Lasts Over A Year',
      bullets: [
        '**Patented Pheromone Infusion** That Attract Your Dogs To Pee On The PuppyPad',
        '**Replaces Over 1,000 Disposable Pads** - Just wash & reuse (saves $2000/year)',
        '**Absorbs In Less Than 5 Seconds** & Holds Up To 4 Pees With No Smell'
      ],
      image: {
        src: '/assets/reviews-preview.webp',
        alt: 'PuppyPad layers diagram'
      }
    },

    reviews: {
      autoAdvanceMs: 6500,
      slides: [
        {
          rating: 5,
          text: 'My puppy took to the pads like a duck to a pond, washing them is a breeze and my puppy just loves her pads',
          author: 'Charles',
          verified: true,
          images: [
            { src: '/assets/Attraction.webp', alt: 'Dog on PuppyPad' },
            { src: '/assets/Product-IMG-3-Gray.webp', alt: 'PuppyPad close up' },
            { src: '/assets/reason5.webp', alt: 'PuppyPad guarantee' }
          ]
        },
        {
          rating: 5,
          text: 'No smell, no leaks, and it stays put. Our dog figured it out almost immediately.',
          author: 'Morgan',
          verified: true,
          images: [
            { src: '/assets/Product-IMG-3-Gray.webp', alt: 'PuppyPad on floor' },
            { src: '/assets/Attraction.webp', alt: 'Dog using the pad' },
            { src: '/assets/reason5.webp', alt: 'Risk-free trial' }
          ]
        },
        {
          rating: 5,
          text: 'We replaced disposable pads completely. Washing is easy and the pad still looks brand new.',
          author: 'Jamie',
          verified: true,
          images: [
            { src: '/assets/reason5.webp', alt: 'PuppyPad product badge' },
            { src: '/assets/Product-IMG-3-Gray.webp', alt: 'Reusable PuppyPad' },
            { src: '/assets/Attraction.webp', alt: 'Dog near pad' }
          ]
        },
        {
          rating: 5,
          text: 'Perfect for apartments. It grips the floor and absorbs fast — total game changer.',
          author: 'Taylor',
          verified: true,
          images: [
            { src: '/assets/Attraction.webp', alt: 'Dog on pad' },
            { src: '/assets/reason5.webp', alt: 'Limited time offer' },
            { src: '/assets/Product-IMG-3-Gray.webp', alt: 'PuppyPad details' }
          ]
        }
      ]
    },

    reviewsWall: {
      title: 'Over 150,000 Potty Trained Dogs',
      buttonLabel: 'CLICK THE REVIEWS TO VIEW ↓',
      columns: [
        [
          {
            author: 'CJM',
            rating: 5,
            verified: true,
            text: 'I am new to PuppyPad and am so delighted to have found them!',
            image: { src: '/assets/reviews-preview.webp', alt: 'PuppyPad layers diagram' },
            imagePosition: 'bottom'
          },
          {
            author: 'David Yarbrough',
            rating: 5,
            verified: true,
            text:
              "Product is as described – was delivered on time – and is great quality. I've had similar products and this one is easily my favorite.",
            image: { src: '/assets/Product-IMG-3-Gray.webp', alt: 'Dog on PuppyPad' },
            imagePosition: 'top'
          }
        ],
        [
          {
            author: 'Kathleen Parker',
            rating: 5,
            verified: true,
            text: "One of the best things I've done – I love them.",
            image: { src: '/assets/Attraction.webp', alt: 'Dog using PuppyPad' },
            imagePosition: 'bottom'
          },
          {
            author: 'Jayni Satter',
            rating: 5,
            verified: true,
            text:
              "These pads are great. No more accidents. I actually lay them in a washer pan… Buy them, you won't be disappointed!",
            image: { src: '/assets/Attraction.webp', alt: 'PuppyPad close up' },
            imagePosition: 'top'
          }
        ],
        [
          {
            author: 'Darlene Robichaud',
            rating: 5,
            verified: true,
            text: 'Love them. They wash easily and the dogs use them right away.',
            image: { src: '/assets/Product-IMG-3-Gray.webp', alt: 'Dog on PuppyPad' },
            imagePosition: 'bottom'
          },
          {
            author: 'Judy Richardson',
            rating: 5,
            verified: true,
            text: "They are marvelous, and wonderful. I have 3 inside babies, won't go out at night.",
            image: { src: '/assets/Attraction.webp', alt: 'Dog on pad' },
            imagePosition: 'top'
          }
        ]
      ]
    },

    footer: {
      logo: {
        src: '/assets/puppypad-logo.svg',
        alt: 'PuppyPad'
      }
    },

    floatingCta: {
      label: 'SHOP NOW',
      href: 'https://shop.puppypad.co/listicle/pdp/ww',
      showAfterId: 'listicle-end'
    }
  }
}
