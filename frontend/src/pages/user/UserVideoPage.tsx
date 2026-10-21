import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import type { PublishStatus, VideoItem } from '../../types';
import {
  Film,
  Camera as Instagram,
  Send,
  RotateCcw,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ShieldCheck,
  UploadCloud,
  FileVideo,
  Info,
} from 'lucide-react';

export const UserVideoPage: React.FC = () => {
  const { user, refreshProfile } = useAuth();
  const { showToast } = useToast();

  const [video, setVideo] = useState<VideoItem | null>(null);
  const [publishStatus, setPublishStatus] = useState<PublishStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [connecting, setConnecting] = useState(false);

  // Video Upload states
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [videoTitle, setVideoTitle] = useState('');

  const pollIntervalRef = useRef<any>(null);

  const isConnected = user?.instagram_user?.status === 'connected';

  const fetchData = async () => {
    try {
      setLoading(true);
      const [videosRes, statusRes] = await Promise.all([
        apiClient.get('/api/videos/'),
        apiClient.get<PublishStatus>('/api/user/publish-status/'),
      ]);

      const videoList = videosRes.data.results || videosRes.data || [];
      if (videoList.length > 0) {
        setVideo(videoList[0]);
      } else {
        setVideo(null);
      }
      setPublishStatus(statusRes.data);
    } catch {
      showToast('Maʼlumotlarni yuklab boʻlmadi', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Polling logic when status is queued or publishing
  useEffect(() => {
    if (publishStatus?.status === 'queued' || publishStatus?.status === 'publishing') {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const res = await apiClient.get<PublishStatus>('/api/user/publish-status/');
          setPublishStatus(res.data);
          if (res.data.status === 'published' || res.data.status === 'failed') {
            clearInterval(pollIntervalRef.current);
            refreshProfile();
            if (res.data.status === 'published') {
              showToast('Video muvaffaqiyatli Instagram Reelsga joylandi!', 'success');
            } else if (res.data.status === 'failed') {
              showToast(res.data.error || 'Video joylashda xatolik yuz berdi.', 'error');
            }
          }
        } catch {
          // ignore polling error
        }
      }, 4000);
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [publishStatus?.status]);

  const handleConnectInstagram = async () => {
    try {
      setConnecting(true);
      const res = await apiClient.get('/api/user/connect-instagram/');
      if (res.data.auth_url) {
        window.location.href = res.data.auth_url;
      }
    } catch (err: any) {
      showToast(err.detail || 'Ulanish manzilini olib boʻlmadi', 'error');
    } finally {
      setConnecting(false);
    }
  };

  const handlePublish = async () => {
    if (!isConnected) {
      showToast('Iltimos, avval Instagram akkauntingizni ulang', 'error');
      return;
    }

    try {
      setPublishing(true);
      const res = await apiClient.post('/api/user/publish/');
      showToast(res.data.message || 'Video joylash navbatga qoʻyildi', 'success');
      setPublishStatus({
        has_post: true,
        post_id: res.data.post_id,
        status: 'queued',
      });
    } catch (err: any) {
      showToast(err.detail || err.error || 'Videoni joylashda xatolik', 'error');
    } finally {
      setPublishing(false);
    }
  };

  const handleRetry = async () => {
    try {
      setRetrying(true);
      const res = await apiClient.post('/api/user/retry/');
      showToast(res.data.message || 'Qayta urinish navbatga qoʻyildi', 'success');
      setPublishStatus((prev) => (prev ? { ...prev, status: 'queued', error: null } : null));
    } catch (err: any) {
      showToast(err.detail || err.error || 'Qayta urinishda xatolik', 'error');
    } finally {
      setRetrying(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (!file.name.toLowerCase().endsWith('.mp4')) {
        showToast('Faqat .mp4 formatidagi videolarni yuklash mumkin', 'error');
        return;
      }
      if (file.size > 100 * 1024 * 1024) {
        showToast('Video hajmi 100MB dan oshmasligi kerak', 'error');
        return;
      }
      setSelectedFile(file);
      if (!videoTitle) {
        setVideoTitle(file.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      showToast('Iltimos, video faylni tanlang', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('title', videoTitle || selectedFile.name);

    try {
      setUploading(true);
      setUploadProgress(0);

      const res = await apiClient.post<VideoItem>('/api/user/upload-video/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
          }
        },
      });

      showToast('Shaxsiy videongiz muvaffaqiyatli yuklandi!', 'success');
      setVideo(res.data);
      setUploadModalOpen(false);
      setSelectedFile(null);
      setVideoTitle('');
      fetchData();
    } catch (err: any) {
      const msg = err.errors?.file?.[0] || err.detail || 'Videoni yuklashda xatolik yuz berdi';
      showToast(msg, 'error');
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-800 rounded w-48" />
        <div className="h-96 bg-slate-800 rounded-2xl" />
      </div>
    );
  }

  const isPublishingNow = publishStatus?.status === 'queued' || publishStatus?.status === 'publishing';
  const isPersonalVideo = Boolean(video?.owner && video.owner === user?.instagram_user?.id);

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Mening Videom
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Instagram akkauntingizga yuklanadigan video va joylash holati
          </p>
        </div>

        <button
          onClick={() => setUploadModalOpen(true)}
          className="inline-flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white px-4 py-2 rounded-xl text-sm font-semibold transition border border-slate-700 shadow-sm"
        >
          <UploadCloud size={16} className="text-indigo-400" />
          <span>{video ? 'Yangi video yuklash' : 'Video yuklash'}</span>
        </button>
      </div>

      {/* Account Status Banner */}
      <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-pink-500/10 text-pink-400 rounded-xl border border-pink-500/20">
            <Instagram size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-white text-sm">Instagram Ulanish Holati:</span>
              {isConnected ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                  <ShieldCheck size={12} /> Ulangan
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950 text-amber-400 border border-amber-800">
                  <AlertCircle size={12} /> Ulanmagan
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              {isConnected
                ? `Akkaunt: @${user?.instagram_user?.name || user?.username} (Reels ruxsati faol)`
                : 'Videoni avtomatik joylash uchun avval Instagramga ruxsat bering'}
            </p>
          </div>
        </div>

        {!isConnected && (
          <button
            onClick={handleConnectInstagram}
            disabled={connecting}
            className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-pink-600 to-indigo-600 hover:from-pink-500 hover:to-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition shadow-md disabled:opacity-50"
          >
            {connecting ? <Loader2 size={16} className="animate-spin" /> : <Instagram size={16} />}
            <span>Instagramga ulash</span>
          </button>
        )}
      </div>

      {/* Video Preview & Publish Card */}
      <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-sm">
        <div className="p-6 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Film size={20} className="text-indigo-400" />
            <h2 className="font-semibold text-white text-base">
              {video?.title || 'Video topilmadi'}
            </h2>
          </div>
          {video && (
            <span
              className={`text-xs font-medium px-2.5 py-0.5 rounded border ${
                isPersonalVideo
                  ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                  : 'bg-indigo-950 text-indigo-400 border-indigo-800'
              }`}
            >
              {isPersonalVideo ? 'Sizning shaxsiy videongiz' : 'Umumiy (Default) video'}
            </span>
          )}
        </div>

        <div className="p-6 space-y-6">
          {video?.video_url || video?.file ? (
            <div className="space-y-4">
              <div className="bg-slate-900 rounded-xl overflow-hidden max-w-sm mx-auto border border-slate-800 aspect-[9/16] max-h-[460px] flex items-center justify-center shadow-lg">
                <video
                  controls
                  src={video.video_url || video.file}
                  className="w-full h-full object-contain"
                  preload="metadata"
                />
              </div>

              {!isPersonalVideo && (
                <div className="flex items-start gap-2.5 p-3.5 bg-indigo-950/40 border border-indigo-900/50 rounded-xl text-xs text-indigo-300 max-w-lg mx-auto">
                  <Info size={16} className="mt-0.5 shrink-0 text-indigo-400" />
                  <span>
                    Hozircha o'zingizning shaxsiy videongizni yuklamagansiz. Joylash tugmasini bossangiz, tizimning rasmiy <strong>umumiy promo videosi</strong> Reels qilib joylanadi. Istasangiz, yuqoridagi <strong>"Yangi video yuklash"</strong> tugmasi orqali o'z videongizni qo'shishingiz mumkin.
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div className="p-8 bg-slate-900/60 rounded-xl border border-dashed border-slate-800 flex flex-col items-center justify-center text-center space-y-3">
              <div className="p-3 bg-slate-800 rounded-full text-slate-400">
                <Film size={36} />
              </div>
              <div>
                <h3 className="text-white font-semibold text-sm">Hozircha video mavjud emas</h3>
                <p className="text-slate-400 text-xs mt-1 max-w-sm">
                  Instagram Reelsga joylash uchun shaxsiy videongizni (.mp4, vertikal 9:16) yuklang.
                </p>
              </div>
              <button
                onClick={() => setUploadModalOpen(true)}
                className="mt-2 inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-semibold transition"
              >
                <UploadCloud size={15} />
                <span>Video yuklash</span>
              </button>
            </div>
          )}

          {/* Live Publish Status Badge */}
          {publishStatus?.has_post && (
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Joylash Holati
                </span>
                {publishStatus.status === 'queued' && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-950 text-amber-300 border border-amber-800">
                    <Loader2 size={13} className="animate-spin" /> Navbatda kutilmoqda...
                  </span>
                )}
                {publishStatus.status === 'publishing' && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800">
                    <Loader2 size={13} className="animate-spin" /> Instagram Reelsga yuklanmoqda...
                  </span>
                )}
                {publishStatus.status === 'published' && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                    <CheckCircle2 size={14} /> Muvaffaqiyatli joylandi!
                  </span>
                )}
                {publishStatus.status === 'failed' && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-800">
                    <AlertCircle size={14} /> Joylashda xatolik
                  </span>
                )}
              </div>

              {publishStatus.status === 'failed' && publishStatus.error && (
                <div className="text-xs text-rose-300 bg-rose-950/40 p-3 rounded-lg border border-rose-900/50">
                  <p className="font-semibold mb-0.5">Xato sababi:</p>
                  <p>{publishStatus.error}</p>
                </div>
              )}

              {publishStatus.permalink && (
                <div className="pt-1">
                  <a
                    href={publishStatus.permalink}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-pink-400 hover:text-pink-300 underline"
                  >
                    <span>Instagramda ko'rish</span>
                    <ExternalLink size={13} />
                  </a>
                </div>
              )}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-end gap-3 pt-2">
            {publishStatus?.status === 'failed' && publishStatus.can_retry && (
              <div className="flex flex-col items-center sm:items-end">
                <button
                  onClick={handleRetry}
                  disabled={retrying}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition disabled:opacity-50"
                >
                  {retrying ? <Loader2 size={16} className="animate-spin" /> : <RotateCcw size={16} />}
                  <span>Qayta urinish</span>
                </button>
                <span className="text-xs text-amber-500/80 mt-1">
                  Qolgan urinishlar: {publishStatus.retries_left}
                </span>
              </div>
            )}

            <div className="flex flex-col items-center sm:items-end">
              <button
                onClick={handlePublish}
                disabled={publishing || isPublishingNow || !isConnected || !publishStatus?.can_publish || !video}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-xl text-sm font-semibold transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                title={publishStatus?.can_publish_reason || (!video ? 'Video yuklanmagan' : '')}
              >
                {publishing || isPublishingNow ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Jarayonda...</span>
                  </>
                ) : (
                  <>
                    <Send size={16} />
                    <span>Instagramga joylash</span>
                  </>
                )}
              </button>
              {publishStatus?.can_publish_reason && !publishStatus.can_publish && (
                <span className="text-xs text-rose-400 mt-1 max-w-[250px] text-center sm:text-right">
                  {publishStatus.can_publish_reason}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Video Upload Modal */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl relative space-y-5 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center gap-2">
                <FileVideo className="text-indigo-400" size={20} />
                <h3 className="font-semibold text-white text-base">Shaxsiy Video Yuklash</h3>
              </div>
              <button
                onClick={() => {
                  if (!uploading) {
                    setUploadModalOpen(false);
                    setSelectedFile(null);
                  }
                }}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUploadSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Video Sarlavhasi (ixtiyoriy)
                </label>
                <input
                  type="text"
                  value={videoTitle}
                  onChange={(e) => setVideoTitle(e.target.value)}
                  placeholder="Masalan: Mening yangi promo roligim"
                  disabled={uploading}
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white focus:outline-none focus:border-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Video Fayl (.mp4, vertikal 9:16, max 100MB)
                </label>
                <div className="border-2 border-dashed border-slate-800 hover:border-slate-700 bg-slate-950 rounded-xl p-5 text-center transition">
                  <input
                    type="file"
                    id="user-video-file"
                    accept="video/mp4"
                    disabled={uploading}
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <label htmlFor="user-video-file" className="cursor-pointer flex flex-col items-center">
                    <UploadCloud size={32} className="text-indigo-400 mb-2" />
                    <span className="text-xs font-semibold text-white">
                      {selectedFile ? selectedFile.name : 'Video faylni tanlang'}
                    </span>
                    <span className="text-[11px] text-slate-500 mt-1">
                      MP4 (H.264, AAC), 9:16 vertikal, 3 soniyadan 15 daqiqagacha
                    </span>
                  </label>
                </div>
              </div>

              {uploadProgress !== null && (
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Yuklanmoqda...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all duration-200"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => {
                    setUploadModalOpen(false);
                    setSelectedFile(null);
                  }}
                  className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={uploading || !selectedFile}
                  className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-xs font-semibold transition disabled:opacity-50"
                >
                  {uploading ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      <span>Yuklanmoqda...</span>
                    </>
                  ) : (
                    <>
                      <UploadCloud size={14} />
                      <span>Yuklash</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
