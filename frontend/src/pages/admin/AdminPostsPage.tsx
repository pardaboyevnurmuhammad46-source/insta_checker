import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../../api/client';
import type { CampaignPost, CampaignConfig, PaginatedResponse } from '../../types';
import { Pagination } from '../../components/Pagination';
import { useToast } from '../../context/ToastContext';
import { formatNumber, formatDate, formatTimeAgo } from '../../utils/format';
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
  Search,
  Film,
  Trash2,
  Sparkles,
  Mic,
  Award,
  CheckCircle2,
  AlertCircle,
  X,
} from 'lucide-react';

export const AdminPostsPage: React.FC = () => {
  const [posts, setPosts] = useState<CampaignPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [checkingMetricsId, setCheckingMetricsId] = useState<number | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  // AI Campaign Configuration states
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [config, setConfig] = useState<CampaignConfig | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  // Selected post for AI Inspection modal
  const [selectedPostForAI, setSelectedPostForAI] = useState<CampaignPost | null>(null);
  const [reverifyingAI, setReverifyingAI] = useState(false);

  const { showToast } = useToast();

  const fetchConfig = async () => {
    try {
      const res = await apiClient.get<CampaignConfig>('/api/admin/campaign-config/');
      setConfig(res.data);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!config) return;
    try {
      setSavingConfig(true);
      const res = await apiClient.put<CampaignConfig>('/api/admin/campaign-config/', config);
      setConfig(res.data);
      showToast('AI Aksiya mavzusi va qoidalari muvaffaqiyatli saqlandi', 'success');
      setConfigModalOpen(false);
    } catch {
      showToast('Sozlamalarni saqlashda xatolik yuz berdi', 'error');
    } finally {
      setSavingConfig(false);
    }
  };

  const handleReverifyAI = async (postId: number) => {
    try {
      setReverifyingAI(true);
      const res = await apiClient.post(`/api/admin/posts/${postId}/re-verify-ai/`);
      showToast(res.data.message || 'Post yangi mavzu boʻyicha AI tekshiruvidan oʻtdi', 'success');
      fetchPosts();
      if (selectedPostForAI && selectedPostForAI.id === postId) {
        setSelectedPostForAI((prev) => prev ? {
          ...prev,
          ai_verified: res.data.ai_verified,
          ai_confidence: res.data.ai_confidence,
          ai_detection_source: res.data.ai_detection_source,
          transcript: res.data.transcript,
          ai_explanation: res.data.ai_explanation,
          points_awarded: res.data.points_awarded,
        } : null);
      }
    } catch (err: any) {
      showToast(err.detail || 'Qayta tekshirishda xatolik', 'error');
    } finally {
      setReverifyingAI(false);
    }
  };

  const fetchPosts = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('page', page.toString());
      if (statusFilter) params.append('status', statusFilter);
      if (sourceFilter) params.append('source', sourceFilter);
      if (searchQuery) params.append('search', searchQuery);
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);

      const response = await apiClient.get<PaginatedResponse<CampaignPost>>(`/api/admin/campaign-posts/?${params.toString()}`);
      setPosts(response.data.results || []);
      setTotalCount(response.data.count || 0);
    } catch {
      showToast('Postlarni yuklashda xatolik yuz berdi', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, sourceFilter, searchQuery, startDate, endDate, showToast]);

  useEffect(() => {
    fetchPosts();
  }, [fetchPosts]);

  const handleCheckMetrics = async (postId: number) => {
    try {
      setCheckingMetricsId(postId);
      const res = await apiClient.post(`/api/posts/${postId}/check-metrics/`);
      showToast(res.data.message || 'Statistikani tekshirish navbatga qoʻyildi', 'success');
      setTimeout(() => {
        fetchPosts();
      }, 2000);
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

  const handleDeletePost = async (postId: number) => {
    if (!window.confirm("Haqiqatan ham ushbu postni o'chirmoqchimisiz?")) {
      return;
    }
    try {
      await apiClient.delete(`/api/user/posts/${postId}/`);
      showToast("Post o'chirildi", 'success');
      fetchPosts();
    } catch {
      showToast("Postni o'chirishda xatolik yuz berdi", 'error');
    }
  };

  const handleExportCSV = async () => {
    try {
      setExporting(true);
      const params = new URLSearchParams();
      if (statusFilter) params.append('status', statusFilter);
      if (sourceFilter) params.append('source', sourceFilter);
      if (searchQuery) params.append('search', searchQuery);
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
      case 'deleted':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950 text-rose-400 border border-rose-800 inline-flex items-center gap-1 w-max">
            <AlertTriangle size={11} /> O'chirilgan
          </span>
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

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            onClick={() => setConfigModalOpen(true)}
            className="inline-flex items-center gap-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition shadow-md"
          >
            <Sparkles size={16} />
            <span>AI Mavzu & Qoidalar</span>
          </button>
          <button
            onClick={handleExportCSV}
            disabled={exporting}
            className="inline-flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition shadow-sm disabled:opacity-50"
          >
            {exporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            <span>CSV yuklab olish</span>
          </button>
        </div>
      </div>

      {/* Filters and Sorting Bar */}
      <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 flex flex-wrap items-center gap-3">
        {/* Qidiruv */}
        <div className="relative min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Foydalanuvchi yoki kod..."
            className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 placeholder:text-slate-600"
          />
        </div>

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
          <option value="verified">Tasdiqlangan (Verified)</option>
          <option value="revoked">Bekor qilingan (Revoked)</option>
          <option value="rejected">Rad etilgan (Rejected)</option>
          <option value="published">Joylashtirilgan</option>
          <option value="queued">Navbatda</option>
          <option value="failed">Xatolik</option>
        </select>

        {/* Source */}
        <select
          value={sourceFilter}
          onChange={(e) => {
            setSourceFilter(e.target.value);
            setPage(1);
          }}
          className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">Barcha manbalar</option>
          <option value="site">Sayt (site)</option>
          <option value="self">O'zim (self)</option>
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

        {(statusFilter || sourceFilter || searchQuery || startDate || endDate) && (
          <button
            onClick={() => {
              setStatusFilter('');
              setSourceFilter('');
              setSearchQuery('');
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
                <th className="py-3.5 px-4">Video</th>
                <th className="py-3.5 px-4">ID</th>
                <th className="py-3.5 px-4">Foydalanuvchi</th>
                <th className="py-3.5 px-4">Kod</th>
                <th className="py-3.5 px-4">Holati</th>
                <th className="py-3.5 px-4">AI Tahlili</th>
                <th className="py-3.5 px-4">Manba</th>
                <th className="py-3.5 px-4">Ko'rishlar</th>
                <th className="py-3.5 px-4">Like</th>
                <th className="py-3.5 px-4">Izoh</th>
                <th className="py-3.5 px-4">Sana</th>
                <th className="py-3.5 px-4">Sinxronizatsiya</th>
                <th className="py-3.5 px-4">Havola</th>
                <th className="py-3.5 px-4 text-right">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading && (
                <tr>
                  <td colSpan={14} className="py-12 text-center text-slate-500 text-sm">
                    Yuklanmoqda...
                  </td>
                </tr>
              )}
              {!loading && posts.length === 0 && (
                <tr>
                  <td colSpan={14} className="py-12 text-center text-slate-500 text-sm">
                    Postlar topilmadi.
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
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-500">#{post.id}</td>
                    <td className="py-3.5 px-4 font-medium text-white">{post.username || '—'}</td>
                    <td className="py-3.5 px-4 font-mono font-semibold text-amber-400">
                      {post.code || '—'}
                    </td>
                    <td className="py-3.5 px-4">{getStatusBadge(post)}</td>
                    <td className="py-3.5 px-4">
                      {post.ai_verified ? (
                        <button
                          type="button"
                          onClick={() => setSelectedPostForAI(post)}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 transition shadow-sm"
                          title="Batafsil AI tahlilini ko'rish"
                        >
                          <Sparkles size={12} className="text-emerald-400" />
                          <span>Tasdiqlandi</span>
                          <span className="text-[10px] text-emerald-400 font-normal">
                            (+{post.points_awarded || 100})
                          </span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setSelectedPostForAI(post)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20 hover:bg-amber-500/20 transition"
                          title="AI tahlilini ko'rish yoki qayta tekshirish"
                        >
                          <AlertCircle size={12} />
                          <span>Tekshirish</span>
                        </button>
                      )}
                    </td>
                    <td className="py-3.5 px-4">
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
                    <td className="py-3.5 px-4 text-xs text-slate-400">
                      {post.last_synced_at ? `Yangilandi: ${formatTimeAgo(post.last_synced_at)}` : '—'}
                    </td>
                    <td className="py-3.5 px-4">
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
                          className="px-2 py-1 rounded-lg bg-indigo-950/60 text-indigo-400 border border-indigo-800 hover:bg-indigo-900 text-xs transition inline-flex items-center gap-1 disabled:opacity-50"
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
                            className="px-2 py-1 rounded-lg bg-amber-950/60 text-amber-400 border border-amber-800 hover:bg-amber-900 text-xs transition inline-flex items-center gap-1 disabled:opacity-50"
                            title="Qayta joylash"
                          >
                            <RotateCcw
                              size={12}
                              className={retryingId === post.id ? 'animate-spin' : ''}
                            />
                            <span>Qayta joylash</span>
                          </button>
                        )}
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

      {/* AI Kampaniya & Mavzu Sozlamalari Modali */}
      {configModalOpen && config && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-xl overflow-hidden shadow-2xl space-y-0">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-purple-500/20 text-purple-400 rounded-xl border border-purple-500/30">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">AI Reklama Mavzusi va Qoidalari</h3>
                  <p className="text-xs text-slate-400 mt-0.5">AI videolarni aynan qaysi mavzu va so'zlar bo'yicha tekshirishini belgilang</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setConfigModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveConfig} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Aksiya / Kampaniya Mavzusi (Topic)
                </label>
                <input
                  type="text"
                  value={config.topic}
                  onChange={(e) => setConfig({ ...config, topic: e.target.value })}
                  placeholder="Masalan: Kuzgi Megachegirma aksiyasi"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <span className="text-[11px] text-slate-500 mt-1 block">
                  AI videolarni shu mavzu doirasida tahlil qiladi.
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Brend Nomi
                  </label>
                  <input
                    type="text"
                    value={config.brand_name}
                    onChange={(e) => setConfig({ ...config, brand_name: e.target.value })}
                    placeholder="InstaChecker"
                    required
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Tasdiqlanganda Beriladigan Ball
                  </label>
                  <input
                    type="number"
                    value={config.points_reward}
                    onChange={(e) => setConfig({ ...config, points_reward: parseInt(e.target.value) || 0 })}
                    min={10}
                    max={1000}
                    required
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Majburiy Kalit So'zlar va Heshteglar (vergul bilan)
                </label>
                <input
                  type="text"
                  value={config.required_keywords}
                  onChange={(e) => setConfig({ ...config, required_keywords: e.target.value })}
                  placeholder="instachecker, brend, #brend, homiy, aksiya"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <span className="text-[11px] text-slate-500 mt-1 block">
                  Ushbu so'zlar videodagi nutqda (audio) yoki post tavsifida (caption) qidiriladi.
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  AI Uchun Yo'riqnoma (Prompt / Instructions)
                </label>
                <textarea
                  value={config.ai_prompt_instructions}
                  onChange={(e) => setConfig({ ...config, ai_prompt_instructions: e.target.value })}
                  rows={3}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 leading-relaxed"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setConfigModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-300 hover:text-white hover:bg-slate-800 text-sm font-medium transition"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={savingConfig}
                  className="inline-flex items-center gap-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white px-5 py-2 rounded-xl text-sm font-semibold transition disabled:opacity-50 shadow-md"
                >
                  {savingConfig ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                  <span>Qoidalarni Saqlash</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AI Post Tahlili Batafsil Modali */}
      {selectedPostForAI && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl space-y-0">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-purple-500/20 text-purple-400 rounded-xl border border-purple-500/30">
                  <Sparkles size={20} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    Post #{selectedPostForAI.id} — AI Reklama & Ovoz Tahlili
                  </h3>
                  <span className="text-xs text-slate-400">
                    Foydalanuvchi: @{selectedPostForAI.username} • Kod: #{selectedPostForAI.code}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedPostForAI(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto">
              {/* Status Header */}
              <div className="flex items-center justify-between p-3.5 bg-slate-950 rounded-xl border border-slate-800">
                <div className="flex items-center gap-2">
                  {selectedPostForAI.ai_verified ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                      <CheckCircle2 size={14} />
                      <span>Reklama Tasdiqlandi</span>
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                      <AlertCircle size={14} />
                      <span>Reklama aniqlanmadi</span>
                    </span>
                  )}
                  {Boolean(selectedPostForAI.points_awarded) && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-400/15 text-amber-400 border border-amber-400/30">
                      <Award size={13} />
                      <span>+{selectedPostForAI.points_awarded} Ball</span>
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400">
                  <span>Aniqlash manbasi: </span>
                  <span className="font-semibold text-indigo-400 uppercase">
                    {selectedPostForAI.ai_detection_source || 'AUTO'}
                  </span>
                </div>
              </div>

              {/* Ovozli matn (Transcript) */}
              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Mic size={14} className="text-pink-400" />
                  Videodagi Ovoz Matni (Speech Transcript):
                </span>
                <div className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-200 italic leading-relaxed">
                  "{selectedPostForAI.transcript || 'Ovozli nutqda brend tilga olingan yoki tahlil davom etmoqda.'}"
                </div>
              </div>

              {/* Tavsif (Caption) */}
              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                  Instagram Post Tavsifi (Caption):
                </span>
                <div className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-300 font-mono">
                  {selectedPostForAI.code ? `Post kodi: #${selectedPostForAI.code}` : 'Tavsif mavjud emas'}
                </div>
              </div>

              {/* AI Xulosasi */}
              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Sparkles size={14} className="text-purple-400" />
                  AI Tahlil Xulosasi:
                </span>
                <div className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-300 leading-relaxed">
                  {selectedPostForAI.ai_explanation || "AI tahlili muvaffaqiyatli amalga oshirildi."}
                </div>
              </div>

              {/* Action: Re-run AI */}
              <div className="flex items-center justify-between pt-3 border-t border-slate-800">
                <div className="text-xs text-slate-400">
                  Aktiv mavzu bo'yicha qayta tekshirish
                </div>
                <button
                  type="button"
                  onClick={() => handleReverifyAI(selectedPostForAI.id)}
                  disabled={reverifyingAI}
                  className="inline-flex items-center gap-2 bg-purple-600 hover:bg-purple-500 text-white px-4 py-2 rounded-xl text-xs font-bold transition shadow-md disabled:opacity-50"
                >
                  {reverifyingAI ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                  <span>AI Qayta Tekshirsin</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
