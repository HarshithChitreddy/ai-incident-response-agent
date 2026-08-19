export default function TraceTimeline({ steps }) {
  return (
    <ol className="trace">
      {steps.map((step) => (
        <li key={step.id} className="trace-step">
          <details>
            <summary>
              <span className="trace-seq">{String(step.seq).padStart(2, "0")}</span>
              <span className="trace-name">{step.name}</span>
              <span className="trace-tokens">
                {step.step_type === "llm_call" ? `${step.tokens_in}→${step.tokens_out} tok` : ""}
              </span>
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
      ))}
    </ol>
  );
}
