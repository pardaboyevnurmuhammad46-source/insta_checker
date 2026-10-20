import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { Post, PaginatedResponse } from '../types';
import { Pagination } from '../components/Pagination';
import { useToast } from '../context/ToastContext';
import { ExternalLink, RefreshCw, RotateCcw, AlertCircle } from 'lucide-react';

export const PostsPage: React.FC = () => {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [ordering, setOrdering] = useState('-posted_at');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [checkingMetricsId, setCheckingMetricsId] = useState<number | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);

  const { showToast } = useToast();

  const fetchPosts = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('page', page.toString());
      if (statusFilter) params.append('status', statusFilter);
      if (ordering) params.append('ordering', ordering);

      const response = await apiClient.get<PaginatedResponse<Post>>(`/api/posts/?${params.toString()}`);
      setPosts(response.data.results);
      setTotalCount(response.data.count);
    } catch {
      showToast('Postlarni yuklashda xatolik yuz berdi', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, ordering, showToast]);

  useEffect(() => {
    fetchPosts();
  }, [fetchPosts]);

  const handleCheckMetrics = async (postId: number) => {
    try {
      setCheckingMetricsId(postId);
      const res = await apiClient.post(`/api/posts/${postId}/check-metrics/`);
      showToast(res.data.message || 'Statistikani tekshirish navbatga qoʻyildi', 'success');
    } catch (err: any) {
      showToast(err.detail || 'Xatolik yuz berdi', 'error');
    } finally {
      setCheckingMetricsId(null);
    }
  };

  const handleRetry = async (postId: number) => {
    try {
      setRetryingId(postId);
      const res = await apiClient.post(`/api/posts/${postId}/retry/`);
      showToast(res.data.message || 'Post qayta navbatga qoʻyildi', 'success');
      fetchPosts();
    } catch (err: any) {
      showToast(err.detail || 'Qayta urinishda xatolik', 'error');
    } finally {
      setRetryingId(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'published':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">Published</span>;
      case 'publishing':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">Publishing</span>;
      case 'queued':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">Queued</span>;
      case 'failed':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800">Failed</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Postlar (Reels)</h1>
          <p className="text-sm text-slate-500 mt-1">Instagram sahifalariga joylangan Reels videolari va statistikasi</p>
        </div>
      </div>

      {/* Filters and Sorting */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col sm:flex-row gap-3">
        <div className="w-full sm:w-56">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          >
            <option value="">Barcha statuslar</option>
            <option value="published">Published</option>
            <option value="publishing">Publishing</option>
            <option value="queued">Queued</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        <div className="w-full sm:w-56">
          <select
            value={ordering}
            onChange={(e) => {
              setOrdering(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          >
            <option value="-posted_at">Eng yangi postlar</option>
            <option value="posted_at">Eng eski postlar</option>
            <option value="-views">Eng koʻp koʻrilganlar</option>
            <option value="views">Eng kam koʻrilganlar</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm text-left">
            <thead className="bg-slate-50 text-slate-600 font-semibold uppercase text-xs tracking-wider">
              <tr>
                <th className="px-6 py-3">ID</th>
                <th className="px-6 py-3">Foydalanuvchi</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Koʻrishlar</th>
                <th className="px-6 py-3">Layklar</th>
                <th className="px-6 py-3">Kommentlar</th>
                <th className="px-6 py-3">Reels Havolasi</th>
                <th className="px-6 py-3">Joylandi</th>
                <th className="px-6 py-3">Keyingi tekshiruv</th>
                <th className="px-6 py-3 text-right">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan={10} className="px-6 py-8 text-center text-slate-400">
                    Yuklanmoqda...
                  </td>
                </tr>
              ) : posts.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-6 py-8 text-center text-slate-500">
                    Postlar topilmadi
                  </td>
                </tr>
              ) : (
                posts.map((post) => (
                  <tr key={post.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-mono text-xs text-slate-500">{post.id}</td>
                    <td className="px-6 py-4 font-medium text-slate-900">{post.user_name}</td>
                    <td className="px-6 py-4">
                      {getStatusBadge(post.status)}
                      {post.error && (
                        <div className="mt-1 flex items-center gap-1 text-xs text-rose-600" title={post.error}>
                          <AlertCircle size={12} />
                          <span className="truncate max-w-[120px]">{post.error}</span>
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 font-semibold text-slate-800">{post.views.toLocaleString()}</td>
                    <td className="px-6 py-4 text-slate-600">{post.likes.toLocaleString()}</td>
                    <td className="px-6 py-4 text-slate-600">{post.comments_count.toLocaleString()}</td>
                    <td className="px-6 py-4">
                      {post.permalink ? (
                        <a
                          href={post.permalink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                        >
                          <span>Instagram Reels</span>
                          <ExternalLink size={12} />
                        </a>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {post.posted_at ? new Date(post.posted_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {post.next_check_at ? new Date(post.next_check_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-6 py-4 text-right space-x-2 whitespace-nowrap">
                      {post.status === 'published' && (
                        <button
                          onClick={() => handleCheckMetrics(post.id)}
                          disabled={checkingMetricsId === post.id}
                          className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-md transition-colors"
                          title="Statistikani hozir tekshirish"
                        >
                          <RefreshCw size={12} className={checkingMetricsId === post.id ? 'animate-spin' : ''} />
                          <span>Tekshirish</span>
                        </button>
                      )}

                      {post.status === 'failed' && (
                        <button
                          onClick={() => handleRetry(post.id)}
                          disabled={retryingId === post.id}
                          className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 text-xs font-medium rounded-md transition-colors"
                          title="Qayta joylash"
                        >
                          <RotateCcw size={12} className={retryingId === post.id ? 'animate-spin' : ''} />
                          <span>Qayta joylash</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          currentPage={page}
          totalCount={totalCount}
          pageSize={50}
          onPageChange={(newPage) => setPage(newPage)}
        />
      </div>
    </div>
  );
};
