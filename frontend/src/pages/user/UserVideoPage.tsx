import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import type { PublishStatus, VideoItem, CampaignPost } from '../../types';
import {
  Film,
  Camera as Instagram,
  Send,
  Loader2,
  ShieldCheck,
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ChevronRight,
  Info
} from 'lucide-react';

export const UserVideoPage: React.FC = () => {
  const { user, refreshProfile } = useAuth();
  const { showToast } = useToast();

  const [step, setStep] = useState(1);
  const [video, setVideo] = useState<VideoItem | null>(null);
  const [publishStatus, setPublishStatus] = useState<PublishStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [uploading, setUploading] = useState(false);

  const isConnected = user?.instagram_user?.status === 'connected';

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [videosRes, statusRes] = await Promise.all([
          apiClient.get('/api/videos/'),
          apiClient.get<PublishStatus>('/api/user/publish-status/'),
        ]);

        const videoList = videosRes.data.results || videosRes.data || [];
        setVideo(videoList.length > 0 ? videoList[0] : null);
        setPublishStatus(statusRes.data);

        // Logic to auto-advance steps based on state
        if (!isConnected) {
          setStep(1);
        } else if (videoList.length === 0) {
          setStep(2);
        } else if (statusRes.data?.status === 'published' || statusRes.data?.status === 'queued') {
          setStep(4);
        } else {
          setStep(3); // Ready to choose method
        }
      } catch {
        showToast('Maʼlumotlarni yuklab boʻlmadi', 'error');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [isConnected]);

  // OAuth handle
  const handleConnectOAuth = async () => {
    try {
      setConnecting(true);
      const res = await apiClient.get('/api/user/connect-instagram/');
      if (res.data.auth_url) window.location.href = res.data.auth_url;
    } catch {
      showToast('Instagramga ulanishda xatolik', 'error');
      setConnecting(false);
    }
  };

  const handlePublish = async () => {
    try {
      setPublishing(true);
      const res = await apiClient.post('/api/user/publish/');
      showToast(res.data.message || 'Navbatga qoʻyildi', 'success');
      setStep(4);
      // fetch status again
      const statusRes = await apiClient.get<PublishStatus>('/api/user/publish-status/');
      setPublishStatus(statusRes.data);
    } catch (err: any) {
      showToast(err.detail || 'Xatolik', 'error');
    } finally {
      setPublishing(false);
    }
  };

  const cleanFileName = (path: string | undefined) => {
    if (!path) return 'Nomsiz video';
    const parts = path.split('/');
    let name = parts[parts.length - 1];
    name = name.replace(/^[a-zA-Z0-9]+_/, ''); // Basic cleanup for ugly hash prefixes
    if (name.length > 20) return name.substring(0, 20) + '...mp4';
    return name;
  };

  if (loading) {
    return <div className="animate-pulse space-y-4"><div className="h-20 bg-slate-800 rounded-xl" /><div className="h-64 bg-slate-800 rounded-xl" /></div>;
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="mb-8">
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">Reels Joylash</h1>
        <p className="text-slate-400 text-sm mt-1">Bosqichma-bosqich videoni Instagramga yuklash</p>
      </div>

      {/* Stepper Header */}
      <div className="flex items-center justify-between mb-8 relative">
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-full h-0.5 bg-slate-800 -z-10"></div>
        {[1, 2, 3, 4].map((s) => (
          <div key={s} className="flex flex-col items-center gap-2 bg-slate-950 px-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all ${
              step === s ? 'bg-indigo-600 border-indigo-600 text-white shadow-[0_0_15px_rgba(79,70,229,0.5)]' :
              step > s ? 'bg-emerald-500 border-emerald-500 text-slate-900' :
              'bg-slate-900 border-slate-700 text-slate-500'
            }`}>
              {step > s ? <CheckCircle2 size={16} /> : s}
            </div>
            <span className={`text-[10px] font-semibold uppercase tracking-wider hidden sm:block ${step === s ? 'text-indigo-400' : 'text-slate-500'}`}>
              {s === 1 ? 'Ulanish' : s === 2 ? 'Video' : s === 3 ? 'Usul' : 'Natija'}
            </span>
          </div>
        ))}
      </div>

      {/* Step 1: Connect Instagram */}
      {step === 1 && (
        <div className="bg-slate-900 rounded-2xl p-6 md:p-8 border border-slate-800 shadow-xl text-center space-y-5 animate-in fade-in zoom-in-95">
          <div className="w-16 h-16 bg-pink-500/10 rounded-full flex items-center justify-center mx-auto text-pink-500 border border-pink-500/20">
            <Instagram size={32} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Instagramni ulang</h2>
            <p className="text-sm text-slate-400 mt-2 max-w-sm mx-auto leading-relaxed">
              Tizim avtomatik videoni joylashi va ko'rishlar statistikasini kuzatishi uchun Instagram akkauntingizni ulashingiz kerak.
            </p>
          </div>
          <button
            onClick={handleConnectOAuth}
            disabled={connecting}
            className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-pink-600 to-indigo-600 hover:opacity-90 text-white px-6 py-3 rounded-xl text-sm font-bold shadow-lg shadow-pink-500/25 transition w-full sm:w-auto"
          >
            {connecting ? <Loader2 size={18} className="animate-spin" /> : <Instagram size={18} />}
            <span>Instagram bilan davom etish</span>
          </button>
        </div>
      )}

      {/* Step 2: Video Selection */}
      {step === 2 && (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 shadow-xl overflow-hidden animate-in fade-in slide-in-from-right-4">
          <div className="p-6 border-b border-slate-800">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Film className="text-indigo-400" />
              Videoni tayyorlash
            </h2>
            <p className="text-sm text-slate-400 mt-1">Loyiha umumiy videosini ishlating yoki shaxsiy yuklang.</p>
          </div>
          
          <div className="p-6 flex flex-col md:flex-row gap-6">
            <div className="flex-1 space-y-4">
              {video ? (
                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-slate-400">Tanlangan video</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Tayyor</span>
                  </div>
                  <div className="font-medium text-white truncate text-sm" title={video.title || video.file}>
                    {video.title || cleanFileName(video.file)}
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl flex gap-3 text-amber-200/80 text-xs">
                  <Info size={16} className="shrink-0 text-amber-400 mt-0.5" />
                  <p>Hozircha video yo'q. Administrator umumiy video qo'shishi yoki o'zingiz yuklashingiz mumkin.</p>
                </div>
              )}

              <button
                onClick={() => setStep(3)}
                disabled={!video}
                className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3 rounded-xl text-sm font-bold shadow-md transition disabled:opacity-50"
              >
                <span>Keyingi qadam</span>
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Publish Method */}
      {step === 3 && (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 shadow-xl p-6 animate-in fade-in slide-in-from-right-4 space-y-6">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Send className="text-indigo-400" />
              Joylash usulini tanlang
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Auto Publish */}
            <div className="bg-slate-950 border border-indigo-500/40 rounded-xl p-5 relative overflow-hidden group hover:border-indigo-500 transition cursor-pointer" onClick={handlePublish}>
              <div className="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition">
                <Send size={64} />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Avtomatik Joylash</h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-4">
                Tizim Reels videoni Instagram sahifangizga 1 bosishda o'zi joylaydi va barcha nastroykalarni to'g'rilaydi.
              </p>
              <button disabled={publishing} className="w-full py-2 bg-indigo-600/20 text-indigo-400 font-semibold rounded-lg text-xs group-hover:bg-indigo-600 group-hover:text-white transition">
                {publishing ? 'Joylanyapti...' : 'Shu usulda joylash'}
              </button>
            </div>

            {/* Manual Publish */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-5">
              <h3 className="text-base font-bold text-white mb-2 flex items-center gap-2">
                O'zim joylayman <span className="text-[9px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400">Manual</span>
              </h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-4">
                Instagram ilovangizdan kirib videoni o'zingiz joylaysiz. Captionga quyidagi kodni yozish shart:
              </p>
              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 font-mono text-amber-400 text-center text-sm font-bold tracking-wider mb-2">
                {publishStatus?.code || "KOD_KUTILMOQDA"}
              </div>
              <button onClick={() => {}} className="w-full py-2 bg-slate-800 text-slate-300 hover:text-white font-semibold rounded-lg text-xs transition">
                Tasdiqlash (Joyladim)
              </button>
            </div>
          </div>

          <button onClick={() => setStep(2)} className="text-xs text-slate-500 hover:text-slate-300 font-medium">
            ← Ortga qaytish
          </button>
        </div>
      )}

      {/* Step 4: Result */}
      {step === 4 && (
        <div className="bg-slate-900 rounded-2xl border border-slate-800 shadow-xl p-6 md:p-8 text-center animate-in fade-in zoom-in-95 space-y-4">
          <div className="w-16 h-16 bg-emerald-500/10 rounded-full flex items-center justify-center mx-auto text-emerald-400 border border-emerald-500/20 mb-2">
            <CheckCircle2 size={32} />
          </div>
          <h2 className="text-xl font-bold text-white">Tabriklaymiz!</h2>
          <p className="text-sm text-slate-400 max-w-sm mx-auto">
            Videongiz muvaffaqiyatli Instagram Reels ro'yxatiga qo'shildi va kuzatilmoqda.
          </p>
          
          <div className="pt-4 flex flex-col sm:flex-row justify-center gap-3">
             {publishStatus?.permalink && (
                <a href={publishStatus.permalink} target="_blank" rel="noreferrer" className="inline-flex justify-center items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition">
                  <ExternalLink size={16} /> Instagramda ko'rish
                </a>
             )}
             <button onClick={() => window.location.href='/app/posts'} className="inline-flex justify-center items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition shadow-md">
                Statistikaga o'tish
             </button>
          </div>
        </div>
      )}
    </div>
  );
};
