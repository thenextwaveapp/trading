import { useNavigate } from "react-router-dom";

export default function NotFound() {
  const nav = useNavigate();
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, textAlign: "center", padding: 24 }}>
      <div className="num" style={{ fontSize: 68, letterSpacing: "-0.04em" }} >404</div>
      <div className="muted" style={{ fontSize: 15 }}>This page drifted out of formation.</div>
      <button
        onClick={() => nav("/")}
        style={{ height: 40, padding: "0 18px", borderRadius: 10, border: "1px solid #E9ECF1", background: "#E9ECF1", color: "#07090C", fontWeight: 500 }}
      >
        Back to the fleet
      </button>
    </div>
  );
}
