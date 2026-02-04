import { Footer } from '../../components/Footer/Footer'
import { FloatingCta } from '../../components/FloatingCta/FloatingCta'
import { Hero } from '../../components/Hero/Hero'
import { Marquee } from '../../components/Marquee/Marquee'
import { Pitch } from '../../components/Pitch/Pitch'
import { Reasons } from '../../components/Reasons/Reasons'
import { ReviewWall } from '../../components/ReviewWall/ReviewWall'
import { Reviews } from '../../components/Reviews/Reviews'
import { defaultListicleConfig } from './listicleConfig'
import type { ListicleConfig } from './types'
import type { UiCopy } from '../../site/types'
import { siteConfig } from '../../site/siteConfig'

type Props = {
  config?: ListicleConfig
  copy?: UiCopy
}

export function ListiclePage({ config = defaultListicleConfig, copy = siteConfig.copy }: Props) {
  return (
    <>
      <Hero title={config.hero.title} subtitle={config.hero.subtitle} media={config.hero.media} badges={config.badges} />

      <main>
        <Reasons reasons={config.reasons} />
        <Reviews reviews={config.reviews} copy={copy.reviews} starsAriaLabelTemplate={copy.common.starsAriaLabelTemplate} />
        <Marquee items={config.marquee} />
        <Pitch pitch={config.pitch} />
        <ReviewWall
          wall={config.reviewsWall}
          verifiedLabel={copy.reviewWall.verifiedLabel}
          starsAriaLabelTemplate={copy.common.starsAriaLabelTemplate}
          modalCopy={copy.modal}
        />
        <Footer footer={config.footer} />
      </main>

      <FloatingCta cta={config.floatingCta} />
    </>
  )
}
