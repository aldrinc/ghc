import { useEffect, useMemo, useRef, useState } from 'react'
import { Container } from '../../components/Container/Container'
import { Marquee } from '../../components/Marquee/Marquee'
import { Modal } from '../../components/Modal/Modal'
import type { UiCopy } from '../../site/types'
import type {
  ColorOption,
  OfferOption,
  PdpConfig,
  SizeOption,
  VideoItem,
} from './types'
import styles from './pdpPage.module.css'

type Props = {
  config: PdpConfig
  copy: UiCopy
}

function clampIndex(next: number, length: number) {
  if (length <= 0) return 0
  if (next < 0) return length - 1
  if (next >= length) return 0
  return next
}

function currency(n: number) {
  return `$${Math.round(n)}`
}

function isRuleMatch(
  rules: Array<{ sizeId: string; colorId: string }> | undefined,
  sizeId: string,
  colorId: string
) {
  if (!rules?.length) return false
  return rules.some((r) => r.sizeId === sizeId && r.colorId === colorId)
}

function IconPlus({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function IconDiamondStar({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M12 2l2.8 5.8 5.8 2.2-5.8 2.2L12 18l-2.8-5.8L3.4 10l5.8-2.2L12 2z"
        fill="currentColor"
      />
    </svg>
  )
}

function IconMinus({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path d="M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function IconCheck({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M20 6L9 17l-5-5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconChevron({ dir }: { dir: 'left' | 'right' }) {
  const d = dir === 'left' ? 'M14 6l-6 6 6 6' : 'M10 6l6 6-6 6'
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path d={d} stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function IconPlayTriangle({ size = 10 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path d="M9 7l10 5-10 5V7z" fill="currentColor" />
    </svg>
  )
}

function IconArrowRight({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path
        d="M5 12h12"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M13 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconScrollIndicator({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M12 3v18"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M8 7l4-4 4 4"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 17l4 4 4-4"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconWarning({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="#ff3b30" />
      <path d="M12 7v7" stroke="#ffffff" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="12" cy="17.5" r="1.3" fill="#ffffff" />
    </svg>
  )
}

function IconClose({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M18 6L6 18"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M6 6l12 12"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function StarRow({ rating, ariaLabel }: { rating: number; ariaLabel: string }) {
  const stars = Array.from({ length: 5 }).map((_, i) => i < rating)
  return (
    <span className={styles.stars} aria-label={ariaLabel}>
      {stars.map((on, i) => (
        <svg
          key={i}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill={on ? '#f59e0b' : 'rgba(245,158,11,0.25)'}
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path d="M12 17.3l-5.5 3 1-6.1L3 9.8l6.2-.9L12 3.3l2.8 5.6 6.2.9-4.5 4.4 1 6.1-5.7-3z" />
        </svg>
      ))}
    </span>
  )
}

function HeaderBar({
  config,
  visible,
  activeSectionId,
}: {
  config: PdpConfig['hero']['header']
  visible: boolean
  activeSectionId?: string | null
}) {
  return (
    <div className={styles.header} aria-hidden={!visible}>
      <Container>
        <div className={`${styles.headerInner} ${visible ? styles.headerVisible : styles.headerHidden}`}>
          <a className={styles.logo} href={config.logo.href ?? '#top'}>
            <img className={styles.logoImg} src={config.logo.src} alt={config.logo.alt} />
          </a>

          <nav className={styles.nav} aria-label="Primary">
            {config.nav.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className={activeSectionId && item.href === `#${activeSectionId}` ? styles.navLinkActive : undefined}
              >
                {item.label}
              </a>
            ))}
          </nav>

          <a className={styles.headerCta} href={config.cta.href}>
            {config.cta.label}
            <span className={styles.headerCtaIcon} aria-hidden="true">
              <IconArrowRight size={14} />
            </span>
          </a>
        </div>
      </Container>
    </div>
  )
}

function Gallery({
  slides,
  watchLabel,
  freeGifts,
  onFreeGiftsClick,
}: {
  slides: PdpConfig['hero']['gallery']['slides']
  watchLabel: string
  freeGifts?: PdpConfig['hero']['gallery']['freeGifts']
  onFreeGiftsClick?: () => void
}) {
  const [index, setIndex] = useState(0)
  const active = slides[index]

  return (
    <div className={styles.galleryCard}>
      <div className={styles.galleryMain}>
        <img src={active.src} alt={active.alt} />

        {freeGifts ? (
          <button
            type="button"
            className={styles.giftOverlay}
            onClick={onFreeGiftsClick}
            aria-label={freeGifts.ctaLabel}
          >
            <img
              className={styles.giftOverlayIcon}
              src={freeGifts.icon.src}
              alt={freeGifts.icon.alt}
            />
            <div className={styles.giftOverlayText}>
              <p className={styles.giftOverlayTitle}>{freeGifts.title}</p>
              <p className={styles.giftOverlayBody}>{freeGifts.body}</p>
            </div>
          </button>
        ) : null}

        <button type="button" className={styles.watchButton}>
          {watchLabel}
          <span className={styles.watchPlay} aria-hidden="true">
            <IconPlayTriangle size={10} />
          </span>
        </button>
      </div>

      <div className={styles.galleryControls}>
        <button
          type="button"
          className={styles.circleIconBtn}
          onClick={() => setIndex((v) => clampIndex(v - 1, slides.length))}
          aria-label="Previous image"
        >
          <IconChevron dir="left" />
        </button>
        <span className={styles.galleryCounter}>
          {index + 1} / {slides.length}
        </span>
        <button
          type="button"
          className={styles.circleIconBtn}
          onClick={() => setIndex((v) => clampIndex(v + 1, slides.length))}
          aria-label="Next image"
        >
          <IconChevron dir="right" />
        </button>
      </div>

      <div className={styles.thumbRow} role="tablist" aria-label="Image thumbnails">
        {slides.map((s, i) => (
          <button
            key={s.src + i}
            type="button"
            className={`${styles.thumb} ${i === index ? styles.thumbSelected : ''}`}
            onClick={() => setIndex(i)}
            aria-label={`View image ${i + 1}`}
          >
            <img src={s.thumbSrc ?? s.src} alt={s.alt} />
          </button>
        ))}
      </div>
    </div>
  )
}

function SizeCard({
  option,
  selected,
  onClick,
}: {
  option: SizeOption
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={`${styles.optionCard} ${styles.sizeCard} ${selected ? styles.optionCardSelected : ''}`}
      onClick={onClick}
      aria-pressed={selected}
    >
      {selected ? (
        <span className={styles.selectedCheck} aria-hidden="true">
          <span
            style={{
              display: 'grid',
              placeItems: 'center',
              width: 18,
              height: 18,
              borderRadius: 999,
              background: '#1f8f2e',
              color: '#ffffff',
            }}
          >
            <IconCheck size={14} />
          </span>
        </span>
      ) : null}
      <p className={styles.optionLabel}>{option.label}</p>
      <p className={styles.optionMeta}>
        {option.sizeIn}
        <br />
        {option.sizeCm}
      </p>
    </button>
  )
}

function OfferCard({
  option,
  selected,
  onClick,
}: {
  option: OfferOption
  selected: boolean
  onClick: () => void
}) {
  const hasSave = Boolean(option.saveLabel)

  return (
    <button
      type="button"
      className={`${styles.optionCard} ${styles.offerCard} ${hasSave ? styles.offerCardHasSave : ''} ${
        selected ? styles.optionCardSelected : ''
      }`}
      onClick={onClick}
      aria-pressed={selected}
    >
      {selected ? (
        <span className={styles.selectedCheck} aria-hidden="true">
          <span
            style={{
              display: 'grid',
              placeItems: 'center',
              width: 18,
              height: 18,
              borderRadius: 999,
              background: '#1f8f2e',
              color: '#ffffff',
            }}
          >
            <IconCheck size={14} />
          </span>
        </span>
      ) : null}

      <img className={styles.offerCardImage} src={option.image.src} alt={option.image.alt} />
      <p className={styles.offerLabel}>{option.title}</p>
      <div className={styles.price}>
        {typeof option.compareAt === 'number' && option.compareAt > option.price ? (
          <span className={styles.compareAt}>{currency(option.compareAt)}</span>
        ) : null}
        {currency(option.price)}
      </div>
      {option.saveLabel ? <div className={styles.saveBar}>{option.saveLabel}</div> : null}
    </button>
  )
}

function ColorSwatch({
  option,
  selected,
  onClick,
}: {
  option: ColorOption
  selected: boolean
  onClick: () => void
}) {
  const background = option.swatch ? option.swatch : undefined

  return (
    <button type="button" className={styles.swatchBtn} onClick={onClick} aria-pressed={selected}>
      <div
        className={`${styles.swatchCircle} ${selected ? styles.swatchCircleSelected : ''}`}
        style={background ? { background } : undefined}
      >
        {option.swatchImageSrc ? (
          <img src={option.swatchImageSrc} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : null}
        {selected ? (
          <span className={styles.selectedCheck} aria-hidden="true">
            <span
              style={{
                display: 'grid',
                placeItems: 'center',
                width: 18,
                height: 18,
                borderRadius: 999,
                background: '#1f8f2e',
                color: '#ffffff',
              }}
            >
              <IconCheck size={14} />
            </span>
          </span>
        ) : null}
      </div>
      <div className={styles.swatchLabel}>{option.label}</div>
    </button>
  )
}

function VideoGrid({ videos }: { videos: VideoItem[] }) {
  return (
    <div className={styles.videoGrid}>
      {videos.map((v) => (
        <div key={v.id} className={styles.videoCard}>
          <img src={v.thumbnail.src} alt={v.thumbnail.alt} />
          <div className={styles.videoPlay} aria-hidden="true">
            <IconPlayTriangle size={14} />
          </div>
        </div>
      ))}
    </div>
  )
}

export function PdpPage({ config, copy }: Props) {
  const sizeOptions = config.hero.purchase.size.options
  const colorOptions = config.hero.purchase.color.options
  const offerOptions = config.hero.purchase.offer.options
  const navSectionIds = useMemo(
    () =>
      config.hero.header.nav
        .map((item) => item.href)
        .filter((href) => href.startsWith('#'))
        .map((href) => href.slice(1)),
    [config.hero.header.nav]
  )

  const [selectedSize, setSelectedSize] = useState(sizeOptions[1]?.id ?? sizeOptions[0]?.id)
  const [selectedColor, setSelectedColor] = useState(colorOptions[0]?.id)
  const [selectedOffer, setSelectedOffer] = useState(offerOptions[1]?.id ?? offerOptions[0]?.id)
  const [activeSection, setActiveSection] = useState<string | null>(navSectionIds[0] ?? null)

  const [openPillIndex, setOpenPillIndex] = useState<number | null>(null)
  const [isPillDragging, setIsPillDragging] = useState(false)
  const pillViewportRef = useRef<HTMLDivElement | null>(null)
  const manualScrollPanelRef = useRef<HTMLDivElement | null>(null)
  const sectionRatioRef = useRef<Map<string, number>>(new Map())
  const pillDragState = useRef({
    pointerDown: false,
    dragging: false,
    startX: 0,
    startY: 0,
    scrollLeft: 0,
    wasDragged: false,
  })

  const [openSizeChart, setOpenSizeChart] = useState(false)
  const [openWhyBundle, setOpenWhyBundle] = useState(false)
  const [openFreeGifts, setOpenFreeGifts] = useState(false)

  const [showHeader, setShowHeader] = useState(false)

  useEffect(() => {
    const onScroll = () => {
      setShowHeader(window.scrollY > 180)
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!navSectionIds.length) return
    const targets = navSectionIds
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => Boolean(el))
    if (!targets.length) return

    const ratios = sectionRatioRef.current
    ratios.clear()
    targets.forEach((target) => ratios.set(target.id, 0))

    const observer = new IntersectionObserver(
      (entries) => {
        let changed = false
        entries.forEach((entry) => {
          if (!entry.target.id) return
          ratios.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0)
          changed = true
        })
        if (!changed) return
        let bestId: string | null = null
        let bestRatio = 0
        ratios.forEach((ratio, id) => {
          if (ratio > bestRatio) {
            bestRatio = ratio
            bestId = id
          }
        })
        if (bestId) {
          setActiveSection((prev) => (prev === bestId ? prev : bestId))
        }
      },
      {
        threshold: [0, 0.15, 0.3, 0.5, 0.7, 1],
        rootMargin: '-25% 0px -55% 0px',
      }
    )

    targets.forEach((target) => observer.observe(target))

    return () => observer.disconnect()
  }, [navSectionIds])

  useEffect(() => {
    const panel = manualScrollPanelRef.current
    if (!panel) return

    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (media.matches) return

    let rafId = 0
    let lastTime = 0
    let paused = false

    const step = (time: number) => {
      if (!lastTime) lastTime = time
      const delta = time - lastTime
      lastTime = time

      if (!paused) {
        const maxScroll = panel.scrollHeight - panel.clientHeight
        if (maxScroll > 0) {
          panel.scrollTop += delta * 0.015
          if (panel.scrollTop >= maxScroll) {
            panel.scrollTop = 0
          }
        }
      }

      rafId = window.requestAnimationFrame(step)
    }

    const pause = () => {
      paused = true
    }

    const resume = () => {
      paused = false
      lastTime = 0
    }

    panel.addEventListener('pointerenter', pause)
    panel.addEventListener('pointerleave', resume)
    panel.addEventListener('focusin', pause)
    panel.addEventListener('focusout', resume)
    panel.addEventListener('pointerdown', pause)
    panel.addEventListener('pointerup', resume)

    rafId = window.requestAnimationFrame(step)

    return () => {
      window.cancelAnimationFrame(rafId)
      panel.removeEventListener('pointerenter', pause)
      panel.removeEventListener('pointerleave', resume)
      panel.removeEventListener('focusin', pause)
      panel.removeEventListener('focusout', resume)
      panel.removeEventListener('pointerdown', pause)
      panel.removeEventListener('pointerup', resume)
    }
  }, [])

  const selectedSizeObj = useMemo(
    () => sizeOptions.find((o) => o.id === selectedSize) ?? sizeOptions[0],
    [sizeOptions, selectedSize]
  )
  const selectedColorObj = useMemo(
    () => colorOptions.find((o) => o.id === selectedColor) ?? colorOptions[0],
    [colorOptions, selectedColor]
  )
  const selectedOfferObj = useMemo(
    () => offerOptions.find((o) => o.id === selectedOffer) ?? offerOptions[0],
    [offerOptions, selectedOffer]
  )
  const guaranteeImages = useMemo(() => {
    const tiles = config.reviewWall?.tiles?.map((t) => t.image) ?? []
    if (tiles.length) return tiles
    return [config.guarantee.right.image]
  }, [config.guarantee.right.image, config.reviewWall])

  const guaranteeFeedColumns = useMemo(() => {
    const left: typeof guaranteeImages = []
    const right: typeof guaranteeImages = []

    guaranteeImages.forEach((img, idx) => {
      ;(idx % 2 === 0 ? left : right).push(img)
    })

    return { left, right }
  }, [guaranteeImages])

  const showOutOfStock = isRuleMatch(config.hero.purchase.outOfStock, selectedSize, selectedColor)
  const showShippingDelay = isRuleMatch(config.hero.purchase.shippingDelay, selectedSize, selectedColor)

  const ctaLabel = config.hero.purchase.cta.labelTemplate.replace('{price}', currency(selectedOfferObj.price))
  const urgencyMessage = config.hero.purchase.cta.urgency.message
  const urgencyHighlight = 'Order now before we run out again.'
  const urgencyHighlightIndex = urgencyMessage.indexOf(urgencyHighlight)
  const urgencyLead =
    urgencyHighlightIndex >= 0 ? urgencyMessage.slice(0, urgencyHighlightIndex) : urgencyMessage
  const urgencyTail =
    urgencyHighlightIndex >= 0
      ? urgencyMessage.slice(urgencyHighlightIndex + urgencyHighlight.length)
      : ''

  const handlePillPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    const viewport = pillViewportRef.current
    if (!viewport) return
    pillDragState.current.pointerDown = true
    pillDragState.current.dragging = false
    pillDragState.current.wasDragged = false
    pillDragState.current.startX = event.clientX
    pillDragState.current.startY = event.clientY
    pillDragState.current.scrollLeft = viewport.scrollLeft
  }

  const handlePillPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = pillDragState.current
    if (!state.pointerDown) return
    const viewport = pillViewportRef.current
    if (!viewport) return
    const deltaX = event.clientX - state.startX
    const deltaY = event.clientY - state.startY
    if (!state.dragging) {
      if (Math.abs(deltaX) < 6 || Math.abs(deltaX) < Math.abs(deltaY)) return
      state.dragging = true
      state.wasDragged = true
      setIsPillDragging(true)
      viewport.setPointerCapture(event.pointerId)
    }
    viewport.scrollLeft = state.scrollLeft - deltaX
  }

  const handlePillPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = pillDragState.current
    if (!state.pointerDown) return
    const viewport = pillViewportRef.current
    if (state.dragging && viewport?.hasPointerCapture(event.pointerId)) {
      viewport.releasePointerCapture(event.pointerId)
    }
    state.pointerDown = false
    state.dragging = false
    setIsPillDragging(false)
    if (state.wasDragged) {
      window.setTimeout(() => {
        state.wasDragged = false
      }, 0)
    }
  }

  const handlePillClick = (idx: number) => {
    if (pillDragState.current.wasDragged) return
    setOpenPillIndex(idx)
  }

  return (
    <div className={styles.page} id="top">
      <HeaderBar config={config.hero.header} visible={showHeader} activeSectionId={activeSection} />

      {/* HERO */}
      <section className={`${styles.sectionPeach} ${styles.heroSection}`}>
        <Container>
          <div className={styles.heroGrid}>
            <div>
              <Gallery
                slides={config.hero.gallery.slides}
                watchLabel={config.hero.gallery.watchInAction.label}
                freeGifts={config.hero.gallery.freeGifts}
                onFreeGiftsClick={() => setOpenFreeGifts(true)}
              />
            </div>

            <div>
              {/*
                Auto-sliding FAQ pills (marquee-style)
                - Continuously scrolls horizontally like the marquee band.
                - Pauses on hover/focus and when an answer is open.
                - Clicking a pill always opens the answer panel.
              */}
              <div
                className={`${styles.pillMarquee} ${openPillIndex !== null ? styles.pillMarqueePaused : ''} ${
                  isPillDragging ? styles.pillMarqueeDragging : ''
                }`}
                aria-label="Quick questions"
              >
                <div
                  className={styles.pillMarqueeViewport}
                  ref={pillViewportRef}
                  onPointerDown={handlePillPointerDown}
                  onPointerMove={handlePillPointerMove}
                  onPointerUp={handlePillPointerUp}
                  onPointerCancel={handlePillPointerUp}
                >
                  <div className={styles.pillMarqueeTrack}>
                    {/* Primary group */}
                    <div className={styles.pillGroup}>
                      {config.hero.purchase.faqPills.map((p, idx) => {
                        const active = openPillIndex === idx
                        return (
                          <button
                            key={`pill-a-${p.label}-${idx}`}
                            type="button"
                            className={`${styles.pill} ${active ? styles.pillActive : ''}`}
                            onClick={() => handlePillClick(idx)}
                            aria-pressed={active}
                          >
                            <IconDiamondStar size={14} />
                            {p.label}
                          </button>
                        )
                      })}
                    </div>

                    {/* Duplicate group for seamless looping */}
                    <div className={styles.pillGroup} aria-hidden="true">
                      {config.hero.purchase.faqPills.map((p, idx) => {
                        const active = openPillIndex === idx
                        return (
                          <button
                            key={`pill-b-${p.label}-${idx}`}
                            type="button"
                            className={`${styles.pill} ${active ? styles.pillActive : ''}`}
                            onClick={() => handlePillClick(idx)}
                            aria-pressed={active}
                            tabIndex={-1}
                          >
                            <IconDiamondStar size={14} />
                            {p.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>

              {openPillIndex !== null ? (
                <div className={styles.pillAnswer}>
                  <div className={styles.pillAnswerHeader}>
                    <h3 className={styles.pillAnswerTitle}>
                      {config.hero.purchase.faqPills[openPillIndex]?.label}
                    </h3>
                    <button
                      type="button"
                      className={styles.pillAnswerClose}
                      onClick={() => setOpenPillIndex(null)}
                      aria-label="Close"
                    >
                      <IconClose size={18} />
                    </button>
                  </div>
                  <p className={styles.pillAnswerBody}>
                    {config.hero.purchase.faqPills[openPillIndex]?.answer}
                  </p>
                </div>
              ) : null}

              <h1 className={styles.h1}>{config.hero.purchase.title}</h1>

              <div className={styles.benefitsGrid}>
                {config.hero.purchase.benefits.map((b) => (
                  <div key={b.text} className={styles.benefit}>
                    <span className={styles.checkCircle} aria-hidden="true">
                      <IconCheck size={16} />
                    </span>
                    {b.text}
                  </div>
                ))}
              </div>

              <div className={styles.divider} />

              {/* Size */}
              <div>
                <div className={styles.sectionTitleRow}>
                  <div className={styles.stepTitle}>
                    {config.hero.purchase.size.title} <span>{selectedSizeObj?.label}</span>
                  </div>
                  <button type="button" className={styles.helpLink} onClick={() => setOpenSizeChart(true)}>
                    {config.hero.purchase.size.helpLinkLabel}
                  </button>
                </div>

                <div className={styles.optionGrid3}>
                  {sizeOptions.map((o) => (
                    <SizeCard
                      key={o.id}
                      option={o}
                      selected={o.id === selectedSize}
                      onClick={() => setSelectedSize(o.id)}
                    />
                  ))}
                </div>

                {showShippingDelay ? (
                  <div className={styles.delayBar}>
                    <span aria-hidden="true">⚠️</span>
                    <span className={styles.delayText}>{config.hero.purchase.size.shippingDelayLabel}</span>
                  </div>
                ) : null}
              </div>

              <div className={styles.divider} />

              {/* Color */}
              <div>
                <div className={styles.sectionTitleRow}>
                  <div className={styles.stepTitle}>
                    {config.hero.purchase.color.title} <span>{selectedColorObj?.label}</span>
                  </div>
                </div>
                <div className={styles.colorRow}>
                  {colorOptions.map((c) => (
                    <ColorSwatch
                      key={c.id}
                      option={c}
                      selected={c.id === selectedColor}
                      onClick={() => setSelectedColor(c.id)}
                    />
                  ))}
                </div>

                {showOutOfStock ? (
                  <div className={styles.stockNotice}>
                    <div style={{ fontWeight: 900, marginBottom: 6 }}>{config.hero.purchase.color.outOfStockTitle}</div>
                    <div style={{ color: 'var(--color-muted)' }}>{config.hero.purchase.color.outOfStockBody}</div>
                  </div>
                ) : null}
              </div>

              <div className={styles.divider} />

              {/* Offer */}
              <div>
                <div className={styles.sectionTitleRow}>
                  <div className={styles.stepTitle}>
                    {config.hero.purchase.offer.title} <span>{selectedOfferObj?.title}</span>
                  </div>
                </div>
                <div className={styles.offerHelper}>
                  {config.hero.purchase.offer.helperText}{' '}
                  <button type="button" className={styles.seeWhy} onClick={() => setOpenWhyBundle(true)}>
                    {config.hero.purchase.offer.seeWhyLabel}
                  </button>
                </div>

                <div className={styles.optionGrid3}>
                  {offerOptions.map((o) => (
                    <OfferCard
                      key={o.id}
                      option={o}
                      selected={o.id === selectedOffer}
                      onClick={() => setSelectedOffer(o.id)}
                    />
                  ))}
                </div>

                <button type="button" className={styles.ctaButton}>
                  {ctaLabel}
                  <span className={styles.ctaIconCircle} aria-hidden="true">
                    <IconArrowRight size={14} />
                  </span>
                </button>

                <div className={styles.ctaSubBullets}>
                  {config.hero.purchase.cta.subBullets.map((t) => (
                    <span key={t}>
                      <span className={styles.checkCircle} aria-hidden="true">
                        <IconCheck size={12} />
                      </span>
                      {t}
                    </span>
                  ))}
                </div>

                <div className={styles.urgency}>
                <div className={styles.urgencyTop}>
                  <span className={styles.urgencyIcon} aria-hidden="true">
                    <IconWarning size={28} />
                  </span>
                  <div className={styles.urgencyMessage}>
                    {urgencyHighlightIndex >= 0 ? (
                      <>
                        {urgencyLead}
                        <strong>{urgencyHighlight}</strong>
                        {urgencyTail}
                      </>
                    ) : (
                      urgencyMessage
                    )}
                  </div>
                </div>
                  <div className={styles.urgencyRows}>
                    {config.hero.purchase.cta.urgency.rows.map((r) => (
                      <div
                        key={r.label}
                        className={`${styles.urgencyRow} ${
                          r.tone === 'highlight'
                            ? styles.urgencyRowHighlight
                            : r.tone === 'muted'
                              ? styles.urgencyRowMuted
                              : ''
                        }`}
                      >
                        <span>{r.label}</span>
                        <span>{r.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Container>
      </section>

      {/* VIDEOS */}
      <section className={`${styles.sectionBlue} ${styles.sectionPad}`}>
        <Container>
          <div style={{ textAlign: 'center' }}>
            <div className={styles.sectionBadge}>{config.videos.badge}</div>
            <h2 className={styles.sectionHeading}>{config.videos.title}</h2>
          </div>
          <VideoGrid videos={config.videos.videos} />
        </Container>
      </section>

      {/* MARQUEE */}
      <Marquee items={config.marquee.items} repeat={config.marquee.repeat} />

      {/* STORY: PROBLEM */}
      <section
        id={config.story.problem.id}
        className={`${config.story.problem.bg === 'blue' ? styles.sectionBlue : styles.sectionPeach} ${styles.sectionPad}`}
      >
        <Container>
          <div className={styles.storyGrid}>
            {config.story.problem.layout === 'textRight' ? (
              <>
                <img className={styles.storyImage} src={config.story.problem.image.src} alt={config.story.problem.image.alt} />
                <StoryText section={config.story.problem} />
              </>
            ) : (
              <>
                <StoryText section={config.story.problem} />
                <img className={styles.storyImage} src={config.story.problem.image.src} alt={config.story.problem.image.alt} />
              </>
            )}
          </div>
        </Container>
      </section>

      {/* STORY: SOLUTION */}
      <section
        id={config.story.solution.id}
        className={`${config.story.solution.bg === 'blue' ? styles.sectionBlue : styles.sectionPeach} ${styles.sectionPad} ${styles.solutionSection}`}
      >
        <Container>
          <div className={styles.storyGrid}>
            {config.story.solution.layout === 'textRight' ? (
              <>
                <img className={styles.storyImage} src={config.story.solution.image.src} alt={config.story.solution.image.alt} />
                <StoryText section={config.story.solution} />
              </>
            ) : (
              <>
                <StoryText section={config.story.solution} />
                <img className={styles.storyImage} src={config.story.solution.image.src} alt={config.story.solution.image.alt} />
              </>
            )}
          </div>

          <div className={styles.callout}>
            <div>
              <p className={styles.calloutTitle}>{config.story.solution.callout.leftTitle}</p>
              <p className={styles.calloutBody}>{config.story.solution.callout.leftBody}</p>
            </div>
            <div>
              <p className={styles.calloutTitle}>{config.story.solution.callout.rightTitle}</p>
              <p className={styles.calloutBody}>{config.story.solution.callout.rightBody}</p>
            </div>
          </div>
        </Container>
      </section>

      {/* COMPARISON */}
      <section id={config.comparison.id} className={`${styles.sectionPeach} ${styles.sectionPad}`}>
        <Container>
          <div style={{ textAlign: 'center' }}>
            <div className={styles.sectionBadge}>{config.comparison.badge}</div>
            <h2 className={styles.sectionHeading}>{config.comparison.title}</h2>
            <div className={styles.comparisonHint}>{config.comparison.swipeHint}</div>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th style={{ width: 240 }} />
                  <th>{config.comparison.columns.pup}</th>
                  <th>{config.comparison.columns.disposable}</th>
                </tr>
              </thead>
              <tbody>
                {config.comparison.rows.map((r) => (
                  <tr key={r.label}>
                    <td className={styles.tableLabel}>{r.label}</td>
                    <td>
                      <div className={styles.cell}>
                        <span className={`${styles.comparisonIcon} ${styles.comparisonIconGood}`} aria-hidden="true">
                          <IconCheck size={12} />
                        </span>
                        {r.pup}
                      </div>
                    </td>
                    <td>
                      <div className={styles.cell}>
                        <span className={`${styles.comparisonIcon} ${styles.comparisonIconBad}`} aria-hidden="true">
                          <IconClose size={12} />
                        </span>
                        {r.disposable}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Container>
      </section>

      {/* GUARANTEE */}
      <section
        id={config.guarantee.id}
        className={`${styles.sectionBlue} ${styles.sectionPad} ${styles.guaranteeSection}`}
      >
        <Container className={styles.guaranteeContainer}>
          <div className={styles.guaranteeGrid}>
            <div className={styles.guaranteeText}>
              <div className={styles.sectionBadge} style={{ marginLeft: 0 }}>
                {config.guarantee.badge}
              </div>
              <h2>{config.guarantee.title}</h2>
              {config.guarantee.paragraphs.map((p) => (
                <p key={p} className={p === 'No hoops. No hassles. No questions.' ? styles.guaranteeBold : undefined}>
                  {p}
                </p>
              ))}
              <div className={styles.whyTitle}>{config.guarantee.whyTitle}</div>
              <p>{config.guarantee.whyBody}</p>
              <p className={styles.guaranteeClosing}>{config.guarantee.closingLine}</p>
            </div>

            <div className={styles.manualScrollPanelWrap}>
              <div className={styles.manualScrollHint} aria-hidden="true">
                <IconScrollIndicator size={16} />
                {config.guarantee.right.commentThread.label}
              </div>

              <div
                className={styles.manualScrollPanel}
                aria-label="Customer image feed"
                tabIndex={0}
                ref={manualScrollPanelRef}
              >
                <div className={styles.manualScrollColumn}>
                  {guaranteeFeedColumns.left.map((img, idx) => (
                    <div key={`left-${img.src}-${idx}`} className={styles.imageTile}>
                      <img className={styles.panelImg} src={img.src} alt={img.alt} />
                    </div>
                  ))}
                </div>

                <div className={styles.manualScrollColumn}>
                  {guaranteeFeedColumns.right.map((img, idx) => (
                    <div key={`right-${img.src}-${idx}`} className={styles.imageTile}>
                      <img className={styles.panelImg} src={img.src} alt={img.alt} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Container>
      </section>

      {/* FAQ */}
      <section id={config.faq.id} className={`${styles.sectionPeach} ${styles.sectionPad}`}>
        <Container>
          <div className={styles.faqWrap}>
            <h2 className={styles.faqHeading}>{config.faq.title}</h2>
            <FaqAccordion items={config.faq.items} />
          </div>
        </Container>
      </section>

      {/* REVIEW WALL */}
      <section id={config.reviewWall.id} className={`${styles.sectionBlue} ${styles.sectionPad}`}>
        <Container>
          <div className={styles.reviewWallHeader}>
            <div className={styles.sectionBadge}>{config.reviewWall.badge}</div>
            <h2 className={styles.sectionHeading} style={{ marginBottom: 10 }}>
              {config.reviewWall.title}
            </h2>
            <div className={styles.ratingRow}>
              <img
                className={styles.ratingImage}
                src="https://cdn.shopify.com/s/files/1/0433/0510/7612/files/StarRating.svg?v=1754231046"
                alt="5 star rating"
              />
              {config.reviewWall.ratingLabel}
            </div>
          </div>

          <div className={styles.masonry}>
            {config.reviewWall.tiles.map((t) => (
              <div key={t.id} className={styles.tile}>
                <img src={t.image.src} alt={t.image.alt} />
              </div>
            ))}
          </div>

          <button type="button" className={styles.showMore}>
            {config.reviewWall.showMoreLabel}
          </button>
        </Container>
      </section>

      {/* FOOTER */}
      <footer className={`${styles.sectionPeach} ${styles.footer}`}>
        <Container>
          <img className={styles.footerLogo} src={config.footer.logo.src} alt={config.footer.logo.alt} />
          <div className={styles.footerText}>{config.footer.copyright}</div>
        </Container>
      </footer>

      {/* MODALS */}
      <Modal
        open={openSizeChart}
        onClose={() => setOpenSizeChart(false)}
        ariaLabel={config.modals.sizeChart.title}
        copy={copy.modal}
      >
        <h2 style={{ marginTop: 0 }}>{config.modals.sizeChart.title}</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', minWidth: 560, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid rgba(0,0,0,0.12)' }}>Size</th>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid rgba(0,0,0,0.12)' }}>Dimensions</th>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid rgba(0,0,0,0.12)' }}>Ideal for</th>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid rgba(0,0,0,0.12)' }}>Weight</th>
              </tr>
            </thead>
            <tbody>
              {config.modals.sizeChart.sizes.map((s) => (
                <tr key={s.label}>
                  <td style={{ padding: 10, borderBottom: '1px solid rgba(0,0,0,0.08)', fontWeight: 800 }}>{s.label}</td>
                  <td style={{ padding: 10, borderBottom: '1px solid rgba(0,0,0,0.08)' }}>{s.size}</td>
                  <td style={{ padding: 10, borderBottom: '1px solid rgba(0,0,0,0.08)' }}>{s.idealFor}</td>
                  <td style={{ padding: 10, borderBottom: '1px solid rgba(0,0,0,0.08)' }}>{s.weight}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ color: 'rgba(0,0,0,0.65)' }}>{config.modals.sizeChart.note}</p>
      </Modal>

      <Modal
        open={openWhyBundle}
        onClose={() => setOpenWhyBundle(false)}
        ariaLabel={config.modals.whyBundle.title}
        copy={copy.modal}
      >
        <h2 style={{ marginTop: 0 }}>{config.modals.whyBundle.title}</h2>
        <p style={{ color: 'rgba(0,0,0,0.7)' }}>{config.modals.whyBundle.body}</p>
        <div style={{ display: 'grid', gap: 12, marginTop: 14 }}>
          {config.modals.whyBundle.quotes.map((q, i) => (
            <div
              key={q.author + i}
              style={{
                border: '1px solid rgba(0,0,0,0.1)',
                borderRadius: 12,
                padding: 14,
                background: 'rgba(0,0,0,0.03)',
              }}
            >
              <div style={{ fontWeight: 800, marginBottom: 6 }}>&ldquo;{q.text}&rdquo;</div>
              <div style={{ color: 'rgba(0,0,0,0.65)' }}>— {q.author}</div>
            </div>
          ))}
        </div>
      </Modal>

      <Modal
        open={openFreeGifts}
        onClose={() => setOpenFreeGifts(false)}
        ariaLabel={config.modals.freeGifts.title}
        copy={copy.modal}
      >
        <h2 style={{ marginTop: 0 }}>{config.modals.freeGifts.title}</h2>
        <p style={{ color: 'rgba(0,0,0,0.7)' }}>{config.modals.freeGifts.body}</p>
      </Modal>
    </div>
  )
}

function StoryText({ section }: { section: PdpConfig['story']['problem'] }) {
  const isProblem = section.id === 'how-it-works'
  return (
    <div className={styles.storyText}>
      <div className={styles.sectionBadge} style={{ marginLeft: 0 }}>
        {section.badge}
      </div>
      <h2 className={styles.storyTitle}>{section.title}</h2>
      {section.paragraphs.map((p, idx) => (
        <p
          key={p}
          className={`${styles.storyPara} ${
            isProblem && (idx === 0 || idx === 2) ? styles.storyParaStrong : ''
          }`}
        >
          {p}
        </p>
      ))}
      {section.emphasisLine ? <div className={styles.storyEmphasis}>{section.emphasisLine}</div> : null}

      {section.bullets?.length ? (
        <div className={styles.bulletList}>
          {section.bullets.map((b) => (
            <div key={b.title} className={styles.bulletItem}>
              <span className={styles.checkCircle} aria-hidden="true" style={{ marginTop: 2 }}>
                <IconCheck size={16} />
              </span>
              <div>
                <span className={styles.bulletItemTitle}>{b.title} </span>
                <span className={styles.bulletItemBody}>{b.body}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function FaqAccordion({ items }: { items: Array<{ question: string; answer: string }> }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  return (
    <div>
      {items.map((it, idx) => {
        const open = openIndex === idx
        return (
          <div key={it.question} className={`${styles.faqCard} ${open ? styles.faqCardOpen : ''}`}>
            <div
              className={styles.faqItem}
              role="button"
              tabIndex={0}
              onClick={() => setOpenIndex(open ? null : idx)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setOpenIndex(open ? null : idx)
                }
              }}
              aria-expanded={open}
            >
              <div className={styles.faqQ}>{it.question}</div>
              <div aria-hidden="true" style={{ color: 'var(--color-brand)' }}>
                {open ? <IconMinus size={16} /> : <IconPlus size={16} />}
              </div>
            </div>
            <div className={`${styles.faqAnswer} ${open ? styles.faqAnswerOpen : ''}`}>
              <div className={styles.faqA}>{it.answer}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function ReviewSliderSection({ config }: { config: PdpConfig['reviewSlider'] }) {
  const [mode, setMode] = useState<'auto' | 'manual'>('auto')
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (mode !== 'auto') return
    const id = window.setInterval(() => {
      setIndex((v) => clampIndex(v + 1, config.slides.length))
    }, 3200)
    return () => window.clearInterval(id)
  }, [mode, config.slides.length])

  const active = config.slides[index]

  return (
    <section className={`${styles.sectionBlue} ${styles.sectionPad}`}>
      <Container>
        <div className={styles.reviewSliderHeader}>
          <h2>{config.title}</h2>
          <p>{config.body}</p>
          <div className={styles.toggle} role="tablist" aria-label="Review slideshow mode">
            <button
              type="button"
              className={mode === 'auto' ? styles.toggleActive : undefined}
              onClick={() => setMode('auto')}
            >
              {config.toggle.auto}
            </button>
            <button
              type="button"
              className={mode === 'manual' ? styles.toggleActive : undefined}
              onClick={() => setMode('manual')}
            >
              {config.toggle.manual}
            </button>
          </div>
        </div>

        <div className={styles.reviewSlide}>
          <img src={active.src} alt={active.alt} />
        </div>

        <div className={styles.reviewNav}>
          <button
            type="button"
            className={styles.circleIconBtn}
            onClick={() => setIndex((v) => clampIndex(v - 1, config.slides.length))}
            aria-label="Previous review"
          >
            <IconChevron dir="left" />
          </button>
          <span style={{ fontWeight: 800, color: 'var(--color-brand)' }}>{config.hint}</span>
          <button
            type="button"
            className={styles.circleIconBtn}
            onClick={() => setIndex((v) => clampIndex(v + 1, config.slides.length))}
            aria-label="Next review"
          >
            <IconChevron dir="right" />
          </button>
        </div>
      </Container>
    </section>
  )
}
