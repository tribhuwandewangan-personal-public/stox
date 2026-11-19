/**
 * Simple client-side Markdown parser for reports and synthesis.
 * Converts headings, bold, tables, lists, blockquotes, and line breaks to safe HTML.
 */

export function parseMarkdown(md: string | null | undefined): string {
  if (!md) return '';

  let html = md
    // Escape standard HTML tags
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Headings
  html = html.replace(/^### (.*$)/gim, '<h3 class="md-h3">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 class="md-h2">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 class="md-h1">$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/gim, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');

  // Markdown Tables: detect blocks with | ... |
  const lines = html.split('\n');
  const outLines: string[] = [];
  let inTable = false;
  let tableHeaderParsed = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      const cells = line
        .slice(1, -1)
        .split('|')
        .map(c => c.trim());

      // Check if it's separator line (e.g. |---|---|)
      const isSeparator = cells.every(c => /^:?-+:?$/.test(c));

      if (isSeparator) {
        tableHeaderParsed = true;
        continue;
      }

      if (!inTable) {
        inTable = true;
        tableHeaderParsed = false;
        outLines.push('<div class="md-table-wrap"><table class="md-table">');
      }

      if (!tableHeaderParsed) {
        outLines.push('<thead><tr>');
        cells.forEach(c => outLines.push(`<th>${c}</th>`));
        outLines.push('</tr></thead><tbody>');
      } else {
        outLines.push('<tr>');
        cells.forEach(c => outLines.push(`<td>${c}</td>`));
        outLines.push('</tr>');
      }
    } else {
      if (inTable) {
        outLines.push('</tbody></table></div>');
        inTable = false;
        tableHeaderParsed = false;
      }
      outLines.push(line);
    }
  }

  if (inTable) {
    outLines.push('</tbody></table></div>');
  }

  html = outLines.join('\n');

  // Bullet points
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li class="md-li">$1</li>');

  // Paragraphs / Line Breaks
  html = html.replace(/\n\n+/g, '<br><br>');
  html = html.replace(/(<li>.*<\/li>)/gim, '<ul class="md-ul">$1</ul>');
  // Clean duplicate uls
  html = html.replace(/<\/ul>\s*<ul class="md-ul">/gim, '');

  return html;
}
