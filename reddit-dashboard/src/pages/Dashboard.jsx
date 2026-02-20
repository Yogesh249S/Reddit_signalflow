import { useEffect, useState } from "react";
import { fetchPosts, fetchStats } from "../api";
import LiveFeed from "../components/LiveFeed";
import TrendChart from "../components/TrendChart";
import StatsSidebar from "../components/StatsSidebar";

export default function Dashboard() {
  const [posts, setPosts] = useState([]);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const postRes = await fetchPosts();
      const statsRes = await fetchStats();

      setPosts(postRes.data.results || postRes.data);
      setStats(statsRes.data);
    } catch (err) {
      console.error("API error:", err);
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0f14] text-gray-200 p-6">
      <h1 className="text-2xl font-semibold mb-6 tracking-wide text-gray-100">
        Reddit Trends Terminal
      </h1>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-3">
          <LiveFeed posts={posts} />
        </div>

        <div className="col-span-6">
          <TrendChart posts={posts} />
        </div>

        <div className="col-span-3">
          <StatsSidebar stats={stats} />
        </div>
      </div>
    </div>
  );
}
