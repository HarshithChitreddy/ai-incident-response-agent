const TYPE_LABEL = { llm_call: "LLM", tool_call: "TOOL", notification: "NOTIFY" };

// Each step's created_at is stamped after it executes, so the delta from the
// previous step approximates this step's own duration — same trick APM
// waterfalls use when only completion timestamps exist.
function stepDuration(steps, index) {
  if (index === 0) return null;
  const ms = new Date(steps[index].created_at) - new Date(steps[index - 1].created_at);
  if (!Number.isFinite(ms) || ms < 0) return null;
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

export default function TraceTimeline({ steps }) {
  return (
    <ol className="trace">
      {steps.map((step, index) => {
        const duration = stepDuration(steps, index);
        return (
          <li key={step.id} className={`trace-step trace-${step.step_type}`}>
            <details>
              <summary>
                <span className="trace-seq">{String(step.seq).padStart(2, "0")}</span>
                <span className="trace-type">{TYPE_LABEL[step.step_type] || step.step_type}</span>
                <span className="trace-name">{step.name}</span>
                <span className="trace-tokens">
                  {step.step_type === "llm_call" ? `${step.tokens_in}→${step.tokens_out} tok` : ""}
                </span>
                <span className="trace-duration">{duration || ""}</span>
              </summary>
              <div className="trace-io">
                <div>
                  <h5>input</h5>
                  <pre>{JSON.stringify(step.input, null, 2)}</pre>
                </div>
                <div>
                  <h5>output</h5>
                  <pre>{JSON.stringify(step.output, null, 2)}</pre>
                </div>
              </div>
            </details>
          </li>
        );
      })}
    </ol>
  );
}
