// Tiny markdown renderer scoped to AI assistant chat replies. Produces a safe
// HTML string by escaping input first, restricting URL schemes, and never
// inlining arbitrary attributes from the source. Intentionally narrow: handles
// headers, bold, italic, inline code, fenced code blocks, links, ordered and
// unordered lists, blockquotes and paragraphs. Anything else lands as text.

const SAFE_URL_PATTERN = /^(?:https?:\/\/|mailto:|#)/i

const HTML_ESCAPE_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

function escapeHtml(input: string): string {
  return input.replace(/[&<>"']/g, (char) => HTML_ESCAPE_MAP[char] ?? char)
}

function safeUrl(raw: string): string | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (!SAFE_URL_PATTERN.test(trimmed)) return null
  return escapeHtml(trimmed)
}

function renderInline(text: string): string {
  let out = escapeHtml(text)

  // Inline code (must run before bold/italic so `**a**` inside backticks stays literal).
  out = out.replace(/`([^`\n]+)`/g, (_match, code: string) => {
    return `<code class="rounded bg-theme-text/10 px-1 py-0.5 font-mono text-[0.85em] text-theme-text">${code}</code>`
  })

  // Links: [label](href). label is already escaped; href validated.
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label: string, href: string) => {
    const url = safeUrl(href)
    if (!url) return label
    return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="text-theme-primary underline underline-offset-2 hover:text-theme-primary/80">${label}</a>`
  })

  // Bold (**text**) before italic so `*` inside `**` is consumed.
  out = out.replace(/\*\*([^*\n]+)\*\*/g, '<strong class="font-semibold text-theme-text">$1</strong>')

  // Italic (*text*). Avoid matching `**` boundaries by using \b-style guard.
  out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em class="italic">$2</em>')

  return out
}

type Block =
  | { kind: 'paragraph', lines: string[] }
  | { kind: 'heading', level: number, text: string }
  | { kind: 'code', language: string, body: string }
  | { kind: 'ul', items: string[] }
  | { kind: 'ol', items: string[] }
  | { kind: 'quote', lines: string[] }
  | { kind: 'hr' }

function tokenize(input: string): Block[] {
  const lines = input.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    // Fenced code block.
    if (/^```/.test(line)) {
      const language = line.slice(3).trim()
      const bodyLines: string[] = []
      index += 1
      while (index < lines.length && !/^```/.test(lines[index])) {
        bodyLines.push(lines[index])
        index += 1
      }
      // Skip the closing fence if present.
      if (index < lines.length) index += 1
      blocks.push({ kind: 'code', language, body: bodyLines.join('\n') })
      continue
    }

    // Heading.
    const headingMatch = line.match(/^(#{1,4})\s+(.+?)\s*#*\s*$/)
    if (headingMatch) {
      blocks.push({ kind: 'heading', level: headingMatch[1].length, text: headingMatch[2] })
      index += 1
      continue
    }

    // Horizontal rule.
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push({ kind: 'hr' })
      index += 1
      continue
    }

    // Blockquote.
    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = []
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^>\s?/, ''))
        index += 1
      }
      blocks.push({ kind: 'quote', lines: quoteLines })
      continue
    }

    // Unordered list.
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ''))
        index += 1
      }
      blocks.push({ kind: 'ul', items })
      continue
    }

    // Ordered list.
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ''))
        index += 1
      }
      blocks.push({ kind: 'ol', items })
      continue
    }

    // Blank line — paragraph separator.
    if (line.trim() === '') {
      index += 1
      continue
    }

    // Paragraph: collect contiguous non-blank lines that are not the start of
    // another block kind.
    const paragraphLines: string[] = []
    while (
      index < lines.length
      && lines[index].trim() !== ''
      && !/^```/.test(lines[index])
      && !/^(#{1,4})\s+/.test(lines[index])
      && !/^>\s?/.test(lines[index])
      && !/^\s*[-*]\s+/.test(lines[index])
      && !/^\s*\d+\.\s+/.test(lines[index])
      && !/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(lines[index])
    ) {
      paragraphLines.push(lines[index])
      index += 1
    }
    if (paragraphLines.length > 0) blocks.push({ kind: 'paragraph', lines: paragraphLines })
  }

  return blocks
}

function renderBlock(block: Block): string {
  switch (block.kind) {
    case 'heading': {
      const tag = `h${Math.min(Math.max(block.level + 1, 2), 5)}`
      const sizeClass = block.level === 1
        ? 'text-base font-bold'
        : block.level === 2
          ? 'text-sm font-semibold'
          : 'text-xs font-semibold uppercase tracking-wide'
      return `<${tag} class="${sizeClass} text-theme-text mt-2 mb-1">${renderInline(block.text)}</${tag}>`
    }
    case 'code': {
      const langLabel = block.language
        ? `<span class="block text-[10px] uppercase tracking-wider text-theme-text-muted mb-1">${escapeHtml(block.language)}</span>`
        : ''
      return `<pre class="my-2 rounded-md border border-theme-border bg-theme-bg/80 p-2 overflow-x-auto"><code class="font-mono text-[0.78rem] leading-snug text-theme-text whitespace-pre">${langLabel}${escapeHtml(block.body)}</code></pre>`
    }
    case 'ul': {
      const items = block.items.map((item) => `<li class="ml-4 list-disc">${renderInline(item)}</li>`).join('')
      return `<ul class="my-1 flex flex-col gap-0.5">${items}</ul>`
    }
    case 'ol': {
      const items = block.items.map((item) => `<li class="ml-5 list-decimal">${renderInline(item)}</li>`).join('')
      return `<ol class="my-1 flex flex-col gap-0.5">${items}</ol>`
    }
    case 'quote': {
      const body = block.lines.map(renderInline).join('<br />')
      return `<blockquote class="my-2 border-l-2 border-theme-primary/40 pl-2 text-theme-text-muted italic">${body}</blockquote>`
    }
    case 'hr':
      return '<hr class="my-2 border-theme-border" />'
    case 'paragraph': {
      const body = block.lines.map(renderInline).join(' ')
      return `<p class="my-1 whitespace-pre-wrap">${body}</p>`
    }
    default:
      return ''
  }
}

export function renderMarkdown(input: string): string {
  if (!input) return ''
  return tokenize(input).map(renderBlock).join('')
}
