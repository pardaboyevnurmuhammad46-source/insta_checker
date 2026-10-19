import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { AdminSummary, AdminDailyStat, Post } from '../../types';
import { formatNumber, formatDate } from '../../utils/format';
import {
  Users,
  Video as VideoIcon,
  Eye,
  Heart,
  Award,
  AlertTriangle,
  TrendingUp,
  ExternalLink,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

export const AdminDashboardPage: React.FC = () => {
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [dailyStats, setDailyStats] = useState<AdminDailyStat[]>([]);
  const [topPosts, setTopPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true);
        const [sumRes, dailyRes, topRes] = await Promise.all([
          apiClient.get<AdminSummary>('/api/admin/summary/'),
          apiClient.get<AdminDailyStat[]>('/api/admin/stats/daily/'),
          apiClient.get('/api/admin/posts/?ordering=-views&page_size=10'),
        ]);

        setSummary(sumRes.data);
        setDailyStats(dailyRes.data || []);
        setTopPosts(topRes.data.results || []);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-800 rounded w-48" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-slate-800 rounded-xl" />
          ))}
        </div>
        <div className="h-72 bg-slate-800 rounded-xl" />
      </div>
    );
  }

  const postsByStatus = summary?.posts_by_status || {};

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          Administrator Paneli
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Tizimning umumiy holati, koʻrishlar va Reels integratsiyasi monitoringi
        </p>
      </div>

      {/* Expiring Token Warning Banner */}
      {summary && summary.expiring_tokens_count > 0 && (
        <div className="bg-amber-950/40 border border-amber-800/80 p-4 rounded-xl flex items-center gap-3 text-amber-300">
          <AlertTriangle size={20} className="text-amber-400 shrink-0" />
          <div className="text-xs sm:text-sm">
            <span className="font-semibold">Token muddati ogohlantirishi:</span>{' '}
            {summary.expiring_tokens_count} ta Instagram foydalanuvchisi tokenining amal qilish muddati 7 kundan kam qoldi.
          </div>
        </div>
      )}

      {/* Top Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Foydalanuvchilar</span>
            <span className="p-2 bg-indigo-950 text-indigo-400 rounded-lg">
              <Users size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(summary?.total_users)}
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-1">
            <span className="text-emerald-400">{summary?.connected_users || 0} ulangan</span>
            <span>•</span>
            <span className="text-rose-400">{summary?.needs_reauth_users || 0} reauth</span>
          </div>
        </div>

        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Jami Ko'rishlar</span>
            <span className="p-2 bg-sky-950 text-sky-400 rounded-lg">
              <Eye size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(summary?.total_views)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Barcha Reels ko'rishlar</span>
        </div>

        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Like & Izohlar</span>
            <span className="p-2 bg-rose-950 text-rose-400 rounded-lg">
              <Heart size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(summary?.total_likes)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">
            {formatNumber(summary?.total_comments)} ta izoh
          </span>
        </div>

        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Sovrinlar</span>
            <span className="p-2 bg-amber-950 text-amber-400 rounded-lg">
              <Award size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {summary?.total_prizes} ta
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Berilgan yutuqlar</span>
        </div>
      </div>

      {/* Post Status Breakdown */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-400 block mb-1">
            Joylashtirilgan
          </span>
          <span className="text-xl font-bold text-white">{postsByStatus['published'] || 0}</span>
        </div>
        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-rose-400 block mb-1">
            O'chirilgan
          </span>
          <span className="text-xl font-bold text-white">{postsByStatus['deleted'] || 0}</span>
        </div>
        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-400 block mb-1">
            Xatolik
          </span>
          <span className="text-xl font-bold text-white">{postsByStatus['failed'] || 0}</span>
        </div>
        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-indigo-400 block mb-1">
            Jarayonda
          </span>
          <span className="text-xl font-bold text-white">
            {(postsByStatus['queued'] || 0) + (postsByStatus['publishing'] || 0)}
          </span>
        </div>
      </div>

      {/* Daily Growth Chart */}
      <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <h3 className="font-semibold text-white text-base">
              Kunlik Ko'rishlar va Yangi Postlar
            </h3>
          </div>
          <span className="text-xs text-slate-500">So'nggi 30 kun</span>
        </div>

        {dailyStats.length > 0 ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dailyStats}>
                <defs>
                  <linearGradient id="viewsGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="date"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickFormatter={(val) =>
                    new Date(val).toLocaleDateString('uz-UZ', { month: 'short', day: 'numeric' })
                  }
                />
                <YAxis stroke="#94a3b8" fontSize={11} tickFormatter={(val) => formatNumber(val)} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '0.75rem', color: '#fff' }}
                  formatter={(val: any, name: any) => [
                    formatNumber(val),
                    name === 'total_views' ? 'Koʻrishlar' : 'Yangi postlar',
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="total_views"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#viewsGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
            Statistika ma'lumotlari mavjud emas.
          </div>
        )}
      </div>

      {/* Top 10 Posts Table */}
      <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <h3 className="font-semibold text-white text-base flex items-center gap-2">
            <VideoIcon size={18} className="text-pink-400" />
            <span>Eng Ko'p Ko'rilgan 10 ta Post</span>
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Post ID</th>
                <th className="py-3 px-4">Foydalanuvchi</th>
                <th className="py-3 px-4">Ko'rishlar</th>
                <th className="py-3 px-4">Like</th>
                <th className="py-3 px-4">Izoh</th>
                <th className="py-3 px-4">Sana</th>
                <th className="py-3 px-4">Havola</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {topPosts.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 text-sm">
                    Postlar topilmadi.
                  </td>
                </tr>
              )}
              {topPosts.map((post) => (
                <tr key={post.id} className="hover:bg-slate-900/40 transition">
                  <td className="py-3 px-4 font-mono text-xs text-slate-400">#{post.id}</td>
                  <td className="py-3 px-4 font-medium text-white">{post.user_name || '—'}</td>
                  <td className="py-3 px-4 font-semibold text-sky-400">{formatNumber(post.views)}</td>
                  <td className="py-3 px-4 text-rose-400">{formatNumber(post.likes)}</td>
                  <td className="py-3 px-4 text-emerald-400">{formatNumber(post.comments_count)}</td>
                  <td className="py-3 px-4 text-xs text-slate-400">{formatDate(post.posted_at)}</td>
                  <td className="py-3 px-4">
                    {post.permalink ? (
                      <a
                        href={post.permalink}
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
