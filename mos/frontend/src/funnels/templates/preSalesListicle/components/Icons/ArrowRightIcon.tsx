import type { SVGProps } from 'react'

export function ArrowRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" {...props}>
      <path
        d="M13.5 5.5a1 1 0 0 1 1.414 0l6 6a1 1 0 0 1 0 1.414l-6 6A1 1 0 1 1 13.5 17.5l4.293-4.293H4a1 1 0 1 1 0-2h13.793L13.5 6.914a1 1 0 0 1 0-1.414z"
        fill="currentColor"
      />
    </svg>
  )
}
