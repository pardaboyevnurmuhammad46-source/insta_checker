import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { UserSummary, Post } from '../../types';
import {
  formatNumber,
  formatDate,
  formatTimeAgo,
  formatChartDate,
  formatShortTime,
} from '../../utils/format';
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
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

export const UserDashboardPage: React.FC = () => {
  const [summary, setSummary] = useState<UserSummary | null>(null);
  const [allPosts, setAllPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<'7' | '30'>('7');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [sumRes, postsRes] = await Promise.all([
          apiClient.get<UserSummary>('/api/me/summary/'),
          apiClient.get('/api/me/posts/?page_size=50'),
        ]);
        setSummary(sumRes.data);
        const rawPosts = postsRes.data.results || postsRes.data || [];
        const activePosts = rawPosts.filter((p: any) => p.status !== 'deleted');
        setAllPosts(activePosts);
      } catch {
        // error handling handled gracefully
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading && !summary) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-800 rounded w-48" />
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-28 bg-slate-900 rounded-2xl" />
          ))}
        </div>
        <div className="h-32 bg-slate-900 rounded-2xl" />
        <div className="h-72 bg-slate-900 rounded-2xl" />
      </div>
    );
  }

  // Safe fallback values (shows 0 when user has no posts)
  const totalViews = summary?.total_views || 0;
  const totalLikes = summary?.total_likes || 0;
  const totalComments = summary?.total_comments || 0;
  const postsCount = summary?.posts_count || 0;
  const prizesCount = summary?.prizes_count || 0;
  const nextMilestone = summary?.next_milestone || 500;
  const viewsRemaining = summary?.views_remaining ?? Math.max(0, nextMilestone - totalViews);
  const rawProgress = summary?.progress_percent ?? 0;
  const progressPercent = Number(rawProgress.toFixed(1));

  // Filter posts by time range (7 days vs 30 days)
  const nowMs = new Date().getTime();
  const daysLimit = timeRange === '7' ? 7 : 30;
  const filteredPosts = allPosts.filter((p) => {
    if (!p.posted_at) return true;
    const postMs = new Date(p.posted_at).getTime();
    return nowMs - postMs <= daysLimit * 24 * 60 * 60 * 1000;
  });

  const chartData = [...filteredPosts]
    .reverse()
    .map((p) => ({
      rawDate: p.posted_at,
      name: formatChartDate(p.posted_at),
      views: p.views || 0,
      likes: p.likes || 0,
    }));

  const hasPosts = postsCount > 0 && chartData.length > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white flex items-center gap-2">
            Mening Natijalarim
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Instagram Reels statistikasi va sovrinlar holati
          </p>
        </div>

        <Link
          to="/app/video"
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition active:scale-95 self-start md:self-auto"
        >
          <span>Videoni joylash</span>
          <ArrowRight size={16} />
        </Link>
      </div>

      {/* 5 ta Statistik Karta */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {/* 1. Ko'rishlar */}
        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Ko'rishlar</span>
            <span className="p-2 bg-sky-500/10 text-sky-400 rounded-lg">
              <Eye size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(totalViews)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Jami reels ko'rishlar</span>
        </div>

        {/* 2. Like'lar */}
        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Like'lar</span>
            <span className="p-2 bg-rose-500/10 text-rose-400 rounded-lg">
              <Heart size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(totalLikes)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Barcha yoqtirishlar</span>
        </div>

        {/* 3. Izohlar */}
        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Izohlar</span>
            <span className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg">
              <MessageCircle size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {formatNumber(totalComments)}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Jami izohlar soni</span>
        </div>

        {/* 4. Postlar */}
        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Postlar</span>
            <span className="p-2 bg-purple-500/10 text-purple-400 rounded-lg">
              <VideoIcon size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {postsCount}
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Joylashtirilgan videolar</span>
        </div>

        {/* 5. Sovrinlar */}
        <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col justify-between col-span-2 lg:col-span-1">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Sovrinlar</span>
            <span className="p-2 bg-amber-500/10 text-amber-400 rounded-lg">
              <Award size={18} />
            </span>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {prizesCount} ta
          </div>
          <span className="text-[11px] text-slate-500 mt-1">Erishilgan sovrinlar</span>
        </div>
      </div>

      {/* Sovrin Progress Kartasi */}
      <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-md">
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
                  : 'Tabriklaymiz, barcha belgilangan sovrin marralariga erishildi!'}
              </p>
            </div>
          </div>
          <span className="text-sm font-bold text-indigo-400 self-start md:self-auto font-mono">
            {progressPercent}%
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-slate-950 rounded-full h-3 overflow-hidden p-0.5 border border-slate-800">
          <div
            className="bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 h-full rounded-full transition-all duration-700"
            style={{ width: `${Math.max(2, Math.min(100, progressPercent))}%` }}
          />
        </div>
      </div>

      {/* Ko'rishlar Grafigi Kartasi */}
      <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <h3 className="font-semibold text-white text-base">Ko'rishlar O'sish Dinamikasi</h3>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Oxirgi tekshiruv */}
            {summary?.last_checked_at && (
              <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
                <Clock size={13} className="text-slate-500" />
                <span>
                  Oxirgi tekshiruv: {formatShortTime(summary.last_checked_at)} ({formatTimeAgo(summary.last_checked_at)})
                </span>
              </div>
            )}

            {/* 7 kun / 30 kun almashtirgichi */}
            <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800">
              <button
                type="button"
                onClick={() => setTimeRange('7')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
                  timeRange === '7'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                7 kun
              </button>
              <button
                type="button"
                onClick={() => setTimeRange('30')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
                  timeRange === '30'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                30 kun
              </button>
            </div>
          </div>
        </div>

        {hasPosts ? (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorViews" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                <XAxis
                  dataKey="name"
                  stroke="#64748b"
                  fontSize={11}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  stroke="#64748b"
                  fontSize={11}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(val) => formatNumber(val)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    borderRadius: '0.75rem',
                    color: '#fff',
                    boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
                  }}
                  labelFormatter={(label, payload) => {
                    const item = payload?.[0]?.payload;
                    return item?.rawDate ? formatDate(item.rawDate) : label;
                  }}
                  formatter={(value: any) => [formatNumber(value), 'Koʻrishlar']}
                />
                <Area
                  type="monotone"
                  dataKey="views"
                  stroke="#818cf8"
                  strokeWidth={3}
                  fillOpacity={1}
                  fill="url(#colorViews)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          /* Postsiz holat (Requirement 5) */
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 space-y-3 bg-slate-950/40 rounded-xl border border-slate-800/60">
            <div className="w-12 h-12 rounded-full bg-slate-800/80 flex items-center justify-center text-slate-500">
              <VideoIcon size={24} />
            </div>
            <p className="text-sm font-medium text-slate-400">
              Hali post yo'q. Birinchi videoni joylang
            </p>
            <Link
              to="/app/video"
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-bold transition shadow-md shadow-indigo-600/20"
            >
              <span>Videoni joylash</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        )}
      </div>
    </div>
  );
};
