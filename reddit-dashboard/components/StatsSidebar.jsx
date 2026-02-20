export default function StatsSidebar({ stats }) {
  if (!stats) return null;

  return (
    <div className="col-span-1 bg-gray-800 p-4 rounded-xl">
      <h2 className="text-lg mb-3">📊 Daily Stats</h2>
      <div>Total Posts: {stats.overview?.total_posts}</div>
      <div>Avg Score: {stats.overview?.avg_score}</div>
    </div>
  );
}