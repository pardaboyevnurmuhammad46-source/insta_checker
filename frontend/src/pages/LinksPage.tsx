import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { UniqueLink, InstagramUser, PaginatedResponse } from '../types';
import { Pagination } from '../components/Pagination';
import { useToast } from '../context/ToastContext';
import { Copy, Check, Plus, RotateCcw, UploadCloud } from 'lucide-react';

export const LinksPage: React.FC = () => {
  const [links, setLinks] = useState<UniqueLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Users for select dropdown
  const [users, setUsers] = useState<InstagramUser[]>([]);

  // Create Link Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<number | ''>('');
  const [videoSource, setVideoSource] = useState<'default' | 'existing' | 'upload'>('default');
  const [availableVideos, setAvailableVideos] = useState<any[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState<number | ''>('');
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [expiresAt, setExpiresAt] = useState('');
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Resend action loading
  const [resendingId, setResendingId] = useState<number | null>(null);

  // Copied token state
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const { showToast } = useToast();

  const fetchLinks = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('page', page.toString());
      if (statusFilter) params.append('status', statusFilter);

      const response = await apiClient.get<PaginatedResponse<UniqueLink>>(`/api/links/?${params.toString()}`);
      setLinks(response.data.results);
      setTotalCount(response.data.count);
    } catch {
      showToast('Linklarni yuklashda xatolik yuz berdi', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, showToast]);

  useEffect(() => {
    fetchLinks();
  }, [fetchLinks]);

  // Fetch users and videos for dropdown when modal opens
  useEffect(() => {
    if (isModalOpen) {
      if (users.length === 0) {
        apiClient.get<PaginatedResponse<InstagramUser>>('/api/users/?page_size=100').then((res) => {
          setUsers(res.data.results);
        });
      }
      apiClient.get('/api/videos/?page_size=100').then((res) => {
        const list = res.data.results || res.data || [];
        setAvailableVideos(list);
      });
    }
  }, [isModalOpen, users.length]);

  const handleCopy = (id: number, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    showToast('Link nusxalandi!', 'success');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleResend = async (linkId: number) => {
    try {
      setResendingId(linkId);
      const res = await apiClient.post(`/api/links/${linkId}/resend/`);
      showToast(res.data.message || 'Link qayta pending holatiga oʻtkazildi', 'success');
      fetchLinks();
    } catch (err: any) {
      showToast(err.detail || 'Qayta yuborib boʻlmadi', 'error');
    } finally {
      setResendingId(null);
    }
  };

  const handleCreateLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUserId) {
      showToast('Iltimos, foydalanuvchini tanlang', 'error');
      return;
    }

    if (videoSource === 'upload') {
      if (!videoFile) {
        showToast('Iltimos, yangi video faylni tanlang', 'error');
        return;
      }
      if (!videoFile.name.toLowerCase().endsWith('.mp4')) {
        showToast('Faqat .mp4 formatidagi video qabul qilinadi', 'error');
        return;
      }
      if (videoFile.size > 100 * 1024 * 1024) {
        showToast('Video hajmi 100MB dan oshmasligi kerak', 'error');
        return;
      }
    } else if (videoSource === 'existing') {
      if (!selectedVideoId) {
        showToast('Iltimos, kutubxonadan videoni tanlang', 'error');
        return;
      }
    }

    const formData = new FormData();
    formData.append('user', selectedUserId.toString());

    if (videoSource === 'upload' && videoFile) {
      formData.append('video', videoFile);
    } else if (videoSource === 'existing' && selectedVideoId) {
      formData.append('video', selectedVideoId.toString());
    }

    if (expiresAt) {
      formData.append('expires_at', new Date(expiresAt).toISOString());
    }

    try {
      setSubmitting(true);
      setUploadProgress(videoSource === 'upload' ? 0 : null);

      await apiClient.post('/api/links/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total && videoSource === 'upload') {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
          }
        },
      });

      showToast('Link muvaffaqiyatli yaratildi', 'success');
      setIsModalOpen(false);
      setSelectedUserId('');
      setVideoSource('default');
      setSelectedVideoId('');
      setVideoFile(null);
      setExpiresAt('');
      setUploadProgress(null);
      fetchLinks();
    } catch (err: any) {
      const msg = err.errors?.video?.[0] || err.detail || 'Link yaratishda xatolik yuz berdi';
      showToast(msg, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'posted':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">Joylandi</span>;
      case 'opened':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">Ochilgan</span>;
      case 'failed':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800">Xatolik</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">Kutilmoqda</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Unikal Linklar</h1>
          <p className="text-sm text-slate-500 mt-1">Foydalanuvchilarga yuboriladigan bir martalik Reels linklari</p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium shadow-sm transition-colors"
        >
          <Plus size={16} />
          <span>Link yaratish</span>
        </button>
      </div>

      {/* Filter */}
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
            <option value="pending">Kutilmoqda (Pending)</option>
            <option value="opened">Ochilgan (Opened)</option>
            <option value="posted">Joylandi (Posted)</option>
            <option value="failed">Xatolik (Failed)</option>
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
                <th className="px-6 py-3">Unikal Manzil (Full Link)</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Amal qilish muddati</th>
                <th className="px-6 py-3">Yaratilgan</th>
                <th className="px-6 py-3 text-right">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-slate-400">
                    Yuklanmoqda...
                  </td>
                </tr>
              ) : links.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-slate-500">
                    Linklar mavjud emas
                  </td>
                </tr>
              ) : (
                links.map((link) => (
                  <tr key={link.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-mono text-xs text-slate-500">{link.id}</td>
                    <td className="px-6 py-4 font-medium text-slate-900">{link.user_name}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2 max-w-xs">
                        <span className="font-mono text-xs text-slate-600 truncate">{link.full_link}</span>
                        <button
                          onClick={() => handleCopy(link.id, link.full_link)}
                          className="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-slate-600 transition-colors flex-shrink-0"
                          title="Nusxalash"
                        >
                          {copiedId === link.id ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
                        </button>
                      </div>
                    </td>
                    <td className="px-6 py-4">{getStatusBadge(link.status)}</td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {link.expires_at ? new Date(link.expires_at).toLocaleString() : 'Cheksiz'}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(link.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {link.status === 'failed' && (
                        <button
                          onClick={() => handleResend(link.id)}
                          disabled={resendingId === link.id}
                          className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 text-xs font-medium rounded-md transition-colors"
                        >
                          <RotateCcw size={12} className={resendingId === link.id ? 'animate-spin' : ''} />
                          <span>Qayta yuborish</span>
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

      {/* Create Link Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <h2 className="text-lg font-bold text-slate-900">Yangi Unikal Link Yaratish</h2>
            <form onSubmit={handleCreateLink} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Foydalanuvchi
                </label>
                <select
                  required
                  value={selectedUserId}
                  onChange={(e) => setSelectedUserId(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                >
                  <option value="">Foydalanuvchini tanlang</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({u.status})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Reels Videosini Tanlash
                </label>
                <div className="grid grid-cols-3 gap-2 mb-3">
                  <button
                    type="button"
                    onClick={() => setVideoSource('default')}
                    className={`py-2 px-2 text-xs font-medium rounded-lg border text-center transition ${
                      videoSource === 'default'
                        ? 'bg-indigo-50 border-indigo-500 text-indigo-700'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    Avtomatik (Default)
                  </button>
                  <button
                    type="button"
                    onClick={() => setVideoSource('existing')}
                    className={`py-2 px-2 text-xs font-medium rounded-lg border text-center transition ${
                      videoSource === 'existing'
                        ? 'bg-indigo-50 border-indigo-500 text-indigo-700'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    Kutubxonadan
                  </button>
                  <button
                    type="button"
                    onClick={() => setVideoSource('upload')}
                    className={`py-2 px-2 text-xs font-medium rounded-lg border text-center transition ${
                      videoSource === 'upload'
                        ? 'bg-indigo-50 border-indigo-500 text-indigo-700'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    Yangi yuklash
                  </button>
                </div>

                {videoSource === 'default' && (
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600">
                    Foydalanuvchining o'z shaxsiy videosi (agar bor bo'lsa) yoki tizimning umumiy promo videosi avtomatik biriktiriladi.
                  </div>
                )}

                {videoSource === 'existing' && (
                  <div>
                    <select
                      value={selectedVideoId}
                      onChange={(e) => setSelectedVideoId(Number(e.target.value))}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                    >
                      <option value="">Videoni tanlang</option>
                      {availableVideos.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.title} {v.is_default ? '(Umumiy default)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {videoSource === 'upload' && (
                  <div className="border-2 border-dashed border-slate-300 rounded-lg p-4 text-center hover:bg-slate-50 transition-colors">
                    <input
                      type="file"
                      accept=".mp4"
                      onChange={(e) => {
                        if (e.target.files && e.target.files[0]) {
                          setVideoFile(e.target.files[0]);
                        }
                      }}
                      className="hidden"
                      id="video-upload"
                    />
                    <label htmlFor="video-upload" className="cursor-pointer flex flex-col items-center">
                      <UploadCloud size={32} className="text-slate-400 mb-2" />
                      <span className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
                        {videoFile ? videoFile.name : 'Video faylni tanlang'}
                      </span>
                      <span className="text-xs text-slate-400 mt-1">MP4 formatida, 100MB gacha</span>
                    </label>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Amal qilish muddati (ixtiyoriy)
                </label>
                <input
                  type="datetime-local"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {uploadProgress !== null && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-slate-500">
                    <span>Yuklanmoqda...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    ></div>
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium disabled:opacity-50"
                >
                  {submitting ? 'Yuklanmoqda...' : 'Yaratish'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
