import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import type { PublishStatus, VideoItem, CampaignPost, PaginatedResponse } from '../../types';
import { formatNumber, formatDate, formatTimeAgo } from '../../utils/format';
import {
  Film,
  Camera as Instagram,
  Send,
  RotateCcw,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ShieldCheck,
  UploadCloud,
  FileVideo,
  Info,
  Copy,
  Trash2,
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
  const [tokenModalOpen, setTokenModalOpen] = useState(false);
  const [customTokenInput, setCustomTokenInput] = useState('');
  const [connectingToken, setConnectingToken] = useState(false);
  const [refreshingMetrics, setRefreshingMetrics] = useState(false);

  // Video Upload states
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [videoTitle, setVideoTitle] = useState('');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // User's synced campaign posts
  const [userPosts, setUserPosts] = useState<CampaignPost[]>([]);
  const [loadingPosts, setLoadingPosts] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const pollIntervalRef = useRef<any>(null);

  const isConnected = user?.instagram_user?.status === 'connected';

  const fetchUserPosts = async () => {
    try {
      setLoadingPosts(true);
      const res = await apiClient.get<PaginatedResponse<CampaignPost>>('/api/user/posts/');
      setUserPosts(res.data.results || []);
    } catch {
      // ignore
    } finally {
      setLoadingPosts(false);
    }
  };

  const handleSync = async () => {
    try {
      setSyncing(true);
      await apiClient.post('/api/user/sync/');
      showToast("Sinxronizatsiya so'rovi yuborildi. Instagram tekshirilmoqda...", 'info');

      // 2 soniyalik polling
      let count = 0;
      const pollTimer = setInterval(async () => {
        count += 1;
        await Promise.all([fetchUserPosts(), fetchData()]);
        if (count >= 4) {
          clearInterval(pollTimer);
          setSyncing(false);
          showToast('Sinxronizatsiya yakunlandi', 'success');
        }
      }, 2000);
    } catch (err: any) {
      if (err.status === 429) {
        showToast("Minutiga 3 martadan ko'p sinxronizatsiya qilib bo'lmaydi. Biroz kuting.", 'error');
      } else {
        showToast(err.detail || err.error || "Sinxronizatsiyada xatolik yuz berdi", 'error');
      }
      setSyncing(false);
    }
  };

  const handleCopyCaption = (captionText: string) => {
    if (!captionText) {
      showToast('Kodingiz topilmadi', 'error');
      return;
    }
    navigator.clipboard.writeText(captionText);
    showToast('Caption nusxalandi!', 'success');
  };

  const handleDeletePost = async (postId: number) => {
    if (!window.confirm("Haqiqatan ham ushbu postni tarixdan o'chirmoqchimisiz?")) {
      return;
    }
    try {
      await apiClient.delete(`/api/user/posts/${postId}/`);
      showToast("Post tarixdan o'chirildi", 'success');
      fetchUserPosts();
      fetchData();
    } catch {
      showToast("Postni o'chirishda xatolik yuz berdi", 'error');
    }
  };

  // Timer while publishing is running
  useEffect(() => {
    let timer: any = null;
    if (publishStatus?.status === 'queued' || publishStatus?.status === 'publishing') {
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [publishStatus?.status]);

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
    fetchUserPosts();
  }, []);

  // Polling logic when status is queued or publishing (2 second rapid polling)
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
      }, 2000);
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [publishStatus?.status]);

  // Polling logic when video is processing or pending
  useEffect(() => {
    if (video?.id && (video.status === 'processing' || video.status === 'pending')) {
      const timer = setInterval(async () => {
        try {
          const res = await apiClient.get<VideoItem>(`/api/videos/${video.id}/`);
          if (res.data) {
            setVideo(res.data);
            if (res.data.status === 'ready') {
              clearInterval(timer);
              showToast("Video tayyor bo'ldi (9:16 Reels formati)!", 'success');
              fetchData();
            } else if (res.data.status === 'failed') {
              clearInterval(timer);
              showToast(res.data.processing_error || 'Videoni tayyorlashda xatolik yuz berdi', 'error');
            }
          }
        } catch {
          // ignore poll error
        }
      }, 2500);
      return () => clearInterval(timer);
    }
  }, [video?.id, video?.status]);

  const [disconnecting, setDisconnecting] = useState(false);

  const handleConnectInstagram = async () => {
    try {
      setConnecting(true);
<<<<<<< HEAD
      // Har bir foydalanuvchi o'zining shaxsiy/biznes akkauntini ulashi uchun OAuth havolasi olinadi
      const res = await apiClient.get('/api/user/connect-instagram/');
      if (res.data?.auth_url) {
=======
      const res = await apiClient.get('/api/user/connect-instagram/');
      if (res.data.auth_url) {
>>>>>>> origin/messi
        window.location.href = res.data.auth_url;
      } else {
        showToast("Instagram avtorizatsiya havolasini olib bo'lmadi", 'error');
      }
    } catch (err: any) {
<<<<<<< HEAD
      showToast(err.response?.data?.error || err.detail || 'Instagramga ulanishda xatolik yuz berdi', 'error');
=======
      showToast(err.detail || 'Instagramga ulanishda xatolik yuz berdi', 'error');
>>>>>>> origin/messi
    } finally {
      setConnecting(false);
    }
  };

<<<<<<< HEAD
  const handleDisconnectInstagram = async () => {
    if (!window.confirm("Instagram hisobingizni uzmoqchimisiz? Shundan so'ng yangi yoki boshqa biznes akkauntni qaytadan ulashingiz mumkin.")) {
      return;
    }
    try {
      setDisconnecting(true);
      const res = await apiClient.post('/api/user/disconnect-instagram/');
      showToast(res.data?.message || "Instagram hisobi uzildi. Endi yangi hisobingizni ulashingiz mumkin.", 'success');
      await refreshProfile();
    } catch (err: any) {
      showToast(err.response?.data?.error || "Hisobni uzishda xatolik yuz berdi", 'error');
    } finally {
      setDisconnecting(false);
=======
  const handleConnectWithToken = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customTokenInput.trim()) return;
    try {
      setConnectingToken(true);
      const res = await apiClient.post('/api/user/connect-instagram/', {
        access_token: customTokenInput.trim(),
      });
      showToast(res.data.message || 'Instagram hisobingiz muvaffaqiyatli ulandi!', 'success');
      setTokenModalOpen(false);
      setCustomTokenInput('');
      await refreshProfile();
    } catch (err: any) {
      showToast(err.detail || err.error || 'Tokenni tekshirishda xatolik yuz berdi', 'error');
    } finally {
      setConnectingToken(false);
>>>>>>> origin/messi
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

  const handleRefreshMetrics = async () => {
    if (!publishStatus?.post_id) return;
    try {
      setRefreshingMetrics(true);
      await apiClient.post(`/api/posts/${publishStatus.post_id}/check-metrics/`);
      showToast('Statistika tekshiruvi boshlandi...', 'info');
      setTimeout(async () => {
        try {
          const res = await apiClient.get<PublishStatus>('/api/user/publish-status/');
          setPublishStatus(res.data);
          showToast('Statistika yangilandi', 'success');
        } catch {}
        setRefreshingMetrics(false);
      }, 2000);
    } catch (err: any) {
      showToast(err.detail || 'Statistikani yangilab boʻlmadi', 'error');
      setRefreshingMetrics(false);
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
  const isVideoProcessing = video?.status === 'processing' || video?.status === 'pending';
  const isVideoFailed = video?.status === 'failed';

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

<<<<<<< HEAD
        {isConnected ? (
          <button
            onClick={handleDisconnectInstagram}
            disabled={disconnecting}
            className="inline-flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition border border-slate-700 shadow-sm disabled:opacity-50"
            title="Hisobni uzib, boshqa Instagram biznes akkauntini ulash"
          >
            {disconnecting ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            <span>Boshqa akkauntga ulash</span>
          </button>
        ) : (
          <button
            onClick={handleConnectInstagram}
            disabled={connecting}
            className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-pink-600 to-indigo-600 hover:from-pink-500 hover:to-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition shadow-md disabled:opacity-50"
          >
            {connecting ? <Loader2 size={16} className="animate-spin" /> : <Instagram size={16} />}
            <span>Instagramga ulash</span>
          </button>
=======
        {!isConnected && (
          <div className="flex flex-col sm:flex-row items-center gap-2">
            <button
              onClick={handleConnectInstagram}
              disabled={connecting}
              className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-pink-600 to-indigo-600 hover:from-pink-500 hover:to-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition shadow-md disabled:opacity-50"
            >
              {connecting ? <Loader2 size={16} className="animate-spin" /> : <Instagram size={16} />}
              <span>Instagram orqali ulash (OAuth)</span>
            </button>
            <button
              onClick={() => setTokenModalOpen(true)}
              className="text-xs text-indigo-400 hover:text-indigo-300 bg-slate-900 border border-slate-800 hover:border-slate-700 py-2.5 px-3.5 rounded-xl font-medium transition"
            >
              Token orqali ulash
            </button>
          </div>
>>>>>>> origin/messi
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
            <div className="flex items-center gap-2">
              {isVideoProcessing && (
                <span className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-0.5 rounded border bg-amber-950 text-amber-300 border-amber-800">
                  <Loader2 size={12} className="animate-spin" /> Tayyorlanmoqda
                </span>
              )}
              {isVideoFailed && (
                <span className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-0.5 rounded border bg-rose-950 text-rose-300 border-rose-800">
                  <AlertCircle size={12} /> Xatolik
                </span>
              )}
              {video.status === 'ready' && (
                <span className="text-xs font-medium px-2.5 py-0.5 rounded border bg-emerald-950 text-emerald-400 border-emerald-800">
                  Tayyor (9:16)
                </span>
              )}
              <span
                className={`text-xs font-medium px-2.5 py-0.5 rounded border ${
                  isPersonalVideo
                    ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                    : 'bg-indigo-950 text-indigo-400 border-indigo-800'
                }`}
              >
                {isPersonalVideo ? 'Sizning shaxsiy videongiz' : 'Umumiy (Default) video'}
              </span>
            </div>
          )}
        </div>

        <div className="p-6 space-y-6">
          {/* Video Processing Indicator */}
          {isVideoProcessing && (
            <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-950/20 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <Loader2 size={20} className="text-amber-400 animate-spin shrink-0" />
                <div>
                  <h4 className="text-sm font-semibold text-white">Video tayyorlanmoqda...</h4>
                  <p className="text-xs text-amber-300/80 mt-0.5">
                    Server videoni Instagram Reels talablariga moslab 9:16 vertikal formatga o'tkazmoqda.
                  </p>
                </div>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-amber-900/60 text-amber-300 border border-amber-700/60 font-medium">
                Konvertatsiya
              </span>
            </div>
          )}

          {/* Video Failed Indicator */}
          {isVideoFailed && (
            <div className="p-4 rounded-xl border border-rose-800/80 bg-rose-950/20 flex items-start gap-3">
              <AlertCircle size={20} className="text-rose-400 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-white">Video tayyorlashda xatolik</h4>
                <p className="text-xs text-rose-300 mt-1">
                  {video?.processing_error || "Videoni qayta ishlashda xatolik yuz berdi. Iltimos, boshqa video yuklang."}
                </p>
              </div>
            </div>
          )}
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

          {/* Real-time Publishing Pipeline Indicator */}
          {isPublishingNow && (
            <div className="p-5 rounded-2xl border border-indigo-500/40 bg-indigo-950/20 backdrop-blur-sm space-y-4 shadow-lg animate-in fade-in duration-200">
              <div className="flex items-center justify-between border-b border-indigo-900/50 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 bg-indigo-500/20 text-indigo-400 rounded-xl">
                    <Loader2 size={18} className="animate-spin" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-white text-sm">
                      {publishStatus?.status === 'queued'
                        ? "Navbatga qo'yildi..."
                        : "Instagram Meta serverida Reels yaratilmoqda..."}
                    </h4>
                    <p className="text-xs text-indigo-300/80 mt-0.5">
                      Meta algoritmi video sifatini tekshirishi va tayyorlashi 25–45 soniya oladi
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-xs font-mono font-bold text-indigo-300 bg-indigo-900/60 px-3 py-1 rounded-full border border-indigo-700/60">
                    ⏱ {elapsedSeconds}s
                  </span>
                </div>
              </div>

              {/* Step by Step visual flow */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
                <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-slate-900/80 border border-emerald-900/40">
                  <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
                  <div className="text-left">
                    <span className="text-[11px] font-semibold text-white block">1. Tayyorgarlik</span>
                    <span className="text-[10px] text-emerald-400">Token & Video ulandi</span>
                  </div>
                </div>

                <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-slate-900/80 border border-indigo-500/50 shadow-inner">
                  <Loader2 size={16} className="text-indigo-400 animate-spin shrink-0" />
                  <div className="text-left">
                    <span className="text-[11px] font-semibold text-white block">2. Meta Transcoding</span>
                    <span className="text-[10px] text-indigo-300">Formatlanmoqda ({elapsedSeconds}s)</span>
                  </div>
                </div>

                <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-slate-900/40 border border-slate-800/80 opacity-60">
                  <div className="w-4 h-4 rounded-full border border-slate-600 flex items-center justify-center text-[9px] text-slate-400">
                    3
                  </div>
                  <div className="text-left">
                    <span className="text-[11px] font-medium text-slate-400 block">3. Nashr etish</span>
                    <span className="text-[10px] text-slate-500">Reels sahifasiga chiqish</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Published Reel Showcase Card */}
          {publishStatus?.status === 'published' && (
            <div className="p-5 rounded-2xl border border-emerald-500/40 bg-emerald-950/15 backdrop-blur-sm space-y-4 shadow-lg animate-in fade-in duration-200">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-emerald-900/40 pb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-emerald-500/20 text-emerald-400 rounded-xl border border-emerald-500/30">
                    <CheckCircle2 size={22} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="font-bold text-white text-base">Videongiz Instagram Reelsda faol!</h4>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-700/60">
                        Joylandi
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      {publishStatus.posted_at
                        ? new Date(publishStatus.posted_at).toLocaleString('uz-UZ')
                        : 'Muvaffaqiyatli nashr etildi'}
                    </p>
                  </div>
                </div>

                {publishStatus.permalink && (
                  <a
                    href={publishStatus.permalink}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-pink-600 via-rose-600 to-indigo-600 hover:from-pink-500 hover:to-indigo-500 text-white px-5 py-2.5 rounded-xl text-xs font-semibold shadow-md transition transform hover:-translate-y-0.5"
                  >
                    <span>Instagramda ochish</span>
                    <ExternalLink size={14} />
                  </a>
                )}
              </div>

              {/* Metrics Grid Header */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-xs font-semibold text-slate-300">Statistika va ko'rsatkichlar:</span>
                <button
                  onClick={handleRefreshMetrics}
                  disabled={refreshingMetrics}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition disabled:opacity-50"
                  title="Statistikani Instagramdan hozir tekshirish"
                >
                  <RefreshCw size={13} className={refreshingMetrics ? "animate-spin" : ""} />
                  <span>Statistikani yangilash</span>
                </button>
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center">
                  <span className="text-[11px] text-slate-400 font-medium uppercase tracking-wider block">
                    Ko'rishlar
                  </span>
                  <span className="text-xl font-bold text-white mt-1 block">
                    {(publishStatus.views || 0).toLocaleString()}
                  </span>
                </div>
                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center">
                  <span className="text-[11px] text-slate-400 font-medium uppercase tracking-wider block">
                    Like'lar
                  </span>
                  <span className="text-xl font-bold text-rose-400 mt-1 block">
                    {(publishStatus.likes || 0).toLocaleString()}
                  </span>
                </div>
                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center">
                  <span className="text-[11px] text-slate-400 font-medium uppercase tracking-wider block">
                    Izohlar
                  </span>
                  <span className="text-xl font-bold text-indigo-400 mt-1 block">
                    {(publishStatus.comments_count || 0).toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Next Milestone Info */}
              <div className="p-3 bg-slate-900/60 border border-slate-800/80 rounded-xl flex items-center justify-between text-xs">
                <span className="text-slate-400 flex items-center gap-1.5">
                  🎁 <span>Keyingi sovrin marrasi:</span>
                </span>
                <span className="font-semibold text-amber-400">
                  500 ko'rish (avtomatik tekshiruv har 5 daqiqada)
                </span>
              </div>
            </div>
          )}

          {/* Failed State Card */}
          {publishStatus?.status === 'failed' && (
            <div className="p-4 rounded-xl border border-rose-800/80 bg-rose-950/20 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertCircle size={18} className="text-rose-400" />
                  <span className="text-sm font-semibold text-white">Joylashda xatolik yuz berdi</span>
                </div>
                <span className="text-xs text-rose-400 font-medium">
                  Qolgan urinishlar: {publishStatus.retries_left}
                </span>
              </div>
              {publishStatus.error && (
                <p className="text-xs text-rose-300 bg-rose-950/50 p-2.5 rounded-lg border border-rose-900/50">
                  {publishStatus.error}
                </p>
              )}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-end gap-3 pt-2">
            {publishStatus?.status === 'failed' && publishStatus.can_retry && (
              <button
                onClick={handleRetry}
                disabled={retrying}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition disabled:opacity-50"
              >
                {retrying ? <Loader2 size={16} className="animate-spin" /> : <RotateCcw size={16} />}
                <span>Qayta urinish ({publishStatus.retries_left})</span>
              </button>
            )}

            <div className="flex flex-col items-center sm:items-end w-full sm:w-auto">
              <button
                onClick={handlePublish}
                disabled={publishing || isPublishingNow || !isConnected || !video || isVideoProcessing || isVideoFailed}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-xl text-sm font-semibold transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                title={isVideoProcessing ? 'Video tayyorlanmoqda' : isVideoFailed ? (video?.processing_error || 'Video yaroqsiz') : publishStatus?.can_publish_reason || (!video ? 'Video yuklanmagan' : '')}
              >
                {publishing || isPublishingNow ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Jarayonda ({elapsedSeconds}s)...</span>
                  </>
                ) : isVideoProcessing ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Video tayyorlanmoqda...</span>
                  </>
                ) : publishStatus?.status === 'published' ? (
                  <>
                    <Send size={16} />
                    <span>Boshqa yangi video joylash</span>
                  </>
                ) : (
                  <>
                    <Send size={16} />
                    <span>Instagramga joylash</span>
                  </>
                )}
              </button>
              {publishStatus?.can_publish_reason &&
                !publishStatus.can_publish &&
                !isPublishingNow &&
                !isVideoProcessing &&
                publishStatus?.status !== 'published' && (
                  <span className="text-xs text-rose-400 mt-1 max-w-[250px] text-center sm:text-right">
                    {publishStatus.can_publish_reason}
                  </span>
                )}
            </div>
          </div>
        </div>
      </div>

      {/* "O'zim joylayman" Bo'limi */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Instagram className="text-pink-400" size={20} />
              O'zim joylayman
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Reels videoni o'zingiz Instagram ilovangiz orqali joylang. Tavsif (caption) ga quyidagi maxsus kodingizni kiriting.
            </p>
          </div>
          {publishStatus?.code && (
            <div className="flex items-center gap-2 bg-slate-950 px-3.5 py-1.5 rounded-xl border border-slate-800">
              <span className="text-xs text-slate-400">Sizning kodingiz:</span>
              <span className="font-mono text-base font-bold text-amber-400 tracking-wider">
                {publishStatus.code}
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Tayyor tavsif va nusxalash */}
          <div className="md:col-span-2 bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300">Tayyor Tavsif (Caption):</span>
              <button
                type="button"
                onClick={() =>
                  handleCopyCaption(
                    publishStatus?.code
                      ? `Men @brend saytida ishtirok etyapman! #brend ${publishStatus.code}`
                      : ''
                  )
                }
                disabled={!publishStatus?.code}
                className="inline-flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition disabled:opacity-50"
              >
                <Copy size={13} />
                Nusxalash
              </button>
            </div>
            <div className="p-3 bg-slate-900/90 rounded-lg border border-slate-800/80 text-xs font-mono text-slate-300 select-all">
              {publishStatus?.code
                ? `Men @brend saytida ishtirok etyapman! #brend ${publishStatus.code}`
                : "Kod aniqlanmoqda..."}
            </div>
            <p className="text-[11px] text-slate-500">
              💡 Ushbu matnni nusxalab, Instagram'da Reels joylayotganda tavsif qismiga qo'ying. Tizim kodingiz orqali postni avtomatik topadi va statistikani hisoblaydi.
            </p>
          </div>

          {/* Joyladim tugmasi */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 flex flex-col justify-between space-y-3">
            <div>
              <span className="text-xs font-semibold text-slate-300">Instagramda joyladingizmi?</span>
              <p className="text-[11px] text-slate-500 mt-1">
                Video muvaffaqiyatli chiqqanidan so'ng ushbu tugmani bosing. Tizim darhol profilingizni tekshirib, postni tasdiqlaydi.
              </p>
            </div>
            <button
              type="button"
              onClick={handleSync}
              disabled={syncing || !isConnected}
              className="w-full inline-flex items-center justify-center gap-2 bg-gradient-to-r from-pink-600 to-indigo-600 hover:from-pink-500 hover:to-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition shadow-lg disabled:opacity-50"
            >
              {syncing ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>Tekshirilmoqda...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 size={16} />
                  <span>Joyladim</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* "Mening postlarim" Jadvali */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Film className="text-indigo-400" size={20} />
              Mening postlarim
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Barcha tasdiqlangan va kuzatilayotgan Reels postlaringiz (/api/user/posts/)
            </p>
          </div>
          <button
            type="button"
            onClick={fetchUserPosts}
            disabled={loadingPosts}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg transition"
          >
            <RefreshCw size={13} className={loadingPosts ? 'animate-spin' : ''} />
            Yangilash
          </button>
        </div>

        {loadingPosts && userPosts.length === 0 ? (
          <div className="py-12 flex justify-center text-slate-400">
            <Loader2 size={24} className="animate-spin text-indigo-400" />
          </div>
        ) : userPosts.length === 0 ? (
          <div className="text-center py-10 bg-slate-950/40 rounded-xl border border-slate-800/60">
            <Film size={36} className="mx-auto text-slate-600 mb-2" />
            <p className="text-sm text-slate-400 font-medium">Hozircha hech qanday post mavjud emas</p>
            <p className="text-xs text-slate-500 mt-1">
              Instagram ilovangizdan Reels joylang va kodingizni caption'ga yozib "Joyladim" tugmasini bosing.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950/80 text-slate-400 font-medium border-b border-slate-800 uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="py-3 px-3">Video</th>
                  <th className="py-3 px-3">Kod</th>
                  <th className="py-3 px-3">Holat</th>
                  <th className="py-3 px-3">Manba</th>
                  <th className="py-3 px-3">Ko'rishlar</th>
                  <th className="py-3 px-3">Layklar</th>
                  <th className="py-3 px-3">Izohlar</th>
                  <th className="py-3 px-3">Joylandi</th>
                  <th className="py-3 px-3">Sinxronizatsiya</th>
                  <th className="py-3 px-3">Havola</th>
                  <th className="py-3 px-3 text-right">Amallar</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-normal">
                {userPosts.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-800/40 transition">
                    <td className="py-3 px-3">
                      {p.thumbnail_url ? (
                        <img
                          src={p.thumbnail_url}
                          alt="Thumbnail"
                          className="w-10 h-14 object-cover rounded-md border border-slate-700"
                        />
                      ) : (
                        <div className="w-10 h-14 bg-slate-800 rounded-md border border-slate-700 flex items-center justify-center">
                          <Film size={16} className="text-slate-500" />
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-3 font-mono font-semibold text-amber-400">
                      {p.code || '—'}
                    </td>
                    <td className="py-3 px-3">
                      {p.status === 'verified' ? (
                        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                          Tasdiqlangan
                        </span>
                      ) : p.status === 'revoked' ? (
                        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-950 text-amber-400 border border-amber-800">
                          Bekor qilingan
                        </span>
                      ) : p.status === 'rejected' ? (
                        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-rose-950 text-rose-400 border border-rose-800">
                          Rad etilgan
                        </span>
                      ) : p.status === 'deleted' ? (
                        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-rose-950 text-rose-400 border border-rose-800">
                          O'chirilgan
                        </span>
                      ) : (
                        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-800 text-slate-300">
                          {p.status}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`text-[11px] px-2 py-0.5 rounded ${
                          p.source === 'site'
                            ? 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                            : 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {p.source === 'site' ? 'Sayt' : "O'zim"}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-semibold text-white">
                      {formatNumber(p.views)}
                    </td>
                    <td className="py-3 px-3 text-slate-300">
                      {formatNumber(p.likes)}
                    </td>
                    <td className="py-3 px-3 text-slate-300">
                      {formatNumber(p.comments_count)}
                    </td>
                    <td className="py-3 px-3 text-slate-400 text-[11px]">
                      {formatDate(p.posted_at)}
                    </td>
                    <td className="py-3 px-3 text-slate-400 text-[11px]">
                      {p.last_synced_at ? `Yangilandi: ${formatTimeAgo(p.last_synced_at)}` : '—'}
                    </td>
                    <td className="py-3 px-3">
                      {p.status === 'deleted' ? (
                        <span className="text-[11px] text-rose-400 font-medium" title="Ushbu video Instagramda o'chirilgan">
                          Instagramda o'chirilgan
                        </span>
                      ) : p.permalink ? (
                        <a
                          href={p.permalink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition"
                        >
                          Ochish <ExternalLink size={12} />
                        </a>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleDeletePost(p.id)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition text-xs"
                        title="Postni tarixdan o'chirish"
                      >
                        <Trash2 size={13} />
                        <span className="hidden sm:inline">O'chirish</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
                  Video Fayl (.mp4, max 100MB)
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
                      MP4 (H.264, AAC), 3-90 soniya. Gorizontal video avtomatik 9:16 ga o'tkaziladi.
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

      {/* Shaxsiy Token orqali ulash modali */}
      {tokenModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
              <div className="flex items-center gap-2">
                <Instagram size={20} className="text-pink-500" />
                <h3 className="text-base font-semibold text-white">Instagram Token orqali ulash</h3>
              </div>
              <button
                onClick={() => setTokenModalOpen(false)}
                className="text-slate-400 hover:text-white text-lg font-bold leading-none"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Agar sizda Meta Graph API Explorer yoki Meta Business orqali olingan shaxsiy <strong>Instagram User Access Token</strong> bo'lsa, uni quyiga kiriting. Tizim uni avtomatik tekshirib, hisobingizni to'g'ridan-to'g'ri ulaydi.
            </p>

            <form onSubmit={handleConnectWithToken} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Instagram Access Token
                </label>
                <textarea
                  rows={4}
                  value={customTokenInput}
                  onChange={(e) => setCustomTokenInput(e.target.value)}
                  placeholder="IGAAY... yoki EAAB..."
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-white placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-xs font-mono resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setTokenModalOpen(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={connectingToken || !customTokenInput.trim()}
                  className="inline-flex items-center gap-2 bg-gradient-to-r from-pink-600 to-indigo-600 hover:from-pink-500 hover:to-indigo-500 text-white px-5 py-2.5 rounded-xl text-xs font-semibold transition disabled:opacity-50"
                >
                  {connectingToken ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      <span>Tekshirilmoqda...</span>
                    </>
                  ) : (
                    <span>Tekshirish va Ulash</span>
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
