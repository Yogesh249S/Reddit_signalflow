export default function LiveFeed({ posts }) {
  return (
    <div className="col-span-1 bg-gray-800 p-4 rounded-xl">
      <h2 className="text-lg mb-3">🔥 Live Feed</h2>

      {posts.map((p) => (
        <div key={p.id} className="p-2 mb-2 rounded bg-gray-700">
          <div className="font-semibold">{p.title}</div>
          <div className="text-sm text-gray-300">
            Score: {p.current_score} | Momentum: {p.momentum}
          </div>
        </div>
      ))}
    </div>
  );
}