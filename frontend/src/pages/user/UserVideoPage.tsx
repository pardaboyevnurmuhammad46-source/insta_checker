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
      showToast(err.detail || 'Videoni joylashda xatolik', 'error');
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
      showToast(err.detail || 'Qayta urinishda xatolik', 'error');
    } finally {
      setRetrying(false);
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

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          Mening Videom
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Instagram akkauntingizga yuklanadigan video va joylash holati
        </p>
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
              {video?.title || 'Umumiy Promo Video'}
            </h2>
          </div>
          {video?.is_default && (
            <span className="text-xs font-medium px-2.5 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800">
              Umumiy video
            </span>
          )}
        </div>

        <div className="p-6 space-y-6">
          {video?.video_url || video?.file ? (
            <div className="bg-slate-900 rounded-xl overflow-hidden max-w-lg mx-auto border border-slate-800 aspect-[9/16] max-h-[480px] flex items-center justify-center">
              <video
                controls
                src={video.video_url || video.file}
                className="w-full h-full object-contain"
                preload="metadata"
              />
            </div>
          ) : (
            <div className="h-64 bg-slate-900 rounded-xl border border-slate-800 flex flex-col items-center justify-center text-slate-500 text-sm">
              <Film size={36} className="mb-2 opacity-50" />
              <span>Hozircha faol video topilmadi</span>
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
                disabled={publishing || isPublishingNow || !isConnected || !publishStatus?.can_publish}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-xl text-sm font-semibold transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                title={publishStatus?.can_publish_reason || ''}
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
    </div>
  );
};
