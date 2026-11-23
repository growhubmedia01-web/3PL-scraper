import { useEffect, useState } from 'react'
import { SERVICE, api } from './api'
import type { Taxonomy, UiLabels } from './types'

/** Defaults used until the taxonomy loads, or if it fails. */
export const DEFAULT_LABELS: UiLabels = {
  title: 'Distributor Buying Intelligence',
  segment: 'Segment',
  interest_types: {
    EXPLICITLY_SEEKING: 'Explicitly seeking',
    RECENTLY_ADDED: 'Recently added',
    CURRENTLY_CARRIED: 'Currently carried',
    INFERRED_FIT: 'Inferred fit',
  },
  no_product_demand_message: 'Specific product demand not publicly disclosed.',
}

// One request per page load, shared by every component.
let pending: Promise<Taxonomy> | null = null

export function useTaxonomy(): Taxonomy | null {
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null)
  useEffect(() => {
    let alive = true
    pending = pending || api.taxonomy(SERVICE)
    pending.then((t) => { if (alive) setTaxonomy(t) })
      .catch(() => { pending = null })
    return () => { alive = false }
  }, [])
  return taxonomy
}

export function useLabels(): UiLabels {
  const taxonomy = useTaxonomy()
  return taxonomy?.ui_labels ?? DEFAULT_LABELS
}
