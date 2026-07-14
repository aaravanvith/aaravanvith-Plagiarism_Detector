const RISK_COLOR = {
  HIGH: "#B23A48",
  MODERATE: "#B8862F",
  LOW: "#2F7A5C",
};

export default function ScoreSeal({ score, verdict }) {
  const color = RISK_COLOR[verdict] || RISK_COLOR.LOW;
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - score / 100);

  return (
    <div className="relative flex flex-col items-center justify-center">
      <div className="relative scan-sweep overflow-hidden rounded-full">
        <svg width="180" height="180" viewBox="0 0 180 180">
          <circle cx="90" cy="90" r={radius} fill="none" stroke="#E7E9F2" strokeWidth="14" />
          <circle
            cx="90"
            cy="90"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform="rotate(-90 90 90)"
            style={{ transition: "stroke-dashoffset 0.9s ease" }}
          />
          <text x="90" y="84" textAnchor="middle" fontSize="34" fontFamily="'IBM Plex Mono', monospace" fontWeight="600" fill="#182142">
            {score}%
          </text>
          <text x="90" y="106" textAnchor="middle" fontSize="11" letterSpacing="1.5" fontFamily="Inter, sans-serif" fill="#5C6688">
            SIMILARITY
          </text>
        </svg>
      </div>
      <span
        className="mt-3 px-3 py-1 rounded-full text-xs font-semibold tracking-wide uppercase"
        style={{ color, backgroundColor: color + "1A" }}
      >
        {verdict} risk
      </span>
    </div>
  );
}
