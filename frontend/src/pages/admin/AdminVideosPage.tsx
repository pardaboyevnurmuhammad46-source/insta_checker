import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import type { VideoItem, InstagramUser, PaginatedResponse } from '../../types';
import { formatDate } from '../../utils/format';
import { Pagination } from '../../components/Pagination';
import {
  Upload,
  Star,
  UserCheck,
  Power,
  Trash2,
  X,
  Loader2,
  ExternalLink,
} from 'lucide-react';

export const AdminVideosPage: React.FC = () => {
  const { showToast } = useToast();

  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Upload Modal State
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDefault, setIsDefault] = useState(false);
  const [ownerId, setOwnerId] = useState('');
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);

  // Assign Owner Modal State
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  const [targetOwnerId, setTargetOwnerId] = useState('');
  const [assigning, setAssigning] = useState(false);

  // Users list for dropdown
  const [usersList, setUsersList] = useState<InstagramUser[]>([]);

  const fetchVideos = async (pageNumber: number) => {
    try {
      setLoading(true);
      const res = await apiClient.get<PaginatedResponse<VideoItem>>(`/api/videos/?page=${pageNumber}`);
      setVideos(res.data.results || []);
      setTotalCount(res.data.count || 0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const res = await apiClient.get('/api/users/?page_size=100');
      setUsersList(res.data.results || []);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchVideos(page);
  }, [page]);

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.mp4')) {
      showToast('Faqat .mp4 formatidagi videolarni yuklash mumkin', 'error');
      e.target.value = '';
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      showToast('Video hajmi 100MB dan oshmasligi kerak', 'error');
      e.target.value = '';
      return;
    }

    setSelectedFile(file);
    if (!title) {
      setTitle(file.name.replace(/\.[^/.]+$/, ''));
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !title) {
      showToast('Fayl va sarlavhani kiriting', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('title', title);
    formData.append('file', selectedFile);
    if (isDefault) formData.append('is_default', 'true');
    if (ownerId) formData.append('owner', ownerId);

    try {
      setUploading(true);
      setUploadProgress(0);

      await apiClient.post('/api/videos/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
          }
        },
      });

      showToast('Video muvaffaqiyatli yuklandi', 'success');
      setUploadModalOpen(false);
      setTitle('');
      setSelectedFile(null);
      setIsDefault(false);
      setOwnerId('');
      setUploadProgress(null);
      fetchVideos(1);
    } catch (err: any) {
      showToast(err.response?.data?.file?.[0] || 'Yuklashda xatolik yuz berdi', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleSetDefault = async (v: VideoItem) => {
    try {
      const res = await apiClient.post(`/api/videos/${v.id}/set-default/`);
      showToast(res.data.message || 'Video umumiy (default) qilindi', 'success');
      fetchVideos(page);
    } catch {
      showToast('Xatolik yuz berdi', 'error');
    }
  };

  const handleToggleActive = async (v: VideoItem) => {
    try {
      await apiClient.patch(`/api/videos/${v.id}/`, {
        is_active: !v.is_active,
      });
      showToast(`Video ${!v.is_active ? 'faollashtirildi' : 'faolsizlantirildi'}`, 'success');
      fetchVideos(page);
    } catch {
      showToast('Holatni oʻzgartirib boʻlmadi', 'error');
    }
  };

  const handleDelete = async (v: VideoItem) => {
    if (!window.confirm(`'${v.title}' videosini rostdan ham oʻchirmoqchimisiz?`)) return;

    try {
      await apiClient.delete(`/api/videos/${v.id}/`);
      showToast('Video oʻchirildi', 'success');
      fetchVideos(page);
    } catch {
      showToast('Oʻchirishda xatolik yuz berdi', 'error');
    }
  };

  const handleAssignOwnerSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedVideo) return;

    try {
      setAssigning(true);
      await apiClient.post(`/api/videos/${selectedVideo.id}/assign-owner/`, {
        owner_id: targetOwnerId || null,
      });
      showToast('Video egasi muvaffaqiyatli yangilandi', 'success');
      setAssignModalOpen(false);
      fetchVideos(page);
    } catch {
      showToast('Biriktirishda xatolik yuz berdi', 'error');
    } finally {
      setAssigning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Videolar Kutubxonasi
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Instagram Reels uchun umumiy va shaxsiy videolarni boshqarish
          </p>
        </div>

        <button
          onClick={() => setUploadModalOpen(true)}
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition shadow-md self-start sm:self-auto"
        >
          <Upload size={16} />
          <span>Yangi video yuklash</span>
        </button>
      </div>

      {/* Videos Table */}
      <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3.5 px-4">ID</th>
                <th className="py-3.5 px-4">Sarlavha</th>
                <th className="py-3.5 px-4">Turi</th>
                <th className="py-3.5 px-4">Egasi (User)</th>
                <th className="py-3.5 px-4">Holati</th>
                <th className="py-3.5 px-4">Yuklangan</th>
                <th className="py-3.5 px-4 text-right">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500 text-sm">
                    Yuklanmoqda...
                  </td>
                </tr>
              )}
              {!loading && videos.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500 text-sm">
                    Videolar mavjud emas.
                  </td>
                </tr>
              )}
              {!loading &&
                videos.map((v) => (
                  <tr key={v.id} className="hover:bg-slate-900/40 transition">
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-500">#{v.id}</td>
                    <td className="py-3.5 px-4">
                      <div className="font-medium text-white flex items-center gap-2">
                        <span>{v.title}</span>
                        {(v.video_url || v.file) && (
                          <a
                            href={v.video_url || v.file}
                            target="_blank"
                            rel="noreferrer"
                            className="text-indigo-400 hover:text-indigo-300 text-xs inline-flex items-center"
                            title="Videoni ochish"
                          >
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      {v.is_default ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950 text-amber-300 border border-amber-800">
                          <Star size={11} /> Umumiy (Default)
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">Shaxsiy</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-xs">
                      {v.owner_name ? (
                        <span className="text-slate-200 font-medium">{v.owner_name}</span>
                      ) : (
                        <span className="text-slate-500 italic">Barchaga umumiy</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4">
                      {v.is_active ? (
                        <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                          Faol
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400">
                          Faol emas
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-400">
                      {formatDate(v.created_at)}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {!v.is_default && (
                          <button
                            onClick={() => handleSetDefault(v)}
                            className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-amber-400 hover:bg-slate-800 text-xs transition"
                            title="Umumiy (Default) video qilish"
                          >
                            <Star size={14} />
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setSelectedVideo(v);
                            setTargetOwnerId(v.owner ? v.owner.toString() : '');
                            setAssignModalOpen(true);
                          }}
                          className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-indigo-400 hover:bg-slate-800 text-xs transition"
                          title="Userga biriktirish"
                        >
                          <UserCheck size={14} />
                        </button>
                        <button
                          onClick={() => handleToggleActive(v)}
                          className={`p-1.5 rounded-lg border text-xs transition ${
                            v.is_active
                              ? 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
                              : 'bg-emerald-950/60 border-emerald-800 text-emerald-400'
                          }`}
                          title={v.is_active ? 'Faolsizlantirish' : 'Faollashtirish'}
                        >
                          <Power size={14} />
                        </button>
                        <button
                          onClick={() => handleDelete(v)}
                          className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-rose-400 hover:bg-slate-800 text-xs transition"
                          title="O'chirish"
                        >
                          <Trash2 size={14} />
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

      {/* Upload Modal */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-semibold text-white text-base">Video Yuklash</h3>
              <button
                onClick={() => setUploadModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleUpload} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Video Sarlavhasi
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="masalan: Rasmiy Promo Video"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Video Fayl (.mp4, max 100MB)
                </label>
                <input
                  type="file"
                  accept="video/mp4"
                  onChange={handleFileChange}
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Foydalanuvchiga biriktirish (Ixtiyoriy)
                </label>
                <select
                  value={ownerId}
                  onChange={(e) => setOwnerId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Umumiy video (barchaga)</option>
                  {usersList.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} (@{u.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="is_default"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="is_default" className="text-xs text-slate-300">
                  Umumiy (Default) video qilib belgilash
                </label>
              </div>

              {/* Progress bar */}
              {uploadProgress !== null && (
                <div className="space-y-1 pt-1">
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Yuklanmoqda...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-indigo-600 h-full rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setUploadModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-sm"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={uploading}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold transition disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {uploading && <Loader2 size={15} className="animate-spin" />}
                  <span>Yuklash</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Assign Owner Modal */}
      {assignModalOpen && selectedVideo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-semibold text-white text-base">Video Egasini Biriktirish</h3>
              <button
                onClick={() => setAssignModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleAssignOwnerSubmit} className="p-6 space-y-4">
              <div>
                <p className="text-xs text-slate-400 mb-3">
                  Tanlangan video: <span className="font-semibold text-white">{selectedVideo.title}</span>
                </p>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Foydalanuvchi tanlang
                </label>
                <select
                  value={targetOwnerId}
                  onChange={(e) => setTargetOwnerId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Umumiy video qilish (egasi olib tashlanadi)</option>
                  {usersList.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} (ID #{u.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setAssignModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-sm"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={assigning}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold transition disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {assigning && <Loader2 size={15} className="animate-spin" />}
                  <span>Saqlash</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
