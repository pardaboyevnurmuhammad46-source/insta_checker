import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { CampaignPost, PaginatedResponse, PostStat } from '../../types';
import {
  formatNumber,
  formatDate,
  formatTimeAgo,
  formatChartDate,
  formatShortTime,
} from '../../utils/format';
import { Pagination } from '../../components/Pagination';
import {
  Eye,
  Heart,
  MessageCircle,
  ExternalLink,
  Search,
  Trash2,
  Film,
  RefreshCw,
  Clock,
  TrendingUp,
  X,
  Loader2,
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

export const UserPostsPage: React.FC = () => {
  const [posts, setPosts] = useState<CampaignPost[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'published' | 'deleted'>('published');

  // History Modal states
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [selectedPost, setSelectedPost] = useState<CampaignPost | null>(null);
  const [postHistory, setPostHistory] = useState<PostStat[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [checkingPostId, setCheckingPostId] = useState<number | null>(null);

  const fetchPosts = async () => {
    try {
      setLoading(true);
      const statusParam = statusFilter !== 'all' ? `&status=${statusFilter}` : '';
      const searchParam = search ? `&search=${search}` : '';

      const res = await apiClient.get<PaginatedResponse<CampaignPost>>(
        `/api/user/posts/?page=${page}${statusParam}${searchParam}`
      );
      setPosts(res.data.results || []);
      setTotalCount(res.data.count || 0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  // Debounced fetch for search
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      fetchPosts();
    }, 400);
    return () => clearTimeout(timer);
  }, [search, statusFilter]);

  useEffect(() => {
    fetchPosts();
  }, [page]);

  const handleDeletePost = async (postId: number) => {
    if (!window.confirm("Haqiqatan ham ushbu postni o'chirmoqchimisiz? Tarix tozalanadi.")) return;
    try {
      await apiClient.delete(`/api/user/posts/${postId}/`);
      fetchPosts();
    } catch {
      // ignore
    }
  };

  const handleOpenHistory = async (post: CampaignPost) => {
    setSelectedPost(post);
    setHistoryModalOpen(true);
    setLoadingHistory(true);
    try {
      const res = await apiClient.get<PostStat[]>(`/api/me/posts/${post.id}/history/`);
      setPostHistory(res.data || []);
    } catch {
      setPostHistory([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleCheckMetricsNow = async (postId: number) => {
    try {
      setCheckingPostId(postId);
      await apiClient.post(`/api/posts/${postId}/check-metrics/`);
      // Refetch after 1.5 seconds to see fresh Celery output
      setTimeout(async () => {
        await fetchPosts();
        setCheckingPostId(null);
      }, 1500);
    } catch {
      setCheckingPostId(null);
    }
  };

  // Aggregated totals
  const totalViews = posts.reduce((acc, p) => acc + (p.views || 0), 0);
  const totalLikes = posts.reduce((acc, p) => acc + (p.likes || 0), 0);
  const totalComments = posts.reduce((acc, p) => acc + (p.comments_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Mening Postlarim
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Barcha Reels videolaringiz, ko'rishlar statistikasi va Celery monitoring navbati
          </p>
        </div>
        <button
          onClick={fetchPosts}
          disabled={loading}
          className="p-2.5 bg-slate-900 border border-slate-800 text-slate-300 rounded-xl hover:text-white hover:bg-slate-800 transition w-fit flex items-center gap-2 text-xs font-semibold"
          title="Ro'yxatni yangilash"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          <span className="hidden sm:inline">Yangilash</span>
        </button>
      </div>

      {/* Summary KPI Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
              Jami Postlar
            </span>
            <span className="text-xl font-bold text-white">{totalCount}</span>
          </div>
          <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg">
            <Film size={20} />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
              Ko'rishlar
            </span>
            <span className="text-xl font-bold text-sky-400">{formatNumber(totalViews)}</span>
          </div>
          <div className="p-2 bg-sky-500/10 text-sky-400 rounded-lg">
            <Eye size={20} />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
              Like'lar
            </span>
            <span className="text-xl font-bold text-rose-400">{formatNumber(totalLikes)}</span>
          </div>
          <div className="p-2 bg-rose-500/10 text-rose-400 rounded-lg">
            <Heart size={20} />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
              Izohlar
            </span>
            <span className="text-xl font-bold text-emerald-400">{formatNumber(totalComments)}</span>
          </div>
          <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg">
            <MessageCircle size={20} />
          </div>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex flex-col md:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Kod yoki izoh bo'yicha qidirish..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:border-indigo-500 outline-none transition"
          />
        </div>
        <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 w-full md:w-auto">
          {['published', 'deleted', 'all'].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s as any)}
              className={`flex-1 md:px-4 py-1.5 rounded-md text-xs font-semibold capitalize transition ${
                statusFilter === s
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s === 'published' ? 'Faol' : s === 'deleted' ? "O'chirilgan" : 'Barchasi'}
            </button>
          ))}
        </div>
      </div>

      {/* Post Cards Grid */}
      {loading && posts.length === 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-60 bg-slate-900 rounded-2xl border border-slate-800" />
          ))}
        </div>
      ) : posts.length === 0 ? (
        <div className="py-16 bg-slate-900 border border-slate-800 rounded-2xl text-center">
          <Film size={40} className="mx-auto text-slate-600 mb-3" />
          <p className="text-slate-300 font-medium">Postlar topilmadi</p>
          <p className="text-slate-500 text-sm mt-1">
            Boshqa filtr tanlab ko'ring yoki yangi video joylang.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {posts.map((post) => (
            <div
              key={post.id}
              className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden flex flex-col group hover:border-slate-700 transition shadow-lg"
            >
              {/* Card Header & Thumbnail */}
              <div className="h-36 bg-slate-800 relative overflow-hidden">
                {post.thumbnail_url ? (
                  <img
                    src={post.thumbnail_url}
                    alt="Cover"
                    className="w-full h-full object-cover opacity-80 group-hover:scale-105 transition duration-500"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-slate-600 bg-slate-900/50">
                    <Film size={28} className="mb-1" />
                    <span className="text-[10px] uppercase font-bold tracking-widest">Reels</span>
                  </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-900/40 to-transparent" />

                <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      post.status === 'deleted'
                        ? 'bg-rose-500/90 text-white'
                        : 'bg-emerald-500/90 text-white'
                    }`}
                  >
                    {post.status === 'deleted' ? "O'chirilgan" : 'Faol'}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded font-semibold bg-slate-900/90 text-slate-300 border border-slate-700">
                    {post.source === 'site' ? 'Sayt' : "O'zim"}
                  </span>
                </div>

                <div className="absolute bottom-2.5 left-3 right-3 flex justify-between items-end">
                  <span className="font-mono text-amber-400 font-bold bg-slate-950/90 px-2 py-0.5 rounded border border-slate-700 text-xs tracking-wider">
                    {post.code || '#NOCODE'}
                  </span>
                  {post.permalink && (
                    <a
                      href={post.permalink}
                      target="_blank"
                      rel="noreferrer"
                      className="w-7 h-7 bg-white/10 hover:bg-white/20 backdrop-blur rounded-full flex items-center justify-center text-white transition"
                      title="Instagramda ochish"
                    >
                      <ExternalLink size={12} />
                    </a>
                  )}
                </div>
              </div>

              {/* Card Body - Statistics */}
              <div className="p-4 flex-1 flex flex-col justify-between space-y-3.5">
                {/* 3 Metric Boxes */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-slate-950 rounded-xl p-2.5 text-center border border-slate-800/80">
                    <Eye size={14} className="mx-auto text-sky-400 mb-1" />
                    <span className="block text-white font-bold text-sm tracking-tight">
                      {formatNumber(post.views)}
                    </span>
                    <span className="text-[9px] uppercase tracking-wider text-slate-500 font-medium">
                      Ko'rish
                    </span>
                  </div>
                  <div className="bg-slate-950 rounded-xl p-2.5 text-center border border-slate-800/80">
                    <Heart size={14} className="mx-auto text-rose-400 mb-1" />
                    <span className="block text-slate-200 font-bold text-sm tracking-tight">
                      {formatNumber(post.likes)}
                    </span>
                    <span className="text-[9px] uppercase tracking-wider text-slate-500 font-medium">
                      Layk
                    </span>
                  </div>
                  <div className="bg-slate-950 rounded-xl p-2.5 text-center border border-slate-800/80">
                    <MessageCircle size={14} className="mx-auto text-emerald-400 mb-1" />
                    <span className="block text-slate-200 font-bold text-sm tracking-tight">
                      {formatNumber(post.comments_count)}
                    </span>
                    <span className="text-[9px] uppercase tracking-wider text-slate-500 font-medium">
                      Izoh
                    </span>
                  </div>
                </div>

                {/* Celery Monitoring Timing */}
                <div className="bg-slate-950/60 rounded-xl p-2.5 border border-slate-800/60 text-[11px] space-y-1">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="flex items-center gap-1.5">
                      <Clock size={12} className="text-slate-500" />
                      Oxirgi yangilanish:
                    </span>
                    <span className="font-medium text-slate-300">
                      {post.last_checked_at || post.last_synced_at
                        ? `${formatShortTime(post.last_checked_at || post.last_synced_at)} (${formatTimeAgo(
                            post.last_checked_at || post.last_synced_at
                          )})`
                        : 'Kutilmoqda'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="flex items-center gap-1.5">
                      <TrendingUp size={12} className="text-indigo-400" />
                      Keyingi tekshiruv navbati:
                    </span>
                    <span className="font-medium text-indigo-300">
                      {post.next_check_at ? formatShortTime(post.next_check_at) : 'Reja boʻyicha (5m)'}
                    </span>
                  </div>
                </div>

                {/* Actions Row */}
                <div className="flex items-center justify-between text-[11px] pt-3 border-t border-slate-800">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleOpenHistory(post)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-indigo-600/15 hover:bg-indigo-600/25 text-indigo-300 border border-indigo-500/20 font-semibold transition"
                      title="Statistika o'sish tarixini ko'rish"
                    >
                      <TrendingUp size={12} />
                      <span>Statistika tarixi</span>
                    </button>

                    <button
                      onClick={() => handleCheckMetricsNow(post.id)}
                      disabled={checkingPostId === post.id}
                      className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"
                      title="Statistikani hozir tekshirish (Celery)"
                    >
                      <RefreshCw
                        size={12}
                        className={checkingPostId === post.id ? 'animate-spin text-indigo-400' : ''}
                      />
                    </button>
                  </div>

                  <button
                    onClick={() => handleDeletePost(post.id)}
                    className="text-slate-500 hover:text-rose-400 flex items-center gap-1 transition px-2 py-1 rounded"
                    title="Postni o'chirish"
                  >
                    <Trash2 size={12} />
                    <span>O'chirish</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalCount > posts.length && (
        <Pagination currentPage={page} totalCount={totalCount} onPageChange={(p) => setPage(p)} />
      )}

      {/* Statistika Tarixi Modali */}
      {historyModalOpen && selectedPost && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative space-y-5 max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <TrendingUp className="text-indigo-400" size={20} />
                  Post Statistikasi Tarixi
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Celery tomonidan yozib borilgan ko'rishlar va metrikalar dinamikasi (#{selectedPost.code || selectedPost.id})
                </p>
              </div>
              <button
                onClick={() => setHistoryModalOpen(false)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
              >
                <X size={18} />
              </button>
            </div>

            {/* Current Highlights */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] font-semibold uppercase text-slate-400 block mb-0.5">
                  Ko'rishlar
                </span>
                <span className="text-lg font-bold text-white">
                  {formatNumber(selectedPost.views)}
                </span>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] font-semibold uppercase text-slate-400 block mb-0.5">
                  Like'lar
                </span>
                <span className="text-lg font-bold text-rose-400">
                  {formatNumber(selectedPost.likes)}
                </span>
              </div>
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-center">
                <span className="text-[10px] font-semibold uppercase text-slate-400 block mb-0.5">
                  Izohlar
                </span>
                <span className="text-lg font-bold text-emerald-400">
                  {formatNumber(selectedPost.comments_count)}
                </span>
              </div>
            </div>

            {/* Chart Area */}
            {loadingHistory ? (
              <div className="h-56 flex items-center justify-center text-slate-400">
                <Loader2 size={24} className="animate-spin text-indigo-400" />
              </div>
            ) : postHistory.length > 0 ? (
              <div className="space-y-4">
                <div className="h-56 w-full bg-slate-950 p-3 rounded-xl border border-slate-800">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={postHistory.map((s) => ({
                        rawDate: s.checked_at,
                        name: formatChartDate(s.checked_at),
                        views: s.views,
                        likes: s.likes,
                      }))}
                      margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient id="colorHistoryViews" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                      <XAxis dataKey="name" stroke="#64748b" fontSize={10} axisLine={false} tickLine={false} />
                      <YAxis stroke="#64748b" fontSize={10} axisLine={false} tickLine={false} tickFormatter={(v) => formatNumber(v)} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#334155',
                          borderRadius: '0.75rem',
                          color: '#fff',
                        }}
                        labelFormatter={(label, payload) => {
                          const item = payload?.[0]?.payload;
                          return item?.rawDate ? formatDate(item.rawDate) : label;
                        }}
                        formatter={(val: any) => [formatNumber(val), 'Koʻrishlar']}
                      />
                      <Area
                        type="monotone"
                        dataKey="views"
                        stroke="#818cf8"
                        strokeWidth={2.5}
                        fillOpacity={1}
                        fill="url(#colorHistoryViews)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {/* History Table */}
                <div className="overflow-x-auto max-h-48 border border-slate-800 rounded-xl">
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800 sticky top-0">
                      <tr>
                        <th className="py-2.5 px-3">Tekshiruv Vaqti</th>
                        <th className="py-2.5 px-3">Ko'rishlar</th>
                        <th className="py-2.5 px-3">Like'lar</th>
                        <th className="py-2.5 px-3">Izohlar</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 bg-slate-900/50">
                      {postHistory.map((h) => (
                        <tr key={h.id} className="hover:bg-slate-800/30">
                          <td className="py-2 px-3 text-slate-400 font-mono">
                            {formatDate(h.checked_at)}
                          </td>
                          <td className="py-2 px-3 font-bold text-white">
                            {formatNumber(h.views)}
                          </td>
                          <td className="py-2 px-3 text-rose-300">
                            {formatNumber(h.likes)}
                          </td>
                          <td className="py-2 px-3 text-emerald-300">
                            {formatNumber(h.comments_count)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-slate-500 text-xs">
                Ushbu post uchun hali tarixiy yozuvlar yo'q. Celery birinchi navbat kelishi bilan yangilaydi.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
