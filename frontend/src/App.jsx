import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import IncidentList from "./pages/IncidentList";
import IncidentDetail from "./pages/IncidentDetail";

export default function App() {
  return (
    <BrowserRouter>
      <header className="topbar">
        <Link to="/" className="brand">incident-response-agent</Link>
        <span className="topbar-note">local · v0.1</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<IncidentList />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
