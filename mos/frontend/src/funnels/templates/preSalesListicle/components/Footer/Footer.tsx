import type { Footer as FooterType } from '../../types'
import { useDesignSystemTokens } from '@/components/design-system/DesignSystemProvider'
import {
  resolveDesignSystemBrandLogoVariant,
  withDesignSystemBrandLogo,
} from '@/funnels/templates/shared/designSystemBrandLogo'
import { resolveImageSrc } from '../../utils/assetUtils'
import { Container } from '../Container/Container'
import { PaymentIconStrip } from '@/funnels/templates/shared/PaymentIconStrip'
import styles from './Footer.module.css'

type Props = {
  footer: FooterType
}

export function Footer({ footer }: Props) {
  const designSystemTokens = useDesignSystemTokens()
  const logoVariant = resolveDesignSystemBrandLogoVariant(footer.logoVariant, 'onDark')
  const resolvedLogo = withDesignSystemBrandLogo(designSystemTokens, footer.logo, logoVariant)
  const links = Array.isArray(footer.links) ? footer.links : []
  const paymentIcons = Array.isArray(footer.paymentIcons) ? footer.paymentIcons : []

  return (
    <footer className={styles.footer}>
      <Container>
        <div className={styles.inner}>
          <img
            className={styles.logo}
            src={resolveImageSrc(resolvedLogo)}
            alt={resolvedLogo.alt}
            loading="lazy"
            decoding="async"
          />
          {typeof footer.copyright === 'string' && footer.copyright.trim() ? (
            <div className={styles.copyright}>{footer.copyright.trim()}</div>
          ) : null}
          {links.length > 0 ? (
            <nav className={styles.links} aria-label="Policy links">
              {links.map((link) => (
                <a
                  key={`${link.label}-${link.href}`}
                  href={link.href}
                  className={styles.link}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {link.label}
                </a>
              ))}
            </nav>
          ) : null}
          {paymentIcons.length > 0 ? (
            <PaymentIconStrip iconKeys={paymentIcons} className={styles.paymentIcons} />
          ) : null}
        </div>
      </Container>
    </footer>
  )
}
