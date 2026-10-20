import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { UserSummary, Post } from '../../types';
import { formatNumber, formatDate } from '../../utils/format';
import {
  Eye,
  Heart,
  MessageCircle,
  Video as VideoIcon,
  Award,
  ArrowRight,
  TrendingUp,
  Clock,
  Sparkles,
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

export const UserDashboardPage: React.FC = () => {
  const [summary, setSummary] = useState<UserSummary | null>(null);
  const [recentPosts, setRecentPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        const [sumRes, postsRes] = await Promise.all([
          apiClient.get<UserSummary>('/api/me/summary/'),
          apiClient.get('/api/me/posts/?page_size=7'),
        ]);
        setSummary(sumRes.data);
        setRecentPosts(postsRes.data.results || []);
      } catch (err: any) {
        setError(err.detail || 'Maʼlumotlarni yuklashda xatolik yuz berdi');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-800 rounded w-48" />
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-28 bg-slate-800 rounded-xl" />
          ))}
        </div>
        <div className="h-72 bg-slate-800 rounded-xl" />
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="bg-rose-950/40 border border-rose-800 text-rose-200 p-6 rounded-xl text-center">
        <p>{error || 'Statistikani yuklab boʻlmadi.'}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 bg-rose-700 hover:bg-rose-600 text-white rounded-lg text-sm"
        >
          Qayta urinish
        </button>
      </div>
    );
  }

  // Backend'dan olingan ma'lumotlar
  const progressPercent = summary.progress_percent || 0;
  const viewsRemaining = summary.views_remaining || 0;
  const nextMilestone = summary.next_milestone || 0;

  // Chart data from recent posts
  const chartData = [...recentPosts]
    .reverse()
    .map((p, idx) => ({
      name: p.posted_at ? new Date(p.posted_at).toLocaleDateString('uz-UZ', { month: 'short', day: 'numeric' }) : `#${idx + 1}`,
      views: p.views,
      likes: p.likes,
    }));

  return (
    <div className="space-y-8">
      {/* Page Title */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Mening Natijalarim
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Instagram Reels statistikasi va sovrinlar holati
          </p>
        </div>

        <Link
          to="/app/video"
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition shadow-md self-start md:self-auto"
        >
          <span>Videoni joylash</span>
          <ArrowRight size={16} />
        </Link>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Ko'rishlar</span>
            <span className="p-2 bg-sky-950 text-sky-400 rounded-lg">
              <Eye size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(summary.total_views)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Jami reels ko'rishlar</span>
        </div>

        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Like'lar</span>
            <span className="p-2 bg-rose-950 text-rose-400 rounded-lg">
              <Heart size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(summary.total_likes)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Barcha yoqtirishlar</span>
        </div>

        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Izohlar</span>
            <span className="p-2 bg-emerald-950 text-emerald-400 rounded-lg">
              <MessageCircle size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(summary.total_comments)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Jami izohlar soni</span>
        </div>

        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Postlar</span>
            <span className="p-2 bg-purple-950 text-purple-400 rounded-lg">
              <VideoIcon size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {summary.posts_count}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Joylashtirilgan videolar</span>
        </div>

        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between col-span-2 lg:col-span-1">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Yutuqlar</span>
            <span className="p-2 bg-amber-950 text-amber-400 rounded-lg">
              <Award size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {summary.prizes_count} ta
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Erishilgan sovrinlar</span>
        </div>
      </div>

      {/* Milestone Progress Card */}
      <div className="bg-gradient-to-r from-slate-950 via-slate-900 to-indigo-950/40 p-6 rounded-2xl border border-slate-800 shadow-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-amber-500/10 text-amber-400 rounded-xl border border-amber-500/20">
              <Sparkles size={24} />
            </div>
            <div>
              <h3 className="font-semibold text-white text-base">
                Keyingi sovrin: <span className="text-amber-400 font-bold">{formatNumber(nextMilestone)}</span> ko'rish
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                {viewsRemaining > 0
                  ? `Sovringa erishish uchun yana ${formatNumber(viewsRemaining)} ta ko'rish qoldi`
                  : 'Tabriklaymiz, barcha belgilangan marralarga erishildi!'}
              </p>
            </div>
          </div>
          <span className="text-sm font-bold text-indigo-400 self-start md:self-auto">
            {progressPercent}%
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-slate-800 rounded-full h-3 overflow-hidden p-0.5">
          <div
            className="bg-gradient-to-r from-indigo-500 to-pink-500 h-full rounded-full transition-all duration-700"
            style={{ width: `${Math.max(4, Math.min(100, progressPercent))}%` }}
          />
        </div>
      </div>

      {/* Views Growth Chart */}
      <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <h3 className="font-semibold text-white text-base">Ko'rishlar O'sish Dinamikasi</h3>
          </div>
          {summary.last_checked_at && (
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Clock size={14} />
              <span>Oxirgi tekshiruv: {formatDate(summary.last_checked_at)}</span>
            </div>
          )}
        </div>

        {chartData.length > 0 ? (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(val) => formatNumber(val)} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '0.75rem', color: '#fff' }}
                  formatter={(value: any) => [formatNumber(value), 'Koʻrishlar']}
                />
                <Line
                  type="monotone"
                  dataKey="views"
                  stroke="#6366f1"
                  strokeWidth={3}
                  dot={{ r: 4, fill: '#818cf8' }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
            Hozircha postlar mavjud emas. Birinchi videongizni joylang!
          </div>
        )}
      </div>
    </div>
  );
};
