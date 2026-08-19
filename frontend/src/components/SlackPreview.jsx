// Renders stored Block Kit messages in actual-Slack layout: avatar block,
// bold sender + timestamp line, body below. Emoji shortcodes are stripped —
// severity is communicated by the message text and the incident's own badges.

import { fmtTs } from "../services/format";

const SHORTCODE = /:[a-z0-9_+-]+:\s?/g;

function clean(text) {
  return (text || "").replace(SHORTCODE, "").trim();
}

function mrkdwn(text, key) {
  const parts = clean(text).split(/(\*[^*\n]+\*|`[^`\n]+`)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <strong key={`${key}-${i}`}>{part.slice(1, -1)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={`${key}-${i}`}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

function MrkdwnText({ text, k }) {
  return (
    <>
      {(text || "").split("\n").map((line, i) => (
        <div key={i} className="slack-line">
          {mrkdwn(line, `${k}-${i}`)}
        </div>
      ))}
    </>
  );
}

function Block({ block, idx }) {
  switch (block.type) {
    case "header":
      return <div className="slack-header-text">{clean(block.text?.text)}</div>;
    case "section":
      if (block.fields) {
        return (
          <div className="slack-fields">
            {block.fields.map((field, i) => (
              <div key={i} className="slack-field">
                <MrkdwnText text={field.text} k={`f-${idx}-${i}`} />
              </div>
            ))}
          </div>
        );
      }
      return (
        <div className="slack-section">
          <MrkdwnText text={block.text?.text} k={`s-${idx}`} />
        </div>
      );
    case "context":
      return (
        <div className="slack-context">
          {(block.elements || []).map((el, i) => (
            <MrkdwnText key={i} text={el.text} k={`c-${idx}-${i}`} />
          ))}
        </div>
      );
    case "divider":
      return <hr className="slack-divider" />;
    default:
      return null;
  }
}

export default function SlackPreview({ message }) {
  const delivery =
    message.transport === "mock" ? "mock" : message.delivered ? "delivered" : "failed";
  return (
    <div className="slack-message">
      <div className="slack-avatar">IR</div>
      <div className="slack-body">
        <div className="slack-meta">
          <span className="slack-bot">incident-agent</span>
          <span className="slack-app-tag">APP</span>
          <span className="slack-ts">{fmtTs(message.created_at)}</span>
          <span className={`slack-delivery ${message.delivered ? "" : "fail"}`}>
            {message.channel} · {delivery}
          </span>
        </div>
        {(message.blocks || []).map((block, i) => (
          <Block key={i} block={block} idx={i} />
        ))}
      </div>
    </div>
  );
}
