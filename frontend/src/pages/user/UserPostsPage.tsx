import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { CampaignPost, PostStat, PaginatedResponse } from '../../types';
import { formatNumber, formatDate, formatTimeAgo } from '../../utils/format';
import { Pagination } from '../../components/Pagination';
import {
  Eye,
  Heart,
  MessageCircle,
  ExternalLink,
  LineChart as ChartIcon,
  X,
  RefreshCw,
  Film,
  Trash2,
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

export const UserPostsPage: React.FC = () => {
  const [posts, setPosts] = useState<CampaignPost[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // History modal
  const [selectedPost, setSelectedPost] = useState<CampaignPost | null>(null);
  const [historyStats, setHistoryStats] = useState<PostStat[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const fetchPosts = async (pageNumber: number) => {
    try {
      setLoading(true);
      const res = await apiClient.get<PaginatedResponse<CampaignPost>>(
        `/api/user/posts/?page=${pageNumber}`
      );
      setPosts(res.data.results || []);
      setTotalCount(res.data.count || 0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPosts(page);
  }, [page]);

  const handleOpenHistory = async (post: CampaignPost) => {
    setSelectedPost(post);
    setLoadingHistory(true);
    try {
      const res = await apiClient.get<PostStat[]>(`/api/me/posts/${post.id}/history/`);
      setHistoryStats(res.data || []);
    } catch {
      setHistoryStats([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleRefreshHistory = async () => {
    if (!selectedPost) return;
    setLoadingHistory(true);
    try {
      const res = await apiClient.get<PostStat[]>(`/api/me/posts/${selectedPost.id}/history/`);
      setHistoryStats(res.data || []);
      fetchPosts(page);
    } catch {
      // ignore
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleDeletePost = async (postId: number) => {
    if (!window.confirm("Haqiqatan ham ushbu postni tarixdan o'chirmoqchimisiz?")) {
      return;
    }
    try {
      await apiClient.delete(`/api/user/posts/${postId}/`);
      fetchPosts(page);
    } catch {
      // ignore
    }
  };

  const getStatusBadge = (post: CampaignPost) => {
    switch (post.status) {
      case 'verified':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
            Tasdiqlangan
          </span>
        );
      case 'revoked':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950 text-amber-400 border border-amber-800">
            Bekor qilingan
          </span>
        );
      case 'rejected':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950 text-rose-400 border border-rose-800">
            Rad etilgan
          </span>
        );
      case 'published':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-950 text-blue-400 border border-blue-800">
            Joylandi
          </span>
        );
      case 'queued':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950 text-amber-400 border border-amber-800">
            Navbatda
          </span>
        );
      case 'failed':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-900">
            Xatolik
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400">
            {post.status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          Mening Postlarim
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Instagram akkauntingizga joylangan barcha videolar va ularning statistikasi
        </p>
      </div>

      <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3.5 px-4">Video</th>
                <th className="py-3.5 px-4">Kod</th>
                <th className="py-3.5 px-4">Holati</th>
                <th className="py-3.5 px-4">Manba</th>
                <th className="py-3.5 px-4">Ko'rishlar</th>
                <th className="py-3.5 px-4">Like</th>
                <th className="py-3.5 px-4">Izoh</th>
                <th className="py-3.5 px-4">Joylandi</th>
                <th className="py-3.5 px-4">Sinxronizatsiya</th>
                <th className="py-3.5 px-4">Havola</th>
                <th className="py-3.5 px-4 text-right">Tarix</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading && (
                <tr>
                  <td colSpan={11} className="py-12 text-center text-slate-500 text-sm">
                    Yuklanmoqda...
                  </td>
                </tr>
              )}
              {!loading && posts.length === 0 && (
                <tr>
                  <td colSpan={11} className="py-12 text-center text-slate-500 text-sm">
                    Hozircha postlar mavjud emas.
                  </td>
                </tr>
              )}
              {!loading &&
                posts.map((post) => (
                  <tr key={post.id} className="hover:bg-slate-900/40 transition">
                    <td className="py-3 px-4">
                      {post.thumbnail_url ? (
                        <img
                          src={post.thumbnail_url}
                          alt="Thumbnail"
                          className="w-10 h-14 object-cover rounded-md border border-slate-700"
                        />
                      ) : (
                        <div className="w-10 h-14 bg-slate-800 rounded-md border border-slate-700 flex items-center justify-center">
                          <Film size={16} className="text-slate-500" />
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono font-semibold text-amber-400">
                      {post.code || '—'}
                    </td>
                    <td className="py-3 px-4">{getStatusBadge(post)}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`text-[11px] px-2 py-0.5 rounded ${
                          post.source === 'site'
                            ? 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                            : 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {post.source === 'site' ? 'Sayt' : "O'zim"}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-semibold text-white">
                      <span className="inline-flex items-center gap-1.5">
                        <Eye size={14} className="text-sky-400" />
                        {formatNumber(post.views)}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center gap-1 text-slate-400">
                        <Heart size={14} className="text-rose-400" />
                        {formatNumber(post.likes)}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center gap-1 text-slate-400">
                        <MessageCircle size={14} className="text-emerald-400" />
                        {formatNumber(post.comments_count)}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-400">
                      {formatDate(post.posted_at)}
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-400">
                      {post.last_synced_at ? `Yangilandi: ${formatTimeAgo(post.last_synced_at)}` : '—'}
                    </td>
                    <td className="py-3 px-4">
                      {post.status === 'deleted' ? (
                        <span className="text-[11px] text-rose-400 font-medium">
                          Instagramda o'chirilgan
                        </span>
                      ) : post.permalink ? (
                        <a
                          href={post.permalink}
                          target="_blank"
                          rel="noreferrer"
                          className="text-pink-400 hover:text-pink-300 inline-flex items-center gap-1 text-xs"
                        >
                          <span>Instagram</span>
                          <ExternalLink size={12} />
                        </a>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="inline-flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handleOpenHistory(post)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-950/60 text-indigo-400 border border-indigo-800 hover:bg-indigo-900 text-xs transition"
                        >
                          <ChartIcon size={12} />
                          <span>Grafik</span>
                        </button>
                        <button
                          onClick={() => handleDeletePost(post.id)}
                          className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition"
                          title="Tarixdan o'chirish"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        <Pagination
          currentPage={page}
          totalCount={totalCount}
          onPageChange={(p) => setPage(p)}
        />
      </div>

      {/* History Modal */}
      {selectedPost && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-white text-base">
                    Post #{selectedPost.id} Ko'rishlar Tarixi
                  </h3>
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800">
                    Har 5 daqiqada yangilanadi
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Vaqt boʻyicha oʻsish grafigi ({historyStats.length} ta yozuv)
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRefreshHistory}
                  disabled={loadingHistory}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 border border-slate-700 transition disabled:opacity-50"
                  title="Qayta tekshirish va yangilash"
                >
                  <RefreshCw size={15} className={loadingHistory ? 'animate-spin' : ''} />
                </button>
                <button
                  onClick={() => setSelectedPost(null)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="p-6">
              {loadingHistory ? (
                <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
                  Tarix yuklanmoqda...
                </div>
              ) : historyStats.length === 0 ? (
                <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
                  Ushbu post uchun hali tekshiruv statistikasi yozilmagan.
                </div>
              ) : (
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={historyStats.map((s) => ({
                        time: new Date(s.checked_at).toLocaleTimeString('uz-UZ', {
                          hour: '2-digit',
                          minute: '2-digit',
                        }),
                        views: s.views,
                        likes: s.likes,
                      }))}
                    >
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
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
