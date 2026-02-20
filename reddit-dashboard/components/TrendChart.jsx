import { ScatterChart, Scatter, XAxis, YAxis, Tooltip } from "recharts";

export default function TrendChart({ posts }) {
  return (
    <div className="col-span-2 bg-gray-800 p-4 rounded-xl">
      <h2 className="text-lg mb-3">📈 Engagement Trends</h2>

      <ScatterChart width={500} height={300}>
        <XAxis dataKey="age_minutes" />
        <YAxis dataKey="engagement_score" />
        <Tooltip />
        <Scatter data={posts} fill="#82ca9d" />
      </ScatterChart>
    </div>
  );
}