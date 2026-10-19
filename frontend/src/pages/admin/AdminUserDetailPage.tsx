import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { formatNumber, formatDate } from '../../utils/format';
import {
  ArrowLeft,
  Video as VideoIcon,
  ExternalLink,
  TrendingUp,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

export const AdminUserDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [userData, setUserData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        setLoading(true);
        const res = await apiClient.get(`/api/admin/users/${id}/`);
        setUserData(res.data);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };

    fetchUser();
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-800 rounded w-48" />
        <div className="h-44 bg-slate-800 rounded-2xl" />
        <div className="h-96 bg-slate-800 rounded-2xl" />
      </div>
    );
  }

  if (!userData) {
    return (
      <div className="p-8 text-center text-slate-400">
        Foydalanuvchi topilmadi.
      </div>
    );
  }

  // Aggregate history for chart from all user's posts
  const allHistory: any[] = [];
  (userData.posts || []).forEach((p: any) => {
    (p.history || []).forEach((h: any) => {
      allHistory.push({
        time: new Date(h.checked_at).toLocaleDateString('uz-UZ', { month: 'short', day: 'numeric', hour: '2-digit' }),
        timestamp: new Date(h.checked_at).getTime(),
        views: h.views,
        likes: h.likes,
      });
    });
  });
  allHistory.sort((a, b) => a.timestamp - b.timestamp);

  return (
    <div className="space-y-8">
      {/* Back button and title */}
      <div>
        <Link
          to="/admin-panel/users"
          className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-medium mb-3"
        >
          <ArrowLeft size={14} />
          <span>Foydalanuvchilar roʻyxatiga qaytish</span>
        </Link>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          {userData.name}
        </h1>
        <p className="text-slate-400 text-sm mt-0.5">
          @{userData.username || 'user'} • ID #{userData.id}
        </p>
      </div>

      {/* Stats Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
          <span className="text-xs text-slate-500 block mb-1">Holati</span>
          <span className="text-sm font-semibold text-emerald-400 capitalize">
            {userData.status === 'connected' ? 'Ulangan' : userData.status}
          </span>
        </div>

        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
          <span className="text-xs text-slate-500 block mb-1">Jami Ko'rishlar</span>
          <span className="text-lg font-bold text-sky-400">
            {formatNumber(userData.total_views)}
          </span>
        </div>

        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
          <span className="text-xs text-slate-500 block mb-1">Jami Like'lar</span>
          <span className="text-lg font-bold text-rose-400">
            {formatNumber(userData.total_likes)}
          </span>
        </div>

        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
          <span className="text-xs text-slate-500 block mb-1">Postlar Soni</span>
          <span className="text-lg font-bold text-purple-400">
            {userData.posts_count} ta
          </span>
        </div>
      </div>

      {/* History Chart */}
      {allHistory.length > 0 && (
        <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 shadow-sm">
          <h3 className="font-semibold text-white text-base mb-4 flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <span>Ko'rishlar O'sishi Dinamikasi</span>
          </h3>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={allHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} tickFormatter={(val) => formatNumber(val)} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '0.75rem', color: '#fff' }}
                  formatter={(val: any) => [formatNumber(val), 'Koʻrishlar']}
                />
                <Line
                  type="monotone"
                  dataKey="views"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#818cf8' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* User's Posts Table */}
      <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-800">
          <h3 className="font-semibold text-white text-base flex items-center gap-2">
            <VideoIcon size={18} className="text-pink-400" />
            <span>Foydalanuvchining Postlari</span>
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Post ID</th>
                <th className="py-3 px-4">Holati</th>
                <th className="py-3 px-4">Ko'rishlar</th>
                <th className="py-3 px-4">Like</th>
                <th className="py-3 px-4">Izoh</th>
                <th className="py-3 px-4">Joylashtirilgan</th>
                <th className="py-3 px-4">Havola</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {(userData.posts || []).length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 text-sm">
                    Postlar mavjud emas.
                  </td>
                </tr>
              )}
              {(userData.posts || []).map((p: any) => (
                <tr key={p.id} className="hover:bg-slate-900/40 transition">
                  <td className="py-3 px-4 font-mono text-xs text-slate-500">#{p.id}</td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                        p.status === 'published'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : p.status === 'deleted'
                          ? 'bg-rose-950 text-rose-400 border border-rose-800'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {p.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-semibold text-sky-400">{formatNumber(p.views)}</td>
                  <td className="py-3 px-4 text-rose-400">{formatNumber(p.likes)}</td>
                  <td className="py-3 px-4 text-emerald-400">{formatNumber(p.comments_count)}</td>
                  <td className="py-3 px-4 text-xs text-slate-400">{formatDate(p.posted_at)}</td>
                  <td className="py-3 px-4">
                    {p.permalink ? (
                      <a
                        href={p.permalink}
                        target="_blank"
                        rel="noreferrer"
                        className="text-pink-400 hover:text-pink-300 inline-flex items-center gap-1 text-xs"
                      >
                        <span>Reels</span>
                        <ExternalLink size={12} />
                      </a>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
