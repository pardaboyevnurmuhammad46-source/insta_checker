import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../../api/client';
import type { Post, PaginatedResponse, InstagramUser } from '../../types';
import { Pagination } from '../../components/Pagination';
import { useToast } from '../../context/ToastContext';
import { formatNumber, formatDate } from '../../utils/format';
import {
  ExternalLink,
  RefreshCw,
  RotateCcw,
  Download,
  AlertTriangle,
  Loader2,
  Eye,
  Heart,
  MessageCircle,
} from 'lucide-react';

export const AdminPostsPage: React.FC = () => {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [ordering, setOrdering] = useState('-views');
  const [userFilter, setUserFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [checkingMetricsId, setCheckingMetricsId] = useState<number | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  const [usersList, setUsersList] = useState<InstagramUser[]>([]);

  const { showToast } = useToast();

  const fetchUsers = async () => {
    try {
      const res = await apiClient.get('/api/users/?page_size=100');
      setUsersList(res.data.results || []);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchPosts = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('page', page.toString());
      if (statusFilter) params.append('status', statusFilter);
      if (ordering) params.append('ordering', ordering);
      if (userFilter) params.append('user', userFilter);
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);

      const response = await apiClient.get<PaginatedResponse<Post>>(`/api/admin/posts/?${params.toString()}`);
      setPosts(response.data.results || []);
      setTotalCount(response.data.count || 0);
    } catch {
      showToast('Postlarni yuklashda xatolik yuz berdi', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, ordering, userFilter, startDate, endDate, showToast]);

  useEffect(() => {
    fetchPosts();
  }, [fetchPosts]);

  const handleCheckMetrics = async (postId: number) => {
    try {
      setCheckingMetricsId(postId);
      const res = await apiClient.post(`/api/posts/${postId}/check-metrics/`);
      showToast(res.data.message || 'Statistikani tekshirish navbatga qoʻyildi', 'success');
      fetchPosts();
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
      showToast(res.data.message || 'Post qayta joylash uchun navbatga qoʻyildi', 'success');
      fetchPosts();
    } catch (err: any) {
      showToast(err.detail || 'Qayta urinishda xatolik', 'error');
    } finally {
      setRetryingId(null);
    }
  };

  const handleExportCSV = async () => {
    try {
      setExporting(true);
      const params = new URLSearchParams();
      if (statusFilter) params.append('status', statusFilter);
      if (userFilter) params.append('user', userFilter);
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);

      const res = await apiClient.get(`/api/admin/export/posts.csv?${params.toString()}`, {
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'posts.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      showToast('CSV muvaffaqiyatli yuklab olindi', 'success');
    } catch {
      showToast('CSV eksport qilishda xatolik', 'error');
    } finally {
      setExporting(false);
    }
  };

  const getStatusBadge = (post: Post) => {
    switch (post.status) {
      case 'published':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
            Joylandi
          </span>
        );
      case 'deleted':
        return (
          <div className="flex flex-col">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950 text-rose-400 border border-rose-800 inline-flex items-center gap-1 w-max">
              <AlertTriangle size={11} /> O'chirilgan
            </span>
            {post.deleted_detected_at && (
              <span className="text-[10px] text-slate-500 mt-0.5">
                {formatDate(post.deleted_detected_at)}
              </span>
            )}
          </div>
        );
      case 'publishing':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-950 text-indigo-400 border border-indigo-800">
            Yuklanmoqda
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
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Postlar (Reels)</h1>
          <p className="text-sm text-slate-400 mt-1">
            Instagram Reels postlari, ko'rishlar monitoringi va boshqaruv
          </p>
        </div>

        <button
          onClick={handleExportCSV}
          disabled={exporting}
          className="inline-flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition shadow-sm disabled:opacity-50 self-start sm:self-auto"
        >
          {exporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
          <span>CSV yuklab olish</span>
        </button>
      </div>

      {/* Filters and Sorting Bar */}
      <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 flex flex-wrap items-center gap-3">
        {/* Status */}
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">Barcha holatlar</option>
          <option value="published">Joylashtirilgan</option>
          <option value="deleted">O'chirilgan</option>
          <option value="failed">Xatolik</option>
          <option value="publishing">Yuklanmoqda</option>
          <option value="queued">Navbatda</option>
        </select>

        {/* User filter */}
        <select
          value={userFilter}
          onChange={(e) => {
            setUserFilter(e.target.value);
            setPage(1);
          }}
          className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 max-w-xs"
        >
          <option value="">Barcha foydalanuvchilar</option>
          {usersList.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name} (ID #{u.id})
            </option>
          ))}
        </select>

        {/* Ordering */}
        <select
          value={ordering}
          onChange={(e) => {
            setOrdering(e.target.value);
            setPage(1);
          }}
          className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="-views">Ko'rishlar (ko'pdan kamga)</option>
          <option value="views">Ko'rishlar (kamdan ko'pga)</option>
          <option value="-posted_at">Joylashtirilgan sana (eng yangi)</option>
          <option value="posted_at">Joylashtirilgan sana (eng eski)</option>
          <option value="-id">Post ID (eng yangi)</option>
        </select>

        {/* Date Filters */}
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setPage(1);
            }}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-slate-300 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            title="Boshlanish sanasi"
          />
          <span className="text-slate-600 text-xs">—</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              setPage(1);
            }}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-slate-300 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            title="Tugash sanasi"
          />
        </div>

        {(statusFilter || userFilter || startDate || endDate) && (
          <button
            onClick={() => {
              setStatusFilter('');
              setUserFilter('');
              setStartDate('');
              setEndDate('');
              setPage(1);
            }}
            className="text-xs text-rose-400 hover:text-rose-300 ml-auto px-2 py-1"
          >
            Filtrlarni tozalash
          </button>
        )}
      </div>

      {/* Posts Table */}
      <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3.5 px-4">Post ID</th>
                <th className="py-3.5 px-4">Foydalanuvchi</th>
                <th className="py-3.5 px-4">Holati</th>
                <th className="py-3.5 px-4">Ko'rishlar</th>
                <th className="py-3.5 px-4">Like</th>
                <th className="py-3.5 px-4">Izoh</th>
                <th className="py-3.5 px-4">Sana</th>
                <th className="py-3.5 px-4">Havola</th>
                <th className="py-3.5 px-4 text-right">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading && (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-500 text-sm">
                    Yuklanmoqda...
                  </td>
                </tr>
              )}
              {!loading && posts.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-500 text-sm">
                    Postlar topilmadi.
                  </td>
                </tr>
              )}
              {!loading &&
                posts.map((post) => (
                  <tr key={post.id} className="hover:bg-slate-900/40 transition">
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-500">#{post.id}</td>
                    <td className="py-3.5 px-4 font-medium text-white">{post.user_name || '—'}</td>
                    <td className="py-3.5 px-4">{getStatusBadge(post)}</td>
                    <td className="py-3.5 px-4 font-semibold text-sky-400">
                      <span className="inline-flex items-center gap-1.5">
                        <Eye size={14} />
                        {formatNumber(post.views)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-flex items-center gap-1 text-slate-400">
                        <Heart size={14} className="text-rose-400" />
                        {formatNumber(post.likes)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-flex items-center gap-1 text-slate-400">
                        <MessageCircle size={14} className="text-emerald-400" />
                        {formatNumber(post.comments_count)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-400">
                      {formatDate(post.posted_at)}
                    </td>
                    <td className="py-3.5 px-4">
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
                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handleCheckMetrics(post.id)}
                          disabled={checkingMetricsId === post.id}
                          className="px-2.5 py-1 rounded-lg bg-indigo-950/60 text-indigo-400 border border-indigo-800 hover:bg-indigo-900 text-xs transition inline-flex items-center gap-1 disabled:opacity-50"
                          title="Hozir tekshirish"
                        >
                          <RefreshCw
                            size={12}
                            className={checkingMetricsId === post.id ? 'animate-spin' : ''}
                          />
                          <span>Tekshirish</span>
                        </button>
                        {post.status === 'failed' && (
                          <button
                            onClick={() => handleRetry(post.id)}
                            disabled={retryingId === post.id}
                            className="px-2.5 py-1 rounded-lg bg-amber-950/60 text-amber-400 border border-amber-800 hover:bg-amber-900 text-xs transition inline-flex items-center gap-1 disabled:opacity-50"
                            title="Qayta joylash"
                          >
                            <RotateCcw
                              size={12}
                              className={retryingId === post.id ? 'animate-spin' : ''}
                            />
                            <span>Qayta joylash</span>
                          </button>
                        )}
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
    </div>
  );
};
