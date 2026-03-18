import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { resolveRuntimePagePath, useFunnelRuntime } from '@/funnels/puckConfig'
import { navigationClickEventForStages, resolvePublicFunnelStage } from '@/lib/funnelTracking'
import { ArrowRightIcon } from '../Icons/ArrowRightIcon'
import styles from './Button.module.css'

type ButtonSize = 'lg' | 'sm'

type Props = {
  linkType?: 'external' | 'funnelPage' | 'nextPage'
  href?: string
  targetPageId?: string
  children: ReactNode
  size?: ButtonSize
  className?: string
}

function resolveButtonHref({
  linkType,
  href,
  targetPageId,
  runtime
}: {
  linkType?: Props['linkType']
  href?: string
  targetPageId?: string
  runtime: ReturnType<typeof useFunnelRuntime>
}) {
  const resolvedLinkType = linkType ?? (href ? 'external' : undefined)
  if (!resolvedLinkType) {
    throw new Error('Button linkType is required when no href is provided.')
  }

  if (resolvedLinkType === 'external') {
    if (!href) {
      throw new Error('Button href is required for external links.')
    }
    return { href, isInternal: false }
  }

  if (!runtime) {
    throw new Error('Funnel runtime is required to resolve internal links.')
  }
  if (!runtime.funnelSlug) {
    throw new Error('Funnel runtime is missing a funnel slug.')
  }

  const resolvedTargetPageId =
    resolvedLinkType === 'nextPage' ? runtime.nextPageId ?? null : targetPageId ?? null

  if (!resolvedTargetPageId) {
    throw new Error('Target page id is required to resolve internal links.')
  }

  const slug = runtime.pageMap[resolvedTargetPageId]
  if (!slug) {
    throw new Error('Target page is not available in this funnel.')
  }

  return { href: resolveRuntimePagePath(runtime, slug), isInternal: true }
}

export function Button({ linkType, href, targetPageId, children, size = 'lg', className }: Props) {
  const runtime = useFunnelRuntime()
  const { href: resolvedHref, isInternal } = resolveButtonHref({ linkType, href, targetPageId, runtime })
  const targetSlug = isInternal ? resolvedHref.split('/').pop() ?? '' : resolvedHref
  const targetStage =
    isInternal && targetPageId && runtime?.pageStageMap[targetPageId]
      ? runtime.pageStageMap[targetPageId]
      : resolvePublicFunnelStage(targetSlug)
  const clickEvent = navigationClickEventForStages({
    fromStage: runtime?.pageStage ?? 'custom',
    toStage: targetStage,
    props: {
      ...(targetPageId ? { targetPageId } : {}),
      ...(href ? { href } : {})
    }
  })

  const content = (
    <span className={styles.inner}>
      <span className={styles.label}>{children}</span>
      <span className={styles.circle} aria-hidden="true">
        <ArrowRightIcon className={styles.icon} />
      </span>
    </span>
  )

  if (isInternal) {
    return (
      <Link
        className={`${styles.shell} ${styles[size]} ${className ?? ''}`}
        to={resolvedHref}
        onClick={() => runtime?.trackEvent?.(clickEvent)}
      >
        {content}
      </Link>
    )
  }

  return (
    <a
      className={`${styles.shell} ${styles[size]} ${className ?? ''}`}
      href={resolvedHref}
      onClick={() => runtime?.trackEvent?.(clickEvent)}
    >
      {content}
    </a>
  )
}
