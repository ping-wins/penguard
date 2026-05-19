function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function renderInline(markdown: string): string {
  const codeSpans: string[] = []
  let text = escapeHtml(markdown).replace(/`([^`]+)`/g, (_match, code) => {
    codeSpans.push(`<code>${code}</code>`)
    return `@@CODE_SPAN_${codeSpans.length - 1}@@`
  })

  text = text
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+|mailto:[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>',
    )

  return text.replace(/@@CODE_SPAN_(\d+)@@/g, (_match, index) => codeSpans[Number(index)] ?? '')
}

function renderList(lines: string[], ordered: boolean): string {
  const items = lines.map((line) => {
    const content = ordered
      ? line.replace(/^\d+\.\s+/, '')
      : line.replace(/^[-*]\s+/, '')
    return `<li>${renderInline(content)}</li>`
  })
  const tag = ordered ? 'ol' : 'ul'
  return `<${tag}>${items.join('')}</${tag}>`
}

export function renderSafeMarkdown(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let paragraph: string[] = []
  let list: string[] = []
  let listOrdered = false
  let codeFence: string[] | null = null

  function flushParagraph() {
    if (!paragraph.length) return
    blocks.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`)
    paragraph = []
  }

  function flushList() {
    if (!list.length) return
    blocks.push(renderList(list, listOrdered))
    list = []
  }

  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      if (codeFence) {
        blocks.push(`<pre><code>${escapeHtml(codeFence.join('\n'))}</code></pre>`)
        codeFence = null
      } else {
        flushParagraph()
        flushList()
        codeFence = []
      }
      continue
    }
    if (codeFence) {
      codeFence.push(line)
      continue
    }
    if (!line.trim()) {
      flushParagraph()
      flushList()
      continue
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line)
    if (heading) {
      flushParagraph()
      flushList()
      const level = heading[1].length
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }

    const unordered = /^[-*]\s+/.test(line)
    const ordered = /^\d+\.\s+/.test(line)
    if (unordered || ordered) {
      flushParagraph()
      if (list.length && listOrdered !== ordered) flushList()
      listOrdered = ordered
      list.push(line)
      continue
    }

    flushList()
    paragraph.push(line)
  }

  if (codeFence) blocks.push(`<pre><code>${escapeHtml(codeFence.join('\n'))}</code></pre>`)
  flushParagraph()
  flushList()

  return blocks.join('')
}
