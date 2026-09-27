export function App() {
  return (
    <div className="shell">
      <header className="shell__head" />
      <div className="shell__mid">
        <aside className="shell__channels" />
        <main className="shell__work" />
        <aside className="shell__queue" />
      </div>
      <footer className="shell__transport" />
      <div className="grain" aria-hidden />
    </div>
  );
}
