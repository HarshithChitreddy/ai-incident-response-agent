// Minimal markdown renderer for agent-generated postmortems/runbooks:
// headings, lists, bold, inline code. Deliberately dependency-free.

function inline(text, key) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={`${key}-${i}`}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

export default function Markdown({ text }) {
  if (!text) return null;
  const lines = text.split("\n");
  const blocks = [];
  let list = null;

  const flushList = () => {
    if (list) {
      blocks.push(
        <ul key={`ul-${blocks.length}`}>
          {list.map((item, i) => (
            <li key={i}>{inline(item, `li-${blocks.length}-${i}`)}</li>
          ))}
        </ul>
      );
      list = null;
    }
  };

  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    const listMatch = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/);
    if (listMatch) {
      list = list || [];
      list.push(listMatch[1]);
      return;
    }
    flushList();
    if (!line.trim()) return;
    if (line.startsWith("### ")) blocks.push(<h4 key={idx}>{inline(line.slice(4), idx)}</h4>);
    else if (line.startsWith("## ")) blocks.push(<h3 key={idx}>{inline(line.slice(3), idx)}</h3>);
    else if (line.startsWith("# ")) blocks.push(<h2 key={idx}>{inline(line.slice(2), idx)}</h2>);
    else blocks.push(<p key={idx}>{inline(line, idx)}</p>);
  });
  flushList();

  return <div className="markdown">{blocks}</div>;
}
