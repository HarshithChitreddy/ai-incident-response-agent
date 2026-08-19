export default function Panel({ title, right, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <h2>{title}</h2>
        {right && <div className="panel-header-right">{right}</div>}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}
