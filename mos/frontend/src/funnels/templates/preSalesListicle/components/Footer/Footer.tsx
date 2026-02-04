import type { Footer as FooterType } from '../../types'
import { resolveImageSrc } from '../../utils/assetUtils'
import { Container } from '../Container/Container'
import styles from './Footer.module.css'

type Props = {
  footer: FooterType
}

export function Footer({ footer }: Props) {
  return (
    <footer className={styles.footer}>
      <Container>
        <div className={styles.inner}>
          <img
            className={styles.logo}
            src={resolveImageSrc(footer.logo)}
            alt={footer.logo.alt}
            loading="lazy"
            decoding="async"
          />
        </div>
      </Container>
    </footer>
  )
}
