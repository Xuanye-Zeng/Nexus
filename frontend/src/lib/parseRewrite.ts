/** Parser for the `bullet_rewriter` v8 output format.
 *
 *  Input shape (markdown emitted by the LLM):
 *
 *      ## PROJECTS
 *
 *      ### CloudScale Inventory Management System (Oct 2025 - Dec 2025)
 *      - BEFORE: Architected a fault-tolerant microservices system ...
 *      AFTER: Designed a scalable microservices architecture ...
 *      REASON: targets "build and maintain resilient distributed systems"
 *
 *      - BEFORE: Reduced read latency by 30% by implementing ...
 *      AFTER: KEEP
 *      REASON: ...
 *
 *      ## EXPERIENCE
 *      ...
 *
 *      ## SKILLS
 *      - Programming Languages: Python, Java, ...
 *
 *  We parse it into structured sections, where the bullets in PROJECTS and
 *  EXPERIENCE are BEFORE/AFTER/REASON triples (`AFTER: KEEP` means use the
 *  BEFORE text as-is). SKILLS / EDUCATION are passed through as raw lines.
 */

export interface BulletTriple {
  before: string
  after: string  // "KEEP" => use `before`; the resolved final text is in `final`
  final: string  // the line the user should actually paste — `after === 'KEEP' ? before : after`
  reason: string
  kept: boolean  // true when after === 'KEEP'
}

export interface RewrittenItem {
  /** Heading line under the section, e.g. "CloudScale Inventory ... (Oct 2025 - Dec 2025)". */
  heading: string
  bullets: BulletTriple[]
  /** Free-form lines that aren't part of a triple (used for SKILLS / EDUCATION). */
  raw_lines: string[]
}

export interface RewrittenSection {
  name: string                  // "PROJECTS" / "EXPERIENCE" / "EDUCATION" / "SKILLS" / ...
  items: RewrittenItem[]
  /** Top-level free text under the section header but before any ### item. */
  preamble: string[]
}

const SECTION_RE = /^##\s+([^\n]+)/
const ITEM_RE = /^###\s+([^\n]+)/
const BEFORE_RE = /^\s*-?\s*BEFORE:\s*(.+)$/i
const AFTER_RE = /^\s*AFTER:\s*(.+)$/i
const REASON_RE = /^\s*REASON:\s*(.+)$/i

export function parseRewrite(text: string): RewrittenSection[] {
  const lines = text.split('\n')

  const sections: RewrittenSection[] = []
  let currentSection: RewrittenSection | null = null
  let currentItem: RewrittenItem | null = null

  // Pending triple under construction
  let pending: Partial<BulletTriple> | null = null

  const flushPending = () => {
    if (pending && currentItem && pending.before) {
      const after = pending.after ?? ''
      const kept = after.trim().toUpperCase() === 'KEEP'
      currentItem.bullets.push({
        before: pending.before,
        after,
        final: kept ? pending.before : after,
        reason: pending.reason ?? '',
        kept,
      })
    }
    pending = null
  }

  for (const raw of lines) {
    const line = raw.trim()

    const sectionMatch = line.match(SECTION_RE)
    if (sectionMatch) {
      flushPending()
      currentItem = null
      currentSection = {
        name: sectionMatch[1].trim().toUpperCase(),
        items: [],
        preamble: [],
      }
      sections.push(currentSection)
      continue
    }

    if (!currentSection) continue

    const itemMatch = line.match(ITEM_RE)
    if (itemMatch) {
      flushPending()
      currentItem = { heading: itemMatch[1].trim(), bullets: [], raw_lines: [] }
      currentSection.items.push(currentItem)
      continue
    }

    const beforeMatch = line.match(BEFORE_RE)
    if (beforeMatch) {
      flushPending()
      pending = { before: beforeMatch[1].trim() }
      continue
    }

    const afterMatch = line.match(AFTER_RE)
    if (afterMatch && pending) {
      pending.after = afterMatch[1].trim()
      continue
    }

    const reasonMatch = line.match(REASON_RE)
    if (reasonMatch && pending) {
      pending.reason = reasonMatch[1].trim()
      continue
    }

    // Plain text inside a section (skills lines, education details, etc.)
    if (line.length === 0) continue
    if (currentItem) {
      currentItem.raw_lines.push(line)
    } else {
      currentSection.preamble.push(line)
    }
  }

  flushPending()
  return sections
}

/** Convenience: produce a copy-paste-ready plain-text resume from parsed sections. */
export function rewriteToPlainText(sections: RewrittenSection[]): string {
  const out: string[] = []
  for (const section of sections) {
    out.push(`## ${section.name}`)
    for (const line of section.preamble) out.push(line)
    for (const item of section.items) {
      out.push('')
      out.push(`### ${item.heading}`)
      for (const b of item.bullets) {
        out.push(`- ${b.final}`)
      }
      for (const r of item.raw_lines) out.push(r)
    }
    out.push('')
  }
  return out.join('\n').trim()
}
